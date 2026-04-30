"""Engine-ready AST generation service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from dpmcore.services.semantic import SemanticService
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from dpmcore.services.scope_calculator import (
        ScopeCalculatorService,
        ScopeResult,
    )


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
    ) -> Dict[str, Any]:
        """Generate an engine-ready validations script.

        Args:
            expressions: ``[(expression, validation_code), ...]``.
            module_code: Code of the primary module the validations
                belong to (e.g. ``"COREP_Con"``).
            module_version: Version of the primary module
                (e.g. ``"2.0.1"``).
            preconditions: Optional list of
                ``(precondition_expression, [validation_codes])``
                tuples. A precondition can guard many validation
                codes; a validation may have no precondition.
            severity: Optional severity tag (``"error"``,
                ``"warning"``, ``"info"``) attached to each
                generated validation in the enriched AST.

        Returns a dict with ``success``, ``enriched_ast``,
        ``dependency_information``, ``dependency_modules``, and
        ``error`` keys.
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
            from dpmcore.dpm_xl.ast.ml_generation import MLGeneration
            from dpmcore.dpm_xl.ast.module_analyzer import ModuleAnalyzer

            mv = self._resolve_module_version(module_code, module_version)
            if mv is None:
                return {
                    "success": False,
                    "enriched_ast": None,
                    "error": (
                        f"ModuleVersion not found: "
                        f"{module_code} {module_version}"
                    ),
                }

            primary_module_vid: int = mv.module_vid
            release_id: Optional[int] = mv.start_release_id

            # Index preconditions by validation code.
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

            results = []
            scope_pairs: List[
                tuple[Tuple[str, str], "ScopeResult", Dict[str, str]]
            ] = []

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
                module_analyzer = ModuleAnalyzer(session)
                mode, modules = module_analyzer.visit(ast)

                ml = MLGeneration(
                    session=session,
                    ast=ast,
                    release_id=release_id,
                    module_code=module_code,
                    mode=mode,
                    modules=modules,
                    severity=severity,
                )
                results.append(ml)

                # Collect scope results for dependency detection
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

            dependency_info = self._build_dependency_info(
                scope_pairs=scope_pairs,
                primary_module_vid=primary_module_vid,
                release_id=release_id,
            )

            response: Dict[str, Any] = {
                "success": True,
                "enriched_ast": results,
                "error": None,
            }
            if dependency_info is not None:
                response["dependency_information"] = dependency_info[
                    "dependency_information"
                ]
                response["dependency_modules"] = dependency_info[
                    "dependency_modules"
                ]

            return response

        except Exception as exc:
            return {
                "success": False,
                "enriched_ast": None,
                "error": str(exc),
            }

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
            tuple[Tuple[str, str], "ScopeResult", Dict[str, str]]
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

        def _uri_key(dep: Dict[str, Any]) -> tuple[str, ...]:
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
                # Merge affected_operations
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
