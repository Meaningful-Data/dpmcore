"""Unit tests for the glossary (family 6) model-validation rules."""

from typing import Any, List

from dpmcore.services.model_validation.registry import (
    REGISTRY,
    Finding,
    RuleContext,
)
from dpmcore.services.model_validation.release_context import (
    ReleaseContext,
)
from dpmcore.services.model_validation.rules import glossary  # noqa: F401
from dpmcore.services.model_validation.snapshot import (
    CategoryRow,
    CellRow,
    CompoundItemContextRow,
    ContextCompositionRow,
    DataTypeRow,
    FrameworkRow,
    HeaderRow,
    HeaderVersionRow,
    ItemCategoryRow,
    ItemRow,
    ModelSnapshot,
    ModuleRow,
    ModuleVersionCompositionRow,
    ModuleVersionRow,
    OperationRow,
    OperationVersionRow,
    PropertyCategoryRow,
    PropertyRow,
    ReleaseRow,
    SubCategoryItemRow,
    SubCategoryRow,
    SubCategoryVersionRow,
    SupercategoryCompositionRow,
    TableGroupRow,
    TableRow,
    TableVersionCellRow,
    TableVersionHeaderRow,
    TableVersionRow,
    VariableVersionRow,
)
from dpmcore.services.model_validation.types import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)

CUR = 5
OLD = 3
DRAFT = 9999


# ------------------------------------------------------------------
# Row builders
# ------------------------------------------------------------------


def release(release_id, code=None):
    return ReleaseRow(
        release_id=release_id,
        code=code,
        status=None,
        is_current=None,
        type=None,
    )


def datatype(data_type_id, code=None, name=None):
    return DataTypeRow(
        data_type_id=data_type_id,
        code=code,
        name=name,
        parent_data_type_id=None,
        is_active=True,
    )


def framework(framework_id, code=None):
    return FrameworkRow(framework_id=framework_id, code=code, name=None)


def module(module_id, framework_id=None):
    return ModuleRow(
        module_id=module_id,
        framework_id=framework_id,
        is_document_module=False,
    )


def module_version(module_vid, module_id=None, start=None, code=None):
    return ModuleVersionRow(
        module_vid=module_vid,
        module_id=module_id,
        global_key_id=None,
        start_release_id=start,
        end_release_id=None,
        code=code,
        name=None,
        version_number=None,
        is_reported=None,
        is_calculated=None,
    )


def mvc(module_vid, table_id, table_vid=None):
    return ModuleVersionCompositionRow(
        module_vid=module_vid,
        table_id=table_id,
        table_vid=table_vid,
        order=None,
    )


def table(table_id, is_abstract=False):
    return TableRow(
        table_id=table_id,
        is_abstract=is_abstract,
        has_open_columns=None,
        has_open_rows=None,
        has_open_sheets=None,
    )


def table_version(
    table_vid,
    code=None,
    table_id=None,
    start=None,
    end=None,
    property_id=None,
    context_id=None,
):
    return TableVersionRow(
        table_vid=table_vid,
        code=code,
        name=None,
        table_id=table_id,
        abstract_table_id=None,
        key_id=None,
        property_id=property_id,
        context_id=context_id,
        start_release_id=start,
        end_release_id=end,
    )


def header(header_id, table_id=None):
    return HeaderRow(
        header_id=header_id,
        table_id=table_id,
        direction=None,
        is_key=None,
        is_attribute=None,
    )


def header_version(
    header_vid,
    header_id=None,
    code=None,
    label=None,
    property_id=None,
    context_id=None,
    subcategory_vid=None,
    start=None,
):
    return HeaderVersionRow(
        header_vid=header_vid,
        header_id=header_id,
        code=code,
        label=label,
        property_id=property_id,
        context_id=context_id,
        subcategory_vid=subcategory_vid,
        key_variable_vid=None,
        start_release_id=start,
        end_release_id=None,
    )


def tvh(table_vid, header_id, header_vid=None):
    return TableVersionHeaderRow(
        table_vid=table_vid,
        header_id=header_id,
        header_vid=header_vid,
        parent_header_id=None,
        parent_first=None,
        order=None,
        is_abstract=None,
        is_unique=None,
    )


def cell(cell_id, column_id=None, row_id=None, sheet_id=None):
    return CellRow(
        cell_id=cell_id,
        table_id=None,
        column_id=column_id,
        row_id=row_id,
        sheet_id=sheet_id,
    )


def tvc(
    table_vid,
    cell_id,
    cell_code=None,
    sign=None,
    is_void=False,
    is_excluded=False,
):
    return TableVersionCellRow(
        table_vid=table_vid,
        cell_id=cell_id,
        cell_code=cell_code,
        is_nullable=None,
        is_excluded=is_excluded,
        is_void=is_void,
        sign=sign,
        variable_vid=None,
    )


def table_group(table_group_id, code=None, start=None):
    return TableGroupRow(
        table_group_id=table_group_id,
        code=code,
        name=None,
        type=None,
        start_release_id=start,
        end_release_id=None,
        parent_table_group_id=None,
    )


def variable_version(
    variable_vid, code=None, start=None, context_id=None,
    subcategory_vid=None,
):
    return VariableVersionRow(
        variable_vid=variable_vid,
        variable_id=None,
        property_id=None,
        subcategory_vid=subcategory_vid,
        context_id=context_id,
        key_id=None,
        is_multi_valued=None,
        code=code,
        name=None,
        start_release_id=start,
        end_release_id=None,
    )


def category(category_id, code=None, name=None, is_enumerated=None):
    return CategoryRow(
        category_id=category_id,
        code=code,
        name=name,
        is_enumerated=is_enumerated,
        is_active=True,
        created_release_id=None,
    )


def subcategory(subcategory_id, category_id=None, code=None, name=None):
    return SubCategoryRow(
        subcategory_id=subcategory_id,
        category_id=category_id,
        code=code,
        name=name,
    )


def scv(subcategory_vid, subcategory_id=None, start=None, end=None):
    return SubCategoryVersionRow(
        subcategory_vid=subcategory_vid,
        subcategory_id=subcategory_id,
        start_release_id=start,
        end_release_id=end,
    )


def sci(item_id, subcategory_vid):
    return SubCategoryItemRow(
        item_id=item_id,
        subcategory_vid=subcategory_vid,
        order=None,
        label=None,
        parent_item_id=None,
    )


def item(item_id, name=None, is_property=False):
    return ItemRow(
        item_id=item_id,
        name=name,
        is_property=is_property,
        is_active=True,
        owner_id=None,
    )


def item_category(
    item_id,
    start=CUR,
    category_id=None,
    code=None,
    end=None,
    is_default=None,
):
    return ItemCategoryRow(
        item_id=item_id,
        start_release_id=start,
        category_id=category_id,
        code=code,
        is_default_item=is_default,
        signature=None,
        end_release_id=end,
    )


def prop(property_id, data_type_id=None, is_metric=None, period_type=None):
    return PropertyRow(
        property_id=property_id,
        is_composite=None,
        is_metric=is_metric,
        data_type_id=data_type_id,
        period_type=period_type,
    )


def prop_category(property_id, start=CUR, category_id=None, end=None):
    return PropertyCategoryRow(
        property_id=property_id,
        start_release_id=start,
        category_id=category_id,
        end_release_id=end,
    )


def context_comp(context_id, property_id, item_id=None):
    return ContextCompositionRow(
        context_id=context_id,
        property_id=property_id,
        item_id=item_id,
    )


def cic(item_id, start, context_id=None):
    return CompoundItemContextRow(
        item_id=item_id,
        start_release_id=start,
        context_id=context_id,
        end_release_id=None,
    )


def scc(supercategory_id, category_id, start=None):
    return SupercategoryCompositionRow(
        supercategory_id=supercategory_id,
        category_id=category_id,
        start_release_id=start,
        end_release_id=None,
    )


def operation(operation_id, code=None):
    return OperationRow(operation_id=operation_id, code=code)


def operation_version(operation_vid, operation_id=None, start=None):
    return OperationVersionRow(
        operation_vid=operation_vid,
        operation_id=operation_id,
        start_release_id=start,
        end_release_id=None,
    )


