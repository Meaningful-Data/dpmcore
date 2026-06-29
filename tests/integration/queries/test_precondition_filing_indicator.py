"""Filing-indicator precondition resolution (model_queries Fix 1).

The DPM 2.0 Refit source stores the filing-indicator variable type as the
single token ``"filingindicator"``. ``ModuleVersionQuery`` previously
filtered on the literal ``"Filing Indicator"`` (spaced/capitalised),
which never matched, so preconditions could never be resolved. These
tests pin the normalised match used by ``_is_filing_indicator``.
"""

import datetime

import pytest

from dpmcore.dpm_xl.model_queries import (
    ModuleVersionQuery,
    VariableVersionQuery,
)
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
    """
    session.add_all(
        [
            # Release-axis filtering resolves sort order from Release.code,
            # so the target release must exist as a real row.
            Release(release_id=1, code="3.4", date=datetime.date(2022, 12, 1)),
            Variable(variable_id=1, type="filingindicator"),
            Variable(variable_id=2, type="Filing Indicator"),
            Variable(variable_id=3, type="fact"),
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
