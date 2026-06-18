"""Unit tests for the calculations-graph service (no database required)."""

import pytest

import dpmcore.services.calculations_graph.service as svc_mod
from dpmcore.dpm_xl.ast.nodes import OperationRef, Start, VarID
from dpmcore.errors import InternalError, Invalid
from dpmcore.services.calculations_graph import (
    CalculationsGraphResult,
    CalculationsGraphService,
)


@pytest.fixture
def service():
    return CalculationsGraphService()


def _mk_varid(table=None, rows=None, cols=None, sheets=None, operation=None):
    return VarID(table, rows, cols, sheets, None, None, operation=operation)


# --------------------------------------------------------------------------- #
# AST traversal helpers
# --------------------------------------------------------------------------- #


def test_ast_children_variants():
    var = _mk_varid(table="T")
    assert svc_mod._ast_children(var) == [var]
    assert svc_mod._ast_children([var, 1, "x"]) == [var]
    assert svc_mod._ast_children((var,)) == [var]
    assert svc_mod._ast_children({"a": var, "b": 2}) == [var]
    assert svc_mod._ast_children(42) == []


def test_iter_ast_dedupes_shared_nodes():
    leaf = _mk_varid(table="T", rows=["0010"], cols=["0010"])
    root = Start(children=[leaf, leaf])  # leaf reachable twice
    nodes = list(svc_mod._iter_ast(root))
    assert nodes.count(leaf) == 1
    assert root in nodes


def test_collect_handles_bare_operation_ref():
    # Parsing wraps {o..} into a VarID, but _collect also defends against a
    # bare OperationRef node appearing in the tree.
    root = Start(children=[OperationRef(operation_code="OPX")])
    keys, op_refs = svc_mod._collect(root)
    assert keys == set()
    assert op_refs == {"OPX"}


# --------------------------------------------------------------------------- #
# Cell-key building and matching
# --------------------------------------------------------------------------- #


def test_varid_keys_cartesian():
    var = _mk_varid(table="K_1.00", rows=["0010"], cols=["0010", "0020"])
    assert svc_mod._varid_keys(var) == {
        ("K_1.00", "0010", "0010", "*"),
        ("K_1.00", "0010", "0020", "*"),
    }


def test_varid_keys_config_only_is_empty():
    # A ``with {default: 0}`` clause carries no table/row/col/sheet.
    assert svc_mod._varid_keys(_mk_varid()) == set()


def test_varid_keys_table_only_uses_wildcards():
    assert svc_mod._varid_keys(_mk_varid(table="K_1.00")) == {
        ("K_1.00", "*", "*", "*")
    }


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("0010-0050", (10, 50)),
        ("0010", None),
        ("A-B", None),
        ("0010-0050-0070", None),
    ],
)
def test_as_range(token, expected):
    assert svc_mod._as_range(token) == expected


@pytest.mark.parametrize(
    ("token", "bounds", "expected"),
    [
        ("0030", (10, 50), True),
        ("0060", (10, 50), False),
        ("A", (10, 50), False),
    ],
)
def test_in_range(token, bounds, expected):
    assert svc_mod._in_range(token, bounds) is expected


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("*", "0010", True),
        ("0010", "*", True),
        ("0010", "0010", True),
        ("0010", "0020", False),
        ("0030", "0010-0050", True),
        ("0060", "0010-0050", False),
        ("0010-0050", "0030", True),
        ("0010-0050", "0060", False),
        ("0010-0050", "0040-0090", True),
        ("0010-0050", "0060-0090", False),
    ],
)
def test_dim_overlap(left, right, expected):
    assert svc_mod._dim_overlap(left, right) is expected


def test_cells_overlap():
    base = ("K", "0010", "0010", "*")
    assert svc_mod._cells_overlap(base, base) is True
    assert svc_mod._cells_overlap(base, ("K", "0020", "0010", "*")) is False


def test_producers_for_table_specific_and_wildcard():
    writes = {
        "K1": [("opA", ("K1", "0010", "0010", "*"))],
        "*": [("opW", ("*", "0010", "0010", "*"))],
    }
    producers = svc_mod._producers_for({("K1", "0010", "0010", "*")}, writes)
    assert producers == {"opA", "opW"}


