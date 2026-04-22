"""Tests for ExplorerService.

Ported from the py_dpm ExplorerQueryAPI / ExplorerQuery suite.

py_dpm exposed many additional methods (``get_properties_using_item``,
``audit_table``, ``get_module_url``, ``get_variable_from_cell_address``,
``get_variables_by_codes``) — these are NOT part of
``dpmcore.services.explorer.ExplorerService`` and their coverage moves
out of scope until they are reintroduced. See git history for the full
list of removed scenarios.

Ported scenarios: ``search_table``, ``get_variable_by_code``.
"""

from dpmcore.orm.rendering import TableVersion
from dpmcore.orm.variables import Variable, VariableVersion
from dpmcore.services.explorer import ExplorerService


def test_search_table_returns_matching_table_versions(memory_session):
    """search_table performs an ILIKE match on TableVersion.code."""
    session = memory_session
    session.add_all(
        [
            TableVersion(
                table_vid=1, code="TABLE_A", name="Table A", description="Desc"
            ),
            TableVersion(
                table_vid=2,
                code="OTHER",
                name="Other Table",
                description="Desc",
            ),
        ]
    )
    session.commit()

    service = ExplorerService(session)
    results = service.search_table("TABLE")

    assert len(results) == 1
    assert results[0]["code"] == "TABLE_A"


def test_search_table_release_id_filter(memory_session):
    """release_id is applied against TableVersion start/end release."""
    session = memory_session
    session.add_all(
        [
            TableVersion(
                table_vid=1,
                code="TABLE_A",
                start_release_id=1,
                end_release_id=2,
            ),
            TableVersion(
                table_vid=2,
                code="TABLE_A2",
                start_release_id=2,
                end_release_id=None,
            ),
        ]
    )
    session.commit()

    service = ExplorerService(session)

    res_r1 = service.search_table("TABLE", release_id=1)
    codes_r1 = {r["code"] for r in res_r1}
    # TABLE_A (start=1, end=2 -> 2>1 valid), TABLE_A2 (start=2 > 1 -> excluded).
    assert codes_r1 == {"TABLE_A"}

    res_r2 = service.search_table("TABLE", release_id=2)
    codes_r2 = {r["code"] for r in res_r2}
    # TABLE_A ends at 2 (2>2 False, excluded); TABLE_A2 kept.
    assert codes_r2 == {"TABLE_A2"}


def test_get_variable_by_code_active_version(memory_session):
    """get_variable_by_code returns the first matching VariableVersion."""
    session = memory_session

    session.add(Variable(variable_id=1001))
    session.add(Variable(variable_id=2001))
    session.add(Variable(variable_id=3001))

    session.add_all(
        [
            VariableVersion(
                variable_vid=1001,
                variable_id=1001,
                code="C_01.00",
                name="Filing indicator for C_01.00 (v4.1)",
                start_release_id=1,
                end_release_id=2,
            ),
            VariableVersion(
                variable_vid=2001,
                variable_id=2001,
                code="C_01.00",
                name="Filing indicator for C_01.00 (v4.2)",
                start_release_id=2,
                end_release_id=None,
            ),
            VariableVersion(
                variable_vid=3001,
                variable_id=3001,
                code="C_47.00",
                name="Filing indicator for C_47.00",
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )
    session.commit()

    service = ExplorerService(session)

    # Without release_id, returns the first matching row (ORM insertion order).
    result = service.get_variable_by_code("C_01.00")
    assert result is not None
    assert result["code"] == "C_01.00"

    # With release_id=1, release filter picks the v4.1 row.
    result_r1 = service.get_variable_by_code("C_01.00", release_id=1)
    assert result_r1 is not None
    assert result_r1["variable_vid"] == 1001
    assert "v4.1" in result_r1["name"]

    # release_id=2 picks the v4.2 row.
    result_r2 = service.get_variable_by_code("C_01.00", release_id=2)
    assert result_r2 is not None
    assert result_r2["variable_vid"] == 2001
    assert "v4.2" in result_r2["name"]


def test_get_variable_by_code_not_found(memory_session):
    service = ExplorerService(memory_session)
    assert service.get_variable_by_code("NONEXISTENT") is None
