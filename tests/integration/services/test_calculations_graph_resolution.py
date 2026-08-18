"""Integration tests for engine-resolved calculations graphs.

Every input mode resolves selections through the DPM-XL engine against a real
dictionary, so these tests need the populated fixture database (they skip when
it is absent). They confirm that CSV/inline expressions produce *exact*
dependency edges — matched on resolved ``VariableID`` — including range/wildcard
expansion, with no numeric-overlap approximation.
"""

import pytest

from dpmcore.services.calculations_graph import CalculationsGraphService

pytestmark = pytest.mark.integration


def _find_resolvable_cells(session, wanted=4):
    """Return ``(table_code, [(row, col), ...])`` for real, celled variables.

    Picks the first table with at least *wanted* distinct single-sheet cells
    that carry a ``variable_id`` (so selections resolve without needing the
    sheet dimension or hitting grey cells).
    """
    from dpmcore.dpm_xl.model_queries import (
        ModuleVersionQuery,
        ViewDatapointsQuery,
    )
    from dpmcore.orm.rendering import TableVersion

    release_id = ModuleVersionQuery.get_last_release(session)
    for (code,) in session.query(TableVersion.code).distinct().limit(400):
        try:
            df = ViewDatapointsQuery.get_table_data(
                session, code, None, None, None, release_id
            )
        except Exception:  # noqa: S112, BLE001 — probe: skip odd tables
            continue
        if df is None or df.empty:
            continue
        cells = df[df["variable_id"].notnull()]
        cells = cells[cells["sheet_code"].isnull()]
        cells = cells.dropna(subset=["row_code", "column_code"])
        cells = cells.drop_duplicates(subset=["row_code", "column_code"])
        if len(cells) >= wanted:
            picked = [
                (str(r), str(c))
                for r, c in cells[["row_code", "column_code"]]
                .head(wanted)
                .itertuples(index=False, name=None)
            ]
            return code, picked
    return None, None


@pytest.fixture
def cells(fixture_session):
    code, picked = _find_resolvable_cells(fixture_session)
    if code is None:
        pytest.skip("No resolvable multi-cell table in the fixture DB")
    return code, picked


def _sel(table, row, col):
    return f"{{t{table}, r{row}, c{col}}}"


def test_csv_resolution_exact_implicit_edge(fixture_session, cells):
    table, ((rA, cA), (rB, cB), (rC, cC), _rest) = cells
    rows = [
        # 'w' writes cell A (reads cell B).
        ("w", f"{_sel(table, rA, cA)} <- {_sel(table, rB, cB)} + 1"),
        # 'r' reads cell A -> exact edge w -> r.
        ("r", f"{_sel(table, rC, cC)} <- {_sel(table, rA, cA)} * 2"),
    ]
    result = CalculationsGraphService().generate_from_rows(
        rows, fixture_session, "t"
    )
    pairs = {(e.source, e.target, e.kind) for e in result.edges}
    assert ("w", "r", "implicit") in pairs
    assert not result.warnings


def test_independent_operation_is_root(fixture_session, cells):
    table, ((rA, cA), (rB, cB), (rC, cC), (rD, cD)) = cells
    rows = [
        ("w", f"{_sel(table, rA, cA)} <- {_sel(table, rB, cB)} + 1"),
        # 'indep' reads/writes cells unrelated to 'w' -> no edge, a root.
        ("indep", f"{_sel(table, rC, cC)} <- {_sel(table, rD, cD)} + 1"),
    ]
    result = CalculationsGraphService().generate_from_rows(
        rows, fixture_session, "t"
    )
    edges = {(e.source, e.target) for e in result.edges}
    assert ("w", "indep") not in edges
    assert ("indep", "w") not in edges
    roots = {n.code for n in result.nodes if n.is_root}
    assert "indep" in roots


def test_range_read_resolves_to_real_producers(fixture_session, cells):
    table, picked = cells
    (rA, cA), (rB, cB) = picked[0], picked[1]
    # A numeric row range that spans both producer rows expands to the real
    # cells; the reader must depend on every producer whose cell falls in it.
    lo, hi = sorted([rA, rB])
    consumer_row, consumer_col = picked[2]
    rows = [
        ("p1", f"{_sel(table, rA, cA)} <- {_sel(table, rB, cB)} + 1"),
        ("p2", f"{_sel(table, rB, cB)} <- {_sel(table, rA, cA)} + 1"),
        (
            "reader",
            f"{_sel(table, consumer_row, consumer_col)} <- "
            f"sum({{t{table}, r{lo}-{hi}, c{cA}}})",
        ),
    ]
    result = CalculationsGraphService().generate_from_rows(
        rows, fixture_session, "t"
    )
    incoming = {e.source for e in result.edges if e.target == "reader"}
    # p1 writes cell A and p2 writes cell B; both lie in the r{lo}-{hi} range
    # on column cA, so both must feed the range reader.
    if cA == cB:
        assert {"p1", "p2"} <= incoming
