"""Unit tests for the family-1 (lifecycle) model-validation rules."""

from typing import Any, List, Optional, Tuple

from dpmcore.services.model_validation.registry import (
    Finding,
    RuleContext,
)
from dpmcore.services.model_validation.release_context import (
    ReleaseContext,
)
from dpmcore.services.model_validation.rules import lifecycle
from dpmcore.services.model_validation.snapshot import (
    AuxCellMappingRow,
    CategoryRow,
    CellRow,
    ContextCompositionRow,
    HeaderRow,
    HeaderVersionRow,
    ItemCategoryRow,
    KeyHeaderMappingRow,
    ModelSnapshot,
    ModuleRow,
    ModuleVersionCompositionRow,
    ModuleVersionRow,
    PropertyCategoryRow,
    ReleaseRow,
    SubCategoryItemRow,
    TableAssociationRow,
    TableGroupCompositionRow,
    TableGroupRow,
    TableRow,
    TableVersionCellRow,
    TableVersionHeaderRow,
    TableVersionRow,
    VariableVersionRow,
)

CUR = 100
PREV = 50
DRAFT = 9999

REL = ReleaseContext(current_release_id=CUR, draft_release_id=DRAFT)
REL_NO_DRAFT = ReleaseContext(current_release_id=CUR)


def _ctx(
    rel: ReleaseContext = REL, **stores: List[Any]
) -> RuleContext:
    return RuleContext(
        snapshot=ModelSnapshot.from_rows(**stores), release=rel
    )


# ------------------------------------------------------------------
# Row builders
# ------------------------------------------------------------------


def _table(table_id: int = 1, *, is_abstract: Any = False) -> TableRow:
    return TableRow(
        table_id=table_id,
        is_abstract=is_abstract,
        has_open_columns=None,
        has_open_rows=None,
        has_open_sheets=None,
    )


def _open_table(
    table_id: int, *, rows: Any = False, cols: Any = False,
    sheets: Any = False,
) -> TableRow:
    return TableRow(
        table_id=table_id,
        is_abstract=False,
        has_open_columns=cols,
        has_open_rows=rows,
        has_open_sheets=sheets,
    )


def _tv(
    vid: int = 10,
    *,
    table_id: Any = 1,
    code: Any = "T1",
    name: Any = None,
    start: Any = CUR,
    end: Any = None,
    abstract_table_id: Any = None,
    key_id: Any = None,
    property_id: Any = None,
    context_id: Any = None,
) -> TableVersionRow:
    return TableVersionRow(
        table_vid=vid,
        code=code,
        name=name,
        table_id=table_id,
        abstract_table_id=abstract_table_id,
        key_id=key_id,
        property_id=property_id,
        context_id=context_id,
        start_release_id=start,
        end_release_id=end,
    )


def _module(
    module_id: int = 1, *, is_document: Any = False
) -> ModuleRow:
    return ModuleRow(
        module_id=module_id,
        framework_id=None,
        is_document_module=is_document,
    )


def _mv(
    vid: int = 500,
    *,
    module_id: Any = 1,
    code: Any = "MOD",
    start: Any = CUR,
    end: Any = None,
    version: Any = None,
) -> ModuleVersionRow:
    return ModuleVersionRow(
        module_vid=vid,
        module_id=module_id,
        global_key_id=None,
        start_release_id=start,
        end_release_id=end,
        code=code,
        name=None,
        version_number=version,
        is_reported=None,
        is_calculated=None,
    )


def _mvc(
    module_vid: int = 500,
    *,
    table_id: int = 1,
    table_vid: Any = 10,
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
    code: Any = "010",
    label: Any = None,
    property_id: Any = None,
    context_id: Any = None,
    subcategory_vid: Any = None,
    start: Any = CUR,
    end: Any = None,
) -> HeaderVersionRow:
    return HeaderVersionRow(
        header_vid=vid,
        header_id=header_id,
        code=code,
        label=label,
        property_id=property_id,
        context_id=context_id,
        subcategory_vid=subcategory_vid,
        key_variable_vid=None,
        start_release_id=start,
        end_release_id=end,
    )


def _tvh(
    table_vid: int = 10,
    header_id: int = 1,
    *,
    header_vid: Any = None,
    parent_header_id: Any = None,
    order: Any = None,
    is_abstract: Any = False,
    is_unique: Any = None,
) -> TableVersionHeaderRow:
    return TableVersionHeaderRow(
        table_vid=table_vid,
        header_id=header_id,
        header_vid=header_vid,
        parent_header_id=parent_header_id,
        parent_first=None,
        order=order,
        is_abstract=is_abstract,
        is_unique=is_unique,
    )


def _tvc(
    table_vid: int = 10,
    cell_id: int = 1,
    *,
    cell_code: Any = None,
    nullable: Any = None,
    excluded: Any = None,
    void: Any = None,
    sign: Any = None,
    variable_vid: Any = None,
) -> TableVersionCellRow:
    return TableVersionCellRow(
        table_vid=table_vid,
        cell_id=cell_id,
        cell_code=cell_code,
        is_nullable=nullable,
        is_excluded=excluded,
        is_void=void,
        sign=sign,
        variable_vid=variable_vid,
    )


def _cell(cell_id: int = 1) -> CellRow:
    return CellRow(
        cell_id=cell_id,
        table_id=1,
        column_id=None,
        row_id=None,
        sheet_id=None,
    )


def _tg(
    group_id: int = 30,
    *,
    code: Any = "TG",
    type_: Any = "templateGroup",
    start: Any = PREV,
    end: Any = None,
) -> TableGroupRow:
    return TableGroupRow(
        table_group_id=group_id,
        code=code,
        name=None,
        type=type_,
        start_release_id=start,
        end_release_id=end,
        parent_table_group_id=None,
    )


def _tgc(
    group_id: int = 30,
    table_id: int = 1,
    *,
    start: Any = PREV,
    end: Any = None,
) -> TableGroupCompositionRow:
    return TableGroupCompositionRow(
        table_group_id=group_id,
        table_id=table_id,
        order=None,
        start_release_id=start,
        end_release_id=end,
    )


def _ta(
    assoc_id: int = 900,
    *,
    parent: Any = 10,
    child: Any = 20,
    name: Any = "A1",
) -> TableAssociationRow:
    return TableAssociationRow(
        association_id=assoc_id,
        child_table_vid=child,
        parent_table_vid=parent,
        name=name,
        is_identifying=None,
        is_subtype=None,
        subtype_discriminator=None,
    )


def _khm(
    assoc_id: int = 900, *, fk: int = 2, pk: Any = 1
) -> KeyHeaderMappingRow:
    return KeyHeaderMappingRow(
        association_id=assoc_id,
        foreign_key_header_id=fk,
        primary_key_header_id=pk,
    )


def _ic(
    item_id: int = 7,
    *,
    start: Any = PREV,
    end: Any = None,
    category_id: Any = 3,
    code: Any = "pi7",
    signature: Any = "sig7",
) -> ItemCategoryRow:
    return ItemCategoryRow(
        item_id=item_id,
        start_release_id=start,
        category_id=category_id,
        code=code,
        is_default_item=None,
        signature=signature,
        end_release_id=end,
    )


