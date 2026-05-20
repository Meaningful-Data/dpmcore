"""Tests for time_shift numberPeriods accepting integer expressions."""

import pytest

from dpmcore.dpm_xl.ast.nodes import Constant, TimeShiftOp
from dpmcore.services.syntax import SyntaxService

VALID_LITERAL_FORMS = [
    "time_shift({tT1}, Q, 5)",
    "time_shift({tT1}, Q, 60)",
    "time_shift({tT1}, Q, 1, FACTO)",
]

VALID_EXPRESSION_FORMS = [
    "time_shift({tT1}, Q, -5)",
    "time_shift({tT1}, Q, 5 * 12)",
    "time_shift({tT1}, Q, (5 + 7))",
    "time_shift({tT1}, Q, 5 * 12, FACTO)",
    "time_shift({tT1}, Q, -1, myComp)",
]


@pytest.mark.parametrize("source", VALID_LITERAL_FORMS)
def test_literal_integer_still_valid(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", VALID_EXPRESSION_FORMS)
def test_integer_expression_is_valid(source):
    assert SyntaxService().is_valid(source)


def test_literal_shift_produces_constant_ast_node():
    ast = SyntaxService().parse("time_shift({tT1}, Q, 5)")
    node = ast.children[0]
    assert isinstance(node, TimeShiftOp)
    assert isinstance(node.shift_number, Constant)
    assert node.shift_number.type == "Integer"
    assert node.shift_number.value == 5


def test_negative_shift_produces_unary_ast_node():
    ast = SyntaxService().parse("time_shift({tT1}, Q, -5)")
    node = ast.children[0]
    assert isinstance(node, TimeShiftOp)
    assert node.shift_number is not None


def test_arithmetic_shift_produces_ast_node():
    ast = SyntaxService().parse("time_shift({tT1}, Q, 5 * 12)")
    node = ast.children[0]
    assert isinstance(node, TimeShiftOp)
    assert node.shift_number is not None
    assert not isinstance(node.shift_number, str)
