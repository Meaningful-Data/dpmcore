"""Data models for the table layout exporter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DimensionMember:
    """One dimensional assignment: a dimension (property) mapped to a member (item)."""

    property_id: int
    dimension_label: str
    dimension_code: str
    domain_code: str
    member_label: str
    member_code: str
    data_type_code: str = ""
    hierarchy_code: str = ""
    sign: str = ""


@dataclass
class LayoutHeader:
    """A resolved header in display order."""

    header_id: int
    header_vid: int
    code: str
    label: str
    direction: str  # "x" (column), "y" (row), "z" (sheet)
    order: int
    is_abstract: bool
    is_key: bool
    parent_header_id: Optional[int]
    parent_first: bool
    depth: int = 0
    sort_key: str = ""
    categorisations: list[DimensionMember] = field(default_factory=list)


@dataclass
class CellData:
    """One cell in the table grid."""

    row_header_id: int
    col_header_id: int
    sheet_header_id: Optional[int]
    variable_vid: Optional[int]
    is_excluded: bool
    is_void: bool
    sign: str = ""
    dp_categorisations: list[DimensionMember] = field(default_factory=list)


@dataclass
class ExportConfig:
    """Configuration flags for the export."""

    annotate: bool = True
    add_header_comments: bool = True
    add_cell_comments: bool = True
    show_code_row: bool = True
    show_code_column: bool = True
    show_abstract_header_codes: bool = True


@dataclass
class TableLayout:
    """Complete processed layout for one DPM table."""

    table_vid: int
    table_code: str
    table_name: str
    rows: list[LayoutHeader] = field(default_factory=list)
    columns: list[LayoutHeader] = field(default_factory=list)
    sheets: list[LayoutHeader] = field(default_factory=list)
    cells: dict[tuple[int, int, Optional[int]], CellData] = field(
        default_factory=dict,
    )
    max_col_depth: int = 0
    max_row_depth: int = 0
    dimension_ids: list[tuple[int, str]] = field(default_factory=list)
