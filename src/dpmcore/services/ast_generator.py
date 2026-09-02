"""Engine-ready AST generation service."""

from __future__ import annotations

import logging
import re
import zlib
from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from dpmcore.dpm_xl.utils.tokens import (
    SEVERITY_WARNING,
    VALID_SEVERITIES,
)
from dpmcore.errors import SemanticError
from dpmcore.services._parameters import merge_parameters
from dpmcore.services._precondition_codes import (
    extract_precondition_codes as _extract_precondition_codes,
)
from dpmcore.services.semantic import ParameterInfo, SemanticService
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from dpmcore.services.scope_calculator import (
        ScopeCalculatorService,
        ScopeResult,
    )


logger = logging.getLogger(__name__)


_VAR_REF_PATTERN = re.compile(r"\{v_?([^}]+)\}")
_TABLE_CODE_NORMALIZER = re.compile(r"^([A-Z]+)_(\d+)_(\d+)$")
_DEFAULT_FROM_DATE = "2001-01-01"
_DEFAULT_NAMESPACE = "default_module"
_DATA_FIELDS_TO_STRIP = ("data_type", "cell_code", "table_code", "table_vid")


@dataclass(frozen=True)
class _OperandRefs:
    """What a single operation's operands reference.

    ``tables`` are the table codes of its ``VarID`` nodes; ``variables``
    maps every operand datapoint id to its scalar type code, across all
    modules the operation spans (home module included).
    """

    tables: set[str] = field(default_factory=set)
    variables: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _PreparedExpression:
    """One expression readied for the script, or the reason it is not.

    ``error`` is set when the expression cannot become a declarable
    operation — it failed semantic validation, or it carries a shift
    whose reference period cannot be declared (#326). Both are reported
    the same way, through ``failed_operations``, and both must be caught
    before the caller accumulates anything for the operation: a skip
    afterwards would leave its tables, parameters and operation entry in
    the script.
    """

    result: Any = None
    ast: Any = None
    ts: Dict[str, List[str]] = field(default_factory=dict)
    error: Optional[str] = None


def _normalize_variable_code(code: str) -> str:
    """Normalise ``F_44_04`` → ``F_44.04`` (matches pydpm)."""
    m = _TABLE_CODE_NORMALIZER.match(code)
    if m:
        return f"{m.group(1)}_{m.group(2)}.{m.group(3)}"
    return code


def _format_date(value: Any, fallback: Optional[str] = None) -> Optional[str]:
    """Format a ``date`` / ``datetime`` / string as ``YYYY-MM-DD``."""
    if value is None:
        return fallback
    if isinstance(value, str):
        return value
    if isinstance(value, date_cls):
        return value.strftime("%Y-%m-%d")
    return str(value)