def _pc(
    property_id: int = 7,
    *,
    start: Any = PREV,
    end: Any = None,
    category_id: Any = 3,
) -> PropertyCategoryRow:
    return PropertyCategoryRow(
        property_id=property_id,
        start_release_id=start,
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


def _cc(
    context_id: int = 40,
    property_id: int = 7,
    *,
    item_id: Any = None,
) -> ContextCompositionRow:
    return ContextCompositionRow(
        context_id=context_id,
        property_id=property_id,
        item_id=item_id,
    )


def _sci(item_id: int = 8, scv: int = 60) -> SubCategoryItemRow:
    return SubCategoryItemRow(
        item_id=item_id,
        subcategory_vid=scv,
        order=None,
        label=None,
        parent_item_id=None,
    )


def _vv(
    vid: int = 200,
    *,
    property_id: Any = None,
    context_id: Any = None,
) -> VariableVersionRow:
    return VariableVersionRow(
        variable_vid=vid,
        variable_id=None,
        property_id=property_id,
        subcategory_vid=None,
        context_id=context_id,
        key_id=None,
        is_multi_valued=None,
        code=None,
        name=None,
        start_release_id=PREV,
        end_release_id=None,
    )


def _release(release_id: int = CUR, *, code: Any = "3.0") -> ReleaseRow:
    return ReleaseRow(
        release_id=release_id,
        code=code,
        status=None,
        is_current=None,
        type=None,
    )


def _acm(new_vid: int = 10, old_vid: Any = 20) -> AuxCellMappingRow:
    return AuxCellMappingRow(
        new_cell_id=1,
        new_table_vid=new_vid,
        old_cell_id=None,
        old_table_vid=old_vid,
    )


def _base_stores(**extra: List[Any]) -> dict:
    """Table 1 with open tv 10, composed into new module version."""
    stores: dict = {
        "tables": [_table()],
        "table_versions": [_tv()],
        "modules": [_module()],
        "module_versions": [_mv()],
        "module_version_compositions": [_mvc()],
    }
    stores.update(extra)
    return stores


def _ids(findings: List[Finding]) -> List[Tuple[Any, ...]]:
    return [tuple(o.id for o in f.objects) for f in findings]


# ------------------------------------------------------------------
# 1_1 — header version identical to previous version
# ------------------------------------------------------------------


class TestRule11:
    def _stores(
        self,
        new: HeaderVersionRow,
        old: HeaderVersionRow,
        *,
        header: Optional[HeaderRow] = None,
        tvh: Optional[TableVersionHeaderRow] = None,
    ) -> dict:
        return _base_stores(
            headers=[header if header is not None else _header()],
            header_versions=[new, old],
            table_version_headers=[
                tvh if tvh is not None else _tvh()
            ],
        )

    def test_fires_on_identical_versions(self) -> None:
        stores = self._stores(
            _hv(101, start=CUR), _hv(100, start=PREV, end=CUR)
        )
        findings = list(lifecycle.rule_1_1(_ctx(**stores)))
        assert _ids(findings) == [(101, 100, 10)]
        assert findings[0].objects[0].kind == "header_version"

    def test_clean_when_fields_differ(self) -> None:
        stores = self._stores(
            _hv(101, start=CUR),
            _hv(100, start=PREV, end=CUR, code="020"),
        )
        assert list(lifecycle.rule_1_1(_ctx(**stores))) == []

    def test_clean_when_old_end_mismatches(self) -> None:
        stores = self._stores(
            _hv(101, start=CUR), _hv(100, start=PREV, end=PREV)
        )
        assert list(lifecycle.rule_1_1(_ctx(**stores))) == []

    def test_abstract_tvh_is_skipped(self) -> None:
        stores = self._stores(
            _hv(101, start=CUR),
            _hv(100, start=PREV, end=CUR),
            tvh=_tvh(is_abstract=True),
        )
        assert list(lifecycle.rule_1_1(_ctx(**stores))) == []

    def test_key_header_is_skipped(self) -> None:
        stores = self._stores(
            _hv(101, start=CUR),
            _hv(100, start=PREV, end=CUR),
            header=_header(is_key=True),
        )
        assert list(lifecycle.rule_1_1(_ctx(**stores))) == []

    def test_header_of_other_table_is_skipped(self) -> None:
        stores = self._stores(
            _hv(101, start=CUR),
            _hv(100, start=PREV, end=CUR),
            header=_header(table_id=2),
        )
        assert list(lifecycle.rule_1_1(_ctx(**stores))) == []

    def test_dangling_header_is_skipped(self) -> None:
        stores = self._stores(
            _hv(101, start=CUR), _hv(100, start=PREV, end=CUR)
        )
        stores["headers"] = []
        assert list(lifecycle.rule_1_1(_ctx(**stores))) == []

    def test_abstract_table_is_skipped(self) -> None:
        stores = self._stores(
            _hv(101, start=CUR), _hv(100, start=PREV, end=CUR)
        )
        stores["tables"] = [_table(is_abstract=True)]
        assert list(lifecycle.rule_1_1(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_2 — table version identical to previous version
# ------------------------------------------------------------------


class TestRule12:
    def _stores(self, old: TableVersionRow, **extra: Any) -> dict:
        stores = _base_stores(**extra)
        stores["table_versions"] = [_tv(), old]
        return stores

    def test_fires_on_identical_scalars(self) -> None:
        stores = self._stores(_tv(11, start=PREV, end=CUR))
        findings = list(lifecycle.rule_1_2(_ctx(**stores)))
        assert _ids(findings) == [(10, 11)]

    def test_clean_when_scalars_differ(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR, code="T2")
        )
        assert list(lifecycle.rule_1_2(_ctx(**stores))) == []

    def test_clean_when_old_end_mismatches(self) -> None:
        stores = self._stores(_tv(11, start=PREV, end=PREV))
        assert list(lifecycle.rule_1_2(_ctx(**stores))) == []

    def test_abstract_table_is_skipped(self) -> None:
        stores = self._stores(_tv(11, start=PREV, end=CUR))
        stores["tables"] = [_table(is_abstract=True)]
        assert list(lifecycle.rule_1_2(_ctx(**stores))) == []

    def test_fires_with_identical_headers_and_cells(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR),
            headers=[_header()],
            header_versions=[_hv(100, start=PREV)],
            table_version_headers=[
                _tvh(10, 1, header_vid=100),
                _tvh(11, 1, header_vid=100),
            ],
            cells=[_cell()],
            table_version_cells=[
                _tvc(10, 1, cell_code="C1"),
                _tvc(11, 1, cell_code="C1"),
            ],
        )
        assert _ids(list(lifecycle.rule_1_2(_ctx(**stores)))) == [
            (10, 11)
        ]

    def test_clean_when_header_counts_differ(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR),
            headers=[_header()],
            header_versions=[_hv(100)],
            table_version_headers=[_tvh(10, 1, header_vid=100)],
        )
        assert list(lifecycle.rule_1_2(_ctx(**stores))) == []

    def test_clean_when_header_version_differs(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR),
            headers=[_header()],
            header_versions=[
                _hv(100, start=PREV, end=CUR),
                _hv(101, start=CUR),
            ],
            table_version_headers=[
                _tvh(10, 1, header_vid=101),
                _tvh(11, 1, header_vid=100),
            ],
        )
        assert list(lifecycle.rule_1_2(_ctx(**stores))) == []

    def test_clean_when_old_lacks_the_header(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR),
            headers=[_header(1), _header(2)],
            header_versions=[_hv(100, header_id=1)],
            table_version_headers=[
                _tvh(10, 1, header_vid=100),
                _tvh(11, 2, header_vid=None),
            ],
        )
        assert list(lifecycle.rule_1_2(_ctx(**stores))) == []

    def test_new_tvh_without_header_version_is_ignored(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR),
            table_version_headers=[
                _tvh(10, 1, header_vid=None),
                _tvh(11, 1, header_vid=None),
            ],
        )
        assert _ids(list(lifecycle.rule_1_2(_ctx(**stores)))) == [
            (10, 11)
        ]

    def test_clean_when_tvh_bits_differ(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR),
            headers=[_header()],
            header_versions=[_hv(100, start=PREV)],
            table_version_headers=[
                _tvh(10, 1, header_vid=100, is_unique=True),
                _tvh(11, 1, header_vid=100, is_unique=False),
            ],
        )
        assert list(lifecycle.rule_1_2(_ctx(**stores))) == []

    def test_dangling_old_header_version_differs(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR),
            headers=[_header()],
            header_versions=[_hv(100, start=PREV)],
            table_version_headers=[
                _tvh(10, 1, header_vid=100),
                _tvh(11, 1, header_vid=999),
            ],
        )
        assert list(lifecycle.rule_1_2(_ctx(**stores))) == []

    def test_clean_when_cell_counts_differ(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR),
            cells=[_cell()],
            table_version_cells=[_tvc(10, 1)],
        )
        assert list(lifecycle.rule_1_2(_ctx(**stores))) == []

    def test_clean_when_cell_code_differs(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR),
            cells=[_cell()],
            table_version_cells=[
                _tvc(10, 1, cell_code="A"),
                _tvc(11, 1, cell_code="B"),
            ],
        )
        assert list(lifecycle.rule_1_2(_ctx(**stores))) == []

    def test_clean_when_cell_bits_differ(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR),
            cells=[_cell()],
            table_version_cells=[
                _tvc(10, 1, void=True),
                _tvc(11, 1, void=False),
            ],
        )
        assert list(lifecycle.rule_1_2(_ctx(**stores))) == []

    def test_unknown_cells_are_ignored(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR),
            table_version_cells=[
                _tvc(10, 1, cell_code="A"),
                _tvc(11, 1, cell_code="B"),
            ],
        )
        assert _ids(list(lifecycle.rule_1_2(_ctx(**stores)))) == [
            (10, 11)
        ]

    def test_disjoint_cells_are_ignored(self) -> None:
        stores = self._stores(
            _tv(11, start=PREV, end=CUR),
            cells=[_cell(1), _cell(2)],
            table_version_cells=[
                _tvc(10, 1, cell_code="A"),
                _tvc(11, 2, cell_code="B"),
            ],
        )
        assert _ids(list(lifecycle.rule_1_2(_ctx(**stores)))) == [
            (10, 11)
        ]


# ------------------------------------------------------------------
# 1_3 — abstract table missing from module composition
# ------------------------------------------------------------------


