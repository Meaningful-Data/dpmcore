"""Tests for analytic (windowing) operator parsing."""

import pytest

from dpmcore.dpm_xl.ast.nodes import (
    AggregationOp,
    AnalyticClause,
    GroupingClause,
    RankOp,
    WindowClause,
)
from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor, serialize_ast
from dpmcore.services.syntax import SyntaxService

# ---- Syntax validity --------------------------------------------------


@pytest.mark.parametrize(
    "expr",
    [
        "sum({vRS} over (partition by CNT))",
        "avg({vRS} over (order by r asc))",
        "count({vRS} over (partition by CNT order by r desc))",
        "sum({vRS} over (order by r data points between 2 preceding and current data point))",
        "sum({vRS} over (order by yr range between 2 preceding and current data point))",
        "sum({vRS} over (order by r data points between unbounded preceding and unbounded following))",
        "sum({vRS} over (order by r data points between current data point and 3 following))",
        "sum({vRS} over (order by r data points between 1 preceding and 2 following))",
        "sum({vRS} over (partition by CNT order by r asc, s desc))",
        "sum({vRS} over (partition by CNT, s order by r))",
        "rank({vRS} over (order by f desc))",
        "rank({vRS} over (partition by CNT order by f asc))",
        "sum({vRS} over ())",
    ],
)
def test_analytic_expressions_are_valid_syntax(expr):
    assert SyntaxService().is_valid(expr)


def test_mutually_exclusive_clauses_are_invalid_syntax():
    assert not SyntaxService().is_valid(
        "sum({vRS} group by CNT over (partition by r))"
    )


# ---- AST structure — AggregationOp with analytic_clause ---------------


def test_sum_over_partition_by_builds_aggregation_op_with_analytic_clause():
    ast = SyntaxService().parse("sum({vRS} over (partition by CNT))")
    node = ast.children[0]
    assert isinstance(node, AggregationOp)
    assert node.op == "sum"
    assert node.grouping_clause is None
    assert isinstance(node.analytic_clause, AnalyticClause)
    assert node.analytic_clause.partition_by == ["CNT"]
    assert node.analytic_clause.order_by == []
    assert node.analytic_clause.window is None


def test_avg_over_order_by_with_direction():
    ast = SyntaxService().parse("avg({vRS} over (order by r desc))")
    node = ast.children[0]
    assert node.analytic_clause.order_by[0].direction == "desc"


def test_order_by_defaults_to_asc():
    ast = SyntaxService().parse("sum({vRS} over (order by r))")
    node = ast.children[0]
    assert node.analytic_clause.order_by[0].direction == "asc"


def test_partition_and_order_by_together():
    ast = SyntaxService().parse(
        "count({vRS} over (partition by CNT order by r asc))"
    )
    node = ast.children[0]
    clause = node.analytic_clause
    assert clause.partition_by == ["CNT"]
    assert len(clause.order_by) == 1
    assert clause.order_by[0].key_name == "r"


@pytest.mark.parametrize(
    ("frame_type", "expr"),
    [
        (
            "data_points",
            "sum({vRS} over (order by r data points between 2 preceding and current data point))",
        ),
        (
            "range",
            "sum({vRS} over (order by yr range between 2 preceding and current data point))",
        ),
    ],
)
def test_window_clause_frame_types(frame_type, expr):
    ast = SyntaxService().parse(expr)
    w = ast.children[0].analytic_clause.window
    assert isinstance(w, WindowClause)
    assert w.frame_type == frame_type
    assert w.start.bound_type == "n_preceding"
    assert w.start.n == 2
    assert w.end.bound_type == "current_data_point"


def test_window_clause_unbounded():
    ast = SyntaxService().parse(
        "sum({vRS} over (order by r data points between unbounded preceding and unbounded following))"
    )
    w = ast.children[0].analytic_clause.window
    assert w.start.bound_type == "unbounded_preceding"
    assert w.start.n is None
    assert w.end.bound_type == "unbounded_following"
    assert w.end.n is None


# ---- AST structure — RankOp -------------------------------------------


def test_rank_builds_rank_op_node():
    ast = SyntaxService().parse("rank({vRS} over (order by f desc))")
    node = ast.children[0]
    assert isinstance(node, RankOp)
    assert node.op == "rank"
    assert isinstance(node.analytic_clause, AnalyticClause)
    assert node.analytic_clause.order_by[0].key_name == "f"
    assert node.analytic_clause.order_by[0].direction == "desc"


# ---- grouping_clause still works unaffected ----------------------------


def test_group_by_still_builds_grouping_clause():
    ast = SyntaxService().parse("sum({vRS} group by CNT)")
    node = ast.children[0]
    assert isinstance(node, AggregationOp)
    assert isinstance(node.grouping_clause, GroupingClause)
    assert node.grouping_clause.components == ["CNT"]
    assert node.analytic_clause is None


# ---- toJSON serialisation ---------------------------------------------


