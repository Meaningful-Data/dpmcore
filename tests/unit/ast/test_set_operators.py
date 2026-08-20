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


def test_union_set_op_node():
    s1 = Set(children=[])
    s2 = Set(children=[])
    node = UnionSetOp(operands=[s1, s2])
    assert node.op == "union"
    assert node.operands == [s1, s2]


def test_intersect_set_op_node():
    s1 = Set(children=[])
    s2 = Set(children=[])
    node = IntersectSetOp(operands=[s1, s2])
    assert node.op == "intersect"
    assert node.operands == [s1, s2]


def test_setdiff_op_node():
    s1 = Set(children=[])
    s2 = Set(children=[])
    node = SetdiffOp(left=s1, right=s2)
    assert node.op == "setdiff"
    assert node.left is s1
    assert node.right is s2


def test_symdiff_op_node():
    s1 = Set(children=[])
    s2 = Set(children=[])
    node = SymdiffOp(left=s1, right=s2)
    assert node.op == "symdiff"
    assert node.left is s1
    assert node.right is s2


def test_count_set_op_node():
    s = Set(children=[])
    node = CountSetOp(operand=s)
    assert node.op == "count"
    assert node.operand is s


def test_set_operator_nodes_define_no_own_to_json():
    """The wire shape lives in ``ASTToJSONVisitor``, nowhere else.

    A ``toJSON`` on any of these classes would be a second, divergent
    serialization of the same node that no code path reaches (they are
    ``AST`` subclasses, so ``serialize_ast`` always routes them through
    the visitor), so re-adding one is a bug, not a feature.
    """
    for cls in (
        SetOfOp,
        UnionSetOp,
        IntersectSetOp,
        SetdiffOp,
        SymdiffOp,
        CountSetOp,
    ):
        assert "toJSON" not in vars(cls), f"{cls.__name__} redefines toJSON"


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

from dpmcore.dpm_xl.utils.serialization import (  # noqa: E402
    ASTToJSONVisitor,
    serialize_ast,
)


def _serialize_expr(expression: str) -> dict:
    ast = SyntaxService().parse(expression)
    result = ASTToJSONVisitor().visit(ast)
    assert isinstance(result, dict)
    return result["children"][0]


def _assert_set_op(node: dict, op: str, arity: int) -> list:
    """Assert a node's ``SetOp`` wire shape and return its operands.

    The consumer schema is ``additionalProperties: false``, so the exact
    key set is part of the contract: a stray ``left``/``right``/
    ``operand`` left alongside ``operands`` is a hard rejection
    downstream, not a tolerated extra.
    """
    assert set(node) == {"class_name", "op", "operands"}
    assert node["class_name"] == "SetOp"
    assert node["op"] == op
    assert len(node["operands"]) == arity
    return node["operands"]


def _assert_set_literal(node: dict, values: list) -> None:
    """Assert a serialized ``Set`` literal holds exactly ``values``."""
    assert node["class_name"] == "Set"
    assert [child["value"] for child in node["children"]] == values


def _class_names(node) -> set:
    """Every ``class_name`` in a serialized payload, at any depth."""
    if isinstance(node, dict):
        names = set()
        if "class_name" in node:
            names.add(node["class_name"])
        for value in node.values():
            names |= _class_names(value)
        return names
    if isinstance(node, list):
        names = set()
        for item in node:
            names |= _class_names(item)
        return names
    return set()


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
    ops = _assert_set_op(node["right"], "set_of", 1)
    assert ops[0]["class_name"] == "VarID"


def test_ast_to_json_serializes_union_variadic():
    node = _serialize_expr("{tT1, r001} in union({1, 2}, {3, 4}, {5, 6})")
    ops = _assert_set_op(node["right"], "union", 3)
    expected = [[1, 2], [3, 4], [5, 6]]
    for operand, values in zip(ops, expected, strict=True):
        _assert_set_literal(operand, values)


def test_ast_to_json_serializes_intersect():
    node = _serialize_expr("{tT1, r001} in intersect({1, 2, 3}, {2, 3, 4})")
    ops = _assert_set_op(node["right"], "intersect", 2)
    _assert_set_literal(ops[0], [1, 2, 3])
    _assert_set_literal(ops[1], [2, 3, 4])


