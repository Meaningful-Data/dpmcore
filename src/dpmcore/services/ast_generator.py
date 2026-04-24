"""AST generation service — three levels of detail."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from dpmcore.dpm_xl.utils.serialization import serialize_ast
from dpmcore.services.semantic import SemanticService
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from dpmcore.services.scope_calculator import (
        ScopeCalculatorService,
        ScopeResult,
    )


class ASTGeneratorService:
    """Generate AST representations at three levels of detail.

    1. **parse** — syntax-only AST (no database).
    2. **complete** — AST enriched with semantic metadata.
    3. **script** — engine-ready validations script.

    Args:
        session: An open SQLAlchemy session (only needed for levels 2-3).
    """

    def __init__(self, session: Optional["Session"] = None) -> None:
        """Build the service, optionally bound to a SQLAlchemy ``session``."""
        self.session = session
        self._syntax = SyntaxService()
        self._semantic: Optional[SemanticService] = None
        self._scope_calc: Optional["ScopeCalculatorService"] = None
        if session is not None:
            from dpmcore.services.scope_calculator import (
                ScopeCalculatorService,
            )

            self._semantic = SemanticService(session)
            self._scope_calc = ScopeCalculatorService(session)

    # ------------------------------------------------------------------ #
    # Level 1 — Basic AST (no DB)
    # ------------------------------------------------------------------ #

    def parse(self, expression: str) -> Dict[str, Any]:
        """Parse *expression* into a clean AST dict.

        No database required.
        """
        try:
            raw_ast = self._syntax.parse(expression)
            ast_dict = serialize_ast(raw_ast)
            return {
                "success": True,
                "ast": ast_dict,
                "error": None,
            }
        except Exception as exc:
            return {
                "success": False,
                "ast": None,
                "error": str(exc),
            }

    # ------------------------------------------------------------------ #
    # Level 2 — Complete AST (requires DB)
    # ------------------------------------------------------------------ #

    def complete(
        self,
        expression: str,
        release_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate a semantically enriched AST.

        Requires a database session.
        """
        if self._semantic is None:
            return {
                "success": False,
                "ast": None,
                "error": (
                    "No database session — cannot perform semantic analysis."
                ),
            }

        result = self._semantic.validate(expression, release_id=release_id)
        if not result.is_valid:
            return {
                "success": False,
                "ast": None,
                "error": result.error_message,
            }

        ast_dict = serialize_ast(self._semantic.ast)
        return {
            "success": True,
            "ast": ast_dict,
            "data": self._semantic.oc_data,
            "tables": self._semantic.oc_tables,
            "warning": result.warning,
            "error": None,
        }

    # ------------------------------------------------------------------ #
    # Level 3 — Validations Script (requires DB)
    # ------------------------------------------------------------------ #

    def script(
        self,
        expressions: Union[str, List[Tuple[str, ...]]],
        release_id: Optional[int] = None,
        module_code: Optional[str] = None,
        severity: Optional[str] = None,
        primary_module_vid: Optional[int] = None,
        operation_version_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate an engine-ready validations script.

        This is the highest-level output, suitable for execution
        engines and validation frameworks.

        When *primary_module_vid* and *operation_version_id* are
        supplied, scope-based ``dependency_info`` is computed and
        included in the response.
        """
        session = self.session
        if self._semantic is None or session is None:
            return {
                "success": False,
                "enriched_ast": None,
                "error": "No database session — cannot generate script.",
            }

        try:
            from dpmcore.dpm_xl.ast.ml_generation import MLGeneration
            from dpmcore.dpm_xl.ast.module_analyzer import ModuleAnalyzer

            # Normalise input to list of tuples
            if isinstance(expressions, str):
                items: List[Tuple[str, ...]] = [(expressions,)]
            else:
                items = expressions

            results = []
            scope_pairs: List[
                tuple[Tuple[str, ...], ScopeResult, Dict[str, str]]
            ] = []

            for item in items:
                expr = item[0]
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
                if (
                    self._scope_calc
                    and primary_module_vid
                    and operation_version_id
                ):
                    sr = self._scope_calc.calculate_from_expression(
                        expression=expr,
                        operation_version_id=operation_version_id,
                        release_id=release_id,
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

    def _build_dependency_info(
        self,
        scope_pairs: List[tuple[Tuple[str, ...], ScopeResult, Dict[str, str]]],
        primary_module_vid: Optional[int],
        release_id: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        """Build dependency_info from collected scope results.

        Args:
            scope_pairs: list of
                ``(item_tuple, ScopeResult, time_shifts)``
                triples so each scope result stays matched
                to its originating expression/operation code.
            primary_module_vid: the primary module VID.
            release_id: optional release filter.

        Aggregates across all expressions: merges
        ``intra_instance_validations`` and deduplicates
        ``cross_instance_dependencies`` by module URI set,
        appending new ``affected_operations`` to existing
        entries.
        """
        if not self._scope_calc or not primary_module_vid or not scope_pairs:
            return None

        all_intra: List[str] = []
        all_cross: List[Dict[str, Any]] = []
        all_dep_modules: Dict[str, Any] = {}
        all_scope_results: List[ScopeResult] = []

        for item, sr, ts in scope_pairs:
            all_scope_results.append(sr)
            op_code = item[1] if len(item) > 1 else None
            current = self._scope_calc.detect_cross_module_dependencies(
                scope_result=sr,
                primary_module_vid=primary_module_vid,
                operation_code=op_code,
                release_id=release_id,
                time_shifts=ts,
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

        Deduplicates by the set of module URIs.  When a
        duplicate is found, its ``affected_operations`` are
        merged instead.
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

        Returns a mapping of table codes to ref-period
        strings (e.g. ``{"C_01.00": "T-1Q"}``).
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
