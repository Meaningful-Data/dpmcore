"""Issue #333 — mismatched ``if`` branches against the real dictionary.

The reported expression chains conditions, which is how the mismatch arises
naturally: a nested ``if`` whose condition is a cell selection returns a
recordset, while a literal branch of the outer ``if`` returns a scalar. The
outer ``if`` then paired a scalar with a recordset and reported nothing,
because the ``4-6-1-3`` check only ran for a scalar condition.
"""

import pytest

from dpmcore.services.semantic import SemanticService

RELEASE = "4.2.1"

# A fully specified cell: its only key components are the global ones, so it
# is scalar-like for the branch rule.
CELL = "{tC_01.00, r0010, c0010}"

# A selection over two rows: it carries the standard ``r`` key component, so
# it is a recordset proper and cannot be paired with a scalar branch.
ROWS = "{tC_17.01.a, (r0010, r0110), c0010}"


@pytest.mark.parametrize(
    "expression",
    [
        f"if {CELL} = 0 then 0.65 else {ROWS} endif",
        f"if {CELL} = 0 then {ROWS} else 0.65 endif",
        f"if 1 = 1 then 0.65 else {ROWS} endif",
    ],
    ids=["scalar-then", "scalar-else", "scalar-condition"],
)
def test_scalar_branch_paired_with_a_recordset_is_rejected(
    fixture_session, expression
):
    """Only the third shape was reported before the fix."""
    result = SemanticService(fixture_session).validate(
        expression, release_code=RELEASE
    )
    assert not result.is_valid
    assert "both recordset or both scalars" in (result.error_message or "")


def test_chained_else_if_with_scalar_branches_is_valid(fixture_session):
    """The shape from the report: every branch is scalar-like, so it holds."""
    expression = (
        f"if {CELL} = 0 then 0.65 "
        f"else if {CELL} = 1 then 0.70 else 0.725 endif endif"
    )
    result = SemanticService(fixture_session).validate(
        expression, release_code=RELEASE
    )
    assert result.is_valid, result.error_message


def test_chained_else_if_with_a_recordset_branch_is_rejected(fixture_session):
    """One row-spanning branch in the chain and the pairing no longer holds."""
    expression = (
        f"if {CELL} = 0 then 0.65 "
        f"else if {CELL} = 1 then {ROWS} else {ROWS} endif endif"
    )
    result = SemanticService(fixture_session).validate(
        expression, release_code=RELEASE
    )
    assert not result.is_valid
    assert "both recordset or both scalars" in (result.error_message or "")


@pytest.mark.parametrize(
    "expression",
    [
        f"if {CELL} = 0 then 0.65 else {CELL} endif",
        f"if {CELL} = 0 then {CELL} else 0.65 endif",
        f"if {CELL} = 0 then {ROWS} else {ROWS} endif",
        f"if {ROWS} > 0 then 0.65 else 0.70 endif",
        f"if {CELL} = 0 then 0.65 else 0.70 endif",
    ],
    ids=[
        "cell-else",
        "cell-then",
        "both-rows",
        "recordset-condition",
        "both-scalars",
    ],
)
def test_agreeing_branches_stay_valid(fixture_session, expression):
    result = SemanticService(fixture_session).validate(
        expression, release_code=RELEASE
    )
    assert result.is_valid, result.error_message


def test_set_valued_branch_is_a_semantic_error(fixture_session):
    """A set branch surfaced as an internal ``AttributeError`` before."""
    result = SemanticService(fixture_session).validate(
        f"if {CELL} = 0 then {{1, 2}} else {{3}} endif", release_code=RELEASE
    )
    assert not result.is_valid
    assert "have to be a recordset or a scalar" in (result.error_message or "")
