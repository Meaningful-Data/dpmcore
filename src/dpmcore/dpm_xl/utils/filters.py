"""Release and date filtering utilities for DPM queries.

Provides composable SQLAlchemy filter conditions for
release-based versioning and date-range queries.

Release-range comparisons order releases by ``Release.date`` (via
:func:`dpmcore.orm.release_sort_order.resolve_sort_order`) rather than
by the raw ``Release.release_id`` FK, because EBA's post-4.2.1 ID scheme
is no longer monotonic (4.2.1 has ``ReleaseID = 1010000003``). Dates are
unique and follow the version lineage, so ordering by date works for
every ``code`` format — including EBA's four-segment codes and
non-versioned working releases — without parsing the code.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import Date, and_, cast, or_

from dpmcore.orm.release_sort_order import (
    load_release_sort_orders,
    release_ids_for_sort_order,
    resolve_sort_order,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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


def resolve_release_id(
    session: "Session",
    release_id: Optional[int] = None,
    release_code: Optional[str] = None,
) -> Optional[int]:
    """Normalise ``release_id`` / ``release_code`` to a single ``release_id``.

    Resolves a textual release code to its numeric ``ReleaseID`` via a
    :class:`Release` lookup so downstream filters only have to deal
    with one concept. Pass at most one of the two arguments.

    Args:
        session: SQLAlchemy session used for the code lookup.
        release_id: Already-resolved release ID; returned unchanged.
        release_code: Release code to resolve via ``Release.code``.

    Returns:
        The resolved release ID, or ``None`` when neither input is
        supplied.

    Raises:
        ValueError: If both ``release_id`` and ``release_code`` are
            specified, or if ``release_code`` does not match any
            release.
    """
    if release_id is not None and release_code is not None:
        raise ValueError(
            "Specify a maximum of one of release_id or release_code."
        )
    if release_code is None:
        return release_id

    # Local import keeps utils side of the dependency graph clean.
    from dpmcore.orm.infrastructure import Release

    row = (
        session.query(Release.release_id)
        .filter(Release.code == release_code)
        .first()
    )
    if row is None:
        raise ValueError(f"Release code {release_code!r} not found.")
    return row[0]


def filter_by_release(
    query: Any,
    start_col: Any,
    end_col: Any,
    release_id: Optional[int] = None,
    active_only_fallback: bool = False,
) -> Any:
    """Filter a query by DPM release versioning logic.

    Logic (date-ordered):
        If release_id provided:
            ``sort_order(start) <= sort_order(target)`` AND
            ``(end IS NULL OR sort_order(end) > sort_order(target))``,
            where ``sort_order`` is the release's ``Release.date``. This
            works for every ``code`` format — a ``"Playground"``/working
            release orders by its date like any other, and an undated
            working release ranks as the latest, so a request for it
            naturally resolves to the current rows.
        If release_id is None:
            * ``active_only_fallback=True`` → ``end_col IS NULL`` only
              (currently-active rows). Useful for callers that want a
              deterministic default when no release is supplied.
            * Otherwise → return query unmodified.

    Args:
        query: SQLAlchemy ``Query`` — must be a session-bound ``Query``
            (i.e. produced by ``Session.query(...)``). Core ``Select``
            statements are not supported because the helper needs the
            session to load the release mapping.
        start_col: Column for start release ID (FK to ``Release``).
        end_col: Column for end release ID (FK to ``Release``).
        release_id: Release ID to filter for.
        active_only_fallback: When True and ``release_id`` is None,
            apply :func:`filter_active_only` instead of returning the
            query unchanged.

    Returns:
        Filtered query.

    Raises:
        TypeError: If ``query`` is not a session-bound SQLAlchemy
            ``Query`` (e.g. a Core ``Select`` was passed).
        ValueError: If ``release_id`` does not correspond to a known
            ``Release`` row.
    """
    if release_id is None:
        if active_only_fallback:
            return filter_active_only(query, end_col)
        return query

    session = getattr(query, "session", None)
    if session is None:
        raise TypeError(
            "filter_by_release(query=...) expects a session-bound "
            "SQLAlchemy Query (Session.query(...)). Got "
            f"{type(query).__name__!r} which has no .session — Core "
            "Select statements are not supported.",
        )

    # Order releases by date. A "Playground"/working release orders by
    # its date like any other (an undated one ranks as the latest), so no
    # code parsing and no special-casing is needed; an unknown release_id
    # raises.
    target_sort_order = resolve_sort_order(session, release_id)
    sort_orders = load_release_sort_orders(session)
    start_ids = release_ids_for_sort_order(sort_orders, le=target_sort_order)
    end_ids = release_ids_for_sort_order(sort_orders, gt=target_sort_order)
    return query.filter(
        and_(
            start_col.in_(start_ids),
            or_(end_col.is_(None), end_col.in_(end_ids)),
        )
    )


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
    sort_orders: Dict[int, int],
    ref_sort_order: Optional[int],
    item_start_col: Any,
    item_end_col: Any,
) -> Any:
    """Build a version-range join condition.

    Pattern (date-ordered):

        sort_order(item_start) <= ref_sort_order
        AND (item_end IS NULL OR ref_sort_order < sort_order(item_end))

    Args:
        sort_orders: Pre-loaded mapping from
            :func:`load_release_sort_orders`.
        ref_sort_order: Reference release's pre-resolved sort order.
            ``None`` (an unknown/absent release) collapses to a condition
            that never matches; an undated release is not ``None`` (it
            ranks as the latest).
        item_start_col: Item's start-release ID column.
        item_end_col: Item's end-release ID column.

    Returns:
        SQLAlchemy boolean expression.
    """
    if ref_sort_order is None:
        return and_(item_start_col.is_(None), item_start_col.isnot(None))

    start_ids = release_ids_for_sort_order(sort_orders, le=ref_sort_order)
    end_ids = release_ids_for_sort_order(sort_orders, gt=ref_sort_order)
    return and_(
        item_start_col.in_(start_ids),
        or_(item_end_col.is_(None), item_end_col.in_(end_ids)),
    )
