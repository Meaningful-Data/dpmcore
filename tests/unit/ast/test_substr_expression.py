"""Syntax, AST and validation tests for the substr string operator."""

import pandas as pd
import pytest

from dpmcore.dpm_xl.ast.nodes import SubstrOp
from dpmcore.dpm_xl.operators.string import Len, Substr
from dpmcore.dpm_xl.symbols import (
    ConstantOperand,
    FactComponent,
    KeyComponent,
    RecordSet,
    Scalar,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import Mixed, Number, String
from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor
from dpmcore.dpm_xl.utils.tokens import STANDARD
from dpmcore.errors import SemanticError
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


def _make_mixed_recordset() -> RecordSet:
    """Recordset with Mixed type and compatible row types."""
    structure = Structure(
        [
            KeyComponent("r", Number(), STANDARD, "test"),
            FactComponent(Mixed(), "test"),
        ]
    )
    recordset = RecordSet(structure, "test", "test")
    recordset.records = pd.DataFrame(
        {"r": [1, 2], "data_type": [String(), String()]}
    )
    return recordset


def test_substr_mixed_recordset_does_not_crash():
    """Mixed typed recordset with compatible rows must succeed."""
    result = Substr.validate(_make_mixed_recordset(), start=1)
    assert isinstance(result, RecordSet)


def test_substr_mixed_recordset_without_records_raises():
    """Malformed Mixed recordset (no .records) must raise error, not KeyError."""
    recordset = _make_mixed_recordset()
    recordset.records = None
    with pytest.raises(Exception) as exc_info:
        Substr.validate(recordset, start=1)
    assert not isinstance(exc_info.value, KeyError)


def _make_constant(value: str) -> ConstantOperand:
    return ConstantOperand(
        type_=String(), name=value, origin=f'"{value}"', value=value
    )


@pytest.mark.parametrize(
    ("source", "value", "start", "length", "expected"),
    [
        ('substr("Hello", 2)', "Hello", 2, None, "ello"),
        ('substr("Hello", 5, 3)', "Hello", 5, 3, "o"),
        ('substr("Hello World", 7)', "Hello World", 7, None, "World"),
        ('substr("Hello World", 1, 5)', "Hello World", 1, 5, "Hello"),
        ('substr("Hello World")', "Hello World", None, None, "Hello World"),
        ('substr("Hello World", 20)', "Hello World", 20, None, ""),
        ('substr("Hello", 2, 0)', "Hello", 2, 0, ""),
    ],
)
def test_substr_constant_folds_value(source, value, start, length, expected):
    syntax = SyntaxService()
    assert syntax.is_valid(source)
    syntax.parse(source)

    result = Substr.validate(_make_constant(value), start=start, length=length)
    assert isinstance(result, ConstantOperand)
    assert result.value == expected


@pytest.mark.parametrize(
    ("source", "start", "length"),
    [
        ('substr("Hello", (-5))', -5, None),
        ('substr("Hello", 0)', 0, None),
        ('substr("Hello", 2, (-1))', 2, -1),
    ],
)
def test_substr_invalid_parameters_rejected(source, start, length):
    syntax = SyntaxService()
    assert syntax.is_valid(source)
    syntax.parse(source)

    with pytest.raises(SemanticError):
        Substr.validate(_make_constant("Hello"), start=start, length=length)


def test_substr_constant_relabels_origin_instead_of_reusing_operand():
    operand = _make_constant("Hello")
    result = Substr.validate(operand, start=2)

    assert result is not operand
    assert result.origin == 'substr("Hello", 2)'
    assert operand.origin == '"Hello"'


def test_len_of_substr_constant_uses_substr_label():
    """Verify nested operations preserve inner origin"""
    substr_result = Substr.validate(_make_constant("Hello"), start=2)
    len_result = Len.validate_types(substr_result)

    assert len_result.origin == 'len(substr("Hello", 2))'
