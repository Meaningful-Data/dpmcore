"""Semantic validation service — requires a database session."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.dpm_xl.utils.filters import resolve_release_id
from dpmcore.dpm_xl.warning_collector import collect_warnings
from dpmcore.errors import SemanticError
from dpmcore.orm.infrastructure import Release
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class SemanticResult:
    """Outcome of a semantic validation."""

    is_valid: bool
    error_message: Optional[str]
    error_code: Optional[str]
    expression: str
    results: Optional[Any] = None
    warning: Optional[str] = None


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

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def validate(
        self,
        expression: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> SemanticResult:
        """Full semantic validation of *expression*.

        Returns a :class:`SemanticResult` — never raises on validation
        failure.
        """
        try:
            release_id = resolve_release_id(
                self.session,
                release_id=release_id,
                release_code=release_code,
            )
            if release_id is not None:
                exists = (
                    self.session.query(Release.release_id)
                    .filter(Release.release_id == release_id)
                    .first()
                )
                if exists is None:
                    raise SemanticError("1-21", release_id=release_id)

            ast = self._syntax.parse(expression)
            self.ast = ast

            with collect_warnings() as wc:
                oc = OperandsChecking(
                    session=self.session,
                    expression=expression,
                    ast=ast,
                    release_id=release_id,
                )
                self.oc_data = oc.data
                self.oc_tables = oc.tables

                analyzer = InputAnalyzer(expression)
                analyzer.data = oc.data
                analyzer.key_components = oc.key_components
                analyzer.open_keys = oc.open_keys
                analyzer.preconditions = oc.preconditions

                results = analyzer.visit(ast)

            return SemanticResult(
                is_valid=True,
                error_message=None,
                error_code=None,
                expression=expression,
                results=results,
                warning=wc.get_combined_warning(),
            )

        except SemanticError as exc:
            self.oc_data = None
            self.oc_tables = None
            return SemanticResult(
                is_valid=False,
                error_message=str(exc),
                error_code=getattr(exc, "code", None),
                expression=expression,
            )
        except Exception as exc:
            self.oc_data = None
            self.oc_tables = None
            return SemanticResult(
                is_valid=False,
                error_message=str(exc),
                error_code="UNKNOWN",
                expression=expression,
            )

    def is_valid(
        self,
        expression: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> bool:
        """Quick boolean check."""
        return self.validate(
            expression,
            release_id=release_id,
            release_code=release_code,
        ).is_valid
