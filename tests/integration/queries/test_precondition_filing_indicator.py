"""Filing-indicator precondition resolution (model_queries Fix 1).

The DPM 2.0 Refit source stores the filing-indicator variable type as the
single token ``"filingindicator"``. ``ModuleVersionQuery`` previously
filtered on the literal ``"Filing Indicator"`` (spaced/capitalised),
which never matched, so preconditions could never be resolved. These
tests pin the normalised match used by ``_is_filing_indicator``.
"""

import datetime

import pytest

from dpmcore import errors
from dpmcore.dpm_xl.model_queries import (
    ModuleVersionQuery,
    VariableVersionQuery,
)
from dpmcore.dpm_xl.utils.scopes_calculator import OperationScopeService
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import ModuleParameters, ModuleVersion
from dpmcore.orm.variables import Variable, VariableVersion

pytestmark = pytest.mark.integration


def _seed(session):
    """Insert one module reporting two filing indicators.

    The two filing indicators deliberately use *different* spellings of
    the type (``"filingindicator"`` and ``"Filing Indicator"``) to prove
    the normalised comparison matches both. A third ``"fact"`` variable
    shares a code but must never be returned.

    Two more variables support the scope-filtering tests (issue #240):
    ``BM`` is a business-model attribute (a non-filing-indicator value
    condition) and ``C_99.00`` is a genuine filing indicator that no
    module hosts.
    """
    session.add_all(
        [
            # Release-axis filtering resolves sort order from Release.date,
            # so the target release must exist as a real, dated row.
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            Variable(variable_id=1, type="filingindicator"),
            Variable(variable_id=2, type="Filing Indicator"),
            Variable(variable_id=3, type="fact"),
            # Business-model attribute used in a value condition; NOT a
            # filing indicator and hosted by no module by design.
            Variable(variable_id=4, type="Business Model"),
            # A genuine filing indicator that no module reports.
            Variable(variable_id=5, type="filingindicator"),
            VariableVersion(
                variable_vid=1,
                variable_id=1,
                code="C_02.00",
                start_release_id=1,
                end_release_id=None,
            ),
            VariableVersion(
                variable_vid=2,
                variable_id=2,
                code="C_25.00",
                start_release_id=1,
                end_release_id=None,
            ),
            # Same code as a filing indicator but type "fact" -> excluded.
            VariableVersion(
                variable_vid=3,
                variable_id=3,
                code="C_02.00",
                start_release_id=1,
                end_release_id=None,
            ),
            VariableVersion(
                variable_vid=4,
                variable_id=4,
                code="BM",
                start_release_id=1,
                end_release_id=None,
            ),
            VariableVersion(
                variable_vid=5,
                variable_id=5,
                code="C_99.00",
                start_release_id=1,
                end_release_id=None,
            ),
            ModuleVersion(
                module_vid=100,
                module_id=1,
                code="COREP_OF",
                version_number="1.0",
                start_release_id=1,
                end_release_id=None,
                from_reference_date=datetime.date(2023, 6, 30),
                to_reference_date=None,
            ),
            ModuleParameters(module_vid=100, variable_vid=1),
            ModuleParameters(module_vid=100, variable_vid=2),
            ModuleParameters(module_vid=100, variable_vid=3),
        ]
    )
    session.flush()


def test_filing_indicators_resolve_for_both_spellings(memory_session):
    _seed(memory_session)

    df = ModuleVersionQuery.get_precondition_module_versions(
        memory_session,
        ["C_02.00", "C_25.00"],
        release_id=1,
    )

    # Both filing indicators resolve, regardless of type spelling.
    assert set(df["Code"]) == {"C_02.00", "C_25.00"}
    assert set(df["ModuleCode"]) == {"COREP_OF"}


