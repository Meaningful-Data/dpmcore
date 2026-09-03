"""Integration tests for layout_exporter.queries."""

from __future__ import annotations

import tempfile
from pathlib import Path

from _helpers import (  # noqa: E402  (sys.path injected via conftest)
    add_context_composition,
    add_item_category,
    add_subcategory,
    add_subcategory_item,
    add_table,
    add_variable_version,
    build_basic_module_with_table,
    make_member,
    make_module,
    make_property,
    seed_data_types,
    seed_domain_category,
    seed_property_category,
    seed_releases,
)

from dpmcore.orm.glossary import Item, ItemCategory
from dpmcore.orm.release_sort_order import load_release_sort_orders
from dpmcore.services.layout_exporter import queries
from dpmcore.services.layout_exporter.models import ReleaseWindow

# Most tests do not care about release windows: an unbounded window
# selects the latest version of every code, like the DB's current state.
OPEN = ReleaseWindow()

# ---------------------------------------------------------------- #
# load_module_table_versions
# ---------------------------------------------------------------- #


def test_load_module_table_versions_no_release(memory_session):
    build_basic_module_with_table(memory_session)
    result = queries.load_module_table_versions(memory_session, "MOD1")
    assert len(result) == 1
    assert result[0].code == "T1"


def test_load_module_table_versions_with_release(memory_session):
    build_basic_module_with_table(memory_session)
    result = queries.load_module_table_versions(
        memory_session, "MOD1", release_code="1.0"
    )
    assert len(result) == 1
    assert result[0].code == "T1"


def test_load_module_table_versions_ordered(memory_session):
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    make_module(memory_session, module_id=1, module_vid=10, code="MOD1")
    add_table(
        memory_session,
        table_id=100,
        table_vid=1000,
        code="A_TBL",
        name="A",
        module_vid=10,
        order=2,
    )
    add_table(
        memory_session,
        table_id=101,
        table_vid=1001,
        code="B_TBL",
        name="B",
        module_vid=10,
        order=1,
    )
    memory_session.commit()
    result = queries.load_module_table_versions(memory_session, "MOD1")
    # Ordered by composition order
    assert [tv.code for tv in result] == ["B_TBL", "A_TBL"]


def test_load_module_table_versions_empty_for_unknown(memory_session):
    build_basic_module_with_table(memory_session)
    result = queries.load_module_table_versions(
        memory_session, "DOES_NOT_EXIST"
    )
    assert result == []


# ---------------------------------------------------------------- #
# load_table_version
# ---------------------------------------------------------------- #


def test_load_table_version_no_release(memory_session):
    build_basic_module_with_table(memory_session)
    tv = queries.load_table_version(memory_session, "T1")
    assert tv is not None
    assert tv.code == "T1"


def test_load_table_version_with_release(memory_session):
    build_basic_module_with_table(memory_session)
    tv = queries.load_table_version(memory_session, "T1", release_code="1.0")
    assert tv is not None
    assert tv.code == "T1"


def test_load_table_version_returns_none_when_missing(memory_session):
    build_basic_module_with_table(memory_session)
    assert queries.load_table_version(memory_session, "NOPE") is None


# ---------------------------------------------------------------- #
# load_headers / load_cells
# ---------------------------------------------------------------- #


def test_load_headers_returns_tuples(memory_session):
    build_basic_module_with_table(memory_session)
    rows = queries.load_headers(memory_session, 1000)
    assert len(rows) == 2
    for r in rows:
        assert len(r) == 3


def test_load_cells_returns_tuples(memory_session):
    build_basic_module_with_table(memory_session)
    rows = queries.load_cells(memory_session, 1000)
    assert len(rows) == 1
    assert len(rows[0]) == 2


# ---------------------------------------------------------------- #
# Code lookups
# ---------------------------------------------------------------- #


def test_load_dimension_codes_empty_returns_empty_dict(memory_session):
    assert queries._load_dimension_codes(memory_session, set(), OPEN) == {}


def test_load_dimension_codes_populated(memory_session):
    build_basic_module_with_table(memory_session)
    out = queries._load_dimension_codes(memory_session, {200}, OPEN)
    assert out == {200: "qCCB"}


