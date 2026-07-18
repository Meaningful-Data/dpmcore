"""Unit tests for the 5_x consistency checks."""

from __future__ import annotations

from dpmcore.services.model_validation.types import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)
from dpmcore.services.variable_generation.checks import (
    apply_5_5,
    apply_5_6_stale_modules,
    blocking_checks,
    check_5_6_shared_aspect,
)
from tests.unit.services.variable_generation.builders import (
    CUR,
    PREV,
    mv,
    mvc,
    rec,
    rel,
    snap,
    tv,
    tvc,
    var,
    vv,
)


def _codes(violations):
    return [v.rule_id for v in violations]


# ------------------------------------------------------------------
# 5_1
# ------------------------------------------------------------------


def test_5_1_expired_version_in_active_table_version():
    bad = rec(tv_start=PREV, vv_old_end=PREV)
    duplicate = rec(module_vid=501, tv_start=PREV, vv_old_end=PREV)
    found = blocking_checks(
        [bad, duplicate], snap(table_versions=[tv(start=PREV)]), rel()
    )
    assert _codes(found) == ["5_1"]
    violation = found[0]
    assert violation.severity == SEVERITY_ERROR
    assert violation.objects[0].id == 1000
    assert violation.objects[1].code == "T1"


def test_5_1_requires_all_conditions():
    cases = [
        rec(tv_start=PREV, vv_old_end=PREV, mv_start=PREV),
        rec(tv_start=None, vv_old_end=PREV),
        rec(tv_start=CUR, vv_old_end=PREV),
        rec(tv_start=PREV, vv_old_end=None),
        rec(tv_start=PREV, vv_old_end=PREV, is_void=True),
    ]
    assert blocking_checks(cases, snap(), rel()) == []


# ------------------------------------------------------------------
# 5_2
# ------------------------------------------------------------------


def _pair_5_2(**second_overrides):
    first = rec(old_variable_id=600, new_property_id=10)
    defaults = {
        "cell_id": 1001,
        "old_variable_id": 600,
        "new_property_id": 11,
    }
    defaults.update(second_overrides)
    return [first, rec(**defaults)]


def test_5_2_same_variable_diverging_aspects():
    first, second = _pair_5_2()
    # the same pair seen through a second module dedupes
    twins = [
        rec(module_vid=501, old_variable_id=600, new_property_id=10),
        rec(
            module_vid=501,
            cell_id=1001,
            old_variable_id=600,
            new_property_id=11,
        ),
    ]
    found = blocking_checks(
        [first, second, *twins], snap(), rel()
    )
    assert _codes(found) == ["5_2"]
    assert [o.id for o in found[0].objects[:2]] == [1000, 1001]


def test_5_2_negative_cases():
    cases = [
        # same new aspect
        _pair_5_2(new_property_id=10),
        # key changed on one side
        _pair_5_2(new_key_id="key:1"),
        # datatype change on one side
        _pair_5_2(is_new_property_datatype=True),
        # new cell on one side
        _pair_5_2(is_new_cell=True),
        # old module on one side
        _pair_5_2(mv_start=PREV),
        # different variable
        _pair_5_2(old_variable_id=601),
    ]
    for records in cases:
        assert blocking_checks(records, snap(), rel()) == [], records


def test_5_2_void_first_cell_is_skipped_but_not_second():
    first, second = _pair_5_2()
    first.is_void = True
    assert blocking_checks([first, second], snap(), rel()) == []
    # SQL only filters cm.IsVoid, not cm2's
    first, second = _pair_5_2(is_void=True)
    found = blocking_checks([first, second], snap(), rel())
    assert _codes(found) == ["5_2"]


def test_5_2_first_side_conditions_gate_the_pair():
    # the *first* record fails the shared conditions
    first = rec(
        old_variable_id=600,
        new_property_id=10,
        is_new_property_datatype=True,
    )
    second = rec(
        cell_id=1001, old_variable_id=600, new_property_id=11
    )
    assert blocking_checks([first, second], snap(), rel()) == []


def test_5_2_records_without_variable_are_ignored():
    records = [rec(new_property_id=10), rec(cell_id=1001)]
    assert blocking_checks(records, snap(), rel()) == []


# ------------------------------------------------------------------
# 5_3
# ------------------------------------------------------------------


def _pair_5_3(**second_overrides):
    first = rec(old_variable_id=600, new_property_id=10)
    defaults = {
        "cell_id": 1001,
        "old_variable_id": 601,
        "new_property_id": 10,
    }
    defaults.update(second_overrides)
    return [first, rec(**defaults)]


def test_5_3_different_variables_same_aspect():
    found = blocking_checks(_pair_5_3(), snap(), rel())
    assert _codes(found) == ["5_3"]


