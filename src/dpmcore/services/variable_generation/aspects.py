"""New-coordinate computation for the cell-modelling working set.

Port of the SQL ``#temp_property`` / ``#temp_context`` /
``NewKeySignature`` stages: for every cell of a table version starting
in the current release, compute the new main property (the *maximum*
property id across the cell's active column/row/sheet header versions
and the table version — SQL semantics preserved exactly), assemble the
per-cell context signature, resolve it against existing contexts
(proposing new ones for unseen signatures) and attach the table's
compound key. Cells of unchanged table versions keep their old
coordinates (set by the working-set builder).

Notes on faithful readings:
    * The SQL filters ``hvX.EndReleaseID IS NULL`` in the WHERE clause
      of a LEFT JOIN: an axis header that has versions but none active
      removes *all* rows for the cell, so both the property and the
      context stay NULL. An axis without a header — or a header
      without versions — simply contributes nothing.
    * Context signatures aggregate ``property_item`` parts in
      *lexicographic* order (the SQL orders by the concatenated
      string) and keep duplicates arising from distinct contexts.
    * Context resolution trims signatures on both sides; when several
      contexts match, the plan picks a proposed context first (the
      SQL's freshly inserted rows carry the largest ids), then the
      existing context with the highest id.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from dpmcore.services.model_validation.release_context import (
    ReleaseContext,
)
from dpmcore.services.model_validation.snapshot import (
    CellRow,
    ContextCompositionRow,
    HeaderVersionRow,
    ModelSnapshot,
    TableVersionRow,
)
from dpmcore.services.variable_generation.state import (
    CellRecord,
    GenerationState,
)
from dpmcore.services.variable_generation.types import (
    OptionalRef,
    ProposedContext,
    Ref,
)


def _axis_versions(
    snapshot: ModelSnapshot, header_id: Optional[int]
) -> Optional[List[HeaderVersionRow]]:
    """Active versions of one axis header.

    Returns None when the axis *blocks* the cell (the header has
    versions but none is active); an empty list when the axis simply
    contributes nothing.
    """
    if header_id is None:
        return []
    versions = snapshot.header_versions_by_header().get(header_id, [])
    active = [hv for hv in versions if hv.end_release_id is None]
    if versions and not active:
        return None
    return active


def _cell_axis_versions(
    snapshot: ModelSnapshot, cell: CellRow
) -> Optional[List[HeaderVersionRow]]:
    """Active header versions of all three axes, or None if blocked."""
    collected: List[HeaderVersionRow] = []
    for header_id in (cell.column_id, cell.row_id, cell.sheet_id):
        versions = _axis_versions(snapshot, header_id)
        if versions is None:
            return None
        collected.extend(versions)
    return collected


def _new_property(
    snapshot: ModelSnapshot, tv: TableVersionRow, cell: CellRow
) -> Optional[int]:
    """Max property across the cell's headers and the table version.

    Only property ids present in the ``Property`` store count (the
    SQL subquery selects from ``Property``).
    """
    versions = _cell_axis_versions(snapshot, cell)
    if versions is None:
        return None
    candidates = {hv.property_id for hv in versions}
    candidates.add(tv.property_id)
    valid = [
        p
        for p in candidates
        if p is not None and p in snapshot.properties_by_id
    ]
    return max(valid) if valid else None


def _context_rows(
    snapshot: ModelSnapshot, tv: TableVersionRow, cell: CellRow
) -> List[ContextCompositionRow]:
    """``#temp_context`` rows for one cell (distinct compositions)."""
    versions = _cell_axis_versions(snapshot, cell)
    if versions is None:
        return []
    context_ids = {
        hv.context_id
        for hv in versions
        if hv.context_id is not None
    }
    if tv.context_id is not None:
        context_ids.add(tv.context_id)
    index = snapshot.context_compositions_by_context()
    return [
        cc for cid in sorted(context_ids) for cc in index.get(cid, [])
    ]


def _signature(rows: List[ContextCompositionRow]) -> str:
    """SQL context signature: sorted ``prop_item`` parts + ``'#'``."""
    parts = sorted(
        f"{cc.property_id}_{cc.item_id}"
        for cc in rows
        if cc.item_id is not None
    )
    return "#".join(parts) + "#" if parts else ""


