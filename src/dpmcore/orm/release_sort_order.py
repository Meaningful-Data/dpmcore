"""Auto-populate ``Release.sort_order`` from ``Release.code``.

DPM ``ReleaseID`` values are no longer monotonic (4.2.1 has
``ReleaseID = 1010000003`` while older releases are still 1..5), so
release-range comparisons cannot rely on numeric ID ordering. Instead
we parse ``Release.code`` as a semver-style version tuple and pack it
into a single ``SortOrder`` integer, which is the column compared at
every range-filter site.

Backports — e.g. a hypothetical ``4.0.1`` published *after* ``4.2.1``
— still slot correctly into the ``4.0`` lineage when ordered by
``SortOrder``, which is the semantic that EBA's range expressions
("module is valid from release X to Y") actually intend.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import event, inspect

from dpmcore.orm.infrastructure import Release

# Three 6-digit slots per version segment → can hold 999999.999999.999999.
# Plenty of headroom for any realistic DPM versioning while staying within
# a SQLite ``INTEGER`` (64-bit signed, max ~9.2e18).
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

    Returns ``None`` when the code is missing or unparseable so the
    DB row can still be inserted; range queries simply exclude such
    rows from comparison.
    """
    parsed = parse_version(code)
    if parsed is None:
        return None
    major, minor, patch = parsed
    return (
        major * _SEGMENT_BITS * _SEGMENT_BITS + minor * _SEGMENT_BITS + patch
    )


@event.listens_for(Release, "before_insert")
def _release_before_insert(
    mapper: Any, connection: Any, target: Release
) -> None:
    """Auto-populate ``sort_order`` on insert when not explicitly set."""
    if target.sort_order is None:
        target.sort_order = compute_sort_order(target.code)


@event.listens_for(Release, "before_update")
def _release_before_update(
    mapper: Any, connection: Any, target: Release
) -> None:
    """Recompute ``sort_order`` only when ``code`` is dirty.

    Skipping the recompute on unrelated updates lets the migration
    backfill (which sets ``sort_order`` directly before commit) and
    any future manual override survive.
    """
    code_history = inspect(target).attrs.code.history
    if code_history.has_changes():
        target.sort_order = compute_sort_order(target.code)
