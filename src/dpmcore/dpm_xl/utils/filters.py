"""Release and date filtering utilities for DPM queries.

Provides composable SQLAlchemy filter conditions for
release-based versioning and date-range queries.

Release-range comparisons use ``Release.sort_order`` rather than
``Release.release_id`` because EBA's post-4.2.1 ID scheme is no longer
monotonic (4.2.1 has ``ReleaseID = 1010000003``). ``sort_order`` is
populated from the parsed semver ``code``, so a hypothetical backport
``4.0.1`` is correctly placed inside the ``4.0`` lineage even when
published chronologically after ``4.2.1``.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Date, and_, cast, or_, select
from sqlalchemy.orm import aliased

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


def sort_order_subquery(release_id_col: Any) -> Any:
    """Return a scalar subquery for ``Release.sort_order`` of *col*.

    Useful when a JOIN cannot be added to the query (typically inside a
    JOIN ``ON`` clause that already correlates against an aliased
    ``Release`` row). Prefer joining an aliased ``Release`` and
    referencing its ``sort_order`` directly when the surrounding query
    can be mutated — see :func:`filter_by_release` for an example.
    """
    # Local import keeps this util's dependency direction clean.
    from dpmcore.orm.infrastructure import Release

    return (
        select(Release.sort_order)
        .where(Release.release_id == release_id_col)
        .scalar_subquery()
    )


def filter_by_release(
    query: Any,
    start_col: Any,
    end_col: Any,
    release_id: Optional[int] = None,
    active_only_fallback: bool = False,
) -> Any:
    """Filter a query by DPM release versioning logic.

    Logic (semver-aware):
        If release_id provided:
            start.sort_order <= target.sort_order AND
            (end IS NULL OR end.sort_order > target.sort_order)
        If release_id is None:
            * ``active_only_fallback=True`` → ``end_col IS NULL`` only
              (currently-active rows). Useful for callers that want a
              deterministic default when no release is supplied.
            * Otherwise → return query unmodified.

    Implementation note: the comparison joins two aliased ``Release``
    rows (one for ``start_col``, one for ``end_col``) so the database
    looks up ``sort_order`` once per row rather than re-running a
    correlated subquery for every comparison. The end-side join is a
    LEFT OUTER JOIN to preserve rows where ``end_col IS NULL``
    (currently-active records).

    Args:
        query: SQLAlchemy ``Query`` — must be a session-bound ``Query``
            (i.e. produced by ``Session.query(...)``). Core ``Select``
            statements are not supported because the helper needs the
            session to resolve the target release's sort order before
            adding the filter joins.
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
            ``Release`` row, or that release has no parseable
            ``sort_order``.
    """
    if release_id is None:
        if active_only_fallback:
            return filter_active_only(query, end_col)
        return query

    from dpmcore.orm.infrastructure import Release

    session = getattr(query, "session", None)
    if session is None:
        raise TypeError(
            "filter_by_release(query=...) expects a session-bound "
            "SQLAlchemy Query (Session.query(...)). Got "
            f"{type(query).__name__!r} which has no .session — Core "
            "Select statements are not supported.",
        )
    target_sort_order = (
        session.query(Release.sort_order)
        .filter(Release.release_id == release_id)
        .scalar()
    )
    if target_sort_order is None:
        raise ValueError(
            f"Release {release_id} has no sort_order — its code "
            "could not be parsed as MAJOR.MINOR[.PATCH].",
        )

    start_release = aliased(Release)
    end_release = aliased(Release)
    return (
        query.join(start_release, start_release.release_id == start_col)
        .outerjoin(end_release, end_release.release_id == end_col)
        .filter(
            and_(
                start_release.sort_order <= target_sort_order,
                or_(
                    end_col.is_(None),
                    end_release.sort_order > target_sort_order,
                ),
            )
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
    ref_sort_order: Optional[int],
    item_start_col: Any,
    item_end_col: Any,
) -> Any:
    """Build a version-range join condition.

    Pattern (semver-aware):

        item_start.sort_order <= ref_sort_order
        AND (item_end IS NULL OR ref_sort_order < item_end.sort_order)

    The reference side is passed as a Python ``int`` (the caller has
    already resolved its ``Release.sort_order``) so only one correlated
    subquery is emitted per item-side column instead of three.
    Comparison still runs against ``Release.sort_order`` so backports
    like a future ``4.0.1`` published after ``4.2.1`` slot into the
    correct lineage.

    Args:
        ref_sort_order: Reference release's pre-resolved
            ``Release.sort_order`` value. ``None`` (unparseable code)
            makes every comparison evaluate to NULL — i.e. the join
            condition never matches.
        item_start_col: Item's start-release ID column.
        item_end_col: Item's end-release ID column.

    Returns:
        SQLAlchemy boolean expression.
    """
    return and_(
        sort_order_subquery(item_start_col) <= ref_sort_order,
        or_(
            sort_order_subquery(item_end_col) > ref_sort_order,
            item_end_col.is_(None),
        ),
    )
