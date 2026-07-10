"""Verify visit_SubstrOp serializes start/length parameters distinctly and
MR !74 set operators emit operation nodes instead of NotImplementedError.
"""

from unittest.mock import MagicMock

import pytest

from dpmcore.dpm_xl.ast.ml_generation import MLGeneration
from dpmcore.dpm_xl.ast.nodes import (
    Constant,
    CountSetOp,
    IntersectSetOp,
    Set,
    SetdiffOp,
    SetOfOp,
    SubstrOp,
    SymdiffOp,
    UnionSetOp,
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
