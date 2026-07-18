"""Unit tests for the result types and the internal working state."""

from __future__ import annotations

import json

from dpmcore.services.variable_generation.state import (
    CellRecord,
    GenerationState,
    TempIdAllocator,
    ref_sort_key,
)
from dpmcore.services.variable_generation.types import (
    Aspect,
    CellAssignment,
    CellOutcome,
    GenerationStatus,
    GenerationSummaryRow,
    HeaderDedup,
    ProposedCompoundKey,
    ProposedContext,
    ProposedFilingIndicator,
    ProposedVariable,
    ProposedVariableVersion,
    VariableGenerationResult,
)
from tests.unit.services.variable_generation.builders import rec


def test_aspect_signature_renders_none_as_empty():
    assert Aspect(None, None, None).signature == "__"
    assert Aspect(7, 10, 40).signature == "7_10_40"
    assert Aspect("key:1", 10, None).signature == "key:1_10_"


def test_aspect_to_dict():
    assert Aspect(7, 10, None).to_dict() == {
        "key_id": 7,
        "property_id": 10,
        "context_id": None,
        "signature": "7_10_",
    }


def test_enums_are_string_valued():
    assert GenerationStatus.COMPLETED.value == "completed"
    assert (
        GenerationStatus.BLOCKED_BY_VALIDATION.value
        == "blocked_by_validation"
    )
    assert CellOutcome.NOT_REPORTABLE.value == "not_reportable"


def _version(temp_id="vv:1", variable_ref="var:1"):
    return ProposedVariableVersion(
        temp_id=temp_id,
        variable_ref=variable_ref,
        aspect=Aspect(None, 10, None),
        code="T1",
        supersedes_vid=5000,
    )


def test_proposed_variable_version_to_dict():
    assert _version().to_dict() == {
        "temp_id": "vv:1",
        "variable_ref": "var:1",
        "aspect": {
            "key_id": None,
            "property_id": 10,
            "context_id": None,
            "signature": "_10_",
        },
        "code": "T1",
        "name": None,
        "supersedes_vid": 5000,
    }


def test_proposed_variable_to_dict_with_and_without_aspect():
    version = _version()
    with_aspect = ProposedVariable(
        temp_id="var:1",
        type="fact",
        aspect=Aspect(None, 10, None),
        code=None,
        versions=(version,),
    )
    as_dict = with_aspect.to_dict()
    assert as_dict["aspect"]["signature"] == "_10_"
    assert as_dict["versions"][0]["temp_id"] == "vv:1"
    keyvar = ProposedVariable(
        temp_id="var:2",
        type="key",
        aspect=None,
        code=None,
        versions=(),
    )
    assert keyvar.to_dict()["aspect"] is None
    assert keyvar.to_dict()["versions"] == []


def test_proposed_context_and_compound_key_to_dict():
    context = ProposedContext(
        temp_id="ctx:1",
        signature="11_70#",
        compositions=((11, 70),),
    )
    assert context.to_dict() == {
        "temp_id": "ctx:1",
        "signature": "11_70#",
        "compositions": [[11, 70]],
    }
    key = ProposedCompoundKey(
        temp_id="key:1",
        signature="20#",
        member_variable_refs=(6000, "vv:1"),
    )
    assert key.to_dict()["member_variable_refs"] == [6000, "vv:1"]


def test_proposed_filing_indicator_to_dict():
    fi = ProposedFilingIndicator(
        temp_id="fi:1",
        code="T1",
        module_vids=(500,),
        item_ref="fi:1",
        item_category_signature="eba__TE:T1",
        context_ref="ctx:1",
        variable_ref="var:1",
        variable_version_ref="vv:1",
    )
    as_dict = fi.to_dict()
    assert as_dict["module_vids"] == [500]
    assert as_dict["item_category_signature"] == "eba__TE:T1"


def test_header_dedup_to_dict():
    dedup = HeaderDedup(
        old_header_vid=100, new_header_vid=101, table_vids=(10, 11)
    )
    assert dedup.to_dict() == {
        "old_header_vid": 100,
        "new_header_vid": 101,
        "table_vids": [10, 11],
    }


