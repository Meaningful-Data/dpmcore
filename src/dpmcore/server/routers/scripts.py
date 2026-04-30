"""Validations-script generation endpoint."""

from __future__ import annotations

from typing import Any, Callable, Dict, Generator, List, Optional

from fastapi import Depends
from fastapi.routing import APIRouter
from pydantic import BaseModel
from sqlalchemy.orm import Session


class PreconditionEntry(BaseModel):
    """A precondition expression and the validation codes it guards."""

    expression: str
    validation_codes: List[str]


class GenerateScriptRequest(BaseModel):
    """Request body for ``POST /scripts``."""

    expressions: List[List[str]]
    module_code: str
    module_version: str
    preconditions: Optional[List[PreconditionEntry]] = None
    severity: Optional[str] = None
    severities: Optional[Dict[str, str]] = None
    release: Optional[str] = None


class GenerateScriptResponse(BaseModel):
    """Response body for ``POST /scripts``.

    ``enriched_ast`` carries the namespaced engine-ready dict
    (``{module_uri: {module_code, dpm_release, operations,
    variables, tables, preconditions, dependency_information,
    dependency_modules, ...}}``). Dependency blocks live inside that
    namespace, not at the top level.
    """

    success: bool
    enriched_ast: Optional[Any] = None
    error: Optional[str] = None


def create_scripts_router(
    get_session: Callable[..., Generator[Session, None, None]],
) -> APIRouter:
    """Build the ``/scripts`` router."""
    router = APIRouter(prefix="/scripts")

    @router.post(
        "",
        response_model=GenerateScriptResponse,
        tags=["Scripts"],
        summary="Generate an engine-ready DPM-XL validations script.",
    )
    def generate_script(
        body: GenerateScriptRequest,
        session: Session = Depends(get_session),  # noqa: B008
    ) -> GenerateScriptResponse:
        from dpmcore.services.ast_generator import ASTGeneratorService

        items: List[tuple[str, str]] = [
            (item[0], item[1]) for item in body.expressions
        ]
        preconditions = (
            [
                (p.expression, list(p.validation_codes))
                for p in body.preconditions
            ]
            if body.preconditions
            else None
        )
        result = ASTGeneratorService(session).script(
            expressions=items,
            module_code=body.module_code,
            module_version=body.module_version,
            preconditions=preconditions,
            severity=body.severity,
            severities=body.severities,
            release=body.release,
        )
        return GenerateScriptResponse(
            success=bool(result.get("success")),
            enriched_ast=result.get("enriched_ast"),
            error=result.get("error"),
        )

    return router
