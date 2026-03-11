"""Generic structure router + artefact handlers (spec §5)."""

from __future__ import annotations

import enum
import json
from typing import Any, Callable, Dict, Generator, List, Optional

from fastapi import Depends, Path, Query, Response
from fastapi.routing import APIRouter
from pydantic import BaseModel
from sqlalchemy.orm import Session

from dpmcore.server.envelope import envelope, error_envelope
from dpmcore.server.params import (
    StructureParams,
    parse_structure_params,
)

# ------------------------------------------------------------------ #
# Artefact type enum (for Swagger dropdown)
# ------------------------------------------------------------------ #


class References(str, enum.Enum):
    """Related artefact inclusion level."""

    NONE = "none"
    ALL = "all"


class ArtefactType(str, enum.Enum):
    """Supported DPM artefact types."""

    CATEGORY = "category"
    CONTEXT = "context"
    DATATYPE = "datatype"
    FRAMEWORK = "framework"
    MODULE = "module"
    OPERATION = "operation"
    OPERATOR = "operator"
    ORGANISATION = "organisation"
    PROPERTY = "property"
    RELEASE = "release"
    STRUCTURE = "structure"
    TABLE = "table"
    TABLEGROUP = "tablegroup"
    VARIABLE = "variable"


# ------------------------------------------------------------------ #
# Handler registry
# ------------------------------------------------------------------ #

ARTEFACT_HANDLERS: Dict[str, Callable[..., Any]] = {}


