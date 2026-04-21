"""Release and date filtering utilities for DPM queries.

Provides composable SQLAlchemy filter conditions for
release-based versioning and date-range queries.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Date, and_, cast, or_
from sqlalchemy.orm import Query


def filter_by_date(
    query: Any,
    date: Any,
    start_col: Any,
    end_col: Any,
) -> Any:
    """Filter a query by a date range.

    Args:
        query: SQLAlchemy Query or Select object.
        date: Date string (YYYY-MM-DD) or date object.
        start_col: Column representing start date.
        end_col: Column representing end date.

    Returns:
        Filtered query.
    """
    if not date:
        return query

    if isinstance(date, str):
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    else:
        target_date = date

    is_postgres = False
    if hasattr(query, "session") and query.session:
        bind = query.session.get_bind()
        if bind.dialect.name == "postgresql":
            is_postgres = True

    if is_postgres:
        start_expr = cast(start_col, Date)
        end_expr = cast(end_col, Date)
    else:
        start_expr = start_col
        end_expr = end_col

    return query.filter(
        and_(
            start_expr <= target_date,
            or_(
                end_col.is_(None),
                end_expr > target_date,
            ),
        )
    )


def filter_by_release(
    query: Any,
    start_col: Any,
    end_col: Any,
    release_id: Optional[int] = None,
    release_code: Optional[str] = None,
) -> Any:
    """Filter a query by DPM release versioning logic.

    Standard Logic:
        If release_id provided:
            start <= release_id AND
            (end is NULL OR end > release_id)
        If neither provided:
            Return query unmodified.

    Args:
        query: SQLAlchemy Query or Select object.
        start_col: Column for start release.
        end_col: Column for end release.
        release_id: Release ID to filter for.
        release_code: Release code to resolve.

    Returns:
        Filtered query.

    Raises:
        ValueError: If both release_id and release_code
            are specified.
    """
    if release_id is not None and release_code is not None:
        raise ValueError(
            "Specify a maximum of one of release_id or release_code."
        )

    if release_id is None and release_code is None:
        return query
    elif release_id:
        return query.filter(
            and_(
                start_col <= release_id,
                or_(
                    end_col.is_(None),
                    end_col > release_id,
                ),
            )
        )
    else:
        return query


def filter_active_only(query: Any, end_col: Any) -> Any:
    """Filter for currently active records.

    Args:
        query: SQLAlchemy Query or Select object.
        end_col: Column for end release.

    Returns:
        Filtered query with end_col IS NULL.
    """
    return query.filter(end_col.is_(None))


def filter_item_version(
    ref_start_col: Any,
    item_start_col: Any,
    item_end_col: Any,
) -> Any:
    """Build a version-range join condition.

    The pattern is::

        ref_start >= item_start
        AND (item_end IS NULL OR ref_start < item_end)

    Args:
        ref_start_col: Reference start-release column.
        item_start_col: Item's start-release column.
        item_end_col: Item's end-release column.

    Returns:
        SQLAlchemy boolean expression.
    """
    return and_(
        ref_start_col >= item_start_col,
        or_(
            ref_start_col < item_end_col,
            item_end_col.is_(None),
        ),
    )
