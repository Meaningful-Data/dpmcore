"""Verify visit_SubstrOp serializes start/length parameters distinctly"""

from unittest.mock import MagicMock

import pytest

from dpmcore.dpm_xl.ast.ml_generation import MLGeneration
from dpmcore.dpm_xl.ast.nodes import Constant, SubstrOp


@pytest.fixture
def ml_generation(monkeypatch):
    monkeypatch.setattr(MLGeneration, "__init__", lambda self, **kwargs: None)
    instance = MLGeneration()
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
