"""Tests for the INTEGER_LITERAL grammar contract.

Negative INTEGER_LITERAL tokens are written wrapped in parentheses,
e.g. '(-1)' (dpm_xlLexer.g4: INTEGER_LITERAL: DIGITS0_9+ | LPAREN MINUS
DIGITS0_9+ RPAREN). Both forms must parse to the same Constant value.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import Constant
from dpmcore.services.syntax import SyntaxService

PLAIN_AND_PARENTHESIZED = [
    ("1", 1),
    ("(-1)", -1),
    ("23", 23),
    ("(-23)", -23),
    ("0", 0),
    ("(-0)", 0),
]


@pytest.mark.parametrize(("literal", "value"), PLAIN_AND_PARENTHESIZED)
def test_integer_literal_produces_constant(literal, value):
    ast = SyntaxService().parse(f"isnull({literal});")
    operand = ast.children[0].operand
    assert isinstance(operand, Constant)
    assert operand.type == "Integer"
    assert operand.value == value


NEGATIVE_NUMBERS = [
    ("(-3.5)", "Number", -3.5),
    ("(-0.5%)", "Number", -0.005),
    ("-3", "Integer", -3),
    ("-3.5", "Number", -3.5),
    ("-1%", "Number", -0.01),
]


@pytest.mark.parametrize(("literal", "type_", "value"), NEGATIVE_NUMBERS)
def test_negative_number_in_set_produces_constant(literal, type_, value):
    ast = SyntaxService().parse(f"{{tT1, r0010}} in {{{literal}}}")
    element = ast.children[0].right.children[0]
    assert isinstance(element, Constant)
    assert element.type == type_
    assert element.value == value


def test_bare_negative_default_produces_constant():
    ast = SyntaxService().parse("{tT1, r0010, default: -1}")
    assert ast.children[0].default.value == -1
