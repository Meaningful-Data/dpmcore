"""Excel workbook writer for table layouts.

Takes processed TableLayout dataclasses and renders them to an
openpyxl Workbook with formatting, merged headers, annotations,
comments, and outline groups.
"""

from __future__ import annotations

from typing import Optional

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from dpmcore.services.layout_exporter.models import (
    DimensionMember,
    ExportConfig,
    LayoutHeader,
    TableLayout,
)

# --- Style constants ---

_THIN = Side(style="thin")
_BORDER_ALL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_GREY_FILL = PatternFill(start_color="D8D8D8", end_color="D8D8D8", fill_type="solid")
_DARK_GREY_FILL = PatternFill(start_color="808080", end_color="808080", fill_type="solid")
_EXCLUDED_FILL = PatternFill(start_color="999999", end_color="999999", fill_type="solid")
_TITLE_FONT = Font(bold=True, size=11)
_HEADER_FONT = Font(bold=True, size=10)
_DATA_FONT = Font(size=9)
_ABSTRACT_FONT = Font(bold=True, size=10, color="FFFFFF")

# Dimension annotation colors (cycling palette)
_DIM_COLORS = [
    "0000CC", "CC0000", "006600", "990099", "CC6600",
    "006666", "660066", "336699", "993333", "339933",
    "666699", "996633", "339966", "993366", "669933",
]