def test_ast_to_json_serializes_setdiff():
    """``setdiff`` is not commutative: operands stay left-then-right."""
    node = _serialize_expr("{tT1, r001} in setdiff({1, 2, 3}, {9})")
    ops = _assert_set_op(node["right"], "setdiff", 2)
    _assert_set_literal(ops[0], [1, 2, 3])
    _assert_set_literal(ops[1], [9])


def test_ast_to_json_serializes_symdiff():
    """Operand order and identity are pinned exactly as for ``setdiff``."""
    node = _serialize_expr("{tT1, r001} in symdiff({1, 2}, {8, 9})")
    ops = _assert_set_op(node["right"], "symdiff", 2)
    _assert_set_literal(ops[0], [1, 2])
    _assert_set_literal(ops[1], [8, 9])


def test_ast_to_json_preserves_nested_set_operators():
    """A nested ``setdiff(union(...), ...)`` expression must serialize as
    ``SetOp`` at every level, with the inner operator in first position.
    """
    node = _serialize_expr(
        "{tT1, r001} in setdiff(union({1, 2}, {3, 4}), {5})"
    )
    outer = _assert_set_op(node["right"], "setdiff", 2)
    _assert_set_op(outer[0], "union", 2)
    _assert_set_literal(outer[1], [5])


def test_ast_to_json_emits_no_per_operator_set_class_names():
    """None of the old per-operator names survives, at any depth."""
    node = _serialize_expr(
        "{tT1, r001} in union("
        "set_of({tT2, r001-010}), "
        "intersect({1, 2}, {2, 3}), "
        "setdiff({4, 5}, {5}), "
        "symdiff({6}, {7})"
        ")"
    )
    names = _class_names(node)
    assert names.isdisjoint(
        {
            "SetOfOp",
            "UnionSetOp",
            "IntersectSetOp",
            "SetdiffOp",
            "SymdiffOp",
        }
    )
    assert "SetOp" in names
    # ``Set`` literals are untouched by the collapse.
    assert "Set" in names


# ---------------------------------------------------------------------------
# ``serialize_ast`` is the entry point ``ASTGeneratorService`` builds scripts
# with, and it does more than the visitor: it expands ``with`` scopes first
# and returns the root expression node directly. The shape has to hold there,
# not just under a bare ``ASTToJSONVisitor().visit()``.
# ---------------------------------------------------------------------------


def test_serialize_ast_emits_set_op_at_the_public_entry_point():
    payload = serialize_ast(
        SyntaxService().parse("{tT1, r001} in setdiff({1, 2}, {3})")
    )
    assert payload["class_name"] == "BinOp"
    ops = _assert_set_op(payload["right"], "setdiff", 2)
    _assert_set_literal(ops[0], [1, 2])
    _assert_set_literal(ops[1], [3])


def test_serialize_ast_emits_set_op_for_with_scoped_expression():
    """``with`` scopes are expanded by reconstructing the nodes."""
    payload = serialize_ast(
        SyntaxService().parse("with {tT1} : {r001} in union({1, 2}, {3})")
    )
    ops = _assert_set_op(payload["right"], "union", 2)
    _assert_set_literal(ops[0], [1, 2])
    _assert_set_literal(ops[1], [3])


def test_serialize_ast_maps_legacy_count_set_op_to_aggregation():
    """``count`` is an aggregation, not a set operator.

    ``CountSetOp`` lost its grammar rule in MR !74 and survives only for
    externally built ASTs, so it must serialize exactly as the parser's
    ``count(...)`` does instead of falling through to ``generic_visit``
    and emitting a class name the consumer schema rejects.
    """
    operand = Set(children=[Constant(type_="Integer", value=1)])
    legacy = serialize_ast(CountSetOp(operand=operand))
    parsed = serialize_ast(SyntaxService().parse("count({1}) = 1"))
    assert legacy == parsed["left"]
    assert legacy["class_name"] == "AggregationOp"
    assert legacy["op"] == "count"
