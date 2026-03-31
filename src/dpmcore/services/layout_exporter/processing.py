"""Processing logic for the table layout exporter.

Pure functions that transform raw ORM data into TableLayout dataclasses.
No database access — all data arrives as arguments.
"""

from __future__ import annotations

from typing import Any, Optional

from dpmcore.services.layout_exporter.models import (
    CellData,
    DimensionMember,
    LayoutHeader,
    TableLayout,
)


def build_layout_headers(
    raw_headers: list[tuple[Any, ...]],
    context_cats: dict[int, list[DimensionMember]],
    property_cats: dict[int, DimensionMember],
) -> tuple[list[LayoutHeader], list[LayoutHeader], list[LayoutHeader]]:
    """Convert raw (TableVersionHeader, Header, HeaderVersion) tuples
    into sorted LayoutHeader lists for each axis.

    Returns (columns, rows, sheets).
    """
    by_direction: dict[str, list[LayoutHeader]] = {"x": [], "y": [], "z": []}

    for tvh, header, hv in raw_headers:
        direction = header.direction.lower()

        # Collect categorisations from context + property
        cats: list[DimensionMember] = []
        if hv.context_id and hv.context_id in context_cats:
            cats.extend(context_cats[hv.context_id])
        if hv.property_id and hv.property_id in property_cats:
            cats.append(property_cats[hv.property_id])

        lh = LayoutHeader(
            header_id=tvh.header_id,
            header_vid=tvh.header_vid or hv.header_vid,
            code=hv.code or "",
            label=hv.label or "",
            direction=direction,
            order=tvh.order or 0,
            is_abstract=bool(tvh.is_abstract),
            is_key=bool(header.is_key),
            parent_header_id=tvh.parent_header_id,
            parent_first=bool(tvh.parent_first) if tvh.parent_first is not None else True,
            categorisations=cats,
        )
        by_direction.setdefault(direction, []).append(lh)

    columns = sort_headers(by_direction.get("x", []))
    rows = sort_headers(by_direction.get("y", []))
    sheets = sort_headers(by_direction.get("z", []))

    return columns, rows, sheets


def sort_headers(headers: list[LayoutHeader]) -> list[LayoutHeader]:
    """Sort headers using the TotalOrder algorithm.

    Builds a recursive sort key that respects parent-child hierarchy
    and the parent_first flag.
    """
    if not headers:
        return []

    by_id: dict[int, LayoutHeader] = {h.header_id: h for h in headers}

    # Find max order width for zero-padding
    max_order = max((h.order for h in headers), default=0)
    pad_width = max(len(str(max_order)), 4)

    # Compute sort keys recursively.
    # The VBA algorithm appends a trailing separator:
    #   "." if the header appears before its children (parent_first=True)
    #   ":" if the header appears after its children (parent_first=False)
    # ":" > "." in ASCII, so a parent-after-children sorts after its descendants.
    # When building a child's key, parent's ":" markers are replaced with "."
    # so they don't affect the child's position.
    cache: dict[int, str] = {}

    def compute_sort_key(h: LayoutHeader) -> str:
        if h.header_id in cache:
            return cache[h.header_id]

        own_order = str(h.order).zfill(pad_width)

        if h.parent_header_id is None or h.parent_header_id not in by_id:
            prefix = ""
        else:
            parent = by_id[h.parent_header_id]
            parent_key = compute_sort_key(parent)
            # Replace ":" with "." so parent's after-children marker
            # doesn't push children after it
            prefix = parent_key.replace(":", ".")

        trailing = ":" if not h.parent_first else "."
        key = prefix + own_order + trailing

        cache[h.header_id] = key
        return key

    for h in headers:
        h.sort_key = compute_sort_key(h)

    # Compute depth (count ancestors)
    depth_cache: dict[int, int] = {}

    def compute_depth(h: LayoutHeader) -> int:
        if h.header_id in depth_cache:
            return depth_cache[h.header_id]
        if h.parent_header_id is None or h.parent_header_id not in by_id:
            d = 0
        else:
            d = 1 + compute_depth(by_id[h.parent_header_id])
        depth_cache[h.header_id] = d
        return d

    for h in headers:
        h.depth = compute_depth(h)

    headers.sort(key=lambda h: h.sort_key)
    return headers


def build_cells(
    raw_cells: list[tuple[Any, ...]],
    row_ids: set[int],
    col_ids: set[int],
    sheet_ids: set[int],
    dp_cats: dict[int, list[DimensionMember]],
) -> dict[tuple[int, int, Optional[int]], CellData]:
    """Build the cell dictionary from raw (TableVersionCell, Cell) tuples.

    Keys are (row_header_id, col_header_id, sheet_header_id).
    Only includes cells whose headers are in the provided sets.
    """
    cells: dict[tuple[int, int, Optional[int]], CellData] = {}

    for tvc, cell in raw_cells:
        row_id = cell.row_id
        col_id = cell.column_id
        sheet_id = cell.sheet_id

        if row_id not in row_ids or col_id not in col_ids:
            continue
        if sheet_id and sheet_id not in sheet_ids:
            continue

        vvid = tvc.variable_vid
        cd = CellData(
            row_header_id=row_id,
            col_header_id=col_id,
            sheet_header_id=sheet_id,
            variable_vid=vvid,
            is_excluded=bool(tvc.is_excluded),
            is_void=bool(tvc.is_void) if tvc.is_void is not None else False,
            sign=tvc.sign or "",
            dp_categorisations=dp_cats.get(vvid, []) if vvid else [],
        )
        cells[(row_id, col_id, sheet_id)] = cd

    return cells


def build_table_layout(
    tv: Any,
    columns: list[LayoutHeader],
    rows: list[LayoutHeader],
    sheets: list[LayoutHeader],
    cells: dict[tuple[int, int, Optional[int]], CellData],
) -> TableLayout:
    """Assemble the final TableLayout."""
    max_col_depth = max((h.depth for h in columns), default=0)
    max_row_depth = max((h.depth for h in rows), default=0)

    # Collect all distinct dimension property_ids used in annotations
    seen: dict[int, str] = {}
    for h in columns + rows + sheets:
        for dm in h.categorisations:
            if dm.property_id not in seen:
                seen[dm.property_id] = dm.dimension_label
    dimension_ids = sorted(seen.items())

    return TableLayout(
        table_vid=tv.table_vid,
        table_code=tv.code or "",
        table_name=tv.name or "",
        rows=rows,
        columns=columns,
        sheets=sheets,
        cells=cells,
        max_col_depth=max_col_depth,
        max_row_depth=max_row_depth,
        dimension_ids=dimension_ids,
    )
