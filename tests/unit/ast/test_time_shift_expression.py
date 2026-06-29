"""Tests for time_shift numberPeriods accepting integer expressions."""

import pytest

from dpmcore.dpm_xl.ast.nodes import Constant, TimeShiftOp, UnaryOp
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
    assert isinstance(node.shift_number, UnaryOp)
    assert node.shift_number.op == "-"
    assert isinstance(node.shift_number.operand, Constant)
    assert node.shift_number.operand.value == 5


def test_arithmetic_shift_produces_ast_node():
    ast = SyntaxService().parse("time_shift({tT1}, Q, 5 * 12)")
    node = ast.children[0]
    assert isinstance(node, TimeShiftOp)
    assert node.shift_number is not None
    assert not isinstance(node.shift_number, str)


def test_tojson_shift_number_is_serializable():
    ast = SyntaxService().parse("time_shift({tT1}, Q, 5 * 12)")
    node = ast.children[0]
    assert isinstance(node, TimeShiftOp)
    result = node.toJSON()
    assert isinstance(result["shift_number"], dict)
    assert "class_name" in result["shift_number"]


def test_serializer_shift_number_is_dict():
    from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor

    ast = SyntaxService().parse("time_shift({tT1}, Q, 5 * 12)")
    result = ASTToJSONVisitor().visit(ast)
    time_shift = result["children"][0]
    assert isinstance(time_shift["shift_number"], dict)
    assert "class_name" in time_shift["shift_number"]


def test_float_shift_has_number_type_constant():
    # Grammar accepts any expression; the AST stores the type as-is.
    # The semantic layer rejects non-Integer types (error 4-7-4).
    ast = SyntaxService().parse("time_shift({tT1}, Q, 5.5)")
    node = ast.children[0]
    assert isinstance(node, TimeShiftOp)
    assert isinstance(node.shift_number, Constant)
    assert node.shift_number.type == "Number"


def test_string_shift_has_string_type_constant():
    # Grammar accepts any expression; the AST stores the type as-is.
    # The semantic layer rejects non-Integer types (error 4-7-4).
    ast = SyntaxService().parse('time_shift({tT1}, Q, "hello")')
    node = ast.children[0]
    assert isinstance(node, TimeShiftOp)
    assert isinstance(node.shift_number, Constant)
    assert node.shift_number.type == "String"


def test_serializer_period_indicator_is_constant_node():
    from dpmcore.dpm_xl.utils.serialization import serialize_ast

    node = (
        SyntaxService().parse("time_shift({tT1}, A, 1, refPeriod)").children[0]
    )
    out = serialize_ast(node)

    assert out["period_indicator"] == {
        "class_name": "Constant",
        "type_": "String",
        "value": "A",
    }
    assert out["reference_period"] == "refPeriod"
    assert "component" not in out


def test_tojson_period_indicator_is_constant_node():
    node = (
        SyntaxService().parse("time_shift({tT1}, A, 1, refPeriod)").children[0]
    )
    out = node.toJSON()

    assert out["period_indicator"] == {
        "class_name": "Constant",
        "type_": "String",
        "value": "A",
    }
    assert out["reference_period"] == "refPeriod"
    assert "component" not in out


def test_serializer_scalar_form_reference_period_is_null():
    # The 3-argument form has no reference-period selector; the key is
    # still emitted, as null, and period_indicator stays a Constant node.
    from dpmcore.dpm_xl.utils.serialization import serialize_ast

    node = SyntaxService().parse("time_shift({tT1}, A, 1)").children[0]
    out = serialize_ast(node)

    assert out["period_indicator"] == {
        "class_name": "Constant",
        "type_": "String",
        "value": "A",
    }
    assert out["reference_period"] is None
    assert "component" not in out


def test_tojson_scalar_form_reference_period_is_null():
    node = SyntaxService().parse("time_shift({tT1}, A, 1)").children[0]
    out = node.toJSON()

    assert out["period_indicator"] == {
        "class_name": "Constant",
        "type_": "String",
        "value": "A",
    }
    assert out["reference_period"] is None
    assert "component" not in out
