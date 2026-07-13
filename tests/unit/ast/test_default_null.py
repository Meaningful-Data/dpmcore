"""Regression tests for ``default: null`` parsing in the AST constructor.

Issue #2: ``default: null`` used to return Python ``None`` from
``visitDefault``, which meant the VarID's ``default`` attribute was
indistinguishable from "no default specified". When wrapped in a
``with`` clause that supplied a default, the partial-selection
default leaked through and produced a spurious 3-6 semantic error.

The fix is to materialise ``null`` as an explicit
``Constant(type_="Null", value=None)`` so it survives the
``getattr(node, "default", None) is None`` propagation check.
"""

from dpmcore.dpm_xl.ast.nodes import (
    BinOp,
    CondExpr,
    Constant,
    Start,
    VarID,
    WithExpression,
)
from dpmcore.services.syntax import SyntaxService


def _all_varids(node, out=None):
    if out is None:
        out = []
    if node is None:
        return out
    if isinstance(node, VarID):
        out.append(node)
        return out
    for attr in (
        "children",
        "partial_selection",
        "expression",
        "left",
        "right",
        "operand",
        "condition",
        "then_expr",
        "else_expr",
    ):
        v = getattr(node, attr, None)
        if v is None:
            continue
        if isinstance(v, list):
            for c in v:
                _all_varids(c, out)
        else:
            _all_varids(v, out)
    return out


def test_default_null_parses_as_null_constant():
    """``default: null`` produces ``Constant("Null", None)``, not ``None``."""
    ast = SyntaxService().parse("{tF_00.01, c0010, default: null}")
    varids = _all_varids(ast)
    assert len(varids) == 1
    default = varids[0].default
    assert isinstance(default, Constant)
    assert default.type == "Null"
    assert default.value is None


def test_unspecified_default_is_none():
    """A VarID without a ``default:`` clause keeps ``default = None``."""
    ast = SyntaxService().parse("{tF_00.01, c0010}")
    varids = _all_varids(ast)
    assert len(varids) == 1
    assert varids[0].default is None


def test_default_null_survives_with_clause_propagation():
    """Issue #2 reproduction.

    The inner VarID explicitly opts out of the outer ``default: 0`` by
    declaring ``default: null``. Operand propagation must not replace
    that with the partial selection's Integer default.
    """
    expression = (
        "with {r0010, interval: true, default: 0}: "
        "if {tF_00.01, c0010, default: null} = [eba_qAS:qx2004] "
        "then {tF_18.00.a, c0020} = "
        "{tF_18.00.a, c0056} + {tF_18.00.a, c0057} + "
        "{tF_18.00.a, c0058} endif"
    )
    ast = SyntaxService().parse(expression)

    assert isinstance(ast, Start)
    with_expr = ast.children[0]
    assert isinstance(with_expr, WithExpression)

    # Locate the {tF_00.01, c0010} VarID via the AST shape.
    cond = with_expr.expression
    assert isinstance(cond, CondExpr)
    comparison = cond.condition
    assert isinstance(comparison, BinOp)
    f00_varid = comparison.left
    assert isinstance(f00_varid, VarID)
    assert f00_varid.table == "F_00.01"

    # The key assertion: ``default: null`` is preserved as a Null
    # Constant rather than being silently treated as "no default" and
    # overwritten by the partial selection.
    assert isinstance(f00_varid.default, Constant)
    assert f00_varid.default.type == "Null"
    assert f00_varid.default.value is None


# ---------------------------------------------------------------------------
# Deprecated ``"null"`` string literal (issue #205).
#
# Historical DB releases used ``"null"`` (a string literal containing the
# word ``null``) as a null sentinel. The grammar accepts it and the intent
# is unambiguous, so ``visitLiteral`` now materialises it as a proper
# ``Null`` Constant and emits a deprecation warning instead of aborting
# with ``SemanticError("0-3")``.
# ---------------------------------------------------------------------------


def test_string_literal_null_no_longer_raises_semantic_error():
    """The historical ``"null"`` string literal now parses instead of
    raising ``SemanticError("0-3")`` — the AST construction path from
    the issue's reproducer must complete without an exception.
    """
    from antlr4 import CommonTokenStream, InputStream

    from dpmcore.dpm_xl.ast.constructor import ASTVisitor
    from dpmcore.dpm_xl.grammar.generated.dpm_xlLexer import dpm_xlLexer
    from dpmcore.dpm_xl.grammar.generated.dpm_xlParser import dpm_xlParser

    expression = (
        "with {tB_05.01, default: 0, interval: false}: "
        'if({c0030} != "null") then ({c0040} != "null") endif'
    )
    lexer = dpm_xlLexer(InputStream(expression))
    parser = dpm_xlParser(CommonTokenStream(lexer))
    tree = parser.start()
    ast = ASTVisitor().visit(tree)
    # No exception: an AST was produced.
    assert isinstance(ast, Start)


def test_string_literal_null_produces_null_constant():
    """A bare ``"null"`` string literal in a comparison materialises as a
    ``Constant(type_="Null", value=None)`` — the same shape the bare
    ``null`` keyword produces (see ``test_default_null_parses_as_null_constant``).
    """
    ast = SyntaxService().parse('1 != "null"')
    # Start -> BinOp -> right operand is the deprecated literal.
    binop = ast.children[0]
    assert isinstance(binop, BinOp)
    assert binop.op == "!="
    assert isinstance(binop.right, Constant)
    assert binop.right.type == "Null"
    assert binop.right.value is None


def test_string_literal_null_emits_deprecation_warning_at_parse_time():
    """The deprecation warning is emitted from ``visitLiteral`` during
    AST construction and captured by any active
    :func:`collect_warnings` context — ``SemanticService.validate``
    surrounds its ``parse`` call with such a context so the warning
    reaches ``SemanticResult.warning``.
    """
    from dpmcore.dpm_xl.warning_collector import collect_warnings

    with collect_warnings() as wc:
        SyntaxService().parse('1 != "null"')

    warning = wc.get_combined_warning()
    assert warning is not None
    assert '"null" string literal' in warning
    assert "isnull" in warning


def test_string_literal_null_reproducer_parses_with_warning():
    """Reproducer from issue #205: the historical expression parses
    without raising and every occurrence of ``"null"`` on the parse
    path contributes a deprecation warning to the active collector.
    Semantic validation against a DB is deferred to the integration
    suite; this test only pins the parse-time behaviour.
    """
    from dpmcore.dpm_xl.warning_collector import collect_warnings

    expression = (
        "with {tB_05.01, default: 0, interval: false}: "
        'if({c0030} != "null") then ({c0040} != "null") endif'
    )
    with collect_warnings() as wc:
        SyntaxService().parse(expression)

    warning = wc.get_combined_warning()
    assert warning is not None
    # Two occurrences of ``"null"`` in the source → two warning lines.
    assert warning.count('"null" string literal') == 2
