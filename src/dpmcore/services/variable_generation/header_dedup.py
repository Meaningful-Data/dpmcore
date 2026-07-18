"""Header-version deduplication (SQL ``#SameHeaderVersions`` stage).

Detects header versions that are byte-identical to their immediate
predecessor (code, label, context, property, subcategory) on
non-abstract, non-key headers of table versions created in the
current release, and applies the SQL's correction *virtually*: the
``TableVersionHeader`` rows are repointed to the old HeaderVID, the
redundant new HeaderVersion disappears and the old one is reopened.
Later stages (and the validation gate) therefore see the old
HeaderVID, exactly as after the SQL's UPDATE/DELETE trio — but the
database is never touched.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional, Set, Tuple

from dpmcore.services.model_validation.release_context import (
    ReleaseContext,
)
from dpmcore.services.model_validation.snapshot import (
    _STORES,
    HeaderVersionRow,
    ModelSnapshot,
)
from dpmcore.services.variable_generation.types import HeaderDedup


def _clone_snapshot(
    snapshot: ModelSnapshot, **overrides: List[object]
) -> ModelSnapshot:
    """Rebuild a snapshot with some primary stores replaced."""
    stores = {
        name: overrides.get(name, getattr(snapshot, name))
        for name in _STORES
    }
    return ModelSnapshot.from_rows(**stores)


def _identical(hv: HeaderVersionRow, prev: HeaderVersionRow) -> bool:
    """True when the two versions carry identical modelling fields.

    Mirrors the SQL's ``ISNULL(x, sentinel) = ISNULL(y, sentinel)``
    comparisons: two NULLs compare equal.
    """
    return (
        hv.code == prev.code
        and hv.label == prev.label
        and hv.context_id == prev.context_id
        and hv.property_id == prev.property_id
        and hv.subcategory_vid == prev.subcategory_vid
    )


def _dedup_candidates(
    snapshot: ModelSnapshot, release: ReleaseContext
) -> Set[Tuple[int, int, int, int]]:
    """Distinct (table_vid, header_id, new_hvid, old_hvid) tuples."""
    tables_in_modules = {
        mvc.table_vid
        for mvc in snapshot.module_version_compositions
        if mvc.table_vid is not None
    }
    found: Set[Tuple[int, int, int, int]] = set()
    for tv in snapshot.table_versions:
        table = snapshot.tables_by_id.get(tv.table_id or -1)
        if (
            table is None
            or table.is_abstract is not False
            or tv.end_release_id is not None
            or not release.is_current(tv.start_release_id)
            or tv.table_vid not in tables_in_modules
        ):
            continue
        for tvh in snapshot.tvh_by_table_vid().get(tv.table_vid, []):
            found.update(
                (tv.table_vid, tvh.header_id, new_vid, old_vid)
                for new_vid, old_vid in _header_pairs(
                    snapshot, tvh.header_id, tv.table_id
                )
            )
    return found


def _header_pairs(
    snapshot: ModelSnapshot, header_id: int, table_id: Optional[int]
) -> List[Tuple[int, int]]:
    """(new_hvid, old_hvid) identical pairs for one non-key header.

    Mirrors the SQL joins: the header must belong to the table
    (``h.TableID = t.TableID``), must not be a key header
    (``h.isKey = 0``, which excludes NULL flags), and the
    ``TableVersionHeader`` row must not be abstract (checked by the
    caller, per ``tvh.isAbstract = 0``).
    """
    header = snapshot.headers_by_id.get(header_id)
    if (
        header is None
        or header.is_key is not False
        or header.table_id is None
        or header.table_id != table_id
    ):
        return []
    versions = snapshot.header_versions_by_header().get(header_id, [])
    pairs: List[Tuple[int, int]] = []
    for hv in versions:
        if hv.end_release_id is not None or hv.start_release_id is None:
            continue
        pairs.extend(
            (hv.header_vid, prev.header_vid)
            for prev in versions
            if prev.end_release_id == hv.start_release_id
            and _identical(hv, prev)
        )
    return pairs


def detect_and_apply(
    snapshot: ModelSnapshot, release: ReleaseContext
) -> Tuple[ModelSnapshot, Tuple[HeaderDedup, ...]]:
    """Detect duplicated header versions and apply them virtually.

    Args:
        snapshot: The loaded model snapshot.
        release: Release semantics of the run.

    Returns:
        The (possibly rebuilt) snapshot in which later stages see the
        old HeaderVIDs, plus the recorded deduplications.

    Note:
        The SQL's ``tvh.isAbstract = 0`` filter is applied on the
        repointed rows: only non-abstract TableVersionHeader rows are
        considered when collecting candidates, mirroring the join.
    """
    candidates = {
        c
        for c in _dedup_candidates(snapshot, release)
        if _tvh_is_concrete(snapshot, c[0], c[1])
    }
    if not candidates:
        return snapshot, ()

    by_pair: Dict[Tuple[int, int], Set[int]] = {}
    new_vids = {c[2] for c in candidates}
    old_vids = {c[3] for c in candidates}
    repoint: Dict[Tuple[int, int, int], int] = {}
    for table_vid, header_id, new_vid, old_vid in candidates:
        by_pair.setdefault((old_vid, new_vid), set()).add(table_vid)
        repoint[(table_vid, header_id, new_vid)] = old_vid

    tvhs = [
        replace(tvh, header_vid=repoint[key])
        if (
            tvh.header_vid is not None
            and (key := (tvh.table_vid, tvh.header_id, tvh.header_vid))
            in repoint
        )
        else tvh
        for tvh in snapshot.table_version_headers
    ]
    hvs = [
        replace(hv, end_release_id=None)
        if hv.header_vid in old_vids
        else hv
        for hv in snapshot.header_versions
        if hv.header_vid not in new_vids
    ]
    dedups = tuple(
        HeaderDedup(
            old_header_vid=old_vid,
            new_header_vid=new_vid,
            table_vids=tuple(sorted(table_vids)),
        )
        for (old_vid, new_vid), table_vids in sorted(by_pair.items())
    )
    rebuilt = _clone_snapshot(
        snapshot,
        table_version_headers=list(tvhs),
        header_versions=list(hvs),
    )
    return rebuilt, dedups


def _tvh_is_concrete(
    snapshot: ModelSnapshot, table_vid: int, header_id: int
) -> bool:
    """SQL ``tvh.isAbstract = 0`` for the (table version, header)."""
    return any(
        tvh.header_id == header_id and tvh.is_abstract is False
        for tvh in snapshot.tvh_by_table_vid().get(table_vid, [])
    )
