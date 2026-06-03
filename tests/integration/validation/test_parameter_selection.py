"""Integration tests for Parameter Selection surfacing.

Parameters are not DPM entities, so a pure-parameter expression validates
against an empty schema (no release/table data required). These tests exercise
the service surface end to end: ``SemanticService`` populating
``SemanticResult.parameters`` / ``oc_parameters`` and the ``DpmXlService``
``get_parameters`` convenience. The scope-wide check (a referenced parameter's
declared type must agree with co-scoped operations already in the database) is
exercised against the real fixture release by persisting a parameterised
operation in-session (rolled back on teardown).
"""

from sqlalchemy import func

from dpmcore.dpm_xl.utils.filters import resolve_release_id
from dpmcore.orm.operations import (
    OperationScope,
    OperationScopeComposition,
    OperationVersion,
)
from dpmcore.orm.packaging import ModuleVersion
from dpmcore.services.dpm_xl import DpmXlService
from dpmcore.services.parameter_scope import ParameterScopeIndex
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


def _persist_parameter_op(session, *, expression, module_vid):
    """Insert a parameterised operation scoped to ``module_vid`` (in-session).

    Only ``flush`` is used, so the rows are visible to same-session queries but
    rolled back when the fixture session is closed.
    """
    op_vid = (
        session.query(func.max(OperationVersion.operation_vid)).scalar() or 0
    ) + 1
    scope_id = (
        session.query(func.max(OperationScope.operation_scope_id)).scalar()
        or 0
    ) + 1
    session.add(OperationVersion(operation_vid=op_vid, expression=expression))
    session.add(
        OperationScope(operation_scope_id=scope_id, operation_vid=op_vid)
    )
    session.add(
        OperationScopeComposition(
            operation_scope_id=scope_id, module_vid=module_vid
        )
    )
    session.flush()


def test_scope_wide_parameter_type_conflict(fixture_session):
    """A clash with a co-scoped persisted parameter is rejected (3-8)."""
    release_id = resolve_release_id(fixture_session, release_code="4.2.1")
    module_vids = ParameterScopeIndex(fixture_session).module_vids_for(
        ["C_09.02"], release_id
    )
    assert module_vids, "fixture must expose C_09.02 at release 4.2.1"
    mvid = next(iter(module_vids))

    # Persisted: p_scope_probe declared `number`, scoped to C_09.02's module.
    _persist_parameter_op(
        fixture_session,
        expression="{p_scope_probe, number}",
        module_vid=mvid,
    )

    svc = SemanticService(fixture_session)
    # New expression declares the same code as `integer` over the same module.
    clash = svc.validate(
        "{tC_09.02, r0030, c0080} > {p_scope_probe, integer}",
        release_code="4.2.1",
    )
    assert clash.is_valid is False
    assert clash.error_code == "3-8"

    # Same declared type -> no conflict (index is reused from the first call).
    agree = svc.validate(
        "{tC_09.02, r0030, c0080} > {p_scope_probe, number}",
        release_code="4.2.1",
    )
    assert agree.is_valid, agree.error_message

    # Opt-out skips the DB scope lookup entirely.
    skipped = svc.validate(
        "{tC_09.02, r0030, c0080} > {p_scope_probe, integer}",
        release_code="4.2.1",
        check_scope=False,
    )
    assert skipped.is_valid, skipped.error_message


def test_scope_wide_check_ignores_disjoint_module(fixture_session):
    """Same code + different type but a non-overlapping scope is allowed."""
    release_id = resolve_release_id(fixture_session, release_code="4.2.1")
    probe_mvids = ParameterScopeIndex(fixture_session).module_vids_for(
        ["C_09.02"], release_id
    )
    assert probe_mvids
    # Persist the clashing declaration against a real module the new expression
    # does NOT touch (FK-safe, and genuinely disjoint from C_09.02's modules).
    all_mvids = {
        vid for (vid,) in fixture_session.query(ModuleVersion.module_vid).all()
    }
    disjoint_mvid = next(iter(all_mvids - set(probe_mvids)))
    _persist_parameter_op(
        fixture_session,
        expression="{p_scope_probe, string}",
        module_vid=disjoint_mvid,
    )

    svc = SemanticService(fixture_session)
    result = svc.validate(
        "{tC_09.02, r0030, c0080} > {p_scope_probe, integer}",
        release_code="4.2.1",
    )
    # No shared module version -> no co-execution -> no conflict.
    assert result.is_valid, result.error_message