class ASTGeneratorService:
    """Generate engine-ready validation scripts from DPM-XL expressions.

    Args:
        session: An open SQLAlchemy session (required for ``script``).
    """

    def __init__(self, session: Optional["Session"] = None) -> None:
        """Build the service, optionally bound to a SQLAlchemy ``session``."""
        self.session = session
        self._semantic: Optional[SemanticService] = None
        self._scope_calc: Optional["ScopeCalculatorService"] = None
        self._syntax = SyntaxService()
        if session is not None:
            from dpmcore.services.scope_calculator import (
                ScopeCalculatorService,
            )

            self._semantic = SemanticService(session)
            self._scope_calc = ScopeCalculatorService(session)

    def script(
        self,
        expressions: List[Tuple[str, str]],
        module_code: str,
        module_version: str,
        preconditions: Optional[
            List[Union[Tuple[str, List[str]], Dict[str, Any]]]
        ] = None,
        severity: Optional[str] = None,
        severities: Optional[Dict[str, str]] = None,
        release: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate an engine-ready validations script.

        Args:
            expressions: ``[(expression, validation_code), ...]``.
            module_code: Code of the primary module (e.g. ``"COREP_Con"``).
            module_version: Version of the primary module
                (e.g. ``"2.0.1"``).
            preconditions: Optional list of precondition specs. Each
                entry is either a tuple
                ``(precondition_expression, [validation_codes])`` or a
                dict with keys ``expression`` and
                ``affected_operations`` (optional ``code`` and
                ``version_id`` are also accepted). A precondition can
                guard many validation codes; a validation may have no
                precondition.
            severity: Optional global default severity tag
                (``"error"``, ``"warning"``, ``"info"``). Defaults to
                ``"warning"``.
            severities: Optional per-validation override map
                ``{validation_code: severity}``. Resolution per
                validation is ``severities.get(code, severity_global)``.
                Unknown codes (not present in ``expressions``) raise
                ``ValueError``.
            release: Optional release code. When omitted, resolved to
                the latest release whose window contains the requested
                ``ModuleVersion``. The resolved release is surfaced in
                the ``dpm_release`` block and used for every
                downstream DB filter.

        Returns:
            A dict with keys ``success`` (bool), ``enriched_ast`` (the
            namespaced dict, or ``None`` on failure), ``error`` (str or
            ``None``), and ``failed_operations`` (a
            ``{validation_code: error_message}`` map of expressions
            skipped due to semantic errors). The namespaced dict mirrors
            the shape pydpm's ``generate_validations_script`` produces.
        """
        session = self.session
        if (
            self._semantic is None
            or self._scope_calc is None
            or session is None
        ):
            return {
                "success": False,
                "enriched_ast": None,
                "error": "No database session — cannot generate script.",
                "failed_operations": {},
            }

        try:
            from dpmcore.dpm_xl.utils.serialization import serialize_ast

            mv, release_row = self._resolve_release(
                module_code, module_version, release
            )
            primary_module_vid: int = mv.module_vid
            release_id: int = release_row.release_id

            validation_codes = [code for _, code in expressions]
            resolved_severities = self._resolve_severities(
                severity, severities, validation_codes
            )

            try:
                code_to_precondition_items = self._build_precondition_index(
                    preconditions or []
                )
            except ValueError as exc:
                return {
                    "success": False,
                    "enriched_ast": None,
                    "error": str(exc),
                    "failed_operations": {},
                }

            from_submission_date = _format_date(
                mv.from_reference_date, fallback=_DEFAULT_FROM_DATE
            )

            operations: Dict[str, Dict[str, Any]] = {}
            failed_operations: Dict[str, str] = {}
            scope_pairs: List[
                Tuple[
                    Tuple[str, str],
                    "ScopeResult",
                    Dict[str, List[str]],
                    _OperandRefs,
                ]
            ] = []
            referenced_table_codes: set[str] = set()
            referenced_parameters: Dict[str, ParameterInfo] = {}

            for item in expressions:
                expr, code = item[0], item[1]
                # Semantic validation plus the reference periods the
                # expression needs; either can reject it. The
                # _accumulate_parameters call below is complementary to
                # the scope check inside — it catches conflicts between
                # two expressions in this same script.
                prepared = self._prepare_expression(
                    self._semantic, expr, release_id
                )
                if prepared.error is not None:
                    failed_operations[code] = prepared.error
                    continue
                result, ast, ts = prepared.result, prepared.ast, prepared.ts
                ast_dict = serialize_ast(ast)
                # Operand refs come off the *raw* serialisation: cleaning
                # strips the ``data_type`` each datapoint is typed by.
                op_refs = _OperandRefs(
                    tables=self._extract_referenced_tables(ast_dict),
                    variables=self._extract_operand_datapoints(ast_dict),
                )
                self._clean_ast_data_entries(ast_dict)
                referenced_table_codes.update(op_refs.tables)
                self._accumulate_parameters(
                    referenced_parameters, result.parameters
                )

                root_operator_id = self._resolve_root_operator_id(ast, session)

                operations[code] = self._build_operation_entry(
                    expression=expr,
                    code=code,
                    ast_dict=ast_dict,
                    severity=resolved_severities[code],
                    submission_date=from_submission_date,
                    root_operator_id=root_operator_id,
                )

                sr = self._scope_calc.calculate_from_expression(
                    expression=expr,
                    release_id=release_id,
                    precondition_items=code_to_precondition_items.get(
                        code, []
                    ),
                )
                if sr.has_error:
                    # A script whose dependency block is silently missing
                    # is structurally valid but semantically wrong (#122),
                    # so a scope failure fails the whole generation.
                    return {
                        "success": False,
                        "enriched_ast": None,
                        "error": (
                            f"Scope calculation failed for operation "
                            f"'{code}': {sr.error_message}"
                        ),
                        "failed_operations": failed_operations,
                    }
                scope_pairs.append((item, sr, ts, op_refs))

            primary_tables_full = self._scope_calc._get_module_tables(
                primary_module_vid, release_id=release_id
            )
            # Seed from every module-composition table that carries
            # variables — i.e. the non-abstract tables; abstract templates
            # have no cells, and the engine schema forbids an empty
            # variables map — then union in anything the expressions
            # reference. MDPM lists all such tables even when no validation
            # touches them (#158). The union keeps this additive: a
            # referenced table is never dropped.
            seed_codes = {
                code
                for code, data in primary_tables_full.items()
                if data.get("variables")
            }
            seed_codes |= {
                code
                for code in referenced_table_codes
                if code in primary_tables_full
            }
            tables_block: Dict[str, Any] = {
                code: primary_tables_full[code] for code in sorted(seed_codes)
            }
            variables_block: Dict[str, str] = {}
            for tbl in tables_block.values():
                variables_block.update(tbl.get("variables", {}))

            # Runtime-binding contract: the declared type of every parameter
            # this script's operations reference, keyed by code. This is the
            # scope-wide invariant. ``is_set`` is recoverable from the ``set-``
            # prefix and ``default`` is a per-reference fallback the engine
            # binds per scope, so neither belongs in this registry.
            parameters_block: Dict[str, str] = {
                prm_code: prm.declared_type
                for prm_code, prm in sorted(referenced_parameters.items())
            }

            preconditions_block, precondition_variables_block = (
                self._build_preconditions_block(
                    preconditions or [], release_id=release_id
                )
            )

            dependency_info = self._build_dependency_info(
                scope_pairs=scope_pairs,
                primary_module_vid=primary_module_vid,
                release_id=release_id,
            )
            dep_information: Dict[str, Any]
            dep_modules: Dict[str, Any]
            if dependency_info is not None:
                dep_information = dependency_info["dependency_information"]
                dep_modules = dependency_info["dependency_modules"]
            else:
                dep_information = {
                    "intra_instance_validations": [],
                    "cross_instance_dependencies": [],
                    "alternative_dependencies": [],
                }
                dep_modules = {}

            namespace = (
                self._scope_calc._get_module_uri(
                    module_vid=primary_module_vid,
                    mv=mv,
                )
                or _DEFAULT_NAMESPACE
            )

            module_info = self._build_module_info(mv)
            ns_block: Dict[str, Any] = {
                **module_info,
                "dpm_release": self._build_release_info(release_row),
                "dates": self._build_dates(mv),
                "operations": operations,
                "variables": variables_block,
                "tables": tables_block,
                "parameters": parameters_block,
                "preconditions": preconditions_block,
                "precondition_variables": precondition_variables_block,
                "dependency_information": dep_information,
                "dependency_modules": dep_modules,
            }

            return {
                "success": True,
                "enriched_ast": {namespace: ns_block},
                "error": None,
                "failed_operations": failed_operations,
            }

        except ValueError as exc:
            return {
                "success": False,
                "enriched_ast": None,
                "error": str(exc),
                "failed_operations": {},
            }
        except Exception as exc:
            return {
                "success": False,
                "enriched_ast": None,
                "error": str(exc),
                "failed_operations": {},
            }

    def script_for_module(
        self,
        module_code: str,
        module_version: str,
        release: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Auto-discover a module version's active validations and script them.

        No ``expressions``, ``preconditions`` or ``severities`` need to be
        supplied — they are looked up from ``OperationScope`` /
        ``OperationScopeComposition`` / ``OperationVersion`` for this module
        version, then handed to :meth:`script`.

        Args:
            module_code: Code of the module (e.g. ``"COREP_Con"``).
            module_version: Version of the module (e.g. ``"2.0.1"``).
            release: Optional release code; resolved the same way as in
                :meth:`script`.

        Returns:
            Same shape as :meth:`script`.
        """
        if self.session is None:
            return {
                "success": False,
                "enriched_ast": None,
                "error": "No database session — cannot generate script.",
                "failed_operations": {},
            }

        try:
            mv, release_row = self._resolve_release(
                module_code, module_version, release
            )
            expressions, preconditions, severities = (
                self._discover_module_validations(mv, release_row)
            )
        except ValueError as exc:
            return {
                "success": False,
                "enriched_ast": None,
                "error": str(exc),
                "failed_operations": {},
            }

        return self.script(
            expressions=expressions,
            module_code=module_code,
            module_version=module_version,
            preconditions=preconditions or None,
            severities=severities or None,
            release=release_row.code,
        )

    def list_module_versions(
        self,
        module_code: Optional[str] = None,
        release: Optional[str] = None,
    ) -> List[Tuple[str, str]]:
        """Enumerate ``(module_code, version_number)`` pairs to sweep.

        Used by the CLI's ``--all-modules``/``--all-versions`` sweep to
        discover targets for :meth:`script_for_module`.

        Args:
            module_code: Restrict to this module's versions. ``None``
                enumerates every module in the database.
            release: When given, only ``ModuleVersion`` rows whose window
                contains this release (via :func:`filter_by_release`) are
                returned.

        Returns:
            ``(module_code, version_number)`` pairs, ordered by
            ``(code, start_release_id)``, excluding ghost/phantom
            ``ModuleVersion`` rows (``from_reference_date ==
            to_reference_date``, both non-null — the same test
            :meth:`_walk_ghost_chain` uses).

        Raises:
            ValueError: If a database session is missing, or ``release``
                doesn't match any ``Release.code``.
        """
        from sqlalchemy import or_

        from dpmcore.dpm_xl.utils.filters import (
            filter_by_release,
            resolve_release_id,
        )
        from dpmcore.orm.packaging import ModuleVersion

        if self.session is None:
            raise ValueError("No database session — cannot list modules.")
        session = self.session

        query = session.query(
            ModuleVersion.code, ModuleVersion.version_number
        ).filter(
            or_(
                ModuleVersion.from_reference_date.is_(None),
                ModuleVersion.to_reference_date.is_(None),
                ModuleVersion.from_reference_date
                != ModuleVersion.to_reference_date,
            )
        )
        if module_code is not None:
            query = query.filter(ModuleVersion.code == module_code)
        if release is not None:
            release_id = resolve_release_id(session, release_code=release)
            query = filter_by_release(
                query,
                start_col=ModuleVersion.start_release_id,
                end_col=ModuleVersion.end_release_id,
                release_id=release_id,
            )
        query = query.order_by(
            ModuleVersion.code, ModuleVersion.start_release_id
        )

        seen: set[Tuple[str, str]] = set()
        pairs: List[Tuple[str, str]] = []
        for code, version_number in query.all():
            if code is None or version_number is None:
                continue
            pair = (code, version_number)
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)
        return pairs

    def _discover_module_validations(
        self,
        mv: Any,
        release_row: Any,
    ) -> Tuple[
        List[Tuple[str, str]],
        List[Union[Tuple[str, List[str]], Dict[str, Any]]],
        Dict[str, str],
    ]:
        """Look up the active ``(expression, code)`` pairs for a module.

        Resolves the module version's active operations by joining
        ``OperationVersion`` to ``OperationScope`` /
        ``OperationScopeComposition``, filtered to this release using
        dpmcore's point-release model (:func:`filter_by_release`, a window
        containment check rather than a raw ``StartReleaseID``/
        ``EndReleaseID`` overlap). This does not filter out operations
        scoped exclusively to phantom module versions (see
        :meth:`list_module_versions`'s docstring for what "phantom" means
        here) — that guard only matters when sweeping every module in the
        database, which this single-module lookup never does; revisit
        alongside a future ``--all-modules`` sweep.

        Returns:
            ``(expressions, preconditions, severities)`` ready to pass to
            :meth:`script`.
        """
        from sqlalchemy import or_

        from dpmcore.dpm_xl.utils.filters import filter_by_release
        from dpmcore.orm.operations import (
            Operation,
            OperationScope,
            OperationScopeComposition,
            OperationVersion,
        )

        session = self.session
        if session is None:
            raise ValueError("No database session — cannot generate script.")

        query = (
            session.query(
                OperationVersion.operation_vid,
                Operation.code,
                OperationVersion.expression,
                OperationScope.severity,
                OperationVersion.precondition_operation_vid,
            )
            .join(
                OperationScope,
                OperationVersion.operation_vid == OperationScope.operation_vid,
            )
            .join(
                OperationScopeComposition,
                OperationScope.operation_scope_id
                == OperationScopeComposition.operation_scope_id,
            )
            .join(
                Operation,
                OperationVersion.operation_id == Operation.operation_id,
            )
            .filter(OperationScopeComposition.module_vid == mv.module_vid)
            # Access boolean convention: True is stored as -1, not 1.
            .filter(OperationScope.is_active.in_([-1, 1, True]))
            .filter(
                or_(
                    Operation.code.startswith("v"),
                    Operation.code.startswith("e"),
                )
            )
        )
        query = filter_by_release(
            query,
            start_col=OperationVersion.start_release_id,
            end_col=OperationVersion.end_release_id,
            release_id=release_row.release_id,
        )

        # A code can match more than one OperationVersion row; keep the
        # latest (highest OperationVID) per code.
        _Row = Tuple[int, str, Optional[str], Optional[int]]
        latest_by_code: Dict[str, _Row] = {}
        for op_vid, code, expression, severity, prec_vid in query.all():
            existing = latest_by_code.get(code)
            if existing is None or op_vid > existing[0]:
                latest_by_code[code] = (op_vid, expression, severity, prec_vid)

        expressions: List[Tuple[str, str]] = []
        severities: Dict[str, str] = {}
        prec_vid_to_codes: Dict[int, List[str]] = {}
        for code, (_, expression, severity, prec_vid) in sorted(
            latest_by_code.items()
        ):
            expressions.append((expression, code))
            if severity:
                severities[code] = severity
            if prec_vid is not None:
                prec_vid_to_codes.setdefault(prec_vid, []).append(code)

        preconditions: List[Union[Tuple[str, List[str]], Dict[str, Any]]] = (
            list(self._resolve_preconditions(prec_vid_to_codes))
        )
        return expressions, preconditions, severities

    def _resolve_preconditions(
        self, prec_vid_to_codes: Dict[int, List[str]]
    ) -> List[Dict[str, Any]]:
        """Resolve discovered ``PreconditionOperationVID``s into entries.

        Note: :meth:`_build_preconditions_block` does not build a
        precondition's AST structurally from the DB's stored
        ``OperationNode`` graph, so it cannot express arbitrary DPM-XL
        boolean expressions — it only recognises ``{v_<variable_code>}``
        markers (or an ``and``-chain of them) in the expression text — see
        its docstring and ``TestBuildPreconditionsBlock`` in
        ``tests/unit/services/test_ast_generator.py``. A discovered
        precondition whose stored ``Expression`` isn't in that form resolves
        to no variables and is silently dropped, same as pydpm. This is a
        pre-existing limitation of ``script()``'s precondition support, not
        specific to auto-discovery.
        """
        if not prec_vid_to_codes:
            return []

        from dpmcore.orm.operations import Operation, OperationVersion

        session = self.session
        if session is None:
            raise ValueError("No database session — cannot generate script.")

        rows = (
            session.query(
                OperationVersion.operation_vid,
                Operation.code,
                OperationVersion.expression,
            )
            .join(
                Operation,
                OperationVersion.operation_id == Operation.operation_id,
            )
            .filter(
                OperationVersion.operation_vid.in_(prec_vid_to_codes.keys())
            )
            .all()
        )

        preconditions: List[Dict[str, Any]] = []
        for prec_vid, prec_code, prec_expression in rows:
            preconditions.append(
                {
                    "expression": prec_expression,
                    "affected_operations": sorted(prec_vid_to_codes[prec_vid]),
                    "code": prec_code,
                    "version_id": prec_vid,
                }
            )
        return preconditions

    # ------------------------------------------------------------------ #
    # Resolution helpers
    # ------------------------------------------------------------------ #

    def _resolve_module_version(
        self,
        module_code: str,
        module_version: str,
    ) -> Optional[Any]:
        """Look up a ``ModuleVersion`` by ``(code, version_number)``.

        Returns the ORM row, or ``None`` if no match.
        """
        from dpmcore.orm.packaging import ModuleVersion

        if self.session is None:
            return None
        return (
            self.session.query(ModuleVersion)
            .filter(ModuleVersion.code == module_code)
            .filter(ModuleVersion.version_number == module_version)
            .first()
        )

    def _resolve_release(
        self,
        module_code: str,
        module_version: str,
        release: Optional[str],
    ) -> Tuple[Any, Any]:
        """Resolve ``(ModuleVersion, Release)`` for the request.

        When ``release`` is omitted, falls back to the most recent
        ``Release`` whose window contains the requested
        ``ModuleVersion``.
        """
        mv = self._resolve_module_version(module_code, module_version)
        if mv is None:
            raise ValueError(
                f"ModuleVersion not found: {module_code} {module_version}"
            )
        if self.session is None:
            raise ValueError("No database session — cannot resolve release.")

        if release is not None:
            release_row = self._resolve_explicit_release(
                release, mv, module_code, module_version
            )
            return mv, release_row

        latest = self._latest_release_in_window(mv)
        if latest is None:
            raise ValueError(
                f"No Release matches module version {module_code} "
                f"{module_version} window."
            )
        return mv, latest

    def _resolve_explicit_release(
        self,
        release: str,
        mv: Any,
        module_code: str,
        module_version: str,
    ) -> Any:
        """Resolve and window-check an explicit release.

        Looks up ``Release.code == release`` and validates that the
        release sits inside ``mv``'s window. Comparison runs against the
        date-based sort order of each release (the DPM ``ReleaseID`` FK
        is no longer monotonic — see
        :mod:`dpmcore.orm.release_sort_order`), not the raw id. Raises
        ``ValueError`` if the release is unknown, predates
        ``start_release_id``, or is past ``end_release_id``.

        Coordinates with the ghost-version fallback in
        :func:`dpmcore.dpm_xl.model_queries._resolve_with_ghost_fallback`:
        when ``mv`` is being used as the fallback for a ghost that
        follows it, ``mv``'s effective end release is virtually extended
        past the ghost(s) to the start of the next non-ghost sibling —
        or ``None`` when only ghosts follow (issue #221). The
        ``predates`` branch is never relaxed:
        ``_latest_prior_non_collapsed_vids`` picks fallbacks strictly
        backward, so a legitimate ghost-fallback can never produce an MV
        whose start ``predates`` the requested release.
        """
        from dpmcore.orm.infrastructure import Release
        from dpmcore.orm.release_sort_order import (
            compute_sort_order,
            resolve_sort_order,
        )

        if self.session is None:
            raise RuntimeError("session required")
        release_row = (
            self.session.query(Release).filter(Release.code == release).first()
        )
        if release_row is None:
            raise ValueError(f"Release not found: {release}")
        target = resolve_sort_order(
            self.session, release_row.release_id, role=f"release {release}"
        )
        start = mv.start_release_id
        end = mv.end_release_id
        if start is not None and target < resolve_sort_order(
            self.session, start, role="module version start release"
        ):
            raise ValueError(
                f"Release {release} predates module version "
                f"{module_code} {module_version} "
                f"(starts at release_id={start})."
            )
        if end is not None:
            effective_end_id = self._effective_end_release_id(mv)
            if effective_end_id is not None:
                effective_end_sort = resolve_sort_order(
                    self.session,
                    effective_end_id,
                    role="module version effective end release",
                )
                # A row ending at an "always latest" release (undated or
                # non-chronological) is still open even when queried at
                # that release.
                if (
                    effective_end_sort != compute_sort_order(None, None)
                    and target >= effective_end_sort
                ):
                    raise ValueError(
                        f"Release {release} is past the end of module "
                        f"version {module_code} {module_version} "
                        f"(ends at release_id={end})."
                    )
        return release_row

    def _effective_end_release_id(self, mv: Any) -> Optional[int]:
        """Compute ``mv``'s effective end, extended past ghost siblings.

        When ``mv`` is used as ghost-fallback (its content substitutes
        for a ghost of the same module covering releases past ``mv``'s
        own end), the effective end virtually extends past those ghost
        siblings. The extension follows a contiguous chain of ghost
        siblings starting at (or overlapping) ``mv.end_release_id``:

        - If the chain is followed by a non-ghost sibling, the effective
          end is that sibling's ``start_release_id``.
        - If only ghosts follow (open-ended ghost, or the last ghost's
          end is null), the effective end is ``None`` (open).
        - If no ghost adjoins ``mv``'s end, the effective end is
          ``mv.end_release_id`` unchanged.

        Args:
            mv: The ``ModuleVersion`` being window-checked.

        Returns:
            The release id to use as the effective upper bound of
            ``mv``'s window, or ``None`` if it is open-ended.
        """
        from dpmcore.orm.packaging import ModuleVersion
        from dpmcore.orm.release_sort_order import resolve_sort_order

        if mv.end_release_id is None:
            return None
        if self.session is None or mv.module_id is None:
            return mv.end_release_id
        session = self.session
        end_sort = resolve_sort_order(
            session,
            mv.end_release_id,
            role="module version end release",
        )
        siblings = (
            session.query(ModuleVersion)
            .filter(ModuleVersion.module_id == mv.module_id)
            .filter(ModuleVersion.module_vid != mv.module_vid)
            .all()
        )
        candidates = self._siblings_past_end(siblings, end_sort)
        return self._walk_ghost_chain(mv, candidates, end_sort)

    def _siblings_past_end(
        self, siblings: Iterable[Any], end_sort: int
    ) -> List[Tuple[int, bool, Any]]:
        """Filter and sort siblings whose window extends past ``end_sort``."""
        from dpmcore.orm.release_sort_order import resolve_sort_order

        session = self.session
        if session is None:
            raise RuntimeError("session required")

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
            # Missing start acts as unbounded below; cap the sort key at
            # ``end_sort`` so such siblings sit at the chain's head.
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

    def _walk_ghost_chain(
        self,
        mv: Any,
        candidates: List[Tuple[int, bool, Any]],
        end_sort: int,
    ) -> Optional[int]:
        """Walk sibling candidates to find ``mv``'s effective end."""
        from dpmcore.orm.release_sort_order import resolve_sort_order

        session = self.session
        if session is None:
            raise RuntimeError("session required")
        saw_ghost = False
        boundary = end_sort
        last_ghost_end_id: Optional[int] = None
        for start_sort, ghost, sibling in candidates:
            if start_sort > boundary:
                break
            if ghost:
                saw_ghost = True
                if sibling.end_release_id is None:
                    return None
                sibling_end_sort = resolve_sort_order(
                    session,
                    sibling.end_release_id,
                    role="sibling module version end release",
                )
                if sibling_end_sort > boundary:
                    boundary = sibling_end_sort
                    last_ghost_end_id = sibling.end_release_id
                continue
            if saw_ghost:
                # First non-ghost after a chain of ghosts terminates the
                # virtual extension at its ``start_release_id``.
                return sibling.start_release_id
            # A non-ghost adjoins ``mv``'s end directly (no ghost bridge),
            # so no extension applies — keep the schema value.
            return mv.end_release_id
        # Chain of ghosts with no non-ghost following it: the effective
        # end is the last bounded ghost's ``end_release_id``. (An
        # open-ended ghost would have returned ``None`` inside the loop.)
        if saw_ghost:
            return last_ghost_end_id
        return mv.end_release_id

    def _latest_release_in_window(self, mv: Any) -> Any:
        """Pick the latest Release covering *mv*'s window.

        A release marked ``is_current`` in the DB is the DB's own signal
        that this row represents "the current release" — pick that one
        first (there can only be one). When no candidate is marked
        current, fall back to the latest by date-based sort order
        (``Release.date`` via :func:`compute_sort_order`), then to the
        latest of any status if no released row matches.

        The previous logic filtered candidates to ``status='released'``
        before ordering by date, which silently downgraded a newer
        release still in ``status='validation'`` — the exact shape that
        made dpmcore emit ``4.2`` while the reference declared ``4.2.1``
        for the same fixture DB.
        """
        from dpmcore.orm.infrastructure import Release
        from dpmcore.orm.release_sort_order import (
            compute_sort_order,
            resolve_sort_order,
        )

        if self.session is None:
            raise RuntimeError("session required")

        start_sort: Optional[int] = None
        end_sort: Optional[int] = None
        if mv.start_release_id is not None:
            start_sort = resolve_sort_order(
                self.session,
                mv.start_release_id,
                role="Module version window start release",
            )
        if mv.end_release_id is not None:
            end_sort = resolve_sort_order(
                self.session,
                mv.end_release_id,
                role="Module version window end release",
            )
        perpetual_sort_order = compute_sort_order(None, None)

        rows = self.session.query(Release).all()
        candidates: List[tuple[int, int, Any]] = []
        for r in rows:
            so = compute_sort_order(r.date, r.type)
            if start_sort is not None and so < start_sort:
                continue
            # A row ending at an "always latest" release (undated or
            # non-chronological) is still open even when queried at
            # that release.
            if (
                end_sort is not None
                and end_sort != perpetual_sort_order
                and so >= end_sort
            ):
                continue
            candidates.append((so, r.release_id, r))
        if not candidates:
            return None
        # release_id breaks ties among releases sharing a sort order.
        current = [c for c in candidates if c[2].is_current]
        if current:
            return max(current, key=lambda c: (c[0], c[1]))[2]
        released = [c for c in candidates if c[2].status == "released"]
        pool = released or candidates
        return max(pool, key=lambda c: (c[0], c[1]))[2]

    def _resolve_severities(
        self,
        severity: Optional[str],
        severities: Optional[Dict[str, str]],
        validation_codes: List[str],
    ) -> Dict[str, str]:
        """Validate severity inputs and return ``{code: severity}``.

        - Global default falls back to ``SEVERITY_WARNING`` when
          ``severity`` is ``None``.
        - Each entry of ``severities`` is validated independently.
        - Codes in ``severities`` that are not in ``validation_codes``
          raise ``ValueError`` so callers learn at request time.
        """

        def _normalise(value: str, label: str) -> str:
            if not isinstance(value, str):
                raise ValueError(
                    f"Invalid severity for {label}: must be a string"
                )
            lowered = value.lower()
            if lowered not in VALID_SEVERITIES:
                allowed = ", ".join(sorted(VALID_SEVERITIES))
                raise ValueError(
                    f"Invalid severity {value!r} for {label}. "
                    f"Must be one of: {allowed}"
                )
            return lowered

        global_value = (
            _normalise(severity, "default")
            if severity is not None
            else SEVERITY_WARNING
        )

        per_code: Dict[str, str] = {}
        if severities:
            known_codes = set(validation_codes)
            for raw_code, raw_severity in severities.items():
                if raw_code not in known_codes:
                    raise ValueError(
                        f"Unknown validation_code in severities: {raw_code!r}"
                    )
                per_code[raw_code] = _normalise(
                    raw_severity, f"validation {raw_code!r}"
                )

        return {
            code: per_code.get(code, global_value) for code in validation_codes
        }

    @staticmethod
    def _resolve_root_operator_id(ast: Any, session: "Session") -> int:
        """Resolve the OperatorID at the root of an expression AST.

        Walks past structural wrappers (``Start``, ``WithExpression``,
        ``PersistentAssignment`` / ``TemporaryAssignment``) down to the
        first node carrying an ``op`` attribute, then looks up
        ``Operator.OperatorID`` by ``Symbol`` via the same DataFrame
        ``MLGeneration.create_operation_node`` uses.

        ``ParExpr`` is treated as the operator itself (Symbol ``()``,
        OperatorID 37 in the reference operator table), mirroring pydpm:
        an expression whose body is wrapped in parentheses roots at the
        paren operator, not at the operator inside. ``CondExpr`` and
        ``ParExpr`` carry no ``op`` attribute but map to fixed synthetic
        symbols.

        Raises ``RuntimeError`` if no operator is resolvable.
        """
        from dpmcore.dpm_xl.model_queries import OperatorQuery

        node: Any = ast
        # Walk through wrappers down to the operator node.
        for _ in range(64):  # bounded to avoid runaway recursion
            class_name = type(node).__name__
            if class_name == "Start":
                children = getattr(node, "children", None) or []
                if not children:
                    break
                node = children[0]
                continue
            if class_name == "WithExpression":
                node = node.expression
                continue
            if class_name in ("PersistentAssignment", "TemporaryAssignment"):
                # The assigned expression carries the comparison.
                node = node.right
                continue
            break

        class_name = type(node).__name__
        op_symbol = getattr(node, "op", None)
        if not op_symbol and class_name == "CondExpr":
            # CondExpr carries no ``op`` attribute; its operator is fixed.
            op_symbol = "if-then-else"
        elif not op_symbol and class_name == "ParExpr":
            # ParExpr carries no ``op`` attribute either; the root of
            # a body wrapped in parentheses is the paren operator, not
            # the operator inside. pydpm serialises this as OperatorID 37.
            op_symbol = "()"
        if not op_symbol:
            raise RuntimeError(
                f"Cannot resolve root operator: AST root "
                f"{class_name!r} has no 'op' attribute."
            )

        df = OperatorQuery.get_operators(session)
        matches = df[df["Symbol"] == op_symbol]["OperatorID"].values
        if len(matches) == 0:
            raise RuntimeError(
                f"No OperatorID found for symbol {op_symbol!r}."
            )
        return int(matches[0])

    # ------------------------------------------------------------------ #
    # Section builders
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_module_info(mv: Any) -> Dict[str, Any]:
        """Extract module identity fields from a ``ModuleVersion`` row."""
        framework_code: Optional[str] = None
        module = getattr(mv, "module", None)
        if module is not None:
            framework = getattr(module, "framework", None)
            if framework is not None:
                framework_code = framework.code
        return {
            "module_code": mv.code or "",
            "module_version": mv.version_number or "",
            "framework_code": framework_code or "",
        }

    @staticmethod
    def _build_release_info(release_row: Any) -> Dict[str, Any]:
        """Build ``{"release", "publication_date"}`` from a ``Release`` row.

        dpmcore exposes the publication date as ``Release.date``;
        pydpm calls it ``publication_date``. We use pydpm's name on
        the wire because the engine consumes that key.
        """
        return {
            "release": release_row.code or "",
            "publication_date": _format_date(
                release_row.date, fallback=_DEFAULT_FROM_DATE
            ),
        }

    @staticmethod
    def _build_dates(mv: Any) -> Dict[str, Any]:
        """Build the ``{"from", "to"}`` block from a ``ModuleVersion``."""
        return {
            "from": _format_date(
                mv.from_reference_date, fallback=_DEFAULT_FROM_DATE
            ),
            "to": _format_date(mv.to_reference_date),
        }

    @staticmethod
    def _build_operation_entry(
        expression: str,
        code: str,
        ast_dict: Any,
        severity: str,
        submission_date: Optional[str],
        root_operator_id: int,
    ) -> Dict[str, Any]:
        """Assemble a single ``operations[code]`` entry.

        ``version_id`` is a deterministic CRC32 of the expression
        truncated to four digits; this replaces pydpm's
        non-deterministic ``hash(expression) % 10000``.
        """
        version_id = zlib.crc32(expression.encode("utf-8")) % 10000
        return {
            "version_id": version_id,
            "code": code,
            "expression": expression,
            "root_operator_id": root_operator_id,
            "ast": ast_dict,
            "from_submission_date": submission_date or _DEFAULT_FROM_DATE,
            "severity": severity,
        }

    def _build_preconditions_block(
        self,
        preconditions: List[Union[Tuple[str, List[str]], Dict[str, Any]]],
        release_id: Optional[int],
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """Build the ``preconditions`` and ``precondition_variables`` blocks.

        Mirrors pydpm's ``_build_preconditions``: regex-extract
        ``{v_*}`` variable codes, batch-resolve each to
        ``(variable_id, variable_vid)``, then emit a
        ``PreconditionItem`` AST for single-variable preconditions or
        a left-folded ``BinOp(op="and")`` chain for compound ones.
        Codes that don't resolve are silently skipped (matches pydpm).
        """
        from dpmcore.dpm_xl.model_queries import VariableVersionQuery

        preconditions_dict: Dict[str, Any] = {}
        precondition_variables: Dict[str, str] = {}
        if not preconditions or self.session is None:
            return preconditions_dict, precondition_variables

        all_codes: List[str] = []
        for precond_spec in preconditions:
            precond_expr = (
                precond_spec.get("expression")
                if isinstance(precond_spec, dict)
                else precond_spec[0]
            )
            if not precond_expr:
                continue
            for raw in _VAR_REF_PATTERN.findall(precond_expr):
                normalized = _normalize_variable_code(raw)
                if normalized not in all_codes:
                    all_codes.append(normalized)
        if not all_codes:
            return preconditions_dict, precondition_variables

        resolved = VariableVersionQuery.get_variable_vids_by_codes(
            self.session, all_codes, release_id=release_id
        )

        for precond_spec in preconditions:
            if isinstance(precond_spec, dict):
                precond_expr = precond_spec["expression"]
                validation_codes = precond_spec["affected_operations"]
                provided_code = precond_spec.get("code")
                provided_version_id = precond_spec.get("version_id")
            else:
                precond_expr, validation_codes = precond_spec
                provided_code = None
                provided_version_id = None

            var_infos = self._collect_precondition_var_infos(
                precond_expr, resolved, precondition_variables
            )
            if not var_infos:
                continue
            key, entry = self._build_precondition_entry(
                var_infos, validation_codes, provided_code, provided_version_id
            )
            self._merge_precondition_entry(preconditions_dict, key, entry)

        return preconditions_dict, precondition_variables

    @staticmethod
    def _merge_precondition_entry(
        preconditions_dict: Dict[str, Any],
        key: str,
        entry: Dict[str, Any],
    ) -> None:
        """Insert *entry* under *key*; merge ops on collision.

        Two preconditions with the same variable-vid set produce the
        same key. Without merging, the second occurrence used to
        clobber the first and lose its ``affected_operations``.
        """
        existing = preconditions_dict.get(key)
        if existing is None:
            preconditions_dict[key] = entry
            return
        merged_ops = list(existing.get("affected_operations", []))
        for op in entry.get("affected_operations", []):
            if op not in merged_ops:
                merged_ops.append(op)
        existing["affected_operations"] = merged_ops

    @staticmethod
    def _collect_precondition_var_infos(
        precondition_expr: str,
        resolved: Dict[str, Dict[str, int]],
        precondition_variables: Dict[str, str],
    ) -> List[Dict[str, int]]:
        """Resolve ``{v_*}`` codes in *precondition_expr* to var-info dicts.

        Updates *precondition_variables* in-place with the resolved
        ``{variable_vid: "b"}`` entries.
        """
        var_infos: List[Dict[str, int]] = []
        raw_codes = [
            _normalize_variable_code(m)
            for m in _VAR_REF_PATTERN.findall(precondition_expr)
        ]
        for var_code in raw_codes:
            info = resolved.get(var_code)
            if info is None:
                continue
            var_infos.append(
                {
                    "variable_code": var_code,  # type: ignore[dict-item]
                    "variable_id": info["variable_id"],
                    "variable_vid": info["variable_vid"],
                }
            )
            precondition_variables[str(info["variable_vid"])] = "b"
        return var_infos

    @staticmethod
    def _build_precondition_entry(
        var_infos: List[Dict[str, Any]],
        validation_codes: List[str],
        provided_code: Optional[str] = None,
        provided_version_id: Optional[int] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Assemble a single ``preconditions[key]`` entry.

        Single-variable case → ``p_<vid>`` with a ``PreconditionItem``
        AST. Compound case → ``p_<sorted_vids>`` with a left-folded
        chain of ``BinOp(op="and")`` nodes.

        When provided_code or provided_version_id are supplied, they override
        the auto-generated values.
        """
        if len(var_infos) == 1:
            vi = var_infos[0]
            default_key = f"p_{vi['variable_vid']}"
            code = provided_code if provided_code is not None else default_key
            version_id = (
                provided_version_id
                if provided_version_id is not None
                else vi["variable_vid"]
            )
            return code, {
                "ast": {
                    "class_name": "PreconditionItem",
                    "variable_id": vi["variable_id"],
                    "variable_code": vi["variable_code"],
                },
                "affected_operations": list(validation_codes),
                "version_id": version_id,
                "code": code,
            }

        sorted_vids = sorted(vi["variable_vid"] for vi in var_infos)
        default_key = "p_" + "_".join(str(v) for v in sorted_vids)
        code = provided_code if provided_code is not None else default_key
        version_id = (
            provided_version_id
            if provided_version_id is not None
            else sorted_vids[0]
        )
        ast_node: Dict[str, Any] = {
            "class_name": "PreconditionItem",
            "variable_id": var_infos[0]["variable_id"],
            "variable_code": var_infos[0]["variable_code"],
        }
        for vi in var_infos[1:]:
            ast_node = {
                "class_name": "BinOp",
                "op": "and",
                "left": ast_node,
                "right": {
                    "class_name": "PreconditionItem",
                    "variable_id": vi["variable_id"],
                    "variable_code": vi["variable_code"],
                },
            }
        return code, {
            "ast": ast_node,
            "affected_operations": list(validation_codes),
            "version_id": version_id,
            "code": code,
        }

    # ------------------------------------------------------------------ #
    # AST helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _clean_ast_data_entries(ast_dict: Any) -> Any:
        """Strip engine-internal debug fields from ``VarID`` data entries.

        Mirrors pydpm's ``_clean_ast_data_entries``: drops
        ``data_type``, ``cell_code``, ``table_code``, ``table_vid``
        from each entry of every ``VarID`` node's ``data`` array.
        Operates in-place.
        """
        if isinstance(ast_dict, dict):
            ASTGeneratorService._strip_varid_data(ast_dict)
            for value in ast_dict.values():
                if isinstance(value, (dict, list)):
                    ASTGeneratorService._clean_ast_data_entries(value)
        elif isinstance(ast_dict, list):
            for item in ast_dict:
                if isinstance(item, (dict, list)):
                    ASTGeneratorService._clean_ast_data_entries(item)
        return ast_dict

    @staticmethod
    def _strip_varid_data(node: Dict[str, Any]) -> None:
        """Drop debug fields from a single ``VarID`` node's ``data`` list."""
        if node.get("class_name") != "VarID":
            return
        data = node.get("data")
        if not isinstance(data, list):
            return
        for entry in data:
            if not isinstance(entry, dict):
                continue
            for name in _DATA_FIELDS_TO_STRIP:
                entry.pop(name, None)

    @staticmethod
    def _extract_referenced_tables(ast_dict: Any) -> set[str]:
        """Walk a serialised AST and return referenced table codes."""
        codes: set[str] = set()

        def _walk(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("class_name") == "VarID":
                    table = node.get("table")
                    if isinstance(table, str) and table:
                        codes.add(table)
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        _walk(value)
            elif isinstance(node, list):
                for item in node:
                    if isinstance(item, (dict, list)):
                        _walk(item)

        _walk(ast_dict)
        return codes

    @staticmethod
    def _extract_operand_datapoints(ast_dict: Any) -> Dict[str, str]:
        """Walk a serialised AST and return ``{datapoint: data_type}``.

        Every ``VarID`` node carries one ``data`` entry per data point its
        cell reference resolves to, each holding the datapoint id (the
        variable id) and its scalar type code. Must run *before*
        :meth:`_clean_ast_data_entries`, which strips ``data_type``.

        A datapoint with no type resolves to ``""`` — the same fallback
        :meth:`ScopeCalculatorService._get_module_tables` uses when a
        property carries no data type.
        """
        datapoints: Dict[str, str] = {}

        def _walk(node: Any) -> None:
            if isinstance(node, dict):
                ASTGeneratorService._collect_varid_datapoints(node, datapoints)
                children: Iterable[Any] = node.values()
            elif isinstance(node, list):
                children = node
            else:
                return
            for child in children:
                if isinstance(child, (dict, list)):
                    _walk(child)

        _walk(ast_dict)
        return datapoints

    @staticmethod
    def _collect_varid_datapoints(
        node: Dict[str, Any],
        into: Dict[str, str],
    ) -> None:
        """Record one ``VarID`` node's datapoints and types into *into*."""
        if node.get("class_name") != "VarID":
            return
        data = node.get("data")
        if not isinstance(data, list):
            return
        for entry in data:
            if not isinstance(entry, dict):
                continue
            dp = entry.get("datapoint")
            if dp is None:
                continue
            into[str(dp)] = entry.get("data_type") or ""

    def _accumulate_parameters(
        self,
        accumulated: Dict[str, ParameterInfo],
        parameters: Iterable[ParameterInfo],
    ) -> None:
        """Merge one expression's parameters into ``accumulated``, by code.

        Consumes the already-deduped ``SemanticResult.parameters`` produced by
        the semantic pass rather than re-walking the serialised AST, so there
        is a single source of truth for which parameters an expression
        references. A parameter binds to a single value across every operation
        it co-executes with, so its declared type is intrinsic and must stay
        consistent script-wide — the flat registry holds one type per code.
        Raises ``SemanticError`` ``3-8`` on a conflicting redeclaration rather
        than silently letting one reference win. The merge itself lives in
        :func:`~dpmcore.services._parameters.merge_parameters`, shared with
        :meth:`~dpmcore.services.semantic.SemanticService.validate`, which
        applies the same rule across an expression and its precondition.
        """
        merge_parameters(accumulated, parameters)

    def _build_precondition_index(
        self,
        preconditions: List[Union[Tuple[str, List[str]], Dict[str, Any]]],
    ) -> Dict[str, List[str]]:
        """Map each validation code → unioned precondition variable codes.

        Parses each precondition expression once and extracts variable
        codes that act as precondition items. Raises ``ValueError`` if
        a precondition expression cannot be parsed.
        Supports both tuple and dict formats.
        """
        index: Dict[str, List[str]] = {}
        for precond_spec in preconditions:
            if isinstance(precond_spec, dict):
                precond_expr = precond_spec["expression"]
                validation_codes = precond_spec["affected_operations"]
            else:
                precond_expr, validation_codes = precond_spec

            try:
                ast = self._syntax.parse(precond_expr)
            except Exception as exc:
                raise ValueError(
                    f"Invalid precondition expression {precond_expr!r}: {exc}"
                ) from exc
            codes = self._extract_precondition_codes(ast)
            for vc in validation_codes:
                merged = index.setdefault(vc, [])
                for c in codes:
                    if c not in merged:
                        merged.append(c)
        return index

    @staticmethod
    def _extract_precondition_codes(ast: Any) -> List[str]:
        """Return the variable codes referenced by a precondition AST.

        Delegates to :func:`~dpmcore.services._precondition_codes.\
extract_precondition_codes`, shared with
        :class:`~dpmcore.services.scope_calculator.ScopeCalculatorService`.
        Kept as a method so it stays an overridable seam.
        """
        return _extract_precondition_codes(ast)

    def _build_dependency_info(
        self,
        scope_pairs: List[
            Tuple[
                Tuple[str, str],
                "ScopeResult",
                Dict[str, List[str]],
                _OperandRefs,
            ]
        ],
        primary_module_vid: Optional[int],
        release_id: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        """Build dependency_info from collected scope results.

        Aggregates across all expressions: merges
        ``intra_instance_validations`` and deduplicates
        ``cross_instance_dependencies`` by module URI set,
        appending new ``affected_operations`` to existing entries.
        """
        if (
            not self._scope_calc
            or primary_module_vid is None
            or not scope_pairs
        ):
            return None

        all_intra: List[str] = []
        all_cross: List[Dict[str, Any]] = []
        all_dep_modules: Dict[str, Any] = {}
        all_scope_results: List["ScopeResult"] = []

        # The home-module table set is a per-script constant (the
        # primary module never changes across this loop), and computing
        # it inside ``detect_cross_module_dependencies`` would repeat a
        # per-table variable/open-key fetch on every iteration. Compute
        # it once here and thread it through.
        home_module_tables: Set[str] = set(
            self._scope_calc._get_module_tables(
                primary_module_vid, release_id=release_id
            ).keys()
        )

        for item, sr, ts, refs in scope_pairs:
            all_scope_results.append(sr)
            op_code = item[1]
            current = self._scope_calc.detect_cross_module_dependencies(
                scope_result=sr,
                primary_module_vid=primary_module_vid,
                operation_code=op_code,
                release_id=release_id,
                time_shifts=ts,
                compute_alternative_deps=False,
                referenced_variables=refs.variables,
                referenced_tables=refs.tables,
                home_module_tables=home_module_tables,
            )
            all_intra.extend(current.get("intra_instance_validations", []))
            self._merge_cross_deps(
                all_cross,
                current.get("cross_instance_dependencies", []),
            )
            self._merge_dep_modules(
                all_dep_modules,
                current.get("dependency_modules", {}),
            )

        # Restrict alternatives to the script's genuine dependency modules
        # so the groups can never name a module absent from
        # ``dependency_modules`` (#202 dangling references).
        alt_deps = self._scope_calc.detect_alternative_dependencies(
            scope_results=all_scope_results,
            primary_module_vid=primary_module_vid,
            release_id=release_id,
            valid_module_uris=set(all_dep_modules),
        )

        deduped_intra: List[str] = list(dict.fromkeys(all_intra))

        return {
            "dependency_information": {
                "intra_instance_validations": deduped_intra,
                "cross_instance_dependencies": all_cross,
                "alternative_dependencies": alt_deps,
            },
            "dependency_modules": all_dep_modules,
        }

    @staticmethod
    def _merge_cross_deps(
        existing: List[Dict[str, Any]],
        new: List[Dict[str, Any]],
    ) -> None:
        """Merge *new* cross-instance deps into *existing*.

        Deduplicates by the set of ``(module URI, reference period)``
        pairs. When a duplicate is found, its ``affected_operations``
        are merged instead.

        The reference period is part of the key because two operations
        can need the *same* module at *different* instances — one at
        ``T``, another at ``T-1Q`` (#325 makes a non-default period
        reachable for the home module). Keying on the URI alone merged
        them into a single entry whose period was whichever operation
        came first, silently sending the other to the wrong instance.
        """

        def _uri_key(dep: Dict[str, Any]) -> Tuple[Tuple[str, str], ...]:
            modules = dep.get("modules", [])
            return tuple(
                sorted(
                    (m.get("URI", ""), m.get("ref_period", ""))
                    if isinstance(m, dict)
                    else (str(m), "")
                    for m in modules
                )
            )

        seen = {_uri_key(d) for d in existing}

        for dep in new:
            key = _uri_key(dep)
            if key not in seen:
                existing.append(dep)
                seen.add(key)
            else:
                for ex in existing:
                    if _uri_key(ex) == key:
                        ops = ex.setdefault("affected_operations", [])
                        for op in dep.get("affected_operations", []):
                            if op not in ops:
                                ops.append(op)
                        break

    @staticmethod
    def _merge_dep_modules(
        existing: Dict[str, Any],
        new: Dict[str, Any],
    ) -> None:
        """Merge *new* dependency_modules into *existing*.

        Avoids table duplicates within each module URI. Two operations
        can reference different cells of the same dependency table, and
        each declares only the datapoints it uses (#250), so a repeated
        table unions its ``variables`` rather than keeping the first.
        """
        for uri, data in new.items():
            if uri not in existing:
                existing[uri] = data
                continue
            tables = existing[uri].setdefault("tables", {})
            for tbl, tbl_data in data.get("tables", {}).items():
                if tbl not in tables:
                    tables[tbl] = tbl_data
                    continue
                merged_vars = dict(tables[tbl].get("variables", {}))
                merged_vars.update(tbl_data.get("variables", {}))
                tables[tbl] = {**tables[tbl], "variables": merged_vars}
            existing[uri].setdefault("variables", {}).update(
                data.get("variables", {})
            )

    @staticmethod
    def _to_ref_period(internal: str) -> str:
        """Render a ``t(+|-)<indicator><n>`` marker as a reference period.

        The declared period is the *opposite* of the shift the expression
        asks for. ``time_shift`` moves the operand's reference period by
        ``shift_number``, so the instance whose shifted operand lines up
        with the one being reported is the one at ``T - shift_number``:
        ``time_shift(x, A, 1, refPeriod)`` needs ``T-1A`` and
        ``time_shift(x, Q, -1, refPeriod)`` needs ``T+1Q``. The marker is
        built with that inversion already applied (see
        :meth:`_extract_time_shifts`), so this only reorders it.
        """
        if internal.startswith(("t+", "t-")):
            sign = internal[1]
            ind = internal[2]
            num = internal[3:]
            return f"T{sign}{num}{ind}"
        return "T"

    @staticmethod
    def _literal_shift(node: Any) -> Tuple[int, Optional[int]]:
        """Resolve a ``shift_number`` expression to ``(sign, magnitude)``.

        ``sign`` is the direction the expression asks for (``1`` or
        ``-1``) and ``magnitude`` its size, or ``None`` when the shift
        number is not an integer literal — a reference or a computed
        expression, whose size no reference period can name.

        The same written literal reaches this in several shapes, and
        reading only the two obvious ones mis-declared the rest: ``+1``
        is a ``UnaryOp``, so it lost its size and rendered ``T-nQ``;
        ``( -1 )`` is a ``ParExpr`` around one, so it lost its direction
        too; and ``(-1)`` without the spaces is lexed as a *negative*
        ``Constant``, which rendered the sign twice (``T--1Q``).
        """
        from dpmcore.dpm_xl.ast.nodes import Constant, ParExpr, UnaryOp

        sign = 1
        while True:
            if isinstance(node, ParExpr):
                node = node.expression
            elif isinstance(node, UnaryOp) and node.op in ("+", "-"):
                if node.op == "-":
                    sign = -sign
                node = node.operand
            else:
                break
        if not isinstance(node, Constant):
            return sign, None
        try:
            shift = sign * int(node.value)
        except (TypeError, ValueError):
            return sign, None
        return (-1 if shift < 0 else 1), abs(shift)

    def _prepare_expression(
        self,
        semantic: SemanticService,
        expr: str,
        release_id: int,
    ) -> _PreparedExpression:
        """Validate *expr* and read the reference periods it needs.

        ``validate()`` runs the per-expression scope check: a parameter
        referenced here must not clash with the declared type of a
        co-scoped operation already persisted in the DB (raises 3-8).
        ``_accumulate_parameters`` in the caller is complementary — it
        catches conflicts between two expressions in the same script.
        """
        result = semantic.validate(expr, release_id=release_id)
        if not result.is_valid:
            return _PreparedExpression(
                error=result.error_message or "",
            )
        ast = semantic.ast
        try:
            return _PreparedExpression(
                result=result,
                ast=ast,
                ts=self._extract_time_shifts(ast),
            )
        except SemanticError as exc:
            return _PreparedExpression(error=str(exc))

    @staticmethod
    def _shift_marker(node: Any) -> str:
        """Return the ``t(+|-)<indicator><n>`` marker for a time shift.

        The marker encodes the *declared* period, which inverts the
        shift the expression asks for: ``time_shift(x, A, 1, refPeriod)``
        reads the instance at ``T-1A`` and
        ``time_shift(x, Q, -1, refPeriod)`` the one at ``T+1Q``. A shift
        of ``0`` is no shift at all, so it keeps the plain marker.

        Raises:
            SemanticError: 4-7-5, when the shift number is not an
                integer literal. Such a shift used
                to render as ``T-nQ``, which names no resolvable
                instance and so silently sent the operation to an
                instance the engine cannot load (#326).
        """
        sign, magnitude = ASTGeneratorService._literal_shift(node.shift_number)
        if magnitude is None:
            raise SemanticError("4-7-5")
        if magnitude == 0:
            return "t"
        # ``magnitude`` is unsigned, so the sign is carried by the marker
        # alone — a ``Constant`` holding a negative value would otherwise
        # render two signs (``t-Q-1``).
        marker = "-" if sign > 0 else "+"
        return f"t{marker}{node.period_indicator}{magnitude}"

    @staticmethod
    def _extract_time_shifts(ast: Any) -> Dict[str, List[str]]:
        """Extract the reference periods each table is referenced at.

        Returns a mapping of table codes to the sorted, de-duplicated
        reference periods that table is read at, e.g.
        ``{"C_01.00": ["T", "T-1Q"]}``.

        One period per table is not enough (#326): a table read both
        plain and shifted, or shifted twice by different amounts, needs
        one instance per period, and keeping a single period collapsed
        the rest into whichever the visitor reached last. Unshifted
        references are recorded as ``"T"`` too, so a module read at both
        the current and a shifted instance is visible to the caller
        instead of being declared at the shifted one alone.

        Raises:
            SemanticError: 4-7-5, propagated from
                :meth:`_shift_marker` for a non-literal shift number.
        """
        from dpmcore.dpm_xl.ast.template import ASTTemplate

        time_shifts: Dict[str, Set[str]] = {}
        current_period = ["t"]

        class _Extractor(ASTTemplate):
            def visit_AnnualiseOp(self, node: Any) -> None:
                self.visit(node.operand)

            def visit_TimeShiftOp(self, node: Any) -> None:
                prev = current_period[0]
                current_period[0] = ASTGeneratorService._shift_marker(node)
                self.visit(node.operand)
                current_period[0] = prev

            def visit_VarID(self, node: Any) -> None:
                if node.table:
                    time_shifts.setdefault(node.table, set()).add(
                        current_period[0]
                    )

        try:
            _Extractor().visit(ast)
        except SemanticError:
            # A shift whose period cannot be declared is the caller's
            # decision to act on, not something to swallow into an
            # empty mapping.
            raise
        except Exception:
            logger.exception(
                "Failed to extract time shifts; returning an empty mapping.",
            )
            return {}
        return {
            table: sorted(
                {ASTGeneratorService._to_ref_period(p) for p in periods}
            )
            for table, periods in time_shifts.items()
        }


__all__ = ["ASTGeneratorService"]
