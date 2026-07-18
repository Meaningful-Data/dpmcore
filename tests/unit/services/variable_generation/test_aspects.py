"""Unit tests for the new-coordinate computation."""

from __future__ import annotations

from dpmcore.services.variable_generation.aspects import (
    compute_new_coordinates,
)
from tests.unit.services.variable_generation.builders import (
    PREV,
    ccomp,
    cell,
    ctx,
    hv,
    prop,
    rec,
    rel,
    snap,
    state,
    tv,
)


def _run(records, gen=None, **stores):
    gen = gen or state()
    compute_new_coordinates(snap(**stores), rel(), records, gen)
    return gen


def test_old_table_versions_keep_their_coordinates():
    record = rec(
        tv_start=PREV,
        old_property_id=10,
        old_context_id=40,
        old_key_id=7,
        new_property_id=10,
        new_context_id=40,
        new_key_id=7,
    )
    _run([record])
    assert record.new_property_id == 10
    assert not record.is_new_key
    assert not record.is_new_property_datatype


def test_property_is_max_across_axes_and_table_version():
    records = [rec()]
    _run(
        records,
        table_versions=[tv(property_id=12)],
        cells=[cell(column_id=1, row_id=2)],
        headers=[],
        header_versions=[
            hv(100, header_id=1, property_id=10, start=PREV),
            hv(200, header_id=2, property_id=11, start=PREV),
            # property not in the Property store does not count
            hv(201, header_id=2, property_id=99, start=PREV),
        ],
        properties=[prop(10), prop(11), prop(12)],
    )
    assert records[0].new_property_id == 12


def test_axis_with_only_expired_versions_blocks_the_cell():
    records = [rec()]
    _run(
        records,
        table_versions=[tv(property_id=12, context_id=40)],
        cells=[cell(column_id=1)],
        header_versions=[
            hv(100, header_id=1, property_id=10, start=PREV, end=PREV)
        ],
        properties=[prop(10), prop(12)],
        context_compositions=[ccomp(40, 11, 70)],
    )
    assert records[0].new_property_id is None
    assert records[0].new_context_id is None


def test_cell_without_any_property_stays_none():
    records = [rec()]
    _run(records, table_versions=[tv()], cells=[cell()])
    assert records[0].new_property_id is None


def test_missing_cell_or_table_version_yields_no_coordinates():
    records = [rec(), rec(table_vid=99, cell_id=2000)]
    _run(records, table_versions=[tv()])
    assert records[0].new_property_id is None
    assert records[1].new_property_id is None
    assert records[1].new_context_id is None


def test_context_signature_resolves_existing_context():
    records = [rec()]
    _run(
        records,
        table_versions=[tv(context_id=40)],
        cells=[cell(row_id=1)],
        header_versions=[
            hv(100, header_id=1, context_id=41, start=PREV)
        ],
        contexts=[
            # trailing whitespace still matches after trimming;
            # the higher context id wins the duplicate
            ctx(45, signature="11_70#12_71# "),
            ctx(46, signature="11_70#12_71#"),
            ctx(44, signature="11_70#12_71#"),
            ctx(47, signature=None),
        ],
        context_compositions=[
            ccomp(40, 11, 70),
            ccomp(41, 12, 71),
            # NULL items are skipped by STRING_AGG
            ccomp(41, 13, None),
        ],
    )
    assert records[0].new_context_id == 46


def test_unseen_signature_proposes_context():
    records = [
        rec(),
        rec(module_vid=501),  # same cell through another module
        rec(cell_id=2000, cell_code="c2000"),
    ]
    gen = _run(
        records,
        table_versions=[tv(context_id=40)],
        cells=[cell(), cell(2000)],
        context_compositions=[ccomp(40, 11, 70), ccomp(40, 13, None)],
    )
    assert [c.to_dict() for c in gen.cell_contexts] == [
        {
            "temp_id": "ctx:1",
            "signature": "11_70#",
            "compositions": [[11, 70]],
        }
    ]
    assert {r.new_context_id for r in records} == {"ctx:1"}


def test_fi_context_proposal_is_reused_for_cells():
    gen = state()
    from dpmcore.services.variable_generation.types import (
        ProposedContext,
    )

    gen.fi_contexts.append(
        ProposedContext("ctx:9", "11_70#", ((11, 70),))
    )
    records = [rec()]
    _run(
        records,
        gen,
        table_versions=[tv(context_id=40)],
        cells=[cell()],
        context_compositions=[ccomp(40, 11, 70)],
    )
    assert records[0].new_context_id == "ctx:9"
    assert gen.cell_contexts == []


def test_table_key_is_attached_to_current_cells():
    gen = state()
    gen.key_by_table_vid[10] = "key:1"
    records = [rec(old_key_id=None)]
    _run(records, gen, table_versions=[tv()], cells=[cell()])
    assert records[0].new_key_id == "key:1"
    assert records[0].is_new_key


def test_datatype_flags():
    records = [
        # new cell: always flagged
        rec(cell_id=1, is_new_cell=True),
        # same datatype: not flagged
        rec(cell_id=2, old_property_id=10),
        # different datatype: flagged
        rec(cell_id=3, old_property_id=11),
        # unknown old datatype: comparison is UNKNOWN, not flagged
        rec(cell_id=4, old_property_id=12),
        # old property not in the store: not flagged
        rec(cell_id=5, old_property_id=99),
        # no old property at all: not flagged
        rec(cell_id=6),
    ]
    _run(
        records,
        table_versions=[tv(property_id=10)],
        cells=[cell(cell_id=i) for i in (1, 2, 3, 4, 5, 6)],
        properties=[
            prop(10, data_type_id=1),
            prop(11, data_type_id=2),
            prop(12, data_type_id=None),
        ],
    )
    flags = {r.cell_id: r.is_new_property_datatype for r in records}
    assert flags == {
        1: True,
        2: False,
        3: True,
        4: False,
        5: False,
        6: False,
    }


def test_key_change_flag_combinations():
    cases = [
        # (old, new via key_by_table, expected)
        (None, None, False),
        (7, None, True),
        (None, 7, True),
        (7, 7, False),
        (7, 8, True),
    ]
    for old_key, new_key, expected in cases:
        gen = state()
        if new_key is not None:
            gen.key_by_table_vid[10] = new_key
        record = rec(old_key_id=old_key)
        _run([record], gen, table_versions=[tv()], cells=[cell()])
        assert record.is_new_key is expected, (old_key, new_key)