class TestRule13:
    def test_fires_when_abstract_table_absent(self) -> None:
        stores = _base_stores()
        stores["table_versions"] = [_tv(abstract_table_id=2)]
        findings = list(lifecycle.rule_1_3(_ctx(**stores)))
        assert _ids(findings) == [(10, 500)]
        assert findings[0].objects[1].kind == "module_version"

    def test_clean_when_abstract_table_present(self) -> None:
        stores = _base_stores()
        stores["tables"] = [_table(), _table(2, is_abstract=True)]
        stores["table_versions"] = [
            _tv(abstract_table_id=2),
            _tv(20, table_id=2),
        ]
        stores["module_version_compositions"] = [
            _mvc(),
            _mvc(table_id=2, table_vid=20),
        ]
        assert list(lifecycle.rule_1_3(_ctx(**stores))) == []

    def test_old_module_version_is_skipped(self) -> None:
        stores = _base_stores()
        stores["table_versions"] = [_tv(abstract_table_id=2)]
        stores["module_versions"] = [_mv(start=PREV)]
        assert list(lifecycle.rule_1_3(_ctx(**stores))) == []

    def test_null_abstract_table_is_skipped(self) -> None:
        assert list(lifecycle.rule_1_3(_ctx(**_base_stores()))) == []

    def test_abstract_table_version_is_skipped(self) -> None:
        stores = _base_stores()
        stores["tables"] = [_table(is_abstract=True)]
        stores["table_versions"] = [_tv(abstract_table_id=2)]
        assert list(lifecycle.rule_1_3(_ctx(**stores))) == []

    def test_missing_table_is_skipped(self) -> None:
        stores = _base_stores()
        stores["tables"] = []
        stores["table_versions"] = [_tv(abstract_table_id=2)]
        assert list(lifecycle.rule_1_3(_ctx(**stores))) == []

    def test_null_table_id_is_skipped(self) -> None:
        stores = _base_stores()
        stores["table_versions"] = [
            _tv(abstract_table_id=2, table_id=None)
        ]
        assert list(lifecycle.rule_1_3(_ctx(**stores))) == []

    def test_dangling_table_vid_is_skipped(self) -> None:
        stores = _base_stores()
        stores["table_versions"] = []
        assert list(lifecycle.rule_1_3(_ctx(**stores))) == []

    def test_null_table_vid_is_skipped(self) -> None:
        stores = _base_stores()
        stores["module_version_compositions"] = [
            _mvc(table_vid=None)
        ]
        assert list(lifecycle.rule_1_3(_ctx(**stores))) == []

    def test_dangling_module_vid_is_skipped(self) -> None:
        stores = _base_stores()
        stores["table_versions"] = [_tv(abstract_table_id=2)]
        stores["module_versions"] = []
        assert list(lifecycle.rule_1_3(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_4 — abstract table without technical table
# ------------------------------------------------------------------


class TestRule14:
    def _stores(self) -> dict:
        stores = _base_stores()
        stores["tables"] = [_table(is_abstract=True)]
        return stores

    def test_fires_without_technical_table(self) -> None:
        findings = list(lifecycle.rule_1_4(_ctx(**self._stores())))
        assert _ids(findings) == [(10, 500)]

    def test_clean_with_technical_table(self) -> None:
        stores = self._stores()
        stores["tables"] = [
            _table(is_abstract=True),
            _table(2),
        ]
        stores["table_versions"] = [
            _tv(),
            _tv(20, table_id=2, abstract_table_id=1),
        ]
        stores["module_version_compositions"] = [
            _mvc(),
            _mvc(table_id=2, table_vid=20),
        ]
        assert list(lifecycle.rule_1_4(_ctx(**stores))) == []

    def test_null_abstract_id_suppresses(self) -> None:
        stores = self._stores()
        stores["tables"] = [_table(is_abstract=True), _table(2)]
        stores["table_versions"] = [
            _tv(),
            _tv(20, table_id=2, abstract_table_id=None),
        ]
        stores["module_version_compositions"] = [
            _mvc(),
            _mvc(table_id=2, table_vid=20),
        ]
        assert list(lifecycle.rule_1_4(_ctx(**stores))) == []

    def test_non_abstract_table_is_skipped(self) -> None:
        assert list(lifecycle.rule_1_4(_ctx(**_base_stores()))) == []

    def test_old_module_version_is_skipped(self) -> None:
        stores = self._stores()
        stores["module_versions"] = [_mv(start=PREV)]
        assert list(lifecycle.rule_1_4(_ctx(**stores))) == []

    def test_dangling_module_vid_is_skipped(self) -> None:
        stores = self._stores()
        stores["module_versions"] = []
        assert list(lifecycle.rule_1_4(_ctx(**stores))) == []

    def test_null_table_vid_rows_are_skipped(self) -> None:
        stores = self._stores()
        stores["module_version_compositions"] = [
            _mvc(),
            _mvc(table_vid=None, table_id=9),
        ]
        assert _ids(list(lifecycle.rule_1_4(_ctx(**stores)))) == [
            (10, 500)
        ]

    def test_null_table_id_tv_is_skipped(self) -> None:
        stores = self._stores()
        stores["table_versions"] = [_tv(table_id=None)]
        assert list(lifecycle.rule_1_4(_ctx(**stores))) == []

    def test_abstract_sibling_does_not_provide_id(self) -> None:
        stores = self._stores()
        stores["tables"] = [
            _table(is_abstract=True),
            _table(2, is_abstract=True),
        ]
        stores["table_versions"] = [
            _tv(),
            _tv(20, table_id=2, abstract_table_id=1),
        ]
        stores["module_version_compositions"] = [
            _mvc(),
            _mvc(table_id=2, table_vid=20),
        ]
        assert len(list(lifecycle.rule_1_4(_ctx(**stores)))) == 2

    def test_missing_sibling_table_is_skipped(self) -> None:
        stores = self._stores()
        stores["table_versions"] = [
            _tv(),
            _tv(20, table_id=2, abstract_table_id=1),
        ]
        stores["module_version_compositions"] = [
            _mvc(),
            _mvc(table_id=2, table_vid=20),
        ]
        assert _ids(list(lifecycle.rule_1_4(_ctx(**stores)))) == [
            (10, 500)
        ]

    def test_dangling_sibling_tv_is_skipped(self) -> None:
        stores = self._stores()
        stores["module_version_compositions"] = [
            _mvc(),
            _mvc(table_id=2, table_vid=99),
        ]
        assert _ids(list(lifecycle.rule_1_4(_ctx(**stores)))) == [
            (10, 500)
        ]


# ------------------------------------------------------------------
# 1_5 — duplicate table code
# ------------------------------------------------------------------


class TestRule15:
    def _stores(self, other: TableVersionRow) -> dict:
        stores = _base_stores()
        stores["tables"] = [_table(), _table(2)]
        stores["table_versions"] = [_tv(code=" T1 "), other]
        stores["module_versions"] = [_mv(), _mv(501)]
        stores["module_version_compositions"] = [
            _mvc(),
            _mvc(501, table_id=2, table_vid=20),
        ]
        return stores

    def test_fires_on_duplicate_code(self) -> None:
        stores = self._stores(_tv(20, table_id=2, code="T1"))
        findings = list(lifecycle.rule_1_5(_ctx(**stores)))
        assert _ids(findings) == [(10,), (20,)]

    def test_clean_when_same_table(self) -> None:
        stores = self._stores(_tv(20, table_id=1, code="T1"))
        stores["module_version_compositions"][1] = _mvc(
            501, table_id=1, table_vid=20
        )
        assert list(lifecycle.rule_1_5(_ctx(**stores))) == []

    def test_clean_when_codes_differ(self) -> None:
        stores = self._stores(_tv(20, table_id=2, code="T2"))
        assert list(lifecycle.rule_1_5(_ctx(**stores))) == []

    def test_draft_only_module_counterpart_is_excluded(self) -> None:
        # mv 501 (draft start, open) is excluded from the counterpart
        # subquery, so tv 10 stays clean; but the OUTER membership
        # check only requires an open module version, so tv 20 still
        # fires against the counterpart tv 10 in the active mv 500.
        stores = self._stores(_tv(20, table_id=2, code="T1"))
        stores["module_versions"] = [_mv(), _mv(501, start=DRAFT)]
        assert _ids(list(lifecycle.rule_1_5(_ctx(**stores)))) == [
            (20,)
        ]

    def test_draft_closed_module_is_included(self) -> None:
        stores = self._stores(_tv(20, table_id=2, code="T1"))
        stores["module_versions"] = [
            _mv(),
            _mv(501, start=PREV, end=DRAFT),
        ]
        assert _ids(list(lifecycle.rule_1_5(_ctx(**stores)))) == [
            (10,)
        ]

    def test_expired_tv_is_skipped_as_outer(self) -> None:
        # tv 10 expired: it can no longer FIRE, but the SQL counterpart
        # subquery has no expiry filter on tv2, so tv 20 still fires
        # against the expired tv 10 in the active mv 500.
        stores = self._stores(_tv(20, table_id=2, code="T1"))
        stores["table_versions"][0] = _tv(code="T1", end=CUR)
        assert _ids(list(lifecycle.rule_1_5(_ctx(**stores)))) == [
            (20,)
        ]

    def test_old_start_is_skipped(self) -> None:
        stores = self._stores(
            _tv(20, table_id=2, code="T1", start=PREV)
        )
        findings = list(lifecycle.rule_1_5(_ctx(**stores)))
        assert _ids(findings) == [(10,)]

    def test_null_code_is_skipped(self) -> None:
        stores = self._stores(_tv(20, table_id=2, code=None))
        stores["table_versions"][0] = _tv(code=None)
        assert list(lifecycle.rule_1_5(_ctx(**stores))) == []

    def test_closed_module_membership_is_skipped(self) -> None:
        stores = self._stores(_tv(20, table_id=2, code="T1"))
        stores["module_versions"] = [
            _mv(end=PREV),
            _mv(501, start=PREV, end=DRAFT),
        ]
        assert list(lifecycle.rule_1_5(_ctx(**stores))) == []

    def test_dangling_rows_are_skipped(self) -> None:
        stores = self._stores(_tv(20, table_id=2, code="T1"))
        stores["module_version_compositions"].append(
            _mvc(999, table_id=9, table_vid=None)
        )
        stores["module_version_compositions"].append(
            _mvc(501, table_id=9, table_vid=999)
        )
        stores["table_versions"].append(
            _tv(30, table_id=None, code="T1", start=PREV)
        )
        stores["module_version_compositions"].append(
            _mvc(501, table_id=9, table_vid=30)
        )
        assert _ids(list(lifecycle.rule_1_5(_ctx(**stores)))) == [
            (10,),
            (20,),
        ]


# ------------------------------------------------------------------
# 1_6 — abstract table in a table group
# ------------------------------------------------------------------


class TestRule16:
    def _stores(self, **overrides: Any) -> dict:
        stores = _base_stores(
            table_groups=[_tg()],
            table_group_compositions=[_tgc(start=CUR)],
        )
        stores["tables"] = [_table(is_abstract=True)]
        stores.update(overrides)
        return stores

    def test_fires_for_abstract_table_in_group(self) -> None:
        findings = list(lifecycle.rule_1_6(_ctx(**self._stores())))
        assert _ids(findings) == [(10, 30)]
        assert findings[0].objects[1].kind == "table_group"

    def test_clean_for_non_abstract_table(self) -> None:
        stores = self._stores()
        stores["tables"] = [_table()]
        assert list(lifecycle.rule_1_6(_ctx(**stores))) == []

    def test_old_composition_is_skipped(self) -> None:
        stores = self._stores(
            table_group_compositions=[_tgc(start=PREV)]
        )
        assert list(lifecycle.rule_1_6(_ctx(**stores))) == []

    def test_closed_composition_is_skipped(self) -> None:
        stores = self._stores(
            table_group_compositions=[_tgc(start=CUR, end=CUR)]
        )
        assert list(lifecycle.rule_1_6(_ctx(**stores))) == []

    def test_missing_group_is_skipped(self) -> None:
        stores = self._stores(table_groups=[])
        assert list(lifecycle.rule_1_6(_ctx(**stores))) == []

    def test_expired_tv_is_skipped(self) -> None:
        stores = self._stores()
        stores["table_versions"] = [_tv(end=CUR)]
        assert list(lifecycle.rule_1_6(_ctx(**stores))) == []

    def test_tv_outside_modules_is_skipped(self) -> None:
        stores = self._stores()
        stores["module_version_compositions"] = []
        assert list(lifecycle.rule_1_6(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_7 — expired table version in new module version
# ------------------------------------------------------------------


class TestRule17:
    def _stores(self, tv: TableVersionRow) -> dict:
        stores = _base_stores(releases=[_release()])
        stores["table_versions"] = [tv]
        return stores

    def test_fires_for_expired_tv(self) -> None:
        stores = self._stores(_tv(start=PREV, end=PREV))
        findings = list(lifecycle.rule_1_7(_ctx(**stores)))
        assert _ids(findings) == [(10, 500)]
        assert findings[0].message is not None
        assert "StartRelease=3.0" in findings[0].message

    def test_fires_for_draft_started_tv(self) -> None:
        stores = self._stores(_tv(start=DRAFT))
        assert _ids(list(lifecycle.rule_1_7(_ctx(**stores)))) == [
            (10, 500)
        ]

    def test_clean_for_open_tv(self) -> None:
        stores = self._stores(_tv(start=PREV))
        assert list(lifecycle.rule_1_7(_ctx(**stores))) == []

    def test_old_module_version_is_skipped(self) -> None:
        stores = self._stores(_tv(start=PREV, end=PREV))
        stores["module_versions"] = [_mv(start=PREV)]
        assert list(lifecycle.rule_1_7(_ctx(**stores))) == []

    def test_missing_release_is_skipped(self) -> None:
        stores = self._stores(_tv(start=PREV, end=PREV))
        stores["releases"] = []
        assert list(lifecycle.rule_1_7(_ctx(**stores))) == []

    def test_dangling_table_vid_is_skipped(self) -> None:
        stores = self._stores(_tv(99, start=PREV, end=PREV))
        assert list(lifecycle.rule_1_7(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_8 — new module version without composition
# ------------------------------------------------------------------


class TestRule18:
    def test_fires_for_empty_composition(self) -> None:
        stores = _base_stores()
        stores["module_version_compositions"] = []
        findings = list(lifecycle.rule_1_8(_ctx(**stores)))
        assert _ids(findings) == [(500,)]
        assert findings[0].objects[0].kind == "module_version"

    def test_clean_with_composition(self) -> None:
        assert list(lifecycle.rule_1_8(_ctx(**_base_stores()))) == []

    def test_document_module_is_skipped(self) -> None:
        stores = _base_stores()
        stores["module_version_compositions"] = []
        stores["modules"] = [_module(is_document=True)]
        assert list(lifecycle.rule_1_8(_ctx(**stores))) == []

    def test_null_document_flag_is_skipped(self) -> None:
        stores = _base_stores()
        stores["module_version_compositions"] = []
        stores["modules"] = [_module(is_document=None)]
        assert list(lifecycle.rule_1_8(_ctx(**stores))) == []

    def test_missing_module_is_skipped(self) -> None:
        stores = _base_stores()
        stores["module_version_compositions"] = []
        stores["modules"] = []
        assert list(lifecycle.rule_1_8(_ctx(**stores))) == []

    def test_null_module_id_is_skipped(self) -> None:
        stores = _base_stores()
        stores["module_version_compositions"] = []
        stores["module_versions"] = [_mv(module_id=None)]
        assert list(lifecycle.rule_1_8(_ctx(**stores))) == []

    def test_old_module_version_is_skipped(self) -> None:
        stores = _base_stores()
        stores["module_version_compositions"] = []
        stores["module_versions"] = [_mv(start=PREV)]
        assert list(lifecycle.rule_1_8(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_9 — module composition identical to previous version
# ------------------------------------------------------------------


class TestRule19:
    def _stores(
        self,
        new_rows: List[ModuleVersionCompositionRow],
        old_rows: List[ModuleVersionCompositionRow],
        *,
        old_mv: Optional[ModuleVersionRow] = None,
    ) -> dict:
        old = (
            old_mv
            if old_mv is not None
            else _mv(499, start=PREV, end=CUR)
        )
        return {
            "modules": [_module()],
            "module_versions": [_mv(), old],
            "module_version_compositions": new_rows + old_rows,
        }

    def test_fires_on_identical_composition(self) -> None:
        stores = self._stores([_mvc(500)], [_mvc(499)])
        findings = list(lifecycle.rule_1_9(_ctx(**stores)))
        assert _ids(findings) == [(500,)]

    def test_clean_when_new_table_added(self) -> None:
        stores = self._stores(
            [_mvc(500), _mvc(500, table_id=2, table_vid=20)],
            [_mvc(499)],
        )
        assert list(lifecycle.rule_1_9(_ctx(**stores))) == []

    def test_clean_when_table_removed(self) -> None:
        stores = self._stores(
            [_mvc(500)],
            [_mvc(499), _mvc(499, table_id=2, table_vid=20)],
        )
        assert list(lifecycle.rule_1_9(_ctx(**stores))) == []

    def test_clean_without_prior_version(self) -> None:
        stores = self._stores([_mvc(500)], [])
        stores["module_versions"] = [_mv()]
        assert list(lifecycle.rule_1_9(_ctx(**stores))) == []

    def test_draft_only_sibling_does_not_count(self) -> None:
        stores = self._stores(
            [_mvc(500)],
            [_mvc(499)],
            old_mv=_mv(499, start=DRAFT),
        )
        assert list(lifecycle.rule_1_9(_ctx(**stores))) == []

    def test_null_vid_in_old_composition_suppresses(self) -> None:
        stores = self._stores(
            [_mvc(500), _mvc(500, table_id=2, table_vid=20)],
            [_mvc(499), _mvc(499, table_id=2, table_vid=None)],
        )
        assert _ids(list(lifecycle.rule_1_9(_ctx(**stores)))) == [
            (500,)
        ]

    def test_null_vid_in_new_composition_suppresses(self) -> None:
        stores = self._stores(
            [_mvc(500), _mvc(500, table_id=2, table_vid=None)],
            [_mvc(499), _mvc(499, table_id=2, table_vid=20)],
        )
        assert _ids(list(lifecycle.rule_1_9(_ctx(**stores)))) == [
            (500,)
        ]

    def test_document_module_is_skipped(self) -> None:
        stores = self._stores([_mvc(500)], [_mvc(499)])
        stores["modules"] = [_module(is_document=True)]
        assert list(lifecycle.rule_1_9(_ctx(**stores))) == []

    def test_null_module_id_is_skipped(self) -> None:
        stores = self._stores([_mvc(500)], [_mvc(499)])
        stores["module_versions"][0] = _mv(module_id=None)
        assert list(lifecycle.rule_1_9(_ctx(**stores))) == []

    def test_old_start_is_skipped(self) -> None:
        stores = self._stores([_mvc(500)], [_mvc(499)])
        stores["module_versions"][0] = _mv(start=PREV)
        assert list(lifecycle.rule_1_9(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_10 — table in group without module assignment
# ------------------------------------------------------------------


class TestRule110:
    def _stores(self, **overrides: Any) -> dict:
        stores: dict = {
            "tables": [_table()],
            "table_versions": [_tv()],
            "table_groups": [_tg()],
            "table_group_compositions": [_tgc(start=CUR)],
        }
        stores.update(overrides)
        return stores

    def test_fires_for_unassigned_table(self) -> None:
        findings = list(
            lifecycle.rule_1_10(_ctx(**self._stores()))
        )
        assert _ids(findings) == [(10, 30)]

    def test_clean_for_assigned_table(self) -> None:
        stores = self._stores(
            module_versions=[_mv()],
            module_version_compositions=[_mvc()],
        )
        assert list(lifecycle.rule_1_10(_ctx(**stores))) == []

    def test_draft_closed_module_counts_as_open(self) -> None:
        stores = self._stores(
            module_versions=[_mv(start=PREV, end=DRAFT)],
            module_version_compositions=[_mvc()],
        )
        assert list(lifecycle.rule_1_10(_ctx(**stores))) == []

    def test_closed_module_does_not_count(self) -> None:
        stores = self._stores(
            module_versions=[_mv(start=PREV, end=PREV)],
            module_version_compositions=[_mvc()],
        )
        assert _ids(list(lifecycle.rule_1_10(_ctx(**stores)))) == [
            (10, 30)
        ]

    def test_dangling_module_does_not_count(self) -> None:
        stores = self._stores(
            module_version_compositions=[_mvc(999)],
        )
        assert _ids(list(lifecycle.rule_1_10(_ctx(**stores)))) == [
            (10, 30)
        ]

    def test_old_composition_is_skipped(self) -> None:
        stores = self._stores(
            table_group_compositions=[_tgc(start=PREV)]
        )
        assert list(lifecycle.rule_1_10(_ctx(**stores))) == []

    def test_closed_composition_is_skipped(self) -> None:
        stores = self._stores(
            table_group_compositions=[_tgc(start=CUR, end=CUR)]
        )
        assert list(lifecycle.rule_1_10(_ctx(**stores))) == []

    def test_missing_group_is_skipped(self) -> None:
        stores = self._stores(table_groups=[])
        assert list(lifecycle.rule_1_10(_ctx(**stores))) == []

    def test_missing_table_is_skipped(self) -> None:
        stores = self._stores(tables=[])
        assert list(lifecycle.rule_1_10(_ctx(**stores))) == []

    def test_expired_tv_is_skipped(self) -> None:
        stores = self._stores(table_versions=[_tv(end=CUR)])
        assert list(lifecycle.rule_1_10(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_11 — table not in exactly one template group
# ------------------------------------------------------------------


class TestRule111:
    def test_fires_without_template_group(self) -> None:
        findings = list(
            lifecycle.rule_1_11(_ctx(**_base_stores()))
        )
        assert _ids(findings) == [(10,)]

    def test_fires_with_two_template_groups(self) -> None:
        stores = _base_stores(
            table_groups=[_tg(30), _tg(31)],
            table_group_compositions=[_tgc(30), _tgc(31)],
        )
        assert _ids(list(lifecycle.rule_1_11(_ctx(**stores)))) == [
            (10,)
        ]

    def test_clean_with_one_template_group(self) -> None:
        stores = _base_stores(
            table_groups=[_tg()],
            table_group_compositions=[_tgc()],
        )
        assert list(lifecycle.rule_1_11(_ctx(**stores))) == []

    def test_abstract_table_is_skipped(self) -> None:
        stores = _base_stores()
        stores["tables"] = [_table(is_abstract=True)]
        assert list(lifecycle.rule_1_11(_ctx(**stores))) == []

    def test_closed_composition_does_not_count(self) -> None:
        stores = _base_stores(
            table_groups=[_tg()],
            table_group_compositions=[_tgc(end=PREV)],
        )
        assert _ids(list(lifecycle.rule_1_11(_ctx(**stores)))) == [
            (10,)
        ]

    def test_non_template_group_does_not_count(self) -> None:
        stores = _base_stores(
            table_groups=[_tg(type_="other")],
            table_group_compositions=[_tgc()],
        )
        assert _ids(list(lifecycle.rule_1_11(_ctx(**stores)))) == [
            (10,)
        ]

    def test_draft_group_does_not_count(self) -> None:
        stores = _base_stores(
            table_groups=[_tg(start=DRAFT)],
            table_group_compositions=[_tgc()],
        )
        assert _ids(list(lifecycle.rule_1_11(_ctx(**stores)))) == [
            (10,)
        ]

    def test_missing_group_does_not_count(self) -> None:
        stores = _base_stores(
            table_group_compositions=[_tgc()],
        )
        assert _ids(list(lifecycle.rule_1_11(_ctx(**stores)))) == [
            (10,)
        ]

    def test_tv_not_in_new_module_is_skipped(self) -> None:
        stores = _base_stores()
        stores["module_versions"] = [_mv(start=PREV)]
        assert list(lifecycle.rule_1_11(_ctx(**stores))) == []

    def test_dangling_module_vid_is_skipped(self) -> None:
        stores = _base_stores()
        stores["module_versions"] = []
        assert list(lifecycle.rule_1_11(_ctx(**stores))) == []

    def test_missing_table_is_skipped(self) -> None:
        stores = _base_stores()
        stores["tables"] = []
        assert list(lifecycle.rule_1_11(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_12 — group tables split across new module versions
# ------------------------------------------------------------------


class TestRule112:
    def _stores(
        self,
        module_rows: List[ModuleVersionCompositionRow],
    ) -> dict:
        return {
            "tables": [_table(), _table(2)],
            "table_versions": [_tv(), _tv(20, table_id=2)],
            "module_versions": [_mv()],
            "module_version_compositions": module_rows,
            "table_groups": [_tg()],
            "table_group_compositions": [
                _tgc(30, 1),
                _tgc(30, 2),
            ],
        }

    def test_fires_on_partial_coverage(self) -> None:
        stores = self._stores([_mvc()])
        findings = list(lifecycle.rule_1_12(_ctx(**stores)))
        assert _ids(findings) == [(30,)]
        assert findings[0].objects[0].kind == "table_group"

    def test_clean_on_full_coverage(self) -> None:
        stores = self._stores(
            [_mvc(), _mvc(table_id=2, table_vid=20)]
        )
        assert list(lifecycle.rule_1_12(_ctx(**stores))) == []

    def test_clean_on_zero_coverage(self) -> None:
        stores = self._stores(
            [_mvc(table_id=9, table_vid=None)]
        )
        assert list(lifecycle.rule_1_12(_ctx(**stores))) == []

    def test_non_template_group_is_skipped(self) -> None:
        stores = self._stores([_mvc()])
        stores["table_groups"] = [_tg(type_="other")]
        assert list(lifecycle.rule_1_12(_ctx(**stores))) == []

    def test_inactive_group_is_skipped(self) -> None:
        stores = self._stores([_mvc()])
        stores["table_groups"] = [_tg(end=PREV)]
        assert list(lifecycle.rule_1_12(_ctx(**stores))) == []

    def test_closed_composition_rows_do_not_count(self) -> None:
        stores = self._stores([_mvc()])
        stores["table_group_compositions"] = [
            _tgc(30, 1),
            _tgc(30, 2, end=PREV),
        ]
        assert list(lifecycle.rule_1_12(_ctx(**stores))) == []

    def test_tables_without_open_tv_do_not_count(self) -> None:
        stores = self._stores([_mvc()])
        stores["table_versions"] = [
            _tv(),
            _tv(20, table_id=2, end=PREV),
            _tv(21, table_id=None),
        ]
        assert list(lifecycle.rule_1_12(_ctx(**stores))) == []

    def test_old_module_versions_do_not_count(self) -> None:
        stores = self._stores([_mvc()])
        stores["module_versions"] = [_mv(start=PREV)]
        assert list(lifecycle.rule_1_12(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_13 — table in no template group
# ------------------------------------------------------------------


class TestRule113:
    def test_fires_without_template_group(self) -> None:
        findings = list(
            lifecycle.rule_1_13(_ctx(**_base_stores()))
        )
        assert _ids(findings) == [(10,)]

    def test_clean_with_template_group(self) -> None:
        stores = _base_stores(
            table_groups=[_tg()],
            table_group_compositions=[_tgc()],
        )
        assert list(lifecycle.rule_1_13(_ctx(**stores))) == []

    def test_closed_group_does_not_shield(self) -> None:
        stores = _base_stores(
            table_groups=[_tg(end=PREV)],
            table_group_compositions=[_tgc()],
        )
        assert _ids(list(lifecycle.rule_1_13(_ctx(**stores)))) == [
            (10,)
        ]

    def test_non_template_group_does_not_shield(self) -> None:
        stores = _base_stores(
            table_groups=[_tg(type_="other")],
            table_group_compositions=[_tgc()],
        )
        assert _ids(list(lifecycle.rule_1_13(_ctx(**stores)))) == [
            (10,)
        ]

    def test_missing_group_does_not_shield(self) -> None:
        stores = _base_stores(
            table_group_compositions=[_tgc()],
        )
        assert _ids(list(lifecycle.rule_1_13(_ctx(**stores)))) == [
            (10,)
        ]

    def test_closed_composition_does_not_shield(self) -> None:
        stores = _base_stores(
            table_groups=[_tg()],
            table_group_compositions=[_tgc(end=PREV)],
        )
        assert _ids(list(lifecycle.rule_1_13(_ctx(**stores)))) == [
            (10,)
        ]

    def test_not_employed_table_is_skipped(self) -> None:
        stores = _base_stores()
        stores["module_versions"] = [_mv(end=CUR)]
        assert list(lifecycle.rule_1_13(_ctx(**stores))) == []

    def test_expired_tv_is_skipped(self) -> None:
        stores = _base_stores()
        stores["table_versions"] = [_tv(end=CUR)]
        assert list(lifecycle.rule_1_13(_ctx(**stores))) == []

    def test_abstract_table_is_skipped(self) -> None:
        stores = _base_stores()
        stores["tables"] = [_table(is_abstract=True)]
        assert list(lifecycle.rule_1_13(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_14 — module version number not increasing
# ------------------------------------------------------------------


class TestRule114:
    def _stores(
        self, new: ModuleVersionRow, old: Optional[ModuleVersionRow]
    ) -> dict:
        versions = [new] if old is None else [new, old]
        return {
            "modules": [_module()],
            "module_versions": versions,
        }

    def test_fires_for_null_version_number(self) -> None:
        stores = self._stores(_mv(version=None), None)
        findings = list(lifecycle.rule_1_14(_ctx(**stores)))
        assert _ids(findings) == [(500,)]

    def test_fires_when_not_greater(self) -> None:
        stores = self._stores(
            _mv(version="2.0"),
            _mv(499, start=PREV, end=CUR, version="2.0"),
        )
        assert _ids(list(lifecycle.rule_1_14(_ctx(**stores)))) == [
            (500,)
        ]

    def test_clean_when_greater(self) -> None:
        stores = self._stores(
            _mv(version="2.0"),
            _mv(499, start=PREV, end=CUR, version="1.0"),
        )
        assert list(lifecycle.rule_1_14(_ctx(**stores))) == []

    def test_sibling_null_version_is_ignored(self) -> None:
        stores = self._stores(
            _mv(version="2.0"),
            _mv(499, start=PREV, end=CUR, version=None),
        )
        assert list(lifecycle.rule_1_14(_ctx(**stores))) == []

    def test_null_module_id_has_no_siblings(self) -> None:
        stores = self._stores(
            _mv(module_id=None, version="2.0"), None
        )
        assert list(lifecycle.rule_1_14(_ctx(**stores))) == []

    def test_old_module_version_is_skipped(self) -> None:
        stores = self._stores(_mv(start=PREV, version=None), None)
        assert list(lifecycle.rule_1_14(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_15 — glossary change without new module version
# ------------------------------------------------------------------


def _stores_1_15(**overrides: Any) -> dict:
    """Old active module (start PREV) employing tv 10."""
    stores: dict = {
        "tables": [_table()],
        "table_versions": [_tv()],
        "modules": [_module()],
        "module_versions": [_mv(start=PREV)],
        "module_version_compositions": [_mvc()],
        "item_categories": [_ic(7, start=CUR)],
        "property_categories": [_pc(7)],
    }
    stores.update(overrides)
    return stores


class TestRule115:
    def test_fires_for_header_property(self) -> None:
        stores = _stores_1_15(
            headers=[_header()],
            header_versions=[_hv(100, property_id=7)],
            table_version_headers=[_tvh(header_vid=100)],
        )
        findings = list(lifecycle.rule_1_15(_ctx(**stores)))
        assert len(findings) == 1
        finding = findings[0]
        assert finding.message is not None
        assert '"header_property"' in finding.message
        assert "Module:MOD" in finding.message
        kinds = [o.kind for o in finding.objects]
        assert kinds == [
            "table_version",
            "module_version",
            "header",
            "property",
            "item",
        ]
        assert finding.objects[2].code == "010"
        assert finding.objects[2].name == "X"
        assert finding.objects[3].code == "pi7"
        assert finding.objects[4].code == "sig7"

    def test_fires_for_table_context_and_item(self) -> None:
        stores = _stores_1_15(
            item_categories=[_ic(7, start=CUR), _ic(8, start=CUR)],
            context_compositions=[_cc(40, 7, item_id=8)],
        )
        stores["table_versions"] = [_tv(context_id=40)]
        findings = list(lifecycle.rule_1_15(_ctx(**stores)))
        messages = [f.message for f in findings]
        assert any('"table_context"' in m for m in messages if m)
        assert any(
            '"table_context_item"' in m for m in messages if m
        )

    def test_fires_for_table_property(self) -> None:
        stores = _stores_1_15()
        stores["table_versions"] = [_tv(property_id=7)]
        findings = list(lifecycle.rule_1_15(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].message is not None
        assert '"table+property"' in findings[0].message

    def test_fires_for_header_context_and_subcategory(self) -> None:
        stores = _stores_1_15(
            item_categories=[_ic(7, start=CUR), _ic(8, start=CUR)],
            headers=[_header()],
            header_versions=[
                _hv(100, context_id=40, subcategory_vid=60)
            ],
            table_version_headers=[_tvh(header_vid=100)],
            context_compositions=[_cc(40, 7, item_id=8)],
            subcategory_items=[_sci(8, 60)],
        )
        findings = list(lifecycle.rule_1_15(_ctx(**stores)))
        messages = [f.message or "" for f in findings]
        assert any('"header_context"' in m for m in messages)
        assert any('"header_context_item"' in m for m in messages)
        assert any(
            '"header_subcategory_item"' in m for m in messages
        )

    def test_fires_for_variable_usages(self) -> None:
        stores = _stores_1_15(
            item_categories=[_ic(7, start=CUR), _ic(8, start=CUR)],
            table_version_cells=[_tvc(variable_vid=200)],
            variable_versions=[
                _vv(200, property_id=7, context_id=40)
            ],
            context_compositions=[_cc(40, 7, item_id=8)],
        )
        findings = list(lifecycle.rule_1_15(_ctx(**stores)))
        messages = [f.message or "" for f in findings]
        assert any('"variable_context"' in m for m in messages)
        assert any(
            '"variable_context_item"' in m for m in messages
        )
        assert any('"variable_property"' in m for m in messages)

    def test_clean_when_glossary_unchanged(self) -> None:
        stores = _stores_1_15(
            item_categories=[_ic(7, start=PREV)],
        )
        stores["table_versions"] = [_tv(property_id=7)]
        assert list(lifecycle.rule_1_15(_ctx(**stores))) == []

    def test_property_changed_via_property_category(self) -> None:
        stores = _stores_1_15(
            item_categories=[_ic(7, start=PREV)],
            property_categories=[_pc(7, start=CUR)],
        )
        stores["table_versions"] = [_tv(property_id=7)]
        assert len(list(lifecycle.rule_1_15(_ctx(**stores)))) == 1

    def test_expired_category_rows_do_not_count(self) -> None:
        stores = _stores_1_15(
            item_categories=[_ic(7, start=CUR, end=CUR)],
            property_categories=[_pc(7, end=CUR)],
        )
        stores["table_versions"] = [_tv(property_id=7)]
        assert list(lifecycle.rule_1_15(_ctx(**stores))) == []

    def test_item_without_current_start_does_not_count(self) -> None:
        stores = _stores_1_15(
            item_categories=[_ic(8, start=PREV)],
            context_compositions=[_cc(40, 7, item_id=8)],
            property_categories=[],
        )
        stores["table_versions"] = [_tv(context_id=40)]
        assert list(lifecycle.rule_1_15(_ctx(**stores))) == []

    def test_new_module_version_is_skipped(self) -> None:
        stores = _stores_1_15()
        stores["table_versions"] = [_tv(property_id=7)]
        stores["module_versions"] = [_mv(start=CUR)]
        assert list(lifecycle.rule_1_15(_ctx(**stores))) == []

    def test_closed_module_version_is_skipped(self) -> None:
        stores = _stores_1_15()
        stores["table_versions"] = [_tv(property_id=7)]
        stores["module_versions"] = [_mv(start=PREV, end=PREV)]
        assert list(lifecycle.rule_1_15(_ctx(**stores))) == []

    def test_draft_only_module_is_skipped(self) -> None:
        stores = _stores_1_15()
        stores["table_versions"] = [_tv(property_id=7)]
        stores["module_versions"] = [_mv(start=DRAFT, end=DRAFT)]
        assert list(lifecycle.rule_1_15(_ctx(**stores))) == []

    def test_draft_closed_module_with_sibling_fires(self) -> None:
        stores = _stores_1_15()
        stores["table_versions"] = [_tv(property_id=7)]
        stores["module_versions"] = [
            _mv(start=DRAFT, end=DRAFT),
            _mv(501, start=PREV, end=PREV),
        ]
        assert len(list(lifecycle.rule_1_15(_ctx(**stores)))) == 1

    def test_null_module_id_is_skipped(self) -> None:
        stores = _stores_1_15()
        stores["table_versions"] = [_tv(property_id=7)]
        stores["module_versions"] = [
            _mv(start=PREV, module_id=None)
        ]
        assert list(lifecycle.rule_1_15(_ctx(**stores))) == []

    def test_dangling_table_vid_is_skipped(self) -> None:
        stores = _stores_1_15()
        stores["table_versions"] = []
        assert list(lifecycle.rule_1_15(_ctx(**stores))) == []

    def test_null_table_vid_is_skipped(self) -> None:
        stores = _stores_1_15()
        stores["module_version_compositions"] = [
            _mvc(table_vid=None)
        ]
        assert list(lifecycle.rule_1_15(_ctx(**stores))) == []

    def test_duplicate_usages_are_deduplicated(self) -> None:
        stores = _stores_1_15()
        stores["table_versions"] = [_tv(property_id=7)]
        stores["module_version_compositions"] = [_mvc(), _mvc()]
        assert len(list(lifecycle.rule_1_15(_ctx(**stores)))) == 1

    def test_header_without_version_or_header_is_skipped(
        self,
    ) -> None:
        stores = _stores_1_15(
            table_version_headers=[
                _tvh(header_vid=None),
                _tvh(10, 2, header_vid=999),
                _tvh(10, 3, header_vid=300),
                _tvh(10, 4, header_vid=301),
            ],
            header_versions=[
                _hv(300, header_id=None, property_id=7),
                _hv(301, header_id=4, property_id=7),
            ],
        )
        assert list(lifecycle.rule_1_15(_ctx(**stores))) == []

    def test_header_null_code_and_direction(self) -> None:
        stores = _stores_1_15(
            headers=[_header(direction=None)],
            header_versions=[
                _hv(100, code=None, property_id=7)
            ],
            table_version_headers=[_tvh(header_vid=100)],
        )
        findings = list(lifecycle.rule_1_15(_ctx(**stores)))
        assert len(findings) == 1
        kinds = [o.kind for o in findings[0].objects]
        assert "header" not in kinds

    def test_variable_rows_without_version_are_skipped(self) -> None:
        stores = _stores_1_15(
            table_version_cells=[
                _tvc(cell_id=1, variable_vid=None),
                _tvc(cell_id=2, variable_vid=999),
                _tvc(cell_id=3, variable_vid=200),
            ],
            variable_versions=[_vv(200)],
        )
        assert list(lifecycle.rule_1_15(_ctx(**stores))) == []

    def test_context_row_without_item_yields_no_item_usage(
        self,
    ) -> None:
        stores = _stores_1_15(
            context_compositions=[_cc(40, 7, item_id=None)],
        )
        stores["table_versions"] = [_tv(context_id=40)]
        findings = list(lifecycle.rule_1_15(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].message is not None
        assert '"table_context"' in findings[0].message

    def test_missing_open_item_category_gives_null_codes(
        self,
    ) -> None:
        stores = _stores_1_15(
            item_categories=[
                _ic(7, start=CUR),
                _ic(7, start=PREV, end=PREV, code="old"),
            ],
        )
        stores["table_versions"] = [_tv(property_id=7)]
        findings = list(lifecycle.rule_1_15(_ctx(**stores)))
        # objects[2] is the property ref (IC code, SQL icpr.Code);
        # objects[3] is the item ref (IC signature, SQL icin.Signature).
        assert findings[0].objects[2].code == "pi7"
        assert findings[0].objects[3].code == "sig7"

    def test_earliest_open_item_category_wins(self) -> None:
        stores = _stores_1_15(
            item_categories=[
                _ic(7, start=CUR, code="late"),
                _ic(7, start=PREV, code="early"),
            ],
        )
        stores["table_versions"] = [_tv(property_id=7)]
        findings = list(lifecycle.rule_1_15(_ctx(**stores)))
        assert findings[0].objects[2].code == "early"


# ------------------------------------------------------------------
# 1_16 — technical tables split across template groups
# ------------------------------------------------------------------


class TestRule116:
    def _stores(self, **overrides: Any) -> dict:
        stores = _base_stores(
            table_groups=[_tg(30), _tg(31)],
            table_group_compositions=[
                _tgc(30, 1, start=CUR),
                _tgc(31, 2),
            ],
        )
        stores["tables"] = [_table(), _table(2)]
        stores["table_versions"] = [
            _tv(abstract_table_id=5),
            _tv(20, table_id=2, code="T2", abstract_table_id=5),
        ]
        stores.update(overrides)
        return stores

    def test_fires_for_split_template_groups(self) -> None:
        findings = list(
            lifecycle.rule_1_16(_ctx(**self._stores()))
        )
        assert _ids(findings) == [(10, 20)]
        assert findings[0].message is not None
        assert findings[0].message.endswith(": T2")

    def test_clean_when_same_group(self) -> None:
        stores = self._stores(
            table_group_compositions=[
                _tgc(30, 1, start=CUR),
                _tgc(30, 2),
            ],
        )
        assert list(lifecycle.rule_1_16(_ctx(**stores))) == []

    def test_null_abstract_table_is_skipped(self) -> None:
        stores = self._stores()
        stores["table_versions"][0] = _tv(abstract_table_id=None)
        assert list(lifecycle.rule_1_16(_ctx(**stores))) == []

    def test_expired_tv_is_skipped(self) -> None:
        stores = self._stores()
        stores["table_versions"][0] = _tv(
            abstract_table_id=5, end=CUR
        )
        assert list(lifecycle.rule_1_16(_ctx(**stores))) == []

    def test_abstract_table_is_skipped(self) -> None:
        stores = self._stores()
        stores["tables"][0] = _table(is_abstract=True)
        assert list(lifecycle.rule_1_16(_ctx(**stores))) == []

    def test_old_own_composition_is_skipped(self) -> None:
        stores = self._stores(
            table_group_compositions=[
                _tgc(30, 1, start=PREV),
                _tgc(31, 2),
            ],
        )
        assert list(lifecycle.rule_1_16(_ctx(**stores))) == []

    def test_non_template_own_group_is_skipped(self) -> None:
        stores = self._stores(
            table_groups=[_tg(30, type_="other"), _tg(31)],
        )
        assert list(lifecycle.rule_1_16(_ctx(**stores))) == []

    def test_missing_own_group_is_skipped(self) -> None:
        stores = self._stores(table_groups=[_tg(31)])
        assert list(lifecycle.rule_1_16(_ctx(**stores))) == []

    def test_expired_sibling_tv_is_skipped(self) -> None:
        stores = self._stores()
        stores["table_versions"][1] = _tv(
            20, table_id=2, abstract_table_id=5, end=CUR
        )
        assert list(lifecycle.rule_1_16(_ctx(**stores))) == []

    def test_same_table_sibling_is_skipped(self) -> None:
        stores = self._stores()
        stores["table_versions"][1] = _tv(
            20, table_id=1, abstract_table_id=5
        )
        stores["table_group_compositions"][1] = _tgc(31, 1)
        assert list(lifecycle.rule_1_16(_ctx(**stores))) == []

    def test_null_table_id_sibling_is_skipped(self) -> None:
        stores = self._stores()
        stores["table_versions"][1] = _tv(
            20, table_id=None, abstract_table_id=5
        )
        assert list(lifecycle.rule_1_16(_ctx(**stores))) == []

    def test_closed_sibling_composition_is_skipped(self) -> None:
        stores = self._stores(
            table_group_compositions=[
                _tgc(30, 1, start=CUR),
                _tgc(31, 2, end=PREV),
            ],
        )
        assert list(lifecycle.rule_1_16(_ctx(**stores))) == []

    def test_closed_sibling_group_is_skipped(self) -> None:
        stores = self._stores(
            table_groups=[_tg(30), _tg(31, end=PREV)],
        )
        assert list(lifecycle.rule_1_16(_ctx(**stores))) == []

    def test_duplicate_pairs_are_deduplicated(self) -> None:
        stores = self._stores(
            table_groups=[_tg(30), _tg(31), _tg(32)],
            table_group_compositions=[
                _tgc(30, 1, start=CUR),
                _tgc(31, 2),
                _tgc(32, 2),
            ],
        )
        assert len(list(lifecycle.rule_1_16(_ctx(**stores)))) == 1


# ------------------------------------------------------------------
# 1_17 — duplicate table version names
# ------------------------------------------------------------------


class TestRule117:
    def _stores(self, other: TableVersionRow, **extra: Any) -> dict:
        stores: dict = {
            "tables": [_table(1), _table(2)],
            "table_versions": [
                _tv(10, table_id=2, name="Name"),
                other,
            ],
            "modules": [_module()],
            "module_versions": [_mv(), _mv(501, start=PREV)],
            "module_version_compositions": [
                _mvc(500, table_id=2, table_vid=10),
                _mvc(501, table_id=1, table_vid=20),
            ],
        }
        stores.update(extra)
        return stores

    def test_fires_on_duplicate_name(self) -> None:
        stores = self._stores(
            _tv(20, table_id=1, code="T0", name=" Name ")
        )
        findings = list(lifecycle.rule_1_17(_ctx(**stores)))
        assert _ids(findings) == [(10, 20)]
        assert findings[0].message is not None
        assert "with: T0" in findings[0].message

    def test_clean_on_distinct_names(self) -> None:
        stores = self._stores(
            _tv(20, table_id=1, name="Other")
        )
        assert list(lifecycle.rule_1_17(_ctx(**stores))) == []

    def test_higher_table_id_is_skipped(self) -> None:
        stores = self._stores(
            _tv(20, table_id=3, name="Name")
        )
        stores["tables"].append(_table(3))
        assert list(lifecycle.rule_1_17(_ctx(**stores))) == []

    def test_null_name_is_skipped(self) -> None:
        stores = self._stores(_tv(20, table_id=1, name=None))
        stores["table_versions"][0] = _tv(
            10, table_id=2, name=None
        )
        assert list(lifecycle.rule_1_17(_ctx(**stores))) == []

    def test_null_other_table_id_is_skipped(self) -> None:
        stores = self._stores(
            _tv(20, table_id=None, name="Name")
        )
        assert list(lifecycle.rule_1_17(_ctx(**stores))) == []

    def test_missing_other_table_is_skipped(self) -> None:
        stores = self._stores(_tv(20, table_id=1, name="Name"))
        stores["tables"] = [_table(2)]
        assert list(lifecycle.rule_1_17(_ctx(**stores))) == []

    def test_different_abstractness_is_skipped(self) -> None:
        stores = self._stores(_tv(20, table_id=1, name="Name"))
        stores["tables"] = [
            _table(1, is_abstract=True),
            _table(2),
        ]
        assert list(lifecycle.rule_1_17(_ctx(**stores))) == []

    def test_null_abstractness_is_skipped(self) -> None:
        stores = self._stores(_tv(20, table_id=1, name="Name"))
        stores["tables"] = [
            _table(1, is_abstract=None),
            _table(2),
        ]
        assert list(lifecycle.rule_1_17(_ctx(**stores))) == []

    def test_other_outside_active_modules_is_skipped(self) -> None:
        stores = self._stores(_tv(20, table_id=1, name="Name"))
        stores["module_versions"] = [
            _mv(),
            _mv(501, start=DRAFT),
        ]
        assert list(lifecycle.rule_1_17(_ctx(**stores))) == []

    def test_duplicate_pairs_are_deduplicated(self) -> None:
        stores = self._stores(_tv(20, table_id=1, name="Name"))
        stores["module_version_compositions"].append(
            _mvc(500, table_id=2, table_vid=10)
        )
        assert len(list(lifecycle.rule_1_17(_ctx(**stores)))) == 1


# ------------------------------------------------------------------
# 1_18 — illegal characters in table group code
# ------------------------------------------------------------------


class TestRule118:
    def test_fires_on_illegal_character(self) -> None:
        stores = {"table_groups": [_tg(code="AE(1)", start=CUR)]}
        findings = list(lifecycle.rule_1_18(_ctx(**stores)))
        assert _ids(findings) == [(30,)]

    def test_clean_code(self) -> None:
        stores = {"table_groups": [_tg(code="AE_1", start=CUR)]}
        assert list(lifecycle.rule_1_18(_ctx(**stores))) == []

    def test_old_group_is_skipped(self) -> None:
        stores = {"table_groups": [_tg(code="AE(1)")]}
        assert list(lifecycle.rule_1_18(_ctx(**stores))) == []

    def test_non_template_group_is_skipped(self) -> None:
        stores = {
            "table_groups": [
                _tg(code="AE(1)", start=CUR, type_="other")
            ]
        }
        assert list(lifecycle.rule_1_18(_ctx(**stores))) == []

    def test_null_code_is_skipped(self) -> None:
        stores = {"table_groups": [_tg(code=None, start=CUR)]}
        assert list(lifecycle.rule_1_18(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_19 — open-axis settings changed by copy-paste
# ------------------------------------------------------------------


class TestRule119:
    def _stores(
        self, new_table: TableRow, old_table: TableRow
    ) -> dict:
        stores = _base_stores(aux_cell_mappings=[_acm()])
        stores["tables"] = [new_table, old_table]
        stores["table_versions"] = [_tv(), _tv(20, table_id=2)]
        return stores

    def test_fires_on_flag_mismatch(self) -> None:
        stores = self._stores(
            _open_table(1, rows=True), _open_table(2)
        )
        assert _ids(list(lifecycle.rule_1_19(_ctx(**stores)))) == [
            (10,)
        ]

    def test_fires_on_sheet_mismatch(self) -> None:
        stores = self._stores(
            _open_table(1, sheets=True), _open_table(2)
        )
        assert _ids(list(lifecycle.rule_1_19(_ctx(**stores)))) == [
            (10,)
        ]

    def test_clean_on_matching_flags(self) -> None:
        stores = self._stores(
            _open_table(1, rows=True), _open_table(2, rows=True)
        )
        assert list(lifecycle.rule_1_19(_ctx(**stores))) == []

    def test_null_flags_never_differ(self) -> None:
        stores = self._stores(_table(1), _table(2))
        assert list(lifecycle.rule_1_19(_ctx(**stores))) == []

    def test_dangling_new_tv_is_skipped(self) -> None:
        stores = self._stores(
            _open_table(1, rows=True), _open_table(2)
        )
        stores["aux_cell_mappings"] = [_acm(new_vid=99)]
        assert list(lifecycle.rule_1_19(_ctx(**stores))) == []

    def test_tv_outside_new_modules_is_skipped(self) -> None:
        stores = self._stores(
            _open_table(1, rows=True), _open_table(2)
        )
        stores["module_versions"] = [_mv(start=PREV)]
        assert list(lifecycle.rule_1_19(_ctx(**stores))) == []

    def test_null_old_vid_is_skipped(self) -> None:
        stores = self._stores(
            _open_table(1, rows=True), _open_table(2)
        )
        stores["aux_cell_mappings"] = [_acm(old_vid=None)]
        assert list(lifecycle.rule_1_19(_ctx(**stores))) == []

    def test_missing_old_table_is_skipped(self) -> None:
        stores = self._stores(
            _open_table(1, rows=True), _open_table(2)
        )
        stores["tables"] = [_open_table(1, rows=True)]
        assert list(lifecycle.rule_1_19(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_20 — new table version employed by old module version
# ------------------------------------------------------------------


class TestRule120:
    def test_fires_for_old_active_module(self) -> None:
        stores = _base_stores()
        stores["module_versions"] = [_mv(start=PREV)]
        findings = list(lifecycle.rule_1_20(_ctx(**stores)))
        assert _ids(findings) == [(10, 500)]

    def test_clean_for_new_module(self) -> None:
        assert (
            list(lifecycle.rule_1_20(_ctx(**_base_stores()))) == []
        )

    def test_closed_module_is_skipped(self) -> None:
        stores = _base_stores()
        stores["module_versions"] = [_mv(start=PREV, end=PREV)]
        assert list(lifecycle.rule_1_20(_ctx(**stores))) == []

    def test_old_tv_is_skipped(self) -> None:
        stores = _base_stores()
        stores["table_versions"] = [_tv(start=PREV)]
        stores["module_versions"] = [_mv(start=PREV)]
        assert list(lifecycle.rule_1_20(_ctx(**stores))) == []

    def test_missing_table_is_skipped(self) -> None:
        stores = _base_stores()
        stores["tables"] = []
        stores["module_versions"] = [_mv(start=PREV)]
        assert list(lifecycle.rule_1_20(_ctx(**stores))) == []

    def test_null_table_id_is_skipped(self) -> None:
        stores = _base_stores()
        stores["table_versions"] = [_tv(table_id=None)]
        stores["module_versions"] = [_mv(start=PREV)]
        assert list(lifecycle.rule_1_20(_ctx(**stores))) == []

    def test_dangling_module_vid_is_skipped(self) -> None:
        stores = _base_stores()
        stores["module_versions"] = []
        assert list(lifecycle.rule_1_20(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_21 — draft composition start in new table group
# ------------------------------------------------------------------


class TestRule121:
    def _stores(self, **overrides: Any) -> dict:
        stores: dict = {
            "tables": [_table()],
            "table_versions": [_tv()],
            "table_groups": [_tg(start=CUR)],
            "table_group_compositions": [_tgc(start=DRAFT)],
        }
        stores.update(overrides)
        return stores

    def test_fires_for_draft_composition(self) -> None:
        findings = list(
            lifecycle.rule_1_21(_ctx(**self._stores()))
        )
        assert _ids(findings) == [(10, 30)]

    def test_never_fires_without_draft_release(self) -> None:
        ctx = _ctx(REL_NO_DRAFT, **self._stores())
        assert list(lifecycle.rule_1_21(ctx)) == []

    def test_non_draft_composition_is_skipped(self) -> None:
        stores = self._stores(
            table_group_compositions=[_tgc(start=CUR)]
        )
        assert list(lifecycle.rule_1_21(_ctx(**stores))) == []

    def test_old_group_is_skipped(self) -> None:
        stores = self._stores(table_groups=[_tg(start=PREV)])
        assert list(lifecycle.rule_1_21(_ctx(**stores))) == []

    def test_missing_group_is_skipped(self) -> None:
        stores = self._stores(table_groups=[])
        assert list(lifecycle.rule_1_21(_ctx(**stores))) == []

    def test_expired_tv_is_skipped(self) -> None:
        stores = self._stores(table_versions=[_tv(end=CUR)])
        assert list(lifecycle.rule_1_21(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_22 — replicated table association
# ------------------------------------------------------------------


class TestRule122:
    def _stores(self, **overrides: Any) -> dict:
        stores: dict = {
            "table_versions": [_tv(), _tv(20, table_id=2)],
            "table_associations": [
                _ta(901, name="A-new"),
                _ta(900, name="A-old"),
            ],
        }
        stores.update(overrides)
        return stores

    def test_fires_for_duplicate_association(self) -> None:
        findings = list(
            lifecycle.rule_1_22(_ctx(**self._stores()))
        )
        assert _ids(findings) == [(10, 901, 900)]
        assert findings[0].message is not None
        assert "A-new" in findings[0].message
        assert "A-old" in findings[0].message

    def test_fires_for_identical_mappings(self) -> None:
        stores = self._stores(
            key_header_mappings=[
                _khm(901, fk=2),
                _khm(900, fk=2),
            ]
        )
        assert len(list(lifecycle.rule_1_22(_ctx(**stores)))) == 1

    def test_clean_for_different_mappings(self) -> None:
        stores = self._stores(
            key_header_mappings=[
                _khm(901, fk=2),
                _khm(900, fk=3),
            ]
        )
        assert list(lifecycle.rule_1_22(_ctx(**stores))) == []

    def test_clean_for_different_pairs(self) -> None:
        stores = self._stores(
            table_associations=[
                _ta(901, child=20),
                _ta(900, child=21),
            ]
        )
        assert list(lifecycle.rule_1_22(_ctx(**stores))) == []

    def test_null_endpoints_are_skipped(self) -> None:
        stores = self._stores(
            table_associations=[
                _ta(901, parent=None),
                _ta(900, child=None),
            ]
        )
        assert list(lifecycle.rule_1_22(_ctx(**stores))) == []

    def test_dangling_parent_tv_is_skipped(self) -> None:
        stores = self._stores(table_versions=[])
        assert list(lifecycle.rule_1_22(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 1_23 — inconsistent categories in association mapping
# ------------------------------------------------------------------


class TestRule123:
    def _stores(self, **overrides: Any) -> dict:
        stores: dict = {
            "table_versions": [_tv(), _tv(20, table_id=2)],
            "table_associations": [_ta()],
            "key_header_mappings": [_khm(fk=2, pk=1)],
            "headers": [_header(1), _header(2, table_id=2)],
            "header_versions": [
                _hv(100, header_id=1, property_id=7),
                _hv(200, header_id=2, property_id=8),
            ],
            "table_version_headers": [
                _tvh(10, 1, header_vid=100),
                _tvh(20, 2, header_vid=200),
            ],
            "item_categories": [_ic(7)],
            "property_categories": [
                _pc(7, category_id=3),
                _pc(8, category_id=4),
            ],
            "categories": [_cat(3)],
        }
        stores.update(overrides)
        return stores

    def test_fires_on_category_mismatch(self) -> None:
        findings = list(
            lifecycle.rule_1_23(_ctx(**self._stores()))
        )
        assert len(findings) == 1
        tv_ref, prop_ref, cat_ref = findings[0].objects
        assert tv_ref.id == 10
        assert prop_ref.id == 7
        assert prop_ref.code == "pi7"
        assert cat_ref.id == 3
        assert findings[0].message is not None
        assert "A1" in findings[0].message

    def test_clean_on_matching_categories(self) -> None:
        stores = self._stores(
            property_categories=[
                _pc(7, category_id=3),
                _pc(8, category_id=3),
            ]
        )
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_null_child_category_does_not_count(self) -> None:
        stores = self._stores(
            property_categories=[
                _pc(7, category_id=3),
                _pc(8, category_id=None),
            ]
        )
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_expired_child_category_does_not_count(self) -> None:
        stores = self._stores(
            property_categories=[
                _pc(7, category_id=3),
                _pc(8, category_id=4, end=CUR),
            ]
        )
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_expired_parent_rows_are_skipped(self) -> None:
        stores = self._stores(
            item_categories=[_ic(7, end=CUR)],
        )
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_expired_parent_pc_is_skipped(self) -> None:
        stores = self._stores(
            property_categories=[
                _pc(7, category_id=3, end=CUR),
                _pc(8, category_id=4),
            ]
        )
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_missing_category_row_is_skipped(self) -> None:
        stores = self._stores(categories=[])
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_null_parent_category_id_is_skipped(self) -> None:
        stores = self._stores(
            property_categories=[
                _pc(7, category_id=None),
                _pc(8, category_id=4),
            ]
        )
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_header_without_property_is_skipped(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(100, header_id=1, property_id=None),
                _hv(200, header_id=2, property_id=8),
            ]
        )
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_child_without_property_is_skipped(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(100, header_id=1, property_id=7),
                _hv(200, header_id=2, property_id=None),
            ]
        )
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_null_pk_mapping_is_skipped(self) -> None:
        stores = self._stores(
            key_header_mappings=[_khm(fk=2, pk=None)]
        )
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_unmapped_headers_are_skipped(self) -> None:
        stores = self._stores(
            key_header_mappings=[_khm(fk=9, pk=1)]
        )
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_tvh_without_header_vid_is_skipped(self) -> None:
        stores = self._stores(
            table_version_headers=[
                _tvh(10, 1, header_vid=None),
                _tvh(20, 2, header_vid=200),
            ]
        )
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_missing_endpoint_tvs_are_skipped(self) -> None:
        stores = self._stores(
            table_associations=[
                _ta(900, parent=None),
                _ta(901, child=None),
            ]
        )
        assert list(lifecycle.rule_1_23(_ctx(**stores))) == []

    def test_duplicate_rows_are_deduplicated(self) -> None:
        stores = self._stores()
        stores["key_header_mappings"].append(_khm(fk=2, pk=1))
        assert len(list(lifecycle.rule_1_23(_ctx(**stores)))) == 1


# ------------------------------------------------------------------
# 1_24 — mapping must cover exactly the key headers
# ------------------------------------------------------------------


class TestRule124:
    def _stores(self, **overrides: Any) -> dict:
        stores: dict = {
            "table_versions": [_tv(), _tv(20, table_id=2)],
            "table_associations": [_ta()],
            "headers": [
                _header(1, is_key=True),
                _header(2, is_key=False),
            ],
            "table_version_headers": [
                _tvh(10, 1),
                _tvh(10, 2),
            ],
            "key_header_mappings": [_khm(fk=5, pk=1)],
        }
        stores.update(overrides)
        return stores

    def test_fires_when_key_header_unmapped(self) -> None:
        stores = self._stores(key_header_mappings=[])
        findings = list(lifecycle.rule_1_24(_ctx(**stores)))
        assert _ids(findings) == [(10, 900)]
        assert findings[0].message is not None
        assert "A1" in findings[0].message

    def test_fires_when_non_key_header_mapped(self) -> None:
        stores = self._stores(
            key_header_mappings=[
                _khm(fk=5, pk=1),
                _khm(fk=6, pk=2),
            ]
        )
        assert _ids(list(lifecycle.rule_1_24(_ctx(**stores)))) == [
            (10, 900)
        ]

    def test_clean_when_mapping_exact(self) -> None:
        ctx = _ctx(**self._stores())
        assert list(lifecycle.rule_1_24(ctx)) == []

    def test_null_pk_suppresses_missing_key(self) -> None:
        stores = self._stores(
            key_header_mappings=[_khm(fk=5, pk=None)]
        )
        assert list(lifecycle.rule_1_24(_ctx(**stores))) == []

    def test_null_is_key_matches_neither(self) -> None:
        stores = self._stores(
            headers=[
                _header(1, is_key=True),
                _header(2, is_key=None),
            ],
            key_header_mappings=[
                _khm(fk=5, pk=1),
                _khm(fk=6, pk=2),
            ],
        )
        assert list(lifecycle.rule_1_24(_ctx(**stores))) == []

    def test_dangling_header_is_skipped(self) -> None:
        stores = self._stores(headers=[_header(1, is_key=True)])
        assert list(lifecycle.rule_1_24(_ctx(**stores))) == []

    def test_null_parent_is_skipped(self) -> None:
        stores = self._stores(
            table_associations=[_ta(parent=None)]
        )
        assert list(lifecycle.rule_1_24(_ctx(**stores))) == []

    def test_dangling_parent_tv_is_skipped(self) -> None:
        stores = self._stores(table_versions=[])
        assert list(lifecycle.rule_1_24(_ctx(**stores))) == []


# ------------------------------------------------------------------
# Defensive-guard and loop-branch coverage
# ------------------------------------------------------------------


class TestSharedHelpersCoverage:
    def test_current_open_tvs_skips_non_candidates(self) -> None:
        # Drive _current_open_tvs through rule_1_1: a tv starting in
        # an old release, a tv with no module composition, and a tv
        # whose table row is missing must all be skipped.
        stores = _base_stores(
            table_versions=[
                _tv(10, start=PREV),
                _tv(11, table_id=1),
                _tv(12, table_id=None),
            ],
            module_version_compositions=[
                _mvc(500, table_id=1, table_vid=10),
                _mvc(999, table_id=1, table_vid=11),
                _mvc(500, table_id=1, table_vid=12),
            ],
        )
        assert list(lifecycle.rule_1_1(_ctx(**stores))) == []

    def test_active_module_vids_skip_null_table_vid(self) -> None:
        # _tvs_in_active_modules must ignore compositions without a
        # TableVID; with tv2 in no active module 1_17 stays quiet.
        stores = {
            "tables": [_table(1), _table(2)],
            "table_versions": [
                _tv(10, table_id=2, name="Name"),
                _tv(20, table_id=1, name="Name"),
            ],
            "modules": [_module()],
            "module_versions": [_mv(), _mv(501, start=PREV)],
            "module_version_compositions": [
                _mvc(500, table_id=2, table_vid=10),
                _mvc(501, table_id=1, table_vid=None),
            ],
        }
        assert list(lifecycle.rule_1_17(_ctx(**stores))) == []


class TestRule115BranchCoverage:
    def test_header_context_composition_without_item(self) -> None:
        stores = _stores_1_15(
            headers=[_header()],
            header_versions=[_hv(100, context_id=40)],
            table_version_headers=[_tvh(header_vid=100)],
            context_compositions=[_cc(40, 7, item_id=None)],
        )
        findings = list(lifecycle.rule_1_15(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].message is not None
        assert '"header_context"' in findings[0].message

    def test_variable_context_composition_without_item(self) -> None:
        stores = _stores_1_15(
            variable_versions=[_vv(200, context_id=40)],
            table_version_cells=[_tvc(variable_vid=200)],
            context_compositions=[_cc(40, 7, item_id=None)],
        )
        findings = list(lifecycle.rule_1_15(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].message is not None
        assert '"variable_context"' in findings[0].message

    def test_later_open_item_category_does_not_win(self) -> None:
        stores = _stores_1_15(
            item_categories=[
                _ic(7, start=PREV, code="early"),
                _ic(7, start=CUR, code="late"),
            ],
        )
        stores["table_versions"] = [_tv(property_id=7)]
        findings = list(lifecycle.rule_1_15(_ctx(**stores)))
        assert findings[0].objects[2].code == "early"

    def test_rule_1_17_deduplicates_across_modules(self) -> None:
        # tv 10 sits in TWO new module versions; the (tv, tv2) pair
        # must be reported only once.
        stores = {
            "tables": [_table(1), _table(2)],
            "table_versions": [
                _tv(10, table_id=2, name="Name"),
                _tv(20, table_id=1, code="T0", name="Name"),
            ],
            "modules": [_module()],
            "module_versions": [
                _mv(),
                _mv(501),
                _mv(502, start=PREV),
            ],
            "module_version_compositions": [
                _mvc(500, table_id=2, table_vid=10),
                _mvc(501, table_id=2, table_vid=10),
                _mvc(502, table_id=1, table_vid=20),
            ],
        }
        findings = list(lifecycle.rule_1_17(_ctx(**stores)))
        assert _ids(findings) == [(10, 20)]
