"""Tests for analytic (windowing) operator parsing."""

import pytest

from dpmcore.dpm_xl.ast.nodes import (
    AggregationOp,
    AnalyticClause,
    GroupingClause,
    WindowClause,
)
from dpmcore.dpm_xl.operators.aggregate import Rank
from dpmcore.dpm_xl.symbols import (
    FactComponent,
    KeyComponent,
    RecordSet,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import Number
from dpmcore.dpm_xl.utils.operator_mapping import AGGR_OP_MAPPING
from dpmcore.dpm_xl.utils.serialization import deserialize_ast, serialize_ast
from dpmcore.dpm_xl.utils.tokens import STANDARD
from dpmcore.errors import SemanticError
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


# ---- AST structure — rank ---------------------------------------------
# ``rank`` is an alternative of the ``aggregateOperators`` grammar rule,
# so the constructor builds it as an ``AggregationOp`` discriminated by
# ``op`` — no node class of its own, and so no pass to special-case.


def test_rank_builds_aggregation_op_node():
    ast = SyntaxService().parse("rank({vRS} over (order by f desc))")
    node = ast.children[0]
    assert isinstance(node, AggregationOp)
    assert node.op == "rank"
    assert node.grouping_clause is None
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
# alternative of the ``aggregateOperators`` rule.

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

# Every clause pinned below is one ``rank`` actually accepts. A window
# frame is rejected by ``Rank.validate_analytic`` (4-4-0-6) and script
# generation drops such expressions before serializing them, so pinning
# a payload with one would assert a shape the pipeline can never emit —
# see ``test_rank_rejects_the_window_frame_it_is_never_asked_to_emit``.
LEGAL_RANK_CLAUSE = "over (partition by c order by f desc)"


def _recordset(key_names: list[str]) -> RecordSet:
    """A minimal RecordSet to check a parsed clause against."""
    components: list = [
        KeyComponent(k, Number(), STANDARD, "test") for k in key_names
    ]
    components.append(FactComponent(Number(), "test"))
    return RecordSet(Structure(components), "ds", "ds")


def test_rank_serializes_as_aggregation_op(serialize_expr):
    node = serialize_expr("rank({tT1, r001} over (order by f desc))")
    assert set(node) == AGGREGATION_KEYS
    assert node["class_name"] == "AggregationOp"
    assert node["op"] == "rank"
    assert node["grouping_clause"] is None
    ac = node["analytic_clause"]
    assert ac["class_name"] == "AnalyticClause"
    assert ac["partition_by"] == []
    assert ac["order_by"] == [{"key_name": "f", "direction": "desc"}]
    assert ac["window"] is None


def test_rank_serializes_partition_by(serialize_expr):
    node = serialize_expr(
        "rank({tT1, r001} over (partition by c order by f asc))"
    )
    assert set(node) == AGGREGATION_KEYS
    assert node["op"] == "rank"
    ac = node["analytic_clause"]
    assert ac["partition_by"] == ["c"]
    assert ac["order_by"] == [{"key_name": "f", "direction": "asc"}]


def test_aggregation_serializes_window_frame(serialize_expr):
    """Window frames are pinned on ``sum``: ``rank`` never carries one."""
    node = serialize_expr(
        "sum({tT1, r001} over (order by r "
        "data points between 1 preceding and 2 following))"
    )
    assert set(node) == AGGREGATION_KEYS
    window = node["analytic_clause"]["window"]
    assert window["frame_type"] == "data_points"
    assert window["start"] == {"bound_type": "n_preceding", "n": 1}
    assert window["end"] == {"bound_type": "n_following", "n": 2}


def test_rank_payload_matches_sum_over_the_same_clause(serialize_expr):
    """Only ``op`` may distinguish ``rank`` from the other aggregates."""
    rank = serialize_expr(f"rank({{tT1, r001}} {LEGAL_RANK_CLAUSE})")
    aggregation = serialize_expr(f"sum({{tT1, r001}} {LEGAL_RANK_CLAUSE})")
    assert aggregation["op"] == "sum"
    assert rank == {**aggregation, "op": "rank"}


def test_the_pinned_rank_clause_is_semantically_accepted():
    """The parity payload above is one the pipeline can really emit.

    ``ASTGeneratorService`` serializes an expression only after semantic
    validation passes, so a wire shape is worth pinning only for a
    clause ``Rank`` accepts.
    """
    ast = SyntaxService().parse(f"rank({{tT1, r001}} {LEGAL_RANK_CLAUSE})")
    result = Rank.validate_analytic(
        _recordset(["r", "c"]), ast.children[0].analytic_clause
    )
    assert isinstance(result, RecordSet)


def test_rank_rejects_the_window_frame_it_is_never_asked_to_emit():
    """Why no wire test pins a ``rank`` with a window frame."""
    ast = SyntaxService().parse(
        "rank({tT1, r001} over (order by r "
        "data points between 1 preceding and 2 following))"
    )
    with pytest.raises(SemanticError) as exc_info:
        Rank.validate_analytic(
            _recordset(["r", "c"]), ast.children[0].analytic_clause
        )
    assert exc_info.value.code == "4-4-0-6"


def test_no_rank_op_class_name_at_any_depth(serialize_expr, class_names):
    node = serialize_expr(
        "{tT1, r002} = rank({tT1, r001} over (order by f desc))"
    )
    names = class_names(node)
    assert "RankOp" not in names
    assert "AggregationOp" in names


def test_rank_tojson_agrees_with_the_visitor():
    """``toJSON`` is a second serialisation path and must not diverge.

    It is lossier by design (it hands operands to ``serialize_ast``
    rather than expanding them itself), but the discriminating keys have
    to be the ones the visitor emits.
    """
    node = (
        SyntaxService()
        .parse(f"rank({{tT1, r001}} {LEGAL_RANK_CLAUSE})")
        .children[0]
    )
    payload = node.toJSON()
    assert set(payload) == AGGREGATION_KEYS
    assert payload["class_name"] == "AggregationOp"
    assert payload["op"] == "rank"
    assert payload["grouping_clause"] is None


def test_serialized_rank_round_trips_to_a_resolvable_node(serialize_expr):
    """A deserialized ``rank`` must resolve in ``AGGR_OP_MAPPING``.

    The wire node is read back as a real ``AggregationOp``, and the
    semantic analyzer looks its ``op`` up in ``AGGR_OP_MAPPING`` — a
    missing key would surface as a bare ``KeyError`` instead of a
    ``DpmCoreError``.
    """
    node = deserialize_ast(
        serialize_expr(f"rank({{tT1, r001}} {LEGAL_RANK_CLAUSE})")
    )
    assert isinstance(node, AggregationOp)
    assert node.op == "rank"
    assert AGGR_OP_MAPPING[node.op] is Rank


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


def test_group_by_aggregation_serialization_is_unchanged(serialize_expr):
    node = serialize_expr("sum({tT1, r001} group by CNT)")
    assert set(node) == AGGREGATION_KEYS
    assert node["class_name"] == "AggregationOp"
    assert node["op"] == "sum"
    assert node["grouping_clause"] == {
        "class_name": "GroupingClause",
        "components": ["CNT"],
    }
    assert node["analytic_clause"] is None