def run(rule_id: str, **stores: List[Any]) -> List[Finding]:
    ctx = RuleContext(
        snapshot=ModelSnapshot.from_rows(**stores),
        release=ReleaseContext(
            current_release_id=CUR, draft_release_id=DRAFT
        ),
    )
    return list(REGISTRY[rule_id].fn(ctx))


def object_ids(finding: Finding) -> List[Any]:
    return [ref.id for ref in finding.objects]


# ------------------------------------------------------------------
# Registry metadata
# ------------------------------------------------------------------

ALL_RULE_IDS = (
    ["6_1", "6_2", "6_3", "6_4", "6_5", "6_6a", "6_6b", "6_7", "6_8"]
    + ["6_9", "6_10"]
    + [f"6_11{suffix}" for suffix in "abcdefghijk"]
    + ["6_12", "6_13", "6_14", "6_15", "6_16", "6_18", "6_19"]
    + ["6_20", "6_21", "6_22", "6_23", "6_24", "6_25", "6_26"]
    + ["6_27", "6_28", "6_29", "6_30", "6_31", "6_32", "6_33"]
    + ["6_34", "6_35", "6_36"]
)

WARNING_RULE_IDS = {"6_15", "6_20", "6_22", "6_35"}


def test_registry_metadata():
    assert "6_17" not in REGISTRY
    for rule_id in ALL_RULE_IDS:
        registered = REGISTRY[rule_id]
        assert registered.family == "glossary"
        expected_legacy = (
            rule_id.rstrip("abcdefghijk")
            if rule_id[-1].isalpha()
            else rule_id
        )
        assert registered.legacy_code == expected_legacy
        expected_severity = (
            SEVERITY_WARNING
            if rule_id in WARNING_RULE_IDS
            else SEVERITY_ERROR
        )
        assert registered.severity == expected_severity


# ------------------------------------------------------------------
# 6_1
# ------------------------------------------------------------------


def test_rule_6_1_fires():
    findings = run(
        "6_1",
        properties=[prop(1), prop(2)],
        header_versions=[header_version(1, start=CUR, property_id=1)],
        table_versions=[table_version(1, start=CUR, context_id=10)],
        context_compositions=[context_comp(10, property_id=2)],
        property_categories=[
            prop_category(2, start=OLD),
            prop_category(2, start=OLD - 1),
        ],
    )
    assert [object_ids(f) for f in findings] == [[1], [2]]
    assert findings[0].objects[0].kind == "property"


