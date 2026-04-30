"""Engine-ready AST generation service."""

from __future__ import annotations

import logging
import re
import zlib
from datetime import date as date_cls
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Tuple,
)

from dpmcore.dpm_xl.utils.tokens import (
    SEVERITY_WARNING,
    VALID_SEVERITIES,
)
from dpmcore.services.semantic import SemanticService
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from dpmcore.services.scope_calculator import (
        ScopeCalculatorService,
        ScopeResult,
    )


logger = logging.getLogger(__name__)


_VAR_REF_PATTERN = re.compile(r"\{v_([^}]+)\}")
_TABLE_CODE_NORMALIZER = re.compile(r"^([A-Z]+)_(\d+)_(\d+)$")
_DEFAULT_FROM_DATE = "2001-01-01"
_DEFAULT_NAMESPACE = "default_module"
_DATA_FIELDS_TO_STRIP = ("data_type", "cell_code", "table_code", "table_vid")


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
        preconditions: Optional[List[Tuple[str, List[str]]]] = None,
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
            preconditions: Optional list of
                ``(precondition_expression, [validation_codes])`` tuples.
                A precondition can guard many validation codes; a
                validation may have no precondition.
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
            ``{"success": bool, "enriched_ast": <namespaced dict>,
            "error": <str | None>}``. The namespaced dict mirrors the
            shape pydpm's ``generate_validations_script`` produces.
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
                }

            from_submission_date = _format_date(
                mv.from_reference_date, fallback=_DEFAULT_FROM_DATE
            )

            operations: Dict[str, Dict[str, Any]] = {}
            scope_pairs: List[
                Tuple[Tuple[str, str], "ScopeResult", Dict[str, str]]
            ] = []
            referenced_table_codes: set[str] = set()

            for item in expressions:
                expr, code = item[0], item[1]
                result = self._semantic.validate(expr, release_id=release_id)
                if not result.is_valid:
                    return {
                        "success": False,
                        "enriched_ast": None,
                        "error": result.error_message,
                    }

                ast = self._semantic.ast
                ast_dict = serialize_ast(ast)
                self._clean_ast_data_entries(ast_dict)
                referenced_table_codes.update(
                    self._extract_referenced_tables(ast_dict)
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
                if not sr.has_error:
                    ts = self._extract_time_shifts(ast)
                    scope_pairs.append((item, sr, ts))

            primary_tables_full = self._scope_calc._get_module_tables(
                primary_module_vid, release_id=release_id
            )
            tables_block: Dict[str, Any] = {
                code: primary_tables_full[code]
                for code in sorted(referenced_table_codes)
                if code in primary_tables_full
            }
            variables_block: Dict[str, str] = {}
            for tbl in tables_block.values():
                variables_block.update(tbl.get("variables", {}))

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
                    release_id=release_id,
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
                "preconditions": preconditions_block,
                "precondition_variables": precondition_variables_block,
                "dependency_information": dep_information,
                "dependency_modules": dep_modules,
            }

            return {
                "success": True,
                "enriched_ast": {namespace: ns_block},
                "error": None,
            }

        except ValueError as exc:
            return {
                "success": False,
                "enriched_ast": None,
                "error": str(exc),
            }
        except Exception as exc:
            return {
                "success": False,
                "enriched_ast": None,
                "error": str(exc),
            }

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
        release_id sits inside ``mv``'s window. Raises ``ValueError``
        if the release is unknown, predates ``start_release_id``, or
        is past ``end_release_id``.
        """
        from dpmcore.orm.infrastructure import Release

        if self.session is None:
            raise RuntimeError("session required")
        release_row = (
            self.session.query(Release).filter(Release.code == release).first()
        )
        if release_row is None:
            raise ValueError(f"Release not found: {release}")
        rid = release_row.release_id
        start = mv.start_release_id
        end = mv.end_release_id
        if start is not None and rid < start:
            raise ValueError(
                f"Release {release} predates module version "
                f"{module_code} {module_version} "
                f"(starts at release_id={start})."
            )
        if end is not None and rid >= end:
            raise ValueError(
                f"Release {release} is past the end of module "
                f"version {module_code} {module_version} "
                f"(ends at release_id={end})."
            )
        return release_row

    def _latest_release_in_window(self, mv: Any) -> Any:
        """Pick the latest ``released`` Release covering *mv*'s window.

        Falls back to the latest of any status if no released row
        matches. Excluding draft/validation rows from the primary
        query ensures we don't generate URIs the engine rejects.
        """
        from sqlalchemy import or_

        from dpmcore.orm.infrastructure import Release

        if self.session is None:
            raise RuntimeError("session required")
        base_query = self.session.query(Release)
        if mv.start_release_id is not None:
            base_query = base_query.filter(
                Release.release_id >= mv.start_release_id
            )
        if mv.end_release_id is not None:
            base_query = base_query.filter(
                or_(Release.release_id < mv.end_release_id)
            )
        latest = (
            base_query.filter(Release.status == "released")
            .order_by(Release.release_id.desc())
            .first()
        )
        if latest is None:
            latest = base_query.order_by(Release.release_id.desc()).first()
        return latest

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

        Walks past structural wrappers (``Start``, ``ParExpr``,
        ``WithExpression``, ``PersistentAssignment`` /
        ``TemporaryAssignment``) down to the first node carrying an
        ``op`` attribute, then looks up ``Operator.OperatorID`` by
        ``Symbol`` via the same DataFrame
        ``MLGeneration.create_operation_node`` uses.

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
            if class_name == "ParExpr":
                node = node.expression
                continue
            if class_name == "WithExpression":
                node = node.expression
                continue
            if class_name in ("PersistentAssignment", "TemporaryAssignment"):
                # The assigned expression carries the comparison.
                node = node.right
                continue
            break

        op_symbol = getattr(node, "op", None)
        if not op_symbol:
            raise RuntimeError(
                f"Cannot resolve root operator: AST root "
                f"{type(node).__name__!r} has no 'op' attribute."
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
        preconditions: List[Tuple[str, List[str]]],
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
        for precondition_expr, _ in preconditions:
            for raw in _VAR_REF_PATTERN.findall(precondition_expr):
                normalized = _normalize_variable_code(raw)
                if normalized not in all_codes:
                    all_codes.append(normalized)
        if not all_codes:
            return preconditions_dict, precondition_variables

        resolved = VariableVersionQuery.get_variable_vids_by_codes(
            self.session, all_codes, release_id=release_id
        )

        for precondition_expr, validation_codes in preconditions:
            var_infos = self._collect_precondition_var_infos(
                precondition_expr, resolved, precondition_variables
            )
            if not var_infos:
                continue
            key, entry = self._build_precondition_entry(
                var_infos, validation_codes
            )
            preconditions_dict[key] = entry

        return preconditions_dict, precondition_variables

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
    ) -> Tuple[str, Dict[str, Any]]:
        """Assemble a single ``preconditions[key]`` entry.

        Single-variable case → ``p_<vid>`` with a ``PreconditionItem``
        AST. Compound case → ``p_<sorted_vids>`` with a left-folded
        chain of ``BinOp(op="and")`` nodes.
        """
        if len(var_infos) == 1:
            vi = var_infos[0]
            key = f"p_{vi['variable_vid']}"
            return key, {
                "ast": {
                    "class_name": "PreconditionItem",
                    "variable_id": vi["variable_id"],
                    "variable_code": vi["variable_code"],
                },
                "affected_operations": list(validation_codes),
                "version_id": vi["variable_vid"],
                "code": key,
            }

        sorted_vids = sorted(vi["variable_vid"] for vi in var_infos)
        key = "p_" + "_".join(str(v) for v in sorted_vids)
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
        return key, {
            "ast": ast_node,
            "affected_operations": list(validation_codes),
            "version_id": sorted_vids[0],
            "code": key,
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
            for field in _DATA_FIELDS_TO_STRIP:
                entry.pop(field, None)

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

    def _build_precondition_index(
        self,
        preconditions: List[Tuple[str, List[str]]],
    ) -> Dict[str, List[str]]:
        """Map each validation code → unioned precondition variable codes.

        Parses each precondition expression once and extracts variable
        codes that act as precondition items. Raises ``ValueError`` if
        a precondition expression cannot be parsed.
        """
        index: Dict[str, List[str]] = {}
        for precondition_expr, validation_codes in preconditions:
            try:
                ast = self._syntax.parse(precondition_expr)
            except Exception as exc:
                raise ValueError(
                    f"Invalid precondition expression "
                    f"{precondition_expr!r}: {exc}"
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

        Walks the AST collecting:
        - ``PreconditionItem.variable_code``
        - ``VarRef.variable``

        Either kind unambiguously identifies a precondition variable
        for scope-calculation purposes.
        """
        from dpmcore.dpm_xl.ast.template import ASTTemplate

        codes: List[str] = []

        class _Extractor(ASTTemplate):
            def visit_PreconditionItem(self, node: Any) -> None:
                vc = getattr(node, "variable_code", None)
                if vc and vc not in codes:
                    codes.append(vc)

            def visit_VarRef(self, node: Any) -> None:
                v = getattr(node, "variable", None)
                if v and v not in codes:
                    codes.append(v)

        try:
            _Extractor().visit(ast)
        except Exception:
            return []
        return codes

    def _build_dependency_info(
        self,
        scope_pairs: List[
            Tuple[Tuple[str, str], "ScopeResult", Dict[str, str]]
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

        for item, sr, ts in scope_pairs:
            all_scope_results.append(sr)
            op_code = item[1]
            current = self._scope_calc.detect_cross_module_dependencies(
                scope_result=sr,
                primary_module_vid=primary_module_vid,
                operation_code=op_code,
                release_id=release_id,
                time_shifts=ts,
                compute_alternative_deps=False,
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

        alt_deps = self._scope_calc.detect_alternative_dependencies(
            scope_results=all_scope_results,
            primary_module_vid=primary_module_vid,
            release_id=release_id,
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

        Deduplicates by the set of module URIs.  When a duplicate is
        found, its ``affected_operations`` are merged instead.
        """

        def _uri_key(dep: Dict[str, Any]) -> Tuple[str, ...]:
            modules = dep.get("modules", [])
            return tuple(
                sorted(
                    m.get("URI", "") if isinstance(m, dict) else str(m)
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

        Avoids table duplicates within each module URI.
        """
        for uri, data in new.items():
            if uri not in existing:
                existing[uri] = data
            else:
                for tbl, tbl_data in data.get("tables", {}).items():
                    existing[uri].setdefault("tables", {}).setdefault(
                        tbl, tbl_data
                    )
                existing[uri].setdefault("variables", {}).update(
                    data.get("variables", {})
                )

    @staticmethod
    def _extract_time_shifts(ast: Any) -> Dict[str, str]:
        """Extract per-table time shifts from an AST.

        Returns a mapping of table codes to ref-period strings
        (e.g. ``{"C_01.00": "T-1Q"}``).
        """
        from dpmcore.dpm_xl.ast.template import ASTTemplate

        time_shifts: Dict[str, str] = {}
        current_period = ["t"]

        class _Extractor(ASTTemplate):
            def visit_TimeShiftOp(self, node: Any) -> None:
                prev = current_period[0]
                pi = node.period_indicator
                sn = node.shift_number
                if "-" in str(sn):
                    current_period[0] = f"t+{pi}{sn}"
                else:
                    current_period[0] = f"t-{pi}{sn}"
                self.visit(node.operand)
                current_period[0] = prev

            def visit_VarID(self, node: Any) -> None:
                if node.table and current_period[0] != "t":
                    time_shifts[node.table] = current_period[0]

        def _to_ref_period(internal: str) -> str:
            if internal.startswith("t+"):
                ind = internal[2]
                num = internal[3:]
                if num.startswith("-"):
                    return f"T{num}{ind}"
                return f"T+{num}{ind}"
            if internal.startswith("t-"):
                ind = internal[2]
                num = internal[3:]
                return f"T-{num}{ind}"
            return "T"

        try:
            _Extractor().visit(ast)
            return {t: _to_ref_period(p) for t, p in time_shifts.items()}
        except Exception:
            return {}


__all__ = ["ASTGeneratorService"]
