"""Semantic validation service — requires a database session."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Callable, Optional, cast

from sqlalchemy import func

from dpmcore.dpm_xl.ast.nodes import (
    AST,
    ParameterRef,
    canonical_param_type,
    parameter_default_value,
)
from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.dpm_xl.model_queries import ModuleVersionQuery, TableVersionQuery
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.dpm_xl.utils.filters import filter_by_release, resolve_release_id
from dpmcore.dpm_xl.warning_collector import collect_warnings
from dpmcore.errors import SemanticError
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.operations import (
    OperandReference,
    OperationNode,
    OperationScope,
    OperationScopeComposition,
    OperationVersion,
)
from dpmcore.orm.query_utils import chunked_in
from dpmcore.orm.variables import VariableVersion
from dpmcore.services._parameters import merge_parameters
from dpmcore.services._precondition_codes import (
    extract_precondition_codes,
    gate_satisfiable,
)
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ParameterInfo:
    """Declared metadata for a parameter referenced by an expression.

    This is the runtime-binding contract: dpmcore reports which parameters an
    expression needs (and their declared types/defaults); the downstream engine
    resolves and binds their values.

    ``is_set`` is a derived property (``Set`` prefix of the canonical
    ``declared_type``), not a stored field, so there is one source of truth for
    set-ness.
    """

    code: str
    declared_type: str
    default: Any = None

    @property
    def is_set(self) -> bool:
        """``True`` for the set variants.

        The canonical ``declared_type`` is ``SetNumber``/``SetItem``/…; no
        scalar type name starts with ``Set``, so the prefix is unambiguous.
        """
        return self.declared_type.startswith("Set")


@dataclass(frozen=True)
class SemanticResult:
    """Outcome of a semantic validation.

    When a ``precondition_expression`` is supplied, ``is_valid`` is the verdict
    for the **pair**: it is ``False`` if either the expression or its gate
    failed, because a row whose gate does not resolve is not evaluable. The
    gate's own independent verdict is ``precondition``; ``error_source`` says
    which half a failure belongs to — ``"expression"``, ``"precondition"``, or
    ``"both"`` — so attribution never needs string matching. ``error_message``
    names *every* failure that occurred, each from the gate prefixed
    ``"Precondition: "``, and ``warning`` merges both halves' warnings the same
    way, so a caller reading only the outer result never misses half the story.
    ``error_code`` holds a single value: the expression's when it failed,
    otherwise the gate's.

    ``precondition`` is ``None`` exactly when the caller supplied no gate —
    never as a way of signalling that one failed. On that nested result
    ``error_source`` is ``"precondition"`` whenever it failed, since it
    describes the gate alone.
    """

    is_valid: bool
    error_message: Optional[str]
    error_code: Optional[str]
    expression: str
    results: Optional[Any] = None
    warning: Optional[str] = None
    parameters: tuple[ParameterInfo, ...] = field(default_factory=tuple)
    # Populated only when a precondition expression was supplied.
    precondition: Optional["SemanticResult"] = None
    # Which input a failure belongs to: "expression", "precondition", or
    # "both". Set whenever ``is_valid`` is False, matching ``ScopeResult``.
    error_source: Optional[str] = None


def _parameters_from_oc(
    oc: OperandsChecking,
) -> tuple[ParameterInfo, ...]:
    """Collect referenced parameters from an OperandsChecking pass.

    Deduplicated by code, preserving first-seen order. A parameter is an
    execution-time input bound to a single value across every expression that
    co-executes with it, so its declared type is intrinsic: all references to a
    given code must declare the same type. Conflicting redeclarations within an
    expression raise ``3-8``. Defaults are per-reference fallbacks and are
    intentionally *not* compared (they never reach the scope-wide registry).
    """
    seen: dict[str, ParameterInfo] = {}
    for node in oc.parameters:
        # Surface the engine's canonical type name (``number`` -> ``Number``).
        declared = canonical_param_type(node.param_type)
        existing = seen.get(node.code)
        if existing is None:
            seen[node.code] = ParameterInfo(
                code=node.code,
                declared_type=declared,
                default=parameter_default_value(node.default),
            )
        elif existing.declared_type != declared:
            raise SemanticError(
                "3-8",
                parameter=node.code,
                type_1=existing.declared_type,
                type_2=declared,
            )
    return tuple(seen.values())


# Distinctive opener of a parameter reference, used as a DB-side pre-filter.
# Selection prefixes are t/g/o/v/p, so ``{p`` marks a parameter reference.
_PARAM_MARKER = "%{p%"

# Whitespace characters stripped from an expression before the ``{p`` match.
_WHITESPACE_CHARS = (" ", "\t", "\n", "\r")


def _whitespace_insensitive(column: Any) -> Any:
    """Wrap a text column so a LIKE match ignores whitespace.

    DPM-XL expressions can be hand-written, so a parameter reference may carry
    spaces after the brace (``{ p_x}``) or span lines. Stripping
    space/tab/newline/CR from the column *at query time* lets the ``{p`` marker
    match regardless of layout. The stored expression is untouched — only the
    comparison is normalised — and ``_declarations`` re-parses the raw text
    authoritatively. ``REPLACE`` is standard across SQLite/PostgreSQL/SQL
    Server, and ``NULL`` survives every ``REPLACE`` (so ``NULL`` rows are still
    excluded by ``LIKE``).
    """
    stripped = column
    for whitespace in _WHITESPACE_CHARS:
        stripped = func.replace(stripped, whitespace, "")
    return stripped


def _walk_parameter_refs(node: object) -> list[ParameterRef]:
    """Collect every ``ParameterRef`` in an AST (no DB lookups)."""
    found: list[ParameterRef] = []

    def walk(current: object) -> None:
        if isinstance(current, ParameterRef):
            found.append(current)
        if isinstance(current, AST):
            for value in vars(current).values():
                walk(value)
        elif isinstance(current, list):
            for item in current:
                walk(item)

    walk(node)
    return found


def _module_vids_for(
    session: "Session", table_codes: list[str], release_id: Optional[int]
) -> frozenset[int]:
    """Resolve the module versions an expression's tables belong to."""
    if not table_codes:
        return frozenset()
    df = ModuleVersionQuery.get_from_table_codes(
        session=session, table_codes=table_codes, release_id=release_id
    )
    if df.empty:
        return frozenset()
    return frozenset(int(vid) for vid in df["ModuleVID"].tolist())


def _as_gate_verdict(result: SemanticResult) -> SemanticResult:
    """Stamp a gate's own verdict with the half it describes.

    A standalone validation attributes its failure to ``"expression"``,
    because that is the only half it knows about. Nested under
    ``SemanticResult.precondition`` that reads as a claim about the *main*
    expression, so the gate's verdict is restamped: on the nested result the
    failing half is always the precondition.
    """
    if result.is_valid:
        return result
    return replace(result, error_source="precondition")


class SemanticService:
    """Validate DPM-XL expressions against the data dictionary.

    Args:
        session: An open SQLAlchemy session bound to a DPM database.
    """

    def __init__(self, session: "Session") -> None:
        """Build the service bound to ``session``."""
        self.session = session
        self._syntax = SyntaxService()
        # Exposed after each validate() call for downstream consumers.
        self.ast: Any = None
        self.oc_data: Any = None
        self.oc_tables: Any = None
        self.oc_parameters: tuple[ParameterInfo, ...] | None = None
        self.oc_operations_data: Any = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def validate(
        self,
        expression: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
        *,
        precondition_expression: Optional[str] = None,
        precondition_operation_vid: Optional[int] = None,
    ) -> SemanticResult:
        """Full semantic validation of *expression* and its optional gate.

        Returns a :class:`SemanticResult` — never raises on validation
        failure.

        A referenced parameter's declared type is also checked against
        co-scoped operations already in the database (raising ``3-8`` on a
        clash). This lookup only runs when the expression actually references a
        parameter and is scoped in SQL to co-located operations, so it adds no
        overhead to a parameter-free database.

        When ``precondition_expression`` is supplied, both halves are validated
        against the same release, resolved once, and ``is_valid`` becomes the
        verdict for the **pair** — ``False`` if either half failed, since a row
        whose gate does not resolve is not evaluable. ``precondition`` carries
        the gate's own verdict and ``error_source`` names the failing half.
        Two checks then apply that a single expression never sees:

        * The gate is validated *as a gate*, so its result must be a boolean
          (``2-1``). A numeric selection is a valid expression but not a valid
          precondition.
        * Parameter declarations are cross-checked across the halves
          (``3-8``). A gate co-executes with its expression, so a parameter
          bound across them must declare one type.

        The halves are evaluated gate-first, so the per-call state this service
        publishes (``ast``, ``oc_data``, ``oc_tables``, ``oc_parameters``,
        ``oc_operations_data``)
        describes the *main* expression when the call returns — what existing
        consumers of this method already rely on.

        Args:
            expression: The DPM-XL expression to validate.
            release_id: Optional release ID filter. When neither this nor
                ``release_code`` is given, defaults to the latest release.
            release_code: Optional release code (mutually exclusive
                with ``release_id``).
            precondition_expression: Optional DPM-XL gate expression.
                Keyword-only, and appended after the pre-existing arguments,
                so ``validate(expr, 5)`` still means ``release_id=5``. When
                ``None``, the result is exactly as before this argument
                existed: ``precondition`` is ``None`` and ``is_valid``
                describes ``expression`` alone.
            precondition_operation_vid: Optional VID of a separately
                persisted ``OperationVersion`` gating this one (its
                ``precondition_operation_vid`` self-FK), distinct from
                ``precondition_expression``. Cross-checked against the
                current module scope when ``expression`` is valid
                (``7-3``/``7-4``/``7-5``); a VID with nothing to check
                against is accepted.
        """
        try:
            resolved = self._resolve_release(release_id, release_code)
        except SemanticError as exc:
            code = getattr(exc, "code", None)
            return self._resolution_failure(
                expression, precondition_expression, exc, code
            )
        except Exception as exc:
            return self._resolution_failure(
                expression, precondition_expression, exc, "UNKNOWN"
            )

        if precondition_expression is None:
            result = self._validate_resolved(expression, resolved)
        else:
            # Gate first, main expression last: the trailing ``self.ast`` /
            # ``self.oc_*`` must describe the main expression (see
            # docstring).
            precondition = _as_gate_verdict(
                self._validate_resolved(
                    precondition_expression, resolved, as_precondition=True
                )
            )
            main = self._validate_resolved(expression, resolved)
            result = self._combine(main, self._cross_check(main, precondition))

        if result.is_valid and precondition_operation_vid is not None:
            try:
                self._check_precondition_link(
                    precondition_operation_vid, resolved
                )
            except SemanticError as exc:
                code = getattr(exc, "code", None)
                return self._precondition_link_failure(result, exc, code)
            except Exception as exc:
                return self._precondition_link_failure(result, exc, "UNKNOWN")
        return result

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _resolve_release(
        self,
        release_id: Optional[int],
        release_code: Optional[str],
    ) -> Optional[int]:
        """Resolve the release once, raising on an unknown or absent one."""
        resolved = resolve_release_id(
            self.session,
            release_id=release_id,
            release_code=release_code,
        )
        # Default to the latest release when none is specified, matching
        # the DPM-XL engine convention (see scopes_calculator). This keeps
        # the co-scope parameter check release-scoped instead of spanning
        # every release. ``None`` only survives on an empty schema.
        if resolved is None:
            resolved = ModuleVersionQuery.get_last_release(self.session)
        if resolved is not None:
            exists = (
                self.session.query(Release.release_id)
                .filter(Release.release_id == resolved)
                .first()
            )
            if exists is None:
                raise SemanticError("1-21", release_id=resolved)
        return resolved

    def _validate_resolved(
        self,
        expression: str,
        release_id: Optional[int],
        *,
        as_precondition: bool = False,
    ) -> SemanticResult:
        """Validate *expression* against an already-resolved release.

        Args:
            expression: The DPM-XL expression to validate.
            release_id: Release the expression is checked against.
            as_precondition: When ``True``, the expression is treated as a
                precondition gate, so the analyzer enforces a boolean result
                (``2-1``) even though the expression itself contains no
                precondition item.
        """
        try:
            with collect_warnings() as wc:
                # ``parse`` is inside the collector so warnings emitted from
                # AST construction (e.g. deprecated ``"null"`` string literal
                # in ``visitLiteral``) are captured alongside the ones from
                # the analyzer pass.
                ast = self._syntax.parse(expression)
                self.ast = ast

                oc = OperandsChecking(
                    session=self.session,
                    expression=expression,
                    ast=ast,
                    release_id=release_id,
                )
                self.oc_data = oc.data
                self.oc_tables = oc.tables
                self.oc_parameters = _parameters_from_oc(oc)
                self.oc_operations_data = oc.operations_data

                analyzer = InputAnalyzer(expression)
                analyzer.data = oc.data
                analyzer.key_components = oc.key_components
                analyzer.open_keys = oc.open_keys
                analyzer.preconditions = as_precondition or oc.preconditions
                analyzer.session = self.session
                analyzer.release_id = release_id

                results = analyzer.visit(ast)

            if self.oc_parameters:
                self._check_persisted_scope(
                    {p.code: p.declared_type for p in self.oc_parameters},
                    list(oc.tables.keys()) if oc.tables else [],
                    release_id,
                )

            return SemanticResult(
                is_valid=True,
                error_message=None,
                error_code=None,
                expression=expression,
                results=results,
                warning=wc.get_combined_warning(),
                parameters=self.oc_parameters,
            )

        except SemanticError as exc:
            return self._failure(expression, exc, getattr(exc, "code", None))
        except Exception as exc:
            return self._failure(expression, exc, "UNKNOWN")

    def _clear_published_state(self) -> None:
        """Clear per-call state exposed on ``self`` after a failure.

        Leaving the previous call's AST/``oc_*`` readable after a failure
        invited consumers to act on stale state.
        """
        self.ast = None
        self.oc_data = None
        self.oc_tables = None
        self.oc_parameters = None
        self.oc_operations_data = None

    def _failure(
        self,
        expression: str,
        exc: Exception,
        error_code: Optional[str],
    ) -> SemanticResult:
        """Clear the published per-call state and build a failing result."""
        self._clear_published_state()
        return SemanticResult(
            is_valid=False,
            error_message=str(exc),
            error_code=error_code,
            expression=expression,
            error_source="expression",
        )

    def _precondition_link_failure(
        self,
        result: SemanticResult,
        exc: Exception,
        error_code: Optional[str],
    ) -> SemanticResult:
        """Fail result over a precondition-link mismatch.

        Unlike :meth:`_failure`, ``expression``/gate already validated, so
        the existing halves survive and ``error_source`` is
        ``"precondition"`` rather than ``"expression"``.
        """
        self._clear_published_state()
        return replace(
            result,
            is_valid=False,
            error_message=str(exc),
            error_code=error_code,
            error_source="precondition",
        )

    def _resolution_failure(
        self,
        expression: str,
        precondition_expression: Optional[str],
        exc: Exception,
        error_code: Optional[str],
    ) -> SemanticResult:
        """Report a release-resolution failure across every supplied half.

        The failure belongs to neither half — no expression was even parsed —
        so it is attributed to ``"expression"`` and mirrored onto the gate's
        own verdict when one was supplied.
        """
        failure = self._failure(expression, exc, error_code)
        if precondition_expression is None:
            return failure
        return replace(
            failure,
            error_source="expression",
            precondition=_as_gate_verdict(
                self._failure(precondition_expression, exc, error_code)
            ),
        )

    @staticmethod
    def _cross_check(
        main: SemanticResult, precondition: SemanticResult
    ) -> SemanticResult:
        """Reject a parameter declared with different types across the halves.

        A gate co-executes with its expression, so a parameter bound across the
        pair must declare one type. The clash is reported on the *precondition*
        half — it carries the second, conflicting declaration — leaving the
        main expression's own verdict intact.
        """
        if not (
            main.is_valid
            and precondition.is_valid
            and main.parameters
            and precondition.parameters
        ):
            return precondition
        accumulated: dict[str, ParameterInfo] = {}
        try:
            merge_parameters(accumulated, main.parameters)
            merge_parameters(accumulated, precondition.parameters)
        except SemanticError as exc:
            return SemanticResult(
                is_valid=False,
                error_message=str(exc),
                error_code=getattr(exc, "code", None),
                expression=precondition.expression,
                error_source="precondition",
            )
        return precondition

    @staticmethod
    def _combine(
        main: SemanticResult, precondition: SemanticResult
    ) -> SemanticResult:
        """Fold the gate's verdict into the pair's result.

        Every summary field on the outer result describes the *pair*, so a
        caller reading only that result never misses half the story:
        ``is_valid`` is pair-wide, warnings from both halves are merged, and
        every failure that occurred is named — so ``is_valid=False`` never
        arrives without a complete explanation. The ``"Precondition: "`` prefix
        matches ``ScopeResult``'s, so both services read the same way.
        """
        warning = main.warning
        if precondition.warning:
            gate_warning = f"Precondition: {precondition.warning}"
            # Newline-joined, matching WarningCollector.get_combined_warning.
            warning = f"{warning}\n{gate_warning}" if warning else gate_warning
        combined = replace(main, warning=warning, precondition=precondition)
        gate_message = f"Precondition: {precondition.error_message}"

        if main.is_valid and precondition.is_valid:
            return combined
        if main.is_valid:
            return replace(
                combined,
                is_valid=False,
                error_message=gate_message,
                error_code=precondition.error_code,
                error_source="precondition",
            )
        if precondition.is_valid:
            return replace(combined, error_source="expression")
        # Both halves failed. Naming only the expression would read as "the
        # gate is fine", costing the caller a round trip to discover it is not,
        # so both messages are surfaced and ``error_source`` says ``"both"``.
        # ``error_code`` holds a single value, so it stays the expression's.
        return replace(
            combined,
            error_message=f"{main.error_message}\n{gate_message}",
            error_source="both",
        )

    def is_valid(
        self,
        expression: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
        *,
        precondition_expression: Optional[str] = None,
    ) -> bool:
        """Quick boolean check, pair-wide when a gate is supplied."""
        return self.validate(
            expression,
            precondition_expression=precondition_expression,
            release_id=release_id,
            release_code=release_code,
        ).is_valid

    # ------------------------------------------------------------------ #
    # Precondition-operation link (``precondition_operation_vid``)
    # ------------------------------------------------------------------ #

    def _check_precondition_link(
        self, precondition_operation_vid: int, release_id: Optional[int]
    ) -> None:
        """Cross-check an externally-linked precondition operation.

        Checks its filing-indicator variables are still live (``7-3``)
        and its tables/modules fit the current expression's (``7-4``/
        ``7-5``). Nothing to check against (malformed, closed, or an
        unresolved ``precondition_operation_vid``) is skipped, not
        raised. An ``or``/``xor`` only fails a check when every side
        does, so ``{v_A} or {v_B}`` needs just one side to pass.
        """
        row = filter_by_release(
            self.session.query(OperationVersion.expression).filter(
                OperationVersion.operation_vid == precondition_operation_vid
            ),
            OperationVersion.start_release_id,
            OperationVersion.end_release_id,
            release_id,
        ).first()
        if row is None or not row[0]:
            return
        try:
            precondition_ast = self._syntax.parse(row[0])
        except Exception:
            return
        if not extract_precondition_codes(precondition_ast):
            return
        self._check_precondition_filing_indicators(
            precondition_operation_vid, precondition_ast, release_id
        )
        self._check_precondition_tables(precondition_ast, release_id)

    def _check_precondition_filing_indicators(
        self,
        precondition_operation_vid: int,
        precondition_ast: Any,
        release_id: Optional[int],
    ) -> None:
        """Raise ``7-3`` when the gate can no longer be satisfied.

        A code that is not a filing indicator (value condition, plain
        variable) always counts as live. An ``or``/``xor`` of filing
        indicators only fails once every side has gone stale.
        """
        all_codes = set(extract_precondition_codes(precondition_ast))
        filing_indicator_codes = ModuleVersionQuery.get_filing_indicator_codes(
            self.session, all_codes
        )
        if not filing_indicator_codes:
            return
        modules_df = ModuleVersionQuery.get_precondition_module_versions(
            self.session,
            list(filing_indicator_codes),
            release_id,
            include_ghosts=True,
        )
        live_codes = set(modules_df["Code"]) if not modules_df.empty else set()
        stale_codes = filing_indicator_codes - live_codes
        if not stale_codes:
            return

        def is_live(code: str) -> bool:
            return code not in stale_codes

        if gate_satisfiable(precondition_ast, is_live):
            return

        variable_ids = sorted(
            {
                vid
                for (vid,) in self.session.query(OperandReference.variable_id)
                .join(
                    OperationNode,
                    OperandReference.node_id == OperationNode.node_id,
                )
                .join(
                    VariableVersion,
                    OperandReference.variable_id
                    == VariableVersion.variable_id,
                )
                .filter(
                    OperationNode.operation_vid == precondition_operation_vid,
                    VariableVersion.code.in_(stale_codes),
                )
                .distinct()
                .all()
            }
        )
        raise SemanticError(
            "7-3",
            precondition_variable_ids=(
                ", ".join(str(vid) for vid in variable_ids)
                if variable_ids
                else ", ".join(sorted(stale_codes))
            ),
        )

    def _check_precondition_tables(
        self, precondition_ast: Any, release_id: Optional[int]
    ) -> None:
        """Raise ``7-4``/``7-5`` when the gate's tables/modules don't fit.

        A code with no table (a value condition like ``{v_BM} = 'G-SIB'``)
        never blocks the gate. An ``or``/``xor`` of table codes only
        fails once every side mismatches, mirroring the ``7-3`` check.
        """
        operand_tables = list(self.oc_tables.keys()) if self.oc_tables else []
        if not operand_tables:
            return
        abstract_by_table = TableVersionQuery.get_abstract_table_codes(
            self.session, operand_tables, release_id
        )
        operand_abstract_tables = set(abstract_by_table.values())

        all_codes = extract_precondition_codes(precondition_ast)
        precondition_abstract_by_table = (
            TableVersionQuery.get_abstract_table_codes(
                self.session, all_codes, release_id
            )
        )
        if not precondition_abstract_by_table:
            return
        precondition_tables = set(precondition_abstract_by_table.keys())

        def table_ok(code: str) -> bool:
            abstract = precondition_abstract_by_table.get(code)
            return abstract is None or abstract in operand_abstract_tables

        if not gate_satisfiable(precondition_ast, table_ok):
            raise SemanticError(
                "7-4",
                precondition_tables=", ".join(sorted(precondition_tables)),
                operation_tables=", ".join(sorted(operand_abstract_tables)),
            )

        self._check_precondition_modules(
            precondition_ast,
            precondition_tables,
            precondition_abstract_by_table,
            operand_tables,
            table_ok,
            release_id,
        )

    def _check_precondition_modules(
        self,
        precondition_ast: Any,
        precondition_tables: set[str],
        precondition_abstract_by_table: dict[str, str],
        operand_tables: list[str],
        table_ok: Callable[[str], bool],
        release_id: Optional[int],
    ) -> None:
        """Raise ``7-5`` when the gate's modules don't fit (``7-4`` passed).

        A gate code matched at the abstract level is expanded to its
        concrete children first, since module composition never links
        an abstract table directly.
        """
        concrete_by_code = TableVersionQuery.get_concrete_table_codes(
            self.session, list(precondition_tables), release_id
        )
        concrete_precondition_tables: set[str] = set().union(
            *concrete_by_code.values()
        )
        precondition_modules_df = ModuleVersionQuery.get_from_table_codes(
            self.session,
            list(concrete_precondition_tables),
            release_id,
            include_ghosts=True,
        )
        operand_modules_df = ModuleVersionQuery.get_from_table_codes(
            self.session,
            operand_tables,
            release_id,
            include_ghosts=True,
        )
        operand_modules = (
            set(operand_modules_df["ModuleCode"])
            if not operand_modules_df.empty
            else set()
        )
        modules_by_concrete_table: dict[str, set[str]] = {}
        if not precondition_modules_df.empty:
            for table_code, group in precondition_modules_df.groupby(
                "TableCode"
            ):
                modules_by_concrete_table[str(table_code)] = set(
                    group["ModuleCode"]
                )
        precondition_modules_by_table: dict[str, set[str]] = {
            code: set().union(
                *(
                    modules_by_concrete_table.get(concrete, set())
                    for concrete in concretes
                )
            )
            for code, concretes in concrete_by_code.items()
        }

        def module_ok(code: str) -> bool:
            if code not in precondition_abstract_by_table:
                return True
            modules = precondition_modules_by_table.get(code, set())
            return bool(modules & operand_modules)

        def fits(code: str) -> bool:
            return table_ok(code) and module_ok(code)

        if not gate_satisfiable(precondition_ast, fits):
            precondition_modules: set[str] = set()
            for modules in precondition_modules_by_table.values():
                precondition_modules |= modules
            raise SemanticError(
                "7-5",
                precondition_modules=", ".join(sorted(precondition_modules)),
                operation_modules=", ".join(sorted(operand_modules)),
            )

    # ------------------------------------------------------------------ #
    # Scope-wide parameter consistency (against persisted operations)
    # ------------------------------------------------------------------ #

    def _check_persisted_scope(
        self,
        declarations: dict[str, str],
        table_codes: list[str],
        release_id: Optional[int],
    ) -> None:
        """Raise ``3-8`` if a parameter clashes with a co-scoped persisted op.

        Two operations co-execute when their scopes share a module version, so
        a parameter bound across them must declare a single type. This compares
        the expression's parameter declarations against every parameterised
        operation already persisted in a shared module version. The lookup is
        scoped in SQL — only co-located, parameter-bearing rows are fetched —
        so it costs nothing when no such operation exists.

        Args:
            declarations: ``{code: declared_type}`` for the expression.
            table_codes: The table codes the expression selects from.
            release_id: Release used to resolve those tables to modules.
        """
        module_vids = _module_vids_for(self.session, table_codes, release_id)
        if not module_vids:
            return
        for expression in self._co_scoped_parameter_expressions(module_vids):
            for code, other_type in self._declarations(expression).items():
                declared = declarations.get(code)
                if declared is not None and declared != other_type:
                    raise SemanticError(
                        "3-8",
                        parameter=code,
                        type_1=other_type,
                        type_2=declared,
                    )

    def _co_scoped_parameter_expressions(
        self, module_vids: frozenset[int]
    ) -> list[str]:
        """Persisted parameterised expressions sharing a module version.

        The marker match is whitespace-insensitive (see
        :func:`_whitespace_insensitive`) so a hand-written ``{ p_x}`` is still
        found. The ``LIKE`` filter guarantees a non-null expression (``LIKE``
        rejects NULL), so the cast to ``str`` is sound.
        """
        base = (
            self.session.query(OperationVersion.expression)
            .join(
                OperationScope,
                OperationVersion.operation_vid == OperationScope.operation_vid,
            )
            .join(
                OperationScopeComposition,
                OperationScope.operation_scope_id
                == OperationScopeComposition.operation_scope_id,
            )
            .filter(
                _whitespace_insensitive(OperationVersion.expression).like(
                    _PARAM_MARKER
                )
            )
            .distinct()
        )
        rows = chunked_in(
            base, OperationScopeComposition.module_vid, module_vids
        )
        # Chunking the module_vid IN clause splits the query, so the
        # per-statement DISTINCT no longer dedups across chunks; collapse
        # repeated expressions here while preserving order.
        return list(
            dict.fromkeys(
                expression for (expression,) in cast("list[tuple[str]]", rows)
            )
        )

    def _declarations(self, expression: str) -> dict[str, str]:
        """Extract ``{code: declared_type}`` from one persisted expression.

        A malformed/legacy persisted expression that fails to parse is skipped
        rather than aborting validation of the current expression.
        """
        try:
            ast = self._syntax.parse(expression)
        except Exception:
            return {}
        decls: dict[str, str] = {}
        for ref in _walk_parameter_refs(ast):
            # Canonical names so the comparison matches ParameterInfo.
            decls.setdefault(ref.code, canonical_param_type(ref.param_type))
        return decls
