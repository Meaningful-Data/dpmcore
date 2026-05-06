"""Tests for the pure-logic processing module."""

from types import SimpleNamespace

from dpmcore.services.layout_exporter.models import (
    DimensionMember,
    LayoutHeader,
)
from dpmcore.services.layout_exporter.processing import (
    build_cells,
    build_layout_headers,
    build_table_layout,
    sort_headers,
)


def _make_raw_header(
    header_id,
    header_vid,
    direction="x",
    code="1",
    label="L",
    order=1,
    is_abstract=False,
    is_key=False,
    parent_header_id=None,
    parent_first=True,
    context_id=None,
    property_id=None,
    subcategory_vid=None,
    key_variable_vid=None,
):
    tvh = SimpleNamespace(
        header_id=header_id,
        header_vid=header_vid,
        order=order,
        is_abstract=is_abstract,
        parent_header_id=parent_header_id,
        parent_first=parent_first,
    )
    header = SimpleNamespace(direction=direction, is_key=is_key)
    hv = SimpleNamespace(
        header_vid=header_vid,
        code=code,
        label=label,
        context_id=context_id,
        property_id=property_id,
        subcategory_vid=subcategory_vid,
        key_variable_vid=key_variable_vid,
    )
    return (tvh, header, hv)


def test_build_layout_headers_splits_by_direction():
    raws = [
        _make_raw_header(1, 11, direction="X", order=1),
        _make_raw_header(2, 12, direction="Y", order=1),
        _make_raw_header(3, 13, direction="Z", order=1),
    ]
    cols, rows, sheets = build_layout_headers(raws, {}, {}, {})
    assert [h.header_id for h in cols] == [1]
    assert [h.header_id for h in rows] == [2]
    assert [h.header_id for h in sheets] == [3]


def test_build_layout_headers_attaches_context_categorisations():
    dm = DimensionMember(
        property_id=5,
        dimension_label="D",
        dimension_code="D",
        domain_code="DOM",
        member_label="M",
        member_code="m",
    )
    raws = [_make_raw_header(1, 11, context_id=99)]
    cols, _, _ = build_layout_headers(raws, {99: [dm]}, {}, {})
    assert cols[0].categorisations == [dm]


def test_build_layout_headers_attaches_property_categorisation():
    dm = DimensionMember(
        property_id=42,
        dimension_label="Main Property",
        dimension_code="ATY",
        domain_code="DOM",
        member_label="lbl",
        member_code="m",
    )
    raws = [_make_raw_header(1, 11, property_id=42)]
    cols, _, _ = build_layout_headers(raws, {}, {42: dm}, {})
    assert cols[0].categorisations == [dm]


def test_build_layout_headers_zero_pads_numeric_codes():
    raws = [_make_raw_header(1, 11, code="7")]
    cols, _, _ = build_layout_headers(raws, {}, {}, {})
    assert cols[0].code == "0007"


def test_build_layout_headers_keeps_alphanumeric_codes():
    raws = [_make_raw_header(1, 11, code="A1")]
    cols, _, _ = build_layout_headers(raws, {}, {}, {})
    assert cols[0].code == "A1"


def test_build_layout_headers_subcategory_attached():
    raws = [_make_raw_header(1, 11, direction="z", subcategory_vid=8)]
    _, _, sheets = build_layout_headers(
        raws, {}, {}, {8: ("SC", "Desc", "CAT")}
    )
    assert sheets[0].subcategory_code == "SC"
    assert sheets[0].subcategory_description == "Desc"
    assert sheets[0].subcategory_cat_code == "CAT"


def test_build_layout_headers_parent_first_none_defaults_true():
    raws = [_make_raw_header(1, 11, parent_first=None)]
    cols, _, _ = build_layout_headers(raws, {}, {}, {})
    assert cols[0].parent_first is True


def test_build_layout_headers_blank_label_and_code():
    tvh = SimpleNamespace(
        header_id=1,
        header_vid=11,
        order=None,
        is_abstract=None,
        parent_header_id=None,
        parent_first=False,
    )
    header = SimpleNamespace(direction="x", is_key=False)
    hv = SimpleNamespace(
        header_vid=11,
        code=None,
        label=None,
        context_id=None,
        property_id=None,
        subcategory_vid=None,
        key_variable_vid=None,
    )
    cols, _, _ = build_layout_headers([(tvh, header, hv)], {}, {}, None)
    h = cols[0]
    assert h.code == ""
    assert h.label == ""
    assert h.order == 0
    assert h.is_abstract is False
    assert h.parent_first is False


def test_sort_headers_empty():
    assert sort_headers([]) == []


def test_sort_headers_parent_before_children():
    parent = LayoutHeader(
        header_id=1,
        header_vid=1,
        code="P",
        label="P",
        direction="y",
        order=1,
        is_abstract=False,
        is_key=False,
        parent_header_id=None,
        parent_first=True,
    )
    child = LayoutHeader(
        header_id=2,
        header_vid=2,
        code="C",
        label="C",
        direction="y",
        order=2,
        is_abstract=False,
        is_key=False,
        parent_header_id=1,
        parent_first=True,
    )
    sib = LayoutHeader(
        header_id=3,
        header_vid=3,
        code="S",
        label="S",
        direction="y",
        order=3,
        is_abstract=False,
        is_key=False,
        parent_header_id=None,
        parent_first=True,
    )
    out = sort_headers([sib, child, parent])
    assert [h.header_id for h in out] == [1, 2, 3]
    assert out[0].depth == 0
    assert out[1].depth == 1


