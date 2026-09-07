"""``node.left`` is the target cell, not an operand: legacy never creates
a node for it. ``visit_PersistentAssignment`` must match that regardless
of whether the cell resolves in ``extract_operand_data``.
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from dpmcore.dpm_xl.ast.ml_generation import MLGeneration
from dpmcore.dpm_xl.ast.nodes import (
    Constant,
    PersistentAssignment,
    VarID,
    VarRef,
)
from dpmcore.dpm_xl.model_queries import (
    VariableVersionQuery,
    ViewDatapointsQuery,
)
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
    ml_generation, monkeypatch
):
    # The target cell happens to also resolve in the datapoints table (e.g.
    # some other rule in the batch persists it) -- legacy discards it anyway.
    ml_generation.extract_operand_data = MagicMock(return_value=[])
    monkeypatch.setattr(
        ViewDatapointsQuery,
        "get_table_data",
        MagicMock(return_value=pd.DataFrame([{"variable_id": 1}])),
    )

    ml_generation.visit_PersistentAssignment(_persistent_assignment())

    # create_operation_node: once for the assignment itself, once for the
    # right-hand formula. Never for the left-hand target cell.
    assert ml_generation.create_operation_node.call_count == 2
    # The LHS target is resolved straight from the DB, not extract_operand_data.
    assert ml_generation.extract_operand_data.call_count == 1


def test_left_hand_side_never_becomes_a_leaf_when_it_does_not_resolve(
    ml_generation, monkeypatch
):
    ml_generation.extract_operand_data = MagicMock(return_value=[])
    monkeypatch.setattr(
        ViewDatapointsQuery,
        "get_table_data",
        MagicMock(return_value=pd.DataFrame(columns=["variable_id"])),
    )

    ml_generation.visit_PersistentAssignment(_persistent_assignment())

    assert ml_generation.create_operation_node.call_count == 2
    ml_generation.session.get.assert_not_called()


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


def test_var_id_left_hand_side_sets_output_variable_id(
    ml_generation, monkeypatch
):
    node = _persistent_assignment()  # left is {tFND, r0010, c0010}
    ml_generation.extract_operand_data = MagicMock(return_value=[])
    get_table_data = MagicMock(return_value=pd.DataFrame([{"variable_id": 7}]))
    monkeypatch.setattr(ViewDatapointsQuery, "get_table_data", get_table_data)

    ml_generation.visit_PersistentAssignment(node)

    get_table_data.assert_called_once_with(
        ml_generation.session, "tFND", ["r0010"], ["c0010"], None, None
    )
    ml_generation.session.get.assert_called_once_with(OperationVersion, 99)
    assert ml_generation.session.get.return_value.output_variable_id == 7


def test_var_id_left_hand_side_that_does_not_resolve_leaves_output_variable_untouched(
    ml_generation, monkeypatch
):
    ml_generation.extract_operand_data = MagicMock(return_value=[])
    monkeypatch.setattr(
        ViewDatapointsQuery,
        "get_table_data",
        MagicMock(return_value=pd.DataFrame(columns=["variable_id"])),
    )

    ml_generation.visit_PersistentAssignment(_persistent_assignment())

    ml_generation.session.get.assert_not_called()


def test_var_id_left_hand_side_grey_cell_leaves_output_variable_untouched(
    ml_generation, monkeypatch
):
    # A grey target upcasts the variable_id column to float64 and reads back as NaN.
    ml_generation.extract_operand_data = MagicMock(return_value=[])
    monkeypatch.setattr(
        ViewDatapointsQuery,
        "get_table_data",
        MagicMock(return_value=pd.DataFrame([{"variable_id": float("nan")}])),
    )

    ml_generation.visit_PersistentAssignment(_persistent_assignment())

    ml_generation.session.get.assert_not_called()


def test_target_without_variable_or_table_leaves_output_variable_untouched(
    ml_generation,
):
    node = PersistentAssignment(
        left=Constant(
            type_="Integer", value=1
        ),  # neither `variable` nor `table`
        op=":=",
        right=_persistent_assignment().right,
    )
    ml_generation.extract_operand_data = MagicMock(return_value=[])

    ml_generation.visit_PersistentAssignment(node)

    ml_generation.session.get.assert_not_called()


def test_missing_operation_version_row_does_not_raise(
    ml_generation, monkeypatch
):
    monkeypatch.setattr(
        VariableVersionQuery,
        "get_variable_id",
        lambda session, value, release_id: [42],
    )
    ml_generation.extract_operand_data = MagicMock(return_value=[])
    ml_generation.session.get = MagicMock(return_value=None)
    node = PersistentAssignment(
        left=VarRef(variable="t1"),
        op=":=",
        right=_persistent_assignment().right,
    )

    ml_generation.visit_PersistentAssignment(node)

    ml_generation.session.get.assert_called_once_with(OperationVersion, 99)


def test_scripting_mode_never_touches_output_variable(ml_generation):
    # Scripting mode must not dirty a real OperationVersion row
    ml_generation.is_scripting = True
    ml_generation.extract_operand_data = MagicMock(return_value=[])

    ml_generation.visit_PersistentAssignment(_persistent_assignment())

    # Only the right-hand formula call; the left-hand resolution is skipped
    assert ml_generation.extract_operand_data.call_count == 1
    ml_generation.session.get.assert_not_called()
