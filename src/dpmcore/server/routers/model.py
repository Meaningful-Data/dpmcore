"""Modelling endpoints: model validation and variable generation."""

from __future__ import annotations

from typing import Any, Callable, Dict, Generator, List, Optional

from fastapi import Depends, HTTPException
from fastapi.routing import APIRouter
from pydantic import BaseModel
from sqlalchemy.orm import Session

from dpmcore.errors import Invalid, NotFound


class ModelValidationRequest(BaseModel):
    """Request body for ``POST /model/validation``."""

    release_id: Optional[int] = None
    release_code: Optional[str] = None
    rule_ids: Optional[List[str]] = None
    include_warnings: bool = True


class VariableGenerationRequest(BaseModel):
    """Request body for ``POST /model/variable-generation``."""

    release_id: Optional[int] = None
    release_code: Optional[str] = None
    validate_first: bool = True


def create_model_router(
    get_session: Callable[..., Generator[Session, None, None]],
) -> APIRouter:
    """Build the ``/model`` router."""
    router = APIRouter(prefix="/model")

    @router.post(
        "/validation",
        tags=["Model"],
        summary="Run the DPM modelling rules and report violations.",
    )
    def validate_model(
        body: ModelValidationRequest,
        session: Session = Depends(get_session),  # noqa: B008
    ) -> Dict[str, Any]:
        from dpmcore.services.model_validation import (
            ModelValidationService,
        )

        try:
            result = ModelValidationService(session).validate(
                release_id=body.release_id,
                release_code=body.release_code,
                rule_ids=body.rule_ids,
                include_warnings=body.include_warnings,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Invalid as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result.to_dict()

    @router.get(
        "/validation/rules",
        tags=["Model"],
        summary="List the registered modelling rules.",
    )
    def list_rules(
        session: Session = Depends(get_session),  # noqa: B008
    ) -> List[Dict[str, Any]]:
        from dpmcore.services.model_validation import (
            ModelValidationService,
        )

        infos = ModelValidationService(session).list_rules()
        return [info.to_dict() for info in infos]

    @router.post(
        "/variable-generation",
        tags=["Model"],
        summary=(
            "Compute the variable-generation plan (no database writes)."
        ),
    )
    def generate_variables(
        body: VariableGenerationRequest,
        session: Session = Depends(get_session),  # noqa: B008
    ) -> Dict[str, Any]:
        from dpmcore.services.variable_generation import (
            VariableGenerationService,
        )

        try:
            result = VariableGenerationService(session).generate(
                release_id=body.release_id,
                release_code=body.release_code,
                validate_first=body.validate_first,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Invalid as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result.to_dict()

    return router
