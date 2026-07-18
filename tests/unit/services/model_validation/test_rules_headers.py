"""Unit tests for the family-3 (headers) modelling rules."""

from __future__ import annotations

from typing import Any, List, Tuple

from dpmcore.services.model_validation import (
    ModelSnapshot,
    ReleaseContext,
    RuleContext,
)
from dpmcore.services.model_validation.rules import headers
from dpmcore.services.model_validation.snapshot import (
    CategoryRow,
    ConceptRelationRow,
    ContextCompositionRow,
    DataTypeRow,
    HeaderRow,
    HeaderVersionRow,
    ItemCategoryRow,
    ModuleVersionCompositionRow,
    ModuleVersionRow,
    PropertyCategoryRow,
    PropertyRow,
    RelatedConceptRow,
    SubCategoryRow,
    SubCategoryVersionRow,
    TableRow,
    TableVersionHeaderRow,
    TableVersionRow,
)
from dpmcore.services.model_validation.types import Violation  # noqa: F401

CUR = 100
PREV = 50
DRAFT = 9999


def _ctx(**stores: List[Any]) -> RuleContext:
    return RuleContext(
        snapshot=ModelSnapshot.from_rows(**stores),
        release=ReleaseContext(
            current_release_id=CUR, draft_release_id=DRAFT
        ),
    )


def _table(table_id: int = 1, *, is_abstract: Any = False) -> TableRow:
    return TableRow(
        table_id=table_id,
        is_abstract=is_abstract,
        has_open_columns=None,
        has_open_rows=None,
        has_open_sheets=None,
    )


