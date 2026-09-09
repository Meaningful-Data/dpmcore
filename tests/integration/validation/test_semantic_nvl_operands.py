"""``nvl`` operand kinds against the real dictionary (§8.2.2).

The operator is typed ``nvl(op1, op2)`` with both operands
``rset | scal <*>``, but the grammar takes two arbitrary expressions and
``expression`` covers a set. A set operand therefore parses, matched none
of the four combinations ``check_structures`` handled, and left the
operator to raise a bare ``Exception`` instead of a ``SemanticError``.
"""

import pytest

from dpmcore.services.semantic import SemanticService

RELEASE = "4.2.1"

NOT_AN_OPERAND = "have to be a recordset or a scalar"

CELL = "{tC_01.00, r0010, c0010}"


@pytest.fixture
def validate(fixture_session):
    service = SemanticService(fixture_session)

    def _validate(expression):
        return service.validate(expression, release_code=RELEASE)

    return _validate


@pytest.mark.parametrize(
    "expression",
    [
        "nvl({1, 2}, 0) = 1",
        "nvl(0, {1, 2}) = 1",
        f"nvl({{1, 2}}, {CELL}) = 1",
        f"nvl({CELL}, {{1, 2}}) = 1",
    ],
    ids=["set-left", "set-right", "set-left-cell", "set-right-cell"],
)
def test_a_set_operand_is_a_semantic_error(validate, expression):
    """These raised a bare ``Exception`` from ``validate`` before."""
    result = validate(expression)
    assert not result.is_valid
    assert NOT_AN_OPERAND in (result.error_message or "")


@pytest.mark.parametrize(
    "expression",
    [
        f"nvl({CELL}, 0) = 1",
        "nvl(0, 1) = 1",
    ],
    ids=["recordset-scalar", "scalar-scalar"],
)
def test_supported_operands_stay_valid(validate, expression):
    result = validate(expression)
    assert result.is_valid, result.error_message
