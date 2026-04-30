"""Smoke tests for layout_exporter dataclass models."""

from dpmcore.services.layout_exporter.models import (
    CellData,
    DimensionMember,
    ExportConfig,
    LayoutHeader,
    TableLayout,
)


def test_dimension_member_defaults():
    dm = DimensionMember(
        property_id=1,
        dimension_label="Dim",
        dimension_code="D",
        domain_code="DOM",
        member_label="M",
        member_code="m",
    )
    assert dm.data_type_code == ""
    assert dm.hierarchy_code == ""
    assert dm.sign == ""


def test_layout_header_defaults():
    h = LayoutHeader(
        header_id=1,
        header_vid=1,
        code="A",
        label="A",
        direction="x",
        order=1,
        is_abstract=False,
        is_key=False,
        parent_header_id=None,
        parent_first=True,
    )
    assert h.depth == 0
    assert h.sort_key == ""
    assert h.categorisations == []
    assert h.key_categorisations == []
    assert h.subcategory_code == ""
    assert h.key_variable_vid is None
    assert h.key_variable_id is None


def test_cell_data_defaults():
    cd = CellData(
        row_header_id=1,
        col_header_id=2,
        sheet_header_id=None,
        variable_vid=10,
    )
    assert cd.variable_id is None
    assert cd.is_excluded is False
    assert cd.is_void is False
    assert cd.sign == ""
    assert cd.data_type_code == ""
    assert cd.dp_categorisations == []


def test_export_config_defaults():
    c = ExportConfig()
    assert c.annotate is True
    assert c.add_header_comments is True
    assert c.add_cell_comments is True
    assert c.show_code_row is True
    assert c.show_code_column is True
    assert c.show_abstract_header_codes is False


def test_table_layout_defaults():
    tl = TableLayout(table_vid=1, table_code="T", table_name="Table")
    assert tl.rows == []
    assert tl.columns == []
    assert tl.sheets == []
    assert tl.cells == {}
    assert tl.dimension_ids == []
    assert tl.is_open_row is False
    assert tl.max_col_depth == 0
    assert tl.max_row_depth == 0
