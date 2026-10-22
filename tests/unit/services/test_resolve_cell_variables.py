"""Unit tests for DataDictionaryService.resolve_cell_variables (#436).

The cell frame comes from a stubbed ``ViewDatapointsQuery.get_table_data``
so the matching rules are exercised without a DPM database: missing axis
codes, grey cells, unknown cells, input order and the scope arguments,
including the module-version table filter.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from dpmcore.dpm_xl.model_queries import ViewDatapointsQuery
from dpmcore.orm.base import Base
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


_MODULE_VID = 494
_GHOST_VID = 495


@pytest.fixture
def module_scope(monkeypatch):
    """Stub the module-version resolution shared with script()."""
    from dpmcore.services.ast_generator import ASTGeneratorService

    calls = {"release": [], "module_vids": []}

    def _resolve_release(self, module_code, module_version, release):
        calls["release"].append((module_code, module_version, release))
        return (
            MagicMock(module_vid=_MODULE_VID),
            MagicMock(release_id=_RELEASE_ID),
        )

    def _release_ghost_fallbacks(self, session, release_id):
        return {_MODULE_VID: [_GHOST_VID]}

    def _module_table_codes(self, module_vids):
        calls["module_vids"].append(module_vids)
        # C_67.00 is an abstract table: part of the module, without cells.
        return {"C_22.00", "C_67.00.a", "C_67.00"}

    monkeypatch.setattr(
        ASTGeneratorService, "_resolve_release", _resolve_release
    )
    monkeypatch.setattr(
        ASTGeneratorService,
        "_release_ghost_fallbacks",
        _release_ghost_fallbacks,
    )
    monkeypatch.setattr(
        DataDictionaryService, "_module_table_codes", _module_table_codes
    )
    return calls


def test_module_version_uses_script_release_resolution(
    service, table_data_calls, module_scope
):
    (result,) = service.resolve_cell_variables(
        [{"table": "C_22.00", "row": "0100", "column": "0020"}],
        module_code="COREP_OF",
        module_version="4.0.0",
    )

    assert module_scope["release"] == [("COREP_OF", "4.0.0", None)]
    # The module version's tables include the ghosts it stands in for.
    assert module_scope["module_vids"] == [[_MODULE_VID, _GHOST_VID]]
    assert table_data_calls == [("C_22.00", _RELEASE_ID)]
    assert result["variable_id"] == 1001


def test_table_not_in_module(service, table_data_calls, module_scope):
    result = service.resolve_cell_variables(
        [
            {"table": "C_66.01.a", "column": "0010"},
            {"table": "C_22.00", "row": "0100", "column": "0020"},
        ],
        module_code="COREP_OF",
        module_version="4.0.0",
    )

    assert [(r["variable_id"], r["error"]) for r in result] == [
        (None, "table_not_in_module"),
        (1001, None),
    ]
    # A table outside the module is not read at all.
    assert table_data_calls == [("C_22.00", _RELEASE_ID)]


def test_abstract_table_of_module_has_no_cells(
    service, table_data_calls, module_scope
):
    (result,) = service.resolve_cell_variables(
        [{"table": "C_67.00", "row": "0010", "column": "0060"}],
        module_code="COREP_OF",
        module_version="4.0.0",
    )

    assert result["variable_id"] is None
    assert result["error"] == "cell_not_found"


def test_release_scope_resolves_any_table(service, table_data_calls):
    (result,) = service.resolve_cell_variables(
        [{"table": "C_66.01.a", "column": "0010"}], release_id=_RELEASE_ID
    )

    assert result["variable_id"] == 3001


@pytest.fixture
def memory_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_module_table_codes(memory_session):
    from dpmcore.orm.packaging import ModuleVersionComposition
    from dpmcore.orm.rendering import TableVersion

    memory_session.add_all(
        [
            TableVersion(table_vid=1, table_id=1, code="T_01.00"),
            TableVersion(table_vid=2, table_id=2, code="T_02.00"),
            TableVersion(table_vid=3, table_id=3, code="T_03.00"),
            TableVersion(table_vid=4, table_id=1, code="T_01.00"),
            ModuleVersionComposition(module_vid=10, table_id=1, table_vid=1),
            ModuleVersionComposition(module_vid=10, table_id=2, table_vid=2),
            ModuleVersionComposition(module_vid=11, table_id=1, table_vid=4),
            ModuleVersionComposition(module_vid=12, table_id=3, table_vid=3),
        ]
    )
    memory_session.flush()

    service = DataDictionaryService(memory_session)

    assert service._module_table_codes([10]) == {"T_01.00", "T_02.00"}
    assert service._module_table_codes([10, 11]) == {"T_01.00", "T_02.00"}
    assert service._module_table_codes([12]) == {"T_03.00"}
    assert service._module_table_codes([99]) == set()


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