def test_sort_headers_parent_after_children():
    parent = LayoutHeader(
        header_id=1,
        header_vid=1,
        code="P",
        label="P",
        direction="y",
        order=2,
        is_abstract=False,
        is_key=False,
        parent_header_id=None,
        parent_first=False,
    )
    child = LayoutHeader(
        header_id=2,
        header_vid=2,
        code="C",
        label="C",
        direction="y",
        order=1,
        is_abstract=False,
        is_key=False,
        parent_header_id=1,
        parent_first=True,
    )
    out = sort_headers([parent, child])
    # Child should appear before parent because parent.parent_first=False
    assert [h.header_id for h in out] == [2, 1]


def test_sort_headers_orphan_parent_id():
    h = LayoutHeader(
        header_id=2,
        header_vid=2,
        code="C",
        label="C",
        direction="y",
        order=1,
        is_abstract=False,
        is_key=False,
        parent_header_id=99,  # not in the set
        parent_first=True,
    )
    out = sort_headers([h])
    assert out[0].depth == 0


def test_build_cells_basic():
    cell = SimpleNamespace(row_id=1, column_id=2, sheet_id=None)
    tvc = SimpleNamespace(
        variable_vid=100, is_excluded=False, is_void=False, sign="positive"
    )
    cells = build_cells(
        [(tvc, cell)],
        row_ids={1},
        col_ids={2},
        sheet_ids=set(),
        dp_cats={100: []},
        variable_info={100: (10, "m", "Currency")},
    )
    cd = cells[(1, 2, None)]
    assert cd.variable_id == 10
    assert cd.data_type_code == "m"
    assert cd.domain_label == "Currency"
    assert cd.sign == "positive"


def test_build_cells_skips_unknown_row():
    cell = SimpleNamespace(row_id=99, column_id=2, sheet_id=None)
    tvc = SimpleNamespace(
        variable_vid=None, is_excluded=False, is_void=None, sign=None
    )
    cells = build_cells(
        [(tvc, cell)],
        row_ids={1},
        col_ids={2},
        sheet_ids=set(),
        dp_cats={},
    )
    assert cells == {}


def test_build_cells_skips_unknown_column():
    cell = SimpleNamespace(row_id=1, column_id=99, sheet_id=None)
    tvc = SimpleNamespace(
        variable_vid=None, is_excluded=False, is_void=None, sign=None
    )
    cells = build_cells(
        [(tvc, cell)],
        row_ids={1},
        col_ids={2},
        sheet_ids=set(),
        dp_cats={},
    )
    assert cells == {}


def test_build_cells_skips_unknown_sheet():
    cell = SimpleNamespace(row_id=1, column_id=2, sheet_id=42)
    tvc = SimpleNamespace(
        variable_vid=None, is_excluded=False, is_void=None, sign=None
    )
    cells = build_cells(
        [(tvc, cell)],
        row_ids={1},
        col_ids={2},
        sheet_ids={5},
        dp_cats={},
    )
    assert cells == {}


def test_build_cells_open_row_allows_none_row_id():
    cell = SimpleNamespace(row_id=None, column_id=2, sheet_id=None)
    tvc = SimpleNamespace(
        variable_vid=None, is_excluded=False, is_void=False, sign=""
    )
    cells = build_cells(
        [(tvc, cell)],
        row_ids=set(),  # empty for open-row
        col_ids={2},
        sheet_ids=set(),
        dp_cats={},
    )
    assert (None, 2, None) in cells
    assert cells[(None, 2, None)].is_void is False


def test_build_cells_is_void_none_defaults_false():
    cell = SimpleNamespace(row_id=1, column_id=2, sheet_id=None)
    tvc = SimpleNamespace(
        variable_vid=None, is_excluded=False, is_void=None, sign=None
    )
    cells = build_cells(
        [(tvc, cell)],
        {1},
        {2},
        set(),
        {},
    )
    assert cells[(1, 2, None)].is_void is False


def test_build_table_layout_collects_dimensions_and_open_row():
    columns = [
        LayoutHeader(
            header_id=1,
            header_vid=1,
            code="C1",
            label="L1",
            direction="x",
            order=1,
            is_abstract=False,
            is_key=False,
            parent_header_id=None,
            parent_first=True,
            depth=0,
            categorisations=[
                DimensionMember(
                    property_id=42,
                    dimension_label="D",
                    dimension_code="DC",
                    domain_code="DOM",
                    member_label="M",
                    member_code="m",
                )
            ],
        )
    ]
    tv = SimpleNamespace(table_vid=1, code="T", name="Table")
    layout = build_table_layout(tv, columns, [], [], {})
    assert layout.is_open_row is True
    assert layout.dimension_ids == [(42, "D")]
    assert layout.max_col_depth == 0
    assert layout.max_row_depth == 0


def test_build_table_layout_with_rows_not_open_row():
    rows = [
        LayoutHeader(
            header_id=2,
            header_vid=2,
            code="R",
            label="R",
            direction="y",
            order=1,
            is_abstract=False,
            is_key=False,
            parent_header_id=None,
            parent_first=True,
            depth=2,
        )
    ]
    tv = SimpleNamespace(table_vid=1, code=None, name=None)
    layout = build_table_layout(tv, [], rows, [], {})
    assert layout.is_open_row is False
    assert layout.max_row_depth == 2
    assert layout.table_code == ""
    assert layout.table_name == ""
