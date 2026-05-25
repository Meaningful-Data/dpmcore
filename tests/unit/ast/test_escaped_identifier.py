"""Tests for backtick-escaped identifier syntax.

Backtick escaping allows reserved words to be used as identifiers:

    `sum`    `where`    `not`    `and`

The backticks are stripped: the resulting AST node is
identical to the one produced by the unescaped form.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import (
    PropertyReference,
    TemporaryAssignment,
    TemporaryIdentifier,
)
from dpmcore.services.syntax import SyntaxService

PROPERTY_CODE_FORMS = [
    ("[myProp]", "myProp"),
    ("[`sum`]", "sum"),
    ("[`where`]", "where"),
    ("[`not`]", "not"),
]

TEMP_ID_FORMS = [
    ("myAlias := true", "myAlias"),
    ("`sum` := true", "sum"),
    ("`where` := true", "where"),
    ("`not` := true", "not"),
]

KEY_NAME_FORMS = [
    ("{tT_00.01, c0010}[get r]", "r"),
    ("{tT_00.01, c0010}[get `where`]", "where"),
    ("{tT_00.01, c0010}[get `sum`]", "sum"),
]

INVALID_ESCAPED_FORMS = [
    "`",  # bare backtick
    "``",  # empty backtick pair
    "`sum",  # unclosed backtick
    "sum`",  # no opening backtick
]

UNESCAPED_KEYWORD_FORMS = [
    "[where]",
    "[sum]",
    "[not]",
    "[and]",
]

VALID_FORMS = PROPERTY_CODE_FORMS + TEMP_ID_FORMS + KEY_NAME_FORMS
INVALID_FORMS = INVALID_ESCAPED_FORMS + UNESCAPED_KEYWORD_FORMS


@pytest.mark.parametrize(("source", "_name"), VALID_FORMS)
def test_valid_forms_are_accepted(source, _name):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", INVALID_FORMS)
def test_invalid_forms_are_rejected(source):
    assert not SyntaxService().is_valid(source)


@pytest.mark.parametrize(("source", "code"), PROPERTY_CODE_FORMS)
def test_property_code_backtick_strips_to_plain(source, code):
    """Backtick form produces PropertyReference with the same code as plain form."""
    start = SyntaxService().parse(source)
    node = start.children[0]
    assert isinstance(node, PropertyReference)
    assert node.code == code


@pytest.mark.parametrize(("source", "name"), TEMP_ID_FORMS)
def test_temporary_identifier_backtick_strips_to_plain(source, name):
    """Backtick form of temporaryIdentifier strips backticks in the AST."""
    start = SyntaxService().parse(source)
    node = start.children[0]
    assert isinstance(node, TemporaryAssignment)
    assert isinstance(node.left, TemporaryIdentifier)
    assert node.left.value == name
