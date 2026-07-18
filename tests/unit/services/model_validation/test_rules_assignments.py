"""Unit tests for the family-4 (assignments) modelling rules."""

from __future__ import annotations

from datetime import date
from typing import Any

from dpmcore.services.model_validation.rules import assignments
from dpmcore.services.model_validation.snapshot import (
    CompoundItemContextRow,
    ModuleVersionCompositionRow,
    ReleaseRow,
    SubCategoryItemRow,
)
from tests.unit.services.model_validation.test_rules_headers import (
    CUR,
    PREV,
    _base,
    _cat,
    _cc,
    _ctx,
    _header,
    _hv,
    _ic,
    _ids,
    _mv,
    _pc,
    _prop,
    _sc,
    _scv,
    _table,
    _tv,
    _tvh,
)


def _release(release_id: int, *, day: Any = None) -> ReleaseRow:
    return ReleaseRow(
        release_id=release_id,
        code=str(release_id),
        status=None,
        is_current=None,
        type=None,
        date=day,
    )


def _cic(
    item_id: int = 70,
    *,
    start: Any = CUR,
    end: Any = None,
    context_id: Any = 40,
) -> CompoundItemContextRow:
    return CompoundItemContextRow(
        item_id=item_id,
        start_release_id=start,
        context_id=context_id,
        end_release_id=end,
    )


def _sci(item_id: int = 8, scv: int = 600) -> SubCategoryItemRow:
    return SubCategoryItemRow(
        item_id=item_id,
        subcategory_vid=scv,
        order=None,
        label=None,
        parent_item_id=None,
    )


def _mvc2(table_id: int, table_vid: int) -> ModuleVersionCompositionRow:
    return ModuleVersionCompositionRow(
        module_vid=500,
        table_id=table_id,
        table_vid=table_vid,
        order=None,
    )


# ------------------------------------------------------------------
# 4_1a / 4_1b
# ------------------------------------------------------------------


class TestRule41a:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            headers=[_header(), _header(2, is_key=True)],
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2, property_id=7),
            ],
            table_version_headers=[
                _tvh(),
                _tvh(10, 2, header_vid=101),
            ],
            item_categories=[_ic()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_fires_when_fact_property_is_key_property(self) -> None:
        findings = list(assignments.rule_4_1a(_ctx(**self._stores())))
        assert _ids(findings) == [(100, 10, 7, 3)]

    def test_clean_for_distinct_properties(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2, property_id=8),
            ],
        )
        assert list(assignments.rule_4_1a(_ctx(**stores))) == []

    def test_skips_key_outer_header(self) -> None:
        stores = self._stores(
            headers=[
                _header(is_key=True),
                _header(2, is_key=True),
            ],
        )
        assert list(assignments.rule_4_1a(_ctx(**stores))) == []

    def test_skips_expired_key_partner(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2, property_id=7, end=CUR),
            ],
        )
        assert list(assignments.rule_4_1a(_ctx(**stores))) == []

    def test_skips_abstract_key_partner(self) -> None:
        stores = self._stores(
            table_version_headers=[
                _tvh(),
                _tvh(10, 2, header_vid=101, is_abstract=True),
            ],
        )
        assert list(assignments.rule_4_1a(_ctx(**stores))) == []

    def test_guards(self) -> None:
        for override in (
            {"tables": [_table(is_abstract=True)]},
            {"table_versions": [_tv(end=CUR)]},
            {"table_versions": [_tv(start=PREV)]},
            {"table_version_headers": [_tvh(is_abstract=True)]},
            {"module_version_compositions": []},
            {
                "header_versions": [
                    _hv(),
                    _hv(101, header_id=2, property_id=7),
                ]
            },
            {
                "header_versions": [
                    _hv(property_id=7, end=CUR),
                    _hv(101, header_id=2, property_id=7),
                ]
            },
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_1a(_ctx(**stores))) == []


