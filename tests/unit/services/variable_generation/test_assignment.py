"""Unit tests for the working-set builder and the outcome engine."""

from __future__ import annotations

from dpmcore.services.variable_generation.assignment import (
    MSG_NEW_VERSION,
    MSG_REASSIGNED_NEW,
    MSG_REASSIGNED_OLD,
    MSG_UNCHANGED,
    MSG_UNCHANGED_1B,
    build_working_set,
    decide_outcomes,
)
from dpmcore.services.variable_generation.types import Aspect
from tests.unit.services.variable_generation.builders import (
    CUR,
    DRAFT,
    PREV,
    aux,
    cell,
    mv,
    mvc,
    rec,
    rel,
    snap,
    state,
    tv,
    tvc,
    var,
    vv,
)

# ------------------------------------------------------------------
# Working set
# ------------------------------------------------------------------


def test_working_set_one_record_per_module_table_cell():
    stores = {
        "module_versions": [
            mv(500, code="A"),
            mv(501, start=PREV, code="B"),
            mv(502, end=CUR),  # closed: excluded
            mv(503, start=DRAFT),  # playground: excluded
        ],
        "module_version_compositions": [
            mvc(500),
            mvc(501, table_vid=10),
            mvc(502, table_vid=10),
            mvc(503, table_vid=10),
            mvc(500, table_vid=None),
            mvc(500, table_vid=99),  # dangling table version
        ],
        "table_versions": [tv()],
        "table_version_cells": [
            tvc(10, 1000, code="c1", variable_vid=5000),
            tvc(10, 1001, code="c2", is_void=True),
            tvc(10, 1002, code="c3", is_excluded=True, variable_vid=9),
        ],
        "variables": [var(600)],
        "variable_versions": [
            vv(
                5000,
                variable_id=600,
                property_id=10,
                context_id=40,
                key_id=7,
            )
        ],
    }
    records = build_working_set(snap(**stores), rel())
    assert [(r.module_vid, r.cell_id) for r in records] == [
        (500, 1000),
        (500, 1001),
        (500, 1002),
        (501, 1000),
        (501, 1001),
        (501, 1002),
    ]
    first = records[0]
    assert first.old_variable_id == 600
    assert first.old_aspect == Aspect(7, 10, 40)
    assert not first.is_void
    # void / excluded flags
    assert records[1].is_void
    assert records[2].is_void
    # cell 1002 has a dangling VariableVID: no old coordinates
    assert records[2].old_variable_vid is None
    # tv 10 starts in CUR: new coordinates are left for aspects.py
    assert first.new_property_id is None
    # cells with no predecessor: new when the TV starts now
    assert first.is_new_cell


def test_working_set_predecessor_coordinates():
    stores = {
        "module_versions": [mv()],
        "module_version_compositions": [mvc()],
        "table_versions": [
            tv(),
            tv(8, start=PREV, end=CUR),
            tv(9, start=PREV, end=CUR),
            tv(7, start=PREV),  # still open: not a predecessor
        ],
        "cells": [cell(), cell(1001), cell(1002)],
        "table_version_cells": [
            tvc(10, 1000, code="c1"),
            tvc(9, 1000, variable_vid=5001),
            tvc(8, 1000, variable_vid=5000),  # lower TableVID loses
            tvc(7, 1000, variable_vid=5002),
            tvc(9, 1001, variable_vid=None),  # no variable
            tvc(9, 1002, variable_vid=99),  # dangling version
        ],
        "variable_versions": [
            vv(5000, variable_id=600, property_id=10),
            vv(5001, variable_id=601, property_id=11, end=CUR),
            vv(5002, variable_id=602, property_id=12),
        ],
    }
    records = build_working_set(snap(**stores), rel())
    record = records[0]
    # highest predecessor TableVID (9) wins the tie
    assert record.old_variable_vid == 5001
    assert record.vv_old_end == CUR
    assert not record.is_new_cell


def test_working_set_predecessor_requires_cell_row():
    stores = {
        "module_versions": [mv()],
        "module_version_compositions": [mvc()],
        "table_versions": [tv(), tv(9, start=PREV, end=CUR)],
        "table_version_cells": [
            tvc(10, 1000, code="c1"),
            tvc(9, 1000, variable_vid=5000),
        ],
        "variable_versions": [vv(5000, variable_id=600)],
    }
    records = build_working_set(snap(**stores), rel())
    # no Cell row: the SQL join fails, coordinates stay empty ...
    assert records[0].old_variable_vid is None
    # ... but isNewCell has no Cell join and still sees the history
    assert not records[0].is_new_cell


