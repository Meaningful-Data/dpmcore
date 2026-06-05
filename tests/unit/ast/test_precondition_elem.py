"""Tests for variable references used as precondition elements.

Per spec, the ``v_`` underscore is purely cosmetic: ``{vZ101}`` and
``{v_Z101}`` are identical and both produce a ``VarRef`` node.
Codes with a leading underscore or a dash must use backtick-escaping.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import VarRef
from dpmcore.services.syntax import SyntaxService

VALID_VAR_REF_FORMS = [
    ("{v_Z101}", "Z101"),
    ("{v_SomeTable}", "SomeTable"),
    ("{v_A}", "A"),
    ("{vZ101}", "Z101"),
    ("{vSomeTable}", "SomeTable"),
]

INVALID_VAR_REF_FORMS = [
    "{v_}",  # bare prefix, no code
    "{v_123}",  # code starts with digit
    "{v_Some-Table}",  # dash not allowed in VAR_CODE — use backtick: v`Some-Table`
    "with {v_Z101}: {tT1, c0010}",  # v not valid as cell ref in with-clause
    "{v_Z101} <- 1",  # v cannot be LHS of persistent assignment
]


@pytest.mark.parametrize(("expression", "code"), VALID_VAR_REF_FORMS)
def test_valid_var_ref_forms_accepted(expression, code):
    assert SyntaxService().is_valid(expression)


@pytest.mark.parametrize(("expression", "code"), VALID_VAR_REF_FORMS)
def test_var_ref_produces_varref_node(expression, code):
    start = SyntaxService().parse(expression)
    node = start.children[0]
    assert isinstance(node, VarRef)
    assert node.variable == code


@pytest.mark.parametrize("expression", INVALID_VAR_REF_FORMS)
def test_invalid_var_ref_forms_rejected(expression):
    assert not SyntaxService().is_valid(expression)