def test_5_3_negative_cases():
    cases = [
        _pair_5_3(old_variable_id=600),  # same variable
        _pair_5_3(is_new_cell=True),
        _pair_5_3(mv_start=PREV),
        _pair_5_3(old_variable_id=None),
    ]
    for records in cases:
        assert blocking_checks(records, snap(), rel()) == [], records
    # first-side conditions
    first, second = _pair_5_3()
    first.is_new_cell = True
    assert blocking_checks([first, second], snap(), rel()) == []
    first, second = _pair_5_3()
    first.is_void = True
    assert blocking_checks([first, second], snap(), rel()) == []
    first, second = _pair_5_3()
    first.mv_start = PREV
    assert blocking_checks([first, second], snap(), rel()) == []
    first, second = _pair_5_3()
    first.old_variable_id = None
    assert blocking_checks([first, second], snap(), rel()) == []


# ------------------------------------------------------------------
# 5_4
# ------------------------------------------------------------------


def _void_stores(*, void_flag=True):
    return {
        "table_version_cells": [
            tvc(10, 1000, is_void=void_flag),
            tvc(10, 1001),
        ]
    }


def test_5_4_void_cell_sharing_aspect():
    records = [
        rec(new_property_id=10, is_void=True),
        rec(cell_id=1001, new_property_id=10),
    ]
    found = blocking_checks(records, snap(**_void_stores()), rel())
    assert _codes(found) == ["5_4"]


def test_5_4_second_variant_via_other_cells_table_version():
    records = [
        rec(new_property_id=10, is_void=True, tv_start=PREV),
        rec(cell_id=1001, new_property_id=10, tv_start=CUR),
    ]
    found = blocking_checks(records, snap(**_void_stores()), rel())
    assert _codes(found) == ["5_4"]


def test_5_4_negative_cases():
    # both table versions old
    records = [
        rec(new_property_id=10, is_void=True, tv_start=PREV),
        rec(cell_id=1001, new_property_id=10, tv_start=PREV),
    ]
    assert (
        blocking_checks(records, snap(**_void_stores()), rel()) == []
    )
    # TVC flag is excluded-only (is_void is not True)
    records = [
        rec(new_property_id=10, is_void=True),
        rec(cell_id=1001, new_property_id=10),
    ]
    assert (
        blocking_checks(
            records, snap(**_void_stores(void_flag=None)), rel()
        )
        == []
    )
    # the second cell is void too
    records = [
        rec(new_property_id=10, is_void=True),
        rec(cell_id=1001, new_property_id=10, is_void=True),
    ]
    assert (
        blocking_checks(records, snap(**_void_stores()), rel()) == []
    )
    # same cell id never pairs with itself
    records = [
        rec(new_property_id=10, is_void=True),
        rec(module_vid=501, new_property_id=10),
    ]
    assert (
        blocking_checks(records, snap(**_void_stores()), rel()) == []
    )


# ------------------------------------------------------------------
# 5_5
# ------------------------------------------------------------------


def _record_5_5(**overrides):
    defaults = {
        "old_property_id": 10,
        "new_property_id": 10,
        "outcome_id": "OLD",
        "outcome_vid": "NEW",
        "new_vvid_ref": "vv:1",
        "vv_old_end": PREV,
    }
    defaults.update(overrides)
    return rec(**defaults)


def test_5_5_warns_and_overwrites_message():
    matched = _record_5_5()
    twin = _record_5_5(module_vid=501)
    found = apply_5_5([matched, twin], rel())
    assert _codes(found) == ["5_5"]
    assert found[0].severity == SEVERITY_WARNING
    assert matched.report_msg == found[0].message
    assert twin.report_msg == found[0].message


def test_5_5_negative_cases():
    cases = [
        _record_5_5(tv_start=PREV),
        _record_5_5(new_property_id=11),  # aspect changed
        _record_5_5(is_new_cell=True),
        _record_5_5(outcome_id="NEW"),
        _record_5_5(outcome_vid="OLD"),
        _record_5_5(new_vvid_ref=None),
        _record_5_5(vv_old_end=None),
        _record_5_5(is_void=True),
    ]
    for record in cases:
        assert apply_5_5([record], rel()) == []
        assert record.report_msg is None


# ------------------------------------------------------------------
# 5_6 shared aspect
# ------------------------------------------------------------------


def _shared_stores(**overrides):
    stores = {
        "variables": [var(700)],
        "variable_versions": [
            vv(7000, variable_id=700, property_id=10)
        ],
        "table_version_cells": [
            tvc(30, 3000, code="other", variable_vid=7000)
        ],
        "module_versions": [mv(501, start=PREV, code="OTH")],
        "module_version_compositions": [
            mvc(501, table_id=3, table_vid=30)
        ],
        "table_versions": [tv()],
    }
    stores.update(overrides)
    return stores


def _record_5_6(**overrides):
    defaults = {
        "new_property_id": 10,
        "new_vvid_ref": "vv:1",
        "new_variable_ref": 600,
    }
    defaults.update(overrides)
    return rec(**defaults)


def test_5_6_shared_aspect_warns_for_old_and_current_modules():
    record = _record_5_6()
    found = check_5_6_shared_aspect(
        [record], snap(**_shared_stores()), rel()
    )
    assert _codes(found) == ["5_6"]
    assert "OTH" in found[0].message
    # variant with the other module changing in this release
    found = check_5_6_shared_aspect(
        [record],
        snap(**_shared_stores(module_versions=[mv(501, code="NEWM")])),
        rel(),
    )
    assert _codes(found) == ["5_6"]