def test_working_set_continuity_overrides_predecessor():
    stores = {
        "module_versions": [mv()],
        "module_version_compositions": [mvc()],
        "table_versions": [
            tv(),
            tv(9, start=PREV, end=CUR),
            tv(5, start=PREV),
        ],
        "cells": [cell(), cell(1000), cell(500)],
        "table_version_cells": [
            tvc(10, 1000, code="c1"),
            tvc(9, 1000, variable_vid=5000),
            tvc(5, 500, variable_vid=5002),
        ],
        "aux_cell_mappings": [aux(10, 1000, 5, 500)],
        "variable_versions": [
            vv(5000, variable_id=600, property_id=10),
            vv(5002, variable_id=602, property_id=12),
        ],
    }
    records = build_working_set(snap(**stores), rel())
    record = records[0]
    assert record.old_variable_vid == 5002
    assert record.old_property_id == 12
    assert not record.is_new_cell


def test_working_set_continuity_ignores_incomplete_mappings():
    base = {
        "module_versions": [mv()],
        "module_version_compositions": [mvc()],
        "table_versions": [tv(), tv(5, start=PREV)],
        "cells": [cell(), cell(500)],
        "table_version_cells": [
            tvc(10, 1000, code="c1"),
            tvc(5, 500, variable_vid=5002),
        ],
        "variable_versions": [vv(5002, variable_id=602)],
    }
    cases = [
        [aux(10, 1000, None, 500)],
        [aux(10, 1000, 5, None)],
        [aux(10, 1000, 5, 501)],  # no such old TVC
    ]
    for mappings in cases:
        stores = dict(base)
        stores["aux_cell_mappings"] = mappings
        records = build_working_set(snap(**stores), rel())
        assert records[0].old_variable_vid is None, mappings
        # only complete mappings with an old variable seed isNewCell
        assert records[0].is_new_cell, mappings
    # old table version row missing (the TVC alone still seeds
    # isNewCell — the SQL subquery never joins TableVersion)
    stores = dict(base)
    stores["table_version_cells"] = [
        tvc(10, 1000, code="c1"),
        tvc(99, 500, variable_vid=5002),
    ]
    stores["aux_cell_mappings"] = [aux(10, 1000, 99, 500)]
    records = build_working_set(snap(**stores), rel())
    assert records[0].old_variable_vid is None
    assert not records[0].is_new_cell
    # dangling version / no variable on the old cell
    for old_tvc in (
        tvc(5, 500, variable_vid=99),
        tvc(5, 500, variable_vid=None),
    ):
        stores = dict(base)
        stores["table_version_cells"] = [
            tvc(10, 1000, code="c1"),
            old_tvc,
        ]
        stores["aux_cell_mappings"] = [aux(10, 1000, 5, 500)]
        records = build_working_set(snap(**stores), rel())
        assert records[0].old_variable_vid is None
    # old cell without a Cell row
    stores = dict(base)
    stores["cells"] = [cell()]
    stores["aux_cell_mappings"] = [aux(10, 1000, 5, 500)]
    records = build_working_set(snap(**stores), rel())
    assert records[0].old_variable_vid is None
    assert not records[0].is_new_cell  # isNewCell has no Cell join


def test_working_set_old_table_version_copies_coordinates():
    stores = {
        "module_versions": [mv()],
        "module_version_compositions": [mvc()],
        "table_versions": [tv(start=PREV)],
        "table_version_cells": [
            tvc(10, 1000, code="c1", variable_vid=5000)
        ],
        "variable_versions": [
            vv(
                5000,
                variable_id=600,
                property_id=10,
                context_id=40,
                key_id=7,
            )
        ],
    }
    records = build_working_set(snap(**stores), rel())
    record = records[0]
    assert record.new_property_id == 10
    assert record.new_context_id == 40
    assert record.new_key_id == 7
    assert record.old_signature == record.new_signature
    assert not record.is_new_cell


# ------------------------------------------------------------------
# Outcome engine, block by block
# ------------------------------------------------------------------


def _unchanged_record(**overrides):
    defaults = {
        "old_variable_id": 600,
        "old_variable_vid": 5000,
        "old_property_id": 10,
        "new_property_id": 10,
    }
    defaults.update(overrides)
    return rec(**defaults)


