"""Unit tests for the calculations-graph service.

Dependency resolution now always runs through the DPM-XL engine
(:class:`OperandsChecking`) against a database, so these unit tests exercise
the pure graph-building helpers plus the graceful-degradation and
explicit-reference behaviour against a *minimal* in-memory database (a single
release, no cell views). Exact cell resolution against real data is covered by
``tests/integration/services/test_calculations_graph_resolution.py``.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import dpmcore.orm  # noqa: F401 — register ORM mappers
from dpmcore.dpm_xl.ast.nodes import AST, OperationRef, VarID
from dpmcore.errors import Invalid
from dpmcore.orm.base import Base
from dpmcore.orm.infrastructure import Release
from dpmcore.services.calculations_graph import CalculationsGraphService
from dpmcore.services.calculations_graph.service import (
    _add_edge,
    _ast_children,
    _collect_op_refs,
    _implicit_edges,
    _iter_ast,
    _json_for_html,
    _load_assets,
    _op_warnings,
    _Operation,
    _read_csv_rows,
    _split_assignment,
)


@pytest.fixture
def session():
    """A minimal in-memory database: one release, no cell/table data."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = Session(engine)
    sess.add(Release(release_id=1, code="4.2"))
    sess.commit()
    yield sess
    sess.close()
    engine.dispose()


@pytest.fixture
def service():
    return CalculationsGraphService()


def _mk_varid(table=None, rows=None, cols=None, sheets=None, operation=None):
    return VarID(table, rows, cols, sheets, None, None, operation=operation)


def _op(code, *, outputs=None, inputs=None, op_refs=None, error=None):
    return _Operation(
        code=code,
        expression=f"{code} expr",
        lhs_text="",
        rhs_text="",
        output_var_ids=set(outputs or ()),
        input_var_ids=set(inputs or ()),
        op_refs=set(op_refs or ()),
        parse_error=error,
    )


# --------------------------------------------------------------------------- #
# AST traversal helpers
# --------------------------------------------------------------------------- #


def test_ast_children_variants():
    var = _mk_varid(table="T")
    assert _ast_children(var) == [var]
    assert _ast_children([var, "not-ast", 3]) == [var]
    assert _ast_children({"a": var, "b": 1}) == [var]
    assert _ast_children("scalar") == []


def test_iter_ast_dedupes_shared_nodes():
    shared = OperationRef("shared")
    root = AST()
    root.left = shared
    root.right = shared
    nodes = list(_iter_ast(root))
    assert nodes.count(shared) == 1
    assert root in nodes


def test_collect_op_refs_from_varid_and_operationref():
    root = AST()
    root.a = _mk_varid(operation="ref1")
    root.b = OperationRef("ref2")
    root.c = _mk_varid(table="tA", rows=["r1"], cols=["c1"])  # cell selection
    assert _collect_op_refs(root) == {"ref1", "ref2"}


# --------------------------------------------------------------------------- #
# Edge building
# --------------------------------------------------------------------------- #


def test_implicit_edges_exact_variable_match():
    edges = _implicit_edges(
        {"a": {100}, "b": {200}},  # a writes 100, b writes 200
        {"a": {200}, "b": {300}},  # a reads 200 (b's output), b reads 300
    )
    assert edges == {("b", "a"): "implicit"}


def test_implicit_edges_skip_self_and_unmatched():
    edges = _implicit_edges(
        {"a": {5}, "b": {9}},
        {"a": {5}, "b": {7}},  # a reads its own output; b shares nothing
    )
    assert edges == {}


def test_add_edge_keeps_first_kind():
    edges: dict[tuple[str, str], str] = {}
    _add_edge(edges, "a", "b", "explicit")
    _add_edge(edges, "a", "b", "implicit")  # ignored: pair already present
    assert edges == {("a", "b"): "explicit"}


def test_build_graph_implicit_and_explicit(service):
    ops = [
        _op("a", outputs={100}, inputs={200}),
        _op("b", outputs={200}, inputs={300}),  # b writes 200 -> edge b->a
        _op("c", op_refs={"a"}),  # explicit -> edge a->c
    ]
    nodes, edges, warnings = service.build_graph(ops)
    pairs = {(e.source, e.target, e.kind) for e in edges}
    assert ("b", "a", "implicit") in pairs
    assert ("a", "c", "explicit") in pairs
    roots = {n.code for n in nodes if n.is_root}
    assert roots == {"b"}  # a's producer is b; c's is a; b is the root
    assert warnings == ()


def test_build_graph_self_edge_skipped(service):
    ops = [_op("a", outputs={1}, inputs={1})]
    _nodes, edges, _warnings = service.build_graph(ops)
    assert edges == ()


