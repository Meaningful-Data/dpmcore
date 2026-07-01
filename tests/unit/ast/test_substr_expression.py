"""Syntax, AST and validation tests for the substr string operator."""

import pytest

from dpmcore.dpm_xl.ast.nodes import SubstrOp
from dpmcore.dpm_xl.operators.string import Substr
from dpmcore.dpm_xl.symbols import (
    FactComponent,
    KeyComponent,
    RecordSet,
    Scalar,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import Number, String
from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor
from dpmcore.dpm_xl.utils.tokens import STANDARD
from dpmcore.services.syntax import SyntaxService

# ---------------------------------------------------------------------------
# Syntax
# ---------------------------------------------------------------------------

VALID_FORMS = [
    "substr({tT1, r010, c010})",
    "substr({tT1, r010, c010}, 2)",
    "substr({tT1, r010, c010}, 2, 5)",
    'substr("Hello World", 7)',
    'substr("Hello World", 1, 5)',
]

INVALID_FORMS = [
    "substr()",
    "substr({tT1}, 2, 5, 1)",
]


@pytest.mark.parametrize("source", VALID_FORMS)
def test_substr_syntax_valid(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", INVALID_FORMS)
def test_substr_wrong_arity_invalid(source):
    assert not SyntaxService().is_valid(source)


# ---------------------------------------------------------------------------
# AST node
# ---------------------------------------------------------------------------


def test_substr_ast_node():
    ast = SyntaxService().parse("substr({tT1, r010, c010}, 2, 5)")
    node = ast.children[0]
    assert isinstance(node, SubstrOp)
    assert node.op == "substr"
    assert node.operand is not None
    assert node.start == 2
    assert node.length == 5


def test_substr_optional_params_default_none():
    ast = SyntaxService().parse("substr({tT1, r010, c010})")
    node = ast.children[0]
    assert isinstance(node, SubstrOp)
    assert node.start is None
    assert node.length is None


def test_substr_tojson():
    ast = SyntaxService().parse("substr({tT1, r010, c010}, 2, 5)")
    node = ast.children[0]
    result = node.toJSON()
    assert result["class_name"] == "SubstrOp"
    assert result["op"] == "substr"
    assert "operand" in result
    assert result["start"] == 2
    assert result["length"] == 5


def test_serializer_produces_substr_dict():
    ast = SyntaxService().parse("substr({tT1, r010, c010}, 2, 5)")
    result = ASTToJSONVisitor().visit(ast)
    node = result["children"][0]
    assert node["class_name"] == "SubstrOp"
    assert node["op"] == "substr"
    assert node["start"] == 2
    assert node["length"] == 5
    assert isinstance(node["operand"], dict)


# ---------------------------------------------------------------------------
# Operator validation
# ---------------------------------------------------------------------------


def _make_scalar(name: str) -> Scalar:
    return Scalar(type_=String(), name=name, origin=name)


def _make_recordset() -> RecordSet:
    structure = Structure(
        [
            KeyComponent("r", Number(), STANDARD, "test"),
            FactComponent(String(), "test"),
        ]
    )
    return RecordSet(structure, "test", "test")


def test_substr_scalar_returns_string_scalar():
    result = Substr.validate(_make_scalar("x"), start=2, length=5)
    assert isinstance(result, Scalar)
    assert isinstance(result.type, String)


def test_substr_optional_params_omitted_returns_string_scalar():
    result = Substr.validate(_make_scalar("x"))
    assert isinstance(result, Scalar)
    assert isinstance(result.type, String)


def test_substr_recordset_returns_string_recordset():
    result = Substr.validate(_make_recordset(), start=1)
    assert isinstance(result, RecordSet)
    assert isinstance(result.get_fact_component().type, String)