def test_block_unchanged_variants():
    same = _unchanged_record()
    old_module = _unchanged_record(
        module_vid=501, mv_start=PREV, tv_start=PREV
    )
    old_tv = _unchanged_record(tv_start=PREV, cell_id=1001)
    expired_old_tv = _unchanged_record(
        tv_start=PREV, cell_id=1002, vv_old_end=PREV
    )
    records = [same, old_module, old_tv, expired_old_tv]
    warnings = decide_outcomes(records, snap(), rel(), state())
    assert warnings == []
    assert (same.outcome_id, same.outcome_vid) == ("OLD", "OLD")
    assert same.new_variable_ref == 600
    assert same.new_vvid_ref == 5000
    assert same.report_msg == MSG_UNCHANGED
    assert old_module.report_msg == "OLD ModuleVersion: "
    assert old_tv.report_msg == "NEW ModuleVersion & OLD TableVersion "
    # expired old VV on an *old* TV still passes block 1
    assert expired_old_tv.outcome_vid == "OLD"


def test_block_unchanged_skips_void_and_expired_current():
    void = _unchanged_record(is_void=True)
    expired = _unchanged_record(vv_old_end=PREV, cell_id=1001)
    decide_outcomes([void], snap(), rel(), state())
    assert void.outcome_id is None
    # expired current-release cell falls through block 1 into 2.1
    stores = {
        "variables": [var(600)],
        "variable_versions": [
            vv(5000, variable_id=600, property_id=10, end=PREV)
        ],
    }
    warnings = decide_outcomes(
        [expired], snap(**stores), rel(), state()
    )
    assert (expired.outcome_id, expired.outcome_vid) == ("OLD", "NEW")
    # ... which is exactly the 5_5 warning situation
    assert [w.rule_id for w in warnings] == ["5_5"]
    assert expired.report_msg == warnings[0].message


def test_block_1b_reuses_active_version_of_same_variable():
    changed = rec(
        old_variable_id=600,
        old_variable_vid=5000,
        old_property_id=10,
        new_property_id=11,
    )
    resolved = rec(
        cell_id=1001,
        old_variable_id=600,
        old_variable_vid=5001,
        old_property_id=11,
        new_property_id=11,
    )
    # a second resolver with a *lower* active VVID: the highest wins
    resolved_low = rec(
        cell_id=1002,
        old_variable_id=600,
        old_variable_vid=4999,
        old_property_id=11,
        new_property_id=11,
    )
    stores = {
        "variables": [var(600)],
        "variable_versions": [
            vv(4999, variable_id=600, property_id=11),
            vv(5000, variable_id=600, property_id=10),
            vv(5001, variable_id=600, property_id=11),
        ],
    }
    warnings = decide_outcomes(
        [changed, resolved, resolved_low],
        snap(**stores),
        rel(),
        state(),
    )
    assert warnings == []
    assert (changed.outcome_id, changed.outcome_vid) == ("OLD", "OLD")
    assert changed.new_vvid_ref == 5001
    assert changed.report_msg == MSG_UNCHANGED_1B


def test_block_1b_requires_active_existing_version():
    changed = rec(
        old_variable_id=600,
        old_variable_vid=5000,
        old_property_id=10,
        new_property_id=11,
    )
    resolved = rec(
        cell_id=1001,
        old_variable_id=600,
        old_variable_vid=5001,
        old_property_id=11,
        new_property_id=11,
    )
    # the resolved version is itself expired -> no 1b reuse; the
    # cell then proposes a NEW_VERSION through block 2.1
    stores = {
        "variables": [var(600)],
        "variable_versions": [
            vv(5000, variable_id=600, property_id=10),
            vv(5001, variable_id=600, property_id=11, end=PREV),
        ],
    }
    decide_outcomes([changed, resolved], snap(**stores), rel(), state())
    assert (changed.outcome_id, changed.outcome_vid) == ("OLD", "NEW")


def test_block_1b_ignores_other_variables_and_void_peers():
    # a *new* cell: block 2.1 does not apply, so a failed 1b lookup
    # sends it to the reassignment step
    changed = rec(
        is_new_cell=True,
        old_variable_id=600,
        old_variable_vid=5000,
        old_property_id=10,
        new_property_id=11,
        new_context_id=40,
    )
    peers = [
        # other variable
        rec(
            cell_id=1001,
            old_variable_id=601,
            old_variable_vid=5100,
            old_property_id=11,
            old_context_id=40,
            new_property_id=11,
            new_context_id=40,
        ),
        # same variable but void
        rec(
            cell_id=1002,
            is_void=True,
            old_variable_id=600,
            old_variable_vid=5001,
            old_property_id=11,
            new_property_id=11,
            new_context_id=40,
        ),
        # same variable, different aspect
        rec(
            cell_id=1003,
            old_variable_id=600,
            old_variable_vid=5001,
            old_property_id=11,
            old_context_id=41,
            new_property_id=11,
            new_context_id=41,
        ),
    ]
    stores = {
        "variables": [var(600), var(601)],
        "variable_versions": [
            vv(5000, variable_id=600, property_id=10),
            vv(5001, variable_id=600, property_id=11, context_id=41),
            vv(5100, variable_id=601, property_id=11, context_id=40),
        ],
    }
    decide_outcomes(
        [changed, *peers], snap(**stores), rel(), state()
    )
    # not resolved by 1b; reassigned to variable 601's version
    assert changed.outcome_id == "OTHER OLD"
    assert changed.new_vvid_ref == 5100
    assert changed.report_msg == MSG_REASSIGNED_NEW