def test_cell_assignment_to_dict_optional_fields():
    full = CellAssignment(
        table_vid=10,
        table_code="T1",
        cell_id=1000,
        cell_code="c1",
        outcome=CellOutcome.UNCHANGED,
        old_variable_id=600,
        old_variable_vid=5000,
        new_variable_ref=600,
        new_variable_vid_ref=5000,
        old_aspect=Aspect(None, 10, None),
        new_aspect=Aspect(None, 10, None),
        notes=("msg",),
    )
    as_dict = full.to_dict()
    assert as_dict["outcome"] == "unchanged"
    assert as_dict["old_aspect"]["signature"] == "_10_"
    assert as_dict["notes"] == ["msg"]
    empty = CellAssignment(
        table_vid=10,
        table_code=None,
        cell_id=1000,
        cell_code=None,
        outcome=None,
        old_variable_id=None,
        old_variable_vid=None,
        new_variable_ref=None,
        new_variable_vid_ref=None,
        old_aspect=None,
        new_aspect=None,
    )
    as_dict = empty.to_dict()
    assert as_dict["outcome"] is None
    assert as_dict["old_aspect"] is None
    assert as_dict["new_aspect"] is None


def test_summary_row_to_dict():
    row = GenerationSummaryRow(
        outcome=CellOutcome.NEW_VARIABLE,
        message="m",
        count=2,
        min_cell_code="a",
        max_cell_code="b",
    )
    assert row.to_dict()["outcome"] == "new_variable"


def test_result_to_dict_is_json_serialisable():
    result = VariableGenerationResult(
        status=GenerationStatus.COMPLETED,
        release_id=100,
        release_code="CUR",
        validation=None,
        consistency_violations=(),
        new_variables=(),
        new_variable_versions=(_version(),),
        new_contexts=(),
        new_compound_keys=(),
        new_filing_indicators=(),
        cell_assignments=(),
        header_deduplications=(),
        summary=(),
        elapsed_ms=1.5,
    )
    as_dict = result.to_dict()
    assert as_dict["status"] == "completed"
    assert as_dict["validation"] is None
    assert as_dict["new_variable_versions"][0]["temp_id"] == "vv:1"
    json.dumps(as_dict)


# ------------------------------------------------------------------
# state
# ------------------------------------------------------------------


def test_temp_id_allocator_counts_per_prefix():
    ids = TempIdAllocator()
    assert ids.next("var") == "var:1"
    assert ids.next("var") == "var:2"
    assert ids.next("vv") == "vv:1"


def test_ref_sort_key_orders_ints_before_temp_ids():
    refs = ["vv:2", 5, "vv:10", 3]
    assert sorted(refs, key=ref_sort_key) == [3, 5, "vv:10", "vv:2"]


def test_cell_record_aspects():
    record = rec(
        old_key_id=7,
        old_property_id=10,
        old_context_id=40,
        new_property_id=11,
    )
    assert record.old_aspect == Aspect(7, 10, 40)
    assert record.old_signature == "7_10_40"
    assert record.new_aspect == Aspect(None, 11, None)
    assert record.new_signature == "_11_"
    assert isinstance(record, CellRecord)


def test_generation_state_plan_ordering():
    state = GenerationState()
    key_version = _version("vv:1", "var:1")
    fi_version = _version("vv:2", "var:2")
    fact_version = _version("vv:4", "var:3")
    state.key_variables.append(
        ProposedVariable("var:1", "key", None, None, (key_version,))
    )
    state.fi_variables.append(
        ProposedVariable(
            "var:2", "filingindicator", None, "T1", (fi_version,)
        )
    )
    state.new_version_versions.append(_version("vv:3", 600))
    state.fact_variables.append(
        ProposedVariable("var:3", "fact", None, None, (fact_version,))
    )
    state.fi_contexts.append(ProposedContext("ctx:1", "s1", ()))
    state.cell_contexts.append(ProposedContext("ctx:2", "s2", ()))
    assert [v.temp_id for v in state.all_variables()] == [
        "var:1",
        "var:2",
        "var:3",
    ]
    assert [v.temp_id for v in state.all_variable_versions()] == [
        "vv:1",
        "vv:2",
        "vv:3",
        "vv:4",
    ]
    assert [c.temp_id for c in state.all_contexts()] == [
        "ctx:1",
        "ctx:2",
    ]