def test_producers_for_wildcard_read():
    writes = {"K1": [("opA", ("K1", "0010", "0010", "*"))]}
    producers = svc_mod._producers_for({("*", "0010", "0010", "*")}, writes)
    assert producers == {"opA"}


def test_producers_for_no_match():
    writes = {"K1": [("opA", ("K1", "0010", "0010", "*"))]}
    producers = svc_mod._producers_for({("K1", "9999", "0010", "*")}, writes)
    assert producers == set()


# --------------------------------------------------------------------------- #
# Display + escaping helpers
# --------------------------------------------------------------------------- #


def test_split_assignment_no_arrow():
    assert svc_mod._split_assignment("{tA} + 1") == ("", "{tA} + 1")


def test_split_assignment_with_clause():
    lhs, rhs = svc_mod._split_assignment(
        "{tA, r1, c1} <- with {default: 0}: ({tB} + 1)"
    )
    assert lhs == "{tA, r1, c1}"
    assert rhs == "({tB} + 1)"


def test_split_assignment_plain_rhs():
    assert svc_mod._split_assignment("{tA} <- {tB} * 2") == (
        "{tA}",
        "{tB} * 2",
    )


def test_json_for_html_escapes_unsafe_chars():
    out = svc_mod._json_for_html({"x": "</script><a>&b"})
    assert "</script>" not in out
    assert "\\u003c/script\\u003e" in out
    assert "\\u0026b" in out


def test_op_warnings_parse_error_and_o_prefix():
    op = svc_mod._Operation(
        code="ocalc",
        expression="x",
        lhs_text="",
        rhs_text="x",
        parse_error="boom",
    )
    warnings = svc_mod._op_warnings(op)
    assert any("could not be parsed" in w for w in warnings)
    assert any("starts with 'o'" in w for w in warnings)


def test_op_warnings_clean():
    op = svc_mod._Operation(
        code="calc", expression="x", lhs_text="", rhs_text="x"
    )
    assert svc_mod._op_warnings(op) == []


def test_add_edge_keeps_explicit_over_implicit():
    edges: dict = {}
    svc_mod._add_edge(edges, "a", "b", "explicit")
    svc_mod._add_edge(edges, "a", "b", "implicit")
    assert edges == {("a", "b"): "explicit"}


# --------------------------------------------------------------------------- #
# Service: parsing
# --------------------------------------------------------------------------- #


def test_collect_part_empty(service):
    assert service._collect_part("   ") == (set(), set(), None)


def test_collect_part_parse_error(service):
    keys, op_refs, error = service._collect_part("@@@ invalid")
    assert keys == set()
    assert op_refs == set()
    assert error is not None


def test_collect_part_success(service):
    keys, op_refs, error = service._collect_part(
        "{tK_1.00, r0010, c0010} + {oOP2}"
    )
    assert ("K_1.00", "0010", "0010", "*") in keys
    assert "OP2" in op_refs
    assert error is None


def test_extract_keys_assignment(service):
    writes, reads, _refs, error = service._extract_keys(
        "{tK_1.00, r0010, c0010} <- {tK_2.00, r0010, c0010} + 1"
    )
    assert ("K_1.00", "0010", "0010", "*") in writes
    assert ("K_2.00", "0010", "0010", "*") in reads
    assert error is None


def test_extract_keys_no_arrow_has_no_writes(service):
    writes, reads, _refs, _error = service._extract_keys(
        "{tK_2.00, r0010, c0010} + 1"
    )
    assert writes == set()
    assert ("K_2.00", "0010", "0010", "*") in reads


def test_extract_keys_records_lhs_error(service):
    _writes, _reads, _refs, error = service._extract_keys(
        "@@@ <- {tK_2.00, r0010, c0010}"
    )
    assert error is not None


# --------------------------------------------------------------------------- #
# Service: graph building
# --------------------------------------------------------------------------- #


def test_build_graph_self_edge_skipped(service):
    ops = service.parse_operations(
        [("calc1", "{tK_1.00, r0010, c0010} <- {tK_1.00, r0010, c0010} + 1")]
    )
    _nodes, edges, _warnings = service.build_graph(ops)
    assert edges == ()


