"""Tests for the isnull warning on non-null defaults (issue #254).

``isnull(x)`` on a selection with a non-null ``default:`` is
tautologically ``false`` — the default guarantees the operand is never
null. The semantic analyzer emits a warning so the user notices the
modelling mistake instead of silently relying on ``not(...)`` around a
constant.
"""

import contextlib

from dpmcore.dpm_xl.ast.nodes import Constant, UnaryOp, VarID
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.dpm_xl.warning_collector import collect_warnings


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
    """``isnull({..., default:0})`` should emit a warning."""
    operand = VarID(
        table="tC_34.06",
        rows=["r0010"],
        cols=["c0010"],
        sheets=None,
        interval=None,
        default=Constant(type_="Integer", value=0),
    )
    node = UnaryOp(op="isnull", operand=operand)

    warnings = _run_visit(node)

    assert any("isnull" in w and "always false" in w for w in warnings), (
        f"expected an isnull-tautology warning, got {warnings!r}"
    )


def test_isnull_does_not_warn_when_operand_has_null_default():
    """``isnull({..., default:null})`` is a legitimate pattern — no warning."""
    operand = VarID(
        table="tC_34.06",
        rows=["r0010"],
        cols=["c0010"],
        sheets=None,
        interval=None,
        default=Constant(type_="Null", value=None),
    )
    node = UnaryOp(op="isnull", operand=operand)

    warnings = _run_visit(node)

    assert not any("always false" in w for w in warnings), (
        f"unexpected isnull warning, got {warnings!r}"
    )


def test_isnull_does_not_warn_when_operand_has_no_default():
    """``isnull({..., no default})`` — no warning."""
    operand = VarID(
        table="tC_34.06",
        rows=["r0010"],
        cols=["c0010"],
        sheets=None,
        interval=None,
        default=None,
    )
    node = UnaryOp(op="isnull", operand=operand)

    warnings = _run_visit(node)

    assert not any("always false" in w for w in warnings), (
        f"unexpected isnull warning, got {warnings!r}"
    )


def test_non_isnull_unary_op_never_warns():
    """The tautology warning is specific to isnull; other unary ops don't fire it."""
    operand = VarID(
        table="tC_34.06",
        rows=["r0010"],
        cols=["c0010"],
        sheets=None,
        interval=None,
        default=Constant(type_="Integer", value=0),
    )
    node = UnaryOp(op="not", operand=operand)

    warnings = _run_visit(node)

    assert not any("always false" in w for w in warnings), (
        f"unexpected warning on non-isnull op, got {warnings!r}"
    )