class ExcelLayoutWriter:
    """Writes one or more TableLayouts to an openpyxl Workbook."""

    def __init__(
        self,
        layouts: list[TableLayout],
        config: Optional[ExportConfig] = None,
    ) -> None:
        self.layouts = layouts
        self.config = config or ExportConfig()
        self.wb = Workbook()
        # Remove default sheet
        if self.wb.sheetnames:
            del self.wb[self.wb.sheetnames[0]]

    def write(self) -> Workbook:
        """Write all table layouts and return the workbook."""
        # Sort layouts alphabetically by table code
        sorted_layouts = sorted(self.layouts, key=lambda l: l.table_code)

        for layout in sorted_layouts:
            self._write_table(layout)

        # Add index sheet at the beginning
        self._write_index(sorted_layouts)

        return self.wb

    def _write_index(self, sorted_layouts: list[TableLayout]) -> None:
        """Write an index sheet with hyperlinks to each table."""
        ws = self.wb.create_sheet(title="Index", index=0)

        # Title
        ws.cell(row=1, column=1, value="Table Index").font = Font(
            bold=True, size=14,
        )

        # Column headers
        for col, header in enumerate(
            ["#", "Table Code", "Table Name"], start=1,
        ):
            cell = ws.cell(row=3, column=col, value=header)
            cell.font = _HEADER_FONT
            cell.fill = _GREY_FILL
            cell.border = _BORDER_ALL

        # Table entries with hyperlinks
        for i, layout in enumerate(sorted_layouts):
            row = 4 + i
            ws.cell(row=row, column=1, value=i + 1).border = _BORDER_ALL

            sheet_name = layout.table_code[:31]
            code_cell = ws.cell(row=row, column=2, value=layout.table_code)
            code_cell.border = _BORDER_ALL
            code_cell.font = Font(color="0000CC", underline="single")
            code_cell.hyperlink = f"#{sheet_name}!A1"

            name_cell = ws.cell(row=row, column=3, value=layout.table_name)
            name_cell.border = _BORDER_ALL

        # Column widths
        ws.column_dimensions["A"].width = 6
        ws.column_dimensions["B"].width = 18
        ws.column_dimensions["C"].width = 80

    def _write_table(self, layout: TableLayout) -> None:
        """Write a single table layout to a worksheet."""
        # Truncate sheet name to 31 chars (Excel limit)
        sheet_name = layout.table_code[:31]
        ws = self.wb.create_sheet(title=sheet_name)

        cfg = self.config
        code_row_offset = 1 if cfg.show_code_row else 0
        code_col_offset = 1 if cfg.show_code_column else 0

        # Layout geometry
        # Row 1: title
        # Row 2: sheet header (if sheets exist)
        # Row 3: "Columns" label
        # Rows 4..4+max_col_depth: column header levels
        # Row 4+max_col_depth+1: column code row (if enabled)
        # Rows after: data rows

        sheet_header_rows = 1 if layout.sheets else 0
        col_header_start_row = 2 + sheet_header_rows
        col_label_rows = layout.max_col_depth + 1
        col_code_row = col_header_start_row + col_label_rows if cfg.show_code_row else 0
        data_start_row = col_header_start_row + col_label_rows + code_row_offset

        # Column geometry
        # Col A: "Rows" label (merged)
        # Col B: row labels
        # Col C: row codes (if enabled)
        # Cols after: data columns
        row_label_col = 2  # B
        row_code_col = 3 if cfg.show_code_column else 0
        data_start_col = 2 + code_col_offset + 1  # after labels + optional codes

        # --- Build column position map (skip abstract headers) ---
        col_positions: dict[int, int] = {}
        visible_col = 0
        for ch in layout.columns:
            if ch.is_abstract:
                col_positions[ch.header_id] = visible_col  # shares position
            else:
                visible_col += 1
                col_positions[ch.header_id] = visible_col

        num_visible_cols = visible_col

        # --- Title ---
        title_text = f"{layout.table_code} - {layout.table_name}"
        title_cell = ws.cell(row=1, column=1, value=title_text)
        title_cell.font = _TITLE_FONT
        title_cell.fill = _GREY_FILL
        title_cell.border = _BORDER_ALL
        # Merge title across all columns
        end_col = data_start_col + num_visible_cols - 1
        if end_col > 1:
            ws.merge_cells(
                start_row=1, start_column=1,
                end_row=1, end_column=max(end_col, 1),
            )

        # --- Sheet header (Z-axis) ---
        if layout.sheets:
            sheet_text = ", ".join(
                f"{s.code} {s.label}" for s in layout.sheets
            )
            if len(layout.sheets) == 1 and layout.sheets[0].code == "9999":
                sheet_text = f"Sheet per {layout.sheets[0].label}"

            sc = ws.cell(row=2, column=row_label_col, value=sheet_text)
            sc.font = _HEADER_FONT
            sc.fill = _GREY_FILL
            sc.border = _BORDER_ALL
            sc.alignment = Alignment(horizontal="center", vertical="center")

            if cfg.add_header_comments and layout.sheets:
                tooltip = _build_header_tooltip(layout.sheets)
                if tooltip:
                    sc.comment = Comment(tooltip, "dpmcore", width=400, height=150)

        # --- Column headers ---
        # "Columns" label
        ws.cell(
            row=col_header_start_row,
            column=data_start_col,
            value="Columns",
        ).font = _HEADER_FONT

        for ch in layout.columns:
            col_offset = col_positions[ch.header_id]
            if col_offset == 0:
                continue  # abstract at position 0 before any real column

            excel_col = data_start_col - 1 + col_offset

            # Column label at the header's depth level
            label_row = col_header_start_row + ch.depth
            label_text = ch.label
            if not cfg.show_code_row and not ch.is_abstract:
                label_text = f"{ch.code} {ch.label}"
            if ch.is_abstract and cfg.show_abstract_header_codes:
                label_text = f"{ch.code} {ch.label}"

            cell = ws.cell(row=label_row, column=excel_col, value=label_text)
            cell.fill = _GREY_FILL
            cell.border = _BORDER_ALL
            cell.alignment = Alignment(
                horizontal="center", vertical="top", wrap_text=True,
            )

            if ch.is_abstract:
                cell.font = _ABSTRACT_FONT
                cell.fill = _DARK_GREY_FILL
            else:
                cell.font = _HEADER_FONT

            # Column code row
            if cfg.show_code_row and not ch.is_abstract and col_code_row:
                code_cell = ws.cell(
                    row=col_code_row, column=excel_col, value=ch.code,
                )
                code_cell.fill = _GREY_FILL
                code_cell.border = _BORDER_ALL
                code_cell.alignment = Alignment(horizontal="center")

            # Header tooltip
            if cfg.add_header_comments and ch.categorisations:
                tooltip = _format_categorisations(ch.categorisations)
                cell.comment = Comment(tooltip, "dpmcore", width=400, height=150)

        # Merge column headers that span multiple depth levels
        _merge_column_headers(
            ws, layout.columns, col_positions, col_header_start_row,
            data_start_col, layout.max_col_depth,
        )

        # --- Row headers ---
        # "Rows" label
        rows_label_cell = ws.cell(
            row=data_start_row, column=1, value="Rows",
        )
        rows_label_cell.font = _HEADER_FONT
        rows_label_cell.fill = _GREY_FILL
        rows_label_cell.border = _BORDER_ALL
        rows_label_cell.alignment = Alignment(
            horizontal="center", vertical="center", text_rotation=90,
        )

        # Merge "Rows" label vertically
        if len(layout.rows) > 1:
            ws.merge_cells(
                start_row=data_start_row, start_column=1,
                end_row=data_start_row + len(layout.rows) - 1, end_column=1,
            )

        # Row header entries
        row_positions: dict[int, int] = {}
        for i, rh in enumerate(layout.rows):
            excel_row = data_start_row + i
            row_positions[rh.header_id] = excel_row

            # Row label with indentation
            label_text = rh.label
            if not cfg.show_code_column:
                label_text = f"{rh.code} {rh.label}"
            if rh.is_abstract and cfg.show_abstract_header_codes:
                label_text = f"{rh.code} {rh.label}"

            indent = max(0, rh.depth) * 2
            label_cell = ws.cell(
                row=excel_row, column=row_label_col, value=label_text,
            )
            label_cell.fill = _GREY_FILL
            label_cell.border = _BORDER_ALL
            label_cell.alignment = Alignment(
                horizontal="left", vertical="center",
                indent=indent, wrap_text=True,
            )

            if rh.is_abstract:
                label_cell.font = _ABSTRACT_FONT
                label_cell.fill = _DARK_GREY_FILL
                # Merge abstract row across all data columns
                if num_visible_cols > 0:
                    merge_end = data_start_col + num_visible_cols - 1
                    ws.merge_cells(
                        start_row=excel_row, start_column=row_label_col,
                        end_row=excel_row, end_column=merge_end,
                    )
            else:
                label_cell.font = Font(size=10)

            # Row code column
            if cfg.show_code_column and not rh.is_abstract:
                ws.cell(
                    row=excel_row, column=row_code_col, value=rh.code,
                ).border = _BORDER_ALL

            # Header tooltip
            if cfg.add_header_comments and rh.categorisations:
                tooltip = _format_categorisations(rh.categorisations)
                label_cell.comment = Comment(
                    tooltip, "dpmcore", width=400, height=150,
                )

        # --- Data cells ---
        default_sheet_id = None
        if not layout.sheets:
            # Find the sheet_id used in cells (usually None or a default)
            for key in layout.cells:
                default_sheet_id = key[2]
                break

        for rh in layout.rows:
            if rh.is_abstract:
                continue
            excel_row = row_positions[rh.header_id]

            for ch in layout.columns:
                if ch.is_abstract:
                    continue
                col_offset = col_positions[ch.header_id]
                excel_col = data_start_col - 1 + col_offset

                # Try to find cell data
                sheet_id = default_sheet_id
                cell_data = layout.cells.get(
                    (rh.header_id, ch.header_id, sheet_id),
                )

                cell = ws.cell(row=excel_row, column=excel_col)
                cell.font = _DATA_FONT
                cell.border = _BORDER_ALL

                if cell_data is None:
                    cell.fill = _EXCLUDED_FILL
                elif cell_data.is_excluded:
                    cell.fill = _EXCLUDED_FILL
                elif cell_data.variable_vid:
                    cell.value = cell_data.variable_vid

                    # Cell tooltip
                    if cfg.add_cell_comments and cell_data.dp_categorisations:
                        tooltip = (
                            f"VariableVID = {cell_data.variable_vid}\n"
                            + _format_categorisations(
                                cell_data.dp_categorisations,
                            )
                        )
                        cell.comment = Comment(
                            tooltip, "dpmcore", width=400, height=180,
                        )

        # --- Annotations ---
        if cfg.annotate:
            self._write_annotations(
                ws, layout, data_start_row, data_start_col,
                row_positions, col_positions, num_visible_cols,
            )

        # --- Outline groups ---
        _apply_row_groups(ws, layout.rows, row_positions)
        _apply_col_groups(
            ws, layout.columns, col_positions, data_start_col,
        )

        # --- Freeze panes ---
        freeze_ref = f"{get_column_letter(data_start_col)}{data_start_row}"
        ws.freeze_panes = freeze_ref

        # --- Column widths ---
        ws.column_dimensions["A"].width = 5
        ws.column_dimensions[get_column_letter(row_label_col)].width = 40
        if cfg.show_code_column:
            ws.column_dimensions[get_column_letter(row_code_col)].width = 8
        for col_offset in range(1, num_visible_cols + 1):
            col_letter = get_column_letter(data_start_col - 1 + col_offset)
            ws.column_dimensions[col_letter].width = 18

    def _write_annotations(
        self,
        ws: Any,
        layout: TableLayout,
        data_start_row: int,
        data_start_col: int,
        row_positions: dict[int, int],
        col_positions: dict[int, int],
        num_visible_cols: int,
    ) -> None:
        """Write dimensional annotations below and to the right of the grid."""
        # Collect all dimension IDs used
        all_dims = layout.dimension_ids
        if not all_dims:
            return

        dim_color_map: dict[int, str] = {}
        for i, (pid, _) in enumerate(all_dims):
            dim_color_map[pid] = _DIM_COLORS[i % len(_DIM_COLORS)]

        # --- Column annotations (below the data grid) ---
        ann_start_row = data_start_row + len(layout.rows) + 1

        for dim_idx, (prop_id, dim_label) in enumerate(all_dims):
            ann_row = ann_start_row + dim_idx
            color = dim_color_map[prop_id]

            # Dimension label
            label_cell = ws.cell(
                row=ann_row, column=data_start_col - 1, value=dim_label,
            )
            label_cell.font = Font(bold=True, size=9, color=color)
            label_cell.alignment = Alignment(horizontal="right")

            # Member values per column
            for ch in layout.columns:
                if ch.is_abstract:
                    continue
                col_offset = col_positions[ch.header_id]
                excel_col = data_start_col - 1 + col_offset

                member = _find_member(ch.categorisations, prop_id)
                if member:
                    mc = ws.cell(
                        row=ann_row, column=excel_col, value=member.member_label,
                    )
                    mc.font = Font(size=9, color=color)
                    mc.alignment = Alignment(
                        horizontal="center", wrap_text=True,
                    )

        # --- Row annotations (to the right of the data grid) ---
        ann_start_col = data_start_col + num_visible_cols + 1

        for dim_idx, (prop_id, dim_label) in enumerate(all_dims):
            ann_col = ann_start_col + dim_idx
            color = dim_color_map[prop_id]

            # Dimension label (in header area)
            label_cell = ws.cell(
                row=data_start_row - 1, column=ann_col, value=dim_label,
            )
            label_cell.font = Font(bold=True, size=9, color=color)
            label_cell.alignment = Alignment(
                horizontal="left", vertical="bottom", wrap_text=True,
            )

            # Member values per row
            for rh in layout.rows:
                if rh.is_abstract:
                    continue
                excel_row = row_positions[rh.header_id]

                member = _find_member(rh.categorisations, prop_id)
                if member:
                    mc = ws.cell(
                        row=excel_row, column=ann_col,
                        value=member.member_label,
                    )
                    mc.font = Font(size=9, color=color)
                    mc.alignment = Alignment(horizontal="left")

            # Set annotation column width
            ws.column_dimensions[get_column_letter(ann_col)].width = 25