def test_build_graph_explicit_wins_over_implicit(service):
    # b writes 200 which a reads (implicit b->a); a also explicitly refs b.
    ops = [
        _op("a", inputs={200}, op_refs={"b"}),
        _op("b", outputs={200}),
    ]
    _nodes, edges, _warnings = service.build_graph(ops)
    kinds = {(e.source, e.target): e.kind for e in edges}
    assert kinds[("b", "a")] == "explicit"


def test_build_graph_dangling_reference_warns(service):
    _nodes, _edges, warnings = service.build_graph([_op("a", op_refs={"ZZZ"})])
    assert any("unknown operation" in w for w in warnings)


def test_op_warnings_parse_error_and_o_prefix():
    warnings = _op_warnings(_op("op1", error="boom"))
    assert any("could not be resolved" in w for w in warnings)
    assert any("should not begin with 'o'" in w for w in warnings)


def test_op_warnings_clean():
    assert _op_warnings(_op("calc1")) == []


# --------------------------------------------------------------------------- #
# Display helpers
# --------------------------------------------------------------------------- #


def test_split_assignment_no_arrow():
    assert _split_assignment("{tA, r1, c1}") == ("", "{tA, r1, c1}")


def test_split_assignment_with_clause():
    lhs, rhs = _split_assignment(
        "{tA, r1, c1} <- with {default: 0, interval: true}: ({tB, r1, c1})"
    )
    assert lhs == "{tA, r1, c1}"
    assert rhs == "({tB, r1, c1})"


def test_json_for_html_escapes_unsafe_chars():
    out = _json_for_html({"k": "<a> & </b>"})
    assert "<" not in out
    assert ">" not in out
    assert "&" not in out
    assert "\\u003c" in out


# --------------------------------------------------------------------------- #
# CSV reading
# --------------------------------------------------------------------------- #


def test_read_csv_rows_ok(tmp_path):
    path = tmp_path / "calc.csv"
    path.write_text(
        'Code,Expression\ncalc1,"{tA} <- {tB}"\n\ncalc2,{tC} <- {tA}\n',
        encoding="utf-8",
    )
    assert _read_csv_rows(path) == [
        ("calc1", "{tA} <- {tB}"),
        ("calc2", "{tC} <- {tA}"),
    ]


def test_read_csv_rows_bad_header(tmp_path):
    path = tmp_path / "calc.csv"
    path.write_text("Name,Expr\na,b\n", encoding="utf-8")
    with pytest.raises(Invalid):
        _read_csv_rows(path)


def test_load_assets_missing_raises(monkeypatch):
    import dpmcore.services.calculations_graph.service as mod

    class _Boom:
        def __truediv__(self, _other):
            return self

        def read_text(self, *args, **kwargs):
            raise FileNotFoundError

    monkeypatch.setattr(mod, "_assets_path", lambda: _Boom())
    from dpmcore.errors import InternalError

    with pytest.raises(InternalError):
        _load_assets()


# --------------------------------------------------------------------------- #
# End-to-end against a minimal database (resolution degrades gracefully)
# --------------------------------------------------------------------------- #


def test_generate_from_rows_renders_and_links_explicit(service, session):
    # The cell selections cannot resolve against the empty minimal DB, so no
    # implicit edges — but explicit references need no cell resolution.
    rows = [
        ("calc1", "{tK_1.00, r0010, c0010} <- {tK_2.00, r0010, c0010} + 1"),
        ("calc2", "{tK_3.00, r0010, c0010} <- {ocalc1} * 2"),
    ]
    result = service.generate_from_rows(rows, session, "graph")
    assert {n.code for n in result.nodes} == {"calc1", "calc2"}
    pairs = {(e.source, e.target, e.kind) for e in result.edges}
    assert pairs == {("calc1", "calc2", "explicit")}
    assert "cytoscape" in result.html
    # Unresolvable cell selections are surfaced, not fatal.
    assert result.warnings


def test_generate_reads_csv(service, session, tmp_path):
    path = tmp_path / "calc.csv"
    path.write_text(
        'Code,Expression\ncalc1,"{tA, r1, c1} <- {ocalc2}"\n'
        'calc2,"{tB, r1, c1} <- {tC, r1, c1}"\n',
        encoding="utf-8",
    )
    result = service.generate(path, session)
    assert {n.code for n in result.nodes} == {"calc1", "calc2"}
    assert ("calc2", "calc1", "explicit") in {
        (e.source, e.target, e.kind) for e in result.edges
    }


def test_generate_escapes_title(service, session, tmp_path):
    path = tmp_path / "calc.csv"
    path.write_text("Code,Expression\ncalc1,{tA}\n", encoding="utf-8")
    result = service.generate(path, session, title="My <Graph>")
    assert "My &lt;Graph&gt;" in result.html
    assert "<title>My <Graph>" not in result.html
