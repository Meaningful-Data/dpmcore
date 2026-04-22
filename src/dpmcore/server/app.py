"""FastAPI application factory for dpmcore."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Optional

from fastapi import Depends, FastAPI
from fastapi.routing import APIRouter
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

import dpmcore.orm  # noqa: F401  — ensure all models are loaded

# ------------------------------------------------------------------ #
# Request / response schemas
# ------------------------------------------------------------------ #


class ExpressionRequest(BaseModel):
    """Body for validation endpoints."""

    expression: str
    release_id: Optional[int] = None


class SyntaxResponse(BaseModel):
    """Syntax validation result."""

    is_valid: bool
    error_message: Optional[str]
    expression: str


class SemanticResponse(BaseModel):
    """Semantic validation result."""

    is_valid: bool
    error_message: Optional[str]
    error_code: Optional[str]
    expression: str
    warning: Optional[str] = None


# ------------------------------------------------------------------ #
# Application factory
# ------------------------------------------------------------------ #


def create_app(
    database_url: str,
    *,
    engine: Optional[Engine] = None,
) -> FastAPI:
    """Create a configured FastAPI application.

    Args:
        database_url: SQLAlchemy connection URL.
        engine: Optional pre-built SQLAlchemy engine (for testing).
    """
    if engine is None:
        engine = create_engine(database_url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title="dpmcore",
        version="0.0.1",
        description=(
            "REST API for the Data Point Model (DPM) "
            "2.0 Refit metamodel. Provides SDMX-style "
            "structure queries, DPM-XL expression "
            "validation, and health monitoring."
        ),
        lifespan=lifespan,
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
        openapi_tags=[
            {
                "name": "Health",
                "description": "Server health checks.",
            },
            {
                "name": "Validation",
                "description": (
                    "DPM-XL expression validation (syntax and semantic)."
                ),
            },
            {
                "name": "Structure",
                "description": (
                    "SDMX-style structure queries for DPM artefacts "
                    "(releases, tables, variables, etc.)."
                ),
            },
        ],
    )

    router = APIRouter(prefix="/api/v1")

    # -- dependency ---------------------------------------------------

    def get_session() -> Session:  # type: ignore[misc]
        session = session_factory()
        try:
            yield session  # type: ignore[misc]
        finally:
            session.close()

    # -- health -------------------------------------------------------

    @router.get("/health", tags=["Health"])
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    # -- DPM-XL validation --------------------------------------------

    @router.post(
        "/validate/syntax",
        response_model=SyntaxResponse,
        tags=["Validation"],
    )
    def validate_syntax(body: ExpressionRequest) -> SyntaxResponse:
        from dpmcore.services.syntax import SyntaxService

        result = SyntaxService().validate(body.expression)
        return SyntaxResponse(
            is_valid=result.is_valid,
            error_message=result.error_message,
            expression=result.expression,
        )

    @router.post(
        "/validate/semantic",
        response_model=SemanticResponse,
        tags=["Validation"],
    )
    def validate_semantic(
        body: ExpressionRequest,
        session: Session = Depends(get_session),  # noqa: B008
    ) -> SemanticResponse:
        from dpmcore.services.dpm_xl import DpmXlService

        result = DpmXlService(session).validate_semantic(
            body.expression,
            release_id=body.release_id,
        )
        return SemanticResponse(
            is_valid=result["is_valid"],
            error_message=result["error_message"],
            error_code=result["error_code"],
            expression=result["expression"],
            warning=result.get("warning"),
        )

    # -- structure endpoints (SDMX-style) --------------------------------

    from dpmcore.server.routers.structure import create_structure_router

    structure_router = create_structure_router(get_session)
    router.include_router(structure_router)

    app.include_router(router)
    return app
