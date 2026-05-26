"""Tests for the duplicate-key guard in InputAnalyzer.visit_SubOp.

When a sub clause contains the same property code twice (``sub a=1, a=2``),
the chained validate loop in visit_SubOp would otherwise drop the
component on the first iteration and the second would fail with the
misleading code 2-8 ("key not on recordset"). The guard rejects the
expression up front with error code 4-5-3-1.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import (
    Constant,
    SubAssignment,
    SubOp,
)
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.errors import SemanticError


def _make_sub_op(property_codes: list[str]) -> SubOp:
    """Build a SubOp with the given property codes (values are dummies).

    The operand is a dummy Constant — visit_SubOp's duplicate-key guard
    runs BEFORE the operand is visited, so the operand only matters for
    the negative test that exercises the path past the guard.
    """
    operand = Constant(type_="String", value="dummy")
    substitutions = [
        SubAssignment(
            property_code=code,
            value=Constant(type_="String", value="dummy"),
        )
        for code in property_codes
    ]
    return SubOp(operand=operand, substitutions=substitutions)


def test_duplicate_property_code_raises_4_5_3_1():
    """Two substitutions with the same property code raise SemanticError 4-5-3-1."""
    analyzer = InputAnalyzer(expression="dummy")
    sub_op = _make_sub_op(["c0010", "c0010"])

    with pytest.raises(SemanticError) as exc_info:
        analyzer.visit_SubOp(sub_op)

    assert exc_info.value.code == "4-5-3-1"
    assert "c0010" in str(exc_info.value)


def test_triple_duplicate_property_code_raises_4_5_3_1():
    """A repeat on the third substitution also fires the guard."""
    analyzer = InputAnalyzer(expression="dummy")
    sub_op = _make_sub_op(["c0010", "c0020", "c0010"])

    with pytest.raises(SemanticError) as exc_info:
        analyzer.visit_SubOp(sub_op)

    assert exc_info.value.code == "4-5-3-1"
    assert "c0010" in str(exc_info.value)


# Branch coverage of the "no duplicate" path (``seen.add``) comes from
# the positive tests above: the first iteration always takes the False
# branch (set is empty) before a duplicate fires on a later iteration.
# End-to-end coverage of multi-sub with distinct codes lives in the
# integration tests under ``tests/integration/validation/``.
