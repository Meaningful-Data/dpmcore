"""Tests for rename clause, only propertyCode is accepted on both sides.

Standard key components are not renameable per the spec.
Only property codes are valid in rename clauses.
"""

import pytest
from dpmcore.services.syntax import SyntaxService


VALID_RENAME_FORMS = [
    "{tT_00.01, c0010}[rename myProp to otherProp]",
    "{tT_00.01, c0010}[rename myProp to other, second to third]",
]

INVALID_RENAME_FORMS = [
    "{tT_00.01, c0010}[rename r to myProp]",
    "{tT_00.01, c0010}[rename c to myProp]",
    "{tT_00.01, c0010}[rename s to myProp]",
    "{tT_00.01, c0010}[rename myProp to r]",
]


@pytest.mark.parametrize("source", VALID_RENAME_FORMS)
def test_valid_rename_forms_are_accepted(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", INVALID_RENAME_FORMS)
def test_standard_key_components_are_rejected_in_rename(source):
    assert not SyntaxService().is_valid(source)
