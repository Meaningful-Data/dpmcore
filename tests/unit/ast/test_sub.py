"""Tests for the sub clause grammar contract.

The sub clause accepts one or more comma-separated substitutions:
    sub key = value {, key = value}*
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import Scalar, SubAssignment, SubOp
from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor
from dpmcore.services.syntax import SyntaxService

SINGLE_SUB_EXPRESSIONS = [
    '{tT, r010}[sub c0010 = "ES"]',
    "{tT, r010}[sub c0010 = {vMyVar}]",
    "{tT, r010}[sub c0010 = [ns:code]]",
]

MULTIPLE_SUB_EXPRESSIONS = [
    '{tT, r010}[sub c0010 = "ES", c0020 = "FR"]',
    '{tT, r010}[sub c0010 = "ES", c0020 = "FR", c0030 = "DE"]',
]

INVALID_SUB_EXPRESSIONS = [
    "{tT, r010}[sub]",
    "{tT, r010}[sub c0010 = ]",
    '{tT, r010}[sub , c0010 = "ES"]',
    '{tT, r010}[sub c0010 = "ES", ]',
]


@pytest.mark.parametrize("expr", SINGLE_SUB_EXPRESSIONS)
def test_single_sub_is_valid(expr):
    """A single substitution is still accepted."""
    assert SyntaxService().is_valid(expr)


@pytest.mark.parametrize("expr", MULTIPLE_SUB_EXPRESSIONS)
def test_multiple_sub_is_valid(expr):
    """Multiple comma-separated substitutions are accepted."""
    assert SyntaxService().is_valid(expr)


@pytest.mark.parametrize("expr", INVALID_SUB_EXPRESSIONS)
def test_malformed_sub_is_invalid(expr):
    """``is_valid`` reports malformed sub expressions as invalid."""
    assert not SyntaxService().is_valid(expr)


@pytest.mark.parametrize("expr", INVALID_SUB_EXPRESSIONS)
def test_malformed_sub_validate_returns_error_message(expr):
    """``validate`` reports malformed sub expressions with an error_message."""
    result = SyntaxService().validate(expr)
    assert not result.is_valid
    assert result.error_message


def test_single_sub_produces_one_substitution():
    """A single sub builds a SubOp with one SubAssignment."""
    ast = SyntaxService().parse('{tT, r010}[sub c0010 = "ES"]')
    sub_op = ast.children[0]
    assert isinstance(sub_op, SubOp)
    assert len(sub_op.substitutions) == 1
    assert isinstance(sub_op.substitutions[0], SubAssignment)
    assert sub_op.substitutions[0].property_code == "c0010"


def test_multiple_sub_produces_multiple_substitutions():
    """Multiple subs build a SubOp with one SubAssignment per pair."""
    ast = SyntaxService().parse('{tT, r010}[sub c0010 = "ES", c0020 = "FR"]')
    sub_op = ast.children[0]
    assert isinstance(sub_op, SubOp)
    assert len(sub_op.substitutions) == 2
    assert sub_op.substitutions[0].property_code == "c0010"
    assert sub_op.substitutions[1].property_code == "c0020"


def test_single_sub_serializes_as_one_subclause_op():
    """Single-sub JSON is one SubClauseOp wrapping the recordset directly.

    Backwards-compatibility check: adam-engine's existing scripts use this
    shape, so the wire format must be unchanged for the single-sub case.
    """
    ast = SyntaxService().parse('{tT, r010}[sub c0010 = "ES"]')
    sub_op = ast.children[0]
    serialized = ASTToJSONVisitor().visit(sub_op)

    assert serialized["class_name"] == "SubClauseOp"
    assert serialized["condition"]["class_name"] == "BinOp"
    assert serialized["condition"]["op"] == "="
    assert serialized["condition"]["left"]["class_name"] == "Dimension"
    assert serialized["condition"]["left"]["dimension_code"] == "c0010"
    # Operand is the recordset, not another SubClauseOp.
    assert serialized["operand"]["class_name"] != "SubClauseOp"


def test_multi_sub_serializes_as_chained_subclause_ops():
    """Multi-sub JSON nests one SubClauseOp per substitution (left-deep).

    Locks the wire-format contract with adam-engine, whose ``SubClauseOp``
    schema accepts a single ``condition`` per node. The outermost node
    wraps the LAST substitution; the original recordset sits at the
    deepest level. Order matches the left-to-right reading of the
    source: ``c0010`` is applied first, ``c0020`` second.
    """
    ast = SyntaxService().parse('{tT, r010}[sub c0010 = "ES", c0020 = "FR"]')
    sub_op = ast.children[0]
    serialized = ASTToJSONVisitor().visit(sub_op)

    # Outer wraps the second substitution.
    assert serialized["class_name"] == "SubClauseOp"
    assert serialized["condition"]["left"]["dimension_code"] == "c0020"

    # Inner wraps the first substitution and the original recordset.
    inner = serialized["operand"]
    assert inner["class_name"] == "SubClauseOp"
    assert inner["condition"]["left"]["dimension_code"] == "c0010"

    # Original recordset sits at the deepest level.
    assert inner["operand"]["class_name"] != "SubClauseOp"


@pytest.mark.parametrize(
    "item_code",
    [
        "eba_qEC:qx01",
        "eba_qAE:qx2023",
        "eba_qLR:qx10",
        "eba_EC:qx01",
        "ns:code",
    ],
)
def test_scalar_item_serialized_verbatim(item_code):
    """A Scalar item code is serialized unchanged.

    Regression: an earlier pass rewrote ``eba_q*`` to ``eba_*`` (dropping
    the ``q``), corrupting the namespaced member signature the engine
    consumes (``eba_qEC:qx01`` became ``eba_EC:qx01``). The code must be
    emitted exactly as authored.
    """
    serialized = ASTToJSONVisitor().visit(
        Scalar(item=item_code, scalar_type="Item")
    )

    assert serialized["class_name"] == "Scalar"
    assert serialized["item"] == item_code
    assert serialized["scalar_type"] == "Item"


def test_sub_clause_preserves_eba_q_item_namespace():
    """``[sub key = [eba_qEC:qx01]]`` keeps the ``q`` in the item code.

    End-to-end through the parser and serializer: the substitution value
    is a namespaced item whose ``q`` must survive into the wire format.
    """
    ast = SyntaxService().parse("{tT, r010}[sub c0010 = [eba_qEC:qx01]]")
    sub_op = ast.children[0]
    serialized = ASTToJSONVisitor().visit(sub_op)

    right = serialized["condition"]["right"]
    assert right["class_name"] == "Scalar"
    assert right["item"] == "eba_qEC:qx01"


def test_three_subs_serialize_as_three_chained_subclause_ops():
    """Three substitutions produce three nested SubClauseOp nodes."""
    ast = SyntaxService().parse(
        '{tT, r010}[sub c0010 = "ES", c0020 = "FR", c0030 = "DE"]'
    )
    sub_op = ast.children[0]
    serialized = ASTToJSONVisitor().visit(sub_op)

    # Outermost wraps c0030.
    assert serialized["class_name"] == "SubClauseOp"
    assert serialized["condition"]["left"]["dimension_code"] == "c0030"

    # Middle wraps c0020.
    middle = serialized["operand"]
    assert middle["class_name"] == "SubClauseOp"
    assert middle["condition"]["left"]["dimension_code"] == "c0020"

    # Innermost wraps c0010 and the original recordset.
    innermost = middle["operand"]
    assert innermost["class_name"] == "SubClauseOp"
    assert innermost["condition"]["left"]["dimension_code"] == "c0010"
    assert innermost["operand"]["class_name"] != "SubClauseOp"