def test_rule_6_1_clean():
    findings = run(
        "6_1",
        properties=[prop(3), prop(4), prop(5), prop(6)],
        header_versions=[
            header_version(1, start=CUR, context_id=11),
            header_version(2, start=OLD, property_id=5),
            header_version(3, start=CUR),
        ],
        table_versions=[
            table_version(1, start=OLD, context_id=12),
            table_version(2, start=CUR, property_id=6),
            table_version(3, start=CUR),
        ],
        context_compositions=[
            context_comp(11, property_id=3),
            context_comp(12, property_id=4),
        ],
        property_categories=[
            prop_category(3),
            prop_category(3, start=OLD, end=CUR),
            prop_category(6),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_2
# ------------------------------------------------------------------


def test_rule_6_2_fires():
    findings = run(
        "6_2",
        items=[item(1), item(2)],
        properties=[prop(1)],
        subcategory_versions=[scv(100, subcategory_id=50, start=CUR)],
        subcategory_items=[sci(2, 100)],
        item_categories=[
            item_category(2, start=OLD, code="A"),
            item_category(2, start=OLD - 1, code="B"),
        ],
    )
    assert [object_ids(f) for f in findings] == [[1], [2]]
    assert findings[0].objects[0].kind == "item"


def test_rule_6_2_clean():
    findings = run(
        "6_2",
        items=[item(3), item(4), item(5), item(6)],
        variable_versions=[
            variable_version(1, start=CUR, context_id=20),
            variable_version(2, start=OLD, context_id=21),
        ],
        context_compositions=[
            context_comp(20, property_id=99, item_id=3),
            context_comp(20, property_id=98, item_id=None),
        ],
        item_categories=[
            item_category(3),
            item_category(3, start=OLD, end=CUR),
            item_category(4),
            item_category(5),
        ],
        compound_item_contexts=[cic(5, CUR), cic(6, OLD)],
        subcategory_items=[sci(6, 999), sci(6, 300)],
        subcategory_versions=[
            scv(300, subcategory_id=50, start=OLD)
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_3
# ------------------------------------------------------------------


def test_rule_6_3_fires():
    findings = run(
        "6_3",
        properties=[prop(1, data_type_id=5, is_metric=True)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[prop_category(1, category_id=70)],
        categories=[category(70, code="CAT")],
    )
    assert len(findings) == 1
    assert object_ids(findings[0]) == [1, 70]
    assert findings[0].objects[0].code == "P1"


def test_rule_6_3_clean():
    findings = run(
        "6_3",
        properties=[
            prop(2, data_type_id=1, is_metric=True),
            prop(3, data_type_id=5, is_metric=False),
            prop(4, data_type_id=None, is_metric=True),
            prop(5, data_type_id=5, is_metric=True),
        ],
        item_categories=[
            item_category(2, code="a"),
            item_category(3, code="b"),
            item_category(4, code="c"),
            item_category(5, code="d", end=CUR),
        ],
        property_categories=[
            prop_category(2, category_id=70),
            prop_category(2, category_id=None),
            prop_category(3, category_id=70),
            prop_category(4, category_id=70),
            prop_category(5, category_id=70),
        ],
        categories=[category(70, code="CAT")],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_4
# ------------------------------------------------------------------


def test_rule_6_4_fires():
    findings = run(
        "6_4",
        properties=[prop(1, data_type_id=9, is_metric=False)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[prop_category(1, category_id=70)],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [[1, 70]]


def test_rule_6_4_clean():
    findings = run(
        "6_4",
        properties=[
            prop(1, data_type_id=9, is_metric=True),
            prop(2, data_type_id=8, is_metric=False),
            prop(3, data_type_id=9, is_metric=False),
            prop(4, data_type_id=9, is_metric=False),
        ],
        item_categories=[
            item_category(1, code="a"),
            item_category(2, code="b"),
            item_category(3, code="c"),
            item_category(4, code="d", end=CUR),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=70),
            prop_category(3, category_id=70, end=CUR),
            prop_category(4, category_id=70),
        ],
        categories=[category(70, code="CAT")],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_5
# ------------------------------------------------------------------


def test_rule_6_5_fires():
    findings = run(
        "6_5",
        categories=[
            category(1, code="C1", name="Foo", is_enumerated=False),
            category(2, code="C2", name="Bar", is_enumerated=False),
        ],
        item_categories=[item_category(9, category_id=1)],
        subcategories=[subcategory(10, category_id=2)],
    )
    assert [object_ids(f) for f in findings] == [[1], [2]]


def test_rule_6_5_clean():
    findings = run(
        "6_5",
        categories=[
            category(
                3, name=" Not applicable ", is_enumerated=False
            ),
            category(4, name="Baz", is_enumerated=True),
            category(5, name=None, is_enumerated=False),
            category(6, name="Qux", is_enumerated=False),
        ],
        item_categories=[
            item_category(9, category_id=3),
            item_category(9, category_id=4),
            item_category(9, category_id=5),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_6a / 6_6b
# ------------------------------------------------------------------


def test_rule_6_6a_fires():
    findings = run(
        "6_6a",
        items=[item(1), item(2), item(3)],
        item_categories=[
            item_category(1, category_id=70, code="X"),
            item_category(2, category_id=70, code="X"),
            item_category(3, category_id=70, code=None),
        ],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [
        [1, 70],
        [2, 70],
        [3, 70],
    ]


def test_rule_6_6a_clean():
    findings = run(
        "6_6a",
        items=[item(4), item(5, is_property=True)],
        item_categories=[
            item_category(4, category_id=70, code="Y"),
            item_category(5, category_id=70, code="V"),
            item_category(4, category_id=None, code="Z"),
            item_category(99, category_id=70, code="Q"),
        ],
        categories=[category(70, code="CAT")],
    )
    assert findings == []


def test_rule_6_6b_fires():
    findings = run(
        "6_6b",
        items=[
            item(10, is_property=True),
            item(11, is_property=True),
        ],
        item_categories=[
            item_category(10, category_id=70, code="PX"),
            item_category(11, category_id=70, code="PX"),
        ],
        property_categories=[
            prop_category(10, category_id=70),
            prop_category(11, category_id=70),
        ],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [
        [10, 70],
        [11, 70],
    ]


def test_rule_6_6b_clean():
    findings = run(
        "6_6b",
        items=[
            item(12, is_property=True),
            item(13, is_property=True),
            item(14, is_property=True),
            item(15, is_property=True),
            item(16, is_property=False),
        ],
        item_categories=[
            item_category(12, category_id=70, code="PA"),
            item_category(13, category_id=70, code="PA", end=OLD),
            item_category(14, category_id=70, code="PB"),
            item_category(15, category_id=70, code="PC", end=DRAFT),
            item_category(16, category_id=70, code="PA"),
        ],
        property_categories=[
            prop_category(12, category_id=70),
            prop_category(12, category_id=None),
            prop_category(13, category_id=70),
            prop_category(15, category_id=70),
        ],
        categories=[category(70, code="CAT")],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_7
# ------------------------------------------------------------------


def test_rule_6_7_fires():
    findings = run(
        "6_7",
        properties=[prop(1, is_metric=True)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[prop_category(1, category_id=70)],
        categories=[category(70, code="CAT", is_enumerated=True)],
    )
    assert [object_ids(f) for f in findings] == [[1, 70]]


def test_rule_6_7_clean():
    findings = run(
        "6_7",
        properties=[
            prop(1, is_metric=False),
            prop(2, is_metric=True),
            prop(3, is_metric=True),
            prop(4, is_metric=True),
        ],
        item_categories=[
            item_category(1, code="a"),
            item_category(2, code="b"),
            item_category(3, code="c"),
            item_category(4, code="d", end=CUR),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=71),
            prop_category(3, category_id=70, end=CUR),
            prop_category(4, category_id=70),
        ],
        categories=[
            category(70, code="E", is_enumerated=True),
            category(71, code="N", is_enumerated=False),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_8
# ------------------------------------------------------------------


def test_rule_6_8_fires():
    findings = run(
        "6_8",
        table_versions=[
            table_version(1, code="T1", table_id=1, start=CUR)
        ],
        headers=[header(100)],
        header_versions=[
            header_version(200, header_id=100, property_id=1)
        ],
        table_version_headers=[tvh(1, 100, header_vid=200)],
        cells=[cell(500, column_id=100)],
        table_version_cells=[
            tvc(1, 500, cell_code="A1", sign="+")
        ],
        properties=[prop(1, is_metric=False)],
    )
    assert len(findings) == 1
    assert object_ids(findings[0]) == [500, 1]
    assert findings[0].objects[0].kind == "cell"
    assert findings[0].objects[1].kind == "table_version"


def test_rule_6_8_clean():
    findings = run(
        "6_8",
        table_versions=[
            table_version(1, code="T1", table_id=1, start=CUR),
            table_version(2, start=OLD),
        ],
        headers=[header(100)],
        header_versions=[
            header_version(200, header_id=100, property_id=1),
            header_version(201, header_id=100),
            header_version(202, header_id=999, property_id=2),
            header_version(203, header_id=100, property_id=77),
        ],
        table_version_headers=[
            tvh(1, 100, header_vid=200),
            tvh(1, 100, header_vid=201),
            tvh(1, 100, header_vid=202),
            tvh(1, 100, header_vid=203),
            tvh(1, 100, header_vid=None),
        ],
        cells=[cell(500, column_id=100, row_id=101)],
        table_version_cells=[
            tvc(1, 500, sign="+"),
            tvc(1, 501, sign="+"),
            tvc(1, 502, sign=None),
            tvc(1, 503, sign=""),
            tvc(1, 504, sign="+", is_void=True),
            tvc(2, 505, sign="+"),
        ],
        properties=[
            prop(1, is_metric=True),
            prop(2, is_metric=False),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_9 / 6_10
# ------------------------------------------------------------------


def test_rule_6_9_fires():
    findings = run(
        "6_9",
        categories=[
            category(1, code="C1", is_enumerated=True),
            category(2, code="C2", is_enumerated=True),
        ],
        item_categories=[
            item_category(11, category_id=2, is_default=True),
            item_category(12, category_id=2, is_default=True),
        ],
    )
    assert [object_ids(f) for f in findings] == [[1], [2]]


def test_rule_6_9_clean():
    findings = run(
        "6_9",
        categories=[
            category(3, code="C3", is_enumerated=True),
            category(4, code="_PR", is_enumerated=True),
            category(5, code="AS", is_enumerated=True),
            category(6, code=None, is_enumerated=True),
            category(7, code="C7", is_enumerated=False),
        ],
        item_categories=[
            item_category(11, category_id=3, is_default=True),
            item_category(
                12, category_id=3, is_default=True, end=CUR
            ),
            item_category(13, category_id=3, is_default=False),
            item_category(14, category_id=None, is_default=True),
        ],
    )
    assert findings == []


def test_rule_6_10_fires():
    findings = run(
        "6_10",
        categories=[category(1, code="C1", is_enumerated=True)],
        item_categories=[
            item_category(11, category_id=1, is_default=True),
            item_category(
                12, category_id=1, is_default=True, end=CUR
            ),
        ],
    )
    assert [object_ids(f) for f in findings] == [[1]]


def test_rule_6_10_clean():
    findings = run(
        "6_10",
        categories=[
            category(2, code="C2", is_enumerated=True),
            category(3, code="_TE", is_enumerated=True),
            category(4, code=None, is_enumerated=True),
            category(5, code="C5", is_enumerated=False),
        ],
        item_categories=[
            item_category(11, category_id=2, is_default=True),
            item_category(12, category_id=2, is_default=False),
            item_category(13, category_id=3, is_default=True),
            item_category(14, category_id=3, is_default=True),
            item_category(15, category_id=None, is_default=True),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_11a — framework codes
# ------------------------------------------------------------------


def test_rule_6_11a_fires():
    findings = run(
        "6_11a",
        frameworks=[framework(1, code="F X"), framework(5, code="A B")],
        modules=[module(10, framework_id=1), module(13, framework_id=5)],
        module_versions=[
            module_version(101, module_id=13, start=CUR)
        ],
    )
    assert [object_ids(f) for f in findings] == [[1], [5]]
    assert findings[0].objects[0].kind == "framework"


def test_rule_6_11a_clean():
    findings = run(
        "6_11a",
        frameworks=[
            framework(2, code="G Y"),
            framework(3, code="H Z"),
            framework(4, code="OK"),
        ],
        modules=[
            module(11, framework_id=2),
            module(14, framework_id=4),
            module(15, framework_id=None),
        ],
        module_versions=[
            module_version(100, module_id=11, start=OLD),
            module_version(102, module_id=999, start=OLD),
            module_version(103, module_id=15, start=OLD),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_11b..6_11f — simple versioned codes
# ------------------------------------------------------------------


def test_rule_6_11b_module_codes():
    findings = run(
        "6_11b",
        module_versions=[
            module_version(1, start=CUR, code="M OD"),
            module_version(2, start=DRAFT, code="D RAFT"),
            module_version(3, start=OLD, code="O LD"),
            module_version(4, start=CUR, code="MOD"),
            module_version(5, start=CUR, code=None),
        ],
    )
    assert [object_ids(f) for f in findings] == [[1], [2]]
    assert findings[0].objects[0].kind == "module_version"


def test_rule_6_11c_table_codes():
    findings = run(
        "6_11c",
        table_versions=[
            table_version(1, start=CUR, code="T 1"),
            table_version(2, start=OLD, code="T 2"),
            table_version(3, start=CUR, code="T3"),
        ],
    )
    assert [object_ids(f) for f in findings] == [[1]]
    assert findings[0].objects[0].kind == "table_version"


def test_rule_6_11d_tablegroup_codes():
    findings = run(
        "6_11d",
        table_groups=[
            table_group(1, code="G 1", start=CUR),
            table_group(2, code="G 2", start=OLD),
            table_group(3, code="G3", start=CUR),
        ],
    )
    assert [object_ids(f) for f in findings] == [[1]]
    assert findings[0].objects[0].kind == "table_group"


def test_rule_6_11e_header_codes():
    findings = run(
        "6_11e",
        header_versions=[
            header_version(1, code="H 1", start=CUR),
            header_version(2, code="H 2", start=OLD),
            header_version(3, code=None, start=CUR),
            header_version(4, code="H4", start=CUR),
        ],
    )
    assert [object_ids(f) for f in findings] == [[1]]
    assert findings[0].objects[0].kind == "header_version"


def test_rule_6_11f_variable_codes():
    findings = run(
        "6_11f",
        variable_versions=[
            variable_version(1, code="V 1", start=CUR),
            variable_version(2, code="V 2", start=OLD),
            variable_version(3, code=None, start=CUR),
            variable_version(4, code="V4", start=CUR),
        ],
    )
    assert [object_ids(f) for f in findings] == [[1]]
    assert findings[0].objects[0].kind == "variable_version"


# ------------------------------------------------------------------
# 6_11g / 6_11h — item and property codes
# ------------------------------------------------------------------


def test_rule_6_11g_item_codes():
    findings = run(
        "6_11g",
        items=[item(1), item(2, is_property=True), item(3), item(4)],
        item_categories=[
            item_category(1, category_id=70, code="I 1"),
            item_category(2, category_id=70, code="I 2"),
            item_category(3, category_id=70, code="I 3", end=CUR),
            item_category(3, category_id=70, code="I 3b", start=OLD),
            item_category(3, category_id=None, code="I 3c"),
            item_category(4, category_id=70, code=None),
            item_category(99, category_id=70, code="I 9"),
        ],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [[1, 70]]
    assert findings[0].objects[0].kind == "item"


def test_rule_6_11h_property_codes():
    findings = run(
        "6_11h",
        items=[
            item(1, is_property=True),
            item(2, is_property=True),
            item(3, is_property=False),
        ],
        item_categories=[
            item_category(1, category_id=70, code="P 1"),
            item_category(2, category_id=70, code="P 2"),
            item_category(3, category_id=70, code="P 3"),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=70, end=CUR),
        ],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [[1, 70]]
    assert findings[0].objects[0].kind == "property"


# ------------------------------------------------------------------
# 6_11i / 6_11j / 6_11k
# ------------------------------------------------------------------


def test_rule_6_11i_subcategory_codes():
    findings = run(
        "6_11i",
        subcategories=[
            subcategory(1, category_id=70, code="S 1"),
            subcategory(5, category_id=70, code="S 5"),
            subcategory(2, category_id=70, code="S 2"),
            subcategory(3, category_id=None, code="S 3"),
            subcategory(4, category_id=70, code="S4"),
        ],
        subcategory_versions=[
            scv(50, subcategory_id=5, start=CUR),
            scv(51, subcategory_id=2, start=OLD),
        ],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [[1, 70], [5, 70]]
    assert findings[0].objects[0].kind == "subcategory"


def test_rule_6_11j_category_codes():
    findings = run(
        "6_11j",
        categories=[
            category(70, code="C 1"),
            category(71, code="C 2"),
            category(72, code="C 3"),
            category(73, code="C 4"),
            category(74, code="C 5"),
            category(75, code="C 6"),
            category(76, code="C7"),
        ],
        item_categories=[
            item_category(1, category_id=71, start=OLD),
            item_category(2, category_id=70, start=CUR),
            item_category(3, category_id=None, start=OLD),
        ],
        property_categories=[
            prop_category(1, category_id=72, start=OLD),
            prop_category(2, category_id=None, start=OLD),
        ],
        subcategories=[
            subcategory(1, category_id=73),
            subcategory(2, category_id=70),
            subcategory(3, category_id=None),
        ],
        subcategory_versions=[
            scv(10, subcategory_id=1, start=OLD),
            scv(11, subcategory_id=2, start=CUR),
            scv(12, subcategory_id=999, start=OLD),
            scv(13, subcategory_id=3, start=OLD),
        ],
        supercategory_compositions=[
            scc(75, 74, start=OLD),
            scc(70, 70, start=CUR),
        ],
    )
    assert [object_ids(f) for f in findings] == [[70]]
    assert findings[0].objects[0].kind == "category"


def test_rule_6_11k_operation_codes():
    findings = run(
        "6_11k",
        operation_list=[
            operation(1, code="O P"),
            operation(5, code="O R"),
            operation(2, code="O Q"),
            operation(3, code="OQ"),
            operation(4, code=None),
        ],
        operation_versions=[
            operation_version(10, operation_id=5, start=CUR),
            operation_version(11, operation_id=2, start=OLD),
            operation_version(12, operation_id=None, start=OLD),
        ],
    )
    assert [object_ids(f) for f in findings] == [[1], [5]]
    assert findings[0].objects[0].kind == "operation"


# ------------------------------------------------------------------
# 6_12 / 6_19
# ------------------------------------------------------------------


def test_rule_6_12_fires():
    findings = run(
        "6_12",
        headers=[header(10)],
        header_versions=[
            header_version(1, header_id=10, code="A1", start=CUR)
        ],
        table_versions=[table_version(1, code="T1", start=CUR)],
        table_version_headers=[tvh(1, 10, header_vid=1)],
    )
    assert len(findings) == 1
    assert object_ids(findings[0]) == [1, 1]
    assert findings[0].objects[0].kind == "header_version"


def test_rule_6_12_clean():
    findings = run(
        "6_12",
        headers=[header(10)],
        header_versions=[
            header_version(1, header_id=10, code="01", start=CUR),
            header_version(2, header_id=10, code=None, start=CUR),
            header_version(3, header_id=10, code="A1", start=OLD),
            header_version(4, header_id=10, code="A1", start=CUR),
            header_version(5, header_id=999, code="A1", start=CUR),
            header_version(6, header_id=None, code="A1", start=CUR),
        ],
        table_versions=[
            table_version(1, start=CUR),
            table_version(2, start=CUR, end=CUR),
        ],
        table_version_headers=[
            tvh(1, 10, header_vid=1),
            tvh(1, 10, header_vid=2),
            tvh(1, 10, header_vid=3),
            tvh(2, 10, header_vid=4),
            tvh(1, 10, header_vid=5),
            tvh(1, 10, header_vid=6),
            tvh(1, 10, header_vid=None),
            tvh(999, 10, header_vid=1),
        ],
    )
    assert findings == []


def test_rule_6_19_fires():
    findings = run(
        "6_19",
        headers=[header(10)],
        header_versions=[
            header_version(
                1, header_id=10, code=None, label="L1", start=CUR
            ),
            header_version(2, header_id=10, code="  ", start=CUR),
        ],
        table_versions=[table_version(1, code="T1", start=CUR)],
        table_version_headers=[
            tvh(1, 10, header_vid=1),
            tvh(1, 10, header_vid=2),
        ],
    )
    assert [object_ids(f) for f in findings] == [[1, 1], [2, 1]]
    assert findings[0].objects[0].name == "L1"


def test_rule_6_19_clean():
    findings = run(
        "6_19",
        headers=[header(10)],
        header_versions=[
            header_version(1, header_id=10, code="1", start=CUR),
            header_version(2, header_id=10, code=None, start=OLD),
            header_version(3, header_id=10, code=None, start=CUR),
        ],
        table_versions=[
            table_version(1, start=CUR),
            table_version(2, start=CUR, end=CUR),
        ],
        table_version_headers=[
            tvh(1, 10, header_vid=1),
            tvh(1, 10, header_vid=2),
            tvh(2, 10, header_vid=3),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_13 / 6_14 / 6_16
# ------------------------------------------------------------------


def test_rule_6_13_fires():
    findings = run(
        "6_13",
        properties=[prop(1, data_type_id=5)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[prop_category(1, category_id=70)],
        categories=[category(70, code="CAT", is_enumerated=True)],
    )
    assert [object_ids(f) for f in findings] == [[1, 70]]


def test_rule_6_13_clean():
    findings = run(
        "6_13",
        properties=[
            prop(1, data_type_id=8),
            prop(2, data_type_id=None),
            prop(3, data_type_id=5),
        ],
        item_categories=[
            item_category(1, code="a"),
            item_category(2, code="b"),
            item_category(3, code="c"),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=70),
            prop_category(3, category_id=71),
        ],
        categories=[
            category(70, code="E", is_enumerated=True),
            category(71, code="N", is_enumerated=False),
        ],
    )
    assert findings == []


def test_rule_6_14_fires():
    findings = run(
        "6_14",
        properties=[prop(1, data_type_id=8)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[prop_category(1, category_id=70)],
        categories=[category(70, code="CC", is_enumerated=False)],
    )
    assert [object_ids(f) for f in findings] == [[1, 70]]


def test_rule_6_14_clean():
    findings = run(
        "6_14",
        properties=[
            prop(1, data_type_id=8),
            prop(2, data_type_id=8),
            prop(3, data_type_id=5),
            prop(4, data_type_id=8),
        ],
        item_categories=[
            item_category(1, code="a"),
            item_category(2, code="b"),
            item_category(3, code="c"),
            item_category(4, code="d"),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=71),
            prop_category(3, category_id=72),
            prop_category(4, category_id=73),
        ],
        categories=[
            category(70, code="_NA", is_enumerated=False),
            category(71, code="E", is_enumerated=True),
            category(72, code="N", is_enumerated=False),
            category(73, code=None, is_enumerated=False),
        ],
    )
    assert findings == []


def test_rule_6_16_fires():
    findings = run(
        "6_16",
        properties=[prop(1, data_type_id=None)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[prop_category(1, category_id=70)],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [[1, 70]]


def test_rule_6_16_clean():
    findings = run(
        "6_16",
        properties=[prop(1, data_type_id=5)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[prop_category(1, category_id=70)],
        categories=[category(70, code="CAT")],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_15
# ------------------------------------------------------------------


def test_rule_6_15_fires():
    findings = run(
        "6_15",
        properties=[prop(1), prop(2)],
        item_categories=[
            item_category(1, code="px123"),
            item_category(2, code="qy123"),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=70),
        ],
        categories=[category(70, code="CAT")],
    )
    assert len(findings) == 2
    assert "(123)" in (findings[0].message or "")


def test_rule_6_15_clean():
    findings = run(
        "6_15",
        properties=[
            prop(3),
            prop(4),
            prop(5),
            prop(6),
            prop(7),
        ],
        item_categories=[
            item_category(3, code="ab12"),
            item_category(4, code="abc"),
            item_category(5, code="ab"),
            item_category(6, code="zz77"),
            item_category(6, code="zy77"),
            item_category(7, code=None),
        ],
        property_categories=[
            prop_category(3, category_id=70),
            prop_category(4, category_id=70),
            prop_category(5, category_id=70),
            prop_category(6, category_id=70),
            prop_category(7, category_id=70),
        ],
        categories=[category(70, code="CAT")],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_18
# ------------------------------------------------------------------


def test_rule_6_18_fires():
    findings = run(
        "6_18",
        tables=[table(1)],
        table_versions=[
            table_version(1, code="T1", table_id=1, start=CUR)
        ],
        headers=[header(10, table_id=1)],
        header_versions=[
            header_version(
                100, header_id=10, code="H", property_id=1, start=CUR
            )
        ],
        table_version_headers=[tvh(1, 10, header_vid=100)],
        properties=[prop(1)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[prop_category(1, category_id=70)],
        categories=[category(70, code="CAT", is_enumerated=True)],
    )
    assert len(findings) == 1
    assert object_ids(findings[0]) == [100, 1, 1, 70]
    kinds = [ref.kind for ref in findings[0].objects]
    assert kinds == [
        "header_version",
        "table_version",
        "property",
        "category",
    ]


def test_rule_6_18_clean():
    findings = run(
        "6_18",
        tables=[table(1), table(2, is_abstract=True)],
        table_versions=[
            table_version(1, table_id=1, start=CUR),
            table_version(2, table_id=2, start=CUR),
            table_version(3, table_id=None, start=CUR),
            table_version(4, table_id=1, start=CUR, end=CUR),
            table_version(5, table_id=1, start=OLD),
        ],
        headers=[header(10, table_id=1)],
        header_versions=[
            header_version(
                100,
                header_id=10,
                property_id=1,
                subcategory_vid=55,
                start=CUR,
            ),
            header_version(101, header_id=10, start=CUR),
            header_version(
                102, header_id=10, property_id=999, start=CUR
            ),
            header_version(
                103, header_id=10, property_id=1, start=CUR
            ),
            header_version(
                104, header_id=10, property_id=2, start=CUR
            ),
        ],
        table_version_headers=[
            tvh(1, 10, header_vid=100),
            tvh(1, 10, header_vid=101),
            tvh(1, 10, header_vid=102),
            tvh(2, 10, header_vid=103),
            tvh(3, 10, header_vid=103),
            tvh(4, 10, header_vid=103),
            tvh(5, 10, header_vid=103),
            tvh(1, 10, header_vid=104),
        ],
        properties=[prop(1), prop(2)],
        item_categories=[
            item_category(1, code="P1"),
            item_category(2, code="P2", end=CUR),
        ],
        property_categories=[
            prop_category(1, category_id=71),
            prop_category(1, category_id=70, end=CUR),
            prop_category(1, category_id=None),
            prop_category(2, category_id=70),
        ],
        categories=[
            category(70, code="E", is_enumerated=True),
            category(71, code="N", is_enumerated=False),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_20 / 6_21
# ------------------------------------------------------------------


def test_rule_6_20_fires():
    findings = run(
        "6_20",
        datatypes=[
            datatype(1, code="m", name="Monetary"),
            datatype(2, code="s", name="String"),
        ],
        properties=[
            prop(1, data_type_id=1, period_type="stock"),
            prop(2, data_type_id=1, period_type="flow"),
            prop(3, data_type_id=1, period_type="stock"),
        ],
        item_categories=[
            item_category(1, code="si123"),
            item_category(2, code="mi123"),
            item_category(3, code="miXYZ"),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=70),
            prop_category(3, category_id=70),
        ],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [
        [1, 70],
        [2, 70],
        [3, 70],
    ]


def test_rule_6_20_clean():
    findings = run(
        "6_20",
        datatypes=[
            datatype(1, code="m", name="Monetary"),
            datatype(3, code=None),
        ],
        properties=[
            prop(4, data_type_id=1, period_type="stock"),
            prop(5, data_type_id=3, period_type="stock"),
            prop(6, data_type_id=None, period_type="stock"),
            prop(7, data_type_id=99, period_type="stock"),
            prop(8, data_type_id=1, period_type="stock"),
            prop(9, data_type_id=1, period_type="stock"),
        ],
        item_categories=[
            item_category(4, code="mi123"),
            item_category(5, code="mi123"),
            item_category(6, code="mi123"),
            item_category(7, code="mi123"),
            item_category(8, code="MI123"),
            item_category(8, code="xi123"),
            item_category(8, code="ms123"),
            item_category(8, code="ab"),
            item_category(8, code=None),
            item_category(8, code="m  "),
            item_category(9, code="mi123", start=OLD),
        ],
        property_categories=[
            prop_category(4, category_id=70),
            prop_category(5, category_id=70),
            prop_category(6, category_id=70),
            prop_category(7, category_id=70),
            prop_category(8, category_id=70),
            prop_category(9, category_id=70, start=OLD),
        ],
        categories=[category(70, code="CAT")],
    )
    assert findings == []


def test_rule_6_21_fires():
    findings = run(
        "6_21",
        properties=[prop(1)],
        item_categories=[item_category(1, code="123")],
        property_categories=[prop_category(1, category_id=70)],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [[1, 70]]


def test_rule_6_21_clean():
    findings = run(
        "6_21",
        properties=[prop(1), prop(2), prop(3)],
        item_categories=[
            item_category(1, code="A12"),
            item_category(2, code="123", start=OLD),
            item_category(3, code=None),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=70),
            prop_category(3, category_id=70),
        ],
        categories=[category(70, code="CAT")],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_22 / 6_23
# ------------------------------------------------------------------


def test_rule_6_22_fires():
    findings = run(
        "6_22",
        subcategories=[subcategory(1, category_id=70, code="S1")],
        subcategory_versions=[
            scv(100, subcategory_id=1, start=CUR)
        ],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [[1, 70]]
    assert findings[0].objects[0].kind == "subcategory"


def test_rule_6_22_clean():
    findings = run(
        "6_22",
        subcategories=[
            subcategory(1, category_id=70, code="S1"),
            subcategory(2, category_id=70, code="S2"),
            subcategory(3, category_id=70, code="S3"),
            subcategory(4, category_id=70, code="S4"),
            subcategory(5, category_id=None, code="S5"),
        ],
        subcategory_versions=[
            scv(100, subcategory_id=1, start=CUR),
            scv(101, subcategory_id=2, start=CUR),
            scv(102, subcategory_id=3, start=OLD),
            scv(103, subcategory_id=4, start=CUR, end=CUR),
            scv(104, subcategory_id=5, start=CUR),
        ],
        header_versions=[
            header_version(1, subcategory_vid=100),
            header_version(2, subcategory_vid=None),
        ],
        variable_versions=[
            variable_version(1, subcategory_vid=101),
            variable_version(2, subcategory_vid=None),
        ],
        categories=[category(70, code="CAT")],
    )
    assert findings == []


def test_rule_6_23_fires():
    findings = run(
        "6_23",
        categories=[
            category(70, code="C70"),
            category(71, code="C71"),
            category(80, code="C80"),
            category(82, code="C82"),
        ],
        subcategories=[
            subcategory(1, category_id=70, code="S1"),
            subcategory(2, category_id=80, code="S2"),
        ],
        subcategory_versions=[
            scv(100, subcategory_id=1, start=CUR),
            scv(101, subcategory_id=2, start=CUR),
        ],
        subcategory_items=[sci(5, 100), sci(6, 101)],
        item_categories=[
            item_category(5, category_id=71),
            item_category(6, category_id=82),
        ],
        supercategory_compositions=[scc(80, 81)],
    )
    assert [object_ids(f) for f in findings] == [
        [1, 70, 5, 71],
        [2, 80, 6, 82],
    ]


def test_rule_6_23_clean():
    findings = run(
        "6_23",
        categories=[
            category(70, code="C70"),
            category(80, code="C80"),
            category(81, code="C81"),
        ],
        subcategories=[
            subcategory(1, category_id=70, code="S1"),
            subcategory(2, category_id=80, code="S2"),
        ],
        subcategory_versions=[
            scv(100, subcategory_id=1, start=CUR),
            scv(101, subcategory_id=2, start=CUR),
        ],
        subcategory_items=[
            sci(7, 100),
            sci(8, 101),
            sci(9, 101),
            sci(10, 100),
            sci(11, 100),
            sci(12, 100),
        ],
        item_categories=[
            item_category(7, category_id=70),
            item_category(8, category_id=81),
            item_category(9, category_id=80),
            item_category(10, category_id=71, end=CUR),
            item_category(11, category_id=None),
        ],
        supercategory_compositions=[scc(80, 81)],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_24
# ------------------------------------------------------------------


def test_rule_6_24_fires():
    findings = run(
        "6_24",
        datatypes=[
            datatype(1, code="m", name="Monetary"),
            datatype(2, code="s", name="String"),
        ],
        properties=[
            prop(1, data_type_id=1),
            prop(2, data_type_id=2),
            prop(3, data_type_id=2),
        ],
        item_categories=[
            item_category(1, code="P1"),
            item_category(2, code="P2"),
            item_category(3, code="P3"),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=70),
            prop_category(3, category_id=70),
        ],
        categories=[
            category(70, code="CAT", is_enumerated=False)
        ],
    )
    assert len(findings) == 1
    assert object_ids(findings[0]) == [1, 70, 2]
    assert "String" in (findings[0].message or "")
    assert findings[0].objects[2].kind == "datatype"


def test_rule_6_24_clean():
    findings = run(
        "6_24",
        datatypes=[
            datatype(1, code="m", name="Monetary"),
            datatype(2, code="s", name="String"),
        ],
        properties=[
            prop(1, data_type_id=1),
            prop(2, data_type_id=2),
            prop(4, data_type_id=1),
            prop(5, data_type_id=99),
            prop(6, data_type_id=None),
        ],
        item_categories=[
            item_category(1, code="P1"),
            item_category(2, code="P2"),
            item_category(4, code="P4"),
            item_category(5, code="P5"),
            item_category(6, code="P6"),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=70, end=CUR),
            prop_category(4, category_id=70),
            prop_category(5, category_id=70),
            prop_category(6, category_id=70),
            prop_category(999, category_id=70),
            prop_category(1, category_id=None),
            prop_category(1, category_id=71),
            prop_category(1, category_id=72),
            prop_category(1, category_id=73),
        ],
        categories=[
            category(70, code="CAT", is_enumerated=False),
            category(71, code="ENU", is_enumerated=True),
            category(72, code="_NA", is_enumerated=False),
            category(73, code=None, is_enumerated=False),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_25 / 6_26 / 6_35
# ------------------------------------------------------------------


def test_rule_6_25_fires():
    findings = run(
        "6_25",
        items=[
            item(1, name="Own Funds", is_property=True),
            item(2, name="OwnFunds.", is_property=True),
        ],
        properties=[prop(1), prop(2)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=70),
        ],
        categories=[category(70, code="CAT")],
    )
    assert len(findings) == 1
    assert object_ids(findings[0]) == [1, 70]
    assert findings[0].message == (
        "Property Name is not essentially Unique within its "
        'Category: "Own Funds"'
    )


def test_rule_6_25_clean():
    findings = run(
        "6_25",
        items=[
            item(1, name="Own Funds", is_property=True),
            item(2, name="OwnFunds", is_property=True),
            item(3, name="Own Funds", is_property=False),
            item(4, name="Other", is_property=True),
            item(5, name=None, is_property=True),
            item(6, name="Own Funds", is_property=True),
            item(7, name="Own Funds", is_property=True),
            item(9, name=None, is_property=True),
        ],
        properties=[
            prop(1),
            prop(4),
            prop(5),
            prop(6),
            prop(7),
        ],
        item_categories=[
            item_category(1, code="P1"),
            item_category(4, code="P4"),
            item_category(5, code="P5"),
            item_category(6, code="P6"),
            item_category(6, start=OLD, code="P6old"),
            item_category(7, code="P7", end=CUR),
            item_category(8, code="P8"),
            item_category(9, code="P9"),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(1, category_id=None),
            prop_category(2, category_id=71),
            prop_category(3, category_id=70),
            prop_category(2, category_id=70, end=CUR),
            prop_category(9, category_id=70),
            prop_category(999, category_id=70),
        ],
        categories=[
            category(70, code="CAT"),
            category(71, code="OTHER"),
        ],
    )
    assert findings == []


def test_rule_6_26_fires():
    findings = run(
        "6_26",
        items=[
            item(1, name="Total Assets"),
            item(2, name="TotalAssets_"),
        ],
        item_categories=[
            item_category(1, category_id=70, code="I1"),
            item_category(2, category_id=70, code="I2", start=OLD),
        ],
        categories=[category(70, code="CAT")],
    )
    assert len(findings) == 1
    assert object_ids(findings[0]) == [1, 70]
    assert findings[0].message == (
        "Item Name is not essentially Unique within its Category "
        'itself: "Total Assets"'
    )


def test_rule_6_26_clean():
    findings = run(
        "6_26",
        items=[
            item(1, name="Total Assets"),
            item(2, name="Total Assets"),
            item(3, name="Different"),
            item(4, name=None),
            item(5, name="Total Assets"),
            item(6, name=None),
        ],
        item_categories=[
            item_category(1, category_id=70, code="I1"),
            item_category(2, category_id=71, code="I2", start=OLD),
            item_category(3, category_id=70, code="I3", start=OLD),
            item_category(4, category_id=70, code="I4", start=OLD),
            item_category(5, category_id=70, code="I5", end=CUR),
            item_category(
                5, category_id=70, code="I5b", start=OLD, end=OLD
            ),
            item_category(6, category_id=70, code="I6"),
            item_category(7, category_id=70, code="I7"),
            item_category(8, category_id=None, code="I8"),
        ],
        categories=[
            category(70, code="CAT"),
            category(71, code="OTHER"),
        ],
    )
    assert findings == []


def test_rule_6_35_fires():
    findings = run(
        "6_35",
        items=[
            item(1, name="Own Funds", is_property=True),
            item(2, name="own_funds", is_property=True),
        ],
        properties=[prop(1), prop(2)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=71, end=DRAFT),
        ],
        categories=[
            category(70, code="CAT"),
            category(71, code="OTHER"),
        ],
    )
    assert len(findings) == 1
    assert object_ids(findings[0]) == [1, 70]
    assert findings[0].message == (
        "Property Name is not essentially Unique across all "
        'Categories: "Own Funds"'
    )


def test_rule_6_35_clean():
    findings = run(
        "6_35",
        items=[
            item(1, name="Own Funds", is_property=True),
            item(2, name="own_funds", is_property=True),
        ],
        properties=[prop(1), prop(2)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=71, end=OLD),
        ],
        categories=[
            category(70, code="CAT"),
            category(71, code="OTHER"),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_27
# ------------------------------------------------------------------


def test_rule_6_27_fires():
    findings = run(
        "6_27",
        datatypes=[datatype(1, code="m")],
        properties=[
            prop(1, data_type_id=1, is_metric=True),
            prop(2, data_type_id=1, is_metric=True,
                 period_type="other"),
        ],
        item_categories=[
            item_category(1, code="P1"),
            item_category(2, code="P2"),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=70),
        ],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [[1, 70], [2, 70]]


def test_rule_6_27_clean():
    findings = run(
        "6_27",
        datatypes=[datatype(1, code="m")],
        properties=[
            prop(1, data_type_id=1, is_metric=True,
                 period_type="stock"),
            prop(2, data_type_id=1, is_metric=True,
                 period_type="flow"),
            prop(3, data_type_id=1, is_metric=False),
            prop(4, data_type_id=1, is_metric=True),
            prop(5, data_type_id=1, is_metric=True),
            prop(6, data_type_id=1, is_metric=True),
            prop(7, data_type_id=99, is_metric=True),
        ],
        item_categories=[
            item_category(1, code="a"),
            item_category(2, code="b"),
            item_category(3, code="c"),
            item_category(4, code="d"),
            item_category(5, code="e"),
            item_category(6, code="f", end=CUR),
            item_category(7, code="g"),
        ],
        property_categories=[
            prop_category(1, category_id=70),
            prop_category(2, category_id=70),
            prop_category(3, category_id=70),
            prop_category(4, category_id=70, start=OLD),
            prop_category(5, category_id=70, end=CUR),
            prop_category(6, category_id=70),
            prop_category(7, category_id=70),
        ],
        categories=[category(70, code="CAT")],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_28
# ------------------------------------------------------------------


def test_rule_6_28_fires():
    findings = run(
        "6_28",
        table_versions=[
            table_version(1, code="T1", table_id=1, start=OLD)
        ],
        module_versions=[
            module_version(10, module_id=1, start=CUR)
        ],
        module_version_compositions=[mvc(10, 1, table_vid=1)],
        table_version_cells=[
            tvc(1, 500, cell_code="A1", sign="+", is_void=True),
            tvc(1, 501, cell_code="A2", sign="-",
                is_excluded=True),
        ],
    )
    assert [object_ids(f) for f in findings] == [
        [500, 1],
        [501, 1],
    ]
    assert findings[0].objects[0].kind == "cell"


def test_rule_6_28_clean():
    findings = run(
        "6_28",
        table_versions=[
            table_version(1, table_id=1, start=OLD),
            table_version(2, table_id=2, start=OLD),
            table_version(3, table_id=3, start=OLD),
        ],
        module_versions=[
            module_version(10, module_id=1, start=OLD)
        ],
        module_version_compositions=[
            mvc(10, 1, table_vid=1),
            mvc(11, 2, table_vid=2),
        ],
        table_version_cells=[
            tvc(1, 500, sign="+", is_void=True),
            tvc(1, 501, sign=None, is_void=True),
            tvc(1, 502, sign="+"),
            tvc(2, 503, sign="+", is_void=True),
            tvc(3, 504, sign="+", is_void=True),
            tvc(999, 505, sign="+", is_void=True),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_29 / 6_30
# ------------------------------------------------------------------


def test_rule_6_29_fires():
    findings = run(
        "6_29",
        subcategories=[
            subcategory(1, category_id=70, code="SC"),
            subcategory(2, category_id=70, code="SC"),
        ],
        subcategory_versions=[
            scv(100, subcategory_id=1, start=CUR)
        ],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [[1, 70]]


def test_rule_6_29_clean():
    findings = run(
        "6_29",
        subcategories=[
            subcategory(1, category_id=70, code="SA"),
            subcategory(2, category_id=70, code="SB"),
            subcategory(3, category_id=70, code="SB"),
            subcategory(4, category_id=71, code="SD"),
            subcategory(5, category_id=None, code="SD"),
            subcategory(6, category_id=70, code=None),
        ],
        subcategory_versions=[
            scv(100, subcategory_id=1, start=CUR),
            scv(101, subcategory_id=2, start=OLD),
            scv(102, subcategory_id=4, start=CUR),
            scv(103, subcategory_id=None, start=CUR),
        ],
        categories=[
            category(70, code="CAT"),
            category(71, code="OTHER"),
        ],
    )
    assert findings == []


def test_rule_6_30_fires():
    findings = run(
        "6_30",
        categories=[
            category(1, code="DUP"),
            category(2, code="DUP"),
        ],
    )
    assert [object_ids(f) for f in findings] == [[1], [2]]


def test_rule_6_30_clean():
    findings = run(
        "6_30",
        categories=[
            category(1, code="A"),
            category(2, code="B"),
            category(3, code=None),
            category(4, code=None),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_31
# ------------------------------------------------------------------


def test_rule_6_31_fires():
    findings = run(
        "6_31",
        items=[item(1), item(2), item(3)],
        item_categories=[
            item_category(1, category_id=70, code="9bad"),
            item_category(2, category_id=70, code="A B"),
            item_category(3, category_id=70, code=""),
        ],
        categories=[category(70, code="CAT", is_enumerated=True)],
    )
    assert [object_ids(f) for f in findings] == [
        [1, 70],
        [2, 70],
        [3, 70],
    ]


def test_rule_6_31_clean():
    findings = run(
        "6_31",
        items=[item(1)],
        item_categories=[
            item_category(1, category_id=70, code="_OK"),
            item_category(1, category_id=70, code="Good"),
            item_category(1, category_id=70, code=None),
            item_category(1, category_id=70, code="9bad",
                          start=OLD),
            item_category(1, category_id=70, code="9bad", end=CUR),
            item_category(1, category_id=71, code="9bad"),
            item_category(1, category_id=None, code="9bad"),
        ],
        categories=[
            category(70, code="E", is_enumerated=True),
            category(71, code="N", is_enumerated=False),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_32 / 6_33
# ------------------------------------------------------------------


def test_rule_6_32_fires():
    findings = run(
        "6_32",
        subcategories=[
            subcategory(1, category_id=70, code="S1", name="Dup"),
            subcategory(2, category_id=70, code="S2", name="Dup"),
        ],
        subcategory_versions=[
            scv(100, subcategory_id=1, start=CUR)
        ],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [[1, 70]]


def test_rule_6_32_clean():
    findings = run(
        "6_32",
        subcategories=[
            subcategory(1, category_id=70, code="S1", name="Dup"),
            subcategory(2, category_id=71, code="S2", name="Dup"),
            subcategory(3, category_id=70, code="S3", name="Uniq"),
            subcategory(4, category_id=70, code="S4", name=None),
            subcategory(5, category_id=70, code="S5", name="Skip"),
        ],
        subcategory_versions=[
            scv(100, subcategory_id=1, start=CUR),
            scv(101, subcategory_id=3, start=CUR),
            scv(102, subcategory_id=4, start=CUR),
            scv(103, subcategory_id=5, start=CUR),
            scv(104, subcategory_id=5, start=OLD),
        ],
        categories=[
            category(70, code="CAT"),
            category(71, code="OTHER"),
        ],
    )
    assert findings == []


def test_rule_6_33_fires():
    findings = run(
        "6_33",
        subcategories=[subcategory(1, category_id=70, code="S1")],
        subcategory_versions=[
            scv(100, subcategory_id=1, start=CUR)
        ],
        categories=[category(70, code="CAT")],
    )
    assert [object_ids(f) for f in findings] == [[1, 70]]


def test_rule_6_33_clean():
    findings = run(
        "6_33",
        subcategories=[
            subcategory(1, category_id=70, code="S1"),
            subcategory(2, category_id=70, code="S2"),
            subcategory(3, category_id=70, code="S3"),
            subcategory(4, category_id=None, code="S4"),
        ],
        subcategory_versions=[
            scv(100, subcategory_id=1, start=CUR),
            scv(101, subcategory_id=2, start=OLD),
            scv(102, subcategory_id=3, start=CUR, end=CUR),
            scv(103, subcategory_id=4, start=CUR),
        ],
        subcategory_items=[sci(5, 100)],
        categories=[category(70, code="CAT")],
    )
    assert findings == []


# ------------------------------------------------------------------
# 6_34 / 6_36
# ------------------------------------------------------------------


def test_rule_6_34_fires():
    findings = run(
        "6_34",
        releases=[release(CUR, code="R5"), release(OLD, code="R3")],
        categories=[category(70, code="CAT")],
        subcategories=[
            subcategory(1, category_id=70, code="NEW"),
            subcategory(2, category_id=70, code="OLDSC"),
        ],
        subcategory_versions=[
            scv(10, subcategory_id=1, start=CUR),
            scv(5, subcategory_id=2, start=OLD),
        ],
        subcategory_items=[
            sci(1, 10),
            sci(2, 10),
            sci(1, 5),
            sci(2, 5),
        ],
    )
    assert len(findings) == 1
    assert object_ids(findings[0]) == [1, 2, 70]
    assert findings[0].message == (
        "SubCategory: NEW updated in release: R5 contains exactly "
        "the same Items as the existing active SubCategory: OLDSC "
        "updated in release: R3"
    )


def test_rule_6_34_clean():
    findings = run(
        "6_34",
        releases=[release(CUR, code="R5"), release(OLD, code="R3")],
        categories=[category(70, code="CAT")],
        subcategories=[
            subcategory(1, category_id=70, code="NEW"),
            subcategory(2, category_id=70, code="DIFF"),
            subcategory(3, category_id=71, code="OTHERCAT"),
            subcategory(4, category_id=70, code="LATER"),
            subcategory(5, category_id=70, code="CLOSED"),
            subcategory(6, category_id=70, code="NOREL"),
            subcategory(7, category_id=None, code="NOCAT"),
            subcategory(8, category_id=70, code="OLDSTART"),
            subcategory(9, category_id=70, code="NORELSELF"),
        ],
        subcategory_versions=[
            scv(10, subcategory_id=1, start=CUR),
            scv(5, subcategory_id=2, start=OLD),
            scv(6, subcategory_id=3, start=OLD),
            scv(20, subcategory_id=4, start=OLD),
            scv(7, subcategory_id=5, start=OLD, end=OLD),
            scv(8, subcategory_id=6, start=OLD - 1),
            scv(9, subcategory_id=7, start=CUR),
            scv(11, subcategory_id=8, start=OLD),
            scv(12, subcategory_id=9, start=DRAFT),
        ],
        subcategory_items=[
            sci(1, 10),
            sci(2, 10),
            sci(1, 5),
            sci(1, 20),
            sci(2, 20),
            sci(1, 7),
            sci(2, 7),
            sci(1, 8),
            sci(2, 8),
        ],
    )
    assert findings == []


def test_rule_6_36_fires():
    findings = run(
        "6_36",
        releases=[release(CUR, code="R5"), release(OLD, code="R3")],
        categories=[category(70, code="CAT")],
        subcategories=[subcategory(1, category_id=70, code="SC")],
        subcategory_versions=[
            scv(10, subcategory_id=1, start=CUR),
            scv(5, subcategory_id=1, start=OLD, end=CUR),
        ],
        subcategory_items=[
            sci(1, 10),
            sci(2, 10),
            sci(1, 5),
            sci(2, 5),
        ],
    )
    assert len(findings) == 1
    assert object_ids(findings[0]) == [1, 70]
    assert findings[0].message == (
        "SubCategory: SC updated in release: R5 contains exactly "
        "the same SubCategoryItems as the previous "
        "SubCategoryVersion"
    )


def test_rule_6_36_clean():
    findings = run(
        "6_36",
        releases=[release(CUR, code="R5"), release(OLD, code="R3")],
        categories=[category(70, code="CAT")],
        subcategories=[
            subcategory(1, category_id=70, code="SC"),
            subcategory(2, category_id=70, code="SD"),
            subcategory(3, category_id=70, code="SE"),
        ],
        subcategory_versions=[
            scv(10, subcategory_id=1, start=CUR),
            scv(5, subcategory_id=1, start=OLD, end=OLD),
            scv(6, subcategory_id=1, start=OLD - 1, end=CUR),
            scv(20, subcategory_id=1, start=OLD, end=CUR),
            scv(30, subcategory_id=2, start=CUR),
            scv(25, subcategory_id=2, start=OLD, end=CUR),
            scv(40, subcategory_id=3, start=DRAFT),
        ],
        subcategory_items=[
            sci(1, 10),
            sci(2, 10),
            sci(1, 6),
            sci(1, 30),
            sci(1, 25),
            sci(2, 25),
        ],
    )
    assert findings == []


# ------------------------------------------------------------------
# Defensive-guard coverage (dangling references)
# ------------------------------------------------------------------


def test_rule_6_35_skips_item_without_property_row():
    findings = run(
        "6_35",
        items=[item(1, name="Own Funds", is_property=True)],
        properties=[],
        item_categories=[item_category(1, code="P1")],
        property_categories=[prop_category(1, category_id=70)],
        categories=[category(70, code="CAT")],
    )
    assert findings == []


def test_rule_6_35_skips_dangling_property_category():
    findings = run(
        "6_35",
        items=[
            item(1, name="Own Funds", is_property=True),
            item(2, name="own_funds", is_property=True),
        ],
        properties=[prop(1), prop(2)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[
            prop_category(1, category_id=999),
            prop_category(2, category_id=71),
        ],
        categories=[category(71, code="OTHER")],
    )
    assert findings == []


def test_rule_6_34_skips_unknown_release():
    findings = run(
        "6_34",
        releases=[release(OLD, code="R3")],
        categories=[category(70, code="CAT")],
        subcategories=[
            subcategory(1, category_id=70, code="NEW"),
            subcategory(2, category_id=70, code="OLDSC"),
        ],
        subcategory_versions=[
            scv(10, subcategory_id=1, start=CUR),
            scv(5, subcategory_id=2, start=OLD),
        ],
        subcategory_items=[
            sci(1, 10),
            sci(2, 10),
            sci(1, 5),
            sci(2, 5),
        ],
    )
    assert findings == []


def test_rule_6_18_skips_closed_property_category():
    findings = run(
        "6_18",
        tables=[table(1)],
        table_versions=[
            table_version(1, code="T1", table_id=1, start=CUR)
        ],
        headers=[header(10, table_id=1)],
        header_versions=[
            header_version(
                100, header_id=10, code="H", property_id=1, start=CUR
            )
        ],
        table_version_headers=[tvh(1, 10, header_vid=100)],
        properties=[prop(1)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[
            prop_category(1, category_id=70, end=OLD)
        ],
        categories=[category(70, code="CAT", is_enumerated=True)],
    )
    assert findings == []


def test_rule_6_18_skips_dangling_category():
    findings = run(
        "6_18",
        tables=[table(1)],
        table_versions=[
            table_version(1, code="T1", table_id=1, start=CUR)
        ],
        headers=[header(10, table_id=1)],
        header_versions=[
            header_version(
                100, header_id=10, code="H", property_id=1, start=CUR
            )
        ],
        table_version_headers=[tvh(1, 10, header_vid=100)],
        properties=[prop(1)],
        item_categories=[item_category(1, code="P1")],
        property_categories=[prop_category(1, category_id=999)],
        categories=[],
    )
    assert findings == []
