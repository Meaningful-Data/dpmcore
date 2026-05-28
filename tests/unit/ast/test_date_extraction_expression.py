"""Syntax and AST tests for date extraction operators: year, semester, quarter, month, week, day."""

import pytest

from dpmcore.dpm_xl.ast.nodes import DateExtractionOp
from dpmcore.services.syntax import SyntaxService

EXTRACTION_OPERATORS = ["year", "semester", "quarter", "month", "week", "day"]

VALID_SCALAR_FORMS = [f"{op}(#2022-03-15#)" for op in EXTRACTION_OPERATORS]

VALID_RECORDSET_FORMS = [
    "year({tC_09.02})",
    "quarter({tC_09.02})",
]

VALID_IN_EXPRESSION = [
    "year(#2022-03-15#) = 2022",
    "quarter(#2022-03-15#) >= 1",
    "month(#2022-03-15#) = 3",
]


@pytest.mark.parametrize("source", VALID_SCALAR_FORMS)
def test_extraction_scalar_syntax_valid(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", VALID_RECORDSET_FORMS)
def test_extraction_recordset_syntax_valid(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", VALID_IN_EXPRESSION)
def test_extraction_in_expression_syntax_valid(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("op", EXTRACTION_OPERATORS)
def test_extraction_produces_date_extraction_op_node(op):
    ast = SyntaxService().parse(f"{op}(#2022-03-15#)")
    node = ast.children[0]
    assert isinstance(node, DateExtractionOp)
    assert node.op == op


def test_extraction_operand_is_ast_node():
    ast = SyntaxService().parse("year(#2022-03-15#)")
    node = ast.children[0]
    assert isinstance(node, DateExtractionOp)
    assert node.operand is not None


def test_extraction_tojson_serializable():
    ast = SyntaxService().parse("quarter(#2022-03-15#)")
    node = ast.children[0]
    assert isinstance(node, DateExtractionOp)
    result = node.toJSON()
    assert result["class_name"] == "DateExtractionOp"
    assert result["op"] == "quarter"
    assert "operand" in result
