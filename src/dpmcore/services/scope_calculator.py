"""Operation scope calculation service."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)

from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.dpm_xl.utils.filters import resolve_release_id
from dpmcore.dpm_xl.utils.scopes_calculator import (
    OperationScopeService,
)
from dpmcore.errors import SemanticError
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.operations import OperationScope, OperationScopeComposition
from dpmcore.orm.packaging import ModuleVersion
from dpmcore.services._precondition_codes import required_precondition_codes
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class UnsupportedDbScope(Exception):
    """Raised when no persisted, non-phantom scope exists for an operation.

    Always a request to fall back to
    :meth:`ScopeCalculatorService.calculate_from_expression` for this
    one operation — never a signal that the DB data itself is broken.
    """


@dataclass
class ScopeResult:
    """Outcome of a scope calculation.

    ``warning`` is only ever set when a ``precondition_expression`` changed the
    computed scope. ``error_source`` names the half a failure belongs to and is
    set whenever ``has_error`` is true. Neither changes ``error_message`` for a
    call that passes no precondition expression.
    """

    scopes: list[Any] = field(default_factory=list)
    total_scopes: int = 0
    is_cross_module: bool = False
    module_versions: List[int] = field(default_factory=list)
    has_error: bool = False
    error_message: Optional[str] = None
    # Set when the precondition expression changes the computed scope.
    warning: Optional[str] = None
    # Which half a failure belongs to: "expression" or "precondition".
    error_source: Optional[str] = None


class ScopeCalculatorService:
    """Calculate operation scopes for DPM-XL expressions.

    Determines which module versions are involved in an operation
    based on table references and precondition items.

    Args:
        session: An open SQLAlchemy session.
    """

    def __init__(self, session: "Session") -> None:
        """Build the service bound to ``session``."""
        self.session = session
        self._syntax = SyntaxService()
        # {release_id: {ghost_module_vid: fallback_module_vid}} (#182),
        # release-wide like ast_generator.py's own
        # ``_ghost_fallback_cache`` — :meth:`build_scope_result_from_db`
        # computes it once per *operation*, so memoising matters here
        # too.
        self._ghost_fallback_map_cache: Dict[int, Dict[int, int]] = {}
        # {module_vid: [ghost_vid, ...]} (#182) — the ghost siblings a
        # module version's own window bridges, memoised per module_vid
        # since :meth:`build_scope_result_from_db` recomputes it once
        # per operation for the same, fixed ``primary_module_vid``.
        self._ghost_chain_vids_cache: Dict[int, List[int]] = {}

    def _check_release_exists(self, release_id: Optional[int]) -> None:
        """Raise SemanticError if *release_id* does not exist."""
        if release_id is None:
            return
        exists = (
            self.session.query(Release.release_id)
            .filter(Release.release_id == release_id)
            .first()
        )
        if exists is None:
            raise SemanticError("1-21", release_id=release_id)

    @staticmethod
    def _compute_cross_module(scopes: list[Any]) -> bool:
        """Return True if any scope spans more than one module."""
        return any(
            len(
                {
                    c.module_vid
                    for c in getattr(s, "operation_scope_compositions", [])
                }
            )
            > 1
            for s in scopes
        )

    @staticmethod
    def _scope_signature(scopes: list[Any]) -> frozenset[frozenset[int]]:
        """Canonical identity of a scope set: the set of module-VID sets.

        Comparing ``module_versions`` alone would miss a re-partitioning —
        two intra-module scopes ``[[462], [513]]`` collapsing into one
        cross-module scope ``[[462, 513]]`` lists the same module versions but
        means something materially different. Comparing ``total_scopes`` alone
        would miss a coincidental equal count. The set of module sets catches
        module additions and removals, intra/cross re-grouping, splits, and the
        empty case.
        """
        return frozenset(
            frozenset(
                c.module_vid
                for c in getattr(s, "operation_scope_compositions", [])
            )
            for s in scopes
        )

    @staticmethod
    def _module_vids(scopes: list[Any]) -> List[int]:
        """Module VIDs across *scopes*, deduped in first-seen order."""
        mvids: List[int] = []
        for scope in scopes:
            for comp in getattr(scope, "operation_scope_compositions", []):
                if comp.module_vid not in mvids:
                    mvids.append(comp.module_vid)
        return mvids

    def _result_from_scopes(self, scopes: list[Any]) -> ScopeResult:
        """Project a computed scope list into a :class:`ScopeResult`."""
        return ScopeResult(
            scopes=scopes,
            total_scopes=len(scopes),
            is_cross_module=self._compute_cross_module(scopes),
            module_versions=self._module_vids(scopes),
        )

    def _operand_tables(
        self, expression: str, release_id: Optional[int]
    ) -> tuple[Any, List[str]]:
        """Parse *expression*, returning its AST and its table codes."""
        ast = self._syntax.parse(expression)
        oc = OperandsChecking(
            session=self.session,
            expression=expression,
            ast=ast,
            release_id=release_id,
        )
        return ast, (list(oc.tables.keys()) if oc.tables else [])

    def _check_tables_hosted(
        self, table_codes: List[str], release_id: Optional[int]
    ) -> None:
        """Raise ``1-13`` naming any table code no module version hosts.

        ``OperationScopeService.extract_module_info`` only raises ``1-13`` when
        *nothing* resolves, so an unhostable gate table is otherwise absorbed
        by the main expression's own rows. It still inflates the operand count,
        which usually empties the scope — but when the main expression resolves
        to a single module-info row the resolver short-circuits before counting
        operands at all, and the call would return a scope that cannot in fact
        evaluate the pair. Checking the gate's codes on their own keeps that
        case an error attributed to the gate rather than a silent wrong answer.
        """
        if not table_codes:
            return
        from dpmcore.dpm_xl.model_queries import ModuleVersionQuery

        df = ModuleVersionQuery.get_from_table_codes(
            session=self.session,
            table_codes=table_codes,
            release_id=release_id,
        )
        hosted = (
            set(df["TableCode"].dropna().unique()) if not df.empty else set()
        )
        missing = [code for code in table_codes if code not in hosted]
        if missing:
            raise SemanticError("1-13", table_version_ids=missing)

    def _run_scope(
        self,
        table_codes: List[str],
        precondition_items: List[str],
        release_id: Optional[int],
    ) -> list[Any]:
        """Resolve one scope set. A fresh service per call — it accumulates."""
        scopes, _ = OperationScopeService(
            session=self.session
        ).calculate_operation_scope(
            tables_vids=[],
            precondition_items=precondition_items,
            release_id=release_id,
            table_codes=table_codes,
        )
        return scopes

    @staticmethod
    def _scope_change_warning(
        baseline: list[Any],
        combined: list[Any],
        gate_tables: List[str],
        gate_items: List[str],
    ) -> str:
        """Describe how the precondition moved the scope."""
        before = sorted(ScopeCalculatorService._module_vids(baseline))
        after = sorted(ScopeCalculatorService._module_vids(combined))
        contributed = ", ".join(
            part
            for part in (
                f"tables {', '.join(gate_tables)}" if gate_tables else "",
                (
                    f"filing indicators {', '.join(gate_items)}"
                    if gate_items
                    else ""
                ),
            )
            if part
        )
        message = (
            "Precondition expression changes the scope of the expression: "
            f"module versions {before} -> {after} "
            f"(scopes {len(baseline)} -> {len(combined)})."
        )
        if not combined:
            message += (
                " The pair is not evaluable in any module version:"
                " no module reports every operand both halves need."
            )
        if contributed:
            message += f" Precondition operands: {contributed}."
        return message

    def calculate_from_expression(
        self,
        expression: str,
        release_id: Optional[int] = None,
        precondition_items: Optional[List[str]] = None,
        release_code: Optional[str] = None,
        *,
        precondition_expression: Optional[str] = None,
    ) -> ScopeResult:
        """Calculate scopes for *expression*, optionally gated.

        Parses the expression, runs OperandsChecking to extract table
        codes, then delegates to :class:`OperationScopeService`.
        ``precondition_items`` is the list of precondition variable
        codes that gate the validation; pass ``None`` or ``[]`` if
        the validation has no preconditions.

        When ``precondition_expression`` is supplied, the gate's own operands
        join the resolution by their matching channels — its table codes are
        unioned into ``table_codes`` and its *mandatory* precondition variable
        codes into ``precondition_items`` (unioned with any the caller passed).
        The two are not interchangeable: only ``table_codes`` resolves through
        ``get_from_table_codes``, and only ``precondition_items`` gets the
        filing-indicator filter and the ``1-14`` check. Because a module hosts
        an intra-module scope only when it supplies *every* operand, a gate
        reaching outside the expression's own modules widens the scope to
        cross-module, or empties it — which is the honest verdict, since the
        pair is only evaluable where both halves resolve. That change is
        reported in ``warning``, and a gate-attributable failure sets
        ``error_source`` to ``"precondition"`` with a prefixed message.

        The two channels treat a disjunctive gate differently, deliberately.
        Variable codes are intersected across ``or`` branches, so an optional
        filing indicator does not constrain scope. Table codes come from the
        gate's ``OperandsChecking`` pass, which does not model boolean
        structure, so every table the gate mentions is required even when only
        one branch needs it. That errs toward reporting a wider scope rather
        than missing a table the pair genuinely needs, and costs nothing on the
        real dictionary, where no persisted precondition references a table.

        Passing no ``precondition_expression`` costs nothing: no second scope
        resolution, no warning, and byte-identical error messages.

        Args:
            expression: The DPM-XL expression to scope.
            release_id: Optional release ID filter.
            precondition_items: Filing-indicator codes gating the validation.
            release_code: Optional release code (mutually exclusive
                with ``release_id``).
            precondition_expression: Optional DPM-XL gate expression.
                Keyword-only, matching ``SemanticService.validate``, so the
                pre-existing positional arguments keep their meaning.
        """
        base_items = list(precondition_items or [])
        try:
            release_id = resolve_release_id(
                self.session,
                release_id=release_id,
                release_code=release_code,
            )
            self._check_release_exists(release_id)
            _, main_tables = self._operand_tables(expression, release_id)
        except Exception as exc:
            return self._failed(exc, None)

        if precondition_expression is None:
            return self._scope_or_error(main_tables, base_items, release_id)

        try:
            gate_ast, gate_tables = self._operand_tables(
                precondition_expression, release_id
            )
            self._check_tables_hosted(gate_tables, release_id)
        except Exception as exc:
            return self._failed(exc, "precondition")
        gate_items = required_precondition_codes(gate_ast)

        table_codes = main_tables + [
            t for t in gate_tables if t not in main_tables
        ]
        items = base_items + [i for i in gate_items if i not in base_items]

        # A gate that contributed no new operand cannot move the scope, so the
        # baseline is provably identical and never computed.
        if set(table_codes) == set(main_tables) and set(items) == set(
            base_items
        ):
            return self._scope_or_error(main_tables, base_items, release_id)

        try:
            combined = self._run_scope(table_codes, items, release_id)
        except Exception as exc:
            # The gate is only to blame if the expression scopes cleanly
            # without it — settled by retrying, not guessed at.
            baseline_ok = self._resolves(main_tables, base_items, release_id)
            return self._failed(exc, "precondition" if baseline_ok else None)

        result = self._result_from_scopes(combined)
        try:
            baseline = self._run_scope(main_tables, base_items, release_id)
        except Exception:
            # The expression alone does not resolve but the pair does; treat
            # the baseline as empty so the change is still reported.
            baseline = []
        if self._scope_signature(baseline) != self._scope_signature(combined):
            result.warning = self._scope_change_warning(
                baseline, combined, gate_tables, gate_items
            )
        return result

    @staticmethod
    def _failed(exc: Exception, source: Optional[str]) -> ScopeResult:
        """Build a failing result, attributed to *source* when known.

        ``source`` is ``None`` for a failure that is the expression's own (or
        that no precondition was involved in), which keeps ``error_message``
        byte-identical to what callers saw before this argument existed.
        """
        message = str(exc)
        if source == "precondition":
            message = f"Precondition: {message}"
        return ScopeResult(
            has_error=True,
            error_message=message,
            error_source="expression" if source is None else source,
        )

    def _scope_or_error(
        self,
        table_codes: List[str],
        items: List[str],
        release_id: Optional[int],
    ) -> ScopeResult:
        """Resolve one scope set into a result, or an unattributed failure."""
        try:
            return self._result_from_scopes(
                self._run_scope(table_codes, items, release_id)
            )
        except Exception as exc:
            return self._failed(exc, None)

    def _resolves(
        self,
        table_codes: List[str],
        items: List[str],
        release_id: Optional[int],
    ) -> bool:
        """True when these operands resolve without raising."""
        try:
            self._run_scope(table_codes, items, release_id)
        except Exception:
            return False
        return True

    def calculate_from_tables(
        self,
        table_vids: List[int],
        precondition_items: Optional[List[str]] = None,
        release_id: Optional[int] = None,
        table_codes: Optional[List[str]] = None,
        release_code: Optional[str] = None,
    ) -> ScopeResult:
        """Calculate scopes directly from table version IDs."""
        try:
            release_id = resolve_release_id(
                self.session,
                release_id=release_id,
                release_code=release_code,
            )
            self._check_release_exists(release_id)
            scope_svc = OperationScopeService(session=self.session)
            scopes, _ = scope_svc.calculate_operation_scope(
                tables_vids=table_vids,
                precondition_items=precondition_items or [],
                release_id=release_id,
                table_codes=table_codes,
            )

            mvids: List[int] = []
            for scope in scopes:
                for comp in getattr(scope, "operation_scope_compositions", []):
                    vid = comp.module_vid
                    if vid not in mvids:
                        mvids.append(vid)

            return ScopeResult(
                scopes=scopes,
                total_scopes=len(scopes),
                is_cross_module=self._compute_cross_module(scopes),
                module_versions=mvids,
            )

        except Exception as exc:
            return ScopeResult(
                has_error=True,
                error_message=str(exc),
            )

    def build_scope_result_from_db(
        self,
        operation_vid: int,
        primary_module_vid: int,
        release_id: Optional[int] = None,
    ) -> ScopeResult:
        """Rebuild a ``ScopeResult`` for *operation_vid* from the DB.

        Reads every active ``OperationScope`` row for the operation —
        each already carrying its ``OperationScopeComposition`` module
        VIDs via the ORM relationship — instead of recomputing scope
        by re-parsing the expression text and re-validating every
        operand against live table data via ``OperandsChecking``. That
        re-validation is what a genuinely persisted validation's cell
        references can legitimately fail on (a wildcard/range axis
        resolved against a table that has since grown grey cells the
        validation's author never touched, for instance) — none of
        which mdpm's own export ever sees, since it reads the same
        persisted scope this reads and never re-validates it against
        live table data either.

        Excludes any scope whose only *other* composed module (besides
        *primary_module_vid*) is a #182 ghost with no fallback at
        *release_id* (see :meth:`_phantom_paired_scope_ids`), matching
        :meth:`~dpmcore.services.ast_generator.ASTGeneratorService.\
_discover_module_validations`'s own exclusion. Applied whenever a
        *release_id* is given (whether resolved from an explicit
        ``--release`` or auto-picked for ``--module-version``/
        ``--all-versions``) — per issue #182: "this fallback must apply
        consistently on every path dpmcore uses to resolve which module
        version applies". mdpm's own reference has no equivalent to
        #182 in any mode, so it is not a valid comparison here.

        When a composition names a ghost that has a fallback, it is not
        excluded, but its ``module_vid`` is substituted for the
        fallback's (see :meth:`_substitute_ghost_compositions`) — the
        persisted composition names the ghost directly, but the ghost
        itself has no table/URI structure for downstream dependency
        resolution to use, only the fallback does.

        Raises :class:`UnsupportedDbScope` when nothing usable
        survives — callers must catch this and fall back to
        :meth:`calculate_from_expression` instead.
        """
        scopes = (
            self.session.query(OperationScope)
            .filter(
                OperationScope.operation_vid == operation_vid,
                OperationScope.is_active.in_([-1, 1, True]),
            )
            .all()
        )
        if not scopes:
            raise UnsupportedDbScope(
                f"No active OperationScope rows for "
                f"operation_vid={operation_vid}"
            )

        # The release-wide map only recognises a ghost as having a
        # fallback when the ghost's *own* window covers this exact
        # release — a chain bridging more than one ghost (e.g.
        # COREP_FRTB's 3.2.0 then 3.3.0) leaves an earlier one
        # unrecognised there even though it genuinely stands in for
        # primary_module_vid too. Folding primary_module_vid's own
        # ghost chain in directly closes that gap without making the
        # release-wide map itself chain-aware.
        ghost_fallback_map: Dict[int, int] = {
            **(
                self._ghost_fallback_map(release_id)
                if release_id is not None
                else {}
            ),
            **dict.fromkeys(
                self._ghost_chain_vids(primary_module_vid), primary_module_vid
            ),
        }
        scope_ids = {s.operation_scope_id for s in scopes}
        phantom_ids = self._phantom_paired_scope_ids(
            self.session, scope_ids, primary_module_vid, ghost_fallback_map
        )
        filtered = [
            s for s in scopes if s.operation_scope_id not in phantom_ids
        ]
        if not filtered:
            raise UnsupportedDbScope(
                f"Every OperationScope for operation_vid={operation_vid} "
                "is phantom-paired"
            )

        substituted = (
            [
                self._substitute_ghost_compositions(s, ghost_fallback_map)
                for s in filtered
            ]
            if ghost_fallback_map
            else filtered
        )

        return ScopeResult(
            scopes=substituted,
            total_scopes=len(substituted),
            is_cross_module=self._compute_cross_module(substituted),
            module_versions=self._module_vids(substituted),
        )

    def _ghost_fallback_map(self, release_id: int) -> Dict[int, int]:
        """``{ghost_module_vid: fallback_module_vid}`` for *release_id*.

        Inverts :func:`ModuleVersionQuery.ghost_fallbacks` (#182): a
        fallback can stand in for several ghosts, but a ghost has at
        most one fallback per release, so the inversion is total.
        Memoised per release — :meth:`build_scope_result_from_db` and
        :meth:`_phantom_paired_scope_ids` both compute it once per
        *operation*, and it's release-wide (same reasoning as
        ast_generator.py's own ``_release_ghost_fallbacks`` cache).
        """
        cached = self._ghost_fallback_map_cache.get(release_id)
        if cached is None:
            from dpmcore.dpm_xl.model_queries import ModuleVersionQuery

            fallbacks = ModuleVersionQuery.ghost_fallbacks(
                self.session, release_id
            )
            cached = {
                ghost_vid: fallback_vid
                for fallback_vid, ghost_vids in fallbacks.items()
                for ghost_vid in ghost_vids
            }
            self._ghost_fallback_map_cache[release_id] = cached
        return cached

    def _ghost_chain_vids(self, module_vid: int) -> List[int]:
        """Every #182 ghost sibling in *module_vid*'s own contiguous chain.

        Mirrors :meth:`~dpmcore.services.ast_generator.\
ASTGeneratorService._ghosts_represented_by` — the same contiguous run
        of ghost siblings :meth:`~dpmcore.services.ast_generator.\
ASTGeneratorService._effective_end_release_id` extends a module
        version's own window through, not just whichever one ghost a
        release-wide lookup happens to resolve. Duplicated here rather
        than shared: the walk only needs ``session`` and a
        ``ModuleVersion`` row, and this service has no dependency on
        ``ASTGeneratorService`` otherwise. Memoised per *module_vid*.
        """
        cached = self._ghost_chain_vids_cache.get(module_vid)
        if cached is not None:
            return cached

        from dpmcore.orm.release_sort_order import resolve_sort_order

        mv = (
            self.session.query(ModuleVersion)
            .filter(ModuleVersion.module_vid == module_vid)
            .one_or_none()
        )
        if mv is None or mv.end_release_id is None or mv.module_id is None:
            self._ghost_chain_vids_cache[module_vid] = []
            return []

        session = self.session
        end_sort = resolve_sort_order(
            session, mv.end_release_id, role="module version end release"
        )
        siblings = (
            session.query(ModuleVersion)
            .filter(ModuleVersion.module_id == mv.module_id)
            .filter(ModuleVersion.module_vid != mv.module_vid)
            .all()
        )
        candidates = self._ghost_chain_candidates(siblings, end_sort)

        ghost_vids: List[int] = []
        boundary = end_sort
        for start_sort, is_ghost, sibling in candidates:
            if start_sort > boundary or not is_ghost:
                break
            ghost_vids.append(sibling.module_vid)
            if sibling.end_release_id is None:
                break
            sibling_end_sort = resolve_sort_order(
                session,
                sibling.end_release_id,
                role="sibling module version end release",
            )
            if sibling_end_sort > boundary:
                boundary = sibling_end_sort

        self._ghost_chain_vids_cache[module_vid] = ghost_vids
        return ghost_vids

    def _ghost_chain_candidates(
        self, siblings: List[Any], end_sort: int
    ) -> List[Tuple[int, bool, Any]]:
        """Sibling ``ModuleVersion`` rows past *end_sort*, sorted by start.

        Split out of :meth:`_ghost_chain_vids` to keep its own walk
        within the complexity limit.
        """
        from dpmcore.orm.release_sort_order import resolve_sort_order

        session = self.session

        def sort_or_none(
            release_id: Optional[int], role: str
        ) -> Optional[int]:
            if release_id is None:
                return None
            return resolve_sort_order(session, release_id, role=role)

        candidates: List[Tuple[int, bool, Any]] = []
        for sibling in siblings:
            sibling_end_sort = sort_or_none(
                sibling.end_release_id, "sibling module version end release"
            )
            if sibling_end_sort is not None and sibling_end_sort <= end_sort:
                continue
            sibling_start_sort = sort_or_none(
                sibling.start_release_id,
                "sibling module version start release",
            )
            effective_start = (
                end_sort
                if sibling_start_sort is None
                else max(sibling_start_sort, end_sort)
            )
            is_ghost = (
                sibling.from_reference_date is not None
                and sibling.to_reference_date is not None
                and sibling.from_reference_date == sibling.to_reference_date
            )
            candidates.append((effective_start, is_ghost, sibling))
        candidates.sort(key=lambda item: item[0])
        return candidates

    @staticmethod
    def _substitute_ghost_compositions(
        scope: Any, ghost_fallback_map: Dict[int, int]
    ) -> Any:
        """Return *scope* with any #182-ghost composition substituted.

        Substitutes a ghost composition's ``module_vid`` for its
        fallback's. A composition naming a ghost module directly is a real,
        persisted fact — #182's own ``OperationScopeComposition`` rows
        are written against the ghost, never against the fallback that
        represents it later — but the ghost has no table/URI structure
        of its own for downstream dependency resolution
        (``_compute_cross_module``, ``_module_vids`` and the
        ``requires`` of the script's dependency groups) to use. Each of
        those reads ``operation_scope_compositions`` off a scope via
        ``getattr`` with a default — already duck-typed — so a
        lightweight, non-persisted substitute is enough; nothing here
        touches the real ORM rows or the session.
        """
        compositions = getattr(scope, "operation_scope_compositions", [])
        if not any(c.module_vid in ghost_fallback_map for c in compositions):
            return scope
        return SimpleNamespace(
            operation_scope_id=scope.operation_scope_id,
            operation_scope_compositions=[
                SimpleNamespace(
                    operation_scope_id=c.operation_scope_id,
                    module_vid=ghost_fallback_map.get(
                        c.module_vid, c.module_vid
                    ),
                    row_guid=getattr(c, "row_guid", None),
                )
                for c in compositions
            ],
        )

    @staticmethod
    def _phantom_paired_scope_ids(
        session: "Session",
        scope_ids: Set[int],
        module_vid: int,
        ghost_fallback_map: Dict[int, int],
    ) -> Set[int]:
        """Return scope ids whose only other composed module is a dead end.

        These are the ``OperationScopeID``s whose only *other* composed
        module versions (besides *module_vid*) are all phantom (#182
        ghosts — mirrors mdpm's ``is_phantom_module_op``) **and** have
        no fallback standing in for them in *ghost_fallback_map*. A
        phantom *with* a fallback there is not void: the fallback
        substitutes for it (see :meth:`_substitute_ghost_compositions`),
        so a scope composed with such a ghost is kept.
        *ghost_fallback_map* is empty whenever no release could be
        resolved at all, which reduces this to the original rule (every
        phantom is a dead end). A scope shared with no other module at
        all is never phantom here — this only
        voids a cross-framework pairing whose counterpart neither
        really existed as its own module version, nor has anything
        current standing in for it.

        Shared by :meth:`build_scope_result_from_db` and
        :meth:`~dpmcore.services.ast_generator.ASTGeneratorService.\
_discover_module_validations`.
        """
        rows = (
            session.query(
                OperationScopeComposition.operation_scope_id,
                OperationScopeComposition.module_vid,
                ModuleVersion.from_reference_date,
                ModuleVersion.to_reference_date,
            )
            .join(
                ModuleVersion,
                ModuleVersion.module_vid
                == OperationScopeComposition.module_vid,
            )
            .filter(
                OperationScopeComposition.operation_scope_id.in_(scope_ids)
            )
            .filter(OperationScopeComposition.module_vid != module_vid)
            .all()
        )
        others_by_scope: Dict[int, List[bool]] = {}
        for scope_id, other_module_vid, from_date, to_date in rows:
            is_phantom = (
                from_date is not None
                and to_date is not None
                and from_date == to_date
            )
            is_dead_end = (
                is_phantom and other_module_vid not in ghost_fallback_map
            )
            others_by_scope.setdefault(scope_id, []).append(is_dead_end)

        return {
            scope_id
            for scope_id, flags in others_by_scope.items()
            if flags and all(flags)
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _get_module_uri(
        self,
        module_vid: int,
        mv: Optional[Any] = None,
    ) -> Optional[str]:
        """Resolve a module VID to its EBA taxonomy URI.

        The URI's release segment always comes from the release in which
        the module version was introduced (its start release), resolved
        via :meth:`_resolve_uri_release_id`. A module version's taxonomy
        is published under that release, so an unchanged module keeps its
        original release segment even inside a later report: e.g. an
        unchanged ``ae`` stays at ``.../ae/4.2/mod/ae`` in a 4.2.1 report,
        because no ``ae`` taxonomy exists at 4.2.1. The report release is
        deliberately not an input: it never sets the release segment, and
        it would not pick the module version either — the lookup filters
        by ``module_vid`` alone.

        Resolution order (in :meth:`_resolve_uri_release_id`): the static
        CSV mapping by ``(module_code, version_number)`` first; on a miss,
        the module version's ``start_release_id``.

        When *mv* is supplied the initial DB lookup is skipped.
        """
        try:
            if mv is None:
                mv = (
                    self.session.query(ModuleVersion)
                    .filter(ModuleVersion.module_vid == module_vid)
                    .first()
                )
            if not mv or not mv.module:
                return None

            module_code = mv.code
            if not module_code:
                return None

            framework = mv.module.framework
            if not framework or not framework.code:
                return None

            csv_or_release_id = self._resolve_uri_release_id(mv, module_code)
            if isinstance(csv_or_release_id, str):
                return csv_or_release_id  # CSV hit (already final URI).
            if csv_or_release_id is None:
                return None

            release_row = (
                self.session.query(Release.code)
                .filter(Release.release_id == csv_or_release_id)
                .first()
            )
            if not release_row or not release_row.code:
                return None

            return (
                "http://www.eba.europa.eu/eu/fr/xbrl/crr"
                "/fws/"
                f"{framework.code.lower()}/"
                f"{release_row.code}/mod/"
                f"{module_code.lower()}"
            )

        except Exception as exc:
            logger.warning(
                "Failed to resolve URI for module VID %s: %s",
                module_vid,
                exc,
            )
            return None

    @staticmethod
    def _resolve_uri_release_id(
        mv: Any,
        module_code: str,
    ) -> Optional[Any]:
        """Pick the release that seeds the URL's release segment.

        A module version's taxonomy is published under the release in
        which that version was introduced (its ``start_release_id``), not
        under the report release. Seeding the segment from the report
        release would build URIs like ``.../ae/4.2.1/mod/ae`` for modules
        that did not change since 4.2 and therefore have no taxonomy at
        4.2.1. So the segment is resolved from the module version itself,
        the same way for every caller.

        Returns one of:

        - ``str`` — a final URI (CSV hit, ``.json`` suffix already
          stripped). The caller must short-circuit and return it.
        - ``int`` — the release_id whose ``Release.code`` should fill
          the ``/{release}/`` segment.
        - ``None`` — nothing resolvable; caller returns ``None``.
        """
        from dpmcore.data import (
            get_module_schema_ref_by_version,
        )

        if mv.version_number:
            static = get_module_schema_ref_by_version(
                module_code, mv.version_number
            )
            if static:
                return static.removesuffix(".json")
        return mv.start_release_id