def compute_new_coordinates(
    snapshot: ModelSnapshot,
    release: ReleaseContext,
    records: List[CellRecord],
    state: GenerationState,
) -> None:
    """Fill the ``new_*`` coordinates and flags of the working set.

    Args:
        snapshot: Model snapshot (after header dedup).
        release: Release semantics.
        records: The cell-modelling working set; mutated in place.
        state: Accumulates proposed contexts; provides table keys.
    """
    per_cell: Dict[Tuple[int, int], Tuple[Optional[int], str]] = {}
    sig_rows: Dict[str, List[ContextCompositionRow]] = {}
    for record in records:
        if not release.is_current(record.tv_start):
            continue
        key = (record.table_vid, record.cell_id)
        if key in per_cell:
            continue
        per_cell[key] = self_coords = _cell_coordinates(
            snapshot, record
        )
        signature = self_coords[1]
        if signature and signature not in sig_rows:
            tv = snapshot.table_versions_by_vid[record.table_vid]
            cell = snapshot.cells_by_id[record.cell_id]
            sig_rows[signature] = _context_rows(snapshot, tv, cell)

    resolution = _resolve_contexts(snapshot, sig_rows, state)
    for record in records:
        if not release.is_current(record.tv_start):
            continue
        prop, signature = per_cell[(record.table_vid, record.cell_id)]
        record.new_property_id = prop
        record.new_context_id = (
            resolution.get(signature.strip()) if signature else None
        )
        record.new_key_id = state.key_by_table_vid.get(
            record.table_vid
        )
    _set_flags(snapshot, records)


def _cell_coordinates(
    snapshot: ModelSnapshot, record: CellRecord
) -> Tuple[Optional[int], str]:
    """(new property, context signature) for one (tv, cell)."""
    tv = snapshot.table_versions_by_vid.get(record.table_vid)
    cell = snapshot.cells_by_id.get(record.cell_id)
    if tv is None or cell is None:
        return None, ""
    prop = _new_property(snapshot, tv, cell)
    signature = _signature(_context_rows(snapshot, tv, cell))
    return prop, signature


def _resolve_contexts(
    snapshot: ModelSnapshot,
    sig_rows: Dict[str, List[ContextCompositionRow]],
    state: GenerationState,
) -> Dict[str, Ref]:
    """Trimmed signature -> context id/temp id, proposing new ones."""
    existing_raw = {
        cx.signature
        for cx in snapshot.contexts
        if cx.signature is not None
    }
    resolution: Dict[str, Ref] = {}
    for cx in sorted(snapshot.contexts, key=lambda c: c.context_id):
        if cx.signature is not None:
            resolution[cx.signature.strip()] = cx.context_id
    for proposed in state.fi_contexts:
        resolution[proposed.signature.strip()] = proposed.temp_id

    # Contexts proposed by the filing-indicator stage were already
    # "inserted" by the time the SQL reaches this NOT IN check.
    proposed_raw = {p.signature for p in state.fi_contexts}
    unseen = sorted(
        sig
        for sig in sig_rows
        if sig not in existing_raw and sig not in proposed_raw
    )
    for signature in unseen:
        compositions: Set[Tuple[int, Ref]] = {
            (cc.property_id, cc.item_id)
            for cc in sig_rows[signature]
            if cc.item_id is not None
        }
        proposal = ProposedContext(
            temp_id=state.ids.next("ctx"),
            signature=signature,
            compositions=tuple(sorted(compositions)),
        )
        state.cell_contexts.append(proposal)
        resolution[signature.strip()] = proposal.temp_id
    return resolution


def _set_flags(
    snapshot: ModelSnapshot, records: List[CellRecord]
) -> None:
    """SQL ``isNewPropertyDataType`` and ``isNewKey`` flags."""
    for record in records:
        record.is_new_property_datatype = record.is_new_cell or (
            _datatype_changed(
                snapshot,
                record.old_property_id,
                record.new_property_id,
            )
        )
        record.is_new_key = _key_changed(
            record.old_key_id, record.new_key_id
        )


def _datatype_changed(
    snapshot: ModelSnapshot,
    old_property: Optional[int],
    new_property: Optional[int],
) -> bool:
    """True only when both datatypes are known and differ.

    Mirrors ``WHERE NOT (dt_old = dt_new)``: a NULL on either side
    makes the comparison UNKNOWN, so the flag stays unset.
    """
    old_dt = _datatype_of(snapshot, old_property)
    new_dt = _datatype_of(snapshot, new_property)
    return old_dt is not None and new_dt is not None and old_dt != new_dt


def _datatype_of(
    snapshot: ModelSnapshot, property_id: Optional[int]
) -> Optional[int]:
    """DataTypeID of a property, None when unknown."""
    if property_id is None:
        return None
    prop = snapshot.properties_by_id.get(property_id)
    return prop.data_type_id if prop is not None else None


def _key_changed(old: OptionalRef, new: OptionalRef) -> bool:
    """SQL ``isNewKey``: nullability flip or differing values."""
    if (old is None) != (new is None):
        return True
    return old is not None and new is not None and old != new
