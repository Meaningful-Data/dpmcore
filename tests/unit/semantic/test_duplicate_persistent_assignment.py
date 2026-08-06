"""Tests for the duplicate-output guard in InputAnalyzer.visit_Start.

Two independent, top-level assignments to the same ``{cellRef}``/``{varRef}``
must be rejected with error code 6-1 (GitHub issue #289).
"""

import pytest

from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.errors import SemanticError
from dpmcore.services.syntax import SyntaxService

DUPLICATE_TARGET_SCRIPTS = [
    (
        "{tF_01.01, r0010, c0010} <- 1; {tF_01.01, r0010, c0010} <- 2;",
        "F_01.01",
    ),
    ("{vFoo} <- 1; {vFoo} <- 2;", "Foo"),
    (
        "{tF_01.01, r0010, c0010, s0010} <- 1; "
        "{tF_01.01, r0010, c0010, s0010} <- 2;",
        "s0010",
    ),
    ("v1 := {vFoo} <- 1; v2 := {vFoo} <- 2;", "Foo"),
    # Same rows, listed in a different order
    (
        "{tF_01.01, (r0010, r0020), c0010} <- 1; "
        "{tF_01.01, (r0020, r0010), c0010} <- 2;",
        "F_01.01",
    ),
    # Same operation reference, same row/col
    ("{oOp1, r0010, c0010} <- 1; {oOp1, r0010, c0010} <- 2;", "oOp1"),
    # A repeated row in a list is still just that one row
    (
        "{tF_01.01, (r0010, r0010), c0010} <- 1; "
        "{tF_01.01, r0010, c0010} <- 2;",
        "F_01.01",
    ),
]

NON_DUPLICATE_SCRIPTS = [
    # Different cells: distinct outputs, not a duplicate target
    "{tF_01.01, r0010, c0010} <- 1; {tF_01.01, r0020, c0010} <- 2;",
    # Different variable-reference targets
    "{vFoo} <- 1; {vBar} <- 2;",
    # A lone assignment never collides with itself
    "{tF_01.01, r0010, c0010} <- 1;",
    # Different variable-reference targets, both wrapped in a temp assignment
    "v1 := {vFoo} <- 1; v2 := {vBar} <- 2;",
    # Different operation references, same row/col
    "{oOp1, r0010, c0010} <- 1; {oOp2, r0010, c0010} <- 2;",
    # A table and a same-named table group are different targets
    "{gF_01.01, r0010, c0010} <- 1; {tF_01.01, r0010, c0010} <- 2;",
]


@pytest.mark.parametrize(
    ("script", "expected_in_message"), DUPLICATE_TARGET_SCRIPTS
)
def test_duplicate_target_raises_6_1(script, expected_in_message):
    start = SyntaxService().parse(script)

    with pytest.raises(SemanticError) as exc_info:
        InputAnalyzer(expression=script).visit_Start(start)

    assert exc_info.value.code == "6-1"
    assert expected_in_message in str(exc_info.value)


@pytest.mark.parametrize("script", NON_DUPLICATE_SCRIPTS)
def test_distinct_targets_are_not_flagged(script):
    start = SyntaxService().parse(script)

    # No error raised means the guard did not treat these as duplicates
    InputAnalyzer(expression=script).visit_Start(start)
