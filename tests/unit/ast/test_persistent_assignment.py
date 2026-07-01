"""Tests for persistent assignment expressions ({sel} <- op).

Covers both cell-reference and var-reference targets as standalone
top-level statements (issue #181) and embedded inside temporary
assignments.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import PersistentAssignment, VarID, VarRef
from dpmcore.services.syntax import SyntaxService

# Syntax validity
VALID_PERSISTENT_ASSIGNMENTS = [
    "{tK_61.00, r0010, c0010} <- {tC_01.00, r0020, c0010}",
    "{tT1, r0010} <- {tT2, r0010}",
    "{tT1, r0010, c0010} <- {tT2, r0010, c0010} * 2",
    "{vFoo} <- {tC_01.00, r0020, c0010}",
    "{v_Z101} <- 1",
    "v1204 := {vFoo} <- {tC_01.00, r0020, c0010}",
]

INVALID_PERSISTENT_ASSIGNMENTS = [
    # RHS only, incomplete expression
    "<- {tC_01.00, r0020, c0010}",
    # literal on LHS, not a valid selection
    "1 <- {tC_01.00, r0020, c0010}",
]


@pytest.fixture(scope="module")
def svc():
    return SyntaxService()


@pytest.mark.parametrize("expression", VALID_PERSISTENT_ASSIGNMENTS)
def test_valid_persistent_assignment_accepted(expression, svc):
    assert svc.is_valid(expression), f"Expected valid: {expression!r}"


@pytest.mark.parametrize("expression", INVALID_PERSISTENT_ASSIGNMENTS)
def test_invalid_persistent_assignment_rejected(expression, svc):
    assert not svc.is_valid(expression), f"Expected invalid: {expression!r}"


# AST shape
def test_cell_ref_lhs_produces_persistent_assignment_with_varid(svc):
    start = svc.parse("{tK_61.00, r0010, c0010} <- {tC_01.00, r0020, c0010}")
    node = start.children[0]
    assert isinstance(node, PersistentAssignment)
    assert node.op == "<-"
    assert isinstance(node.left, VarID)
    assert node.left.table == "K_61.00"


def test_var_ref_lhs_produces_persistent_assignment_with_varref(svc):
    start = svc.parse("{vFoo} <- {tC_01.00, r0020, c0010}")
    node = start.children[0]
    assert isinstance(node, PersistentAssignment)
    assert node.op == "<-"
    assert isinstance(node.left, VarRef)
    assert node.left.variable == "Foo"
