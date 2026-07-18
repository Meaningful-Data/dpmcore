"""Unit tests for the filing-indicator derivation."""

from __future__ import annotations

from dpmcore.services.variable_generation.filing_indicators import (
    codes_for_table_version,
    generate_filing_indicators,
)
from tests.unit.services.variable_generation.builders import (
    CUR,
    PREV,
    cat,
    ccomp,
    ctx,
    ic,
    item,
    mp,
    mv,
    mvc,
    rel,
    snap,
    state,
    tv,
    var,
    vv,
)

TEMPLATE = item(800, name="Template", is_property=True)
IS_REPORTED = item(801, name="isReported", is_property=True)


def _fi_stores(**overrides):
    """One current module employing TV 10 with code ' T1 '."""
    stores = {
        "table_versions": [tv(code=" T1 ")],
        "module_versions": [mv()],
        "module_version_compositions": [mvc()],
        "categories": [cat()],
        "items": [TEMPLATE, IS_REPORTED],
    }
    stores.update(overrides)
    return stores


# ------------------------------------------------------------------
# Code derivation
# ------------------------------------------------------------------


def test_codes_plain_table_version():
    snapshot = snap(table_versions=[tv(code=" T1 ")])
    assert codes_for_table_version(
        snapshot, snapshot.table_versions[0]
    ) == ["T1"]


def test_codes_expired_or_codeless_contribute_nothing():
    snapshot = snap(
        table_versions=[tv(end=CUR), tv(11, code=None)]
    )
    assert (
        codes_for_table_version(snapshot, snapshot.table_versions[0])
        == []
    )
    assert (
        codes_for_table_version(snapshot, snapshot.table_versions[1])
        == []
    )


def test_codes_abstract_resolution():
    snapshot = snap(
        table_versions=[
            # technical table pointing at abstract table 9
            tv(10, code="T1a", abstract_table_id=9),
            # abstract versions: one active, one expired, one codeless
            tv(90, table_id=9, code=" A1 ", start=PREV),
            tv(91, table_id=9, code="A0", start=PREV, end=PREV),
            tv(92, table_id=9, code=None, start=PREV),
            # technical table whose abstract table has no versions
            tv(11, code="T2", abstract_table_id=8),
            # ... and one without even its own code
            tv(12, code=None, abstract_table_id=8),
            # technical table whose abstract versions are all expired
            tv(13, code="T3", abstract_table_id=7),
            tv(70, table_id=7, code="A7", start=PREV, end=PREV),
        ]
    )
    by_vid = snapshot.table_versions_by_vid
    assert codes_for_table_version(snapshot, by_vid[10]) == ["A1"]
    assert codes_for_table_version(snapshot, by_vid[11]) == ["T2"]
    assert codes_for_table_version(snapshot, by_vid[12]) == []
    assert codes_for_table_version(snapshot, by_vid[13]) == []


# ------------------------------------------------------------------
# Proposal bundles
# ------------------------------------------------------------------


def test_brand_new_filing_indicator_bundle():
    gen = state()
    generate_filing_indicators(snap(**_fi_stores()), rel(), gen)
    assert [f.to_dict() for f in gen.filing_indicators] == [
        {
            "temp_id": "fi:1",
            "code": "T1",
            "module_vids": [500],
            "item_ref": "fi:1",
            "item_category_signature": "eba__TE:T1",
            "context_ref": "ctx:1",
            "variable_ref": "var:1",
            "variable_version_ref": "vv:1",
        }
    ]
    assert [c.to_dict() for c in gen.fi_contexts] == [
        {
            "temp_id": "ctx:1",
            "signature": "800_fi:1#",
            "compositions": [[800, "fi:1"]],
        }
    ]
    variable = gen.fi_variables[0]
    assert variable.type == "filingindicator"
    assert variable.code == "T1"
    version = variable.versions[0]
    assert version.aspect.property_id == 801
    assert version.aspect.context_id == "ctx:1"
    assert version.code == "T1"


def test_fully_existing_filing_indicator_is_skipped():
    stores = _fi_stores(
        items=[TEMPLATE, IS_REPORTED, item(802, name="T1 item")],
        item_categories=[ic(802, code=" T1 ")],
        contexts=[ctx(41, signature="800_802#")],
        context_compositions=[ccomp(41, 800, 802)],
        variables=[var(650, type_="filingindicator")],
        variable_versions=[
            vv(6500, variable_id=650, property_id=801, code="T1")
        ],
        module_parameters=[mp(500, 6500)],
    )
    gen = state()
    generate_filing_indicators(snap(**stores), rel(), gen)
    assert gen.filing_indicators == []
    assert gen.fi_variables == []
    assert gen.fi_contexts == []


def test_existing_item_but_missing_links_emits_bundle():
    stores = _fi_stores(
        items=[TEMPLATE, IS_REPORTED, item(802, name="T1 item")],
        item_categories=[ic(802, code="T1")],
        contexts=[ctx(41, signature="800_802#")],
        context_compositions=[
            ccomp(41, 800, 802),
            # a second, multi-composition context wins max()
            ccomp(42, 800, 802),
            ccomp(42, 11, 70),
        ],
        variables=[var(650, type_="filingindicator")],
        variable_versions=[
            vv(6500, variable_id=650, property_id=801, code="T1")
        ],
    )
    gen = state()
    generate_filing_indicators(snap(**stores), rel(), gen)
    bundle = gen.filing_indicators[0]
    assert bundle.temp_id == "fi:1"
    assert bundle.item_ref == 802
    assert bundle.item_category_signature is None
    assert bundle.context_ref == 42
    assert bundle.variable_ref == 650
    assert bundle.variable_version_ref == 6500
    assert bundle.module_vids == (500,)
    assert gen.fi_variables == []


