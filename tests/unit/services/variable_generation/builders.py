"""Row and state builders shared by the variable-generation tests."""

from __future__ import annotations

from datetime import date
from typing import Any

from dpmcore.services.model_validation import (
    ModelSnapshot,
    ReleaseContext,
)
from dpmcore.services.model_validation.snapshot import (
    AuxCellMappingRow,
    CategoryRow,
    CellRow,
    CompoundKeyRow,
    ContextCompositionRow,
    ContextRow,
    HeaderRow,
    HeaderVersionRow,
    ItemCategoryRow,
    ItemRow,
    KeyCompositionRow,
    ModuleParametersRow,
    ModuleVersionCompositionRow,
    ModuleVersionRow,
    PropertyRow,
    TableRow,
    TableVersionCellRow,
    TableVersionHeaderRow,
    TableVersionRow,
    VariableRow,
    VariableVersionRow,
)
from dpmcore.services.variable_generation.state import (
    CellRecord,
    GenerationState,
)

CUR = 100
PREV = 50
DRAFT = 9999

CUR_DATE = date(2025, 1, 1)
PREV_DATE = date(2024, 1, 1)


def rel(*, draft: bool = True) -> ReleaseContext:
    return ReleaseContext(
        current_release_id=CUR,
        draft_release_id=DRAFT if draft else None,
    )


def snap(**stores: Any) -> ModelSnapshot:
    return ModelSnapshot.from_rows(**stores)


def state(**kwargs: Any) -> GenerationState:
    kwargs.setdefault(
        "release_dates", {CUR: CUR_DATE, PREV: PREV_DATE}
    )
    return GenerationState(**kwargs)


def table(table_id: int = 1, *, is_abstract: Any = False) -> TableRow:
    return TableRow(
        table_id=table_id,
        is_abstract=is_abstract,
        has_open_columns=None,
        has_open_rows=None,
        has_open_sheets=None,
    )


def tv(
    vid: int = 10,
    *,
    table_id: Any = 1,
    code: Any = "T1",
    abstract_table_id: Any = None,
    key_id: Any = None,
    property_id: Any = None,
    context_id: Any = None,
    start: Any = CUR,
    end: Any = None,
) -> TableVersionRow:
    return TableVersionRow(
        table_vid=vid,
        code=code,
        name=None,
        table_id=table_id,
        abstract_table_id=abstract_table_id,
        key_id=key_id,
        property_id=property_id,
        context_id=context_id,
        start_release_id=start,
        end_release_id=end,
    )


def header(
    header_id: int = 1,
    *,
    table_id: Any = 1,
    direction: Any = "x",
    is_key: Any = False,
) -> HeaderRow:
    return HeaderRow(
        header_id=header_id,
        table_id=table_id,
        direction=direction,
        is_key=is_key,
        is_attribute=None,
    )


def hv(
    vid: int = 100,
    *,
    header_id: Any = 1,
    code: Any = "010",
    label: Any = None,
    property_id: Any = None,
    context_id: Any = None,
    subcategory_vid: Any = None,
    key_variable_vid: Any = None,
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
        key_variable_vid=key_variable_vid,
        start_release_id=start,
        end_release_id=end,
    )


