"""AST.ASTConstructor.py.
=====================

Description
-----------
Generate an AST based on object of AST.ASTObjects.
"""

from __future__ import annotations

import re
from typing import Any, cast

from antlr4.tree.Tree import TerminalNodeImpl

from dpmcore import errors
from dpmcore.dpm_xl.ast.nodes import (
    AST,
    AggregationOp,
    AnalyticClause,
    AnnualiseOp,
    BinOp,
    ComplexNumericOp,
    CondExpr,
    Constant,
    DateConstructorOp,
    Dimension,
    FilterOp,
    GetOp,
    GroupingClause,
    IntersectSetOp,
    OperationRef,
    OrderItem,
    ParameterRef,
    ParExpr,
    PersistentAssignment,
    PropertyReference,
    RankOp,
    RenameNode,
    RenameOp,
    Scalar,
    Set,
    SetdiffOp,
    SetOfOp,
    Start,
    SubAssignment,
    SubOp,
    SubstrOp,
    SymdiffOp,
    TemporaryAssignment,
    TemporaryIdentifier,
    TimeShiftOp,
    UnaryOp,
    UnionSetOp,
    VarID,
    VarRef,
    WhereClauseOp,
    WindowBoundary,
    WindowClause,
    WithExpression,
)
from dpmcore.dpm_xl.grammar.generated.dpm_xlParser import dpm_xlParser
from dpmcore.dpm_xl.grammar.generated.dpm_xlParserVisitor import (
    dpm_xlParserVisitor,
)
from dpmcore.dpm_xl.utils.tokens import TABLE_GROUP_PREFIX
from dpmcore.dpm_xl.warning_collector import add_semantic_warning
from dpmcore.errors import SemanticError


def _strip_backticks(text: str) -> str:
    if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
        return text[1:-1]
    return text


def _parameter_code(text: str) -> str:
    """Strip the parameter prefix from a ``PARAMETER_REFERENCE`` token.

    The leading ``p`` is always dropped. A single following ``_`` is a cosmetic
    separator (``p_threshold`` -> ``threshold``, ``pthreshold`` -> ``threshold``);
    a backtick-escaped code keeps its inner text verbatim
    (``p`_legacy``` -> ``_legacy``).
    """
    remainder = text[1:]
    if remainder.startswith("`"):
        return _strip_backticks(remainder)
    if remainder.startswith("_"):
        return remainder[1:]
    return remainder


