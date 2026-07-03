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

A release with **no publication date** is an unpublished working release,
which represents the current in-progress state; it therefore sorts *after*
every dated release — i.e. it is the latest. This is expressed by mapping a
missing date to a sentinel ordinal greater than any real date's.

The order key is the date's proleptic-Gregorian ordinal, computed in
Python at query time and held as a plain ``int`` — there is no persisted
SQL column; only its ordering is ever used.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Sentinel sort order for a release with no publication date: it sorts
# after every real date (which cannot exceed ``date.max``), so an
# unpublished working release ranks as the latest.
_UNDATED_SORT_ORDER = date.max.toordinal() + 1


def compute_sort_order(release_date: Optional[date]) -> int:
    """Return a sortable integer for a release's publication date.

    Ordering is purely chronological: an earlier ``Release.date`` sorts
    before a later one. Dates are unique per release, so the ordinal is a
    total order and needs no tiebreak.

    Args:
        release_date: The release's ``Release.date``. ``None`` (an
            unpublished working release) sorts as the latest release.

    Returns:
        The date's ordinal (days since 0001-01-01), or the "latest"
        sentinel (:data:`_UNDATED_SORT_ORDER`) when ``release_date`` is
        missing.
    """
    if release_date is None:
        return _UNDATED_SORT_ORDER
    return release_date.toordinal()


def load_release_sort_orders(
    session: "Session",
) -> Dict[int, Optional[int]]:
    """Return ``{release_id: sort_order}`` derived from ``Release.date``.

    Every release maps to an ``int``: dated releases to their date's
    ordinal, and an undated (unpublished) release to the "latest"
    sentinel. Only a ``.get()`` miss on a release_id absent from the
    mapping (an orphan FK) yields ``None`` for a caller.
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

    An undated (unpublished) release is *not* an error — it resolves to
    the "latest" sentinel like any other release.

    Raises:
        ValueError: If no Release row matches ``release_id``.
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
    return compute_sort_order(row[0])


def release_ids_for_sort_order(
    sort_orders: Dict[int, Optional[int]],
    *,
    le: Optional[int] = None,
    lt: Optional[int] = None,
    ge: Optional[int] = None,
    gt: Optional[int] = None,
) -> List[int]:
    """Filter ``{release_id: sort_order}`` by inequality predicates.

    Releases whose ``sort_order`` is ``None`` (an orphan FK absent from
    the mapping) are always excluded — they cannot satisfy a comparison
    either way. Undated releases are *not* ``None``: they carry the
    "latest" sentinel and rank above every dated release.

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
