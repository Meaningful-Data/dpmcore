"""Unit tests for the family-2 (axes) model-validation rules."""

from typing import Any, List

from dpmcore.services.model_validation.registry import (
    Finding,
    RuleContext,
)
from dpmcore.services.model_validation.release_context import (
    ReleaseContext,
)
from dpmcore.services.model_validation.rules import axes
from dpmcore.services.model_validation.snapshot import (
    CategoryRow,
    HeaderRow,
    HeaderVersionRow,
    ItemCategoryRow,
    ModelSnapshot,
    ModuleVersionCompositionRow,
    ModuleVersionRow,
    PropertyCategoryRow,
    PropertyRow,
    TableRow,
    TableVersionHeaderRow,
    TableVersionRow,
)

CUR = 100
PREV = 50
DRAFT = 9999

REL = ReleaseContext(current_release_id=CUR, draft_release_id=DRAFT)


def _ctx(**stores: List[Any]) -> RuleContext:
    return RuleContext(
        snapshot=ModelSnapshot.from_rows(**stores), release=REL
    )


def _table(
    table_id: int = 1,
    *,
    is_abstract: Any = False,
    rows: Any = False,
    cols: Any = False,
    sheets: Any = False,
) -> TableRow:
    return TableRow(
        table_id=table_id,
        is_abstract=is_abstract,
        has_open_columns=cols,
        has_open_rows=rows,
        has_open_sheets=sheets,
    )


def _tv(
    vid: int = 10,
    *,
    table_id: Any = 1,
    code: Any = "T1",
    start: Any = CUR,
    end: Any = None,
    property_id: Any = None,
) -> TableVersionRow:
    return TableVersionRow(
        table_vid=vid,
        code=code,
        name=None,
        table_id=table_id,
        abstract_table_id=None,
        key_id=None,
        property_id=property_id,
        context_id=None,
        start_release_id=start,
        end_release_id=end,
    )


def _mv(vid: int = 500) -> ModuleVersionRow:
    return ModuleVersionRow(
        module_vid=vid,
        module_id=1,
        global_key_id=None,
        start_release_id=CUR,
        end_release_id=None,
        code="MOD",
        name=None,
        version_number=None,
        is_reported=None,
        is_calculated=None,
    )


def _mvc(
    module_vid: int = 500, table_vid: int = 10, table_id: int = 1
) -> ModuleVersionCompositionRow:
    return ModuleVersionCompositionRow(
        module_vid=module_vid,
        table_id=table_id,
        table_vid=table_vid,
        order=None,
    )


def _header(
    header_id: int = 1,
    *,
    table_id: Any = 1,
    direction: Any = "X",
    is_key: Any = False,
) -> HeaderRow:
    return HeaderRow(
        header_id=header_id,
        table_id=table_id,
        direction=direction,
        is_key=is_key,
        is_attribute=None,
    )


def _hv(
    vid: int = 100,
    *,
    header_id: Any = 1,
    property_id: Any = None,
    end: Any = None,
) -> HeaderVersionRow:
    return HeaderVersionRow(
        header_vid=vid,
        header_id=header_id,
        code="010",
        label=None,
        property_id=property_id,
        context_id=None,
        subcategory_vid=None,
        key_variable_vid=None,
        start_release_id=CUR,
        end_release_id=end,
    )


def _tvh(
    table_vid: int = 10,
    header_id: int = 1,
    *,
    header_vid: Any = None,
    is_abstract: Any = False,
) -> TableVersionHeaderRow:
    return TableVersionHeaderRow(
        table_vid=table_vid,
        header_id=header_id,
        header_vid=header_vid,
        parent_header_id=None,
        parent_first=None,
        order=None,
        is_abstract=is_abstract,
        is_unique=None,
    )


def _base_stores(
    table: TableRow, tv: TableVersionRow, **extra: List[Any]
) -> dict:
    stores: dict = {
        "tables": [table],
        "table_versions": [tv],
        "module_versions": [_mv()],
        "module_version_compositions": [
            _mvc(table_vid=tv.table_vid, table_id=table.table_id)
        ],
    }
    stores.update(extra)
    return stores


def _vids(findings: List[Finding]) -> List[Any]:
    return [f.objects[0].id for f in findings]


