"""Tests for DPM-XL set operators: tokens, AST nodes, and parser."""

from dpmcore.dpm_xl.utils import tokens


def test_set_operator_token_constants_exist():
    assert tokens.SET_OF == "set_of"
    assert tokens.UNION == "union"
    assert tokens.INTERSECT == "intersect"
    assert tokens.SETDIFF == "setdiff"
    assert tokens.SYMDIFF == "symdiff"


# ---------------------------------------------------------------------------
# AST node tests
# ---------------------------------------------------------------------------

from dpmcore.dpm_xl.ast.nodes import (
    BinOp,
    Constant,
    CountSetOp,
    IntersectSetOp,
    Set,
    SetdiffOp,
    SetOfOp,
    SymdiffOp,
    UnionSetOp,
)


def test_set_of_op_node():
    operand = Constant(type_="Integer", value=1)
    node = SetOfOp(operand=operand)
    assert node.op == "set_of"
    assert node.operand is operand
    j = node.toJSON()
    assert j["class_name"] == "SetOfOp"
    assert "operand" in j


def test_union_set_op_node():
    s1 = Set(children=[])
    s2 = Set(children=[])
    node = UnionSetOp(operands=[s1, s2])
    assert node.op == "union"
    assert len(node.operands) == 2
    j = node.toJSON()
    assert j["class_name"] == "UnionSetOp"
    assert "operands" in j


def test_intersect_set_op_node():
    s1 = Set(children=[])
    s2 = Set(children=[])
    node = IntersectSetOp(operands=[s1, s2])
    assert node.op == "intersect"
    j = node.toJSON()
    assert j["class_name"] == "IntersectSetOp"


def test_setdiff_op_node():
    s1 = Set(children=[])
    s2 = Set(children=[])
    node = SetdiffOp(left=s1, right=s2)
    assert node.op == "setdiff"
    assert node.left is s1
    assert node.right is s2
    j = node.toJSON()
    assert j["class_name"] == "SetdiffOp"
    assert "left" in j
    assert "right" in j


def test_symdiff_op_node():
    s1 = Set(children=[])
    s2 = Set(children=[])
    node = SymdiffOp(left=s1, right=s2)
    assert node.op == "symdiff"
    j = node.toJSON()
    assert j["class_name"] == "SymdiffOp"


def test_count_set_op_node():
    s = Set(children=[])
    node = CountSetOp(operand=s)
    assert node.op == "count"
    assert node.operand is s
    j = node.toJSON()
    assert j["class_name"] == "CountSetOp"
    assert "operand" in j


# ---------------------------------------------------------------------------
# Parser / syntax tests
# ---------------------------------------------------------------------------

import pytest

from dpmcore.services.syntax import SyntaxService

VALID_IN_EXPRESSIONS = [
    # Existing literal set — must still work
    "{tT1, r001} in {1, 2, 3}",
    # set_of
    "{tT1, r001} in set_of({tT2, r001-010})",
    # union (2 operands)
    "{tT1, r001} in union({1, 2}, {3, 4})",
    # union (3 operands)
    "{tT1, r001} in union({1}, {2}, {3})",
    # intersect
    "{tT1, r001} in intersect({1, 2, 3}, {2, 3, 4})",
    # setdiff
    "{tT1, r001} in setdiff({1, 2, 3}, {3, 4})",
    # symdiff
    "{tT1, r001} in symdiff({1, 2, 3}, {3, 4, 5})",
    # nested
    "{tT1, r001} in union(setdiff({1, 2, 3}, {3}), {4, 5})",
    # count with literal set
    "count({1, 2, 3}) = 3",
    # count with set_of
    "count(set_of({tT1, r001-010})) > 0",
    # count with union
    "count(union({1, 2}, {3, 4})) = 4",
]

INVALID_EXPRESSIONS = [
    # union with only one operand (needs 2+)
    "{tT1, r001} in union({1, 2})",
    # setdiff with three operands (binary only)
    "{tT1, r001} in setdiff({1}, {2}, {3})",
    # symdiff with three operands (binary only)
    "{tT1, r001} in symdiff({1}, {2}, {3})",
]


@pytest.mark.parametrize("source", VALID_IN_EXPRESSIONS)
def test_set_operator_expressions_parse(source):
    assert SyntaxService().is_valid(source), f"Expected valid: {source}"


@pytest.mark.parametrize("source", INVALID_EXPRESSIONS)
def test_invalid_set_operator_expressions_rejected(source):
    assert not SyntaxService().is_valid(source), f"Expected invalid: {source}"


def test_in_set_of_produces_bin_op_with_set_of_op():
    ast = SyntaxService().parse("{tT1, r001} in set_of({tT2, r001-010})")
    node = ast.children[0]
    assert isinstance(node, BinOp)
    assert node.op == "in"
    assert isinstance(node.right, SetOfOp)


def test_in_union_produces_bin_op_with_union_set_op():
    ast = SyntaxService().parse("{tT1, r001} in union({1, 2}, {3, 4})")
    node = ast.children[0]
    assert isinstance(node, BinOp)
    assert isinstance(node.right, UnionSetOp)
    assert len(node.right.operands) == 2


def test_in_intersect_produces_bin_op_with_intersect_set_op():
    ast = SyntaxService().parse(
        "{tT1, r001} in intersect({1, 2, 3}, {2, 3, 4})"
    )
    node = ast.children[0]
    assert isinstance(node, BinOp)
    assert isinstance(node.right, IntersectSetOp)


def test_in_setdiff_produces_bin_op_with_setdiff_op():
    ast = SyntaxService().parse("{tT1, r001} in setdiff({1, 2, 3}, {3, 4})")
    node = ast.children[0]
    assert isinstance(node, BinOp)
    assert isinstance(node.right, SetdiffOp)


def test_in_symdiff_produces_bin_op_with_symdiff_op():
    ast = SyntaxService().parse("{tT1, r001} in symdiff({1, 2, 3}, {3, 4, 5})")
    node = ast.children[0]
    assert isinstance(node, BinOp)
    assert isinstance(node.right, SymdiffOp)


def test_count_set_of_produces_count_set_op():
    ast = SyntaxService().parse("count(set_of({tT1, r001-010}))")
    node = ast.children[0]
    assert isinstance(node, CountSetOp)
    assert isinstance(node.operand, SetOfOp)


def test_union_with_three_operands():
    ast = SyntaxService().parse("{tT1, r001} in union({1}, {2}, {3})")
    node = ast.children[0]
    assert isinstance(node.right, UnionSetOp)
    assert len(node.right.operands) == 3


def test_nested_set_expression():
    ast = SyntaxService().parse(
        "{tT1, r001} in union(setdiff({1, 2, 3}, {3}), {4, 5})"
    )
    node = ast.children[0]
    assert isinstance(node.right, UnionSetOp)
    assert isinstance(node.right.operands[0], SetdiffOp)


def test_existing_literal_set_still_works():
    ast = SyntaxService().parse("{tT1, r001} in {1, 2, 3}")
    node = ast.children[0]
    assert isinstance(node, BinOp)
    assert node.op == "in"