def register_artefact(type_name: str):
    """Decorator to register a handler for an artefact type."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        ARTEFACT_HANDLERS[type_name] = fn
        return fn

    return decorator


# ------------------------------------------------------------------ #
# Response models (OpenAPI schema only — not used for serialization)
# ------------------------------------------------------------------ #


class MetaModel(BaseModel):
    """Response envelope metadata."""

    id: str
    prepared: str
    contentLanguage: str = "en"
    totalCount: Optional[int] = None
    offset: int = 0
    limit: int = 100


class StructureResponse(BaseModel):
    """Successful structure query response."""

    meta: MetaModel
    data: Dict[str, Any]


class ErrorDetail(BaseModel):
    """Single error entry in an error response."""

    code: int
    title: str
    detail: str


class ErrorResponseModel(BaseModel):
    """Error response envelope."""

    meta: MetaModel
    errors: List[ErrorDetail]


# ------------------------------------------------------------------ #
# Shared description (rendered as markdown in Swagger UI)
# ------------------------------------------------------------------ #

STRUCTURE_DESCRIPTION = (  # noqa: E501
    "Query DPM artefacts using SDMX-style URL conventions.\n\n"
    "**Path parameters**\n\n"
    "| Segment | Meaning |\n"
    "|---------|---------|  \n"
    "| `artefact_type` | One of the supported DPM artefact types |\n"
    "| `owner` | Organisation acronym, comma-separated list, "
    "or `*` (all) |\n"
    "| `id` | Artefact code, comma-separated list, "
    "or `*` (all) |\n"
    "| `release` | `~` latest · `+` latest stable · "
    "`*` all · literal release |\n\n"
    "**Query parameters**\n\n"
    "| Parameter | Default | Description |\n"
    "|-----------|---------|-------------|  \n"
    "| `detail` | `full` | Response detail level |\n"
    "| `references` | `none` | Related artefact inclusion |\n"
    "| `offset` | `0` | Results to skip (pagination) |\n"
    "| `limit` | `100` | Max results per page (1–1000) |\n\n"
    "**Detail levels:** `full`, `allstubs`, `allcompletestubs`, "
    "`referencestubs`, `referencecompletestubs`, "
    "`referencepartial`, `raw`\n\n"
    "**Response codes**\n\n"
    "- **200** — Matching artefacts found\n"
    "- **204** — Query valid but no results "
    "(SDMX convention: empty body)\n"
    "- **400** — Invalid parameter value\n"
    "- **422** — Invalid artefact type (not in the enum)\n"
)


# ------------------------------------------------------------------ #
# Router factory
# ------------------------------------------------------------------ #


def create_structure_router(
    get_session: Callable[..., Generator[Session, None, None]],
) -> APIRouter:
    """Create the ``/structure`` router with all registered handlers."""
    router = APIRouter(prefix="/structure")

    _type_path = Path(
        ..., description="DPM artefact type",
    )
    _owner_path = Path(
        ...,
        description=(
            "Organisation acronym, comma-separated, "
            "or * for all"
        ),
        json_schema_extra={"default": "*"},
    )
    _id_path = Path(
        ...,
        description=(
            "Artefact code, comma-separated, "
            "or * for all"
        ),
        json_schema_extra={"default": "*"},
    )
    _release_path = Path(
        ...,
        description=(
            "~ (latest) | + (latest stable) "
            "| * (all) | literal release"
        ),
        json_schema_extra={"default": "*"},
    )

    def _handler(
        artefact_type: ArtefactType = _type_path,  # noqa: B008
        owner: str = _owner_path,  # noqa: B008
        id: str = _id_path,  # noqa: B008
        release: str = _release_path,  # noqa: B008
        detail: str = Query(  # noqa: B008
            "full",
            description="Response detail level",
        ),
        references: References = Query(  # noqa: B008
            References.NONE,
            description="Related artefact inclusion",
        ),
        offset: int = Query(  # noqa: B008
            0, ge=0, description="Results to skip",
        ),
        limit: int = Query(  # noqa: B008
            100, ge=1, le=1000, description="Max results",
        ),
        session: Session = Depends(get_session),  # noqa: B008
    ) -> Any:
        type_value = artefact_type.value

        # "structure" is a wildcard — not backed by a handler
        if type_value not in ARTEFACT_HANDLERS:
            valid = ", ".join(sorted(ARTEFACT_HANDLERS.keys()))
            return Response(
                content=_json_dumps(
                    error_envelope(
                        400,
                        "Bad Request",
                        f"Unknown artefact type: "
                        f"'{type_value}'. "
                        f"Valid types are: {valid}",
                    )
                ),
                status_code=400,
                media_type="application/json",
            )

        params = parse_structure_params(owner, id, release)
        handler = ARTEFACT_HANDLERS[type_value]
        return handler(
            session=session,
            params=params,
            detail=detail,
            references=references.value,
            offset=offset,
            limit=limit,
        )

    _204_desc = (
        "Query valid but no results (SDMX convention)"
    )

    router.add_api_route(
        "/{artefact_type}/{owner}/{id}/{release}",
        _handler,
        methods=["GET"],
        tags=["Structure"],
        summary="Query DPM artefacts",
        description=STRUCTURE_DESCRIPTION,
        responses={
            200: {
                "model": StructureResponse,
                "description": "Matching artefacts",
            },
            204: {"description": _204_desc},
            400: {
                "model": ErrorResponseModel,
                "description": "Invalid parameter",
            },
        },
    )

    # Shorter path variants (hidden from OpenAPI docs)
    # Need a separate signature since Path() cannot have
    # defaults — these routes omit some path segments.
    def _short_handler(
        artefact_type: ArtefactType = _type_path,  # noqa: B008
        owner: str = "*",
        id: str = "*",
        release: str = "~",
        detail: str = Query(  # noqa: B008
            "full",
            description="Response detail level",
        ),
        references: References = Query(  # noqa: B008
            References.NONE,
            description="Related artefact inclusion",
        ),
        offset: int = Query(  # noqa: B008
            0, ge=0, description="Results to skip",
        ),
        limit: int = Query(  # noqa: B008
            100, ge=1, le=1000, description="Max results",
        ),
        session: Session = Depends(get_session),  # noqa: B008
    ) -> Any:
        return _handler(
            artefact_type=artefact_type,
            owner=owner,
            id=id,
            release=release,
            detail=detail,
            references=references,
            offset=offset,
            limit=limit,
            session=session,
        )

    for path in [
        "/{artefact_type}/{owner}/{id}",
        "/{artefact_type}/{owner}",
        "/{artefact_type}",
    ]:
        router.add_api_route(
            path, _short_handler, methods=["GET"],
            include_in_schema=False,
        )

    return router


# ------------------------------------------------------------------ #
# JSON helper
# ------------------------------------------------------------------ #


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj)


# ------------------------------------------------------------------ #
# Release handler
# ------------------------------------------------------------------ #


@register_artefact("release")
def handle_release(
    *,
    session: Session,
    params: StructureParams,
    detail: str,
    references: str,
    offset: int,
    limit: int,
) -> Any:
    """Handle ``/structure/release/...`` requests."""
    from dpmcore.services.structure import StructureService

    svc = StructureService(session)

    # Single release by code (non-wildcard id, no special release)
    if params.is_single_id and not params.wants_all_releases:
        owner = params.owners[0] if not params.is_owner_wildcard else None
        result = svc.get_release_by_code(
            params.ids[0], owner=owner, detail=detail,
        )
        if result is None:
            return Response(status_code=204)
        data: Dict[str, Any] = {"release": result}
        if references == "all":
            data["organisations"] = svc.get_release_organisations(
                [result.get("ownerId")],
            )
        return envelope(
            data, total_count=1, offset=0, limit=1,
        )

    # Collection query
    codes = None if params.is_id_wildcard else params.ids
    owners = None if params.is_owner_wildcard else params.owners

    results, total = svc.query_releases(
        owners=owners,
        codes=codes,
        latest=params.wants_latest and params.is_id_wildcard,
        latest_stable=params.wants_latest_stable,
        detail=detail,
        offset=offset,
        limit=limit,
    )

    if not results:
        return Response(status_code=204)

    data = {"releases": results}
    if references == "all":
        owner_ids = [r.get("ownerId") for r in results]
        data["organisations"] = svc.get_release_organisations(
            owner_ids,
        )

    return envelope(
        data,
        total_count=total,
        offset=offset,
        limit=limit,
    )


# ------------------------------------------------------------------ #
# Category handler
# ------------------------------------------------------------------ #


@register_artefact("category")
def handle_category(
    *,
    session: Session,
    params: StructureParams,
    detail: str,
    references: str,
    offset: int,
    limit: int,
) -> Any:
    """Handle ``/structure/category/...`` requests."""
    from dpmcore.services.structure import StructureService

    svc = StructureService(session)

    results, total = svc.query_categories(
        params=params,
        detail=detail,
        offset=offset,
        limit=limit,
    )

    if not results:
        return Response(status_code=204)

    data: Dict[str, Any] = {"categories": results}
    if references == "all":
        acronyms = list({
            r.get("owner")
            for r in results
            if r.get("owner") is not None
        })
        if acronyms:
            data["organisations"] = (
                svc.get_release_organisations(
                    _owner_ids_from_acronyms(svc, acronyms),
                )
            )

    return envelope(
        data,
        total_count=total,
        offset=offset,
        limit=limit,
    )


def _owner_ids_from_acronyms(
    svc: Any,
    acronyms: List[str],
) -> List[int]:
    """Resolve acronyms to org IDs for get_release_organisations."""
    from dpmcore.orm.infrastructure import Organisation

    orgs = (
        svc.session.query(Organisation)
        .filter(Organisation.acronym.in_(acronyms))
        .all()
    )
    return [o.org_id for o in orgs]
