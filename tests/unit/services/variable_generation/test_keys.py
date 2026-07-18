"""Unit tests for key-variable identification and compound keys."""

from __future__ import annotations

from dpmcore.services.variable_generation.keys import (
    generate_compound_keys,
    identify_key_variables,
)
from tests.unit.services.variable_generation.builders import (
    PREV,
    ck,
    header,
    hv,
    mv,
    mvc,
    rel,
    snap,
    state,
    table,
    tv,
    tvh,
    var,
    vv,
)


def _key_stores(**overrides):
    """One current TV (10) with key header 1 / hv 100 (property 20)."""
    stores = {
        "tables": [table()],
        "table_versions": [tv()],
        "headers": [header(is_key=True)],
        "header_versions": [hv(100, property_id=20)],
        "table_version_headers": [tvh()],
        "module_versions": [mv()],
        "module_version_compositions": [mvc()],
    }
    stores.update(overrides)
    return stores


def test_proposes_missing_key_variable_and_resolves_header():
    gen = state()
    identify_key_variables(snap(**_key_stores()), rel(), gen)
    assert [v.temp_id for v in gen.key_variables] == ["var:1"]
    proposed = gen.key_variables[0]
    assert proposed.type == "key"
    assert proposed.versions[0].aspect.property_id == 20
    assert gen.key_variable_by_property == {20: "vv:1"}
    assert gen.header_key_refs == {100: "vv:1"}


def test_existing_key_variable_is_not_reproposed():
    stores = _key_stores(
        variables=[var(600, type_="key")],
        variable_versions=[
            vv(6000, variable_id=600, property_id=20),
            vv(6001, variable_id=600, property_id=20),
            vv(5999, variable_id=600, property_id=20),
        ],
    )
    gen = state()
    identify_key_variables(snap(**stores), rel(), gen)
    assert gen.key_variables == []
    # ties resolve to the highest VariableVID
    assert gen.key_variable_by_property == {20: 6001}
    assert gen.header_key_refs == {100: 6001}


def test_key_variable_lookup_ignores_non_key_and_expired():
    stores = _key_stores(
        variables=[var(600, type_="key"), var(601, type_="fact")],
        variable_versions=[
            # expired key version does not count
            vv(6000, variable_id=600, property_id=20, end=PREV),
            # fact variable does not count
            vv(6100, variable_id=601, property_id=20),
            # dangling variable id
            vv(6200, variable_id=None, property_id=20),
            # key version without a property
            vv(6300, variable_id=600, property_id=None),
        ],
    )
    gen = state()
    identify_key_variables(snap(**stores), rel(), gen)
    assert [v.temp_id for v in gen.key_variables] == ["var:1"]


def test_missing_key_variable_requires_current_tv_and_module():
    cases = [
        {"table_versions": [tv(start=PREV)]},
        {"module_versions": [mv(start=PREV)]},
        {"module_versions": []},
        {"module_version_compositions": [mvc(table_vid=None)]},
        {"table_version_headers": [tvh(header_vid=None)]},
        # dangling header version
        {"header_versions": []},
        # header version without a property
        {"header_versions": [hv(100, property_id=None)]},
        # non-key header
        {"headers": [header(is_key=False)]},
        # dangling header
        {"headers": []},
        # header version without a header
        {"header_versions": [hv(100, header_id=None, property_id=20)]},
    ]
    for override in cases:
        stores = _key_stores()
        stores.update(override)
        gen = state()
        identify_key_variables(snap(**stores), rel(), gen)
        assert gen.key_variables == [], override


def test_header_key_refs_only_for_current_release_headers():
    stores = _key_stores(
        headers=[header(is_key=True), header(2, is_key=True)],
        header_versions=[
            hv(100, property_id=20),
            # old HV: keeps its stored KeyVariableVID, no virtual ref
            hv(200, header_id=2, property_id=21, start=PREV),
            # current HV whose property has no key variable at all
            hv(300, header_id=2, property_id=None),
        ],
    )
    gen = state()
    identify_key_variables(snap(**stores), rel(), gen)
    assert set(gen.header_key_refs) == {100}