def test_load_member_codes_empty_inputs(memory_session):
    assert queries._load_member_codes(memory_session, set(), set(), OPEN) == {}
    assert queries._load_member_codes(memory_session, {1}, set(), OPEN) == {}
    assert queries._load_member_codes(memory_session, set(), {1}, OPEN) == {}


def test_load_member_codes_populated(memory_session):
    seed_releases(memory_session)
    seed_property_category(memory_session)
    seed_domain_category(memory_session, 20, "DOM2")
    make_member(
        memory_session,
        item_id=500,
        name="MyMember",
        domain_category_id=20,
        code="m1",
    )
    memory_session.commit()
    out = queries._load_member_codes(memory_session, {500}, {20}, OPEN)
    assert out == {500: "m1"}


def test_load_member_codes_out_of_domain_filtered(memory_session):
    """Rows whose category isn't in the domain set are dropped."""
    seed_releases(memory_session)
    make_member(
        memory_session,
        item_id=500,
        name="InDomain",
        domain_category_id=20,
        code="keep",
    )
    make_member(
        memory_session,
        item_id=501,
        name="OutOfDomain",
        domain_category_id=99,
        code="drop",
    )
    memory_session.commit()
    # 99 is not in the requested domain set, so 501 is filtered in Python.
    out = queries._load_member_codes(memory_session, {500, 501}, {20}, OPEN)
    assert out == {500: "keep"}


def test_load_member_codes_multiple_domains_deterministic(memory_session):
    """An item in several in-domain categories resolves deterministically.

    The highest ``(category_id, code)`` wins last-write-wins, regardless
    of the backend's physical row order.
    """
    from dpmcore.orm.glossary import ItemCategory

    seed_releases(memory_session)
    # One item categorised under two domains the export spans.
    make_member(
        memory_session,
        item_id=500,
        name="MultiDomain",
        domain_category_id=20,
        code="aaa",
    )
    # Distinct start release: ItemCategory is unique on (item, start).
    memory_session.add(
        ItemCategory(
            item_id=500,
            start_release_id=2,
            category_id=21,
            code="bbb",
        ),
    )
    memory_session.commit()
    out = queries._load_member_codes(memory_session, {500}, {20, 21}, OPEN)
    assert out == {500: "bbb"}


# ---------------------------------------------------------------- #
# load_categorisations
# ---------------------------------------------------------------- #


def test_load_categorisations_empty(memory_session):
    assert queries.load_categorisations(memory_session, set(), OPEN) == {}


def test_load_categorisations_dim_no_property_category(memory_session):
    """Property has no PropertyCategory -> row[7] is None branch."""
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    # Don't set domain_category_id (no PropertyCategory)
    make_property(
        memory_session,
        property_id=200,
        name="OrphanDim",
        data_type_id=1,
        dim_code="OD",
        domain_category_id=None,
    )
    add_context_composition(
        memory_session, context_id=50, property_id=200, item_id=None
    )
    memory_session.commit()
    result = queries.load_categorisations(memory_session, {50}, OPEN)
    assert 50 in result


def test_load_categorisations_populated(memory_session):
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    seed_domain_category(memory_session, 20, "DOMM")

    # The dimension property
    make_property(
        memory_session,
        property_id=200,
        name="Dim 1",
        data_type_id=1,
        dim_code="DC1",
        domain_category_id=20,
    )
    # A member item in the domain
    make_member(
        memory_session,
        item_id=300,
        name="Member A",
        domain_category_id=20,
        code="ma",
    )
    add_context_composition(
        memory_session, context_id=50, property_id=200, item_id=300
    )
    memory_session.commit()

    result = queries.load_categorisations(memory_session, {50}, OPEN)
    assert 50 in result
    [dm] = result[50]
    assert dm.property_id == 200
    assert dm.dimension_label == "Dim 1"
    assert dm.dimension_code == "DC1"
    assert dm.domain_code == "DOMM"
    assert dm.member_label == "Member A"
    assert dm.member_code == "ma"
    assert dm.data_type_code == "m"