# ------------------------------------------------------------------
# Shared plumbing (_current_open_tvs)
# ------------------------------------------------------------------


class TestCurrentOpenTvs:
    def test_expired_tv_is_skipped(self) -> None:
        ctx = _ctx(
            **_base_stores(_table(rows=True), _tv(end=PREV))
        )
        assert list(axes.rule_2_1(ctx)) == []

    def test_old_start_release_is_skipped(self) -> None:
        ctx = _ctx(
            **_base_stores(_table(rows=True), _tv(start=PREV))
        )
        assert list(axes.rule_2_1(ctx)) == []

    def test_draft_start_release_counts_as_current(self) -> None:
        ctx = _ctx(
            **_base_stores(_table(rows=True), _tv(start=DRAFT))
        )
        assert _vids(list(axes.rule_2_1(ctx))) == [10]

    def test_tv_not_in_any_module_is_skipped(self) -> None:
        ctx = _ctx(
            tables=[_table(rows=True)],
            table_versions=[_tv()],
        )
        assert list(axes.rule_2_1(ctx)) == []

    def test_dangling_module_vid_is_skipped(self) -> None:
        ctx = _ctx(
            tables=[_table(rows=True)],
            table_versions=[_tv()],
            module_version_compositions=[_mvc(module_vid=999)],
        )
        assert list(axes.rule_2_1(ctx)) == []

    def test_missing_table_is_skipped(self) -> None:
        stores = _base_stores(_table(rows=True), _tv(table_id=77))
        ctx = _ctx(**stores)
        assert list(axes.rule_2_1(ctx)) == []

    def test_null_table_id_is_skipped(self) -> None:
        stores = _base_stores(_table(rows=True), _tv(table_id=None))
        ctx = _ctx(**stores)
        assert list(axes.rule_2_1(ctx)) == []


# ------------------------------------------------------------------
# 2_1 .. 2_5 (open axes need key / non-key headers)
# ------------------------------------------------------------------


class TestRule21:
    def test_fires_without_key_column(self) -> None:
        ctx = _ctx(**_base_stores(_table(rows=True), _tv()))
        findings = list(axes.rule_2_1(ctx))
        assert _vids(findings) == [10]
        assert findings[0].objects[0].kind == "table_version"
        assert findings[0].objects[0].code == "T1"

    def test_clean_with_key_column(self) -> None:
        stores = _base_stores(
            _table(rows=True),
            _tv(),
            headers=[_header(is_key=True, direction="X")],
            table_version_headers=[_tvh()],
        )
        assert list(axes.rule_2_1(_ctx(**stores))) == []

    def test_abstract_table_is_skipped(self) -> None:
        ctx = _ctx(
            **_base_stores(
                _table(is_abstract=True, rows=True), _tv()
            )
        )
        assert list(axes.rule_2_1(ctx)) == []

    def test_null_abstract_flag_is_skipped(self) -> None:
        ctx = _ctx(
            **_base_stores(
                _table(is_abstract=None, rows=True), _tv()
            )
        )
        assert list(axes.rule_2_1(ctx)) == []

    def test_closed_rows_is_skipped(self) -> None:
        ctx = _ctx(**_base_stores(_table(rows=False), _tv()))
        assert list(axes.rule_2_1(ctx)) == []

    def test_key_header_of_other_table_does_not_count(self) -> None:
        stores = _base_stores(
            _table(rows=True),
            _tv(),
            headers=[
                _header(is_key=True, direction="X", table_id=2)
            ],
            table_version_headers=[_tvh()],
        )
        findings = list(axes.rule_2_1(_ctx(**stores)))
        assert _vids(findings) == [10]

    def test_null_is_key_never_matches(self) -> None:
        stores = _base_stores(
            _table(rows=True),
            _tv(),
            headers=[_header(is_key=None, direction="X")],
            table_version_headers=[_tvh()],
        )
        assert _vids(list(axes.rule_2_1(_ctx(**stores)))) == [10]

    def test_wrong_direction_does_not_count(self) -> None:
        stores = _base_stores(
            _table(rows=True),
            _tv(),
            headers=[_header(is_key=True, direction="Y")],
            table_version_headers=[_tvh()],
        )
        assert _vids(list(axes.rule_2_1(_ctx(**stores)))) == [10]

    def test_dangling_header_id_does_not_count(self) -> None:
        stores = _base_stores(
            _table(rows=True),
            _tv(),
            table_version_headers=[_tvh(header_id=42)],
        )
        assert _vids(list(axes.rule_2_1(_ctx(**stores)))) == [10]


