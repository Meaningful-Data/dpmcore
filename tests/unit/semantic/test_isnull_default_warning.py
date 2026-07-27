"""Tests for the isnull warning on non-null defaults (issue #254).

``isnull(x)`` on a selection with a non-null ``default:`` is
tautologically ``false`` — the default guarantees the operand is never
null. The semantic analyzer emits a warning so the user notices the
modelling mistake instead of silently relying on ``not(...)`` around a
constant.
"""

import contextlib

from dpmcore.dpm_xl.ast.nodes import Constant, ParExpr, UnaryOp, VarID
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.dpm_xl.warning_collector import collect_warnings


def _varid(table="C_34.06", cols=("c0010",), default=None):
    return VarID(
        table=table,
        rows=None,
        cols=list(cols) if cols else None,
        sheets=None,
        interval=None,
        default=default,
    )


def _run_visit(node: UnaryOp) -> list[str]:
    """Run ``visit_UnaryOp`` and return collected semantic warnings.

    ``visit_UnaryOp`` will try to visit the VarID operand against the DB;
    without a session that raises. The isnull warning fires *before* the
    operand is visited, so the downstream error is suppressed here and
    only the collected warnings are inspected.
    """
    analyzer = InputAnalyzer(expression="dummy")
    with collect_warnings() as wc:
        with contextlib.suppress(Exception):
            analyzer.visit_UnaryOp(node)
        return wc.get_warnings()


def test_isnull_warns_when_operand_has_integer_default():
    """``isnull({..., default:0})`` should emit a warning naming the selection."""
    operand = _varid(default=Constant(type_="Integer", value=0))
    node = UnaryOp(op="isnull", operand=operand)

    warnings = _run_visit(node)

    assert any("always false" in w for w in warnings), (
        f"expected an isnull-tautology warning, got {warnings!r}"
    )
    # The message must identify the selection so multiple isnull calls in
    # the same expression yield distinct lines (andres-sole review on
    # PR #255).
    assert any("c0010" in w for w in warnings), (
        f"warning should name the operand columns, got {warnings!r}"
    )


def test_isnull_warns_through_parentheses():
    """``isnull((x))`` — parens around the operand must not defeat the check.

    Regression: the AST wraps the operand in a ``ParExpr`` when the user
    adds redundant parentheses; the naive ``node.operand.default`` lookup
    misses the underlying VarID.
    """
    operand = _varid(default=Constant(type_="Integer", value=0))
    paren = ParExpr(expression=operand)
    node = UnaryOp(op="isnull", operand=paren)

    warnings = _run_visit(node)

    assert any("always false" in w and "c0010" in w for w in warnings), (
        f"expected warning through ParExpr, got {warnings!r}"
    )


def test_isnull_warns_through_nested_parentheses():
    """``isnull(((x)))`` — multiple ParExpr layers must all be unwrapped."""
    operand = _varid(default=Constant(type_="Integer", value=0))
    wrapped = ParExpr(
        expression=ParExpr(expression=ParExpr(expression=operand))
    )
    node = UnaryOp(op="isnull", operand=wrapped)

    warnings = _run_visit(node)

    assert any("always false" in w for w in warnings), (
        f"expected warning through nested ParExpr, got {warnings!r}"
    )


def test_isnull_warning_identifies_distinct_selections():
    """Two isnull calls on different selections yield two distinct warnings.

    Reported by andres-sole on PR #255: a shared boilerplate message
    collapsed to two identical lines in
    ``isnull({c0040}) and isnull({c0130})``. The message must include the
    selection so the two lines differ.
    """
    a = _varid(cols=("c0040",), default=Constant(type_="Integer", value=0))
    b = _varid(cols=("c0130",), default=Constant(type_="Integer", value=0))
    wa = _run_visit(UnaryOp(op="isnull", operand=a))
    wb = _run_visit(UnaryOp(op="isnull", operand=b))

    combined = wa + wb
    assert any("c0040" in w for w in combined)
    assert any("c0130" in w for w in combined)
    # The two messages must not be identical.
    assert wa != wb, (
        f"expected distinct warnings per selection, both were {wa!r}"
    )


def test_isnull_does_not_warn_when_operand_has_null_default():
    """``isnull({..., default:null})`` is a legitimate pattern — no warning."""
    operand = _varid(default=Constant(type_="Null", value=None))
    node = UnaryOp(op="isnull", operand=operand)

    warnings = _run_visit(node)

    assert not any("always false" in w for w in warnings), (
        f"unexpected isnull warning, got {warnings!r}"
    )


def test_isnull_does_not_warn_when_operand_has_no_default():
    """``isnull({..., no default})`` — no warning."""
    node = UnaryOp(op="isnull", operand=_varid(default=None))

    warnings = _run_visit(node)

    assert not any("always false" in w for w in warnings), (
        f"unexpected isnull warning, got {warnings!r}"
    )


def test_non_isnull_unary_op_never_warns():
    """The tautology warning is specific to isnull; other unary ops don't fire it."""
    operand = _varid(default=Constant(type_="Integer", value=0))
    node = UnaryOp(op="not", operand=operand)

    warnings = _run_visit(node)

    assert not any("always false" in w for w in warnings), (
        f"unexpected warning on non-isnull op, got {warnings!r}"
    )
