"""Scope calculation endpoint."""

from __future__ import annotations

from typing import Callable, Generator, List, Optional

from fastapi import Depends
from fastapi.routing import APIRouter
from pydantic import BaseModel
from sqlalchemy.orm import Session


class ScopeRequest(BaseModel):
    """Request body for ``POST /scope``.

    ``precondition_items`` are filing-indicator variable codes;
    ``precondition_expression`` is a full DPM-XL gate expression whose own
    operands join the scope resolution. The two are independent.
    """

    expression: str
    release_id: Optional[int] = None
    release_code: Optional[str] = None
    precondition_items: Optional[List[str]] = None
    precondition_expression: Optional[str] = None


class ScopeResponse(BaseModel):
    """Response body for ``POST /scope``.

    The raw ``scopes`` collection produced by the service is intentionally
    omitted: it contains ORM objects that are not JSON-serialisable and
    callers only need the summary fields below. ``total_scopes`` and
    ``module_versions`` carry the information consumers actually use.

    ``warning`` is set when a supplied ``precondition_expression`` changed the
    scope; ``error_source`` names the half a failure belongs to.
    """

    total_scopes: int
    is_cross_module: bool
    module_versions: List[int]
    has_error: bool
    error_message: Optional[str] = None
    warning: Optional[str] = None
    error_source: Optional[str] = None


def create_scope_router(
    get_session: Callable[..., Generator[Session, None, None]],
) -> APIRouter:
    """Build the ``/scope`` router."""
    router = APIRouter(prefix="/scope")

    @router.post(
        "",
        response_model=ScopeResponse,
        tags=["Scope"],
        summary="Calculate the scope of a DPM-XL expression.",
    )
    def calculate_scope(
        body: ScopeRequest,
        session: Session = Depends(get_session),  # noqa: B008
    ) -> ScopeResponse:
        from dpmcore.services.scope_calculator import ScopeCalculatorService

        result = ScopeCalculatorService(session).calculate_from_expression(
            expression=body.expression,
            release_id=body.release_id,
            precondition_items=body.precondition_items,
            release_code=body.release_code,
            precondition_expression=body.precondition_expression,
        )
        return ScopeResponse(
            total_scopes=result.total_scopes,
            is_cross_module=result.is_cross_module,
            module_versions=result.module_versions,
            has_error=result.has_error,
            error_message=result.error_message,
            warning=result.warning,
            error_source=result.error_source,
        )

    return router
