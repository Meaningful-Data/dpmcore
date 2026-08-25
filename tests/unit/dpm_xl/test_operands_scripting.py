"""A ``TemporaryAssignment`` LHS (e.g. ``t1``) is a batch-local scratch name,
not a persisted ``Operation.Code``: ``{oCODE}`` must resolve against other
rules declared earlier in the same batch, no DB round trip required.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.errors import SemanticError
from dpmcore.services.syntax import SyntaxService


def _empty_operations_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["OperationVID", "Code"])


def _check(expression: str, is_scripting: bool) -> OperandsChecking:
    ast = SyntaxService().parse(expression)
    with patch(
        "dpmcore.dpm_xl.ast.operands.OperationQuery.get_operations_from_codes",
        return_value=_empty_operations_df(),
    ):
        return OperandsChecking(
            session=MagicMock(),
            expression=expression,
            ast=ast,
            release_id=None,
            is_scripting=is_scripting,
        )


def test_operation_ref_is_rejected_outside_scripting_mode():
    with pytest.raises(SemanticError) as exc_info:
        _check("t2 := {ot1} + 1;", is_scripting=False)
    assert exc_info.value.code == "6-2"


def test_batch_local_scratch_name_needs_no_persisted_operation_code():
    # t1 is not (and need not be) a real Operation.Code.
    oc = _check("t1 := 1;", is_scripting=True)
    assert oc.operations == ["t1"]


def test_operation_ref_resolves_against_a_batch_local_name():
    oc = _check("t1 := 1; t2 := {ot1} + 1;", is_scripting=True)
    assert oc.operations == ["t1", "t2"]


def test_operation_ref_to_an_undeclared_name_still_raises():
    with pytest.raises(SemanticError) as exc_info:
        _check("t2 := {otX} + 1;", is_scripting=True)
    assert exc_info.value.code == "1-8"


def test_operation_ref_cannot_forward_reference_a_later_name():
    # t2 is declared after t1, so it isn't a valid reference yet.
    with pytest.raises(SemanticError) as exc_info:
        _check("t1 := {ot2} + 1; t2 := 1;", is_scripting=True)
    assert exc_info.value.code == "1-8"


def test_check_operations_enriches_operations_data_for_a_real_persisted_code():
    expression = "t1 := 1;"
    ast = SyntaxService().parse(expression)
    real_match = pd.DataFrame({"OperationVID": [42], "Code": ["t1"]})
    with patch(
        "dpmcore.dpm_xl.ast.operands.OperationQuery.get_operations_from_codes",
        return_value=real_match,
    ):
        oc = OperandsChecking(
            session=MagicMock(),
            expression=expression,
            ast=ast,
            release_id=None,
            is_scripting=True,
        )
    assert oc.operations_data is not None
    assert oc.operations_data["OperationVID"].tolist() == [42]
