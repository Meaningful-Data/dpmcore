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
]

NON_DUPLICATE_SCRIPTS = [
    # Different cells: a dependency/alias, not a duplicate output
    "{tF_01.01, r0010, c0010} <- 1; {tF_01.01, r0020, c0010} <- 2;",
    # Different variable-reference targets
    "{vFoo} <- 1; {vBar} <- 2;",
    # A lone assignment never collides with itself
    "{tF_01.01, r0010, c0010} <- 1;",
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
