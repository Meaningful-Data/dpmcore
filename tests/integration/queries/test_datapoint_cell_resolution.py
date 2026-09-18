"""How a cell's axes and module scoping are resolved (issue #361).

Validating real expressions was dominated by three queries that each
joined nine tables and then collapsed the result with ``DISTINCT``: the
header of every cell was resolved by an ``OR``-ed outer join no optimiser
could turn into a seek, and the module versions carrying the table
repeated every cell once per version. Both are now resolved away from the
cells -- the headers of a table version are read once and applied in
pandas, module membership once as a list of table versions -- so the cell
query is a plain scan of one table version's cells.

These tests pin what that rewrite must keep: which ``HeaderVersion``
answers for an axis, the fallback when a table version pins none, and the
module-membership rule. They also pin the cost contract itself, since
nothing in the results would otherwise show that a whole validation run
now reads a table's cells once.

Seed model: one table version in two modules, a row and two columns
pinned by ``TableVersionHeader`` rows, and one row header with no such
row so it has to fall back.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import event

from dpmcore.dpm_xl.model_queries import ViewDatapointsQuery
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import (
    Cell,
    Header,
    HeaderVersion,
    Table,
    TableVersion,
    TableVersionCell,
    TableVersionHeader,
)
from dpmcore.orm.variables import VariableVersion

OLD = 8001
NEW = 8002

TABLE_VID = 300
# Headers: the row and both columns are pinned, ROW_LOOSE is not.
ROW_PINNED = 1
COL_FIRST = 2
ROW_LOOSE = 3
COL_SECOND = 4


def _seed(session, code):
    """Seed one table version of ``code`` and everything it needs.

    Args:
        session: SQLAlchemy session.
        code: Table version code; distinct per test, since the query
            caches are keyed by engine URL and every in-memory session
            shares one.
    """
    session.add_all(
        [
            Release(release_id=OLD, code="8.0", date=date(2024, 1, 1)),
            Release(release_id=NEW, code="8.1", date=date(2025, 1, 1)),
            Framework(framework_id=1, code="FW"),
            Module(module_id=1, framework_id=1),
            Module(module_id=2, framework_id=1),
        ]
    )
    # Two modules carry the same table version: the cells used to come
    # back once per module version, only for DISTINCT to collapse them.
    session.add_all(
        ModuleVersion(
            module_vid=vid,
            module_id=vid - 19,
            code=f"M{vid}",
            version_number="1.0.0",
            start_release_id=OLD,
            end_release_id=None,
        )
        for vid in (20, 21)
    )
    session.add_all(
        [
            Table(table_id=1),
            TableVersion(
                table_vid=TABLE_VID,
                table_id=1,
                code=code,
                start_release_id=OLD,
                end_release_id=None,
            ),
            ModuleVersionComposition(
                module_vid=20, table_vid=TABLE_VID, table_id=1
            ),
            ModuleVersionComposition(
                module_vid=21, table_vid=TABLE_VID, table_id=1
            ),
        ]
    )
    _seed_headers(session)
    _seed_cells(session, code)
    session.commit()


def _seed_headers(session):
    """The four headers, their versions and the three pinned rows."""
    session.add_all(
        [
            Header(header_id=ROW_PINNED, table_id=1, direction="Y"),
            Header(header_id=COL_FIRST, table_id=1, direction="X"),
            Header(header_id=ROW_LOOSE, table_id=1, direction="Y"),
            Header(header_id=COL_SECOND, table_id=1, direction="X"),
            # The pinned row header has a second version, which no cell
            # may resolve to: the TableVersionHeader row names the other.
            HeaderVersion(header_vid=10, header_id=ROW_PINNED, code="r0010"),
            HeaderVersion(header_vid=11, header_id=ROW_PINNED, code="r0010x"),
            HeaderVersion(header_vid=20, header_id=COL_FIRST, code="c0010"),
            HeaderVersion(header_vid=40, header_id=COL_SECOND, code="c0020"),
            # ROW_LOOSE is pinned by nothing, so both of its versions
            # answer -- the row multiplication the outer join produced.
            HeaderVersion(header_vid=30, header_id=ROW_LOOSE, code="r0020"),
            HeaderVersion(header_vid=31, header_id=ROW_LOOSE, code="r0020b"),
            TableVersionHeader(
                table_vid=TABLE_VID,
                header_id=ROW_PINNED,
                header_vid=10,
                order=1,
            ),
            TableVersionHeader(
                table_vid=TABLE_VID,
                header_id=COL_FIRST,
                header_vid=20,
                order=1,
            ),
            TableVersionHeader(
                table_vid=TABLE_VID,
                header_id=COL_SECOND,
                header_vid=40,
                order=2,
            ),
        ]
    )


def _seed_cells(session, code):
    """Three cells: a plain one, a grey one and one on the loose row."""
    session.add_all(
        [
            VariableVersion(variable_vid=500, variable_id=700, code="V700"),
            VariableVersion(variable_vid=501, variable_id=701, code="V701"),
            Cell(
                cell_id=901, table_id=1, row_id=ROW_PINNED, column_id=COL_FIRST
            ),
            Cell(
                cell_id=902,
                table_id=1,
                row_id=ROW_PINNED,
                column_id=COL_SECOND,
            ),
            Cell(
                cell_id=903, table_id=1, row_id=ROW_LOOSE, column_id=COL_FIRST
            ),
        ]
    )
    session.add_all(
        TableVersionCell(
            table_vid=TABLE_VID,
            cell_id=cell_id,
            cell_code=cell_code,
            variable_vid=variable_vid,
            is_nullable=True,
            is_void=False,
            is_excluded=False,
        )
        for cell_id, cell_code, variable_vid in (
            (901, f"{{{code}, r0010, c0010}}", 500),
            # A grey cell: part of the rendering, carrying no variable.
            (902, f"{{{code}, r0010, c0020}}", None),
            (903, f"{{{code}, r0020, c0010}}", 501),
        )
    )


@pytest.fixture
def statements(memory_session):
    """Record every statement the session's engine executes."""
    recorded: list[str] = []
    engine = memory_session.get_bind().engine

    @event.listens_for(engine, "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):
        recorded.append(statement)

    yield recorded
    event.remove(engine, "before_cursor_execute", _record)


def test_the_pinned_header_version_answers(memory_session):
    """A cell's axis code is the version its table version pins."""
    _seed(memory_session, "T_CELLS_PINNED")

    data = ViewDatapointsQuery.get_table_data(
        memory_session, "T_CELLS_PINNED", release_id=NEW
    )

    pinned = data[data["cell_code"].str.contains("r0010, c0010")]
    assert pinned["row_code"].tolist() == ["r0010"]
    assert pinned["row_order"].tolist() == [1]
    assert pinned["column_code"].tolist() == ["c0010"]


def test_an_unpinned_header_falls_back_to_every_version(memory_session):
    """With no ``TableVersionHeader`` row, each version of it answers."""
    _seed(memory_session, "T_CELLS_LOOSE")

    data = ViewDatapointsQuery.get_filtered_datapoints(
        memory_session,
        "T_CELLS_LOOSE",
        {"rows": None, "cols": None, "sheets": None},
        release_id=NEW,
    )

    loose = data[data["cell_code"].str.endswith("r0020, c0010}")]
    assert sorted(loose["row_code"]) == ["r0020", "r0020b"]
    # The display order lives on the missing row, so it has none.
    assert loose["row_order"].isna().all()


def test_module_versions_sharing_a_window_yield_one_row(memory_session):
    """Two module versions, one release window: one row per cell.

    The frame reports the window of the module version the cells were
    read through, so the module versions carrying a table version are
    what multiplies its cells -- and two that agree on the window are
    indistinguishable, so the de-duplication folds them back together.
    """
    _seed(memory_session, "T_CELLS_ONE_ROW")

    data = ViewDatapointsQuery.get_filtered_datapoints(
        memory_session,
        "T_CELLS_ONE_ROW",
        {"rows": None, "cols": None, "sheets": None},
        release_id=NEW,
    )

    cell = data[data["cell_code"] == "{T_CELLS_ONE_ROW, r0010, c0010}"]
    assert len(cell) == 1
    assert cell["start_release"].tolist() == [OLD]
    assert cell["end_release"].isna().all()


def test_a_cell_is_reported_once_per_module_version_window(memory_session):
    """Module versions with different windows each report the cell."""
    _seed(memory_session, "T_CELLS_TWO_ROWS")
    # Close the second module version earlier, so the two windows differ.
    memory_session.query(ModuleVersion).filter(
        ModuleVersion.module_vid == 21
    ).update({"end_release_id": NEW})
    memory_session.commit()

    data = ViewDatapointsQuery.get_filtered_datapoints(
        memory_session,
        "T_CELLS_TWO_ROWS",
        {"rows": None, "cols": None, "sheets": None},
        release_id=OLD,
    )

    cell = data[data["cell_code"] == "{T_CELLS_TWO_ROWS, r0010, c0010}"]
    assert len(cell) == 2
    assert sorted(cell["end_release"].fillna(-1)) == [-1, NEW]


def test_a_table_version_no_module_carries_has_no_cells(memory_session):
    """Module membership still scopes which table versions are read."""
    _seed(memory_session, "T_CELLS_ORPHAN")
    memory_session.query(ModuleVersionComposition).delete()
    memory_session.commit()

    data = ViewDatapointsQuery.get_table_data(
        memory_session, "T_CELLS_ORPHAN", release_id=NEW
    )

    assert data.empty


def test_axis_orders_read_the_pinned_rows(memory_session):
    """Each axis is ordered only when every code on it carries an order."""
    _seed(memory_session, "T_CELLS_ORDERS")

    orders = ViewDatapointsQuery.get_axis_orders(
        memory_session, "T_CELLS_ORDERS", release_id=NEW
    )

    assert orders["cols"] == {"c0010": 1, "c0020": 2}
    # The loose row header carries no order, so the whole axis falls back
    # to string comparison rather than mixing the two.
    assert orders["rows"] is None


def test_ids_keep_the_dtype_reading_them_from_sql_gave(memory_session):
    """A selection with no grey cell still hands back integer ids.

    The cells are read once for the whole table version, where the grey
    cell in another column makes the column a float; a caller putting
    these ids in a dependency list must still get ``701``, not ``701.0``.
    """
    _seed(memory_session, "T_CELLS_DTYPE")

    data = ViewDatapointsQuery.get_table_data(
        memory_session, "T_CELLS_DTYPE", cols=["c0010"], release_id=NEW
    )

    assert data["variable_id"].dtype == "int64"
    assert sorted(data["variable_id"]) == [700, 701]


def test_one_cell_query_serves_every_selection(memory_session, statements):
    """The cost contract of issue #361: one read of a table's cells.

    Whatever a validation run asks of one table -- the display order of
    its axes, one cell selection, then another -- the cells behind the
    answers are read once.
    """
    _seed(memory_session, "T_CELLS_COST")
    statements.clear()

    ViewDatapointsQuery.get_axis_orders(
        memory_session, "T_CELLS_COST", release_id=NEW
    )
    ViewDatapointsQuery.get_table_data(
        memory_session, "T_CELLS_COST", rows=["r0010"], release_id=NEW
    )
    ViewDatapointsQuery.get_table_data(
        memory_session, "T_CELLS_COST", cols=["c0020"], release_id=NEW
    )
    ViewDatapointsQuery.get_filtered_datapoints(
        memory_session,
        "T_CELLS_COST",
        {"rows": ["r0010"], "cols": None, "sheets": None},
        release_id=NEW,
    )

    cell_reads = [s for s in statements if "TableVersionCell" in s]
    assert len(cell_reads) == 1
    # And it is a scan of one table version's cells, not a join over the
    # headers and the module versions carrying it.
    assert "HeaderVersion" not in cell_reads[0]
    assert "ModuleVersionComposition" not in cell_reads[0]