def test_block_2_1_new_version_on_old_variable():
    record = rec(
        old_variable_id=600,
        old_variable_vid=5000,
        old_property_id=10,
        old_key_id=7,
        new_property_id=11,
        new_key_id=7,
    )
    stores = {
        "variables": [var(600)],
        "variable_versions": [
            vv(5000, variable_id=600, property_id=10, key_id=7),
            # a second active old version is superseded too; the
            # highest vid is recorded
            vv(5001, variable_id=600, property_id=10, key_id=7),
        ],
    }
    gen = state()
    decide_outcomes([record], snap(**stores), rel(), gen)
    assert (record.outcome_id, record.outcome_vid) == ("OLD", "NEW")
    assert record.new_variable_ref == 600
    assert record.new_vvid_ref == "vv:1"
    assert record.report_msg == MSG_NEW_VERSION
    version = gen.new_version_versions[0]
    assert version.variable_ref == 600
    assert version.aspect == Aspect(7, 11, None)
    assert version.supersedes_vid == 5001


def test_block_2_1_not_applied_when_variable_already_updated():
    record = rec(
        old_variable_id=600,
        old_variable_vid=5000,
        old_property_id=10,
        new_property_id=11,
    )
    # variable 600 already has a version starting in CUR
    stores = {
        "variables": [var(600)],
        "variable_versions": [
            vv(5000, variable_id=600, property_id=10, end=CUR),
            vv(5002, variable_id=600, property_id=12, start=CUR),
        ],
    }
    gen = state()
    decide_outcomes([record], snap(**stores), rel(), gen)
    assert gen.new_version_versions == []
    # falls through to a brand-new variable
    assert (record.outcome_id, record.outcome_vid) == ("NEW", "NEW")


def test_block_2_1_requires_same_key_and_datatype():
    key_changed = rec(
        old_variable_id=600,
        old_variable_vid=5000,
        old_property_id=10,
        old_key_id=7,
        new_property_id=11,
        new_key_id=8,
    )
    dtype_changed = rec(
        cell_id=1001,
        old_variable_id=600,
        old_variable_vid=5000,
        old_property_id=10,
        new_property_id=11,
        is_new_property_datatype=True,
    )
    new_cell = rec(
        cell_id=1002,
        is_new_cell=True,
        old_variable_id=600,
        new_property_id=11,
    )
    no_variable = rec(cell_id=1003, new_property_id=11)
    gen = state()
    decide_outcomes(
        [key_changed, dtype_changed, new_cell, no_variable],
        snap(variables=[var(600)]),
        rel(),
        gen,
    )
    assert gen.new_version_versions == []
    for record in (key_changed, dtype_changed, new_cell, no_variable):
        assert record.outcome_id == "NEW"


def test_reassignment_prefers_most_recent_release():
    record = rec(new_property_id=10)
    stores = {
        "variables": [var(700), var(701), var(702, type_="key")],
        "variable_versions": [
            # older release
            vv(7000, variable_id=700, property_id=10, start=PREV),
            # current release, two candidates: highest vid wins
            vv(7010, variable_id=701, property_id=10, start=CUR),
            vv(7011, variable_id=701, property_id=10, start=CUR),
            # matching but non-fact: in the date pool only
            vv(7020, variable_id=702, property_id=10, start=CUR),
            # not matching the aspect
            vv(7030, variable_id=701, property_id=11, start=CUR),
            # expired
            vv(7040, variable_id=700, property_id=10, end=PREV),
            # dangling variable
            vv(7050, variable_id=None, property_id=10, start=CUR),
        ],
    }
    gen = state()
    decide_outcomes([record], snap(**stores), rel(), gen)
    assert record.new_vvid_ref == 7011
    assert record.outcome_id == "OTHER NEW"  # 701 has no old version
    assert record.outcome_vid == "OTHER NEW"  # starts in CUR
    assert record.report_msg == MSG_REASSIGNED_OLD


