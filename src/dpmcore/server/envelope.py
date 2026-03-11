"""Response envelope builder per REST API spec §9."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def build_meta(
    *,
    total_count: Optional[int] = None,
    offset: int = 0,
    limit: int = 100,
    content_language: str = "en",
) -> Dict[str, Any]:
    """Build the ``meta`` block for a success envelope."""
    meta: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "prepared": datetime.now(timezone.utc).isoformat(),
        "contentLanguage": content_language,
    }
    if total_count is not None:
        meta["totalCount"] = total_count
    meta["offset"] = offset
    meta["limit"] = limit
    return meta


def envelope(
    data: Dict[str, Any],
    *,
    total_count: Optional[int] = None,
    offset: int = 0,
    limit: int = 100,
    content_language: str = "en",
) -> Dict[str, Any]:
    """Wrap *data* in the standard success envelope."""
    return {
        "meta": build_meta(
            total_count=total_count,
            offset=offset,
            limit=limit,
            content_language=content_language,
        ),
        "data": data,
    }


def error_envelope(
    code: int,
    title: str,
    detail: str,
) -> Dict[str, Any]:
    """Build an error response envelope."""
    return {
        "meta": {
            "id": str(uuid.uuid4()),
            "prepared": datetime.now(timezone.utc).isoformat(),
        },
        "errors": [
            {
                "code": code,
                "title": title,
                "detail": detail,
            },
        ],
    }
