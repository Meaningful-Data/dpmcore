"""Integration tests for DataDictionaryService.resolve_cell_variables (#436).

Every cell of a real table must resolve to the variable the internal
``ViewDatapointsQuery.get_table_data`` gives it, both when scoped by a
release and when scoped by a module version (resolved to its release
the way ``ASTGeneratorService.script`` does).

Tests skip cleanly when ``tests/fixtures/test_data.db`` is absent.
"""

from __future__ import annotations

import pandas as pd
import pytest

from dpmcore.dpm_xl.model_queries import ViewDatapointsQuery
from dpmcore.services.data_dictionary import DataDictionaryService

_RELEASE_CODE = "4.2.1"
_TABLE = "F_01.01"


@pytest.fixture
def service(fixture_session):
    return DataDictionaryService(fixture_session)


def _release_id(session, code):
    from dpmcore.orm.infrastructure import Release

    row = session.query(Release).filter(Release.code == code).first()
    if row is None:
        pytest.skip(f"Fixture DB has no release with code {code!r}")
    return row.release_id


def _code(value):
    return None if pd.isna(value) else str(value)


def _expected_cells(session, table, release_id):
    data = ViewDatapointsQuery.get_table_data(
        session, table, release_id=release_id
    )
    data = data[data["variable_id"].notna()]
    assert not data.empty, f"expected cells with variables in {table}"
    cells = [
        {
            "table": table,
            "row": _code(row),
            "column": _code(column),
            "sheet": _code(sheet),
        }
        for row, column, sheet in data[
            ["row_code", "column_code", "sheet_code"]
        ].itertuples(index=False)
    ]
    return cells, [int(v) for v in data["variable_id"]]


def test_release_scope_matches_table_data(service, fixture_session):
    release_id = _release_id(fixture_session, _RELEASE_CODE)
    cells, expected = _expected_cells(fixture_session, _TABLE, release_id)

    result = service.resolve_cell_variables(cells, release_code=_RELEASE_CODE)

    assert [r["variable_id"] for r in result] == expected
    assert all(r["error"] is None for r in result)


def test_module_scope_matches_script_release(service, fixture_session):
    from dpmcore.orm.packaging import ModuleVersion, ModuleVersionComposition
    from dpmcore.orm.rendering import TableVersion
    from dpmcore.services.ast_generator import ASTGeneratorService

    mv = (
        fixture_session.query(ModuleVersion)
        .join(
            ModuleVersionComposition,
            ModuleVersionComposition.module_vid == ModuleVersion.module_vid,
        )
        .join(
            TableVersion,
            TableVersion.table_vid == ModuleVersionComposition.table_vid,
        )
        .filter(TableVersion.code == _TABLE)
        .order_by(ModuleVersion.module_vid.desc())
        .first()
    )
    if mv is None:
        pytest.skip(f"Fixture DB has no module version with {_TABLE}")

    _, release_row = ASTGeneratorService(fixture_session)._resolve_release(
        mv.code, mv.version_number, None
    )
    cells, expected = _expected_cells(
        fixture_session, _TABLE, release_row.release_id
    )

    result = service.resolve_cell_variables(
        cells, module_code=mv.code, module_version=mv.version_number
    )

    assert [r["variable_id"] for r in result] == expected


def test_unknown_cell(service, fixture_session):
    _release_id(fixture_session, _RELEASE_CODE)

    (result,) = service.resolve_cell_variables(
        [{"table": _TABLE, "row": "9999", "column": "9999"}],
        release_code=_RELEASE_CODE,
    )

    assert result["variable_id"] is None
    assert result["error"] == "cell_not_found"
