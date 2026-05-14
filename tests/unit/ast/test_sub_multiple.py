"""Tests for the sub clause grammar contract.

The sub clause accepts one or more comma-separated substitutions:
    sub key = value {, key = value}*
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import SubAssignment, SubOp
from dpmcore.services.syntax import SyntaxService

SINGLE_SUB_EXPRESSIONS = [
    '{tT, r010}[sub c0010 = "ES"]',
    "{tT, r010}[sub c0010 = {vMyVar}]",
    "{tT, r010}[sub c0010 = [ns:code]]",
]

MULTIPLE_SUB_EXPRESSIONS = [
    '{tT, r010}[sub c0010 = "ES", c0020 = "FR"]',
    '{tT, r010}[sub c0010 = "ES", c0020 = "FR", c0030 = "DE"]',
]


@pytest.mark.parametrize("expr", SINGLE_SUB_EXPRESSIONS)
def test_single_sub_is_valid(expr):
    """A single substitution is still accepted."""
    assert SyntaxService().is_valid(expr)


@pytest.mark.parametrize("expr", MULTIPLE_SUB_EXPRESSIONS)
def test_multiple_sub_is_valid(expr):
    """Multiple comma-separated substitutions are accepted."""
    assert SyntaxService().is_valid(expr)


def test_single_sub_produces_one_substitution():
    """A single sub builds a SubOp with one SubAssignment."""
    ast = SyntaxService().parse('{tT, r010}[sub c0010 = "ES"]')
    sub_op = ast.children[0]
    assert isinstance(sub_op, SubOp)
    assert len(sub_op.substitutions) == 1
    assert isinstance(sub_op.substitutions[0], SubAssignment)
    assert sub_op.substitutions[0].property_code == "c0010"


def test_multiple_sub_produces_multiple_substitutions():
    """Multiple subs build a SubOp with one SubAssignment per pair."""
    ast = SyntaxService().parse('{tT, r010}[sub c0010 = "ES", c0020 = "FR"]')
    sub_op = ast.children[0]
    assert isinstance(sub_op, SubOp)
    assert len(sub_op.substitutions) == 2
    assert sub_op.substitutions[0].property_code == "c0010"
    assert sub_op.substitutions[1].property_code == "c0020"