def test_build_graph_implicit_and_explicit(service):
    ops = service.parse_operations(
        [
            (
                "calc1",
                "{tK_1.00, r0010, c0010} <- {tK_9.00, r0010, c0010} + 1",
            ),
            (
                "calc2",
                "{tK_2.00, r0010, c0010} <- {tK_1.00, r0010, c0010} * 2",
            ),
            ("calc3", "{tK_3.00, r0010, c0010} <- {ocalc1, r0010, c0010}"),
        ]
    )
    nodes, edges, _warnings = service.build_graph(ops)
    pairs = {(e.source, e.target, e.kind) for e in edges}
    assert ("calc1", "calc2", "implicit") in pairs
    assert ("calc1", "calc3", "explicit") in pairs
    roots = {n.code for n in nodes if n.is_root}
    assert roots == {"calc1"}


def test_build_graph_dangling_reference_warns(service):
    ops = service.parse_operations(
        [("calc1", "{tK_1.00, r0010, c0010} <- {oZZZ, r0010, c0010}")]
    )
    _nodes, edges, warnings = service.build_graph(ops)
    assert edges == ()
    assert any("unknown operation" in w for w in warnings)


# --------------------------------------------------------------------------- #
# Service: CSV reading
# --------------------------------------------------------------------------- #


def test_read_csv_rows_ok(tmp_path):
    path = tmp_path / "calc.csv"
    path.write_text(
        "Code,Expression\ncalc1,{tA} <- {tB}\n\n,ignored\ncalc2\n",
        encoding="utf-8",
    )
    assert svc_mod._read_csv_rows(path) == [
        ("calc1", "{tA} <- {tB}"),
        ("calc2", ""),
    ]


def test_read_csv_rows_bad_header(tmp_path):
    path = tmp_path / "calc.csv"
    path.write_text("Name,Expr\na,b\n", encoding="utf-8")
    with pytest.raises(Invalid):
        svc_mod._read_csv_rows(path)


def test_read_csv_rows_empty_file(tmp_path):
    path = tmp_path / "calc.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(Invalid):
        svc_mod._read_csv_rows(path)


# --------------------------------------------------------------------------- #
# Resource loading
# --------------------------------------------------------------------------- #


def test_load_assets_missing_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(svc_mod, "_assets_path", lambda: tmp_path)
    with pytest.raises(InternalError):
        svc_mod._load_assets()


# --------------------------------------------------------------------------- #
# Service: end-to-end
# --------------------------------------------------------------------------- #


def test_generate_end_to_end(tmp_path):
    path = tmp_path / "calc.csv"
    path.write_text(
        "Code,Expression\n"
        'calc1,"{tK_1.00, r0010, c0010} <- {tK_2.00, r0010, c0010} + 1"\n'
        'calc2,"{tK_3.00, r0010, c0010} <- {tK_1.00, r0010, c0010} * 2"\n',
        encoding="utf-8",
    )
    result = CalculationsGraphService().generate(path)
    assert isinstance(result, CalculationsGraphResult)
    assert result.n_nodes == 2
    assert result.n_edges == 1
    assert result.n_roots == 1
    assert "cytoscape" in result.html


def test_generate_escapes_script_tag(tmp_path):
    path = tmp_path / "calc.csv"
    path.write_text(
        "Code,Expression\n"
        'calc1,"{tA, r1, c1} <- {tB, r1, c1} + 1 </script><b>x</b>"\n',
        encoding="utf-8",
    )
    result = CalculationsGraphService().generate(path)
    assert "\\u003c/script\\u003e" in result.html
    # Only the legitimate script tags (3 vendored + 1 inline) remain raw.
    assert result.html.count("</script>") == 4


def test_generate_escapes_title(tmp_path):
    path = tmp_path / "calc.csv"
    path.write_text(
        "Code,Expression\ncalc1,{tA, r1, c1} <- {tB, r1, c1}\n",
        encoding="utf-8",
    )
    result = CalculationsGraphService().generate(path, title="My <Graph>")
    assert "My &lt;Graph&gt;" in result.html


def test_generate_from_rows():
    result = CalculationsGraphService().generate_from_rows(
        [
            ("calc1", "{tK_1.00, r0010, c0010} <- {tK_2.00, r0010, c0010}"),
            (
                "calc2",
                "{tK_3.00, r0010, c0010} <- {tK_1.00, r0010, c0010} + 1",
            ),
        ],
        title="Inline",
    )
    assert isinstance(result, CalculationsGraphResult)
    assert result.n_nodes == 2
    assert result.n_edges == 1
    assert "Inline" in result.html
