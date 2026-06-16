"""Tests for analytic (windowing) operator parsing."""

import pytest

from dpmcore.dpm_xl.ast.nodes import (
    AggregationOp,
    AnalyticClause,
    GroupingClause,
    RankOp,
    WindowClause,
)
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


def test_rank_tojson_is_serialisable():
    ast = SyntaxService().parse("rank({vRS} over (order by f desc))")
    result = ast.children[0].toJSON()
    assert result["op"] == "rank"
    assert result["analytic_clause"]["order_by"][0]["direction"] == "desc"
