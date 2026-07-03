"""Compute release sort order from ``Release.date`` at query time.

DPM ``ReleaseID`` values are no longer monotonic (4.2.1 has
``ReleaseID = 1010000003`` while older releases are still 1..5), so
release-range comparisons cannot rely on numeric ID ordering. They order
by ``Release.date`` instead: EBA publishes releases chronologically in
lineage order, and the date is present regardless of the ``code`` format,
so date ordering handles every code — the classic ``MAJOR.MINOR[.PATCH]``
form, EBA's four-segment codes (e.g. ``4.2.1.3``) and non-versioned
working releases like ``"Playground"`` — uniformly, without parsing the
code. Release dates are unique, so no tiebreak is needed.

The order key is the date's proleptic-Gregorian ordinal, computed in
Python at query time and held as a plain ``int`` — there is no persisted
SQL column; only its ordering is ever used.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def compute_sort_order(release_date: Optional[date]) -> Optional[int]:
    """Return a sortable integer for a release's publication date.

    Ordering is purely chronological: an earlier ``Release.date`` sorts
    before a later one. Dates are unique per release, so the ordinal is a
    total order and needs no tiebreak.

    Args:
        release_date: The release's ``Release.date``. ``None`` returns
            ``None`` so callers can skip an unorderable row; in practice
            every release carries a date.

    Returns:
        The date's ordinal (days since 0001-01-01), or ``None`` when
        ``release_date`` is missing.
    """
    if release_date is None:
        return None
    return release_date.toordinal()


def load_release_sort_orders(
    session: "Session",
) -> Dict[int, Optional[int]]:
    """Return ``{release_id: sort_order}`` derived from ``Release.date``.

    Rows with no date map to ``None`` so callers can skip them; every
    release is expected to carry a date in practice.
    """
    from dpmcore.orm.infrastructure import Release

    rows = session.query(Release.release_id, Release.date).all()
    return {rid: compute_sort_order(d) for rid, d in rows}


def resolve_sort_order(
    session: "Session", release_id: int, *, role: str = "release"
) -> int:
    """Return the date-based sort order for ``release_id`` or raise.

    Args:
        session: Open SQLAlchemy session.
        release_id: Numeric FK of the release whose sort order to
            resolve.
        role: Short label used in the error message to identify the
            release's role (``"window start release"`` etc.) so callers
            don't have to wrap the call in their own try/except just to
            customise wording.

    Raises:
        ValueError: If no Release row matches ``release_id`` or that
            release has no ``date``.
    """
    from dpmcore.orm.infrastructure import Release

    row = (
        session.query(Release.date)
        .filter(Release.release_id == release_id)
        .first()
    )
    if row is None:
        raise ValueError(
            f"{role} {release_id} has no sort_order — "
            "no Release row matches that ID."
        )
    sort_order = compute_sort_order(row[0])
    if sort_order is None:
        raise ValueError(
            f"{role} {release_id} has no sort_order — the release has no date."
        )
    return sort_order


def release_ids_for_sort_order(
    sort_orders: Dict[int, Optional[int]],
    *,
    le: Optional[int] = None,
    lt: Optional[int] = None,
    ge: Optional[int] = None,
    gt: Optional[int] = None,
) -> List[int]:
    """Filter ``{release_id: sort_order}`` by inequality predicates.

    Releases whose ``sort_order`` is ``None`` (no date, or an orphan FK
    absent from the mapping) are always excluded — they cannot satisfy a
    comparison either way.

    Args:
        sort_orders: Mapping from :func:`load_release_sort_orders`.
        le: Optional ``sort_order <= le`` bound.
        lt: Optional ``sort_order < lt`` bound.
        ge: Optional ``sort_order >= ge`` bound.
        gt: Optional ``sort_order > gt`` bound. All bounds are
            combined with logical AND.

    Returns:
        Sorted list of matching release IDs (ascending by
        ``sort_order``).
    """
    matches: List[tuple[int, int]] = []
    for rid, so in sort_orders.items():
        if so is None:
            continue
        if le is not None and not so <= le:
            continue
        if lt is not None and not so < lt:
            continue
        if ge is not None and not so >= ge:
            continue
        if gt is not None and not so > gt:
            continue
        matches.append((rid, so))
    matches.sort(key=lambda pair: pair[1])
    return [rid for rid, _ in matches]