class TestRule41b:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            table_versions=[_tv(property_id=7)],
            headers=[_header(is_key=True)],
            header_versions=[_hv(property_id=7)],
            item_categories=[_ic()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_fires_for_table_property_in_key(self) -> None:
        findings = list(assignments.rule_4_1b(_ctx(**self._stores())))
        assert _ids(findings) == [(10, 7, 3)]

    def test_clean_without_key_match(self) -> None:
        stores = self._stores(header_versions=[_hv(property_id=8)])
        assert list(assignments.rule_4_1b(_ctx(**stores))) == []

    def test_guards(self) -> None:
        for override in (
            {"table_versions": [_tv(property_id=7, end=CUR)]},
            {"table_versions": [_tv()]},
            {"table_versions": [_tv(property_id=7, start=PREV)]},
            {"table_versions": [_tv(property_id=7, table_id=None)]},
            {"tables": [_table(is_abstract=True)]},
            {"tables": []},
            {"module_version_compositions": []},
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_1b(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 4_2
# ------------------------------------------------------------------


class TestRule42:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            headers=[_header(), _header(2)],
            header_versions=[
                _hv(property_id=7, context_id=40),
                _hv(101, header_id=2, property_id=7, context_id=40),
            ],
            table_version_headers=[
                _tvh(),
                _tvh(10, 2, header_vid=101),
            ],
            item_categories=[_ic()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_fires_for_duplicate_coordinates(self) -> None:
        findings = list(assignments.rule_4_2(_ctx(**self._stores())))
        assert len(findings) == 2

    def test_null_coordinates_compare_equal(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(),
                _hv(101, header_id=2),
            ],
        )
        findings = list(assignments.rule_4_2(_ctx(**stores)))
        assert len(findings) == 2
        assert findings[0].objects[2].code is None

    def test_clean_for_distinct_context(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(property_id=7, context_id=40),
                _hv(101, header_id=2, property_id=7, context_id=41),
            ],
        )
        assert list(assignments.rule_4_2(_ctx(**stores))) == []

    def test_clean_for_other_direction(self) -> None:
        stores = self._stores(
            headers=[_header(), _header(2, direction="y")],
        )
        assert list(assignments.rule_4_2(_ctx(**stores))) == []

    def test_twin_guards(self) -> None:
        for override in (
            {
                "table_version_headers": [
                    _tvh(),
                    _tvh(10, 2, header_vid=101, is_abstract=True),
                ]
            },
            {"headers": [_header(), _header(2, is_key=True)]},
            {
                "header_versions": [
                    _hv(property_id=7, context_id=40),
                    _hv(
                        101,
                        header_id=2,
                        property_id=7,
                        context_id=40,
                        end=CUR,
                    ),
                ]
            },
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_2(_ctx(**stores))) == []

    def test_outer_guards(self) -> None:
        for override in (
            {"tables": [_table(is_abstract=True)]},
            {"table_versions": [_tv(end=CUR)]},
            {"table_versions": [_tv(start=PREV)]},
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_2(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 4_3a / 4_3b
# ------------------------------------------------------------------


class TestRule43:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            headers=[_header(), _header(2, direction="y")],
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2, context_id=40),
            ],
            table_version_headers=[
                _tvh(),
                _tvh(10, 2, header_vid=101),
            ],
            context_compositions=[_cc(40, 7)],
            item_categories=[_ic()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_4_3a_fires_via_other_direction_context(self) -> None:
        findings = list(assignments.rule_4_3a(_ctx(**self._stores())))
        assert _ids(findings) == [(1, 10, 7, 3)]

    def test_4_3a_fires_via_own_header_context(self) -> None:
        stores = self._stores(
            headers=[_header()],
            header_versions=[_hv(property_id=7, context_id=40)],
            table_version_headers=[_tvh()],
        )
        findings = list(assignments.rule_4_3a(_ctx(**stores)))
        assert len(findings) == 1

    def test_4_3a_same_direction_other_header_ignored(self) -> None:
        stores = self._stores(headers=[_header(), _header(2)])
        assert list(assignments.rule_4_3a(_ctx(**stores))) == []

    def test_4_3a_partner_guards(self) -> None:
        for override in (
            {
                "table_version_headers": [
                    _tvh(),
                    _tvh(10, 2, header_vid=101, is_abstract=True),
                ]
            },
            {
                "headers": [
                    _header(),
                    _header(2, direction="y", is_key=True),
                ],
            },
            {
                "header_versions": [
                    _hv(property_id=7),
                    _hv(101, header_id=2, context_id=40, end=CUR),
                ]
            },
            {"context_compositions": [_cc(40, 8)]},
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_3a(_ctx(**stores))) == []

    def test_4_3b_fires_via_table_context(self) -> None:
        stores = self._stores(table_versions=[_tv(context_id=40)])
        findings = list(assignments.rule_4_3b(_ctx(**stores)))
        assert len(findings) == 1

    def test_4_3b_clean_without_table_context(self) -> None:
        stores = self._stores()
        assert list(assignments.rule_4_3b(_ctx(**stores))) == []

    def test_base_row_guards(self) -> None:
        for override in (
            {"tables": [_table(is_abstract=True)]},
            {"table_versions": [_tv(end=CUR)]},
            {"table_versions": [_tv(start=PREV)]},
            {"module_version_compositions": []},
            {
                "header_versions": [
                    _hv(),
                    _hv(101, header_id=2, context_id=40),
                ]
            },
            {
                "header_versions": [
                    _hv(property_id=7, end=CUR),
                    _hv(101, header_id=2, context_id=40),
                ]
            },
            {"headers": [_header(is_key=True), _header(2)]},
            {
                "table_version_headers": [
                    _tvh(is_abstract=True),
                    _tvh(10, 2, header_vid=101),
                ]
            },
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_3a(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 4_4
# ------------------------------------------------------------------


class TestRule44:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            headers=[_header(), _header(2)],
            header_versions=[
                _hv(code="010"),
                _hv(101, header_id=2, code="010"),
            ],
            table_version_headers=[
                _tvh(),
                _tvh(10, 2, header_vid=101),
            ],
        )
        stores.update(extra)
        return stores

    def test_fires_for_duplicate_code(self) -> None:
        findings = list(assignments.rule_4_4(_ctx(**self._stores())))
        assert len(findings) == 2

    def test_clean_for_distinct_codes(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(code="010"),
                _hv(101, header_id=2, code="020"),
            ],
        )
        assert list(assignments.rule_4_4(_ctx(**stores))) == []

    def test_clean_for_other_direction(self) -> None:
        stores = self._stores(
            headers=[_header(), _header(2, direction="y")],
        )
        assert list(assignments.rule_4_4(_ctx(**stores))) == []

    def test_expired_twin_ignored(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(code="010"),
                _hv(101, header_id=2, code="010", end=CUR),
            ],
        )
        assert list(assignments.rule_4_4(_ctx(**stores))) == []

    def test_guards(self) -> None:
        for override in (
            {"tables": [_table(is_abstract=True)]},
            {"table_versions": [_tv(end=CUR)]},
            {"table_versions": [_tv(start=PREV)]},
            {"module_version_compositions": []},
            {
                "header_versions": [
                    _hv(code="010", end=CUR),
                    _hv(101, header_id=2, code="010"),
                ]
            },
        ):
            stores = self._stores(**override)
            findings = list(assignments.rule_4_4(_ctx(**stores)))
            assert len(findings) <= 1


# ------------------------------------------------------------------
# 4_5a / 4_5b
# ------------------------------------------------------------------


class TestRule45:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            headers=[_header(), _header(2, direction="y")],
            header_versions=[
                _hv(context_id=40),
                _hv(101, header_id=2, context_id=41),
            ],
            table_version_headers=[
                _tvh(),
                _tvh(10, 2, header_vid=101),
            ],
            context_compositions=[_cc(40, 7), _cc(41, 7)],
            item_categories=[_ic()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_4_5a_fires_for_repeated_property(self) -> None:
        findings = list(assignments.rule_4_5a(_ctx(**self._stores())))
        assert _ids(findings) == [(10, 7, 3)]

    def test_4_5a_clean_same_direction(self) -> None:
        stores = self._stores(headers=[_header(), _header(2)])
        assert list(assignments.rule_4_5a(_ctx(**stores))) == []

    def test_4_5a_partner_guards(self) -> None:
        for override in (
            {
                "table_version_headers": [
                    _tvh(),
                    _tvh(10, 2, header_vid=101, is_abstract=True),
                ]
            },
            {
                "headers": [
                    _header(),
                    _header(2, direction="y", is_key=True),
                ],
            },
            {
                # Expired partner hv2 is skipped; the outer side of
                # header 2 has no composition of its own (the SQL
                # applies no EndReleaseID filter on the OUTER hv).
                "header_versions": [
                    _hv(context_id=40),
                    _hv(101, header_id=2, context_id=41, end=CUR),
                ],
                "context_compositions": [_cc(40, 7)],
            },
            {"context_compositions": [_cc(40, 7), _cc(41, 8)]},
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_5a(_ctx(**stores))) == []

    def test_4_5b_fires_for_table_context_repeat(self) -> None:
        stores = self._stores(table_versions=[_tv(context_id=41)])
        findings = list(assignments.rule_4_5b(_ctx(**stores)))
        assert _ids(findings) == [(10, 7, 3)]

    def test_4_5b_clean_without_table_context(self) -> None:
        stores = self._stores()
        assert list(assignments.rule_4_5b(_ctx(**stores))) == []

    def test_4_5b_clean_disjoint_table_context(self) -> None:
        stores = self._stores(
            table_versions=[_tv(context_id=42)],
            context_compositions=[_cc(40, 7), _cc(42, 8)],
        )
        assert list(assignments.rule_4_5b(_ctx(**stores))) == []

    def test_outer_guards(self) -> None:
        for override in (
            {"tables": [_table(is_abstract=True)]},
            {"table_versions": [_tv(end=CUR)]},
            {"table_versions": [_tv(start=PREV)]},
            {"module_version_compositions": []},
            {"headers": [_header(is_key=True), _header(2)]},
            {
                "table_version_headers": [
                    _tvh(is_abstract=True),
                    _tvh(10, 2, header_vid=101),
                ]
            },
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_5a(_ctx(**stores))) == []

    def test_emit_needs_open_assignments(self) -> None:
        stores = self._stores(item_categories=[_ic(end=PREV)])
        assert list(assignments.rule_4_5a(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 4_6
# ------------------------------------------------------------------


class TestRule46:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            header_versions=[_hv(context_id=40)],
            context_compositions=[_cc(40, 7)],
            item_categories=[_ic()],
            property_categories=[_pc()],
            categories=[_cat(is_enumerated=False)],
        )
        stores.update(extra)
        return stores

    def test_fires_for_non_enumerated_category(self) -> None:
        findings = list(assignments.rule_4_6(_ctx(**self._stores())))
        assert _ids(findings) == [(10, 7, 3)]

    def test_clean_for_enumerated(self) -> None:
        stores = self._stores(categories=[_cat()])
        assert list(assignments.rule_4_6(_ctx(**stores))) == []

    def test_null_enumeration_flag_excluded(self) -> None:
        stores = self._stores(categories=[_cat(is_enumerated=None)])
        assert list(assignments.rule_4_6(_ctx(**stores))) == []

    def test_requires_open_ic(self) -> None:
        stores = self._stores(item_categories=[_ic(end=PREV)])
        assert list(assignments.rule_4_6(_ctx(**stores))) == []

    def test_pc_guards(self) -> None:
        for override in (
            {"property_categories": [_pc(end=PREV)]},
            {"property_categories": [_pc(category_id=None)]},
            {"property_categories": [_pc(category_id=999)]},
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_6(_ctx(**stores))) == []

    def test_outer_guards(self) -> None:
        for override in (
            {"tables": [_table(is_abstract=True)]},
            {"table_versions": [_tv(end=CUR)]},
            {"module_versions": [_mv(start=PREV)]},
            {"headers": [_header(is_key=True)]},
            {"table_version_headers": [_tvh(is_abstract=True)]},
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_6(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 4_7 family
# ------------------------------------------------------------------


class TestRule47Family:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            releases=[
                _release(PREV, day=date(2024, 1, 1)),
                _release(CUR, day=date(2025, 1, 1)),
            ],
            header_versions=[_hv(context_id=40)],
            context_compositions=[_cc(40, 7, item_id=8)],
            item_categories=[
                _ic(7, code="prop"),
                _ic(8, category_id=4, code="item"),
            ],
            property_categories=[_pc(category_id=3)],
            categories=[_cat(3), _cat(4, code="OTHER")],
        )
        stores.update(extra)
        return stores

    def test_4_7_fires_on_category_mismatch(self) -> None:
        findings = list(assignments.rule_4_7(_ctx(**self._stores())))
        assert len(findings) == 1
        assert findings[0].message is not None
        assert "(CAT)" in findings[0].message
        assert "(OTHER)" in findings[0].message

    def test_4_7_clean_on_matching_categories(self) -> None:
        stores = self._stores(
            item_categories=[
                _ic(7, code="prop"),
                _ic(8, category_id=3, code="item"),
            ],
        )
        assert list(assignments.rule_4_7(_ctx(**stores))) == []

    def test_4_7_only_latest_assignment_counts(self) -> None:
        stores = self._stores(
            property_categories=[
                _pc(category_id=4, start=PREV),
                _pc(category_id=4, start=CUR),
            ],
        )
        # Latest PC (CUR) matches the item category -> clean.
        assert list(assignments.rule_4_7(_ctx(**stores))) == []

    def test_4_7_undated_releases_never_latest(self) -> None:
        stores = self._stores(releases=[])
        assert list(assignments.rule_4_7(_ctx(**stores))) == []

    def test_4_7b_fires_on_expired_latest_pc(self) -> None:
        stores = self._stores(
            property_categories=[_pc(category_id=3, end=CUR)],
        )
        findings = list(assignments.rule_4_7b(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].message is not None
        assert "has Expired" in findings[0].message

    def test_4_7b_clean_on_open_pc(self) -> None:
        stores = self._stores()
        assert list(assignments.rule_4_7b(_ctx(**stores))) == []

    def test_4_7c_fires_on_expired_latest_property_ic(self) -> None:
        stores = self._stores(
            item_categories=[
                _ic(7, code="prop", end=CUR),
                _ic(8, category_id=4, code="item"),
            ],
        )
        findings = list(assignments.rule_4_7c(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].message is not None
        assert "Property Code" in findings[0].message

    def test_4_7c_clean_on_open_ic(self) -> None:
        stores = self._stores()
        assert list(assignments.rule_4_7c(_ctx(**stores))) == []

    def test_4_7d_fires_on_expired_latest_item_ic(self) -> None:
        stores = self._stores(
            item_categories=[
                _ic(7, code="prop"),
                _ic(8, category_id=4, code="item", end=CUR),
            ],
        )
        findings = list(assignments.rule_4_7d(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].message is not None
        assert "Item Category" in findings[0].message

    def test_4_7d_clean_on_open_ic(self) -> None:
        stores = self._stores()
        assert list(assignments.rule_4_7d(_ctx(**stores))) == []

    def test_compound_item_branch(self) -> None:
        stores = self._stores(
            header_versions=[_hv()],
            compound_item_contexts=[_cic(70)],
            item_categories=[
                _ic(7, code="prop"),
                _ic(8, category_id=4, code="item"),
                _ic(70, code="comp"),
            ],
        )
        findings = list(assignments.rule_4_7(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].objects[0].kind == "compound_item"

    def test_compound_item_branch_guards(self) -> None:
        stores = self._stores(
            header_versions=[_hv()],
            compound_item_contexts=[
                _cic(70, end=CUR),
                _cic(71, start=PREV),
            ],
            item_categories=[
                _ic(7, code="prop"),
                _ic(8, category_id=4, code="item"),
                _ic(70, code="comp"),
                _ic(71, code="comp2"),
            ],
        )
        assert list(assignments.rule_4_7(_ctx(**stores))) == []

    def test_table_context_branch(self) -> None:
        stores = self._stores(
            header_versions=[_hv()],
            table_versions=[_tv(context_id=40)],
        )
        findings = list(assignments.rule_4_7(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].objects[0].name == "Table_Context"

    def test_table_context_branch_guards(self) -> None:
        base = {"header_versions": [_hv()]}
        for override in (
            {"table_versions": [_tv(context_id=40, end=CUR)]},
            {"table_versions": [_tv(context_id=40, table_id=None)]},
            {
                "table_versions": [_tv(context_id=40)],
                "tables": [_table(is_abstract=True)],
            },
            {
                "table_versions": [_tv(context_id=40)],
                "module_versions": [_mv(start=PREV)],
            },
        ):
            stores = self._stores(**{**base, **override})
            assert list(assignments.rule_4_7(_ctx(**stores))) == []

    def test_header_branch_guards(self) -> None:
        for override in (
            {"tables": [_table(is_abstract=True)]},
            {"table_versions": [_tv(end=CUR)]},
            {"headers": [_header(is_key=True)]},
            {"table_version_headers": [_tvh(is_abstract=True)]},
            {"module_versions": [_mv(start=PREV)]},
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_7(_ctx(**stores))) == []

    def test_composition_without_item_skipped(self) -> None:
        stores = self._stores(
            context_compositions=[_cc(40, 7, item_id=None)],
        )
        assert list(assignments.rule_4_7(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 4_8
# ------------------------------------------------------------------


class TestRule48:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            tables=[_table(), _table(2)],
            table_versions=[_tv(), _tv(20, table_id=2)],
            headers=[_header(), _header(2, table_id=2)],
            header_versions=[
                _hv(property_id=7, subcategory_vid=600),
                _hv(
                    101,
                    header_id=2,
                    property_id=7,
                    subcategory_vid=601,
                ),
            ],
            table_version_headers=[
                _tvh(),
                _tvh(20, 2, header_vid=101),
            ],
            module_version_compositions=[
                _mvc2(1, 10),
                _mvc2(2, 20),
            ],
            subcategory_versions=[_scv(600), _scv(601)],
            subcategories=[_sc()],
            categories=[_cat()],
            item_categories=[_ic()],
        )
        stores.update(extra)
        return stores

    def test_fires_for_two_subcategories(self) -> None:
        findings = list(assignments.rule_4_8(_ctx(**self._stores())))
        assert len(findings) == 2

    def test_clean_for_single_subcategory(self) -> None:
        stores = self._stores(
            header_versions=[
                _hv(property_id=7, subcategory_vid=600),
                _hv(
                    101,
                    header_id=2,
                    property_id=7,
                    subcategory_vid=600,
                ),
            ],
        )
        assert list(assignments.rule_4_8(_ctx(**stores))) == []

    def test_skips_expired_scv_row(self) -> None:
        stores = self._stores(
            subcategory_versions=[_scv(600, end=PREV), _scv(601)],
        )
        findings = list(assignments.rule_4_8(_ctx(**stores)))
        assert len(findings) == 1

    def test_skips_dangling_sc_or_category(self) -> None:
        stores = self._stores(subcategories=[])
        assert list(assignments.rule_4_8(_ctx(**stores))) == []
        stores = self._stores(categories=[])
        assert list(assignments.rule_4_8(_ctx(**stores))) == []

    def test_guards(self) -> None:
        for override in (
            {
                "headers": [
                    _header(is_key=True),
                    _header(2, table_id=2, is_key=True),
                ]
            },
            {
                "table_version_headers": [
                    _tvh(is_abstract=True),
                    _tvh(20, 2, header_vid=101, is_abstract=True),
                ]
            },
            {"module_versions": [_mv(start=PREV)]},
            {
                "header_versions": [
                    _hv(subcategory_vid=600),
                    _hv(101, header_id=2, subcategory_vid=601),
                ]
            },
            {
                "header_versions": [
                    _hv(property_id=7),
                    _hv(101, header_id=2, property_id=7),
                ]
            },
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_8(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 4_9a / 4_9b / 4_9c
# ------------------------------------------------------------------


class TestRule49:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            header_versions=[_hv(context_id=40)],
            context_compositions=[_cc(40, 7, item_id=8)],
            item_categories=[_ic(8, code="item", is_default=True)],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_4_9a_fires_for_default_item(self) -> None:
        findings = list(assignments.rule_4_9a(_ctx(**self._stores())))
        assert _ids(findings) == [(1, 10, 8, 3)]

    def test_4_9a_clean_for_non_default(self) -> None:
        stores = self._stores(item_categories=[_ic(8, code="item")])
        assert list(assignments.rule_4_9a(_ctx(**stores))) == []

    def test_4_9a_requires_enumerated_category(self) -> None:
        stores = self._stores(categories=[_cat(is_enumerated=False)])
        assert list(assignments.rule_4_9a(_ctx(**stores))) == []

    def test_4_9a_dangling_category(self) -> None:
        stores = self._stores(categories=[])
        assert list(assignments.rule_4_9a(_ctx(**stores))) == []
        stores = self._stores(
            item_categories=[
                _ic(
                    8,
                    code="item",
                    is_default=True,
                    category_id=None,
                )
            ],
        )
        assert list(assignments.rule_4_9a(_ctx(**stores))) == []

    def test_4_9a_guards(self) -> None:
        for override in (
            {"tables": [_table(is_abstract=True)]},
            {"table_versions": [_tv(end=CUR)]},
            {"headers": [_header(is_key=True)]},
            {"table_version_headers": [_tvh(is_abstract=True)]},
            {"module_versions": [_mv(start=PREV)]},
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_9a(_ctx(**stores))) == []

    def test_4_9b_fires_for_table_context(self) -> None:
        stores = self._stores(
            header_versions=[_hv()],
            table_versions=[_tv(context_id=40)],
        )
        findings = list(assignments.rule_4_9b(_ctx(**stores)))
        assert _ids(findings) == [(10, 8, 3)]

    def test_4_9b_guards(self) -> None:
        for override in (
            {"table_versions": [_tv()]},
            {"table_versions": [_tv(context_id=40, end=CUR)]},
            {"table_versions": [_tv(context_id=40, table_id=None)]},
            {
                "table_versions": [_tv(context_id=40)],
                "tables": [_table(is_abstract=True)],
            },
            {
                "table_versions": [_tv(context_id=40)],
                "module_versions": [_mv(start=PREV)],
            },
        ):
            stores = self._stores(
                **{"header_versions": [_hv()], **override}
            )
            assert list(assignments.rule_4_9b(_ctx(**stores))) == []

    def test_4_9c_fires_for_compound_item_context(self) -> None:
        stores = self._stores(
            header_versions=[_hv()],
            compound_item_contexts=[_cic(70)],
            item_categories=[
                _ic(8, code="item", is_default=True),
                _ic(70, code="comp"),
            ],
        )
        findings = list(assignments.rule_4_9c(_ctx(**stores)))
        assert len(findings) == 1
        assert findings[0].objects[0].kind == "compound_item"

    def test_4_9c_skips_old_start(self) -> None:
        stores = self._stores(
            header_versions=[_hv()],
            compound_item_contexts=[_cic(70, start=PREV)],
            item_categories=[
                _ic(8, code="item", is_default=True),
                _ic(70, code="comp"),
            ],
        )
        assert list(assignments.rule_4_9c(_ctx(**stores))) == []


# ------------------------------------------------------------------
# 4_10
# ------------------------------------------------------------------


class TestRule410:
    def _stores(self, **extra: Any) -> dict:
        stores = _base(
            header_versions=[
                _hv(property_id=7, subcategory_vid=600)
            ],
            subcategory_versions=[_scv()],
            subcategories=[_sc()],
            subcategory_items=[_sci(8, 600)],
            item_categories=[
                _ic(7, code="prop"),
                _ic(8, code="item", is_default=True),
            ],
            properties=[_prop()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        stores.update(extra)
        return stores

    def test_fires_for_default_item_in_subcategory(self) -> None:
        findings = list(assignments.rule_4_10(_ctx(**self._stores())))
        assert len(findings) == 1
        assert findings[0].objects[4].code == "Default_ItemCode:item"

    def test_clean_without_default_items(self) -> None:
        stores = self._stores(
            item_categories=[
                _ic(7, code="prop"),
                _ic(8, code="item"),
            ],
        )
        assert list(assignments.rule_4_10(_ctx(**stores))) == []

    def test_skips_dangling_scv_or_sc(self) -> None:
        stores = self._stores(subcategory_versions=[])
        assert list(assignments.rule_4_10(_ctx(**stores))) == []
        stores = self._stores(subcategories=[])
        assert list(assignments.rule_4_10(_ctx(**stores))) == []

    def test_skips_property_without_row(self) -> None:
        stores = self._stores(properties=[])
        assert list(assignments.rule_4_10(_ctx(**stores))) == []

    def test_guards(self) -> None:
        for override in (
            {"tables": [_table(is_abstract=True)]},
            {"table_versions": [_tv(end=CUR)]},
            {"table_version_headers": [_tvh(is_abstract=True)]},
            {"module_versions": [_mv(start=PREV)]},
            {"header_versions": [_hv(subcategory_vid=600)]},
            {"header_versions": [_hv(property_id=7)]},
        ):
            stores = self._stores(**override)
            assert list(assignments.rule_4_10(_ctx(**stores))) == []


# ------------------------------------------------------------------
# Helper edge cases
# ------------------------------------------------------------------


class TestHelpers:
    def test_pc_rows_none_property(self) -> None:
        assert assignments._pc_rows(_ctx().snapshot, None) == []

    def test_context_ccs_none(self) -> None:
        assert assignments._context_ccs(_ctx().snapshot, None) == []

    def test_latest_by_release_date_missing_release(self) -> None:
        stores = _base(property_categories=[_pc(start=None)])
        ctx = _ctx(**stores)
        rows = assignments._latest_by_release_date(
            ctx,
            ctx.snapshot.property_categories,
            lambda r: r.start_release_id,
        )
        assert rows == []

    def test_category_code_none(self) -> None:
        assert (
            assignments._category_code(_ctx().snapshot, None) is None
        )
        assert (
            assignments._category_code(_ctx(**_base()).snapshot, 999)
            is None
        )

    def test_key_header_without_property_ignored(self) -> None:
        stores = _base(
            headers=[_header(), _header(2, is_key=True)],
            header_versions=[
                _hv(property_id=7),
                _hv(101, header_id=2),
            ],
            table_version_headers=[
                _tvh(),
                _tvh(10, 2, header_vid=101),
            ],
            item_categories=[_ic()],
            property_categories=[_pc()],
            categories=[_cat()],
        )
        assert list(assignments.rule_4_1a(_ctx(**stores))) == []
