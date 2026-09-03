"""Data models for the table layout exporter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DimensionMember:
    """One dimensional assignment: a dimension (property) to a member."""

    property_id: int
    dimension_label: str
    dimension_code: str
    domain_code: str
    member_label: str
    member_code: str
    data_type_code: str = ""
    hierarchy_code: str = ""
    sign: str = ""


@dataclass(frozen=True)
class ReleaseWindow:
    """Validity window of the version being exported.

    Codes and signatures are release-versioned, so a workbook must show
    the ones in force while its module version was reportable — not
    today's. The window is the module version's start/end releases (the
    table version's own, when tables are exported outside a module).

    ``start_release_id`` of ``None`` means "since the beginning" and
    ``end_release_id`` of ``None`` means "still open".
    """

    start_release_id: Optional[int] = None
    end_release_id: Optional[int] = None


@dataclass
class EnumValue:
    """One allowed value of an enumerated variable."""

    code: str
    label: str
    depth: int = 0
    # Fully qualified member signature (e.g. ``eba_CU:ALL``).
    signature: str = ""


@dataclass
class Enumeration:
    """The hierarchy that restricts an enumerated variable's values."""

    subcategory_vid: int
    code: str
    name: str
    category_code: str
    values: list[EnumValue] = field(default_factory=list)


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
    subcategory_vid: Optional[int] = None
    subcategory_code: str = ""
    subcategory_description: str = ""
    subcategory_cat_code: str = ""
    # Open-row key column fields (populated for IsKey columns)
    key_variable_vid: Optional[int] = None
    key_variable_id: Optional[int] = None
    key_data_type_code: str = ""
    key_property_name: str = ""
    key_categorisations: list["DimensionMember"] = field(default_factory=list)
    key_enumeration: Optional[Enumeration] = None


@dataclass
class CellData:
    """One cell in the table grid."""

    row_header_id: Optional[int]
    col_header_id: int
    sheet_header_id: Optional[int]
    variable_vid: Optional[int]
    variable_id: Optional[int] = None
    is_excluded: bool = False
    is_void: bool = False
    sign: str = ""
    data_type_code: str = ""
    domain_label: str = ""
    dp_categorisations: list[DimensionMember] = field(default_factory=list)
    # Enumerated cells only: the hierarchy of the bounding header that
    # restricts which values may be reported here.
    subcategory_vid: Optional[int] = None
    enumeration: Optional[Enumeration] = None


@dataclass
class ExportConfig:
    """Configuration flags for the export."""

    annotate: bool = True
    add_header_comments: bool = True
    add_cell_comments: bool = True
    show_code_row: bool = True
    show_code_column: bool = True
    show_abstract_header_codes: bool = False


@dataclass
class TableLayout:
    """Complete processed layout for one DPM table."""

    table_vid: int
    table_code: str
    table_name: str
    rows: list[LayoutHeader] = field(default_factory=list)
    columns: list[LayoutHeader] = field(default_factory=list)
    sheets: list[LayoutHeader] = field(default_factory=list)
    cells: dict[tuple[Optional[int], int, Optional[int]], CellData] = field(
        default_factory=dict,
    )
    max_col_depth: int = 0
    max_row_depth: int = 0
    dimension_ids: list[tuple[int, str]] = field(default_factory=list)
    is_open_row: bool = False
