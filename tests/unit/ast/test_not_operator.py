"""Tests for ``not`` as a prefix unary operator.

All three syntactic forms are equivalent and produce the same AST:

    not expr       (no parentheses)
    not(expr)      (parentheses, no space)
    not (expr)     (parentheses with space)

"""

import pytest

from dpmcore.dpm_xl.ast.nodes import BinOp, Constant, UnaryOp
from dpmcore.services.syntax import SyntaxService

VALID_NOT_FORMS = [
    "not true",
    "not(true)",
    "not (true)",
]

NOT_BINARY_FORMS = [
    ("not true and false", "and"),
    ("not(true) and false", "and"),
    ("not (true) and false", "and"),
    ("not true or false", "or"),
    ("not(true) or false", "or"),
    ("not (true) or false", "or"),
]

EXPLICIT_PARENS_FORMS = [
    ("not(true and false)", "and"),
    ("not(true or false)", "or"),
]


@pytest.mark.parametrize("source", VALID_NOT_FORMS)
def test_all_valid_forms_are_valid(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", VALID_NOT_FORMS)
def test_all_valid_forms_produce_unary_not_of_true(source):
    start = SyntaxService().parse(source)
    expr = start.children[0]
    assert isinstance(expr, UnaryOp)
    assert expr.op == "not"
    assert isinstance(expr.operand, Constant)
    assert expr.operand.type == "Boolean"
    assert expr.operand.value is True


@pytest.mark.parametrize(("source", "operator"), NOT_BINARY_FORMS)
def test_not_has_higher_precedence_than_binary_ops(source, operator):
    start = SyntaxService().parse(source)
    expr = start.children[0]
    assert isinstance(expr, BinOp)
    assert expr.op == operator
    assert isinstance(expr.left, UnaryOp)
    assert expr.left.op == "not"
    assert isinstance(expr.left.operand, Constant)
    assert expr.left.operand.value is True
    assert isinstance(expr.right, Constant)
    assert expr.right.value is False


@pytest.mark.parametrize(("source", "operator"), EXPLICIT_PARENS_FORMS)
def test_explicit_parentheses_bind_before_not(source, operator):
    start = SyntaxService().parse(source)
    expr = start.children[0]
    assert isinstance(expr, UnaryOp)
    assert expr.op == "not"
    assert isinstance(expr.operand, BinOp)
    assert expr.operand.op == operator
    assert isinstance(expr.operand.left, Constant)
    assert expr.operand.left.value is True
    assert isinstance(expr.operand.right, Constant)
    assert expr.operand.right.value is False
