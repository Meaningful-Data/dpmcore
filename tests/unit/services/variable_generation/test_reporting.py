"""Unit tests for the report assembly."""

from __future__ import annotations

from dpmcore.services.variable_generation.reporting import (
    build_cell_assignments,
    build_summary,
    outcome_of,
)
from dpmcore.services.variable_generation.types import CellOutcome
from tests.unit.services.variable_generation.builders import rec


def test_outcome_mapping():
    assert outcome_of(rec(is_void=True)) == CellOutcome.NOT_REPORTABLE
    assert outcome_of(rec()) is None
    assert outcome_of(rec(outcome_id="OLD")) is None
    assert (
        outcome_of(rec(outcome_id="NEW", outcome_vid="NEW"))
        == CellOutcome.NEW_VARIABLE
    )
    assert (
        outcome_of(rec(outcome_id="OTHER OLD", outcome_vid="OTHER NEW"))
        == CellOutcome.REASSIGNED
    )
    assert (
        outcome_of(rec(outcome_id="OLD", outcome_vid="NEW"))
        == CellOutcome.NEW_VERSION
    )
    assert (
        outcome_of(rec(outcome_id="OLD", outcome_vid="OLD"))
        == CellOutcome.UNCHANGED
    )


def test_cell_assignments_collapse_module_rows():
    records = [
        rec(
            outcome_id="OLD",
            outcome_vid="OLD",
            old_variable_id=600,
            old_variable_vid=5000,
            new_variable_ref=600,
            new_vvid_ref=5000,
            report_msg="same",
        ),
        rec(module_vid=501, report_msg="OLD ModuleVersion: "),
        rec(module_vid=502, report_msg="same"),
        rec(cell_id=999, table_vid=11, table_code="T2"),
    ]
    assignments = build_cell_assignments(records)
    assert [(a.table_vid, a.cell_id) for a in assignments] == [
        (10, 1000),
        (11, 999),
    ]
    merged = assignments[1]
    assert merged.notes == ()
    merged = assignments[0]
    assert merged.outcome == CellOutcome.UNCHANGED
    assert merged.old_variable_id == 600
    assert merged.new_variable_ref == 600
    assert merged.notes == ("OLD ModuleVersion: ", "same")
    assert merged.old_aspect is not None
    assert merged.new_aspect is not None


def test_summary_applies_detail_filter():
    records = [
        # unchanged: excluded (OutcomeVID = OLD)
        rec(outcome_id="OLD", outcome_vid="OLD", report_msg="u"),
        # unassigned: excluded (NULL <> 'OLD' is UNKNOWN)
        rec(cell_id=1001),
        # void: excluded
        rec(
            cell_id=1002,
            is_void=True,
            outcome_id="NEW",
            outcome_vid="NEW",
        ),
        # the same (tv, cell) through two modules counts once
        rec(
            cell_id=1003,
            cell_code="a",
            outcome_id="NEW",
            outcome_vid="NEW",
            report_msg="created",
        ),
        rec(
            cell_id=1003,
            cell_code="a",
            module_vid=501,
            outcome_id="NEW",
            outcome_vid="NEW",
            report_msg="created",
        ),
        rec(
            cell_id=1004,
            cell_code="b",
            outcome_id="NEW",
            outcome_vid="NEW",
            report_msg="created",
        ),
        rec(
            cell_id=1005,
            cell_code=None,
            outcome_id="OLD",
            outcome_vid="NEW",
            report_msg=None,
        ),
    ]
    rows = [r.to_dict() for r in build_summary(records)]
    assert rows == [
        {
            "outcome": "new_variable",
            "message": "created",
            "count": 2,
            "min_cell_code": "a",
            "max_cell_code": "b",
        },
        {
            "outcome": "new_version",
            "message": "",
            "count": 1,
            "min_cell_code": None,
            "max_cell_code": None,
        },
    ]
