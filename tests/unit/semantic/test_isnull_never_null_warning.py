"""Tests for the isnull warning on never-null operands (issue #443).

``isnull(x)`` is always false when ``x`` can never be null by definition:
``count``, ``rank``, ``isnull`` itself, non-null literals, and selections
with a non-null ``default:``, possibly behind a wrapper that keeps that
property. ``never_null_reason`` is driven over hand-built ASTs, and the
analyzer hook is checked to emit one warning per offending ``isnull``.
"""

import contextlib

import pytest

from dpmcore.dpm_xl.ast.nodes import (
    AggregationOp,
    AnalyticClause,
    BinOp,
    CondExpr,
    Constant,
    CountSetOp,
    Dimension,
    GroupingClause,
    OrderItem,
    ParameterRef,
    ParExpr,
    RenameNode,
    RenameOp,
    Scalar,
    SubAssignment,
    SubOp,
    UnaryOp,
    VarID,
    WhereClauseOp,
)
from dpmcore.dpm_xl.ast.nullability import never_null_reason, render_operand
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.dpm_xl.warning_collector import collect_warnings


def _varid(cols=("0010",), default=None):
    return VarID(
        table="C_01.00",
        rows=["0100"],
        cols=list(cols),
        sheets=None,
        interval=None,
        default=default,
    )


def _count(operand=None, grouping=None, analytic=None):
    return AggregationOp(
        op="count",
        operand=operand if operand is not None else _varid(cols=("*",)),
        grouping_clause=grouping,
        analytic_clause=analytic,
    )


def _rank():
    return AggregationOp(
        op="rank",
        operand=_varid(cols=("*",)),
        grouping_clause=None,
        analytic_clause=AnalyticClause(
            partition_by=[], order_by=[OrderItem(key_name="r")], window=None
        ),
    )


def _condition():
    return BinOp(
        left=_varid(), op=">", right=Constant(type_="Integer", value=0)
    )


def _zero():
    return Constant(type_="Integer", value=0)


def _where(operand):
    condition = BinOp(
        left=Dimension(dimension_code="r"),
        op="=",
        right=Constant(type_="String", value="0010"),
    )
    return WhereClauseOp(operand=operand, condition=condition)


def _run_visit(node: UnaryOp) -> list[str]:
    """Run ``visit_UnaryOp`` and return the collected warnings.

    The warning fires before the operand is visited; without a session
    the operand visit raises, so that error is suppressed here.
    """
    analyzer = InputAnalyzer(expression="dummy")
    with collect_warnings() as wc:
        with contextlib.suppress(Exception):
            analyzer.visit_UnaryOp(node)
        return wc.get_warnings()


class TestNeverNull:
    """Operands whose result can never be null by definition."""

    @pytest.mark.parametrize(
        ("operand", "reason"),
        [
            (_count(), "count never returns null"),
            (
                _count(grouping=GroupingClause(components=["r"])),
                "count never returns null",
            ),
            (
                _count(
                    analytic=AnalyticClause(
                        partition_by=["r"], order_by=[], window=None
                    )
                ),
                "count never returns null",
            ),
            (CountSetOp(operand=_varid()), "count never returns null"),
            (_rank(), "rank never returns null"),
            (
                UnaryOp(op="isnull", operand=_varid()),
                "isnull returns only true or false",
            ),
            (_zero(), "operand is a non-null literal"),
            (
                Constant(type_="String", value=""),
                "operand is a non-null literal",
            ),
            (
                Constant(type_="Boolean", value=True),
                "operand is a non-null literal",
            ),
            (
                Scalar(item="eba_qx:x1", scalar_type="Item"),
                "operand is a non-null literal",
            ),
            (
                _varid(default=_zero()),
                "operand has a non-null default (default:0)",
            ),
            (
                ParameterRef(code="x", param_type="number", default=_zero()),
                "operand has a non-null default (default:0)",
            ),
        ],
    )
    def test_reason(self, operand, reason):
        assert never_null_reason(operand) == reason

    @pytest.mark.parametrize(
        "wrap",
        [
            lambda x: ParExpr(expression=x),
            lambda x: ParExpr(expression=ParExpr(expression=x)),
            _where,
            lambda x: RenameOp(
                operand=x,
                rename_nodes=[RenameNode(old_name="r", new_name="x")],
            ),
            lambda x: SubOp(
                operand=x,
                substitutions=[
                    SubAssignment(property_code="qABC", value=_zero())
                ],
            ),
            lambda x: UnaryOp(op="not", operand=x),
        ],
        ids=["paren", "nested-paren", "where", "rename", "sub", "not"],
    )
    def test_wrapper_keeps_the_reason(self, wrap):
        assert never_null_reason(wrap(_count())) == (
            "count never returns null"
        )

    def test_not_isnull(self):
        node = UnaryOp(
            op="not", operand=UnaryOp(op="isnull", operand=_varid())
        )
        assert never_null_reason(node) == "isnull returns only true or false"

    @pytest.mark.parametrize(
        "fallback",
        [_zero(), _count(), _varid(cols=("0020",), default=_zero())],
        ids=["literal", "count", "default"],
    )
    def test_nvl_with_never_null_fallback(self, fallback):
        node = BinOp(left=_varid(), op="nvl", right=fallback)
        assert never_null_reason(node) == "the nvl fallback can never be null"

    def test_if_with_both_branches_never_null(self):
        node = CondExpr(
            condition=_condition(), then_expr=_count(), else_expr=_zero()
        )
        assert never_null_reason(node) == (
            "both if-then-else branches can never be null"
        )

    def test_if_without_else(self):
        node = CondExpr(
            condition=_condition(), then_expr=_zero(), else_expr=None
        )
        assert never_null_reason(node) == (
            "the then branch can never be null and there is no else"
        )