def _find_member(
    cats: list[DimensionMember],
    property_id: int,
) -> Optional[DimensionMember]:
    """Find a DimensionMember matching a given property_id."""
    for dm in cats:
        if dm.property_id == property_id:
            return dm
    return None


def _format_categorisations(cats: list[DimensionMember]) -> str:
    """Format categorisations as tooltip text: Dimension = Member."""
    lines = []
    for dm in cats:
        lines.append(f"{dm.dimension_label}  =  {dm.member_label}")
    return "\n".join(lines)


def _build_header_tooltip(headers: list[LayoutHeader]) -> str:
    """Build a tooltip for sheet headers."""
    parts = []
    for h in headers:
        parts.append(f"{h.code} {h.label}")
        for dm in h.categorisations:
            parts.append(f"  {dm.dimension_label} = {dm.member_label}")
    return "\n".join(parts)


def _merge_column_headers(
    ws: Any,
    columns: list[LayoutHeader],
    col_positions: dict[int, int],
    col_header_start_row: int,
    data_start_col: int,
    max_depth: int,
) -> None:
    """Merge column header cells vertically (non-abstract at depth < max)
    and horizontally (abstract spanning children)."""
    for ch in columns:
        col_offset = col_positions[ch.header_id]
        if col_offset == 0:
            continue
        excel_col = data_start_col - 1 + col_offset
        label_row = col_header_start_row + ch.depth

        # Vertical merge: leaf columns that don't reach max_depth
        if not ch.is_abstract and ch.depth < max_depth:
            end_row = col_header_start_row + max_depth
            if end_row > label_row:
                ws.merge_cells(
                    start_row=label_row, start_column=excel_col,
                    end_row=end_row, end_column=excel_col,
                )

    # Horizontal merge for abstract headers: find span of children
    for ch in columns:
        if not ch.is_abstract:
            continue
        col_offset = col_positions[ch.header_id]
        if col_offset == 0:
            continue

        # Find all columns that are direct or indirect children
        children_positions = []
        for other in columns:
            if other.header_id == ch.header_id:
                continue
            if not other.is_abstract and _is_descendant(
                other, ch.header_id, {h.header_id: h for h in columns},
            ):
                pos = col_positions[other.header_id]
                if pos > 0:
                    children_positions.append(pos)

        if children_positions:
            min_pos = min(children_positions)
            max_pos = max(children_positions)
            start_col = data_start_col - 1 + min_pos
            end_col = data_start_col - 1 + max_pos
            label_row = col_header_start_row + ch.depth

            if end_col > start_col:
                ws.merge_cells(
                    start_row=label_row, start_column=start_col,
                    end_row=label_row, end_column=end_col,
                )