def test_analytic_clause_tojson_is_serialisable():
    ast = SyntaxService().parse(
        "sum({vRS} over (partition by CNT order by r desc "
        "data points between 1 preceding and 1 following))"
    )
    result = ast.children[0].toJSON()
    assert result["analytic_clause"] is not None
    ac = result["analytic_clause"]
    assert ac["partition_by"] == ["CNT"]
    assert ac["order_by"][0]["key_name"] == "r"
    assert ac["window"]["frame_type"] == "data_points"
    assert ac["window"]["start"]["bound_type"] == "n_preceding"
    assert ac["window"]["end"]["bound_type"] == "n_following"


# ---- Wire serialisation ------------------------------------------------
# ``ASTToJSONVisitor`` is what script generation emits, and ``rank`` goes
# out as an ``AggregationOp`` discriminated by ``op`` like every other
# alternative of the ``aggregateOperators`` rule. ``RankOp.toJSON`` is
# gone, so these cases replace the assertions that read off it.

# The consumer schema is ``additionalProperties: false``, so the exact
# key set is part of the contract: ``grouping_clause`` is present and
# ``null`` rather than omitted, matching the rest of the family.
AGGREGATION_KEYS = {
    "class_name",
    "op",
    "operand",
    "grouping_clause",
    "analytic_clause",
}


def _serialize_expr(expression: str) -> dict:
    result = ASTToJSONVisitor().visit(SyntaxService().parse(expression))
    assert isinstance(result, dict)
    return result["children"][0]


def _class_names(node) -> set:
    """Every ``class_name`` in a serialized payload, at any depth."""
    if isinstance(node, dict):
        names = {node["class_name"]} if "class_name" in node else set()
        for value in node.values():
            names |= _class_names(value)
        return names
    if isinstance(node, list):
        names = set()
        for item in node:
            names |= _class_names(item)
        return names
    return set()


def test_rank_serializes_as_aggregation_op():
    node = _serialize_expr("rank({tT1, r001} over (order by f desc))")
    assert set(node) == AGGREGATION_KEYS
    assert node["class_name"] == "AggregationOp"
    assert node["op"] == "rank"
    assert node["grouping_clause"] is None
    ac = node["analytic_clause"]
    assert ac["class_name"] == "AnalyticClause"
    assert ac["partition_by"] == []
    assert ac["order_by"] == [{"key_name": "f", "direction": "desc"}]
    assert ac["window"] is None


def test_rank_serializes_partition_by():
    node = _serialize_expr(
        "rank({tT1, r001} over (partition by CNT order by f asc))"
    )
    assert set(node) == AGGREGATION_KEYS
    assert node["op"] == "rank"
    ac = node["analytic_clause"]
    assert ac["partition_by"] == ["CNT"]
    assert ac["order_by"] == [{"key_name": "f", "direction": "asc"}]


def test_rank_serializes_window_frame():
    node = _serialize_expr(
        "rank({tT1, r001} over (order by r "
        "data points between 1 preceding and 2 following))"
    )
    assert set(node) == AGGREGATION_KEYS
    window = node["analytic_clause"]["window"]
    assert window["frame_type"] == "data_points"
    assert window["start"] == {"bound_type": "n_preceding", "n": 1}
    assert window["end"] == {"bound_type": "n_following", "n": 2}


def test_rank_payload_matches_sum_over_the_same_clause():
    """Only ``op`` may distinguish ``rank`` from the other aggregates."""
    clause = (
        "over (partition by CNT order by f desc "
        "data points between 1 preceding and 1 following)"
    )
    rank = _serialize_expr(f"rank({{tT1, r001}} {clause})")
    aggregation = _serialize_expr(f"sum({{tT1, r001}} {clause})")
    assert aggregation["op"] == "sum"
    assert rank == {**aggregation, "op": "rank"}


def test_no_rank_op_class_name_at_any_depth():
    node = _serialize_expr(
        "{tT1, r002} = rank({tT1, r001} over (order by f desc))"
    )
    names = _class_names(node)
    assert "RankOp" not in names
    assert "AggregationOp" in names


def test_serialize_ast_emits_aggregation_op_at_the_public_entry_point():
    """``serialize_ast`` expands ``with`` scopes before serializing.

    It is the entry point ``ASTGeneratorService`` builds scripts with, so
    the shape has to hold there and not only under a bare visit.
    """
    payload = serialize_ast(
        SyntaxService().parse(
            "with {tT1} : {r002} = rank({r001} over (order by f desc))"
        )
    )
    node = payload["right"]
    assert set(node) == AGGREGATION_KEYS
    assert node["class_name"] == "AggregationOp"
    assert node["op"] == "rank"
    assert node["grouping_clause"] is None


def test_group_by_aggregation_serialization_is_unchanged():
    node = _serialize_expr("sum({tT1, r001} group by CNT)")
    assert set(node) == AGGREGATION_KEYS
    assert node["class_name"] == "AggregationOp"
    assert node["op"] == "sum"
    assert node["grouping_clause"] == {
        "class_name": "GroupingClause",
        "components": ["CNT"],
    }
    assert node["analytic_clause"] is None