def tvh(
    table_vid: int = 10,
    header_id: int = 1,
    *,
    header_vid: Any = 100,
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


def mv(
    vid: int = 500,
    *,
    module_id: int = 1,
    start: Any = CUR,
    end: Any = None,
    code: Any = "MOD",
) -> ModuleVersionRow:
    return ModuleVersionRow(
        module_vid=vid,
        module_id=module_id,
        global_key_id=None,
        start_release_id=start,
        end_release_id=end,
        code=code,
        name=None,
        version_number=None,
        is_reported=None,
        is_calculated=None,
    )


def mvc(
    module_vid: int = 500, table_id: int = 1, table_vid: Any = 10
) -> ModuleVersionCompositionRow:
    return ModuleVersionCompositionRow(
        module_vid=module_vid,
        table_id=table_id,
        table_vid=table_vid,
        order=None,
    )


def mp(module_vid: int, variable_vid: int) -> ModuleParametersRow:
    return ModuleParametersRow(
        module_vid=module_vid, variable_vid=variable_vid
    )


def cell(
    cell_id: int = 1000,
    *,
    table_id: Any = 1,
    column_id: Any = None,
    row_id: Any = None,
    sheet_id: Any = None,
) -> CellRow:
    return CellRow(
        cell_id=cell_id,
        table_id=table_id,
        column_id=column_id,
        row_id=row_id,
        sheet_id=sheet_id,
    )


def tvc(
    table_vid: int = 10,
    cell_id: int = 1000,
    *,
    code: Any = None,
    is_void: Any = None,
    is_excluded: Any = None,
    variable_vid: Any = None,
) -> TableVersionCellRow:
    return TableVersionCellRow(
        table_vid=table_vid,
        cell_id=cell_id,
        cell_code=code,
        is_nullable=None,
        is_excluded=is_excluded,
        is_void=is_void,
        sign=None,
        variable_vid=variable_vid,
    )


def var(variable_id: int = 600, *, type_: Any = "fact") -> VariableRow:
    return VariableRow(variable_id=variable_id, type=type_)


def vv(
    vid: int = 5000,
    *,
    variable_id: Any = 600,
    property_id: Any = None,
    context_id: Any = None,
    key_id: Any = None,
    code: Any = None,
    start: Any = PREV,
    end: Any = None,
) -> VariableVersionRow:
    return VariableVersionRow(
        variable_vid=vid,
        variable_id=variable_id,
        property_id=property_id,
        subcategory_vid=None,
        context_id=context_id,
        key_id=key_id,
        is_multi_valued=None,
        code=code,
        name=None,
        start_release_id=start,
        end_release_id=end,
    )


def ck(key_id: int = 70, *, signature: Any = "20#") -> CompoundKeyRow:
    return CompoundKeyRow(key_id=key_id, signature=signature)


def kc(key_id: int, variable_vid: int) -> KeyCompositionRow:
    return KeyCompositionRow(key_id=key_id, variable_vid=variable_vid)


def item(
    item_id: int, *, name: Any = None, is_property: Any = False
) -> ItemRow:
    return ItemRow(
        item_id=item_id,
        name=name,
        is_property=is_property,
        is_active=True,
        owner_id=None,
    )


def ic(
    item_id: int,
    *,
    category_id: Any = 900,
    code: Any = None,
    start: Any = PREV,
    end: Any = None,
    signature: Any = None,
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


def cat(
    category_id: int = 900,
    *,
    name: Any = "Templates",
    code: Any = "TE",
) -> CategoryRow:
    return CategoryRow(
        category_id=category_id,
        code=code,
        name=name,
        is_enumerated=None,
        is_active=True,
        created_release_id=None,
    )


def prop(
    property_id: int = 10, *, data_type_id: Any = None
) -> PropertyRow:
    return PropertyRow(
        property_id=property_id,
        is_composite=None,
        is_metric=None,
        data_type_id=data_type_id,
        period_type=None,
    )


def ctx(context_id: int = 40, *, signature: Any = None) -> ContextRow:
    return ContextRow(context_id=context_id, signature=signature)


def ccomp(
    context_id: int = 40, property_id: int = 11, item_id: Any = 70
) -> ContextCompositionRow:
    return ContextCompositionRow(
        context_id=context_id,
        property_id=property_id,
        item_id=item_id,
    )


def aux(
    new_table_vid: int,
    new_cell_id: int,
    old_table_vid: Any,
    old_cell_id: Any,
) -> AuxCellMappingRow:
    return AuxCellMappingRow(
        new_cell_id=new_cell_id,
        new_table_vid=new_table_vid,
        old_cell_id=old_cell_id,
        old_table_vid=old_table_vid,
    )


def rec(**overrides: Any) -> CellRecord:
    defaults: dict = {
        "module_vid": 500,
        "module_code": "MOD",
        "table_vid": 10,
        "table_code": "T1",
        "cell_id": 1000,
        "cell_code": "c1000",
        "is_void": False,
        "tv_start": CUR,
        "mv_start": CUR,
    }
    defaults.update(overrides)
    return CellRecord(**defaults)
