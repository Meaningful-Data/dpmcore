"""AST generation service — three levels of detail."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from dpmcore.dpm_xl.utils.serialization import serialize_ast
from dpmcore.services.semantic import SemanticService
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ASTGeneratorService:
    """Generate AST representations at three levels of detail.

    1. **parse** — syntax-only AST (no database).
    2. **complete** — AST enriched with semantic metadata.
    3. **script** — engine-ready validations script.

    Args:
        session: An open SQLAlchemy session (only needed for levels 2-3).
    """

    def __init__(self, session: Optional["Session"] = None) -> None:
        self.session = session
        self._syntax = SyntaxService()
        self._semantic: Optional[SemanticService] = None
        if session is not None:
            self._semantic = SemanticService(session)

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
                "error": "No database session — cannot perform semantic analysis.",
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
    ) -> Dict[str, Any]:
        """Generate an engine-ready validations script.

        This is the highest-level output, suitable for execution
        engines and validation frameworks.
        """
        if self._semantic is None:
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
                module_analyzer = ModuleAnalyzer(self.session)
                mode, modules = module_analyzer.visit(ast)

                ml = MLGeneration(
                    session=self.session,
                    ast=ast,
                    release_id=release_id,
                    module_code=module_code,
                    mode=mode,
                    modules=modules,
                    severity=severity,
                )
                results.append(ml)

            return {
                "success": True,
                "enriched_ast": results,
                "error": None,
            }

        except Exception as exc:
            return {
                "success": False,
                "enriched_ast": None,
                "error": str(exc),
            }
