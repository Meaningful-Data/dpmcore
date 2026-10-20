"""Unit tests for DataDictionaryService.resolve_cell_variables (#436).

The cell frame comes from a stubbed ``ViewDatapointsQuery.get_table_data``
so the matching rules are exercised without a DPM database: missing axis
codes, grey cells, unknown cells, input order and the scope arguments.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from dpmcore.dpm_xl.model_queries import ViewDatapointsQuery
from dpmcore.services.data_dictionary import DataDictionaryService

pytestmark = pytest.mark.unit

_RELEASE_ID = 7

# (row, column, sheet, variable_id) per table, as get_table_data returns
# them: missing axes are NaN, grey cells have a NaN variable_id.
_TABLES = {
    "C_22.00": [
        ("0100", "0020", None, 1001.0),
        ("0110", "0020", None, 1002.0),
        ("0120", "0020", None, np.nan),
    ],
    "C_67.00.a": [
        ("0010", "0060", "0010", 2001.0),
        ("0010", "0060", "0020", 2002.0),
    ],
    # Open rows: the cells have no row code.
    "C_66.01.a": [
        (None, "0010", None, 3001.0),
    ],
}


@pytest.fixture
def table_data_calls(monkeypatch):
    calls = []

    def get_table_data(cls, session, table, *args, release_id=None, **kw):
        calls.append((table, release_id))
        rows = _TABLES.get(table, [])
        return pd.DataFrame(
            rows,
            columns=["row_code", "column_code", "sheet_code", "variable_id"],
        )

    monkeypatch.setattr(
        ViewDatapointsQuery, "get_table_data", classmethod(get_table_data)
    )
    return calls


@pytest.fixture
def service():
    return DataDictionaryService(MagicMock())


def test_resolves_cells_in_input_order(service, table_data_calls):
    result = service.resolve_cell_variables(
        [
            {
                "table": "C_67.00.a",
                "row": "0010",
                "column": "0060",
                "sheet": "0020",
            },
            {"table": "C_22.00", "row": "0100", "column": "0020"},
            {
                "table": "C_22.00",
                "row": "0110",
                "column": "0020",
                "sheet": None,
            },
        ],
        release_id=_RELEASE_ID,
    )

    assert [r["variable_id"] for r in result] == [2002, 1001, 1002]
    assert all(r["error"] is None for r in result)
    assert result[0] == {
        "table": "C_67.00.a",
        "row": "0010",
        "column": "0060",
        "sheet": "0020",
        "variable_id": 2002,
        "error": None,
    }


def test_reads_each_table_once_at_the_release(service, table_data_calls):
    service.resolve_cell_variables(
        [
            {"table": "C_22.00", "row": "0100", "column": "0020"},
            {"table": "C_22.00", "row": "0110", "column": "0020"},
        ],
        release_id=_RELEASE_ID,
    )

    assert table_data_calls == [("C_22.00", _RELEASE_ID)]


def test_empty_coordinate_matches_open_axis(service, table_data_calls):
    result = service.resolve_cell_variables(
        [
            {"table": "C_66.01.a", "column": "0010"},
            {"table": "C_66.01.a", "row": "", "column": "0010"},
        ],
        release_id=_RELEASE_ID,
    )

    assert [r["variable_id"] for r in result] == [3001, 3001]
    assert result[1]["row"] is None


def test_grey_cell(service, table_data_calls):
    (result,) = service.resolve_cell_variables(
        [{"table": "C_22.00", "row": "0120", "column": "0020"}],
        release_id=_RELEASE_ID,
    )

    assert result["variable_id"] is None
    assert result["error"] == "grey_cell"


@pytest.mark.parametrize(
    "cell",
    [
        # Unknown row.
        {"table": "C_22.00", "row": "9999", "column": "0020"},
        # Sheet missing on a table that has sheets.
        {"table": "C_67.00.a", "row": "0010", "column": "0060"},
        # Unknown table.
        {"table": "X_00.00", "row": "0010", "column": "0010"},
    ],
)
def test_cell_not_found(service, table_data_calls, cell):
    (result,) = service.resolve_cell_variables([cell], release_id=_RELEASE_ID)

    assert result["variable_id"] is None
    assert result["error"] == "cell_not_found"


def test_cell_without_table_is_rejected(service, table_data_calls):
    with pytest.raises(ValueError, match="without a table"):
        service.resolve_cell_variables(
            [{"row": "0010", "column": "0010"}], release_id=_RELEASE_ID
        )


def test_scope_is_required(service, table_data_calls):
    with pytest.raises(ValueError, match="Specify a module"):
        service.resolve_cell_variables(
            [{"table": "C_22.00", "row": "0100", "column": "0020"}]
        )


def test_module_code_needs_module_version(service, table_data_calls):
    with pytest.raises(ValueError, match="together"):
        service.resolve_cell_variables([], module_code="COREP_OF")


@pytest.mark.parametrize(
    "release", [{"release_id": _RELEASE_ID}, {"release_code": "4.2"}]
)
def test_module_and_release_are_exclusive(service, table_data_calls, release):
    with pytest.raises(ValueError, match="not both"):
        service.resolve_cell_variables(
            [], module_code="COREP_OF", module_version="4.0.0", **release
        )


def test_module_version_uses_script_release_resolution(
    service, table_data_calls, monkeypatch
):
    from dpmcore.services.ast_generator import ASTGeneratorService

    seen = []

    def _resolve_release(self, module_code, module_version, release):
        seen.append((module_code, module_version, release))
        return MagicMock(), MagicMock(release_id=_RELEASE_ID)

    monkeypatch.setattr(
        ASTGeneratorService, "_resolve_release", _resolve_release
    )

    (result,) = service.resolve_cell_variables(
        [{"table": "C_22.00", "row": "0100", "column": "0020"}],
        module_code="COREP_OF",
        module_version="4.0.0",
    )

    assert seen == [("COREP_OF", "4.0.0", None)]
    assert table_data_calls == [("C_22.00", _RELEASE_ID)]
    assert result["variable_id"] == 1001


@pytest.mark.parametrize(
    "variable_ids",
    [(np.nan, 4001.0), (4001.0, np.nan)],
    ids=["grey-first", "variable-first"],
)
def test_cell_with_variable_wins_over_grey_duplicate(
    service, monkeypatch, variable_ids
):
    """The same cell grey in one table version keeps the variable."""

    def get_table_data(cls, session, table, *args, **kwargs):
        return pd.DataFrame(
            [("0010", "0010", None, v) for v in variable_ids],
            columns=["row_code", "column_code", "sheet_code", "variable_id"],
        )

    monkeypatch.setattr(
        ViewDatapointsQuery, "get_table_data", classmethod(get_table_data)
    )

    (result,) = service.resolve_cell_variables(
        [{"table": "T_01.00", "row": "0010", "column": "0010"}],
        release_id=_RELEASE_ID,
    )

    assert result["variable_id"] == 4001
    assert result["error"] is None


def test_codes_are_stripped(service, table_data_calls):
    (result,) = service.resolve_cell_variables(
        [
            {
                "table": " C_22.00 ",
                "row": " 0100",
                "column": "0020 ",
                "sheet": "  ",
            }
        ],
        release_id=_RELEASE_ID,
    )

    assert result["table"] == "C_22.00"
    assert (result["row"], result["column"], result["sheet"]) == (
        "0100",
        "0020",
        None,
    )
    assert result["variable_id"] == 1001
