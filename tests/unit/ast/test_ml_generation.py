"""Verify visit_SubstrOp serializes start/length parameters distinctly and
MR !74 set operators emit operation nodes instead of NotImplementedError.
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from dpmcore.dpm_xl.ast.ml_generation import MLGeneration
from dpmcore.dpm_xl.ast.nodes import (
    AggregationOp,
    AnalyticClause,
    Constant,
    CountSetOp,
    Dimension,
    IntersectSetOp,
    OrderItem,
    Scalar,
    Set,
    SetdiffOp,
    SetOfOp,
    SubstrOp,
    SymdiffOp,
    UnionSetOp,
    VarID,
)
from dpmcore.dpm_xl.utils.tokens import FACT
from dpmcore.orm.operations import (
    OperandReference,
    OperandReferenceLocation,
    OperationNode,
)


@pytest.fixture
def ml_generation(monkeypatch):
    monkeypatch.setattr(MLGeneration, "__init__", lambda self, **kwargs: None)
    instance = MLGeneration(session=MagicMock())
    instance.create_operation_node = MagicMock(
        side_effect=lambda node, is_leaf=False: node
    )
    return instance


def _visited_children(ml_generation, node: SubstrOp) -> dict:
    """Extract child nodes created by visit_SubstrOp"""
    ml_generation.create_operation_node.reset_mock()
    ml_generation.visit = MagicMock(
        side_effect=lambda n: ml_generation.create_operation_node(n)
    )
    ml_generation.visit_SubstrOp(node)
    calls = [
        call.args[0]
        for call in ml_generation.create_operation_node.call_args_list
    ]
    return {n.argument: n.scalar for n in calls if n.argument is not None}


def test_substr_start_and_length_serialize_distinctly(ml_generation):
    """substr(x, 2, 5) and substr(x, 3, 9) must serialize differently;
    substr(x) must omit start/length entirely.
    """

    def children_for(start, length):
        node = SubstrOp(
            operand=Constant(type_="String", value="Hello"),
            start=start,
            length=length,
        )
        return _visited_children(ml_generation, node)

    children_2_5 = children_for(2, 5)
    children_3_9 = children_for(3, 9)
    children_none = children_for(None, None)

    assert children_2_5 != children_3_9
    assert children_2_5["start"] == 2
    assert children_2_5["length"] == 5
    assert children_3_9["start"] == 3
    assert children_3_9["length"] == 9
    assert "start" not in children_none
    assert "length" not in children_none


# ---------------------------------------------------------------------------
# MR !74: set operators (SetOfOp, UnionSetOp, IntersectSetOp, SetdiffOp,
# SymdiffOp) previously raised ``NotImplementedError`` in ``MLGeneration``,
# so any expression using them was silently dropped from the enriched AST.
# The visitors now emit real operation nodes and traverse every child.
# ---------------------------------------------------------------------------


def _int_constant(value: int) -> Constant:
    return Constant(type_="Integer", value=value)


def _visit_and_capture(ml_generation, visitor_name: str, node) -> list:
    """Invoke a MLGeneration visitor and return the child argument names it
    forwarded through ``self.visit(child)``. The fixture's ``visit`` mock
    records each call, which is enough to prove the visitor no longer
    raises and traversed every operand.
    """
    ml_generation.create_operation_node.reset_mock()
    visited: list = []
    ml_generation.visit = MagicMock(side_effect=lambda n: visited.append(n))
    getattr(ml_generation, visitor_name)(node)
    return visited


def test_visit_set_of_op_no_longer_raises_and_walks_operand(ml_generation):
    node = SetOfOp(operand=_int_constant(1))
    visited = _visit_and_capture(ml_generation, "visit_SetOfOp", node)
    assert ml_generation.create_operation_node.call_count == 1
    assert len(visited) == 1
    assert visited[0].argument == "operand"


def test_visit_rank_creates_an_operation_node_and_links_its_operand(
    ml_generation,
):
    """``rank`` is walked as an ``AggregationOp``, so it lands in the tree.

    Its own visitor created no ``OperationNode`` and never set the
    operand's ``parent``/``argument``, which stored the operand as a
    root-level orphan and left nothing representing the operator itself.
    """
    node = AggregationOp(
        op="rank",
        operand=_int_constant(1),
        grouping_clause=None,
        analytic_clause=AnalyticClause(
            partition_by=[], order_by=[OrderItem("r")], window=None
        ),
    )
    visited = _visit_and_capture(ml_generation, "visit_AggregationOp", node)
    assert ml_generation.create_operation_node.call_count == 1
    assert len(visited) == 1
    assert visited[0].argument == "operand"
    assert visited[0].parent is node


def test_visit_union_set_op_walks_every_operand(ml_generation):
    node = UnionSetOp(
        operands=[_int_constant(1), _int_constant(2), _int_constant(3)],
    )
    visited = _visit_and_capture(ml_generation, "visit_UnionSetOp", node)
    assert ml_generation.create_operation_node.call_count == 1
    assert len(visited) == 3
    assert all(v.argument == "operand" for v in visited)


def test_visit_intersect_set_op_walks_every_operand(ml_generation):
    node = IntersectSetOp(operands=[_int_constant(1), _int_constant(2)])
    visited = _visit_and_capture(ml_generation, "visit_IntersectSetOp", node)
    assert ml_generation.create_operation_node.call_count == 1
    assert len(visited) == 2
    assert all(v.argument == "operand" for v in visited)


def test_visit_setdiff_op_assigns_left_and_right_arguments(ml_generation):
    node = SetdiffOp(left=_int_constant(1), right=_int_constant(2))
    visited = _visit_and_capture(ml_generation, "visit_SetdiffOp", node)
    assert ml_generation.create_operation_node.call_count == 1
    assert [v.argument for v in visited] == ["left", "right"]


def test_visit_symdiff_op_assigns_left_and_right_arguments(ml_generation):
    node = SymdiffOp(left=_int_constant(1), right=_int_constant(2))
    visited = _visit_and_capture(ml_generation, "visit_SymdiffOp", node)
    assert ml_generation.create_operation_node.call_count == 1
    assert [v.argument for v in visited] == ["left", "right"]


def test_visit_count_set_op_walks_operand(ml_generation):
    """``CountSetOp`` is kept as a legacy AST shape after MR !74 dropped the
    grammar rule; the visitor still needs to route through create/visit so
    externally-built ASTs keep round-tripping.
    """
    node = CountSetOp(operand=Set(children=[_int_constant(1)]))
    visited = _visit_and_capture(ml_generation, "visit_CountSetOp", node)
    assert ml_generation.create_operation_node.call_count == 1
    assert len(visited) == 1
    assert visited[0].argument == "operand"


def test_visit_empty_set_creates_leaf_without_operand_refs(ml_generation):
    """``visit_Set`` iterates ``node.children``; for the empty literal ``{}``
    the loop is a no-op, and the operation node is still emitted.
    """
    ml_generation.session = MagicMock()
    ml_generation.visit_Set(Set(children=[]))
    assert ml_generation.create_operation_node.call_count == 1
    # No ``OperandReference`` rows added for children that don't exist.
    assert ml_generation.session.add.call_count == 0


def test_create_operation_node_builds_operation_node_with_real_attributes(
    ml_generation,
):
    ml_generation.session = MagicMock()
    ml_generation.op_version_id = 99
    ml_generation.df_operators = pd.DataFrame(
        columns=["Symbol", "OperatorID", "Name"]
    )
    ml_generation.df_arguments = pd.DataFrame(
        columns=["Name", "OperatorID", "ArgumentID"]
    )
    node = Constant(type_="Integer", value=1)
    node.scalar = "1"

    result = MLGeneration.create_operation_node(
        ml_generation, node, is_leaf=True
    )

    assert isinstance(result, OperationNode)
    assert result.operation_vid == 99
    assert result.scalar == "1"
    assert result.is_leaf is True


def test_create_operation_node_resolves_argument_id_from_parent_operator_id(
    ml_generation,
):
    ml_generation.session = MagicMock()
    ml_generation.op_version_id = 99
    ml_generation.df_operators = pd.DataFrame(
        columns=["Symbol", "OperatorID", "Name"]
    )
    ml_generation.df_arguments = pd.DataFrame(
        {"Name": ["left"], "OperatorID": [7], "ArgumentID": [11]}
    )
    node = Constant(type_="Integer", value=1)
    node.argument = "left"
    node.parent = OperationNode(operator_id=7)

    result = MLGeneration.create_operation_node(ml_generation, node)

    assert result.argument_id == 11


def test_visit_var_id_builds_operand_reference_and_location_with_real_attributes(
    ml_generation,
):
    ml_generation.session = MagicMock()
    ml_generation.data = None
    ml_generation.is_scripting = False
    ml_generation.create_operation_node = MagicMock(
        return_value=OperationNode()
    )
    ml_generation.extract_operand_data = MagicMock(
        return_value=[
            {
                "x": None,
                "y": None,
                "z": None,
                "variable_id": 42,
                "cell_id": 7,
                "row_code": "r1",
                "column_code": "c1",
                "sheet_code": "s1",
            }
        ]
    )
    node = VarID(
        table="T1",
        rows=None,
        cols=None,
        sheets=None,
        interval=None,
        default=None,
    )

    ml_generation.visit_VarID(node)

    added = [call.args[0] for call in ml_generation.session.add.call_args_list]
    op_ref = next(o for o in added if isinstance(o, OperandReference))
    op_ref_loc = next(
        o for o in added if isinstance(o, OperandReferenceLocation)
    )
    assert op_ref.variable_id == 42
    assert op_ref.operand_reference == "variable"
    assert op_ref_loc.cell_id == 7
    assert op_ref_loc.table == "T1"


def test_visit_dimension_on_the_fact_emits_a_leaf_without_operand_refs(
    ml_generation,
):
    """The Fact Component is not a Property, so there is nothing to reference.

    ``visit_Dimension`` normally resolves the code to a ``property_id`` and
    adds an ``OperandReference``; the dictionary has no row for "f", so the
    component name is stored on the node itself instead — the same mechanism
    literal arguments use.
    """
    ml_generation.session = MagicMock()
    node = Dimension(dimension_code=FACT)

    ml_generation.visit_Dimension(node)

    assert node.scalar == FACT
    assert ml_generation.create_operation_node.call_count == 1
    assert ml_generation.session.add.call_count == 0


def test_visit_set_creates_an_operand_reference_per_item_child(
    ml_generation, monkeypatch
):
    """``x in {[a],[b]}`` must emit one item ``OperandReference`` per element."""
    ml_generation.session = MagicMock()
    ml_generation.session_queries = MagicMock()
    ml_generation.create_operation_node = MagicMock(
        return_value=OperationNode()
    )
    monkeypatch.setattr(
        "dpmcore.dpm_xl.ast.ml_generation.ItemCategoryQuery.get_item_category_id_from_signature",
        lambda signature, session: [{"a": 1, "b": 2}[signature]],
    )
    node = Set(
        children=[
            Scalar(item="a", scalar_type="Item"),
            Scalar(item="b", scalar_type="Item"),
        ]
    )

    ml_generation.visit_Set(node)

    added = [call.args[0] for call in ml_generation.session.add.call_args_list]
    item_ids = sorted(
        o.item_id for o in added if isinstance(o, OperandReference)
    )
    assert item_ids == [1, 2]


def test_visit_set_creates_operand_references_for_children_from_another_ast_implementation(
    ml_generation, monkeypatch
):
    """Regression test: ``visit_Set`` used to require dpmcore's own concrete
    ``Scalar`` class via ``isinstance``, so a structurally identical ``Scalar``
    from another parser silently produced zero ``OperandReference`` rows.
    """

    class Scalar:  # a different, unrelated "Scalar" class - not dpmcore's
        def __init__(self, item, scalar_type):
            self.item = item
            self.scalar_type = scalar_type

    ml_generation.session = MagicMock()
    ml_generation.session_queries = MagicMock()
    ml_generation.create_operation_node = MagicMock(
        return_value=OperationNode()
    )
    monkeypatch.setattr(
        "dpmcore.dpm_xl.ast.ml_generation.ItemCategoryQuery.get_item_category_id_from_signature",
        lambda signature, session: [1],
    )
    node = Set(children=[Scalar(item="eba_MC:x1281", scalar_type="Item")])

    ml_generation.visit_Set(node)

    added = [call.args[0] for call in ml_generation.session.add.call_args_list]
    op_refs = [o for o in added if isinstance(o, OperandReference)]
    assert len(op_refs) == 1
    assert op_refs[0].item_id == 1


def test_create_operation_node_unwraps_a_constant_default(ml_generation):
    """A ``default(...)`` fallback value must be unwrapped to its raw value."""
    ml_generation.session = MagicMock()
    ml_generation.op_version_id = 99
    ml_generation.df_operators = pd.DataFrame(
        columns=["Symbol", "OperatorID", "Name"]
    )
    ml_generation.df_arguments = pd.DataFrame(
        columns=["Name", "OperatorID", "ArgumentID"]
    )
    node = Constant(type_="Integer", value=1)
    node.default = Constant(type_="Integer", value=0)

    result = MLGeneration.create_operation_node(ml_generation, node)

    assert result.fallback_value == 0


def test_create_operation_node_unwraps_a_default_from_another_ast_implementation(
    ml_generation,
):
    """Regression test: ``create_operation_node`` used to require dpmcore's own
    concrete ``Constant`` class via ``isinstance``, so a structurally identical
    ``Constant`` from another parser was kept wrapped instead of unwrapped to
    its raw value.
    """

    class Constant:  # a different, unrelated "Constant" class - not dpmcore's
        def __init__(self, value):
            self.value = value

    ml_generation.session = MagicMock()
    ml_generation.op_version_id = 99
    ml_generation.df_operators = pd.DataFrame(
        columns=["Symbol", "OperatorID", "Name"]
    )
    ml_generation.df_arguments = pd.DataFrame(
        columns=["Name", "OperatorID", "ArgumentID"]
    )
    node = VarID(
        table=None, rows=None, cols=None, sheets=None, interval=False,
        default=Constant(value=0),
    )

    result = MLGeneration.create_operation_node(ml_generation, node)

    assert result.fallback_value == 0
