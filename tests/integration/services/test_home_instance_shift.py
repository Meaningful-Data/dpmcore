"""Integration regression: ``time_shift`` over a home-module table (#325).

A validation that shifts a table of the module the script is generated for
needs another instance of *that* module. It is therefore not
intra-instance, and the shifted instance must be declared under the
module's own URI with the shift's reference period — before #325 the
validation was declared intra with no dependency at all, and the computed
reference period never reached the output because it was only ever read
off a dependency module's tables.

Both real forms are covered: the shifted table named inline, and the
shifted table inherited from a ``with`` clause.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from dpmcore.services.ast_generator import ASTGeneratorService

_MODULE_CODE = "FINREP9"
_MODULE_VERSION = "3.3.0"

# Both validations shift a FINREP9 table by one year:
# v1313_m names it inline — ``{tF_46.00, ...} = time_shift({tF_01.03,
# ...}, A, 1, refPeriod)`` — and v1226_m inherits ``tF_46.00`` from its
# ``with`` clause, so the shifted operand only resolves to a table after
# semantic enrichment.
_INLINE_CODE = "v1313_m"
_WITH_CLAUSE_CODE = "v1226_m"
_EXPECTED_REF_PERIOD = "T-1A"

# FINREP9 3.3.0's own D0 precedes the shifted date, so the predecessor
# version (3.1.0) substitutes for it.
_EXPECTED_VERSION_WINDOWS = [
    {
        "URI": (
            "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/finrep/"
            "its-005-2020/2022-06-01/mod/finrep9"
        ),
        "module_version": "3.1.0",
        "from_reference_date": "2025-03-31",
        "to_reference_date": "2026-03-30",
    }
]


def _latest_expression(session, code: str) -> str:
    operation_id = session.execute(
        text("SELECT OperationID FROM Operation WHERE Code = :c"),
        {"c": code},
    ).scalar()
    assert operation_id is not None, f"{code} not in fixture DB"
    expression = session.execute(
        text(
            "SELECT Expression FROM OperationVersion "
            "WHERE OperationID = :o ORDER BY OperationVID DESC LIMIT 1"
        ),
        {"o": operation_id},
    ).scalar()
    assert expression is not None, f"{code} has no expression in fixture DB"
    return expression


def _script(session, code: str) -> tuple[str, dict]:
    expression = _latest_expression(session, code)
    assert "time_shift" in expression, f"{code} must shift an operand"
    result = ASTGeneratorService(session).script(
        expressions=[(expression, code)],
        module_code=_MODULE_CODE,
        module_version=_MODULE_VERSION,
    )
    assert result["success"], result["error"]
    assert not result["failed_operations"], result["failed_operations"]
    namespace = next(iter(result["enriched_ast"]))
    return namespace, result["enriched_ast"][namespace]


@pytest.mark.parametrize("code", [_INLINE_CODE, _WITH_CLAUSE_CODE])
def test_home_shift_is_declared_as_a_cross_instance_dependency(
    fixture_session, code
):
    namespace, module = _script(fixture_session, code)
    info = module["dependency_information"]

    assert info["intra_instance_validations"] == []
    assert len(info["cross_instance_dependencies"]) == 1
    dependency = info["cross_instance_dependencies"][0]
    assert dependency["affected_operations"] == [code]
    assert dependency["modules"] == [
        {
            "URI": namespace,
            "ref_period": _EXPECTED_REF_PERIOD,
            "module_version": _MODULE_VERSION,
            "version_windows": _EXPECTED_VERSION_WINDOWS,
        }
    ]


@pytest.mark.parametrize("code", [_INLINE_CODE, _WITH_CLAUSE_CODE])
def test_home_module_is_not_declared_as_a_dependency_module(
    fixture_session, code
):
    """The home module's tables and variables are already at the top level."""
    namespace, module = _script(fixture_session, code)
    assert namespace not in module["dependency_modules"]
