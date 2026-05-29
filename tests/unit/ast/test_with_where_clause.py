"""Regression test for ``with { } [ where ]: body`` expression parsing.

Bug: ``visitWithExpression`` hard-coded ``ctx_list[3]`` as the body
expression.  When the optional ``[ WHERE expression ]`` block is present,
ctx_list[3] is the WHERE terminal node, not the body.  Visiting a terminal
node returns None, so ``WithExpression.expression`` was None, and the
semantic analyzer then called ``self.visit(None)`` which raised
``NotImplementedError: No visit_NoneType method``.

The fix uses ``ctx_list[-1]`` which is always the body expression.
"""

from dpmcore.dpm_xl.ast.nodes import Start, WithExpression
from dpmcore.services.syntax import SyntaxService


def test_with_where_clause_body_is_not_none() -> None:
    """Body expression of ``with { } [ where ]: body`` must not be None."""
    expression = (
        "with {tR_04.00.a, c*, default: 0, interval: true}"
        " [where qPYB = [eba_qIA:qx2090]]:"
        " {r0100} >= 0"
    )
    ast = SyntaxService().parse(expression)
    assert isinstance(ast, Start)
    with_expr = ast.children[0]
    assert isinstance(with_expr, WithExpression)
    assert with_expr.expression is not None
