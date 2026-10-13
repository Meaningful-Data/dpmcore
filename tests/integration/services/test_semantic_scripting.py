"""``is_scripting`` wiring: a broken forward wouldn't show up in the unit
tests, which stub ``_validate_resolved`` and never build a real
``OperandsChecking``.
"""

import pytest

from dpmcore.services.dpm_xl import DpmXlService
from dpmcore.services.semantic import SemanticService

_BATCH = "t1 := 1; t2 := {ot1} + 1;"


def test_semantic_service_allows_scripting_operation_ref(fixture_session):
    result = SemanticService(fixture_session).validate(
        _BATCH, is_scripting=True
    )
    assert result.is_valid, result.error_message


def test_semantic_service_rejects_operation_ref_without_scripting(
    fixture_session,
):
    result = SemanticService(fixture_session).validate(_BATCH)
    assert not result.is_valid
    assert result.error_code == "6-2"
    assert result.error_message == (
        "References to operations are not allowed in single expressions, "
        "trying it with t1."
    )


def test_is_valid_forwards_is_scripting(fixture_session):
    svc = SemanticService(fixture_session)
    assert svc.is_valid(_BATCH, is_scripting=True)
    assert not svc.is_valid(_BATCH)


def test_dpm_xl_service_allows_scripting_operation_ref(fixture_session):
    result = DpmXlService(fixture_session).validate_semantic(
        _BATCH, is_scripting=True
    )
    assert result["is_valid"], result["error_message"]


def test_dpm_xl_service_rejects_operation_ref_without_scripting(
    fixture_session,
):
    result = DpmXlService(fixture_session).validate_semantic(_BATCH)
    assert not result["is_valid"]
    assert result["error_code"] == "6-2"
    assert result["error_message"] == (
        "References to operations are not allowed in single expressions, "
        "trying it with t1."
    )


def test_self_reference_is_still_rejected_despite_scripting(fixture_session):
    # OperandsChecking alone would accept this self-reference; it's
    # InputAnalyzer's dependency-order check (1-9) that actually rejects it.
    result = SemanticService(fixture_session).validate(
        "t1 := {ot1} + 1;", is_scripting=True
    )
    assert not result.is_valid
    assert result.error_code == "1-9"
    assert result.error_message == "Previous operation: t1 was not found"


def test_is_scripting_does_not_leak_into_the_precondition(fixture_session):
    # is_scripting must not extend to the precondition gate.
    result = SemanticService(fixture_session).validate(
        _BATCH, precondition_expression="{ot1}", is_scripting=True
    )
    assert not result.precondition.is_valid
    assert result.precondition.error_code == "6-2"
    assert result.precondition.error_message == (
        "References to operations are not allowed in single expressions, "
        "trying it with t1."
    )


def test_a_forward_operation_reference_is_validated_in_dependency_order(
    fixture_session,
):
    # The consumer comes first: the script is sorted before it is checked.
    result = SemanticService(fixture_session).validate(
        "t2 := {ot1} + 1; t1 := 1;", is_scripting=True
    )
    assert result.is_valid, result.error_message


def test_an_unknown_operation_is_still_reported_as_1_8(fixture_session):
    # Sorting must not hide a reference to an operation the script lacks.
    result = SemanticService(fixture_session).validate(
        "t1 := {oZ} + 1;", is_scripting=True
    )
    assert not result.is_valid
    assert result.error_code == "1-8"
    assert result.error_message == (
        "The following operations ['Z'] were not found."
    )


def test_a_cycle_between_operations_is_reported_as_6_4(fixture_session):
    result = SemanticService(fixture_session).validate(
        "t1 := {ot2} + 1; t2 := {ot1} + 1;", is_scripting=True
    )
    assert not result.is_valid
    assert result.error_code == "6-4"
    assert result.error_message == (
        "Circular reference between operations t1 and t2. Try removing or "
        "changing these references."
    )


@pytest.mark.parametrize("selection", ["r0020-0030", "(r0020, r0030)", "r*"])
def test_a_cycle_through_a_cell_inside_a_selection_is_reported_as_6_4(
    fixture_session, selection
):
    # r0030 is written by the second statement and only read inside the
    # first one's selection: the DAG has to match it cell by cell.
    result = SemanticService(fixture_session).validate(
        f"{{tF_01.01, r0010, c0010}} <- sum({{tF_01.01, {selection}, c0010}});"
        " {tF_01.01, r0030, c0010} <- {tF_01.01, r0010, c0010};",
        release_code="4.2.1",
        is_scripting=True,
    )
    assert not result.is_valid
    assert result.error_code == "6-4"
    assert result.error_message == (
        "Circular reference between operations {F_01.01, r0010, c0010} and "
        "{F_01.01, r0030, c0010}. Try removing or changing these references."
    )


def test_overwriting_is_still_reported_as_6_1(fixture_session):
    # Reported by the analyzer, not by the DAG's own overwrite check.
    result = SemanticService(fixture_session).validate(
        "{tF_01.01, r0010-0020, c0010} <- 1; {tF_01.01, r0020, c0010} <- 2;",
        release_code="4.2.1",
        is_scripting=True,
    )
    assert not result.is_valid
    assert result.error_code == "6-1"
    assert result.error_message == (
        "Overwriting a variable is not allowed, trying it with "
        "F_01.01, r0020, c0010."
    )


def test_a_temporary_assigned_twice_is_reported_as_6_1(fixture_session):
    result = SemanticService(fixture_session).validate(
        "t1 := 1; t1 := 2; t2 := {ot1} + 1;", is_scripting=True
    )
    assert not result.is_valid
    assert result.error_code == "6-1"
    assert result.error_message == (
        "Overwriting a variable is not allowed, trying it with t1."
    )


def test_without_scripting_the_statements_are_not_reordered(fixture_session):
    result = SemanticService(fixture_session).validate(
        "t2 := {ot1} + 1; t1 := 1;"
    )
    assert not result.is_valid
    assert result.error_code == "6-2"
    assert result.error_message == (
        "References to operations are not allowed in single expressions, "
        "trying it with t1."
    )
