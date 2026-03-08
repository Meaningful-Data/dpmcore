"""Operation scope calculation service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.dpm_xl.utils.scopes_calculator import OperationScopeService
from dpmcore.errors import SemanticError
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass
class ScopeResult:
    """Outcome of a scope calculation."""

    existing_scopes: list = field(default_factory=list)
    new_scopes: list = field(default_factory=list)
    total_scopes: int = 0
    module_versions: List[int] = field(default_factory=list)
    has_error: bool = False
    error_message: Optional[str] = None


class ScopeCalculatorService:
    """Calculate operation scopes for DPM-XL expressions.

    Determines which module versions are involved in an operation
    based on table references and precondition items.

    Args:
        session: An open SQLAlchemy session.
    """

    def __init__(self, session: "Session") -> None:
        self.session = session
        self._syntax = SyntaxService()

    def calculate_from_expression(
        self,
        expression: str,
        operation_version_id: int,
        release_id: Optional[int] = None,
        severity: Optional[str] = None,
    ) -> ScopeResult:
        """Calculate scopes for *expression*.

        Parses the expression, runs OperandsChecking to extract table
        version IDs and precondition items, then delegates to
        :class:`OperationScopeService`.
        """
        try:
            ast = self._syntax.parse(expression)
            oc = OperandsChecking(
                session=self.session,
                expression=expression,
                ast=ast,
                release_id=release_id,
            )

            table_vids = list(oc.tables.keys()) if oc.tables else []
            precondition_items = oc.preconditions or []

            scope_svc = OperationScopeService(
                operation_version_id=operation_version_id,
                session=self.session,
            )
            existing, new = scope_svc.calculate_operation_scope(
                tables_vids=table_vids,
                precondition_items=precondition_items,
                release_id=release_id,
            )

            all_scopes = existing + new
            mvids: List[int] = []
            for scope in all_scopes:
                for comp in getattr(scope, "operation_scope_compositions", []):
                    vid = comp.modulevid
                    if vid not in mvids:
                        mvids.append(vid)

            return ScopeResult(
                existing_scopes=existing,
                new_scopes=new,
                total_scopes=len(all_scopes),
                module_versions=mvids,
            )

        except (SemanticError, Exception) as exc:
            return ScopeResult(
                has_error=True,
                error_message=str(exc),
            )

    def calculate_from_tables(
        self,
        operation_version_id: int,
        table_vids: List[int],
        precondition_items: Optional[List[str]] = None,
        release_id: Optional[int] = None,
        table_codes: Optional[List[str]] = None,
    ) -> ScopeResult:
        """Calculate scopes directly from table version IDs."""
        try:
            scope_svc = OperationScopeService(
                operation_version_id=operation_version_id,
                session=self.session,
            )
            existing, new = scope_svc.calculate_operation_scope(
                tables_vids=table_vids,
                precondition_items=precondition_items or [],
                release_id=release_id,
                table_codes=table_codes,
            )

            all_scopes = existing + new
            mvids: List[int] = []
            for scope in all_scopes:
                for comp in getattr(scope, "operation_scope_compositions", []):
                    vid = comp.modulevid
                    if vid not in mvids:
                        mvids.append(vid)

            return ScopeResult(
                existing_scopes=existing,
                new_scopes=new,
                total_scopes=len(all_scopes),
                module_versions=mvids,
            )

        except Exception as exc:
            return ScopeResult(
                has_error=True,
                error_message=str(exc),
            )