def test_single_composition_context_prevents_new_context():
    # Context 41 exists with a *different* signature but is a
    # 1-composition Template->T1 context: no new context, and the
    # pool by exact item resolves it.
    stores = _fi_stores(
        items=[TEMPLATE, IS_REPORTED, item(802, name="T1 item")],
        item_categories=[ic(802, code="T1")],
        contexts=[ctx(41, signature="something-else")],
        context_compositions=[ccomp(41, 800, 802)],
    )
    gen = state()
    generate_filing_indicators(snap(**stores), rel(), gen)
    bundle = gen.filing_indicators[0]
    assert bundle.context_ref == 41
    assert gen.fi_contexts == []


def test_signature_match_with_empty_pool_leaves_context_none():
    # The signature exists as a Context row but no composition links
    # the Template property to the item: pool is empty.
    stores = _fi_stores(
        items=[TEMPLATE, IS_REPORTED, item(802, name="T1 item")],
        item_categories=[ic(802, code="T1")],
        contexts=[ctx(41, signature="800_802#")],
    )
    gen = state()
    generate_filing_indicators(snap(**stores), rel(), gen)
    assert gen.filing_indicators[0].context_ref is None
    assert gen.fi_contexts == []


def test_without_template_item_no_context_is_proposed():
    stores = _fi_stores(items=[IS_REPORTED])
    gen = state()
    generate_filing_indicators(snap(**stores), rel(), gen)
    bundle = gen.filing_indicators[0]
    assert bundle.context_ref is None
    assert gen.fi_variables[0].versions[0].aspect.context_id is None


def test_without_is_reported_item_variable_has_no_version():
    stores = _fi_stores(items=[TEMPLATE])
    gen = state()
    generate_filing_indicators(snap(**stores), rel(), gen)
    bundle = gen.filing_indicators[0]
    variable = gen.fi_variables[0]
    assert variable.versions == ()
    assert variable.aspect is None
    assert bundle.variable_version_ref is None
    assert bundle.module_vids == ()


def test_fi_version_lookup_filters():
    stores = _fi_stores(
        variables=[
            var(650, type_="filingindicator"),
            var(651, type_="fact"),
        ],
        variable_versions=[
            # expired FI version
            vv(6500, variable_id=650, code="T1", end=PREV),
            # codeless FI version
            vv(6501, variable_id=650, code=None),
            # fact variable with the code
            vv(6510, variable_id=651, code="T1"),
            # dangling variable
            vv(6520, variable_id=None, code="T1"),
        ],
    )
    gen = state()
    generate_filing_indicators(snap(**stores), rel(), gen)
    # none of the above counts as an existing FI variable
    assert len(gen.fi_variables) == 1


def test_fi_version_ties_resolve_to_highest_vid():
    stores = _fi_stores(
        items=[TEMPLATE, IS_REPORTED, item(802, name="T1 item")],
        item_categories=[ic(802, code="T1")],
        contexts=[ctx(41, signature="800_802#")],
        context_compositions=[ccomp(41, 800, 802)],
        variables=[var(650, type_="filingindicator")],
        variable_versions=[
            vv(6500, variable_id=650, property_id=801, code="T1"),
            vv(6501, variable_id=650, property_id=801, code="T1"),
            vv(6499, variable_id=650, property_id=801, code="T1"),
        ],
    )
    gen = state()
    generate_filing_indicators(snap(**stores), rel(), gen)
    assert gen.filing_indicators[0].variable_version_ref == 6501


def test_templates_item_lookup_filters():
    stores = _fi_stores(
        items=[TEMPLATE, IS_REPORTED, item(802), item(803)],
        item_categories=[
            # expired
            ic(802, code="T1", end=PREV),
            # other category
            ic(802, category_id=901, code="T1"),
            # codeless
            ic(802, code=None),
            # duplicates: highest item wins (in either order)
            ic(802, code="X1"),
            ic(803, code="X1"),
            ic(802, code="X1", start=CUR),
        ],
    )
    gen = state()
    generate_filing_indicators(snap(**stores), rel(), gen)
    # T1 is still missing (only category-900 active rows count)
    assert gen.filing_indicators[0].item_ref == "fi:1"


def test_module_links_require_current_active_module():
    stores = _fi_stores(
        table_versions=[
            tv(code="T1"),
            # expired TV with the same code contributes no link
            tv(11, code="T1", end=CUR),
        ],
        module_versions=[
            mv(),
            mv(501, start=PREV),  # old module
            mv(502, end=CUR),  # closed module
        ],
        module_version_compositions=[
            mvc(),
            mvc(501, table_vid=10),
            mvc(502, table_vid=10),
            mvc(500, table_vid=11),
            mvc(500, table_vid=None),
            mvc(500, table_vid=99),  # dangling table version
        ],
    )
    gen = state()
    generate_filing_indicators(snap(**stores), rel(), gen)
    assert gen.filing_indicators[0].module_vids == (500,)


def test_abstract_code_matching_links_module():
    stores = _fi_stores(
        table_versions=[
            tv(10, code="T1a", abstract_table_id=9),
            tv(90, table_id=9, code="A1", start=PREV),
        ],
    )
    gen = state()
    generate_filing_indicators(snap(**stores), rel(), gen)
    bundle = gen.filing_indicators[0]
    assert bundle.code == "A1"
    assert bundle.module_vids == (500,)


def test_fi_codes_skip_modules_not_in_current_release():
    stores = _fi_stores(module_versions=[mv(start=PREV)])
    gen = state()
    generate_filing_indicators(snap(**stores), rel(), gen)
    assert gen.filing_indicators == []
