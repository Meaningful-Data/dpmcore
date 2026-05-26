"""Tests for operation reference as head of cellAddress.

{oOp1, r010} should parse as a VarID selecting row 010 from the result
of operation Op1, parallel to {tT1, r010} for table references.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import VarID
from dpmcore.services.syntax import SyntaxService

VALID_OP_CELL_FORMS = [
    "{oOp1, r010}",
    "{oOp1, c0010}",
    "{oOp1, r010, c0010}",
    "{oOp1, r010, c0010, s001}",
]

VALID_EXISTING_FORMS = [
    "{oOp1}",
    "{tT1, r010}",
]


@pytest.mark.parametrize("source", VALID_OP_CELL_FORMS)
def test_operation_cell_address_is_valid(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", VALID_EXISTING_FORMS)
def test_existing_forms_still_valid(source):
    assert SyntaxService().is_valid(source)


def test_operation_cell_address_row_produces_varid():
    ast = SyntaxService().parse("{oOp1, r010}")
    varid = ast.children[0]
    assert isinstance(varid, VarID)
    assert varid.operation == "Op1"
    assert varid.table is None
    assert varid.rows == ["010"]


def test_operation_cell_address_col_produces_varid():
    ast = SyntaxService().parse("{oOp1, c0010}")
    varid = ast.children[0]
    assert isinstance(varid, VarID)
    assert varid.operation == "Op1"
    assert varid.cols == ["0010"]


def test_operation_cell_address_row_and_col_produces_varid():
    ast = SyntaxService().parse("{oOp1, r010, c0010}")
    varid = ast.children[0]
    assert isinstance(varid, VarID)
    assert varid.operation == "Op1"
    assert varid.rows == ["010"]
    assert varid.cols == ["0010"]