def test_5_6_shared_aspect_deduplicates_pairs():
    record = _record_5_6()
    twin = _record_5_6(module_vid=502)
    stores = _shared_stores(
        module_version_compositions=[
            mvc(501, table_id=3, table_vid=30),
            mvc(501, table_id=3, table_vid=30),
        ]
    )
    found = check_5_6_shared_aspect(
        [record, twin], snap(**stores), rel()
    )
    assert len(found) == 1


def test_5_6_shared_aspect_negative_record_conditions():
    cases = [
        _record_5_6(mv_start=PREV),
        _record_5_6(new_vvid_ref=None),
        _record_5_6(is_void=True),
        _record_5_6(new_variable_ref=None),
    ]
    for record in cases:
        found = check_5_6_shared_aspect(
            [record], snap(**_shared_stores()), rel()
        )
        assert found == [], record


def test_5_6_shared_aspect_negative_version_conditions():
    record = _record_5_6()
    cases = [
        # expired version
        {"variable_versions": [vv(7000, variable_id=700, property_id=10, end=PREV)]},
        # aspect mismatch on key
        {"variable_versions": [vv(7000, variable_id=700, property_id=10, key_id=7)]},
        # aspect mismatch on context
        {"variable_versions": [vv(7000, variable_id=700, property_id=10, context_id=40)]},
        # property mismatch
        {"variable_versions": [vv(7000, variable_id=700, property_id=11)]},
        # dangling variable id
        {"variable_versions": [vv(7000, variable_id=None, property_id=10)]},
        # same variable as the record's assignment
        {"variable_versions": [vv(7000, variable_id=600, property_id=10)]},
        # the other cell is the record's own cell
        {
            "table_version_cells": [
                tvc(30, 1000, code="self", variable_vid=7000)
            ]
        },
        # the other module version is closed
        {"module_versions": [mv(501, start=PREV, end=CUR)]},
        # no module version at all
        {"module_versions": []},
        # nobody references the version
        {"table_version_cells": []},
    ]
    for override in cases:
        stores = _shared_stores(**override)
        found = check_5_6_shared_aspect(
            [record], snap(**stores), rel()
        )
        assert found == [], override


def test_5_6_shared_aspect_requires_new_property():
    record = _record_5_6(new_property_id=None)
    stores = _shared_stores(
        variable_versions=[vv(7000, variable_id=700, property_id=None)]
    )
    assert (
        check_5_6_shared_aspect([record], snap(**stores), rel()) == []
    )


# ------------------------------------------------------------------
# 5_6 stale modules
# ------------------------------------------------------------------


def _record_5_6d(**overrides):
    defaults = {
        "old_variable_id": 600,
        "outcome_id": "OLD",
        "outcome_vid": "NEW",
        "new_vvid_ref": "vv:1",
    }
    defaults.update(overrides)
    return rec(**defaults)


def _stale_rows():
    return [
        rec(
            module_vid=502,
            module_code="ZZZ",
            mv_start=PREV,
            old_variable_id=600,
            vv_old_end=PREV,
            cell_id=5000,
        ),
        rec(
            module_vid=503,
            module_code="AAA",
            mv_start=PREV,
            old_variable_id=600,
            vv_old_end=PREV,
            cell_id=5001,
        ),
        # a later, larger code does not displace the minimum
        rec(
            module_vid=504,
            module_code="MMM",
            mv_start=PREV,
            old_variable_id=600,
            vv_old_end=PREV,
            cell_id=5002,
        ),
    ]


def test_5_6_stale_modules_warns_with_min_module_code():
    record = _record_5_6d()
    twin = _record_5_6d(module_vid=501)
    found = apply_5_6_stale_modules(
        [record, twin, *_stale_rows()], rel()
    )
    assert _codes(found) == ["5_6"]
    assert "AAA" in found[0].message
    assert record.report_msg == found[0].message


def test_5_6_stale_modules_negative_cases():
    stale = _stale_rows()
    cases = [
        _record_5_6d(tv_start=PREV),
        _record_5_6d(is_new_cell=True),
        _record_5_6d(outcome_id="NEW"),
        _record_5_6d(outcome_vid="OLD"),
        _record_5_6d(new_vvid_ref=None),
        _record_5_6d(is_void=True),
        _record_5_6d(old_variable_id=601),
    ]
    for record in cases:
        assert apply_5_6_stale_modules([record, *stale], rel()) == []
    # stale set requires expired versions and module codes
    incomplete_stale = [
        rec(mv_start=PREV, old_variable_id=600, vv_old_end=None),
        rec(mv_start=PREV, old_variable_id=None, vv_old_end=PREV),
        rec(
            mv_start=PREV,
            old_variable_id=600,
            vv_old_end=PREV,
            module_code=None,
        ),
        rec(mv_start=CUR, old_variable_id=600, vv_old_end=PREV),
    ]
    record = _record_5_6d()
    assert (
        apply_5_6_stale_modules([record, *incomplete_stale], rel())
        == []
    )
