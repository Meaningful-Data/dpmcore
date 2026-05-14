"""Tests for the date literal grammar contract.

The only accepted is DATE_LITERAL (#YYYY-MM-DD#).
Any other form must be rejected by the parser.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import Constant
from dpmcore.services.syntax import SyntaxService


VALID_DATE_LITERALS = [
    "#2023-01-01#",
    "#2023-12-31#",
    "#2023-01-01T12:30:00#",
]

INVALID_HASH_LITERALS = [
    "#2023-01-01/2023-12-31#",  # interval: DATE/DATE
    "#2023A#",                  # time period: annual
    "#2023Q3#",                 # time period: quarterly
    "#2023M06#",                # time period: monthly
    "#2023W12#",                # time period: weekly
    "#2023D045#",               # time period: daily
    "#not-a-date#",             # completely invalid
]


@pytest.mark.parametrize("literal", VALID_DATE_LITERALS)
def test_valid_date_literal(literal):
    """Only #YYYY-MM-DD# (and its datetime variant) is accepted."""
    assert SyntaxService().is_valid(f"isnull({literal})")


@pytest.mark.parametrize("literal", VALID_DATE_LITERALS)
def test_date_literal_produces_date_constant(literal):
    """DATE_LITERAL builds a Constant node with type Date."""
    ast = SyntaxService().parse(f"isnull({literal})")
    operand = ast.children[0].operand
    assert isinstance(operand, Constant)
    assert operand.type == "Date"
    assert operand.value == literal.strip("#")


@pytest.mark.parametrize("literal", INVALID_HASH_LITERALS)
def test_other_hash_forms_are_invalid(literal):
    """Any #...# form other than DATE_LITERAL is rejected by the parser."""
    assert not SyntaxService().is_valid(f"isnull({literal})")
