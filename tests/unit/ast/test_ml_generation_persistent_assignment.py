"""``node.left`` is the target cell, not an operand: legacy never creates
a node for it. ``visit_PersistentAssignment`` must match that regardless
of whether the cell resolves in ``extract_operand_data``.
"""

from unittest.mock import MagicMock

import pytest

from dpmcore.dpm_xl.ast.ml_generation import MLGeneration
from dpmcore.dpm_xl.ast.nodes import PersistentAssignment, VarID
from dpmcore.orm.operations import OperationNode


@pytest.fixture
def ml_generation():
    ml = MLGeneration.__new__(MLGeneration)
    ml.session = MagicMock()
    ml.op_version_id = 99
    ml.is_scripting = False
    ml.data = None
    ml.create_operation_node = MagicMock(
        side_effect=lambda n, is_leaf=False: OperationNode()
    )
    return ml


def _persistent_assignment():
    target = VarID(
        table="tFND", rows=["r0010"], cols=["c0010"], sheets=None,
        interval=None, default=None,
    )
    formula = VarID(
        table="tFND", rows=["r0020"], cols=["c0010"], sheets=None,
        interval=None, default=None,
    )
    return PersistentAssignment(left=target, op="<-", right=formula)


def test_left_hand_side_never_becomes_a_leaf_even_when_it_resolves(
    ml_generation,
):
    # The target cell happens to also resolve in extract_operand_data (e.g.
    # some other rule in the batch reads it) -- legacy discards it anyway.
    ml_generation.extract_operand_data = MagicMock(
        return_value=[
            {"x": None, "y": None, "z": None, "variable_id": 1, "cell_id": 7,
             "row_code": "r0010", "column_code": "c0010", "sheet_code": None},
        ]
    )

    ml_generation.visit_PersistentAssignment(_persistent_assignment())

    # create_operation_node: once for the assignment itself, once for the
    # right-hand formula. Never for the left-hand target cell.
    assert ml_generation.create_operation_node.call_count == 2
    ml_generation.extract_operand_data.assert_called_once()
    right_call_table = ml_generation.extract_operand_data.call_args[0][0]
    assert right_call_table == "tFND"


def test_left_hand_side_never_becomes_a_leaf_when_it_does_not_resolve(
    ml_generation,
):
    ml_generation.extract_operand_data = MagicMock(return_value=[])

    ml_generation.visit_PersistentAssignment(_persistent_assignment())

    assert ml_generation.create_operation_node.call_count == 2
    assert ml_generation.session.add.call_count == 0


def test_right_hand_side_is_still_visited_and_linked(ml_generation):
    ml_generation.extract_operand_data = MagicMock(return_value=[])

    node = _persistent_assignment()
    ml_generation.visit_PersistentAssignment(node)

    assert node.right.argument == "right"
    assert node.right.parent is not None
