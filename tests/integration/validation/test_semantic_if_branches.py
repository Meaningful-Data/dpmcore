"""Issue #333 — ``if`` branch agreement against the real dictionary.

§8.1.5 of the DPM-XL specification states the rule on key components, not
on the scalar/recordset kind of the branches: ``join(condition, then)`` and
``join(condition, else)`` must carry the same key components. So a scalar
branch pairs with a recordset branch as long as the recordset does not add
a key component the condition lacks (§8.1.7, example 6), while the mismatch
that has to be rejected is a branch reaching outside the condition when the
other cannot follow it there (§8.1.7, examples 5 and 8).
"""

import pytest

from dpmcore.services.semantic import SemanticService

RELEASE = "4.2.1"

MATCHED_JOIN = "same key components once joined with the condition"
NOT_A_BRANCH = "have to be a recordset or a scalar"

# A fully specified cell: its only key components are the global ones, so it
# is scalar-like — the specification calls the comparison of such a cell a
# "Scalar Boolean".
CELL = "{tC_01.00, r0010, c0010}"

# A selection over two rows: it carries the standard ``r`` key component, so
# it reaches outside a single-cell condition.
ROWS = "{tC_17.01.a, (r0010, r0110), c0010}"


@pytest.fixture
def validate(fixture_session):
    service = SemanticService(fixture_session)

    def _validate(expression):
        return service.validate(expression, release_code=RELEASE)

    return _validate


@pytest.mark.parametrize(
    "expression",
    [
        f"if {ROWS} > 0 then {ROWS} else 0 endif",
        f"if {ROWS} > 0 then 0 else {ROWS} endif",
        f"if {ROWS} = 0 then 1 else {ROWS} endif",
        f"if {ROWS} > 0 then 1 else 0 endif",
    ],
    ids=["rows-then", "rows-else", "replace-idiom", "scalar-branches"],
)
def test_a_scalar_branch_pairs_with_the_condition_of_a_recordset(
    validate, expression
):
    """§8.1.7 examples 3 and 6, and the ``if A = x then y else A`` idiom."""
    result = validate(expression)
    assert result.is_valid, result.error_message


@pytest.mark.parametrize(
    "expression",
    [
        f"if {CELL} = 0 then 0.65 else {ROWS} endif",
        f"if {CELL} = 0 then {ROWS} else 0.65 endif",
        f"if 1 = 1 then 0.65 else {ROWS} endif",
    ],
    ids=["scalar-then", "scalar-else", "scalar-condition"],
)
def test_a_branch_reaching_outside_the_condition_is_rejected(
    validate, expression
):
    """§8.1.7 examples 5 and 8 — only the third shape was reported before."""
    result = validate(expression)
    assert not result.is_valid
    assert MATCHED_JOIN in (result.error_message or "")


def test_chained_else_if_with_scalar_branches_is_valid(validate):
    """The shape from the report: every branch is scalar-like, so it holds."""
    result = validate(
        f"if {CELL} = 0 then 0.65 "
        f"else if {CELL} = 1 then 0.70 else 0.725 endif endif"
    )
    assert result.is_valid, result.error_message


def test_chained_else_if_with_a_recordset_branch_is_rejected(validate):
    """The inner ``if`` returns rows, which the outer scalar cannot follow."""
    result = validate(
        f"if {CELL} = 0 then 0.65 "
        f"else if {CELL} = 1 then {ROWS} else {ROWS} endif endif"
    )
    assert not result.is_valid
    assert MATCHED_JOIN in (result.error_message or "")


@pytest.mark.parametrize(
    "expression",
    [
        f"if {CELL} = 0 then 0.65 else {CELL} endif",
        f"if {CELL} = 0 then {CELL} else 0.65 endif",
        f"if {CELL} = 0 then {ROWS} else {ROWS} endif",
        f"if {CELL} = 0 then 0.65 else 0.70 endif",
    ],
    ids=["cell-else", "cell-then", "both-rows", "both-scalars"],
)
def test_agreeing_branches_stay_valid(validate, expression):
    result = validate(expression)
    assert result.is_valid, result.error_message


@pytest.mark.parametrize(
    "expression",
    [
        f"if {CELL} = 0 then {ROWS} endif",
        f'if {CELL} = 0 then {ROWS} else "null" endif',
        f'if {CELL} = 0 then "null" else {ROWS} endif',
    ],
    ids=["omitted-else", "null-else", "null-then"],
)
def test_a_null_branch_admits_a_wider_other_branch(validate, expression):
    """§8.1.5 Null literal exception: a null branch contributes no record."""
    result = validate(expression)
    assert result.is_valid, result.error_message


def test_set_valued_branch_is_a_semantic_error(validate):
    """A set branch surfaced as an internal ``AttributeError`` before."""
    result = validate(f"if {CELL} = 0 then {{1, 2}} else {{3}} endif")
    assert not result.is_valid
    assert NOT_A_BRANCH in (result.error_message or "")
