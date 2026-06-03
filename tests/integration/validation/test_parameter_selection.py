"""Integration tests for Parameter Selection surfacing.

Parameters are not DPM entities, so a pure-parameter expression validates
against an empty schema (no release/table data required). These tests exercise
the service surface end to end: ``SemanticService`` populating
``SemanticResult.parameters`` / ``oc_parameters`` and the ``DpmXlService``
``get_parameters`` convenience.
"""

from dpmcore.services.dpm_xl import DpmXlService
from dpmcore.services.semantic import ParameterInfo, SemanticService


def test_parameters_surfaced_on_result(memory_session):
    svc = SemanticService(memory_session)
    result = svc.validate("{p_a, number} > {p_b, number, default: 0}")
    assert result.is_valid, result.error_message
    assert result.parameters == (
        ParameterInfo("a", "number", False, None),
        ParameterInfo("b", "number", False, 0),
    )
    # Also exposed on the service for downstream consumers.
    assert svc.oc_parameters == result.parameters


def test_duplicate_parameter_deduped(memory_session):
    svc = SemanticService(memory_session)
    result = svc.validate("{p_x, number} > {p_x, number}")
    assert result.is_valid, result.error_message
    assert result.parameters == (ParameterInfo("x", "number", False, None),)


def test_set_parameter_in_membership(memory_session):
    svc = SemanticService(memory_session)
    result = svc.validate("1 in {p_ccys, set-number}")
    assert result.is_valid, result.error_message
    assert result.parameters == (
        ParameterInfo("ccys", "set-number", True, None),
    )


def test_conflicting_parameter_types_in_one_expression_invalid(memory_session):
    svc = SemanticService(memory_session)
    # Same code declared as two different scalar types: caught as 3-8 before
    # structural analysis; no parameters surfaced.
    result = svc.validate("{p_x, number} > {p_x, integer}")
    assert result.is_valid is False
    assert result.error_code == "3-8"
    assert result.parameters == ()
    assert svc.oc_parameters is None


def test_invalid_expression_surfaces_no_parameters(memory_session):
    svc = SemanticService(memory_session)
    # Scalar compared against a set is invalid; parameters are not surfaced.
    result = svc.validate("{p_a, number} > {p_b, set-number}")
    assert result.is_valid is False
    assert result.parameters == ()
    assert svc.oc_parameters is None


def test_get_parameters_facade(memory_session):
    params = DpmXlService(memory_session).get_parameters(
        "{p_a, integer, default: 0} > {p_b, number}"
    )
    assert params == (
        ParameterInfo("a", "integer", False, 0),
        ParameterInfo("b", "number", False, None),
    )


def test_parameter_alongside_real_table(fixture_session):
    """A parameter referenced next to a real cell selection (release 4.2.1)."""
    svc = SemanticService(fixture_session)
    result = svc.validate(
        "{tC_09.02, r0030, c0080} > {p_threshold, number, default: 0}",
        release_code="4.2.1",
    )
    assert result.is_valid, result.error_message
    assert ParameterInfo("threshold", "number", False, 0) in result.parameters
