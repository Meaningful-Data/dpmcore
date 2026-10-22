"""``isnull`` over never-null operands against the real dictionary (#443).

Each expression below can never make ``isnull`` true by definition, so
semantic validation warns about it. The warning never becomes an error: the
expressions are valid DPM-XL, just pointless.
"""

from __future__ import annotations

import pytest

from dpmcore.services.semantic import SemanticService

RELEASE = "4.2.1"
MARKER = "is always false"
CELL = "{tF_01.01, r0010, c0010}"
ROWS = "{tF_01.01, r0010-0020, c0010}"


@pytest.fixture
def semantic(fixture_session):
    return SemanticService(fixture_session)


def _always_false_warnings(semantic, expression):
    result = semantic.validate(expression, release_code=RELEASE)
    assert result.is_valid, result.error_message
    return [
        line for line in (result.warning or "").splitlines() if MARKER in line
    ]


@pytest.mark.parametrize(
    ("expression", "reason"),
    [
        (f"isnull(count({ROWS}))", "count never returns null"),
        (f"isnull(count({ROWS} group by r))", "count never returns null"),
        (f"isnull((count({ROWS})))", "count never returns null"),
        (f"isnull(nvl({CELL}, 0))", "the nvl fallback can never be null"),
        (f"isnull(isnull({CELL}))", "isnull returns only true or false"),
        (f"isnull(not isnull({CELL}))", "isnull returns only true or false"),
        ("isnull(0)", "operand is a non-null literal"),
        (
            f"isnull(if {CELL} > 0 then 1 else 0 endif)",
            "both if-then-else branches can never be null",
        ),
    ],
)
def test_never_null_operand_warns(semantic, expression, reason):
    warnings = _always_false_warnings(semantic, expression)

    assert len(warnings) == 1
    assert warnings[0].endswith(reason)


@pytest.mark.parametrize(
    "expression",
    [f"isnull({CELL})", f"isnull({CELL} + 1)", f"isnull(nvl({CELL}, {CELL}))"],
)
def test_nullable_operand_does_not_warn(semantic, expression):
    assert _always_false_warnings(semantic, expression) == []
