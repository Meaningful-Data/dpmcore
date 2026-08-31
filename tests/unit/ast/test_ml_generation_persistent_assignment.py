"""``node.left`` is the target cell, not an operand: legacy never creates
a node for it. ``visit_PersistentAssignment`` must match that regardless
of whether the cell resolves in ``extract_operand_data``.
"""

from unittest.mock import MagicMock

import pytest

from dpmcore.dpm_xl.ast.ml_generation import MLGeneration
from dpmcore.dpm_xl.ast.nodes import PersistentAssignment, VarID, VarRef
from dpmcore.dpm_xl.model_queries import VariableVersionQuery
from dpmcore.orm.operations import OperationNode, OperationVersion


@pytest.fixture
def ml_generation():
    ml = MLGeneration.__new__(MLGeneration)
    ml.session = MagicMock()
    ml.op_version_id = 99
    ml.is_scripting = False
    ml.data = None
    ml.release_id = None
    ml.create_operation_node = MagicMock(
        side_effect=lambda n, is_leaf=False: OperationNode()
    )
    return ml


def _persistent_assignment():
    target = VarID(
        table="tFND",
        rows=["r0010"],
        cols=["c0010"],
        sheets=None,
        interval=None,
        default=None,
    )
    formula = VarID(
        table="tFND",
        rows=["r0020"],
        cols=["c0010"],
        sheets=None,
        interval=None,
        default=None,
    )
    return PersistentAssignment(left=target, op="<-", right=formula)


def test_left_hand_side_never_becomes_a_leaf_even_when_it_resolves(
    ml_generation,
):
    # The target cell happens to also resolve in extract_operand_data (e.g.
    # some other rule in the batch reads it) -- legacy discards it anyway.
    ml_generation.extract_operand_data = MagicMock(
        return_value=[
            {
                "x": None,
                "y": None,
                "z": None,
                "variable_id": 1,
                "cell_id": 7,
                "row_code": "r0010",
                "column_code": "c0010",
                "sheet_code": None,
            },
        ]
    )

    ml_generation.visit_PersistentAssignment(_persistent_assignment())

    # create_operation_node: once for the assignment itself, once for the
    # right-hand formula. Never for the left-hand target cell.
    assert ml_generation.create_operation_node.call_count == 2
    # Once for the RHS formula, once to resolve the LHS target's variable_id.
    assert ml_generation.extract_operand_data.call_count == 2


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


# ---------------------------------------------------------------------------
# Resolving OperationVersion.output_variable_id from the left-hand target
# ---------------------------------------------------------------------------


def test_var_ref_left_hand_side_sets_output_variable_id(
    ml_generation, monkeypatch
):
    monkeypatch.setattr(
        VariableVersionQuery,
        "get_variable_id",
        lambda session, value, release_id: [42] if value == "t1" else None,
    )
    ml_generation.extract_operand_data = MagicMock(return_value=[])
    node = PersistentAssignment(
        left=VarRef(variable="t1"),
        op=":=",
        right=_persistent_assignment().right,
    )

    ml_generation.visit_PersistentAssignment(node)

    ml_generation.session.get.assert_called_once_with(OperationVersion, 99)
    assert ml_generation.session.get.return_value.output_variable_id == 42


def test_var_id_left_hand_side_sets_output_variable_id(ml_generation):
    node = _persistent_assignment()  # left is {tFND, r0010, c0010}

    def extract_operand_data(table, rows, cols, sheets):
        if rows == ["r0010"]:
            return [{"variable_id": 7, "cell_id": 1}]
        return []

    ml_generation.extract_operand_data = MagicMock(
        side_effect=extract_operand_data
    )

    ml_generation.visit_PersistentAssignment(node)

    ml_generation.session.get.assert_called_once_with(OperationVersion, 99)
    assert ml_generation.session.get.return_value.output_variable_id == 7


def test_var_id_left_hand_side_that_does_not_resolve_leaves_output_variable_untouched(
    ml_generation,
):
    ml_generation.extract_operand_data = MagicMock(return_value=[])

    ml_generation.visit_PersistentAssignment(_persistent_assignment())

    ml_generation.session.get.assert_not_called()


def test_scripting_mode_never_touches_output_variable(ml_generation):
    # Scripting mode must not dirty a real OperationVersion row
    ml_generation.is_scripting = True
    ml_generation.extract_operand_data = MagicMock(return_value=[])

    ml_generation.visit_PersistentAssignment(_persistent_assignment())

    # Only the right-hand formula call; the left-hand resolution is skipped
    assert ml_generation.extract_operand_data.call_count == 1
    ml_generation.session.get.assert_not_called()


def test_var_id_left_hand_side_without_data_degrades_to_unresolved(
    ml_generation,
):
    # A RuntimeError from extract_operand_data must not propagate
    def extract_operand_data(table, rows, cols, sheets):
        if rows == ["r0010"]:  # the left-hand target
            raise RuntimeError("extract_operand_data requires data")
        return []

    ml_generation.extract_operand_data = MagicMock(
        side_effect=extract_operand_data
    )

    ml_generation.visit_PersistentAssignment(_persistent_assignment())

    ml_generation.session.get.assert_not_called()
