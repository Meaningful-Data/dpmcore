"""``is_scripting`` wiring: a broken forward wouldn't show up in the unit
tests, which stub ``_validate_resolved`` and never build a real
``OperandsChecking``.
"""

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


def test_self_reference_is_still_rejected_despite_scripting(fixture_session):
    # OperandsChecking alone would accept this self-reference; it's
    # InputAnalyzer's dependency-order check (1-9) that actually rejects it.
    result = SemanticService(fixture_session).validate(
        "t1 := {ot1} + 1;", is_scripting=True
    )
    assert not result.is_valid
    assert result.error_code == "1-9"


def test_is_scripting_does_not_leak_into_the_precondition(fixture_session):
    # is_scripting must not extend to the precondition gate.
    result = SemanticService(fixture_session).validate(
        _BATCH, precondition_expression="{ot1}", is_scripting=True
    )
    assert not result.precondition.is_valid
    assert result.precondition.error_code == "6-2"