# ---------------------------------------------------------------- #
# load_property_as_categorisation
# ---------------------------------------------------------------- #


def test_load_property_as_categorisation_empty(memory_session):
    assert (
        queries.load_property_as_categorisation(memory_session, set(), OPEN)
        == {}
    )


def test_load_property_as_categorisation_populated(memory_session):
    build_basic_module_with_table(memory_session)
    out = queries.load_property_as_categorisation(memory_session, {200}, OPEN)
    assert 200 in out
    dm = out[200]
    assert dm.dimension_label == "Main Property"
    assert dm.dimension_code == "ATY"
    assert dm.domain_code == "DOM"
    assert dm.member_label == "Carrying amount"
    assert dm.member_code == "qCCB"
    assert dm.data_type_code == "m"


# ---------------------------------------------------------------- #
# load_dp_categorisations
# ---------------------------------------------------------------- #


def test_load_dp_categorisations_empty(memory_session):
    assert queries.load_dp_categorisations(memory_session, set(), OPEN) == {}


def test_load_dp_categorisations_with_member_item(memory_session):
    """row[3] populated -> member label comes from row[4] (member name)."""
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    seed_domain_category(memory_session, 20, "DOMX")
    make_property(
        memory_session,
        property_id=200,
        name="Dim",
        data_type_id=1,
        dim_code="DC1",
        domain_category_id=20,
    )
    make_member(
        memory_session,
        item_id=300,
        name="MemX",
        domain_category_id=20,
        code="mx",
    )
    add_context_composition(
        memory_session, context_id=50, property_id=200, item_id=300
    )
    add_variable_version(
        memory_session,
        variable_id=400,
        variable_vid=4000,
        code="V",
        context_id=50,
    )
    memory_session.commit()
    res = queries.load_dp_categorisations(memory_session, {4000}, OPEN)
    [dm] = res[4000]
    assert dm.member_label == "MemX"
    assert dm.member_code == "mx"


def test_load_dp_categorisations_no_property_category(memory_session):
    """Property without PropertyCategory hits the row[7] is None branch."""
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    make_property(
        memory_session,
        property_id=200,
        name="Dim",
        data_type_id=1,
        dim_code="DC1",
        domain_category_id=None,  # no PropertyCategory
    )
    add_context_composition(
        memory_session, context_id=50, property_id=200, item_id=None
    )
    add_variable_version(
        memory_session,
        variable_id=400,
        variable_vid=4000,
        code="V",
        context_id=50,
    )
    memory_session.commit()
    res = queries.load_dp_categorisations(memory_session, {4000}, OPEN)
    assert 4000 in res


def test_load_dp_categorisations_label_only(memory_session):
    """When item_id is None, member_label falls back to row[3] = '' empty."""
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    seed_domain_category(memory_session, 20, "DOMX")
    make_property(
        memory_session,
        property_id=200,
        name="Dim",
        data_type_id=1,
        dim_code="DC1",
        domain_category_id=20,
    )
    add_context_composition(
        memory_session, context_id=50, property_id=200, item_id=None
    )
    add_variable_version(
        memory_session,
        variable_id=400,
        variable_vid=4000,
        code="V",
        context_id=50,
    )
    memory_session.commit()
    res = queries.load_dp_categorisations(memory_session, {4000}, OPEN)
    [dm] = res[4000]
    assert dm.member_label == ""
    assert dm.member_code == ""


# ---------------------------------------------------------------- #
# load_subcategory_info
# ---------------------------------------------------------------- #


def test_load_subcategory_info_empty(memory_session):
    assert queries.load_subcategory_info(memory_session, set()) == {}


def test_load_subcategory_info_description_preferred(memory_session):
    seed_releases(memory_session)
    seed_property_category(memory_session)
    seed_domain_category(memory_session, 30, "CCC")
    add_subcategory(
        memory_session,
        subcategory_id=1,
        subcategory_vid=11,
        category_id=30,
        code="SC",
        description="Has Desc",
        name="Has Name",
    )
    memory_session.commit()
    out = queries.load_subcategory_info(memory_session, {11})
    assert out[11] == ("SC", "Has Desc", "CCC")


