"""Tests for precondition element parsing via the varRef grammar rule.

Precondition elements use the ``v_`` prefix (e.g. ``{v_Z101}``) and must
produce a ``PreconditionItem`` AST node, while regular variable references
(``{vMyVar}``) must continue to produce a ``VarRef`` node.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import PreconditionItem, VarRef
from dpmcore.services.syntax import SyntaxService

VALID_PRECONDITION_ELEMS = [
    ("{v_Z101}", "Z101"),
    ("{v_SomeTable}", "SomeTable"),
    ("{v_A}", "A"),  # single-letter code
    (
        "{v_Some-Table}",
        "Some-Table",
    ),  # dash in code (TABLE_CODE allows '-', VAR_CODE does not)
]

INVALID_PRECONDITION_FORMS = [
    "{v_}",  # bare prefix, no code
    "{v_123}",  # code starts with digit, not a letter
    "with {v_Z101}: {tT1, c0010}",  # v_ is not a valid cell ref for with-clause
    "{v_Z101} <- 1",  # v_ cannot be the LHS of a persistent assignment
]


@pytest.mark.parametrize(("expression", "code"), VALID_PRECONDITION_ELEMS)
def test_valid_precondition_elem(expression, code):
    """A v_ expression is accepted by the parser."""
    assert SyntaxService().is_valid(expression)


@pytest.mark.parametrize(("expression", "code"), VALID_PRECONDITION_ELEMS)
def test_precondition_elem_produces_precondition_item(expression, code):
    """A v_ expression produces a PreconditionItem node with the correct code."""
    start = SyntaxService().parse(expression)
    node = start.children[0]
    assert isinstance(node, PreconditionItem)
    assert node.variable_id == code
    assert node.variable_code == code


def test_regular_var_ref():
    """{vMyVar} parses to a VarRef node (not PreconditionItem)."""
    start = SyntaxService().parse("{vMyVar}")
    node = start.children[0]
    assert isinstance(node, VarRef)
    assert node.variable == "MyVar"


@pytest.mark.parametrize("expression", INVALID_PRECONDITION_FORMS)
def test_invalid_precondition_forms_are_rejected(expression):
    """Malformed or context-invalid v_ expressions are rejected by the parser."""
    assert not SyntaxService().is_valid(expression)