def test_header_key_ref_none_when_property_unresolved():
    # A current key HV whose property is not used by any current TV:
    # no proposal is made, so the ref stays unset.
    stores = _key_stores(
        header_versions=[
            hv(100, property_id=20),
            hv(400, header_id=1, property_id=99, end=None),
        ],
        table_version_headers=[tvh(header_vid=100)],
    )
    gen = state()
    identify_key_variables(snap(**stores), rel(), gen)
    assert 400 not in gen.header_key_refs


# ------------------------------------------------------------------
# Compound keys
# ------------------------------------------------------------------


def _prepare(stores):
    snapshot = snap(**stores)
    gen = state()
    identify_key_variables(snapshot, rel(), gen)
    generate_compound_keys(snapshot, rel(), gen)
    return gen


def test_proposes_compound_key_with_proposed_member():
    gen = _prepare(_key_stores())
    assert [k.to_dict() for k in gen.compound_keys] == [
        {
            "temp_id": "key:1",
            "signature": "20#",
            "member_variable_refs": ["vv:1"],
        }
    ]
    assert gen.key_by_table_vid == {10: "key:1"}


def test_existing_compound_key_is_reused():
    stores = _key_stores(
        variables=[var(600, type_="key")],
        variable_versions=[vv(6000, variable_id=600, property_id=20)],
        compound_keys=[
            ck(70, signature="20#"),
            ck(71, signature="20#"),  # duplicate: highest id wins
            ck(69, signature="20#"),
            ck(72, signature=None),
        ],
    )
    gen = _prepare(stores)
    assert gen.compound_keys == []
    assert gen.key_by_table_vid == {10: 71}


def test_signature_orders_properties_and_keeps_stored_refs():
    stores = _key_stores(
        headers=[header(is_key=True), header(2, is_key=True)],
        header_versions=[
            hv(100, property_id=21),
            # an *old* key HV carries its stored KeyVariableVID
            hv(
                200,
                header_id=2,
                property_id=20,
                start=PREV,
                key_variable_vid=6000,
            ),
            # expired versions do not contribute
            hv(201, header_id=2, property_id=99, start=PREV, end=PREV),
        ],
        table_version_headers=[tvh(), tvh(header_id=2, header_vid=200)],
    )
    gen = _prepare(stores)
    key = gen.compound_keys[0]
    assert key.signature == "20#21#"
    # property 21 (hv 100, current) resolves to the proposed key
    # variable for 21 (vv:2 — 20 was proposed first); property 20
    # (old hv 200) keeps its stored KeyVariableVID.
    assert key.member_variable_refs == (6000, "vv:2")


def test_table_without_key_properties_gets_no_signature():
    stores = _key_stores(
        header_versions=[hv(100, property_id=None)],
    )
    gen = _prepare(stores)
    assert gen.compound_keys == []
    assert gen.key_by_table_vid == {}


def test_non_key_headers_do_not_contribute():
    stores = _key_stores(headers=[header(is_key=False)])
    gen = _prepare(stores)
    assert gen.compound_keys == []


def test_dangling_header_rows_are_skipped():
    stores = _key_stores(headers=[])
    gen = _prepare(stores)
    assert gen.compound_keys == []


def test_shared_signature_collects_members_of_both_tables():
    stores = _key_stores(
        tables=[table(), table(2)],
        table_versions=[tv(), tv(11, table_id=2, code="T2")],
        headers=[
            header(is_key=True),
            header(2, table_id=2, is_key=True),
        ],
        header_versions=[
            hv(100, property_id=20),
            hv(
                200,
                header_id=2,
                property_id=20,
                start=PREV,
                key_variable_vid=6000,
            ),
        ],
        table_version_headers=[
            tvh(),
            tvh(11, 2, header_vid=200),
        ],
        module_version_compositions=[mvc(), mvc(table_id=2, table_vid=11)],
    )
    gen = _prepare(stores)
    assert len(gen.compound_keys) == 1
    key = gen.compound_keys[0]
    assert key.signature == "20#"
    assert key.member_variable_refs == (6000, "vv:1")
    assert gen.key_by_table_vid == {10: "key:1", 11: "key:1"}
