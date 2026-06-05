"""Tests for optional cosmetic underscore and backtick-escape in reference types.

Per spec, the underscore after a reference prefix is purely cosmetic:
  tT1 ≡ t_T1,  oOp1 ≡ o_Op1,  gGrp1 ≡ g_Grp1

Backtick-escape lets codes contain characters that would otherwise conflict
with the lexer (e.g. a code that starts with an underscore):
  t`_meta`  o`Op.1`  g`grp-1`

VAR_REFERENCE (`v_`) retains its existing PreconditionItem semantics — only
backtick support is added here.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import VarID, VarRef
from dpmcore.services.syntax import SyntaxService

# ---------------------------------------------------------------------------
# Table reference — cosmetic underscore
# ---------------------------------------------------------------------------

TABLE_UNDERSCORE_FORMS = [
    "{t_T1, r010}",
    "{t_T1, c0010}",
    "{t_T1, r010, c0010}",
    "{t_MyTable, r010}",
    "{t_T1}",
]

TABLE_PLAIN_FORMS = [
    "{tT1, r010}",
    "{tT1, c0010}",
    "{tT1, r010, c0010}",
    "{tT1}",
]


@pytest.mark.parametrize("source", TABLE_UNDERSCORE_FORMS)
def test_table_reference_with_underscore_is_valid(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", TABLE_PLAIN_FORMS)
def test_table_reference_plain_still_valid(source):
    assert SyntaxService().is_valid(source)


# ---------------------------------------------------------------------------
# Table group reference — cosmetic underscore
# ---------------------------------------------------------------------------

TABLE_GROUP_UNDERSCORE_FORMS = [
    "{g_grp1, r010}",
    "{g_Grp1, c0010}",
    "{g_grp1, r010, c0010}",
    "{g_grp1}",
]

TABLE_GROUP_PLAIN_FORMS = [
    "{ggrp1, r010}",
    "{gGrp1}",
]


@pytest.mark.parametrize("source", TABLE_GROUP_UNDERSCORE_FORMS)
def test_table_group_reference_with_underscore_is_valid(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", TABLE_GROUP_PLAIN_FORMS)
def test_table_group_reference_plain_still_valid(source):
    assert SyntaxService().is_valid(source)


# ---------------------------------------------------------------------------
# Operation reference — cosmetic underscore
# ---------------------------------------------------------------------------

OPERATION_UNDERSCORE_FORMS = [
    "{o_Op1, r010}",
    "{o_Op1, c0010}",
    "{o_Op1, r010, c0010}",
    "{o_Op1}",
]

OPERATION_PLAIN_FORMS = [
    "{oOp1, r010}",
    "{oOp1}",
]


@pytest.mark.parametrize("source", OPERATION_UNDERSCORE_FORMS)
def test_operation_reference_with_underscore_is_valid(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", OPERATION_PLAIN_FORMS)
def test_operation_reference_plain_still_valid(source):
    assert SyntaxService().is_valid(source)


# ---------------------------------------------------------------------------
# Backtick-escaped codes in references
# ---------------------------------------------------------------------------

BACKTICK_FORMS = [
    "{t`T1`, r010}",
    "{t`MyTable`, r010}",
    "{g`grp1`, r010}",
    "{o`Op1`, r010}",
    "{v`foo`}",
]


@pytest.mark.parametrize("source", BACKTICK_FORMS)
def test_backtick_reference_is_valid(source):
    assert SyntaxService().is_valid(source)


# ---------------------------------------------------------------------------
# AST — underscore is stripped: t_T1 and tT1 produce identical VarID nodes
# ---------------------------------------------------------------------------


def test_table_underscore_produces_same_varid_as_plain():
    svc = SyntaxService()
    plain = svc.parse("{tT1, r010}")
    with_underscore = svc.parse("{t_T1, r010}")

    plain_node = plain.children[0]
    underscore_node = with_underscore.children[0]

    assert isinstance(plain_node, VarID)
    assert isinstance(underscore_node, VarID)
    assert plain_node.table == underscore_node.table
    assert plain_node.rows == underscore_node.rows


def test_table_group_underscore_produces_same_varid_as_plain():
    svc = SyntaxService()
    plain = svc.parse("{gGrp1}")
    with_underscore = svc.parse("{g_Grp1}")

    plain_node = plain.children[0]
    underscore_node = with_underscore.children[0]

    assert isinstance(plain_node, VarID)
    assert isinstance(underscore_node, VarID)
    assert plain_node.table == underscore_node.table
    assert plain_node.is_table_group is True
    assert underscore_node.is_table_group is True


def test_operation_underscore_produces_same_varid_as_plain():
    svc = SyntaxService()
    plain = svc.parse("{oOp1, r010}")
    with_underscore = svc.parse("{o_Op1, r010}")

    plain_node = plain.children[0]
    underscore_node = with_underscore.children[0]

    assert isinstance(plain_node, VarID)
    assert isinstance(underscore_node, VarID)
    assert plain_node.operation == underscore_node.operation
    assert plain_node.rows == underscore_node.rows


# ---------------------------------------------------------------------------
# AST — backtick form strips backticks: t`T1` ≡ tT1
# ---------------------------------------------------------------------------


def test_table_backtick_produces_same_table_as_plain():
    svc = SyntaxService()
    plain = svc.parse("{tT1, r010}")
    backtick = svc.parse("{t`T1`, r010}")

    plain_node = plain.children[0]
    backtick_node = backtick.children[0]

    assert isinstance(plain_node, VarID)
    assert isinstance(backtick_node, VarID)
    assert plain_node.table == backtick_node.table


def test_var_backtick_produces_varref_with_stripped_code():
    svc = SyntaxService()
    node = svc.parse("{v`foo`}").children[0]
    assert isinstance(node, VarRef)
    assert node.variable == "foo"