def test_load_subcategory_info_falls_back_to_name(memory_session):
    seed_releases(memory_session)
    seed_property_category(memory_session)
    seed_domain_category(memory_session, 30, "CCC")
    add_subcategory(
        memory_session,
        subcategory_id=1,
        subcategory_vid=11,
        category_id=30,
        code="SC",
        description=None,
        name="Just Name",
    )
    memory_session.commit()
    out = queries.load_subcategory_info(memory_session, {11})
    assert out[11] == ("SC", "Just Name", "CCC")


# ---------------------------------------------------------------- #
# load_key_variable_property_ids / load_variable_info
# ---------------------------------------------------------------- #


def test_load_key_variable_property_ids_empty(memory_session):
    assert queries.load_key_variable_property_ids(memory_session, set()) == {}


def test_load_key_variable_property_ids_populated(memory_session):
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    make_property(memory_session, property_id=200, name="P", data_type_id=1)
    add_variable_version(
        memory_session,
        variable_id=400,
        variable_vid=4000,
        code="V",
        property_id=200,
    )
    # one without property_id (filtered out)
    add_variable_version(
        memory_session,
        variable_id=401,
        variable_vid=4001,
        code="W",
        property_id=None,
    )
    memory_session.commit()
    out = queries.load_key_variable_property_ids(memory_session, {4000, 4001})
    assert out == {4000: 200}


def test_load_variable_info_empty(memory_session):
    assert queries.load_variable_info(memory_session, set()) == {}


def test_load_variable_info_populated(memory_session):
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    make_property(
        memory_session,
        property_id=200,
        name="Currency Domain",
        data_type_id=2,
    )
    add_variable_version(
        memory_session,
        variable_id=400,
        variable_vid=4000,
        code="V",
        property_id=200,
    )
    memory_session.commit()
    out = queries.load_variable_info(memory_session, {4000})
    assert out[4000] == (400, "e", "Currency Domain")


# Avoid lint complaint about unused imports
_ = (Path, tempfile)


# ---------------------------------------------------------------- #
# load_enumerations
# ---------------------------------------------------------------- #


def _seed_hierarchy(session):
    """A 'DOM' domain whose 'SC' hierarchy nests m2 under m1."""
    seed_releases(session)
    seed_property_category(session)
    seed_domain_category(session, 30, "DOM")
    add_subcategory(
        session,
        subcategory_id=1,
        subcategory_vid=11,
        category_id=30,
        code="SC",
        name="Type of identifier",
    )
    make_member(
        session,
        item_id=201,
        name="Member one",
        domain_category_id=30,
        code="m1",
        signature="eba_DOM:m1",
    )
    make_member(
        session,
        item_id=202,
        name="Member two",
        domain_category_id=30,
        code="m2",
        signature="eba_DOM:m2",
    )
    add_subcategory_item(session, subcategory_vid=11, item_id=201, order=1)
    add_subcategory_item(
        session, subcategory_vid=11, item_id=202, order=2, parent_item_id=201
    )


def test_load_enumerations_returns_values_in_hierarchy_order(memory_session):
    _seed_hierarchy(memory_session)
    memory_session.commit()

    enum = queries.load_enumerations(memory_session, {11}, OPEN)[11]

    assert (enum.code, enum.name, enum.category_code) == (
        "SC",
        "Type of identifier",
        "DOM",
    )
    assert [(v.code, v.signature, v.label, v.depth) for v in enum.values] == [
        ("m1", "eba_DOM:m1", "Member one", 0),
        ("m2", "eba_DOM:m2", "Member two", 1),
    ]


def test_load_enumerations_skips_items_without_a_code(memory_session):
    """An item outside the parent category has no code at this release."""
    _seed_hierarchy(memory_session)
    seed_domain_category(memory_session, 31, "OTHER")
    make_member(
        memory_session,
        item_id=203,
        name="Foreign",
        domain_category_id=31,
        code="f1",
    )
    add_subcategory_item(
        memory_session, subcategory_vid=11, item_id=203, order=3
    )
    memory_session.commit()

    enum = queries.load_enumerations(memory_session, {11}, OPEN)[11]
    assert [v.code for v in enum.values] == ["m1", "m2"]