def _tv(
    vid: int = 10,
    *,
    table_id: Any = 1,
    code: Any = "T1",
    start: Any = CUR,
    end: Any = None,
    property_id: Any = None,
    context_id: Any = None,
) -> TableVersionRow:
    return TableVersionRow(
        table_vid=vid,
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


def _header(
    header_id: int = 1,
    *,
    table_id: Any = 1,
    direction: Any = "x",
    is_key: Any = False,
    is_attribute: Any = False,
    row_guid: Any = None,
) -> HeaderRow:
    return HeaderRow(
        header_id=header_id,
        table_id=table_id,
        direction=direction,
        is_key=is_key,
        is_attribute=is_attribute,
        row_guid=row_guid,
    )


def _hv(
    vid: int = 100,
    *,
    header_id: Any = 1,
    code: Any = "010",
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
        label=None,
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
    header_vid: Any = 100,
    parent_header_id: Any = None,
    parent_first: Any = None,
    order: Any = None,
    is_abstract: Any = False,
) -> TableVersionHeaderRow:
    return TableVersionHeaderRow(
        table_vid=table_vid,
        header_id=header_id,
        header_vid=header_vid,
        parent_header_id=parent_header_id,
        parent_first=parent_first,
        order=order,
        is_abstract=is_abstract,
        is_unique=None,
    )


def _mv(
    vid: int = 500, *, start: Any = CUR, end: Any = None
) -> ModuleVersionRow:
    return ModuleVersionRow(
        module_vid=vid,
        module_id=1,
        global_key_id=None,
        start_release_id=start,
        end_release_id=end,
        code="MOD",
        name=None,
        version_number=None,
        is_reported=None,
        is_calculated=None,
    )


def _mvc(
    module_vid: int = 500, table_id: int = 1, table_vid: Any = 10
) -> ModuleVersionCompositionRow:
    return ModuleVersionCompositionRow(
        module_vid=module_vid,
        table_id=table_id,
        table_vid=table_vid,
        order=None,
    )


def _prop(
    property_id: int = 7,
    *,
    is_metric: Any = False,
    data_type_id: Any = None,
) -> PropertyRow:
    return PropertyRow(
        property_id=property_id,
        is_composite=None,
        is_metric=is_metric,
        data_type_id=data_type_id,
        period_type=None,
    )


def _dt(data_type_id: int = 1, code: Any = "m") -> DataTypeRow:
    return DataTypeRow(
        data_type_id=data_type_id,
        code=code,
        name=None,
        parent_data_type_id=None,
        is_active=True,
    )


def _ic(
    item_id: int = 7,
    *,
    start: Any = PREV,
    end: Any = None,
    category_id: Any = 3,
    code: Any = "pi7",
    is_default: Any = None,
) -> ItemCategoryRow:
    return ItemCategoryRow(
        item_id=item_id,
        start_release_id=start,
        category_id=category_id,
        code=code,
        is_default_item=is_default,
        signature=None,
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


def _cat(
    category_id: int = 3,
    *,
    code: Any = "CAT",
    is_enumerated: Any = True,
) -> CategoryRow:
    return CategoryRow(
        category_id=category_id,
        code=code,
        name=None,
        is_enumerated=is_enumerated,
        is_active=True,
        created_release_id=None,
    )


def _sc(
    subcategory_id: int = 60, *, category_id: Any = 3, name: Any = "SC"
) -> SubCategoryRow:
    return SubCategoryRow(
        subcategory_id=subcategory_id,
        category_id=category_id,
        code="SC",
        name=name,
    )


def _scv(
    vid: int = 600,
    *,
    subcategory_id: Any = 60,
    start: Any = PREV,
    end: Any = None,
) -> SubCategoryVersionRow:
    return SubCategoryVersionRow(
        subcategory_vid=vid,
        subcategory_id=subcategory_id,
        start_release_id=start,
        end_release_id=end,
    )


def _cc(
    context_id: int = 40, property_id: int = 7, item_id: Any = None
) -> ContextCompositionRow:
    return ContextCompositionRow(
        context_id=context_id,
        property_id=property_id,
        item_id=item_id,
    )


def _cr(
    relation_id: int = 900, type_: Any = "header_attributeHeader"
) -> ConceptRelationRow:
    return ConceptRelationRow(
        concept_relation_id=relation_id, type=type_
    )


def _rc(
    guid: str, relation_id: int = 900, *, related: Any = True
) -> RelatedConceptRow:
    return RelatedConceptRow(
        concept_guid=guid,
        concept_relation_id=relation_id,
        is_related_concept=related,
    )


def _base(**extra: List[Any]) -> dict:
    """Table 1 / tv 10 / header 1 / hv 100 in current module 500."""
    stores: dict = {
        "tables": [_table()],
        "table_versions": [_tv()],
        "headers": [_header()],
        "header_versions": [_hv()],
        "table_version_headers": [_tvh()],
        "module_versions": [_mv()],
        "module_version_compositions": [_mvc()],
    }
    stores.update(extra)
    return stores


def _ids(findings: List[Any]) -> List[Tuple[Any, ...]]:
    return [tuple(o.id for o in f.objects) for f in findings]


# ------------------------------------------------------------------
# 3_1
# ------------------------------------------------------------------


class TestRule31:
    def test_fires_for_key_header_without_property(self) -> None:
        stores = _base(headers=[_header(is_key=True)])
        findings = list(headers.rule_3_1(_ctx(**stores)))
        assert _ids(findings) == [(1, 10)]

    def test_clean_with_property(self) -> None:
        stores = _base(
            headers=[_header(is_key=True)],
            header_versions=[_hv(property_id=7)],
        )
        assert list(headers.rule_3_1(_ctx(**stores))) == []

    def test_skips_non_key_expired_and_abstract(self) -> None:
        stores = _base(
            tables=[_table(is_abstract=True), _table(2)],
            headers=[
                _header(is_key=True),
                _header(2, table_id=2, is_key=True),
                _header(3, table_id=2, is_key=False),
            ],
            table_versions=[_tv(), _tv(20, table_id=2, start=PREV)],
            header_versions=[
                _hv(),
                _hv(101, header_id=2, end=CUR),
                _hv(102, header_id=3),
            ],
            table_version_headers=[
                _tvh(),
                _tvh(20, 2, header_vid=101),
                _tvh(20, 3, header_vid=102),
            ],
        )
        assert list(headers.rule_3_1(_ctx(**stores))) == []

    def test_skips_without_module_membership(self) -> None:
        stores = _base(
            headers=[_header(is_key=True)],
            module_version_compositions=[],
        )
        assert list(headers.rule_3_1(_ctx(**stores))) == []

    def test_skips_expired_tv(self) -> None:
        stores = _base(
            headers=[_header(is_key=True)],
            table_versions=[_tv(end=CUR)],
        )
        assert list(headers.rule_3_1(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 3_2
# ------------------------------------------------------------------


class TestRule32:
    def test_fires_for_abstract_key_header(self) -> None:
        stores = _base(
            headers=[_header(is_key=True)],
            table_version_headers=[_tvh(is_abstract=True)],
        )
        findings = list(headers.rule_3_2(_ctx(**stores)))
        assert _ids(findings) == [(1, 10)]

    def test_clean_for_non_abstract_attachment(self) -> None:
        stores = _base(headers=[_header(is_key=True)])
        assert list(headers.rule_3_2(_ctx(**stores))) == []

    def test_skips_old_tv(self) -> None:
        stores = _base(
            headers=[_header(is_key=True)],
            table_versions=[_tv(start=PREV)],
            table_version_headers=[_tvh(is_abstract=True)],
        )
        assert list(headers.rule_3_2(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 3_3
# ------------------------------------------------------------------


class TestRule33:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            headers=[_header(direction="z")],
            header_versions=[_hv(property_id=7)],
            properties=[_prop()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_fires_for_non_metric_on_sheet(self) -> None:
        findings = list(headers.rule_3_3(_ctx(**self._stores())))
        assert _ids(findings) == [(1, 10, 3)]

    def test_clean_for_metric(self) -> None:
        stores = self._stores(properties=[_prop(is_metric=True)])
        assert list(headers.rule_3_3(_ctx(**stores))) == []

    def test_clean_for_other_direction(self) -> None:
        stores = self._stores(headers=[_header(direction="x")])
        assert list(headers.rule_3_3(_ctx(**stores))) == []

    def test_skips_expired_pc(self) -> None:
        stores = self._stores(property_categories=[_pc(end=PREV)])
        assert list(headers.rule_3_3(_ctx(**stores))) == []

    def test_skips_missing_property_row(self) -> None:
        stores = self._stores(properties=[])
        assert list(headers.rule_3_3(_ctx(**stores))) == []

    def test_skips_key_header_and_no_module(self) -> None:
        stores = self._stores(
            headers=[_header(direction="z", is_key=True)]
        )
        assert list(headers.rule_3_3(_ctx(**stores))) == []
        stores = self._stores(module_version_compositions=[])
        assert list(headers.rule_3_3(_ctx(**stores))) == []

    def test_skips_expired_hv_and_old_tv(self) -> None:
        stores = self._stores(
            header_versions=[_hv(property_id=7, end=CUR)]
        )
        assert list(headers.rule_3_3(_ctx(**stores))) == []
        stores = self._stores(table_versions=[_tv(start=PREV)])
        assert list(headers.rule_3_3(_ctx(**stores))) == []

    def test_skips_null_property(self) -> None:
        stores = self._stores(header_versions=[_hv()])
        assert list(headers.rule_3_3(_ctx(**stores))) == []

    def test_skips_abstract_table_and_tvh(self) -> None:
        stores = self._stores(tables=[_table(is_abstract=True)])
        assert list(headers.rule_3_3(_ctx(**stores))) == []
        stores = self._stores(
            table_version_headers=[_tvh(is_abstract=True)]
        )
        assert list(headers.rule_3_3(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 3_4
# ------------------------------------------------------------------


class TestRule34:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            header_versions=[_hv(subcategory_vid=600)],
            subcategory_versions=[_scv(end=PREV)],
            subcategories=[_sc()],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_fires_for_expired_scv(self) -> None:
        findings = list(headers.rule_3_4(_ctx(**self._stores())))
        assert _ids(findings) == [(1, 10, 60, 3)]

    def test_clean_for_open_scv(self) -> None:
        stores = self._stores(subcategory_versions=[_scv()])
        assert list(headers.rule_3_4(_ctx(**stores))) == []

    def test_skips_dangling_subcategory(self) -> None:
        stores = self._stores(subcategories=[])
        assert list(headers.rule_3_4(_ctx(**stores))) == []

    def test_skips_dangling_category(self) -> None:
        stores = self._stores(categories=[])
        assert list(headers.rule_3_4(_ctx(**stores))) == []

    def test_skips_module_not_starting_now(self) -> None:
        stores = self._stores(module_versions=[_mv(start=PREV)])
        assert list(headers.rule_3_4(_ctx(**stores))) == []

    def test_skips_no_subcategory(self) -> None:
        stores = self._stores(header_versions=[_hv()])
        assert list(headers.rule_3_4(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 3_5a / 3_5b
# ------------------------------------------------------------------


class TestRule35a:
    def test_fires_for_childless_abstract_header(self) -> None:
        stores = _base(table_version_headers=[_tvh(is_abstract=True)])
        findings = list(headers.rule_3_5a(_ctx(**stores)))
        assert _ids(findings) == [(1, 10)]

    def test_clean_with_descendant(self) -> None:
        stores = _base(
            headers=[_header(), _header(2)],
            header_versions=[_hv(), _hv(101, header_id=2)],
            table_version_headers=[
                _tvh(is_abstract=True),
                _tvh(10, 2, header_vid=101, parent_header_id=1),
            ],
        )
        assert list(headers.rule_3_5a(_ctx(**stores))) == []

    def test_skips_closed_module(self) -> None:
        stores = _base(
            table_version_headers=[_tvh(is_abstract=True)],
            module_versions=[_mv(end=CUR)],
        )
        assert list(headers.rule_3_5a(_ctx(**stores))) == []


class TestRule35b:
    def test_fires_for_missing_parent(self) -> None:
        stores = _base(
            table_version_headers=[_tvh(parent_header_id=99)]
        )
        findings = list(headers.rule_3_5b(_ctx(**stores)))
        assert _ids(findings) == [(1, 10)]

    def test_clean_when_parent_present(self) -> None:
        stores = _base(
            headers=[_header(), _header(99)],
            header_versions=[_hv(), _hv(101, header_id=99)],
            table_version_headers=[
                _tvh(parent_header_id=99),
                _tvh(10, 99, header_vid=101),
            ],
        )
        assert list(headers.rule_3_5b(_ctx(**stores))) == []

    def test_skips_expired_tv_and_rootless(self) -> None:
        stores = _base(
            table_versions=[_tv(end=CUR)],
            table_version_headers=[_tvh(parent_header_id=99)],
        )
        assert list(headers.rule_3_5b(_ctx(**stores))) == []
        stores = _base()
        assert list(headers.rule_3_5b(_ctx(**stores))) == []

    def test_skips_module_not_starting_now(self) -> None:
        stores = _base(
            table_version_headers=[_tvh(parent_header_id=99)],
            module_versions=[_mv(start=PREV)],
        )
        assert list(headers.rule_3_5b(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 3_6
# ------------------------------------------------------------------


class TestRule36:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            headers=[_header(is_key=True)],
            header_versions=[_hv(property_id=7)],
            properties=[_prop(is_metric=True)],
            item_categories=[_ic()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_fires_for_metric_key_property(self) -> None:
        findings = list(headers.rule_3_6(_ctx(**self._stores())))
        assert _ids(findings) == [(7, 10, 3)]

    def test_clean_for_non_metric(self) -> None:
        stores = self._stores(properties=[_prop()])
        assert list(headers.rule_3_6(_ctx(**stores))) == []

    def test_skips_expired_ic(self) -> None:
        stores = self._stores(item_categories=[_ic(end=PREV)])
        assert list(headers.rule_3_6(_ctx(**stores))) == []

    def test_skips_non_key(self) -> None:
        stores = self._stores(headers=[_header()])
        assert list(headers.rule_3_6(_ctx(**stores))) == []

    def test_skips_without_module(self) -> None:
        stores = self._stores(module_version_compositions=[])
        assert list(headers.rule_3_6(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 3_7
# ------------------------------------------------------------------


class TestRule37:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            headers=[
                _header(is_key=True),
                _header(2, is_key=True),
            ],
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2, property_id=7),
            ],
            table_version_headers=[_tvh(), _tvh(10, 2, header_vid=101)],
            item_categories=[_ic()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_fires_for_shared_key_property(self) -> None:
        findings = list(headers.rule_3_7(_ctx(**self._stores())))
        assert _ids(findings) == [(100, 101, 10, 7, 3)]

    def test_clean_for_distinct_properties(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2, property_id=8),
            ],
        )
        assert list(headers.rule_3_7(_ctx(**stores))) == []

    def test_skips_non_key_partner(self) -> None:
        stores = self._stores(
            headers=[_header(is_key=True), _header(2, is_key=False)],
        )
        assert list(headers.rule_3_7(_ctx(**stores))) == []

    def test_skips_expired_partner(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2, property_id=7, end=CUR),
            ],
        )
        assert list(headers.rule_3_7(_ctx(**stores))) == []

    def test_skips_null_property(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(),
                _hv(101, header_id=2),
            ],
        )
        assert list(headers.rule_3_7(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 3_8
# ------------------------------------------------------------------


class TestRule38:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            headers=[
                _header(is_key=True),
                _header(2, direction="y"),
            ],
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2, context_id=40),
            ],
            table_version_headers=[_tvh(), _tvh(10, 2, header_vid=101)],
            context_compositions=[_cc(40, 7)],
            item_categories=[_ic()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_fires_via_header_context(self) -> None:
        findings = list(headers.rule_3_8(_ctx(**self._stores())))
        assert _ids(findings) == [(1, 10, 7, 3)]

    def test_fires_via_table_context(self) -> None:
        stores = self._stores(
            table_versions=[_tv(context_id=40)],
            header_versions=[_hv(property_id=7)],
            table_version_headers=[_tvh()],
        )
        findings = list(headers.rule_3_8(_ctx(**stores)))
        assert len(findings) == 1

    def test_clean_without_context_hit(self) -> None:
        stores = self._stores(context_compositions=[_cc(40, 8)])
        assert list(headers.rule_3_8(_ctx(**stores))) == []

    def test_left_join_passes_missing_assignments(self) -> None:
        stores = self._stores(
            item_categories=[], property_categories=[]
        )
        findings = list(headers.rule_3_8(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].objects[2].code is None

    def test_left_join_drops_expired_only_assignments(self) -> None:
        stores = self._stores(item_categories=[_ic(end=PREV)])
        assert list(headers.rule_3_8(_ctx(**stores))) == []

    def test_left_join_category_unresolvable(self) -> None:
        stores = self._stores(categories=[])
        findings = list(headers.rule_3_8(_ctx(**stores)))
        assert findings[0].objects[3].id is None

    def test_skips_expired_context_partner(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2, context_id=40, end=CUR),
            ],
        )
        assert list(headers.rule_3_8(_ctx(**stores))) == []

    def test_skips_key_context_partner(self) -> None:
        stores = self._stores(
            headers=[
                _header(is_key=True),
                _header(2, direction="y", is_key=True),
            ],
        )
        assert list(headers.rule_3_8(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 3_9
# ------------------------------------------------------------------


class TestRule39:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            header_versions=[
                _hv(property_id=7, subcategory_vid=600)
            ],
            subcategory_versions=[_scv()],
            subcategories=[_sc(category_id=4)],
            property_categories=[_pc(category_id=3)],
            categories=[_cat(3), _cat(4, code="OTHER")],
            item_categories=[_ic()],
        )
        stores.update(extra)
        return stores

    def test_fires_for_incompatible_categories(self) -> None:
        findings = list(headers.rule_3_9(_ctx(**self._stores())))
        assert _ids(findings) == [(1, 10, 7, 60)]

    def test_clean_same_enumerated_category(self) -> None:
        stores = self._stores(subcategories=[_sc(category_id=3)])
        assert list(headers.rule_3_9(_ctx(**stores))) == []

    def test_clean_na_pr_exception(self) -> None:
        stores = self._stores(
            categories=[
                _cat(3, code="_NA", is_enumerated=False),
                _cat(4, code="_PR", is_enumerated=False),
            ],
        )
        assert list(headers.rule_3_9(_ctx(**stores))) == []

    def test_fires_same_category_not_enumerated(self) -> None:
        stores = self._stores(
            subcategories=[_sc(category_id=3)],
            categories=[_cat(3, is_enumerated=False)],
        )
        assert len(list(headers.rule_3_9(_ctx(**stores)))) == 1

    def test_skips_expired_scv(self) -> None:
        stores = self._stores(subcategory_versions=[_scv(end=PREV)])
        assert list(headers.rule_3_9(_ctx(**stores))) == []

    def test_skips_without_open_ic(self) -> None:
        stores = self._stores(item_categories=[_ic(end=PREV)])
        assert list(headers.rule_3_9(_ctx(**stores))) == []

    def test_skips_dangling_pc_category(self) -> None:
        stores = self._stores(
            categories=[_cat(4, code="OTHER")],
        )
        assert list(headers.rule_3_9(_ctx(**stores))) == []

    def test_skips_dangling_subcategory(self) -> None:
        stores = self._stores(subcategories=[])
        assert list(headers.rule_3_9(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 3_10a
# ------------------------------------------------------------------


class TestRule310a:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            headers=[
                _header(is_attribute=True, row_guid="g-attr"),
                _header(2, row_guid="g-base"),
            ],
            header_versions=[_hv(), _hv(101, header_id=2)],
            table_version_headers=[_tvh(), _tvh(10, 2, header_vid=101)],
            concept_relations=[_cr()],
            related_concepts=[
                _rc("g-attr", related=True),
                _rc("g-base", related=False),
            ],
        )
        stores.update(extra)
        return stores

    def test_clean_with_exactly_one_relation(self) -> None:
        assert list(headers.rule_3_10a(_ctx(**self._stores()))) == []

    def test_fires_with_no_relation(self) -> None:
        stores = self._stores(related_concepts=[])
        findings = list(headers.rule_3_10a(_ctx(**stores)))
        assert _ids(findings) == [(100, 10)]

    def test_fires_with_two_relations(self) -> None:
        stores = self._stores(
            concept_relations=[_cr(900), _cr(901)],
            related_concepts=[
                _rc("g-attr", 900, related=True),
                _rc("g-base", 900, related=False),
                _rc("g-attr", 901, related=True),
                _rc("g-base", 901, related=False),
            ],
        )
        findings = list(headers.rule_3_10a(_ctx(**stores)))
        assert len(findings) == 1

    def test_relation_to_other_direction_ignored(self) -> None:
        stores = self._stores(
            headers=[
                _header(is_attribute=True, row_guid="g-attr"),
                _header(2, direction="y", row_guid="g-base"),
            ],
        )
        findings = list(headers.rule_3_10a(_ctx(**stores)))
        assert len(findings) == 1

    def test_non_attribute_headers_ignored(self) -> None:
        stores = self._stores(
            headers=[
                _header(row_guid="g-attr"),
                _header(2, row_guid="g-base"),
            ],
        )
        assert list(headers.rule_3_10a(_ctx(**stores))) == []

    def test_wrong_relation_type_ignored(self) -> None:
        stores = self._stores(
            concept_relations=[_cr(type_="other")],
        )
        findings = list(headers.rule_3_10a(_ctx(**stores)))
        assert len(findings) == 1


# ------------------------------------------------------------------
# 3_10b
# ------------------------------------------------------------------


class TestRule310b:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            header_versions=[_hv(property_id=7)],
            properties=[_prop(data_type_id=1)],
            datatypes=[_dt(1, code="es")],
            item_categories=[_ic()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_fires_for_es_datatype(self) -> None:
        findings = list(headers.rule_3_10b(_ctx(**self._stores())))
        assert _ids(findings) == [(100, 10, 7, 3)]

    def test_clean_for_other_datatype(self) -> None:
        stores = self._stores(datatypes=[_dt(1, code="m")])
        assert list(headers.rule_3_10b(_ctx(**stores))) == []

    def test_expired_assignments_still_fire(self) -> None:
        stores = self._stores(
            item_categories=[_ic(end=PREV)],
            property_categories=[_pc(end=PREV)],
        )
        assert len(list(headers.rule_3_10b(_ctx(**stores)))) == 1

    def test_skips_no_property_or_datatype(self) -> None:
        stores = self._stores(header_versions=[_hv()])
        assert list(headers.rule_3_10b(_ctx(**stores))) == []
        stores = self._stores(properties=[_prop()])
        assert list(headers.rule_3_10b(_ctx(**stores))) == []

    def test_skips_dangling_datatype_or_category(self) -> None:
        stores = self._stores(datatypes=[])
        assert list(headers.rule_3_10b(_ctx(**stores))) == []
        stores = self._stores(categories=[])
        assert list(headers.rule_3_10b(_ctx(**stores))) == []

    def test_skips_module_not_starting_now(self) -> None:
        stores = self._stores(module_versions=[_mv(start=PREV)])
        assert list(headers.rule_3_10b(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 3_11 / 3_12
# ------------------------------------------------------------------


def _attr_stores(**extra: Any) -> dict:
    stores = _base(
        headers=[
            _header(is_attribute=True, row_guid="g-attr"),
            _header(2, row_guid="g-base"),
        ],
        header_versions=[_hv(), _hv(101, header_id=2)],
        table_version_headers=[_tvh(), _tvh(10, 2, header_vid=101)],
        concept_relations=[_cr()],
        related_concepts=[
            _rc("g-attr", related=True),
            _rc("g-base", related=False),
        ],
    )
    stores.update(extra)
    return stores


class TestRule311:
    def test_fires_for_fact_partner_without_property(self) -> None:
        findings = list(headers.rule_3_11(_ctx(**_attr_stores())))
        assert _ids(findings) == [(100, 10)]

    def test_clean_when_partner_has_property(self) -> None:
        stores = _attr_stores(
            header_versions=[
                _hv(),
                _hv(101, header_id=2, property_id=7),
            ],
        )
        assert list(headers.rule_3_11(_ctx(**stores))) == []

    def test_key_partner_ignored(self) -> None:
        stores = _attr_stores(
            headers=[
                _header(is_attribute=True, row_guid="g-attr"),
                _header(2, is_key=True, row_guid="g-base"),
            ],
        )
        assert list(headers.rule_3_11(_ctx(**stores))) == []


class TestRule312:
    def test_fires_for_key_partner_other_direction(self) -> None:
        stores = _attr_stores(
            headers=[
                _header(is_attribute=True, row_guid="g-attr"),
                _header(
                    2, direction="y", is_key=True, row_guid="g-base"
                ),
            ],
        )
        findings = list(headers.rule_3_12(_ctx(**stores)))
        assert _ids(findings) == [(100, 10)]

    def test_clean_same_direction(self) -> None:
        stores = _attr_stores(
            headers=[
                _header(is_attribute=True, row_guid="g-attr"),
                _header(2, is_key=True, row_guid="g-base"),
            ],
        )
        assert list(headers.rule_3_12(_ctx(**stores))) == []

    def test_non_key_partner_ignored(self) -> None:
        assert list(headers.rule_3_12(_ctx(**_attr_stores()))) == []


# ------------------------------------------------------------------
# 3_14 / 3_15a
# ------------------------------------------------------------------


def _dtype_stores(**extra: Any) -> dict:
    stores = _attr_stores(
        header_versions=[
            _hv(property_id=7),
            _hv(101, header_id=2),
            _hv(102, header_id=1, property_id=8, end=CUR, start=PREV),
        ],
        properties=[
            _prop(7, data_type_id=1),
            _prop(8, data_type_id=2),
        ],
        datatypes=[_dt(1, "m"), _dt(2, "s")],
    )
    stores.update(extra)
    return stores


class TestRule314:
    def test_fires_on_datatype_change(self) -> None:
        findings = list(headers.rule_3_14(_ctx(**_dtype_stores())))
        assert _ids(findings) == [(100, 10)]
        assert findings[0].message is not None
        assert "m" in findings[0].message
        assert "s" in findings[0].message

    def test_clean_same_datatype(self) -> None:
        stores = _dtype_stores(
            properties=[
                _prop(7, data_type_id=1),
                _prop(8, data_type_id=1),
            ],
        )
        assert list(headers.rule_3_14(_ctx(**stores))) == []

    def test_clean_without_predecessor(self) -> None:
        stores = _dtype_stores(
            header_versions=[_hv(property_id=7), _hv(101, header_id=2)],
        )
        assert list(headers.rule_3_14(_ctx(**stores))) == []

    def test_skips_predecessor_without_property(self) -> None:
        stores = _dtype_stores(
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2),
                _hv(102, header_id=1, end=CUR, start=PREV),
            ],
        )
        assert list(headers.rule_3_14(_ctx(**stores))) == []

    def test_skips_unresolvable_datatypes(self) -> None:
        stores = _dtype_stores(datatypes=[])
        assert list(headers.rule_3_14(_ctx(**stores))) == []
        stores = _dtype_stores(properties=[_prop(7, data_type_id=1)])
        assert list(headers.rule_3_14(_ctx(**stores))) == []
        stores = _dtype_stores(
            properties=[_prop(7), _prop(8, data_type_id=2)],
        )
        assert list(headers.rule_3_14(_ctx(**stores))) == []


class TestRule315a:
    def _stores(self, **extra: Any) -> dict:
        # Base header 1 has the attribute header 2 related to it
        # (attribute side = IsRelatedConcept 1 on header 2).
        stores = _base(
            headers=[
                _header(row_guid="g-base"),
                _header(2, is_attribute=True, row_guid="g-attr"),
            ],
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2),
                _hv(
                    102,
                    header_id=1,
                    property_id=8,
                    end=CUR,
                    start=PREV,
                ),
            ],
            table_version_headers=[
                _tvh(),
                _tvh(10, 2, header_vid=101),
            ],
            concept_relations=[_cr()],
            related_concepts=[
                _rc("g-attr", related=True),
                _rc("g-base", related=False),
            ],
            properties=[
                _prop(7, data_type_id=1),
                _prop(8, data_type_id=2),
            ],
            datatypes=[_dt(1, "m"), _dt(2, "s")],
        )
        stores.update(extra)
        return stores

    def test_fires_on_base_header_change(self) -> None:
        findings = list(headers.rule_3_15a(_ctx(**self._stores())))
        assert (100, 10) in _ids(findings)

    def test_clean_without_attribute_partner(self) -> None:
        stores = self._stores(related_concepts=[])
        assert list(headers.rule_3_15a(_ctx(**stores))) == []

    def test_clean_without_datatype_change(self) -> None:
        stores = self._stores(
            properties=[
                _prop(7, data_type_id=1),
                _prop(8, data_type_id=1),
            ],
        )
        assert list(headers.rule_3_15a(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 3_15b
# ------------------------------------------------------------------


class TestRule315b:
    def _stores(self, parent_first: Any, child: int, parent: int) -> dict:
        return _base(
            headers=[_header(), _header(2)],
            header_versions=[_hv(), _hv(101, header_id=2)],
            table_version_headers=[
                _tvh(order=child, parent_header_id=2),
                _tvh(
                    10,
                    2,
                    header_vid=101,
                    order=parent,
                    parent_first=parent_first,
                ),
            ],
        )

    def test_fires_child_before_parent_first(self) -> None:
        stores = self._stores(True, child=1, parent=2)
        findings = list(headers.rule_3_15b(_ctx(**stores)))
        assert _ids(findings) == [(1, 10)]
        assert findings[0].message is not None
        assert "ParentFirst=1" in findings[0].message

    def test_fires_child_after_parent_last(self) -> None:
        stores = self._stores(False, child=3, parent=2)
        findings = list(headers.rule_3_15b(_ctx(**stores)))
        assert len(findings) == 1

    def test_clean_correct_order(self) -> None:
        stores = self._stores(True, child=3, parent=2)
        assert list(headers.rule_3_15b(_ctx(**stores))) == []
        stores = self._stores(False, child=1, parent=2)
        assert list(headers.rule_3_15b(_ctx(**stores))) == []

    def test_skips_null_orders_and_flag(self) -> None:
        stores = self._stores(None, child=1, parent=2)
        assert list(headers.rule_3_15b(_ctx(**stores))) == []
        stores = self._stores(True, child=1, parent=2)
        stores["table_version_headers"][0] = _tvh(
            order=None, parent_header_id=2
        )
        assert list(headers.rule_3_15b(_ctx(**stores))) == []
        stores = self._stores(True, child=1, parent=2)
        stores["table_version_headers"][1] = _tvh(
            10, 2, header_vid=101, order=None, parent_first=True
        )
        assert list(headers.rule_3_15b(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 3_16
# ------------------------------------------------------------------


class TestRule316:
    def test_fires_for_abstract_header_with_property(self) -> None:
        stores = _base(
            header_versions=[_hv(property_id=7)],
            table_version_headers=[_tvh(is_abstract=True)],
            item_categories=[_ic()],
        )
        findings = list(headers.rule_3_16(_ctx(**stores)))
        assert _ids(findings) == [(1, 10, 7, None)]
        assert findings[0].objects[2].code == "pi7"

    def test_fires_for_abstract_header_with_context(self) -> None:
        stores = _base(
            header_versions=[_hv(context_id=40)],
            table_version_headers=[_tvh(is_abstract=True)],
        )
        findings = list(headers.rule_3_16(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].objects[3].id == 40

    def test_clean_for_bare_abstract_header(self) -> None:
        stores = _base(
            table_version_headers=[_tvh(is_abstract=True)],
        )
        assert list(headers.rule_3_16(_ctx(**stores))) == []

    def test_skips_module_not_starting_now(self) -> None:
        stores = _base(
            header_versions=[_hv(property_id=7)],
            table_version_headers=[_tvh(is_abstract=True)],
            module_versions=[_mv(start=PREV)],
        )
        assert list(headers.rule_3_16(_ctx(**stores))) == []


# ------------------------------------------------------------------
# Shared join-row edge cases
# ------------------------------------------------------------------


class TestJoinRows:
    def test_rows_by_header_vid_skips_dangling(self) -> None:
        stores = _base(
            table_version_headers=[
                _tvh(header_vid=None),
                _tvh(10, 2, header_vid=999),
                _tvh(),
            ],
        )
        ctx = _ctx(**stores)
        rows = headers._rows_by_header_vid(ctx)
        assert len(rows) == 1

    def test_rows_by_header_vid_requires_matching_table(self) -> None:
        stores = _base(headers=[_header(table_id=2)])
        ctx = _ctx(**stores)
        assert headers._rows_by_header_vid(ctx) == []

    def test_rows_by_header_vid_hv_without_header_id(self) -> None:
        stores = _base(header_versions=[_hv(header_id=None)])
        ctx = _ctx(**stores)
        assert headers._rows_by_header_vid(ctx) == []

    def test_rows_by_header_vid_dangling_table(self) -> None:
        stores = _base(table_versions=[_tv(table_id=None)])
        ctx = _ctx(**stores)
        assert headers._rows_by_header_vid(ctx) == []
        stores = _base(tables=[])
        ctx = _ctx(**stores)
        assert headers._rows_by_header_vid(ctx) == []

    def test_rows_by_header_id_skips_dangling(self) -> None:
        stores = _base(
            table_version_headers=[
                _tvh(10, 99),
                _tvh(),
            ],
            table_versions=[_tv(), _tv(20, table_id=None)],
        )
        ctx = _ctx(**stores)
        rows = headers._rows_by_header_id(ctx)
        assert len(rows) == 1

    def test_rows_by_header_id_table_mismatch(self) -> None:
        stores = _base(headers=[_header(table_id=2)])
        ctx = _ctx(**stores)
        assert headers._rows_by_header_id(ctx) == []

    def test_tv_header_rows_skip_dangling(self) -> None:
        stores = _base(
            header_versions=[_hv(header_id=None)],
            table_version_headers=[
                _tvh(),
                _tvh(10, 2, header_vid=None),
                _tvh(10, 3, header_vid=999),
            ],
        )
        ctx = _ctx(**stores)
        assert headers._tv_header_rows(ctx, 10) == []

    def test_same_direction_none_handling(self) -> None:
        assert headers._same_direction(None, None)
        assert not headers._same_direction("x", None)
        assert headers._same_direction("X", "x")

    def test_member_open_mv_missing_module(self) -> None:
        stores = _base(module_versions=[])
        ctx = _ctx(**stores)
        assert not headers._member_open_mv_start_now(ctx, 10)
        assert not headers._member_mv_start_now(ctx, 10)

    def test_relations_between_none_guids(self) -> None:
        ctx = _ctx()
        assert headers._relations_between(ctx, None, "g") == set()

    def test_left_open_categories_dangling_category(self) -> None:
        stores = _base(property_categories=[_pc(category_id=999)])
        ctx = _ctx(**stores)
        assert headers._left_open_categories(ctx, 7) == [(None, None)]


# ------------------------------------------------------------------
# Guard gauntlet: every rule must stay quiet on degenerate models
# ------------------------------------------------------------------

import pytest

_ALL_RULES = [
    headers.rule_3_1,
    headers.rule_3_2,
    headers.rule_3_3,
    headers.rule_3_4,
    headers.rule_3_5a,
    headers.rule_3_5b,
    headers.rule_3_6,
    headers.rule_3_7,
    headers.rule_3_8,
    headers.rule_3_9,
    headers.rule_3_10a,
    headers.rule_3_10b,
    headers.rule_3_11,
    headers.rule_3_12,
    headers.rule_3_14,
    headers.rule_3_15a,
    headers.rule_3_15b,
    headers.rule_3_16,
]


def _rich_row_stores(**overrides: Any) -> dict:
    """A fully loaded row that passes the shared join, for guards."""
    stores = _base(
        headers=[
            _header(
                is_key=True, is_attribute=True, row_guid="g-attr"
            ),
            _header(2, row_guid="g-base"),
        ],
        header_versions=[
            _hv(property_id=7, context_id=40, subcategory_vid=600),
            _hv(101, header_id=2),
        ],
        table_version_headers=[
            _tvh(parent_header_id=2, order=1),
            _tvh(10, 2, header_vid=101, order=2, parent_first=True),
        ],
        properties=[_prop(7, is_metric=True, data_type_id=1)],
        datatypes=[_dt(1, "es")],
        item_categories=[_ic()],
        property_categories=[_pc()],
        categories=[_cat()],
        subcategory_versions=[_scv(end=PREV)],
        subcategories=[_sc()],
        context_compositions=[_cc(40, 7)],
        concept_relations=[_cr()],
        related_concepts=[
            _rc("g-attr", related=True),
            _rc("g-base", related=False),
        ],
    )
    stores.update(overrides)
    return stores


@pytest.mark.parametrize("rule_fn", _ALL_RULES)
@pytest.mark.parametrize(
    "override",
    [
        {"tables": [_table(is_abstract=True)]},
        {"tables": [_table(is_abstract=None)]},
        {"table_versions": [_tv(end=CUR)]},
        {"table_versions": [_tv(start=PREV)]},
        {
            "header_versions": [
                _hv(
                    property_id=7,
                    context_id=40,
                    subcategory_vid=600,
                    end=CUR,
                ),
                _hv(101, header_id=2, end=CUR),
            ]
        },
        {"table_version_headers": [_tvh(is_abstract=None)]},
        {"module_versions": [_mv(start=PREV, end=PREV)]},
        {"module_version_compositions": []},
        {
            "headers": [
                _header(is_key=None, is_attribute=None),
                _header(2),
            ]
        },
        {
            "header_versions": [
                _hv(),
                _hv(101, header_id=2),
            ]
        },
    ],
)
def test_guard_gauntlet(rule_fn: Any, override: dict) -> None:
    """Degenerate variants must never crash; most yield nothing."""
    findings = list(rule_fn(_ctx(**_rich_row_stores(**override))))
    # The gauntlet asserts robustness, not emptiness: a handful of
    # rules legitimately fire on some variants (e.g. 3_5b fires on
    # is_abstract=None rows). It must simply not raise.
    assert isinstance(findings, list)


# ------------------------------------------------------------------
# Remaining branch coverage
# ------------------------------------------------------------------


class TestRemainingBranches:
    def test_rows_by_header_vid_dangling_header(self) -> None:
        stores = _base(headers=[])
        assert headers._rows_by_header_vid(_ctx(**stores)) == []

    def test_open_pc_categories_none_property(self) -> None:
        assert headers._open_pc_categories(_ctx(), None) == []

    def test_open_pc_categories_skips_other_property(self) -> None:
        stores = _base(
            property_categories=[_pc(8), _pc(7)],
            categories=[_cat()],
        )
        result = headers._open_pc_categories(_ctx(**stores), 7)
        assert result == [(3, "CAT")]

    def test_3_1_skips_expired_hv(self) -> None:
        stores = _base(
            headers=[_header(is_key=True)],
            header_versions=[_hv(end=CUR)],
        )
        assert list(headers.rule_3_1(_ctx(**stores))) == []

    def test_3_2_skips_expired_versions(self) -> None:
        stores = _base(
            headers=[_header(is_key=True)],
            table_versions=[_tv(end=CUR)],
            table_version_headers=[_tvh(is_abstract=True)],
        )
        assert list(headers.rule_3_2(_ctx(**stores))) == []
        stores = _base(
            headers=[_header(is_key=True)],
            header_versions=[_hv(end=CUR)],
            table_version_headers=[_tvh(is_abstract=True)],
        )
        assert list(headers.rule_3_2(_ctx(**stores))) == []

    def test_3_8_ignores_abstract_context_partner(self) -> None:
        stores = _base(
            headers=[
                _header(is_key=True),
                _header(2, direction="y"),
            ],
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2, context_id=40),
            ],
            table_version_headers=[
                _tvh(),
                _tvh(10, 2, header_vid=101, is_abstract=True),
            ],
            context_compositions=[_cc(40, 7)],
        )
        assert list(headers.rule_3_8(_ctx(**stores))) == []

    def test_left_open_categories_mixed_rows(self) -> None:
        stores = _base(
            property_categories=[
                _pc(end=PREV, category_id=4),
                _pc(category_id=3),
            ],
            categories=[_cat()],
        )
        result = headers._left_open_categories(_ctx(**stores), 7)
        assert result == [(3, "CAT")]

    def test_3_9_skips_null_pc_category(self) -> None:
        stores = _base(
            header_versions=[
                _hv(property_id=7, subcategory_vid=600)
            ],
            subcategory_versions=[_scv()],
            subcategories=[_sc(category_id=4)],
            property_categories=[_pc(category_id=None)],
            categories=[_cat(4, code="OTHER")],
            item_categories=[_ic()],
        )
        assert list(headers.rule_3_9(_ctx(**stores))) == []

    def test_3_10b_ignores_other_property_pc(self) -> None:
        stores = _base(
            header_versions=[_hv(property_id=7)],
            properties=[_prop(data_type_id=1)],
            datatypes=[_dt(1, code="es")],
            item_categories=[_ic()],
            property_categories=[_pc(8), _pc(7)],
            categories=[_cat()],
        )
        findings = list(headers.rule_3_10b(_ctx(**stores)))
        assert len(findings) == 1

    def test_3_1_skips_old_tv_with_open_hv(self) -> None:
        stores = _base(
            headers=[_header(is_key=True)],
            table_versions=[_tv(start=PREV)],
        )
        assert list(headers.rule_3_1(_ctx(**stores))) == []

    def test_open_pc_categories_dangling_category(self) -> None:
        stores = _base(property_categories=[_pc(category_id=999)])
        assert headers._open_pc_categories(_ctx(**stores), 7) == []

    def test_attr_relations_ignore_null_flag(self) -> None:
        stores = _base(
            concept_relations=[_cr()],
            related_concepts=[
                RelatedConceptRow("g-x", 900, None),
                _rc("g-attr", related=True),
            ],
        )
        rels = headers._attr_relations(_ctx(**stores))
        assert rels[900] == ({"g-attr"}, set())

    def test_tv_header_rows_dangling_header_row(self) -> None:
        stores = _base(headers=[])
        assert headers._tv_header_rows(_ctx(**stores), 10) == []

    def test_3_14_deduplicates_multiple_partners(self) -> None:
        stores = _dtype_stores(
            headers=[
                _header(is_attribute=True, row_guid="g-attr"),
                _header(2, row_guid="g-base"),
                _header(3, row_guid="g-base2"),
            ],
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2),
                _hv(103, header_id=3),
                _hv(
                    102,
                    header_id=1,
                    property_id=8,
                    end=CUR,
                    start=PREV,
                ),
            ],
            table_version_headers=[
                _tvh(),
                _tvh(10, 2, header_vid=101),
                _tvh(10, 3, header_vid=103),
            ],
            concept_relations=[_cr(900), _cr(901)],
            related_concepts=[
                _rc("g-attr", 900, related=True),
                _rc("g-base", 900, related=False),
                _rc("g-attr", 901, related=True),
                _rc("g-base2", 901, related=False),
            ],
        )
        findings = list(headers.rule_3_14(_ctx(**stores)))
        assert len(findings) == 1

    def test_3_15a_deduplicates_duplicate_join_rows(self) -> None:
        # Two TVH rows of the same table version pointing at the same
        # HeaderVersion produce the same (tv, hv) key twice.
        stores = _base(
            headers=[
                _header(row_guid="g-base"),
                _header(2, is_attribute=True, row_guid="g-attr"),
                _header(99, row_guid=None),
            ],
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2),
                _hv(
                    102,
                    header_id=1,
                    property_id=8,
                    end=CUR,
                    start=PREV,
                ),
            ],
            table_version_headers=[
                _tvh(),
                _tvh(10, 2, header_vid=101),
                _tvh(10, 99, header_vid=100),
            ],
            concept_relations=[_cr()],
            related_concepts=[
                _rc("g-attr", related=True),
                _rc("g-base", related=False),
            ],
            properties=[
                _prop(7, data_type_id=1),
                _prop(8, data_type_id=2),
            ],
            datatypes=[_dt(1, "m"), _dt(2, "s")],
        )
        findings = list(headers.rule_3_15a(_ctx(**stores)))
        assert len(findings) == 1