class TestMightBeNull:
    """Operands where nothing in the definitions rules a null out."""

    @pytest.mark.parametrize(
        "operand",
        [
            None,
            _varid(),
            _varid(default=Constant(type_="Null", value=None)),
            ParameterRef(code="x", param_type="number"),
            Constant(type_="Null", value=None),
            AggregationOp(
                op="sum",
                operand=_varid(cols=("*",)),
                grouping_clause=None,
            ),
            UnaryOp(op="abs", operand=_count()),
            UnaryOp(op="not", operand=_varid()),
            BinOp(left=_count(), op="+", right=_zero()),
            BinOp(left=_zero(), op="nvl", right=_varid()),
            CondExpr(
                condition=_condition(), then_expr=_varid(), else_expr=None
            ),
            CondExpr(
                condition=_condition(), then_expr=_zero(), else_expr=_varid()
            ),
            _where(_varid()),
            Dimension(dimension_code="r"),
        ],
        ids=[
            "none",
            "cell-no-default",
            "cell-default-null",
            "parameter-no-default",
            "null-literal",
            "sum",
            "abs-not-propagated",
            "not-over-cell",
            "arithmetic-not-propagated",
            "nvl-nullable-fallback",
            "if-nullable-then",
            "if-nullable-else",
            "where-over-cell",
            "other-node",
        ],
    )
    def test_no_reason(self, operand):
        assert never_null_reason(operand) is None


class TestRenderOperand:
    @pytest.mark.parametrize(
        ("operand", "text"),
        [
            (_count(), "count({ tC_01.00, r0100, c* })"),
            (
                _count(grouping=GroupingClause(components=["r", "s"])),
                "count({ tC_01.00, r0100, c* } group by r, s)",
            ),
            (_rank(), "rank({ tC_01.00, r0100, c* } over (...))"),
            (
                CountSetOp(operand=_varid()),
                "count({ tC_01.00, r0100, c0010 })",
            ),
            (
                UnaryOp(
                    op="not", operand=UnaryOp(op="isnull", operand=_varid())
                ),
                "not isnull({ tC_01.00, r0100, c0010 })",
            ),
            (
                BinOp(left=_varid(), op="nvl", right=_zero()),
                "nvl({ tC_01.00, r0100, c0010 }, 0)",
            ),
            (
                ParExpr(expression=_where(_count())),
                "(count({ tC_01.00, r0100, c* })[where ...])",
            ),
            (
                ParameterRef(code="x", param_type="number"),
                "{p_x, number}",
            ),
            (Constant(type_="String", value="abc"), '"abc"'),
            (Constant(type_="Boolean", value=False), "false"),
            (Scalar(item="eba_qx:x1", scalar_type="Item"), "[eba_qx:x1]"),
            (
                CondExpr(
                    condition=_condition(), then_expr=_zero(), else_expr=None
                ),
                "if ... endif",
            ),
            (BinOp(left=_zero(), op="+", right=_zero()), "..."),
        ],
    )
    def test_render(self, operand, text):
        assert render_operand(operand) == text


class TestAnalyzerWarning:
    def test_warns_on_isnull_of_count(self):
        warnings = _run_visit(UnaryOp(op="isnull", operand=_count()))

        assert warnings == [
            "isnull(count({ tC_01.00, r0100, c* })) is always false: "
            "count never returns null"
        ]

    def test_warning_strips_outer_parentheses(self):
        node = UnaryOp(op="isnull", operand=ParExpr(expression=_count()))

        warnings = _run_visit(node)

        assert warnings[0].startswith("isnull(count(")

    def test_default_message_is_unchanged(self):
        """The #254 wording for a non-null default is kept as is."""
        node = UnaryOp(op="isnull", operand=_varid(default=_zero()))

        assert _run_visit(node) == [
            "isnull({ tC_01.00, r0100, c0010 }) is always false: operand "
            "has a non-null default (default:0)"
        ]

    def test_no_warning_on_nullable_operand(self):
        assert _run_visit(UnaryOp(op="isnull", operand=_varid())) == []

    def test_no_warning_on_other_unary_ops(self):
        assert _run_visit(UnaryOp(op="not", operand=_count())) == []
