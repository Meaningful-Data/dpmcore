"""CLI tests for ``dpmcore generate-graph``.

``--database`` is required in every input mode: the engine resolves each
selection's cells against the dictionary. These tests use a *minimal* SQLite
database — the database-input path is fully exercised (it reads pre-resolved
operands), while the CSV/inline paths render nodes and explicit-reference
edges but cannot resolve cell selections against the empty tables (that exact
resolution is covered by the integration tests).
"""

import pytest
from click.testing import CliRunner

from dpmcore.cli.main import main


@pytest.fixture
def runner():
    return CliRunner()


def _write_csv(tmp_path, body):
    path = tmp_path / "calc.csv"
    path.write_text("Code,Expression\n" + body, encoding="utf-8")
    return path


def _build_minimal_db(path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import dpmcore.orm  # noqa: F401 — register mappers
    from dpmcore.orm.base import Base
    from dpmcore.orm.infrastructure import Release
    from dpmcore.orm.operations import (
        OperandReference,
        Operation,
        OperationNode,
        OperationVersion,
        Operator,
        OperatorArgument,
    )

    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        sess.add_all(
            [
                Release(release_id=1, code="4.2"),
                Operator(operator_id=1, name="Equal", symbol="="),
                OperatorArgument(
                    argument_id=10, operator_id=1, order=1, name="left"
                ),
                OperatorArgument(
                    argument_id=11, operator_id=1, order=2, name="right"
                ),
                Operation(operation_id=1, code="a"),
                Operation(operation_id=2, code="b"),
                OperationVersion(
                    operation_vid=1, operation_id=1, start_release_id=1
                ),
                OperationVersion(
                    operation_vid=2, operation_id=2, start_release_id=1
                ),
                OperationNode(node_id=1, operation_vid=1, operator_id=1),
                OperationNode(
                    node_id=2,
                    operation_vid=1,
                    parent_node_id=1,
                    argument_id=10,
                ),
                OperationNode(
                    node_id=3,
                    operation_vid=1,
                    parent_node_id=1,
                    argument_id=11,
                ),
                OperationNode(node_id=4, operation_vid=2, operator_id=1),
                OperationNode(
                    node_id=5,
                    operation_vid=2,
                    parent_node_id=4,
                    argument_id=10,
                ),
                OperationNode(
                    node_id=6,
                    operation_vid=2,
                    parent_node_id=4,
                    argument_id=11,
                ),
                OperandReference(
                    operand_reference_id=1, node_id=2, variable_id=100
                ),
                OperandReference(
                    operand_reference_id=2, node_id=3, variable_id=200
                ),
                OperandReference(
                    operand_reference_id=3, node_id=5, variable_id=200
                ),
                OperandReference(
                    operand_reference_id=4, node_id=6, variable_id=300
                ),
            ]
        )
        sess.commit()
    engine.dispose()


@pytest.fixture
def db_url(tmp_path):
    db_path = tmp_path / "dpm.db"
    _build_minimal_db(db_path)
    return f"sqlite:///{db_path}"


# --------------------------------------------------------------------------- #
# CSV / inline input modes (with --database)
# --------------------------------------------------------------------------- #


def test_generate_graph_csv_happy_path(runner, tmp_path, db_url):
    csv = _write_csv(
        tmp_path,
        'calc1,"{tK_1.00, r0010, c0010} <- {ocalc2}"\n'
        'calc2,"{tK_3.00, r0010, c0010} <- {tK_1.00, r0010, c0010} * 2"\n',
    )
    out = tmp_path / "graph.html"
    result = runner.invoke(
        main,
        ["generate-graph", str(csv), "--database", db_url, "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "cytoscape" in out.read_text(encoding="utf-8")
    # rich wraps console output, so normalise whitespace before matching.
    normalised = " ".join(result.output.split())
    assert "2 operations" in normalised
    # calc1 explicitly references calc2 -> exactly one (explicit) edge.
    assert "1 dependencies" in normalised


def test_generate_graph_with_title(runner, tmp_path, db_url):
    csv = _write_csv(tmp_path, "calc1,{tA, r1, c1} <- {tB, r1, c1}\n")
    out = tmp_path / "graph.html"
    result = runner.invoke(
        main,
        [
            "generate-graph",
            str(csv),
            "--database",
            db_url,
            "-o",
            str(out),
            "-t",
            "Custom",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Custom" in out.read_text(encoding="utf-8")


def test_generate_graph_inline_expressions(runner, tmp_path, db_url):
    out = tmp_path / "graph.html"
    result = runner.invoke(
        main,
        [
            "generate-graph",
            "-e",
            "calc1={tK_1.00, r0010, c0010} <- {ocalc2}",
            "-e",
            "calc2={tK_3.00, r0010, c0010} <- {tK_1.00, r0010, c0010} + 1",
            "--database",
            db_url,
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "2 operations" in " ".join(result.output.split())


def test_generate_graph_database_mode(runner, tmp_path, db_url):
    out = tmp_path / "graph.html"
    result = runner.invoke(
        main,
        ["generate-graph", "--database", db_url, "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    # op 'b' writes var 200 which op 'a' reads -> one edge, one root.
    normalised = " ".join(result.output.split())
    assert "2 operations" in normalised
    assert "1 dependencies" in normalised


def test_generate_graph_bad_header_exits_1(runner, tmp_path, db_url):
    csv = tmp_path / "calc.csv"
    csv.write_text("Name,Expr\na,b\n", encoding="utf-8")
    result = runner.invoke(
        main,
        [
            "generate-graph",
            str(csv),
            "--database",
            db_url,
            "-o",
            str(tmp_path / "g.html"),
        ],
    )
    assert result.exit_code == 1
    assert "Error" in result.output


# --------------------------------------------------------------------------- #
# Argument validation (fails before touching the database)
# --------------------------------------------------------------------------- #


def test_generate_graph_requires_database(runner, tmp_path):
    csv = _write_csv(tmp_path, "calc1,{tA, r1, c1} <- {tB, r1, c1}\n")
    result = runner.invoke(main, ["generate-graph", str(csv)])
    assert result.exit_code != 0
    assert "--database" in result.output


def test_generate_graph_rejects_both_sources(runner, tmp_path, db_url):
    csv = _write_csv(tmp_path, "calc1,{tA, r1, c1} <- {tB, r1, c1}\n")
    result = runner.invoke(
        main,
        [
            "generate-graph",
            str(csv),
            "-e",
            "calc2={tC} <- {tA}",
            "--database",
            db_url,
        ],
    )
    assert result.exit_code != 0
    assert "not both" in result.output


def test_generate_graph_filter_in_text_mode_rejected(runner, tmp_path, db_url):
    csv = _write_csv(tmp_path, "calc1,{tA, r1, c1} <- {tB, r1, c1}\n")
    result = runner.invoke(
        main,
        [
            "generate-graph",
            str(csv),
            "--database",
            db_url,
            "--table",
            "C_01.00",
        ],
    )
    assert result.exit_code != 0
    assert "reading the dictionary directly" in result.output


def test_generate_graph_inline_bad_format(runner, tmp_path, db_url):
    result = runner.invoke(
        main,
        [
            "generate-graph",
            "-e",
            "no-equals-sign",
            "--database",
            db_url,
            "-o",
            str(tmp_path / "g.html"),
        ],
    )
    assert result.exit_code != 0
    assert "CODE=EXPRESSION" in result.output


def test_generate_graph_missing_csv_file(runner, tmp_path, db_url):
    result = runner.invoke(
        main,
        ["generate-graph", str(tmp_path / "nope.csv"), "--database", db_url],
    )
    assert result.exit_code != 0