def test_load_enumerations_empty_input(memory_session):
    assert queries.load_enumerations(memory_session, set(), OPEN) == {}


def test_load_enumerations_unknown_subcategory(memory_session):
    seed_releases(memory_session)
    memory_session.commit()
    assert queries.load_enumerations(memory_session, {999}, OPEN) == {}


def _seed_recoded_member(memory_session):
    """Member 201 is 'x7' up to release 2.0 and 'qx2015' from 2.0 on.

    The shape the EBA dictionary uses when a member is recoded.
    """
    seed_releases(memory_session)
    seed_property_category(memory_session)
    seed_domain_category(memory_session, 30, "DOM")
    add_subcategory(
        memory_session,
        subcategory_id=1,
        subcategory_vid=11,
        category_id=30,
        code="SC",
        name="Hierarchy",
    )
    memory_session.add(Item(item_id=201, name="Member one"))
    add_item_category(
        memory_session,
        item_id=201,
        domain_category_id=30,
        code="x7",
        signature="eba_DOM:x7",
        start_release_id=1,
        end_release_id=2,
    )
    add_item_category(
        memory_session,
        item_id=201,
        domain_category_id=30,
        code="qx2015",
        signature="eba_DOM:qx2015",
        start_release_id=2,
    )
    add_subcategory_item(
        memory_session, subcategory_vid=11, item_id=201, order=1
    )
    memory_session.commit()


def _signature_in(memory_session, window):
    enum = queries.load_enumerations(memory_session, {11}, window)[11]
    return [v.signature for v in enum.values]


def test_load_enumerations_reads_codes_inside_the_window(memory_session):
    """A window closing before the recoding keeps the old signature."""
    _seed_recoded_member(memory_session)
    window = ReleaseWindow(start_release_id=1, end_release_id=2)
    assert _signature_in(memory_session, window) == ["eba_DOM:x7"]


def test_load_enumerations_takes_the_latest_version_in_the_window(
    memory_session,
):
    """A recoding inside the window wins: the module reports the new code."""
    _seed_recoded_member(memory_session)
    window = ReleaseWindow(start_release_id=1, end_release_id=None)
    assert _signature_in(memory_session, window) == ["eba_DOM:qx2015"]


def test_load_enumerations_uses_the_version_in_force_at_the_window_start(
    memory_session,
):
    """No version starts inside the window: the one in force is used."""
    _seed_hierarchy(memory_session)  # both members start at release 1.0
    memory_session.commit()

    window = ReleaseWindow(start_release_id=2, end_release_id=None)
    enum = queries.load_enumerations(memory_session, {11}, window)[11]
    assert [v.signature for v in enum.values] == [
        "eba_DOM:m1",
        "eba_DOM:m2",
    ]


def test_load_enumerations_ignores_versions_expired_before_the_window(
    memory_session,
):
    """A member withdrawn before the window opened is not reported."""
    _seed_recoded_member(memory_session)
    # Drop the second version: item 201 now ends at release 2.0.
    memory_session.query(ItemCategory).filter(
        ItemCategory.item_id == 201,
        ItemCategory.start_release_id == 2,
    ).delete()
    memory_session.commit()

    window = ReleaseWindow(start_release_id=2, end_release_id=None)
    assert _signature_in(memory_session, window) == []


def test_pick_in_window_breaks_ties_on_release_id(memory_session):
    """Overlapping versions must still resolve deterministically."""
    seed_releases(memory_session)
    memory_session.commit()
    sort_orders = load_release_sort_orders(memory_session)
    rows = [
        ("k", 1, None, "first"),
        ("k", 2, None, "second"),
    ]
    picked = queries._pick_in_window(rows, sort_orders, ReleaseWindow())
    assert picked == {"k": "second"}
    # Reversing the input order must not change the winner.
    picked = queries._pick_in_window(
        list(reversed(rows)), sort_orders, ReleaseWindow()
    )
    assert picked == {"k": "second"}