class ASTVisitor(dpm_xlParserVisitor):
    """Class to walk to generate an AST which nodes are defined at AST.ASTObjects.

    The base ``dpm_xlParserVisitor`` lives under ``grammar/generated`` which
    is out-of-scope for this phase; it is treated as untyped. The per-method
    overrides below narrow the return types using ``cast`` around the
    untyped ``self.visit(...)`` calls, because the upstream ANTLR
    ``ParseTreeVisitor.visit`` stub is declared as returning ``None`` even
    though at runtime it returns whatever the subclass visitor returns.
    """

    # ``self.visit`` is declared in the upstream stub as returning ``None``.
    # A thin typed helper gives the real shape: any AST node our visitors
    # produce (plus ``None`` or ``str`` for a few non-AST return flavours).
    def _visit(self, tree: Any) -> Any:
        return cast(Any, super().visit(tree))

    @staticmethod
    def _symbol_text(node: Any) -> str:
        """Extract the token text from a terminal node.

        The ANTLR Python stubs type ``getChild``/iteration as returning the
        base ``ParseTree``, which has no ``symbol`` attribute. At runtime
        these are always ``TerminalNodeImpl`` in the terminal positions we
        read — cast once here so call sites stay readable.
        """
        return str(cast(TerminalNodeImpl, node).symbol.text)

    @staticmethod
    def _int_literal_value(text: str) -> int:
        """Parse both INTEGER_LITERAL formats (plain or parenthesized negatives).

        int() fails on (-5), so this handles both forms.
        """
        if text.startswith("(") and text.endswith(")"):
            return int(text[1:-1])
        return int(text)

    def visitStart(self, ctx: dpm_xlParser.StartContext) -> Start:
        ctx_list = list(ctx.getChildren())

        expression_nodes: list[AST] = []
        expressions = [
            expr
            for expr in ctx_list
            if isinstance(expr, dpm_xlParser.StatementContext)
        ]
        if len(ctx_list) > 3 and isinstance(
            ctx_list[2], dpm_xlParser.StatementsContext
        ):
            statements_list = list(ctx_list[2].getChildren())
            expressions += [
                statement
                for statement in statements_list
                if isinstance(statement, dpm_xlParser.StatementContext)
            ]

        if len(expressions) > 0:
            for expression in expressions:
                expression_nodes.append(self._visit(expression))

        start = Start(children=expression_nodes)
        return start

    def visitExprWithSelection(
        self, ctx: dpm_xlParser.ExprWithSelectionContext
    ) -> WithExpression:
        ctx_list = list(ctx.getChildren())
        partial_selection: VarID = self._visit(ctx_list[1])
        # Body expression is always the last child.  When the optional
        # [WHERE expression] block is present the token count grows by 4,
        # so ctx_list[3] would land on the WHERE terminal rather than the
        # body.  ctx_list[-1] is correct in both cases.
        expression: AST = self._visit(ctx_list[-1])
        return WithExpression(
            partial_selection=partial_selection, expression=expression
        )

    def visitPartialSelect(
        self, ctx: dpm_xlParser.PartialSelectContext
    ) -> VarID:
        return cast(VarID, self._visit(ctx.getChild(1)))

    def visitAssignmentTarget(
        self, ctx: dpm_xlParser.AssignmentTargetContext
    ) -> AST:
        return self._visit(ctx.getChild(1))

    def visitPersistentAssignmentExpression(
        self, ctx: dpm_xlParser.PersistentAssignmentExpressionContext
    ) -> PersistentAssignment:

        ctx_list = list(ctx.getChildren())
        left: AST = self._visit(ctx_list[0])
        op = cast(TerminalNodeImpl, ctx_list[1]).symbol.text
        right: AST = self._visit(ctx_list[2])
        return PersistentAssignment(left=left, op=op, right=right)

    def visitTemporaryAssignmentExpression(
        self, ctx: dpm_xlParser.TemporaryAssignmentExpressionContext
    ) -> TemporaryAssignment:
        ctx_list = list(ctx.getChildren())
        left: AST = self._visit(ctx_list[0])
        op = cast(TerminalNodeImpl, ctx_list[1]).symbol.text
        right: AST = self._visit(ctx_list[2])
        return TemporaryAssignment(left=left, op=op, right=right)

    def visitExpr(self, ctx: dpm_xlParser.ExpressionContext) -> AST | None:
        child = ctx.getChild(0)
        if isinstance(child, dpm_xlParser.ParExprContext):
            return self.visitParExpr(child)
        elif isinstance(child, dpm_xlParser.FuncExprContext):
            return cast(AST, self.visitFuncExpr(child))
        elif isinstance(child, dpm_xlParser.ClauseExprContext):
            return self.visitClauseExpr(child)
        elif isinstance(child, dpm_xlParser.UnaryExprContext):
            return self.visitUnaryExpr(child)
        elif isinstance(child, dpm_xlParser.NotExprContext):
            return self.visitNotExpr(child)
        elif isinstance(child, dpm_xlParser.NumericExprContext):
            return self.visitNumericExpr(child)
        elif isinstance(child, dpm_xlParser.ConcatExprContext):
            return self.visitConcatExpr(child)
        elif isinstance(child, dpm_xlParser.CompExprContext):
            return self.visitCompExpr(child)
        elif isinstance(child, dpm_xlParser.InExprContext):
            return self.visitInExpr(child)
        elif isinstance(child, dpm_xlParser.PropertyReferenceExprContext):
            return self.visitPropertyReferenceExpr(child)
        elif isinstance(child, dpm_xlParser.ItemReferenceExprContext):
            return cast(AST, self.visitItemReferenceExpr(child))
        elif isinstance(child, dpm_xlParser.BoolExprContext):
            return self.visitBoolExpr(child)
        elif isinstance(child, dpm_xlParser.IfExprContext):
            return self.visitIfExpr(child)
        elif isinstance(child, dpm_xlParser.KeyNamesExprContext):
            return self.visitKeyNamesExpr(child)
        elif isinstance(child, dpm_xlParser.LiteralExprContext):
            return cast(AST, self.visitLiteralExpr(child))
        elif isinstance(child, dpm_xlParser.SelectExprContext):
            return cast(AST, self.visitSelectExpr(child))
        elif isinstance(child, dpm_xlParser.SetExprContext):
            return cast(AST, self._visit(child.getChild(0)))
        return None

    def visitParExpr(self, ctx: dpm_xlParser.ParExprContext) -> ParExpr:
        expression: AST = self._visit(ctx.getChild(1))
        return ParExpr(expression=expression)

    def visitUnaryExpr(self, ctx: dpm_xlParser.UnaryExprContext) -> UnaryOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        operand: AST = self._visit(ctx_list[1])
        return UnaryOp(op=op, operand=operand)

    def visitNotExpr(self, ctx: dpm_xlParser.NotExprContext) -> UnaryOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        operand: AST = self._visit(ctx_list[1])
        if isinstance(operand, ParExpr):
            operand = operand.expression
        return UnaryOp(op=op, operand=operand)

    def visitCommonAggrOp(
        self, ctx: dpm_xlParser.CommonAggrOpContext
    ) -> AggregationOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        operand: AST | None = None
        grouping_clause: GroupingClause | None = None
        analytic_clause: AnalyticClause | None = None
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.GroupingClauseContext):
                grouping_clause = self.visitGroupingClause(child)
            elif isinstance(child, dpm_xlParser.AnalyticClauseContext):
                analytic_clause = self.visitAnalyticClause(child)
            elif not isinstance(child, TerminalNodeImpl):
                operand = self._visit(child)

        if operand is None:
            raise RuntimeError(
                "AggregationOp requires an operand; parser produced none"
            )
        return AggregationOp(
            op=op,
            operand=operand,
            grouping_clause=grouping_clause,
            analytic_clause=analytic_clause,
        )

    def visitRankOp(self, ctx: dpm_xlParser.RankOpContext) -> RankOp:
        ctx_list = list(ctx.getChildren())
        operand: AST | None = None
        analytic_clause: AnalyticClause | None = None
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.AnalyticClauseContext):
                analytic_clause = self.visitAnalyticClause(child)
            elif not isinstance(child, TerminalNodeImpl):
                operand = self._visit(child)
        if operand is None:
            raise RuntimeError(
                "RankOp requires an operand; parser produced none"
            )
        if analytic_clause is None:
            raise RuntimeError(
                "RankOp requires an analytic clause; parser produced none"
            )
        return RankOp(operand=operand, analytic_clause=analytic_clause)

    def visitAnalyticClause(
        self, ctx: dpm_xlParser.AnalyticClauseContext
    ) -> AnalyticClause:
        ctx_list = list(ctx.getChildren())
        partition_by: list[str] = []
        order_by: list[OrderItem] = []
        window: WindowClause | None = None
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.PartitionClauseContext):
                partition_by = self.visitPartitionClause(child)
            elif isinstance(child, dpm_xlParser.OrderClauseContext):
                order_by = self.visitOrderClause(child)
            elif isinstance(child, dpm_xlParser.WindowClauseContext):
                window = self.visitWindowClause(child)
        return AnalyticClause(
            partition_by=partition_by, order_by=order_by, window=window
        )

    def visitPartitionClause(
        self, ctx: dpm_xlParser.PartitionClauseContext
    ) -> list[str]:
        ctx_list = list(ctx.getChildren())
        return [
            self._visit(child)
            for child in ctx_list
            if isinstance(child, dpm_xlParser.KeyNamesContext)
        ]

    def visitOrderClause(
        self, ctx: dpm_xlParser.OrderClauseContext
    ) -> list[OrderItem]:
        ctx_list = list(ctx.getChildren())
        return [
            self.visitOrderItem(child)
            for child in ctx_list
            if isinstance(child, dpm_xlParser.OrderItemContext)
        ]

    def visitOrderItem(self, ctx: dpm_xlParser.OrderItemContext) -> OrderItem:
        ctx_list = list(ctx.getChildren())
        key_name: str = self._visit(ctx_list[0])
        direction = "asc"
        for child in ctx_list[1:]:
            if isinstance(child, TerminalNodeImpl):
                text = self._symbol_text(child)
                if text in ("asc", "desc"):
                    direction = text
        return OrderItem(key_name=key_name, direction=direction)

    def visitWindowClause(
        self, ctx: dpm_xlParser.WindowClauseContext
    ) -> WindowClause:
        ctx_list = list(ctx.getChildren())
        # (DATA_POINTS|RANGE) BETWEEN windowBoundary AND windowBoundary
        frame_text = self._symbol_text(ctx_list[0])
        frame_type = "data_points" if frame_text == "data points" else "range"
        boundaries = [
            self.visitWindowBoundary(child)
            for child in ctx_list
            if isinstance(child, dpm_xlParser.WindowBoundaryContext)
        ]
        return WindowClause(
            frame_type=frame_type, start=boundaries[0], end=boundaries[1]
        )

    def visitWindowBoundary(
        self, ctx: dpm_xlParser.WindowBoundaryContext
    ) -> WindowBoundary:
        ctx_list = list(ctx.getChildren())
        first = self._symbol_text(ctx_list[0])
        if first == "unbounded":
            second = self._symbol_text(ctx_list[1])
            bound_type = (
                "unbounded_preceding"
                if second == "preceding"
                else "unbounded_following"
            )
            return WindowBoundary(bound_type=bound_type)
        elif first == "current data point":
            return WindowBoundary(bound_type="current_data_point")
        else:
            # INTEGER_LITERAL n preceding|following
            n = int(first)
            second = self._symbol_text(ctx_list[1])
            bound_type = (
                "n_preceding" if second == "preceding" else "n_following"
            )
            return WindowBoundary(bound_type=bound_type, n=n)

    def visitGroupingClause(
        self, ctx: dpm_xlParser.GroupingClauseContext
    ) -> GroupingClause:
        ctx_list = list(ctx.getChildren())
        components: list[str] = [
            self._visit(child)
            for child in ctx_list
            if isinstance(child, dpm_xlParser.KeyNamesContext)
        ]
        return GroupingClause(components=components)

    def visitKeyNames(self, ctx: dpm_xlParser.KeyNamesContext) -> str:
        child = ctx.getChild(0)
        text = cast(str, child.symbol.text)
        if text.startswith("`"):  # strip backtick escaping (`sum` to sum)
            return text[1:-1]
        return text

    def visitPropertyCode(self, ctx: dpm_xlParser.PropertyCodeContext) -> str:
        child = ctx.getChild(0)
        text = cast(str, child.symbol.text)
        if text.startswith("`"):  # strip backtick escaping (`sum` to sum)
            return text[1:-1]
        return text

    def visitUnaryNumericFunctions(
        self, ctx: dpm_xlParser.UnaryNumericFunctionsContext
    ) -> UnaryOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        operand: AST = self._visit(ctx_list[2])
        return UnaryOp(op=op, operand=operand)

    def visitBinaryNumericFunctions(
        self, ctx: dpm_xlParser.BinaryNumericFunctionsContext
    ) -> BinOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        left: AST = self._visit(ctx_list[2])
        right: AST = self._visit(ctx_list[4])
        return BinOp(op=op, left=left, right=right)

    def visitComplexNumericFunctions(
        self, ctx: dpm_xlParser.ComplexNumericFunctionsContext
    ) -> ComplexNumericOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        operands: list[AST] = []
        for child in ctx_list:
            if not isinstance(child, TerminalNodeImpl):
                operands.append(self._visit(child))
        return ComplexNumericOp(op=op, operands=operands)

    def visitMatchExpr(self, ctx: dpm_xlParser.MatchExprContext) -> BinOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        left: AST = self._visit(ctx_list[2])
        pattern: Constant = self.visitLiteral(
            cast(dpm_xlParser.LiteralContext, ctx_list[4])
        )
        try:
            re.compile(pattern.value)
        except re.error as error:
            raise errors.SyntaxError_(code="0-1", message=error.msg)
        return BinOp(left=left, op=op, right=pattern)

    def visitIsnullExpr(self, ctx: dpm_xlParser.IsnullExprContext) -> UnaryOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        operand: AST = self._visit(ctx_list[2])
        return UnaryOp(op=op, operand=operand)

    def visitFilterOperators(
        self, ctx: dpm_xlParser.FilterOperatorsContext
    ) -> FilterOp:
        ctx_list = list(ctx.getChildren())
        selection: AST = self._visit(ctx_list[2])
        condition: AST = self._visit(ctx_list[4])
        return FilterOp(selection=selection, condition=condition)

    def visitNvlFunction(self, ctx: dpm_xlParser.NvlFunctionContext) -> BinOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        left: AST = self._visit(ctx_list[2])
        right: AST = self._visit(ctx_list[4])
        return BinOp(op=op, left=left, right=right)

    def visitTimeShiftFunction(
        self, ctx: dpm_xlParser.TimeShiftFunctionContext
    ) -> TimeShiftOp:
        ctx_list = list(ctx.getChildren())
        operand: AST = self._visit(ctx_list[2])
        component: str | None = None
        period_indicator = self._symbol_text(ctx_list[4])
        shift_number = self._visit(ctx_list[6])
        if len(ctx_list) > 8:
            component = self._visit(ctx_list[8])
        return TimeShiftOp(
            operand=operand,
            component=component,
            period_indicator=period_indicator,
            shift_number=shift_number,
        )

    def visitAnnualiseFunction(
        self, ctx: dpm_xlParser.AnnualiseFunctionContext
    ) -> AnnualiseOp:
        ctx_list = list(ctx.getChildren())
        # ANNUALISE ( op , fyEnd , var )
        #     0     1  2 3   4   5  6  7
        operand: AST = self._visit(ctx_list[2])
        fy_end: AST = self._visit(ctx_list[4])
        component: str = self._visit(ctx_list[6])
        return AnnualiseOp(operand=operand, fy_end=fy_end, component=component)

    def visitDateExtractFunction(
        self, ctx: dpm_xlParser.DateExtractFunctionContext
    ) -> UnaryOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        operand: AST = self._visit(ctx_list[2])
        return UnaryOp(op=op, operand=operand)

    def visitDateConstructorFunction(
        self, ctx: dpm_xlParser.DateConstructorFunctionContext
    ) -> DateConstructorOp:
        ctx_list = list(ctx.getChildren())
        # DATE ( year , month , day )
        #  0   1  2  3   4   5  6  7
        return DateConstructorOp(
            year=self._visit(ctx_list[2]),
            month=self._visit(ctx_list[4]),
            day=self._visit(ctx_list[6]),
        )

    def visitUnaryStringFunction(
        self, ctx: dpm_xlParser.UnaryStringFunctionContext
    ) -> UnaryOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        operand: AST = self._visit(ctx_list[2])
        return UnaryOp(op=op, operand=operand)

    def visitSubstrFunction(
        self, ctx: dpm_xlParser.SubstrFunctionContext
    ) -> SubstrOp:
        ctx_list = list(ctx.getChildren())
        # SUBSTR ( operand , start , length )
        #   0    1    2    3   4   5   6    7
        operand: AST = self._visit(ctx_list[2])
        start = (
            self._int_literal_value(self._symbol_text(ctx_list[4]))
            if len(ctx_list) >= 6
            else None
        )
        length = (
            self._int_literal_value(self._symbol_text(ctx_list[6]))
            if len(ctx_list) >= 8
            else None
        )
        return SubstrOp(operand=operand, start=start, length=length)

    def visitClauseExpr(
        self, ctx: dpm_xlParser.ClauseExprContext
    ) -> AST | None:
        ctx_list = list(ctx.getChildren())
        operand: AST = self._visit(ctx_list[0])
        if isinstance(ctx_list[2], dpm_xlParser.WhereExprContext):
            condition: AST = self.visitWhereExpr(ctx_list[2])
            return WhereClauseOp(operand=operand, condition=condition)
        elif isinstance(ctx_list[2], dpm_xlParser.GetExprContext):
            component: str = self.visitGetExpr(ctx_list[2])
            return GetOp(operand=operand, component=component)
        elif isinstance(ctx_list[2], dpm_xlParser.RenameExprContext):
            rename_nodes = self.visitRenameExpr(ctx_list[2])
            return RenameOp(operand=operand, rename_nodes=rename_nodes)
        elif isinstance(ctx_list[2], dpm_xlParser.SubExprContext):
            substitutions = self.visitSubExpr(ctx_list[2])
            return SubOp(operand=operand, substitutions=substitutions)
        return None

    def visitWhereExpr(self, ctx: dpm_xlParser.WhereExprContext) -> AST:
        return cast(AST, self._visit(ctx.getChild(1)))

    def visitGetExpr(self, ctx: dpm_xlParser.GetExprContext) -> str:
        return cast(str, self._visit(ctx.getChild(1)))

    def visitRenameExpr(
        self, ctx: dpm_xlParser.RenameExprContext
    ) -> list[RenameNode]:
        ctx_list = list(ctx.getChildren())
        rename_nodes: list[RenameNode] = []
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.RenameClauseContext):
                rename_nodes.append(self._visit(child))
        return rename_nodes

    def visitRenameClause(
        self, ctx: dpm_xlParser.RenameClauseContext
    ) -> RenameNode:
        ctx_list = list(ctx.getChildren())
        old_name: str = self._visit(ctx_list[0])
        new_name: str = self._visit(ctx_list[2])
        return RenameNode(old_name=old_name, new_name=new_name)

    def visitSubExpr(
        self, ctx: dpm_xlParser.SubExprContext
    ) -> list[SubAssignment]:
        substitutions: list[SubAssignment] = []
        for child in ctx.getChildren():
            if isinstance(child, dpm_xlParser.SubAssignmentContext):
                substitutions.append(self._visit(child))
        return substitutions

    def visitSubAssignment(
        self, ctx: dpm_xlParser.SubAssignmentContext
    ) -> SubAssignment:
        ctx_list = list(ctx.getChildren())
        property_code: str = self._visit(ctx_list[0])
        value: AST = self._visit(ctx_list[2])
        return SubAssignment(property_code=property_code, value=value)

    def create_bin_op(self, ctx: dpm_xlParser.ExpressionContext) -> BinOp:
        ctx_list = list(ctx.getChildren())

        left: AST = self._visit(ctx_list[0])
        if isinstance(ctx_list[1], dpm_xlParser.ComparisonOperatorsContext):
            op = self.visitComparisonOperators(ctx_list[1])
        else:
            op = self._symbol_text(ctx_list[1])
        right: AST = self._visit(ctx_list[2])

        return BinOp(left=left, op=op, right=right)

    def visitSelect(self, ctx: dpm_xlParser.SelectContext) -> AST:
        return cast(AST, self._visit(ctx.getChild(1)))

    def visitParameterRef(
        self, ctx: dpm_xlParser.ParameterRefContext
    ) -> ParameterRef:
        ctx_list = list(ctx.getChildren())
        code = _parameter_code(self._symbol_text(ctx_list[0]))
        # parameterType holds a single keyword terminal (e.g. ``number`` or
        # ``set-item``); the grammar restricts it to the 12 supported types.
        # ``is_set`` is derived from this keyword on the node itself.
        param_type = self._symbol_text(ctx_list[2].getChild(0))
        default: AST | None = None
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.DefaultContext):
                default = self.visitDefault(child)
        return ParameterRef(
            code=code,
            param_type=param_type,
            default=default,
        )

    def visitComparisonOperators(
        self, ctx: dpm_xlParser.ComparisonOperatorsContext
    ) -> str:
        child = ctx.getChild(0)
        return cast(str, child.symbol.text)

    def visitNumericExpr(self, ctx: dpm_xlParser.NumericExprContext) -> BinOp:
        return self.create_bin_op(ctx)

    def visitConcatExpr(self, ctx: dpm_xlParser.ConcatExprContext) -> BinOp:
        return self.create_bin_op(ctx)

    def visitCompExpr(self, ctx: dpm_xlParser.CompExprContext) -> BinOp:
        return self.create_bin_op(ctx)

    def visitIfExpr(self, ctx: dpm_xlParser.IfExprContext) -> CondExpr:
        ctx_list = list(ctx.getChildren())
        condition: AST = self._visit(ctx_list[1])
        then_expr: AST = self._visit(ctx_list[3])
        else_expr: AST | None = (
            self._visit(ctx_list[5]) if len(ctx_list) > 5 else None
        )
        return CondExpr(
            condition=condition, then_expr=then_expr, else_expr=else_expr
        )

    def visitInExpr(self, ctx: dpm_xlParser.InExprContext) -> BinOp:
        ctx_list = list(ctx.getChildren())
        left: AST = self._visit(ctx_list[0])
        op = self._symbol_text(ctx_list[1])
        right: AST = self._visit(ctx_list[2])
        return BinOp(left=left, op=op, right=right)

    def visitSetOperand(self, ctx: dpm_xlParser.SetOperandContext) -> AST:
        for child in ctx.getChildren():
            if isinstance(child, dpm_xlParser.SetElementsContext):
                return cast(AST, self._visit(child))
        return Set(children=[])

    def visitSetElements(
        self, ctx: dpm_xlParser.SetElementsContext
    ) -> Set | ParameterRef:
        ctx_list = list(ctx.getChildren())
        set_elements: list[AST] = []
        for child in ctx_list:
            if not isinstance(child, TerminalNodeImpl):
                set_elements.append(self._visit(child))
        # A set parameter used as the RHS of ``in`` is a single ParameterRef,
        # not a literal/item set — return it bare so the semantic pass turns it
        # into a ScalarSet (visit_Set only handles Constant/Scalar children).
        if len(set_elements) == 1 and isinstance(
            set_elements[0], ParameterRef
        ):
            return set_elements[0]
        return Set(children=set_elements)

    def visitSetLiteralExpr(
        self, ctx: dpm_xlParser.SetLiteralExprContext
    ) -> AST:
        return cast(AST, self._visit(ctx.getChild(0)))

    def visitSetOfExpr(self, ctx: dpm_xlParser.SetOfExprContext) -> SetOfOp:
        return SetOfOp(operand=self._visit(ctx.getChild(2)))

    def visitUnionSetExpr(
        self, ctx: dpm_xlParser.UnionSetExprContext
    ) -> UnionSetOp:
        operands = [
            self._visit(child)
            for child in ctx.getChildren()
            if isinstance(child, dpm_xlParser.ExpressionContext)
        ]
        return UnionSetOp(operands=operands)

    def visitIntersectSetExpr(
        self, ctx: dpm_xlParser.IntersectSetExprContext
    ) -> IntersectSetOp:
        operands = [
            self._visit(child)
            for child in ctx.getChildren()
            if isinstance(child, dpm_xlParser.ExpressionContext)
        ]
        return IntersectSetOp(operands=operands)

    def visitSetdiffSetExpr(
        self, ctx: dpm_xlParser.SetdiffSetExprContext
    ) -> SetdiffOp:
        set_exprs = [
            child
            for child in ctx.getChildren()
            if isinstance(child, dpm_xlParser.ExpressionContext)
        ]
        return SetdiffOp(
            left=self._visit(set_exprs[0]), right=self._visit(set_exprs[1])
        )

    def visitSymdiffSetExpr(
        self, ctx: dpm_xlParser.SymdiffSetExprContext
    ) -> SymdiffOp:
        set_exprs = [
            child
            for child in ctx.getChildren()
            if isinstance(child, dpm_xlParser.ExpressionContext)
        ]
        return SymdiffOp(
            left=self._visit(set_exprs[0]), right=self._visit(set_exprs[1])
        )

    def visitItemReference(
        self, ctx: dpm_xlParser.ItemReferenceContext
    ) -> Scalar:
        item: str = self._visit(ctx.getChild(1))
        return Scalar(item=item, scalar_type="Item")

    def visitItemSignature(
        self, ctx: dpm_xlParser.ItemSignatureContext
    ) -> str:
        ctx_list = list(ctx.getChildren())
        return "".join([child.symbol.text for child in ctx_list])

    def visitBoolExpr(self, ctx: dpm_xlParser.BoolExprContext) -> BinOp:
        return self.create_bin_op(ctx)

    def visitPropertyReferenceExpr(
        self, ctx: dpm_xlParser.PropertyReferenceExprContext
    ) -> AST:
        return cast(AST, self._visit(ctx.getChild(0)))

    def visitPropertyReference(
        self, ctx: dpm_xlParser.PropertyReferenceContext
    ) -> PropertyReference:
        code: str = self._visit(ctx.getChild(1))
        return PropertyReference(code=code)

    def visitItemReferenceExpr(
        self, ctx: dpm_xlParser.ItemReferenceExprContext
    ) -> Any:
        return self.visitChildren(ctx)

    def visitLiteral(self, ctx: dpm_xlParser.LiteralContext) -> Constant:

        if not hasattr(ctx, "children"):
            symbol = ctx.symbol
            if symbol.text == "null":
                return Constant(type_="Null", value=None)

        token = ctx.getChild(0).symbol
        value = token.text
        type_ = token.type

        if type_ == dpm_xlParser.INTEGER_LITERAL:
            return Constant(
                type_="Integer", value=self._int_literal_value(value)
            )
        elif type_ == dpm_xlParser.DECIMAL_LITERAL:
            return Constant(type_="Number", value=float(value))
        elif type_ == dpm_xlParser.PERCENT_LITERAL:
            return Constant(
                type_="Number", value=float(value.replace("%", "")) / 100
            )
        elif type_ == dpm_xlParser.STRING_LITERAL:
            value = value[1:-1]
            if value == "null":
                # Historical DPM-XL expressions shipped in older DB releases
                # used the string literal ``"null"`` as a null sentinel. The
                # grammar accepts it and the intent is unambiguous, so treat
                # it as a proper Null Constant and surface a deprecation
                # warning instead of aborting semantic analysis.
                add_semantic_warning(
                    'Deprecated use of the "null" string literal; '
                    "prefer the ``isnull(...)`` function or the bare "
                    "``null`` keyword."
                )
                return Constant(type_="Null", value=None)
            return Constant(type_="String", value=value)
        elif type_ == dpm_xlParser.BOOLEAN_LITERAL:
            constant_value: bool
            if value == "true":
                constant_value = True
            elif value == "false":
                constant_value = False
            else:
                raise NotImplementedError
            return Constant(type_="Boolean", value=constant_value)
        elif type_ == dpm_xlParser.DATE_LITERAL:
            return Constant(type_="Date", value=value.replace("#", ""))
        elif type_ == dpm_xlParser.EMPTY_LITERAL:
            value = value[1:-1]
            return Constant(type_="String", value=value)
        elif type_ == dpm_xlParser.NULL_LITERAL:
            return Constant(type_="Null", value=None)
        else:
            raise NotImplementedError

    @staticmethod
    def _strip_ref_code(raw: str) -> str:
        raw = raw.removeprefix("_")
        if raw.startswith("`") and raw.endswith("`"):
            raw = raw[1:-1]
        return raw

    def visitVarRef(self, ctx: dpm_xlParser.VarRefContext) -> VarRef:
        child = ctx.getChild(0)
        text = child.symbol.text
        return VarRef(variable=self._strip_ref_code(text[1:]))

    def visitCellRef(self, ctx: dpm_xlParser.CellRefContext) -> VarID | None:
        ctx_list = list(ctx.getChildren())

        child = ctx_list[0]
        if isinstance(child, dpm_xlParser.TableRefContext):
            return self.visitTableRef(child)
        elif isinstance(child, dpm_xlParser.OpRefContext):
            return self.visitOpRef(child)
        elif isinstance(child, dpm_xlParser.CompRefContext):
            return self.visitCompRef(child)
        return None

    def visitOpRef(self, ctx: dpm_xlParser.OpRefContext) -> VarID:
        ctx_list = list(ctx.getChildren())
        operation_ref: OperationRef = self._visit(ctx_list[0])
        return self.create_var_id(
            ctx_list=ctx_list,
            operation=operation_ref.operation_code,
        )

    def visitOperationRef(
        self, ctx: dpm_xlParser.OperationRefContext
    ) -> OperationRef:
        child = ctx.getChild(0)
        operation_code = self._strip_ref_code(child.symbol.text[1:])
        return OperationRef(operation_code=operation_code)

    def create_var_id(
        self,
        ctx_list: list[Any],
        table: str | None = None,
        is_table_group: bool = False,
        operation: str | None = None,
    ) -> VarID:
        rows: list[str] | None = None
        cols: list[str] | None = None
        sheets: list[str] | None = None
        interval: bool | None = None
        default: AST | None = None
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.RowArgContext):
                if rows is not None:
                    raise errors.SemanticError("0-2", argument="rows")
                rows = self.visitRowArg(child)
            elif isinstance(child, dpm_xlParser.ColArgContext):
                if cols is not None:
                    raise errors.SemanticError("0-2", argument="columns")
                cols = self.visitColArg(child)
            elif isinstance(child, dpm_xlParser.SheetArgContext):
                if sheets is not None:
                    raise errors.SemanticError("0-2", argument="sheets")
                sheets = self.visitSheetArg(child)
            elif isinstance(child, dpm_xlParser.IntervalArgContext):
                if interval is not None:
                    raise errors.SemanticError("0-2", argument="interval")
                interval = self.visitIntervalArg(child)
            elif isinstance(child, dpm_xlParser.DefaultArgContext):
                if default is not None:
                    raise errors.SemanticError("0-2", argument="default")
                default = self.visitDefaultArg(child)

        return VarID(
            table=table,
            rows=rows,
            cols=cols,
            sheets=sheets,
            interval=interval,
            default=default,
            is_table_group=is_table_group,
            operation=operation,
        )

    def visitTableRef(self, ctx: dpm_xlParser.TableRefContext) -> VarID:
        ctx_list = list(ctx.getChildren())
        table_reference: str = self._visit(ctx_list[0])
        is_group = False
        if table_reference[0] == TABLE_GROUP_PREFIX:
            is_group = True
        return self.create_var_id(
            ctx_list=ctx_list,
            table=self._strip_ref_code(table_reference[1:]),
            is_table_group=is_group,
        )

    def visitTableReference(
        self, ctx: dpm_xlParser.TableReferenceContext
    ) -> str:
        child = ctx.getChild(0)
        return cast(str, child.symbol.text)

    def visitCompRef(self, ctx: dpm_xlParser.CompRefContext) -> VarID:
        ctx_list = list(ctx.getChildren())
        return self.create_var_id(ctx_list=ctx_list)

    def visitRowHandler(
        self, ctx: dpm_xlParser.RowHandlerContext
    ) -> list[str]:
        ctx_list = list(ctx.getChildren())

        rows: list[str] = []
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.RowElemContext):
                rows.append(self.visitRowElem(child))
            elif isinstance(
                child, TerminalNodeImpl
            ) and child.symbol.text not in (",", "(", ")"):
                rows.append(child.symbol.text[1:])
        return rows

    def visitColHandler(
        self, ctx: dpm_xlParser.ColHandlerContext
    ) -> list[str]:
        ctx_list = list(ctx.getChildren())

        cols: list[str] = []
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.ColElemContext):
                cols.append(self.visitColElem(child))
            elif isinstance(
                child, TerminalNodeImpl
            ) and child.symbol.text not in (",", "(", ")"):
                cols.append(child.symbol.text[1:])
        return cols

    def visitSheetHandler(
        self, ctx: dpm_xlParser.SheetHandlerContext
    ) -> list[str]:
        ctx_list = list(ctx.getChildren())

        sheets: list[str] = []
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.SheetElemContext):
                sheets.append(self.visitSheetElem(child))
            elif isinstance(
                child, TerminalNodeImpl
            ) and child.symbol.text not in (",", "(", ")"):
                sheets.append(child.symbol.text[1:])
        return sheets

    def visitInterval(self, ctx: dpm_xlParser.IntervalContext) -> bool | None:
        interval: bool | None = None
        ctx_list = list(ctx.getChildren())
        symbol_text: str = self._symbol_text(ctx_list[2])
        if symbol_text and symbol_text.lower() == "true":
            interval = True
        if symbol_text and symbol_text.lower() == "false":
            interval = False
        return interval

    def visitDefault(self, ctx: dpm_xlParser.DefaultContext) -> AST:
        third = ctx.getChild(2)
        # DEFAULT COLON NULL_LITERAL — the only terminal at this position.
        if isinstance(third, TerminalNodeImpl):
            return Constant(type_="Null", value=None)
        # Item-typed parameter default: ``default: [ns:code]``.
        if isinstance(third, dpm_xlParser.ItemReferenceContext):
            return self.visitItemReference(third)
        # Set-typed parameter default: ``default: { ... }``.
        if isinstance(third, dpm_xlParser.SetOperandContext):
            return self.visitSetOperand(third)
        return self.visitLiteral(cast(dpm_xlParser.LiteralContext, third))

    def visitRowElem(self, ctx: dpm_xlParser.RowElemContext) -> str:
        return self.process_cell_element(ctx)

    def visitColElem(self, ctx: dpm_xlParser.ColElemContext) -> str:
        return self.process_cell_element(ctx)

    def visitSheetElem(self, ctx: dpm_xlParser.SheetElemContext) -> str:
        return self.process_cell_element(ctx)

    def visitKeyNamesExpr(
        self, ctx: dpm_xlParser.KeyNamesExprContext
    ) -> Dimension:
        child = ctx.getChild(0)
        code: str = self._visit(child)
        return Dimension(dimension_code=code)

    def visitVarID(self, ctx: dpm_xlParser.VarIDContext) -> VarID:
        return cast(VarID, self._visit(ctx.getChild(1)))

    def visitTemporaryIdentifier(
        self, ctx: dpm_xlParser.TemporaryIdentifierContext
    ) -> TemporaryIdentifier:
        child = ctx.getChild(0)
        value = child.symbol.text
        if value.startswith("`"):  # strip backtick escaping (`sum` to sum)
            value = value[1:-1]
        return TemporaryIdentifier(value=value)

    @staticmethod
    def process_cell_element(ctx: Any) -> str:

        child = ctx.getChild(0)
        value: str = child.symbol.text
        return value[1:]
