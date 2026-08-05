"""Tests for the Fact Component ("f") as a ``where`` clause target (#266).

The DPM-XL spec was extended so a ``where`` condition may reference the Fact
Component of its operand, not just DPM *Key Components*. ``get``, ``rename``
and ``sub`` keep rejecting it, and Standard *Key Components* ("r", "c", "s")
stay out of bounds for every clause operator.

These tests cover the parse/AST/serialization side and the pin-extraction
side. The structural rules live in
``tests/unit/dpm_xl/test_clause_fact_component.py``.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import (
    BinOp,
    Constant,
    Dimension,
    GetOp,
    RenameOp,
    SubOp,
    WhereClauseOp,
)
from dpmcore.dpm_xl.ast.operands import (
    IMPLICIT_OPEN_KEYS,
    NON_KEY_COMPONENT_CODES,
)
from dpmcore.dpm_xl.ast.where_clause import (
    WhereClauseChecker,
    collect_where_equality_pins,
)
from dpmcore.dpm_xl.utils import tokens
from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor
from dpmcore.services.syntax import SyntaxService

WHERE_FACT_EXPRESSIONS = [
    "{tT, r010}[where f > 0]",
    '{tT, r010}[where f = "x"]',
    "{tT, r010}[where f]",
    "{tT, r010}[where f in {[ns:code1], [ns:code2]}]",
    "{tT, r010}[where f and CNT != entityID]",
    "{tT, r010}[where f > 0][get CNT]",
]

# Rejected semantically, not syntactically: ``f`` lexes as an ordinary
# PROPERTY_CODE, so these all parse.
PARSEABLE_NON_WHERE_FACT_EXPRESSIONS = [
    "{tT, r010}[get f]",
    "{tT, r010}[rename f to CNT]",
    '{tT, r010}[sub f = "x"]',
]


@pytest.mark.parametrize("expr", WHERE_FACT_EXPRESSIONS)
def test_where_on_fact_is_valid_syntax(expr):
    """A where condition referencing ``f`` parses."""
    assert SyntaxService().is_valid(expr)


@pytest.mark.parametrize("expr", PARSEABLE_NON_WHERE_FACT_EXPRESSIONS)
def test_fact_in_other_clauses_still_parses(expr):
    """``f`` in get/rename/sub is a semantic error, not a syntax error.

    Pinning this keeps the rejection where it belongs: no grammar change was
    needed for #266, and none should be introduced to reject these.
    """
    assert SyntaxService().is_valid(expr)


def test_where_on_fact_builds_a_dimension_node():
    """``f`` becomes a plain ``Dimension``, like any other component name."""
    ast = SyntaxService().parse("{tT, r010}[where f > 0]")
    where_op = ast.children[0]
    assert isinstance(where_op, WhereClauseOp)
    condition = where_op.condition
    assert isinstance(condition, BinOp)
    assert isinstance(condition.left, Dimension)
    assert condition.left.dimension_code == tokens.FACT


def test_where_clause_checker_collects_the_fact():
    """The Fact counts towards ``key_components``.

    ``visit_WhereClauseOp`` rejects a condition that names no component at
    all (4-5-2-1); a Fact-only condition must not trip that check.
    """
    ast = SyntaxService().parse("{tT, r010}[where f > 0]")
    checker = WhereClauseChecker()
    checker.visit(ast.children[0].condition)
    assert checker.key_components == [tokens.FACT]


def test_get_and_rename_and_sub_keep_the_component_name_as_a_string():
    """Only where conditions produce ``Dimension`` nodes."""
    parse = SyntaxService().parse
    get_op = parse("{tT, r010}[get f]").children[0]
    rename_op = parse("{tT, r010}[rename f to CNT]").children[0]
    sub_op = parse('{tT, r010}[sub f = "x"]').children[0]

    assert isinstance(get_op, GetOp)
    assert get_op.component == tokens.FACT
    assert isinstance(rename_op, RenameOp)
    assert rename_op.rename_nodes[0].old_name == tokens.FACT
    assert isinstance(sub_op, SubOp)
    assert sub_op.substitutions[0].property_code == tokens.FACT


def test_fact_dimension_serializes_unchanged():
    """The wire payload is identical to a key dimension's.

    The engine's AST schema pins ``Dimension`` to exactly ``class_name`` +
    ``dimension_code`` (``additionalProperties: false``), so a Fact reference
    must travel as ``dimension_code: "f"`` and nothing more. Component names
    are unique within a Recordset and the Fact is named "f" by definition, so
    the engine can resolve it by name.
    """
    ast = SyntaxService().parse("{tT, r010}[where f > 0]")
    serialized = ASTToJSONVisitor().visit(ast.children[0])

    assert serialized["class_name"] == "WhereClauseOp"
    assert serialized["condition"]["left"] == {
        "class_name": "Dimension",
        "dimension_code": "f",
    }


class TestFactIsNeverPinned:
    """Pins exist to spot a dead inner join, which is keyed on *keys*.

    Two operands filtering on different fact values join perfectly well, so
    the Fact must never contribute a pin — otherwise
    ``Binary.check_disjoint_where_constraints`` reports a false 2-2.
    """

    def test_fact_equality_yields_no_pin(self):
        node = BinOp(Dimension(tokens.FACT), tokens.EQ, Constant("Integer", 5))
        assert collect_where_equality_pins(node) == {}

    def test_fact_on_the_right_yields_no_pin(self):
        node = BinOp(Constant("Integer", 5), tokens.EQ, Dimension(tokens.FACT))
        assert collect_where_equality_pins(node) == {}

    def test_key_pin_survives_alongside_a_fact_equality(self):
        node = BinOp(
            BinOp(Dimension("qA"), tokens.EQ, Constant("String", "X")),
            tokens.AND,
            BinOp(Dimension(tokens.FACT), tokens.EQ, Constant("Integer", 5)),
        )
        assert collect_where_equality_pins(node) == {"qA": "X"}


class TestNonKeyComponentCodes:
    """The Fact must stay out of the open-key catalogues."""

    def test_fact_is_declared_as_a_non_key_component(self):
        assert tokens.FACT in NON_KEY_COMPONENT_CODES

    def test_fact_is_not_an_implicit_open_key(self):
        """Folding ``f`` into ``IMPLICIT_OPEN_KEYS`` would break it.

        Entries there are injected as DPM *Key Components* into every
        Recordset by ``InputAnalyzer.visit_VarID``, which is exactly what the
        Fact Component must not become — it would then be renameable,
        projectable via ``get``, and counted as a join key.
        """
        assert tokens.FACT not in IMPLICIT_OPEN_KEYS

    def test_catalogues_are_disjoint(self):
        assert not NON_KEY_COMPONENT_CODES & set(IMPLICIT_OPEN_KEYS)