def test_fact_typed_variable_is_not_a_precondition(memory_session):
    _seed(memory_session)

    df = ModuleVersionQuery.get_precondition_module_versions(
        memory_session,
        ["C_02.00"],
        release_id=1,
    )

    # Only the filing-indicator C_02.00 (variable_vid 1), never the
    # "fact" variable that shares the code (variable_vid 3).
    assert list(df["Code"]) == ["C_02.00"]
    assert df["variable_vid"].tolist() == [1]


def test_check_precondition_finds_filing_indicator(memory_session):
    _seed(memory_session)

    row = VariableVersionQuery.check_precondition(
        memory_session, "C_25.00", release_id=1
    )

    assert row is not None
    assert row.Code == "C_25.00"


# --------------------------------------------------------------------- #
# get_filing_indicator_codes — the helper backing the #240 scope fix.
# --------------------------------------------------------------------- #


def test_get_filing_indicator_codes_keeps_only_filing_indicators(
    memory_session,
):
    _seed(memory_session)

    result = ModuleVersionQuery.get_filing_indicator_codes(
        memory_session, ["C_02.00", "C_25.00", "BM"]
    )

    # Both filing indicators are returned (regardless of type spelling);
    # the business-model value-condition variable BM is excluded.
    assert result == {"C_02.00", "C_25.00"}


def test_get_filing_indicator_codes_ignores_unknown_code(memory_session):
    _seed(memory_session)

    # Neither BM (a known non-filing-indicator variable) nor a code that is
    # not a variable at all counts as a filing indicator. Per issue #240 a
    # value-condition item "need not even be a VariableVersion".
    result = ModuleVersionQuery.get_filing_indicator_codes(
        memory_session, ["BM", "DOES_NOT_EXIST"]
    )

    assert result == set()


def test_get_filing_indicator_codes_empty_input_short_circuits(
    memory_session,
):
    # Empty input returns an empty set without issuing a query.
    assert (
        ModuleVersionQuery.get_filing_indicator_codes(memory_session, [])
        == set()
    )


# --------------------------------------------------------------------- #
# calculate_operation_scope — a value condition must not fail scope calc,
# while a genuinely-missing filing indicator still raises 1-14 (#240).
# The up-front filter drops non-filing-indicator preconditions before they
# reach module resolution.
# --------------------------------------------------------------------- #


def test_value_condition_precondition_does_not_fail_scope(memory_session):
    _seed(memory_session)
    svc = OperationScopeService(session=memory_session)

    # C_02.00 (filing indicator) resolves to module COREP_OF; BM is a value
    # condition with no module version and must simply be ignored.
    scopes, _ = svc.calculate_operation_scope(
        tables_vids=[],
        precondition_items=["C_02.00", "BM"],
        release_id=1,
    )

    # The filing indicator alone drives a single-module scope; BM neither
    # raised 1-14 nor added a spurious module.
    assert len(scopes) == 1
    module_vids = {
        comp.module_vid for comp in scopes[0].operation_scope_compositions
    }
    assert module_vids == {100}


def test_only_value_condition_precondition_does_not_fail_scope(memory_session):
    _seed(memory_session)
    svc = OperationScopeService(session=memory_session)

    # A precondition made up solely of a non-filing-indicator value
    # condition is filtered to nothing, so scope calc resolves no module
    # and simply returns no scopes instead of raising 1-14.
    scopes, _ = svc.calculate_operation_scope(
        tables_vids=[],
        precondition_items=["BM"],
        release_id=1,
    )

    assert scopes == []


def test_missing_filing_indicator_still_raises_1_14(memory_session):
    _seed(memory_session)
    svc = OperationScopeService(session=memory_session)

    # C_99.00 is a genuine filing indicator that no module hosts: it survives
    # the filter and scope calculation must still fail with 1-14, while the BM
    # value condition is dropped and never reported.
    with pytest.raises(errors.SemanticError) as exc_info:
        svc.calculate_operation_scope(
            tables_vids=[],
            precondition_items=["C_99.00", "BM"],
            release_id=1,
        )

    assert exc_info.value.code == "1-14"
    assert "C_99.00" in str(exc_info.value)
    assert "BM" not in str(exc_info.value)