def test_reassignment_old_variable_and_old_version():
    record = rec(is_new_cell=True, new_property_id=10)
    stores = {
        "variables": [var(700)],
        "variable_versions": [
            vv(7000, variable_id=700, property_id=10, start=PREV),
        ],
    }
    gen = state()
    decide_outcomes([record], snap(**stores), rel(), gen)
    assert record.outcome_id == "OTHER OLD"
    assert record.outcome_vid == "OTHER OLD"
    assert record.report_msg == MSG_REASSIGNED_NEW


def test_reassignment_uses_block_2_1_proposals():
    # cell A creates a NEW_VERSION on variable 600; cell B (a new
    # cell with the same aspect) is reassigned to that proposal.
    version_maker = rec(
        old_variable_id=600,
        old_variable_vid=5000,
        old_property_id=10,
        new_property_id=11,
    )
    follower = rec(cell_id=1001, is_new_cell=True, new_property_id=11)
    stores = {
        "variables": [var(600)],
        "variable_versions": [
            vv(5000, variable_id=600, property_id=10)
        ],
    }
    gen = state()
    decide_outcomes(
        [version_maker, follower], snap(**stores), rel(), gen
    )
    assert follower.new_vvid_ref == "vv:1"
    assert follower.outcome_id == "OTHER OLD"
    assert follower.outcome_vid == "OTHER NEW"


def test_reassignment_requires_release_dates():
    record = rec(new_property_id=10)
    stores = {
        "variables": [var(700), var(701)],
        "variable_versions": [
            # no release date at all
            vv(7000, variable_id=700, property_id=10, start=99),
            # no start release
            vv(7010, variable_id=701, property_id=10, start=None),
        ],
    }
    gen = state()
    decide_outcomes([record], snap(**stores), rel(), gen)
    # nothing datable: the cell becomes a new variable instead
    assert record.outcome_id == "NEW"


def test_reassignment_skips_non_fact_max_date_candidates():
    record = rec(new_property_id=10)
    stores = {
        "variables": [var(700), var(702, type_="key")],
        "variable_versions": [
            # fact, but older date
            vv(7000, variable_id=700, property_id=10, start=PREV),
            # newest date is non-fact: no eligible candidate on the
            # max date -> no reassignment at all
            vv(7020, variable_id=702, property_id=10, start=CUR),
        ],
    }
    gen = state()
    decide_outcomes([record], snap(**stores), rel(), gen)
    assert record.outcome_id == "NEW"


def test_new_variable_per_distinct_aspect():
    first = rec(is_new_cell=True, new_property_id=10)
    twin = rec(
        cell_id=1001, is_new_cell=True, new_property_id=10
    )
    other = rec(
        cell_id=1002,
        old_variable_id=600,
        old_variable_vid=5000,
        old_property_id=9,
        new_property_id=11,
        is_new_property_datatype=True,
    )
    void = rec(cell_id=1003, is_void=True, new_property_id=10)
    # a cell that lost its property entirely: the SQL never assigns
    # it (its aspect is excluded from #new_Aspects)
    no_property = rec(
        cell_id=1004,
        old_variable_id=603,
        old_variable_vid=5300,
        old_property_id=9,
    )
    records = [first, twin, other, void, no_property]
    gen = state()
    warnings = decide_outcomes(
        records, snap(variables=[var(600)]), rel(), gen
    )
    assert warnings == []
    # ordered by property: aspect _10_ then _11_
    assert [v.temp_id for v in gen.fact_variables] == [
        "var:1",
        "var:2",
    ]
    assert gen.fact_variables[0].aspect == Aspect(None, 10, None)
    assert first.new_variable_ref == "var:1"
    assert twin.new_variable_ref == "var:1"
    assert twin.new_vvid_ref == first.new_vvid_ref == "vv:1"
    assert first.report_msg.endswith("New Cell")
    assert other.new_variable_ref == "var:2"
    assert other.report_msg.endswith("has a new created variable")
    assert void.outcome_id is None
    assert no_property.outcome_id is None


def test_case_message_null_starts_fall_to_else():
    record = _unchanged_record(mv_start=None, tv_start=None)
    decide_outcomes([record], snap(), rel(), state())
    # NULL comparisons are UNKNOWN in SQL: CASE falls through to ELSE
    assert record.report_msg == MSG_UNCHANGED