def _is_descendant(
    header: LayoutHeader,
    ancestor_id: int,
    by_id: dict[int, LayoutHeader],
) -> bool:
    """Check if header is a descendant of ancestor_id."""
    current = header
    visited: set[int] = set()
    while current.parent_header_id is not None:
        if current.parent_header_id in visited:
            break
        visited.add(current.parent_header_id)
        if current.parent_header_id == ancestor_id:
            return True
        current = by_id.get(current.parent_header_id)  # type: ignore[assignment]
        if current is None:
            break
    return False


def _apply_row_groups(
    ws: Any,
    rows: list[LayoutHeader],
    row_positions: dict[int, int],
) -> None:
    """Apply Excel outline grouping to hierarchical rows."""
    for rh in rows:
        if rh.depth > 0:
            excel_row = row_positions.get(rh.header_id)
            if excel_row:
                ws.row_dimensions[excel_row].outline_level = min(rh.depth, 7)


def _apply_col_groups(
    ws: Any,
    columns: list[LayoutHeader],
    col_positions: dict[int, int],
    data_start_col: int,
) -> None:
    """Apply Excel outline grouping to hierarchical columns."""
    for ch in columns:
        if ch.depth > 0 and not ch.is_abstract:
            col_offset = col_positions.get(ch.header_id, 0)
            if col_offset > 0:
                excel_col = data_start_col - 1 + col_offset
                col_letter = get_column_letter(excel_col)
                ws.column_dimensions[col_letter].outline_level = min(
                    ch.depth, 7,
                )
