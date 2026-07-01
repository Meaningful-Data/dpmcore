"""Syntax and AST tests for the date(year, month, day) constructor operator."""

import pytest

from dpmcore.dpm_xl.ast.nodes import DateConstructorOp
from dpmcore.dpm_xl.operators.time import DateConstructor
from dpmcore.dpm_xl.symbols import (
    FactComponent,
    KeyComponent,
    RecordSet,
    Scalar,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import Date, Integer, Number
from dpmcore.dpm_xl.utils.tokens import STANDARD
from dpmcore.services.syntax import SyntaxService

VALID_FORMS = [
    "date(2025, 12, 31)",
    "date(2022, 1, 1)",
    "isnull(date(2025, 2, 30))",
    "date(2025, 12, 31) = #2025-12-31#",
]

INVALID_ARITY = [
    "date(2025, 12)",
    "date(2025, 12, 31, 0)",
    "date()",
]


@pytest.mark.parametrize("source", VALID_FORMS)
def test_constructor_syntax_valid(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", INVALID_ARITY)
def test_constructor_wrong_arity_invalid(source):
    assert not SyntaxService().is_valid(source)


def test_constructor_produces_date_constructor_op_node():
    ast = SyntaxService().parse("date(2025, 12, 31)")
    node = ast.children[0]
    assert isinstance(node, DateConstructorOp)


def test_constructor_node_has_year_month_day():
    ast = SyntaxService().parse("date(2025, 12, 31)")
    node = ast.children[0]
    assert isinstance(node, DateConstructorOp)
    assert node.year is not None
    assert node.month is not None
    assert node.day is not None


def test_constructor_tojson_serializable():
    ast = SyntaxService().parse("date(2025, 12, 31)")
    node = ast.children[0]
    assert isinstance(node, DateConstructorOp)
    result = node.toJSON()
    assert result["class_name"] == "DateConstructorOp"
    assert "year" in result
    assert "month" in result
    assert "day" in result


def test_constructor_node_op_is_date():
    """``op`` is set at construction (like ``UnaryOp``) so raw-AST
    consumers — e.g. ``_resolve_root_operator_id`` — see the operator symbol
    instead of the inherited ``None``.
    """
    ast = SyntaxService().parse("date(2025, 12, 31)")
    node = ast.children[0]
    assert isinstance(node, DateConstructorOp)
    assert node.op == "date"
    assert node.toJSON()["op"] == "date"


# Operator validation: any combination of Scalar and Recordset operands is allowed


def _int_scalar(name: str) -> Scalar:
    return Scalar(type_=Integer(), name=name, origin=name)


def _int_recordset() -> RecordSet:
    structure = Structure(
        [
            KeyComponent("r", Number(), STANDARD, "test"),
            FactComponent(Integer(), "test"),
        ]
    )
    return RecordSet(structure, "test", "test")


@pytest.mark.parametrize(
    ("operands", "expects_recordset"),
    [
        ((_int_scalar("y"), _int_scalar("m"), _int_scalar("d")), False),
        ((_int_recordset(), _int_scalar("m"), _int_scalar("d")), True),
    ],
)
def test_date_constructor_validate_scalar_and_recordset(
    operands, expects_recordset
):
    result = DateConstructor.validate(*operands)
    if expects_recordset:
        assert isinstance(result, RecordSet)
        assert isinstance(result.get_fact_component().type, Date)
    else:
        assert isinstance(result, Scalar)
        assert isinstance(result.type, Date)
