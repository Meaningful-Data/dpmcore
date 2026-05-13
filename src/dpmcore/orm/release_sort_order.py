"""Compute release sort order from ``Release.code`` at query time.

DPM ``ReleaseID`` values are no longer monotonic (4.2.1 has
``ReleaseID = 1010000003`` while older releases are still 1..5), so
release-range comparisons cannot rely on numeric ID ordering. Instead
we parse ``Release.code`` as a semver-style version tuple and pack it
into a single sortable integer. Backports — e.g. a hypothetical
``4.0.1`` published after ``4.2.1`` — still slot correctly into the
``4.0`` lineage because comparison runs against the parsed semver, not
the FK ID.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Three 6-digit slots per version segment → can hold 999999.999999.999999.
# Requires BIGINT (64-bit) — the ORM column uses BigInteger for PostgreSQL/
# SQL Server compatibility. SQLite INTEGER is always 64-bit so it was silent.
_SEGMENT_BITS = 1_000_000


def parse_version(code: Optional[str]) -> Optional[tuple[int, int, int]]:
    """Parse a release code into a ``(major, minor, patch)`` tuple.

    Args:
        code: Release code such as ``"4.2"`` or ``"4.2.1"``. ``None``
            and unparseable codes return ``None`` so the caller can
            decide whether to exclude or fall back.

    Returns:
        A 3-tuple of integers, or ``None`` when ``code`` is missing or
        cannot be parsed as ``MAJOR.MINOR[.PATCH]``.
    """
    if not code:
        return None
    parts = code.split(".")
    if not (1 <= len(parts) <= 3):
        return None
    try:
        ints = [int(p) for p in parts]
    except ValueError:
        return None
    while len(ints) < 3:
        ints.append(0)
    if any(p < 0 or p >= _SEGMENT_BITS for p in ints):
        return None
    return (ints[0], ints[1], ints[2])


def compute_sort_order(code: Optional[str]) -> Optional[int]:
    """Pack a release code into a single sortable integer.

    ``"4.2.1"`` packs to ``4_000002_000001``. The packing is monotone:
    if ``parse_version(a) < parse_version(b)`` then
    ``compute_sort_order(a) < compute_sort_order(b)``.

    Returns ``None`` when the code is missing or unparseable so callers
    can decide whether to skip or fail for that release.
    """
    parsed = parse_version(code)
    if parsed is None:
        return None
    major, minor, patch = parsed
    return (
        major * _SEGMENT_BITS * _SEGMENT_BITS + minor * _SEGMENT_BITS + patch
    )


def load_release_sort_orders(
    session: "Session",
) -> Dict[int, Optional[int]]:
    """Return ``{release_id: sort_order}`` parsed from ``Release.code``.

    Rows whose code is unparseable map to ``None`` so callers can fail
    loudly when one of them is named as a bound.
    """
    from dpmcore.orm.infrastructure import Release

    rows = session.query(Release.release_id, Release.code).all()
    return {rid: compute_sort_order(code) for rid, code in rows}


def resolve_sort_order(
    session: "Session", release_id: int, *, role: str = "release"
) -> int:
    """Return the parsed sort order for ``release_id`` or raise.

    Args:
        session: Open SQLAlchemy session.
        release_id: Numeric FK of the release whose sort order to
            resolve.
        role: Short label used in the error message to identify the
            release's role (``"window start release"`` etc.) so callers
            don't have to wrap the call in their own try/except just to
            customise wording.

    Raises:
        ValueError: If no Release row matches ``release_id`` or its
            code cannot be parsed as ``MAJOR.MINOR[.PATCH]``.
    """
    from dpmcore.orm.infrastructure import Release

    row = (
        session.query(Release.code)
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
            f"{role} {release_id} has no sort_order — its "
            "code could not be parsed as MAJOR.MINOR[.PATCH]."
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

    Releases whose ``sort_order`` is ``None`` (unparseable code) are
    always excluded — they cannot satisfy a comparison either way.

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
