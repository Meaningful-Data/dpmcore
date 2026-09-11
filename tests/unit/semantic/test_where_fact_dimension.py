"""Tests for Fact Component resolution in ``InputAnalyzer.visit_Dimension``.

A ``Dimension`` naming the Fact Component ("f") is not looked up in the
dictionary: its data type is whatever the enclosing clause operand carries.
``visit_WhereClauseOp`` therefore pushes its operand onto a stack before
visiting the condition, and ``visit_Dimension`` reads the top of that stack.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import Constant, Dimension, WhereClauseOp
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.dpm_xl.symbols import (
    FactComponent,
    KeyComponent,
    RecordSet,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import Boolean, Item, Number, String
from dpmcore.dpm_xl.utils.tokens import DPM, FACT
from dpmcore.errors import SemanticError


def _make_rs(fact_type) -> RecordSet:
    structure = Structure(
        [
            KeyComponent("qA", Item(), DPM, "test"),
            FactComponent(fact_type, "test"),
        ]
    )
    return RecordSet(structure, "ds", "ds")


@pytest.mark.parametrize("fact_type", [Number(), String(), Boolean()])
def test_fact_dimension_takes_the_operands_fact_type(fact_type):
    """The scalar returned mirrors the operand's Fact Component type.

    This is what makes ``[where f]`` valid on a Boolean-typed selection and a
    type error on a numeric one, and what type-checks ``[where f = "x"]``
    against the right side.
    """
    analyser = InputAnalyzer(expression="")
    analyser._clause_operands.append(_make_rs(fact_type))

    result = analyser.visit_Dimension(Dimension(FACT))

    assert type(result.type) is type(fact_type)
    assert result.origin == FACT


def test_innermost_operand_wins():
    """Chained/nested clauses resolve against the operand they belong to."""
    analyser = InputAnalyzer(expression="")
    analyser._clause_operands.append(_make_rs(Number()))
    analyser._clause_operands.append(_make_rs(String()))

    assert isinstance(analyser.visit_Dimension(Dimension(FACT)).type, String)

    analyser._clause_operands.pop()
    assert isinstance(analyser.visit_Dimension(Dimension(FACT)).type, Number)


def test_non_recordset_operand_raises_4_5_0_2_before_the_condition():
    """A scalar operand is rejected before the condition is resolved.

    ``ClauseOperator.validate`` rejects it too, but only after the condition
    has been visited — and resolving the Fact needs a structure. Failing
    first here keeps the operand stack total, with the same error code.
    """
    analyser = InputAnalyzer(expression="")
    node = WhereClauseOp(
        operand=Constant(type_="String", value="dummy"),
        condition=Dimension(FACT),
    )
    node.key_components = [FACT]

    with pytest.raises(SemanticError) as exc:
        analyser.visit_WhereClauseOp(node)

    assert exc.value.code == "4-5-0-2"
    assert analyser._clause_operands == []


def test_empty_condition_still_raises_4_5_2_1_first():
    """Error precedence is unchanged: the empty-condition check comes first."""
    analyser = InputAnalyzer(expression="")
    node = WhereClauseOp(
        operand=Constant(type_="String", value="dummy"),
        condition=Dimension(FACT),
    )

    with pytest.raises(SemanticError) as exc:
        analyser.visit_WhereClauseOp(node)

    assert exc.value.code == "4-5-2-1"


def test_fact_outside_a_clause_raises_4_5_0_1():
    """Defensive guard: no operand in scope means no Fact to resolve.

    The grammar only produces a ``Dimension`` inside a clause, so this is not
    reachable from a parsed expression — but the resolution must fail loudly
    rather than index an empty stack.
    """
    analyser = InputAnalyzer(expression="{tT}[where f]")

    with pytest.raises(SemanticError) as exc:
        analyser.visit_Dimension(Dimension(FACT))

    assert exc.value.code == "4-5-0-1"
