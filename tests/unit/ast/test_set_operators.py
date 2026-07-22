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
    AggregationOp,
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
    assert node.component is None
    j = node.toJSON()
    assert j["class_name"] == "SetOfOp"
    assert "operand" in j
    assert j["component"] is None


def test_set_of_op_node_with_component():
    operand = Constant(type_="Integer", value=1)
    node = SetOfOp(operand=operand, component="INC")
    assert node.op == "set_of"
    assert node.operand is operand
    assert node.component == "INC"
    j = node.toJSON()
    assert j["class_name"] == "SetOfOp"
    assert j["component"] == "INC"


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
    # set_of alias without underscore
    "{tT1, r001} in setof({tT2, r001-010})",
    # set_of with component projection (2-arg form)
    "{tT1, r001} in set_of({tT2, r001-010}, INC)",
    # setof with component projection (2-arg form, no underscore)
    "{tT1, r001} in setof({tT2, r001-010}, INC)",
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
    assert node.right.component is None


def test_setof_alias_produces_same_ast_as_set_of():
    """``setof`` (no underscore) is lexed as the same ``SET_OF`` token."""
    with_underscore = SyntaxService().parse("set_of({tT1, r001-010})")
    without_underscore = SyntaxService().parse("setof({tT1, r001-010})")
    node_a = with_underscore.children[0]
    node_b = without_underscore.children[0]
    assert isinstance(node_a, SetOfOp)
    assert isinstance(node_b, SetOfOp)
    assert node_a.component is None
    assert node_b.component is None


def test_set_of_with_component_projection():
    """``set_of(recordset, component)`` produces a SetOfOp with the
    component captured on the node.
    """
    ast = SyntaxService().parse("set_of({tT2, r001-010}, INC)")
    node = ast.children[0]
    assert isinstance(node, SetOfOp)
    assert node.component == "INC"


def test_setof_alias_with_component_projection():
    """The no-underscore spelling accepts the component projection too."""
    ast = SyntaxService().parse("setof({tT2, r001-010}, INC)")
    node = ast.children[0]
    assert isinstance(node, SetOfOp)
    assert node.component == "INC"


def test_setof_component_with_escaped_identifier():
    """A backtick-escaped component code (used for reserved words like
    ``f``, the fact component) is stripped and stored bare on the node,
    mirroring how ``keyNames`` unwraps escaped identifiers elsewhere.
    """
    ast = SyntaxService().parse("setof({tT2, r001-010}, `f`)")
    node = ast.children[0]
    assert isinstance(node, SetOfOp)
    assert node.component == "f"


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
    assert isinstance(node, AggregationOp)
    assert node.op == "count"
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


# ---------------------------------------------------------------------------
# ASTToJSONVisitor: MR !74 set operators must serialize as first-class nodes
# with their ``class_name`` preserved. Previously the visitor lacked handlers
# and these nodes were silently dropped from the enriched AST payload.
# ---------------------------------------------------------------------------

from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor  # noqa: E402


def _serialize_expr(expression: str) -> dict:
    ast = SyntaxService().parse(expression)
    result = ASTToJSONVisitor().visit(ast)
    assert isinstance(result, dict)
    return result["children"][0]


def test_ast_to_json_serializes_empty_set_literal():
    node = _serialize_expr("{tT1, r001} in {}")
    assert node["class_name"] == "BinOp"
    assert node["op"] == "in"
    right = node["right"]
    assert right["class_name"] == "Set"
    assert right["children"] == []


def test_ast_to_json_serializes_non_empty_set_literal():
    node = _serialize_expr("{tT1, r001} in {1, 2, 3}")
    right = node["right"]
    assert right["class_name"] == "Set"
    assert len(right["children"]) == 3
    for child, expected in zip(right["children"], [1, 2, 3], strict=True):
        assert child["class_name"] == "Constant"
        assert child["value"] == expected


def test_ast_to_json_serializes_set_of_op():
    node = _serialize_expr("{tT1, r001} in set_of({tT2, r001-010})")
    right = node["right"]
    assert right["class_name"] == "SetOfOp"
    assert right["op"] == "set_of"
    assert isinstance(right["operand"], dict)


def test_ast_to_json_serializes_union_variadic():
    node = _serialize_expr("{tT1, r001} in union({1, 2}, {3, 4}, {5, 6})")
    right = node["right"]
    assert right["class_name"] == "UnionSetOp"
    assert right["op"] == "union"
    assert len(right["operands"]) == 3
    for operand in right["operands"]:
        assert operand["class_name"] == "Set"


def test_ast_to_json_serializes_intersect():
    node = _serialize_expr("{tT1, r001} in intersect({1, 2, 3}, {2, 3, 4})")
    right = node["right"]
    assert right["class_name"] == "IntersectSetOp"
    assert right["op"] == "intersect"
    assert len(right["operands"]) == 2


def test_ast_to_json_serializes_setdiff():
    node = _serialize_expr("{tT1, r001} in setdiff({1, 2, 3}, {3})")
    right = node["right"]
    assert right["class_name"] == "SetdiffOp"
    assert right["op"] == "setdiff"
    assert right["left"]["class_name"] == "Set"
    assert right["right"]["class_name"] == "Set"


def test_ast_to_json_serializes_symdiff():
    node = _serialize_expr("{tT1, r001} in symdiff({1, 2}, {2, 3})")
    right = node["right"]
    assert right["class_name"] == "SymdiffOp"
    assert right["op"] == "symdiff"
    assert right["left"]["class_name"] == "Set"
    assert right["right"]["class_name"] == "Set"


def test_ast_to_json_preserves_nested_set_operators():
    """A nested ``setdiff(union(...), ...)`` expression must round-trip with
    every intermediate ``class_name`` intact — not just the outermost node.
    """
    node = _serialize_expr(
        "{tT1, r001} in setdiff(union({1, 2}, {3, 4}), {5})"
    )
    outer = node["right"]
    assert outer["class_name"] == "SetdiffOp"
    inner = outer["left"]
    assert inner["class_name"] == "UnionSetOp"
    assert len(inner["operands"]) == 2
