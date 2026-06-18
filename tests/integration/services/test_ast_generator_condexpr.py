"""Integration regression for if-then(-else) script generation.

``ASTGeneratorService.script`` previously failed for every ``if-then`` /
``if-then-else`` validation with::

    Cannot resolve root operator: AST root 'CondExpr' has no 'op' attribute.

because ``CondExpr`` carries no ``op`` on the stateless serialize path (only
``MLGeneration.visit_CondExpr`` sets it). The downstream engine consumes the
``script`` output, so this blocked a broad slice of the dictionary (DORA,
REM_DBM, ...). These tests pin the fix against the real 4.2.1 dictionary.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from dpmcore.services.ast_generator import ASTGeneratorService

_IF_THEN_OPERATOR_ID = 30  # Operator.Symbol == "if-then-else"


def _latest_expression(session, code: str) -> str:
    """Return the latest-version expression text for an operation code."""
    operation_id = session.execute(
        text("SELECT OperationID FROM Operation WHERE Code = :c"),
        {"c": code},
    ).scalar()
    assert operation_id is not None, f"{code} not in fixture DB"
    return session.execute(
        text(
            "SELECT Expression FROM OperationVersion "
            "WHERE OperationID = :o ORDER BY OperationVID DESC LIMIT 1"
        ),
        {"o": operation_id},
    ).scalar()


@pytest.mark.parametrize(
    ("code", "module_code", "module_version"),
    [
        ("v22581_m", "REM_DBM", "2.3.0"),
        ("v8804_m", "DORA", "1.2.0"),
    ],
)
def test_if_then_validation_generates(
    fixture_session, code, module_code, module_version
):
    """A real if-then validation now generates a CondExpr-rooted script."""
    expression = _latest_expression(fixture_session, code)
    service = ASTGeneratorService(fixture_session)

    result = service.script(
        expressions=[(expression, code)],
        module_code=module_code,
        module_version=module_version,
    )

    assert result["success"], result["error"]
    namespace = next(iter(result["enriched_ast"]))
    operation = result["enriched_ast"][namespace]["operations"][code]
    assert operation["root_operator_id"] == _IF_THEN_OPERATOR_ID
    assert operation["ast"]["class_name"] == "CondExpr"
