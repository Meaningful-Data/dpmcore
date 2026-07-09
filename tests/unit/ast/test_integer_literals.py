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