class TestRule22:
    def test_fires_without_key_row(self) -> None:
        ctx = _ctx(**_base_stores(_table(cols=True), _tv()))
        assert _vids(list(axes.rule_2_2(ctx))) == [10]

    def test_clean_with_key_row(self) -> None:
        stores = _base_stores(
            _table(cols=True),
            _tv(),
            headers=[_header(is_key=True, direction="Y")],
            table_version_headers=[_tvh()],
        )
        assert list(axes.rule_2_2(_ctx(**stores))) == []


class TestRule23:
    def test_fires_without_key_sheet(self) -> None:
        ctx = _ctx(**_base_stores(_table(sheets=True), _tv()))
        assert _vids(list(axes.rule_2_3(ctx))) == [10]

    def test_clean_with_key_sheet(self) -> None:
        stores = _base_stores(
            _table(sheets=True),
            _tv(),
            headers=[_header(is_key=True, direction="Z")],
            table_version_headers=[_tvh()],
        )
        assert list(axes.rule_2_3(_ctx(**stores))) == []


class TestRule24:
    def test_fires_without_non_key_column(self) -> None:
        stores = _base_stores(
            _table(rows=True),
            _tv(),
            headers=[_header(is_key=True, direction="X")],
            table_version_headers=[_tvh()],
        )
        assert _vids(list(axes.rule_2_4(_ctx(**stores)))) == [10]

    def test_clean_with_non_key_column(self) -> None:
        stores = _base_stores(
            _table(rows=True),
            _tv(),
            headers=[_header(is_key=False, direction="X")],
            table_version_headers=[_tvh()],
        )
        assert list(axes.rule_2_4(_ctx(**stores))) == []


