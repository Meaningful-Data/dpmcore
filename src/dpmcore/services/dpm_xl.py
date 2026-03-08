"""Unified DPM-XL service facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from dpmcore.services.ast_generator import ASTGeneratorService
from dpmcore.services.scope_calculator import ScopeCalculatorService
from dpmcore.services.semantic import SemanticService
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class DpmXlService:
    """One-stop facade for all DPM-XL operations.

    Composes the individual services and provides convenient shortcuts
    for common workflows.

    Args:
        session: An open SQLAlchemy session (optional for syntax-only
            operations).
    """

    def __init__(self, session: Optional["Session"] = None) -> None:
        self.syntax = SyntaxService()
        self.session = session

        if session is not None:
            self.semantic = SemanticService(session)
            self.ast_generator = ASTGeneratorService(session)
            self.scope_calculator = ScopeCalculatorService(session)
        else:
            self.semantic = None  # type: ignore[assignment]
            self.ast_generator = ASTGeneratorService()
            self.scope_calculator = None  # type: ignore[assignment]

    def validate_syntax(self, expression: str) -> dict:
        """Validate syntax only (no DB required)."""
        result = self.syntax.validate(expression)
        return {
            "is_valid": result.is_valid,
            "error_message": result.error_message,
            "expression": result.expression,
        }

    def validate_semantic(
        self,
        expression: str,
        release_id: Optional[int] = None,
    ) -> dict:
        """Full semantic validation (requires DB)."""
        if self.semantic is None:
            raise RuntimeError("No database session provided.")
        result = self.semantic.validate(expression, release_id=release_id)
        return {
            "is_valid": result.is_valid,
            "error_message": result.error_message,
            "error_code": result.error_code,
            "expression": result.expression,
            "warning": result.warning,
        }