class TestRule25:
    def test_fires_without_non_key_row(self) -> None:
        ctx = _ctx(**_base_stores(_table(cols=True), _tv()))
        assert _vids(list(axes.rule_2_5(ctx))) == [10]

    def test_clean_with_non_key_row(self) -> None:
        stores = _base_stores(
            _table(cols=True),
            _tv(),
            headers=[_header(is_key=False, direction="Y")],
            table_version_headers=[_tvh()],
        )
        assert list(axes.rule_2_5(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 2_6 (closed row & column tables need X and Y headers)
# ------------------------------------------------------------------


class TestRule26:
    def _stores(self, headers: List[HeaderRow]) -> dict:
        return _base_stores(
            _table(),
            _tv(),
            headers=headers,
            table_version_headers=[
                _tvh(header_id=h.header_id) for h in headers
            ],
        )

    def test_fires_when_missing_both(self) -> None:
        ctx = _ctx(**self._stores([]))
        assert _vids(list(axes.rule_2_6(ctx))) == [10]

    def test_fires_when_missing_columns(self) -> None:
        ctx = _ctx(**self._stores([_header(direction="Y")]))
        assert _vids(list(axes.rule_2_6(ctx))) == [10]

    def test_clean_with_rows_and_columns(self) -> None:
        ctx = _ctx(
            **self._stores(
                [
                    _header(1, direction="X"),
                    _header(2, direction="Y"),
                ]
            )
        )
        assert list(axes.rule_2_6(ctx)) == []

    def test_open_rows_is_skipped(self) -> None:
        ctx = _ctx(**_base_stores(_table(rows=True), _tv()))
        assert list(axes.rule_2_6(ctx)) == []

    def test_open_columns_is_skipped(self) -> None:
        ctx = _ctx(**_base_stores(_table(cols=True), _tv()))
        assert list(axes.rule_2_6(ctx)) == []

    def test_abstract_table_is_skipped(self) -> None:
        ctx = _ctx(**_base_stores(_table(is_abstract=True), _tv()))
        assert list(axes.rule_2_6(ctx)) == []


# ------------------------------------------------------------------
# 2_7 .. 2_9 (closed axes must not have key headers)
# ------------------------------------------------------------------


class TestRule27:
    def test_fires_with_key_column_on_closed_rows(self) -> None:
        stores = _base_stores(
            _table(rows=False),
            _tv(),
            headers=[_header(is_key=True, direction="X")],
            table_version_headers=[_tvh()],
        )
        assert _vids(list(axes.rule_2_7(_ctx(**stores)))) == [10]

    def test_clean_without_key_column(self) -> None:
        ctx = _ctx(**_base_stores(_table(rows=False), _tv()))
        assert list(axes.rule_2_7(ctx)) == []

    def test_open_rows_is_skipped(self) -> None:
        stores = _base_stores(
            _table(rows=True),
            _tv(),
            headers=[_header(is_key=True, direction="X")],
            table_version_headers=[_tvh()],
        )
        assert list(axes.rule_2_7(_ctx(**stores))) == []

    def test_null_flag_is_skipped(self) -> None:
        stores = _base_stores(
            _table(rows=None),
            _tv(),
            headers=[_header(is_key=True, direction="X")],
            table_version_headers=[_tvh()],
        )
        assert list(axes.rule_2_7(_ctx(**stores))) == []


class TestRule28:
    def test_fires_with_key_row_on_closed_columns(self) -> None:
        stores = _base_stores(
            _table(cols=False),
            _tv(),
            headers=[_header(is_key=True, direction="Y")],
            table_version_headers=[_tvh()],
        )
        assert _vids(list(axes.rule_2_8(_ctx(**stores)))) == [10]

    def test_clean_without_key_row(self) -> None:
        ctx = _ctx(**_base_stores(_table(), _tv()))
        assert list(axes.rule_2_8(ctx)) == []


class TestRule29:
    def test_fires_with_key_sheet_on_closed_sheets(self) -> None:
        stores = _base_stores(
            _table(sheets=False),
            _tv(),
            headers=[_header(is_key=True, direction="Z")],
            table_version_headers=[_tvh()],
        )
        assert _vids(list(axes.rule_2_9(_ctx(**stores)))) == [10]

    def test_clean_without_key_sheet(self) -> None:
        ctx = _ctx(**_base_stores(_table(), _tv()))
        assert list(axes.rule_2_9(ctx)) == []


# ------------------------------------------------------------------
# 2_10 / 2_11 / 2_12 (main-property axis rules)
# ------------------------------------------------------------------


def _prop_header_stores(
    *,
    tv_property: Any = None,
    header_specs: Any = (),
) -> dict:
    """Build stores with headers described by (id, dir, prop, key)."""
    headers = []
    header_versions = []
    tvhs = []
    for header_id, direction, property_id, is_key in header_specs:
        headers.append(
            _header(header_id, direction=direction, is_key=is_key)
        )
        header_versions.append(
            _hv(
                100 + header_id,
                header_id=header_id,
                property_id=property_id,
            )
        )
        tvhs.append(
            _tvh(header_id=header_id, header_vid=100 + header_id)
        )
    return _base_stores(
        _table(),
        _tv(property_id=tv_property),
        headers=headers,
        header_versions=header_versions,
        table_version_headers=tvhs,
    )


class TestRule210:
    def test_fires_with_two_property_axes(self) -> None:
        stores = _prop_header_stores(
            header_specs=[
                (1, "X", 7, False),
                (2, "Y", 8, False),
            ]
        )
        assert _vids(list(axes.rule_2_10(_ctx(**stores)))) == [10]

    def test_fires_with_axis_plus_whole_table_property(self) -> None:
        stores = _prop_header_stores(
            tv_property=9,
            header_specs=[(1, "X", 7, False)],
        )
        assert _vids(list(axes.rule_2_10(_ctx(**stores)))) == [10]

    def test_clean_with_single_axis(self) -> None:
        stores = _prop_header_stores(
            header_specs=[
                (1, "X", 7, False),
                (2, "X", 8, False),
            ]
        )
        assert list(axes.rule_2_10(_ctx(**stores))) == []

    def test_abstract_table_is_skipped(self) -> None:
        stores = _base_stores(_table(is_abstract=True), _tv())
        assert list(axes.rule_2_10(_ctx(**stores))) == []

    def test_expired_header_version_does_not_count(self) -> None:
        stores = _prop_header_stores(
            header_specs=[(1, "X", 7, False)]
        )
        stores["header_versions"].append(
            _hv(300, header_id=2, property_id=8, end=PREV)
        )
        stores["headers"].append(_header(2, direction="Y"))
        stores["table_version_headers"].append(
            _tvh(header_id=2, header_vid=300)
        )
        assert list(axes.rule_2_10(_ctx(**stores))) == []

    def test_key_header_does_not_count(self) -> None:
        stores = _prop_header_stores(
            header_specs=[
                (1, "X", 7, False),
                (2, "Y", 8, True),
            ]
        )
        assert list(axes.rule_2_10(_ctx(**stores))) == []

    def test_abstract_tvh_does_not_count(self) -> None:
        stores = _prop_header_stores(
            header_specs=[(1, "X", 7, False)]
        )
        stores["headers"].append(_header(2, direction="Y"))
        stores["header_versions"].append(
            _hv(300, header_id=2, property_id=8)
        )
        stores["table_version_headers"].append(
            _tvh(header_id=2, header_vid=300, is_abstract=True)
        )
        assert list(axes.rule_2_10(_ctx(**stores))) == []

    def test_null_header_vid_does_not_count(self) -> None:
        stores = _prop_header_stores(
            header_specs=[(1, "X", 7, False)]
        )
        stores["table_version_headers"].append(
            _tvh(header_id=2, header_vid=None)
        )
        assert list(axes.rule_2_10(_ctx(**stores))) == []

    def test_dangling_header_vid_does_not_count(self) -> None:
        stores = _prop_header_stores(
            header_specs=[(1, "X", 7, False)]
        )
        stores["table_version_headers"].append(
            _tvh(header_id=2, header_vid=999)
        )
        assert list(axes.rule_2_10(_ctx(**stores))) == []

    def test_null_header_id_does_not_count(self) -> None:
        stores = _prop_header_stores(
            header_specs=[(1, "X", 7, False)]
        )
        stores["header_versions"].append(
            _hv(300, header_id=None, property_id=8)
        )
        stores["table_version_headers"].append(
            _tvh(header_id=2, header_vid=300)
        )
        assert list(axes.rule_2_10(_ctx(**stores))) == []

    def test_header_of_other_table_does_not_count(self) -> None:
        stores = _prop_header_stores(
            header_specs=[(1, "X", 7, False)]
        )
        stores["headers"].append(
            _header(2, direction="Y", table_id=2)
        )
        stores["header_versions"].append(
            _hv(300, header_id=2, property_id=8)
        )
        stores["table_version_headers"].append(
            _tvh(header_id=2, header_vid=300)
        )
        assert list(axes.rule_2_10(_ctx(**stores))) == []

    def test_null_direction_does_not_count(self) -> None:
        stores = _prop_header_stores(
            header_specs=[
                (1, "X", 7, False),
                (2, None, 8, False),
            ]
        )
        assert list(axes.rule_2_10(_ctx(**stores))) == []


class TestRule211:
    def test_fires_without_any_main_property(self) -> None:
        stores = _prop_header_stores(
            header_specs=[(1, "X", None, False)]
        )
        assert _vids(list(axes.rule_2_11(_ctx(**stores)))) == [10]

    def test_clean_with_header_property(self) -> None:
        stores = _prop_header_stores(
            header_specs=[(1, "X", 7, False)]
        )
        assert list(axes.rule_2_11(_ctx(**stores))) == []

    def test_clean_with_whole_table_property(self) -> None:
        stores = _prop_header_stores(tv_property=9)
        assert list(axes.rule_2_11(_ctx(**stores))) == []

    def test_abstract_table_is_skipped(self) -> None:
        stores = _base_stores(_table(is_abstract=True), _tv())
        assert list(axes.rule_2_11(_ctx(**stores))) == []


class TestRule212:
    def test_fires_on_partially_covered_axis(self) -> None:
        stores = _prop_header_stores(
            header_specs=[
                (1, "X", 7, False),
                (2, "X", None, False),
            ]
        )
        findings = list(axes.rule_2_12(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].objects[0].id == 10
        assert findings[0].objects[1].kind == "axis"
        assert findings[0].objects[1].id == "X"

    def test_clean_when_axis_fully_covered(self) -> None:
        stores = _prop_header_stores(
            header_specs=[
                (1, "X", 7, False),
                (2, "X", 8, False),
                (3, "Y", None, False),
            ]
        )
        assert list(axes.rule_2_12(_ctx(**stores))) == []

    def test_abstract_table_is_skipped(self) -> None:
        stores = _base_stores(_table(is_abstract=True), _tv())
        assert list(axes.rule_2_12(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 2_13 (whole-table main property must be a metric)
# ------------------------------------------------------------------


def _prop(property_id: int = 7, *, is_metric: Any = False) -> PropertyRow:
    return PropertyRow(
        property_id=property_id,
        is_composite=None,
        is_metric=is_metric,
        data_type_id=None,
        period_type=None,
    )


def _ic(
    item_id: int = 7,
    *,
    code: Any = "pi7",
    end: Any = None,
    start: Any = PREV,
    signature: Any = None,
) -> ItemCategoryRow:
    return ItemCategoryRow(
        item_id=item_id,
        start_release_id=start,
        category_id=3,
        code=code,
        is_default_item=None,
        signature=signature,
        end_release_id=end,
    )


def _pc(
    property_id: int = 7,
    *,
    category_id: Any = 3,
    end: Any = None,
) -> PropertyCategoryRow:
    return PropertyCategoryRow(
        property_id=property_id,
        start_release_id=PREV,
        category_id=category_id,
        end_release_id=end,
    )


def _cat(category_id: int = 3, *, code: Any = "CAT") -> CategoryRow:
    return CategoryRow(
        category_id=category_id,
        code=code,
        name=None,
        is_enumerated=None,
        is_active=None,
        created_release_id=None,
    )


class TestRule213:
    def _stores(self, **overrides: List[Any]) -> dict:
        stores = _base_stores(
            _table(),
            _tv(property_id=7),
            properties=[_prop()],
            item_categories=[_ic()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        stores.update(overrides)
        return stores

    def test_fires_for_non_metric_whole_table_property(self) -> None:
        findings = list(axes.rule_2_13(_ctx(**self._stores())))
        assert len(findings) == 1
        tv_ref, prop_ref, cat_ref = findings[0].objects
        assert tv_ref.id == 10
        assert prop_ref.kind == "property"
        assert prop_ref.id == 7
        assert prop_ref.code == "pi7"
        assert cat_ref.kind == "category"
        assert cat_ref.id == 3
        assert cat_ref.code == "CAT"

    def test_clean_for_metric_property(self) -> None:
        stores = self._stores(properties=[_prop(is_metric=True)])
        assert list(axes.rule_2_13(_ctx(**stores))) == []

    def test_null_is_metric_is_skipped(self) -> None:
        stores = self._stores(properties=[_prop(is_metric=None)])
        assert list(axes.rule_2_13(_ctx(**stores))) == []

    def test_no_property_id_is_skipped(self) -> None:
        stores = self._stores()
        stores["table_versions"] = [_tv(property_id=None)]
        assert list(axes.rule_2_13(_ctx(**stores))) == []

    def test_missing_property_row_is_skipped(self) -> None:
        stores = self._stores(properties=[])
        assert list(axes.rule_2_13(_ctx(**stores))) == []

    def test_expired_property_category_is_skipped(self) -> None:
        stores = self._stores(property_categories=[_pc(end=CUR)])
        assert list(axes.rule_2_13(_ctx(**stores))) == []

    def test_null_category_id_is_skipped(self) -> None:
        stores = self._stores(
            property_categories=[_pc(category_id=None)]
        )
        assert list(axes.rule_2_13(_ctx(**stores))) == []

    def test_missing_category_is_skipped(self) -> None:
        stores = self._stores(categories=[])
        assert list(axes.rule_2_13(_ctx(**stores))) == []

    def test_duplicate_rows_are_deduplicated(self) -> None:
        stores = self._stores(
            item_categories=[_ic(), _ic(start=CUR)],
        )
        findings = list(axes.rule_2_13(_ctx(**stores)))
        assert len(findings) == 1
