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
    BinOp,
    ComplexNumericOp,
    CondExpr,
    Constant,
    Dimension,
    FilterOp,
    GetOp,
    GroupingClause,
    OperationRef,
    ParExpr,
    PersistentAssignment,
    PreconditionItem,
    PropertyReference,
    RenameNode,
    RenameOp,
    Scalar,
    Set,
    Start,
    SubOp,
    TemporaryAssignment,
    TemporaryIdentifier,
    TimeShiftOp,
    UnaryOp,
    VarID,
    VarRef,
    WhereClauseOp,
    WithExpression,
)
from dpmcore.dpm_xl.grammar.generated.dpm_xlParser import dpm_xlParser
from dpmcore.dpm_xl.grammar.generated.dpm_xlParserVisitor import (
    dpm_xlParserVisitor,
)
from dpmcore.dpm_xl.utils.tokens import TABLE_GROUP_PREFIX
from dpmcore.errors import SemanticError


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
        return cast(TerminalNodeImpl, node).symbol.text

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
        expression: AST = self._visit(ctx_list[3])
        return WithExpression(
            partial_selection=partial_selection, expression=expression
        )

    def visitPartialSelect(
        self, ctx: dpm_xlParser.PartialSelectContext
    ) -> VarID:
        return cast(VarID, self._visit(ctx.getChild(1)))

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
        operand: AST = self._visit(ctx_list[2])
        return UnaryOp(op=op, operand=operand)

    def visitCommonAggrOp(
        self, ctx: dpm_xlParser.CommonAggrOpContext
    ) -> AggregationOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        operand: AST | None = None
        grouping_clause: GroupingClause | None = None
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.GroupingClauseContext):
                grouping_clause = self.visitGroupingClause(child)
            elif not isinstance(child, TerminalNodeImpl):
                operand = self._visit(child)

        if operand is None:
            raise RuntimeError(
                "AggregationOp requires an operand; parser produced none"
            )
        return AggregationOp(
            op=op, operand=operand, grouping_clause=grouping_clause
        )

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
        return cast(str, child.symbol.text)

    def visitPropertyCode(self, ctx: dpm_xlParser.PropertyCodeContext) -> str:
        child = ctx.getChild(0)
        return cast(str, child.symbol.text)

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
        shift_number = self._symbol_text(ctx_list[6])
        if len(ctx_list) > 8:
            component = self._visit(ctx_list[8])
        return TimeShiftOp(
            operand=operand,
            component=component,
            period_indicator=period_indicator,
            shift_number=shift_number,
        )

    def visitUnaryStringFunction(
        self, ctx: dpm_xlParser.UnaryStringFunctionContext
    ) -> UnaryOp:
        ctx_list = list(ctx.getChildren())
        op = self._symbol_text(ctx_list[0])
        operand: AST = self._visit(ctx_list[2])
        return UnaryOp(op=op, operand=operand)

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
            property_code, value = self.visitSubExpr(ctx_list[2])
            return SubOp(
                operand=operand, property_code=property_code, value=value
            )
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
    ) -> tuple[str, AST]:
        # SUB propertyCode EQ (literal | select | itemReference)
        ctx_list = list(ctx.getChildren())
        property_code: str = self._visit(ctx_list[1])  # propertyCode
        # ctx_list[2] is EQ
        value: AST = self._visit(
            ctx_list[3]
        )  # literal, select, or itemReference
        return property_code, value

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
        return cast(AST, self._visit(ctx.getChild(1)))

    def visitSetElements(self, ctx: dpm_xlParser.SetElementsContext) -> Set:
        ctx_list = list(ctx.getChildren())
        set_elements: list[AST] = []
        for child in ctx_list:
            if not isinstance(child, TerminalNodeImpl):
                set_elements.append(self._visit(child))
        return Set(children=set_elements)

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
            return Constant(type_="Integer", value=int(value))
        elif type_ == dpm_xlParser.DECIMAL_LITERAL:
            return Constant(type_="Number", value=float(value))
        elif type_ == dpm_xlParser.PERCENT_LITERAL:
            return Constant(
                type_="Number", value=float(value.replace("%", "")) / 100
            )
        elif type_ == dpm_xlParser.STRING_LITERAL:
            value = value[1:-1]
            if value == "null":
                raise SemanticError("0-3")
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
        elif type_ == dpm_xlParser.TIME_PERIOD_LITERAL:
            return Constant(type_="TimePeriod", value=value.replace("#", ""))
        elif type_ == dpm_xlParser.TIME_INTERVAL_LITERAL:
            return Constant(type_="TimeInterval", value=value.replace("#", ""))
        elif type_ == dpm_xlParser.EMPTY_LITERAL:
            value = value[1:-1]
            return Constant(type_="String", value=value)
        elif type_ == dpm_xlParser.NULL_LITERAL:
            return Constant(type_="Null", value=None)
        else:
            raise NotImplementedError

    def visitVarRef(self, ctx: dpm_xlParser.VarRefContext) -> VarRef:
        child = ctx.getChild(0)
        variable = child.symbol.text[1:]
        return VarRef(variable=variable)

    def visitCellRef(self, ctx: dpm_xlParser.CellRefContext) -> VarID | None:
        ctx_list = list(ctx.getChildren())

        child = ctx_list[0]
        if isinstance(child, dpm_xlParser.TableRefContext):
            return self.visitTableRef(child)
        elif isinstance(child, dpm_xlParser.CompRefContext):
            return self.visitCompRef(child)
        return None

    def visitPreconditionElem(
        self, ctx: dpm_xlParser.PreconditionElemContext
    ) -> PreconditionItem:
        child = ctx.getChild(0)
        precondition = child.symbol.text[2:]
        return PreconditionItem(
            variable_id=precondition, variable_code=precondition
        )  # This is not the variable_id but we keep the name for later

    def visitOperationRef(
        self, ctx: dpm_xlParser.OperationRefContext
    ) -> OperationRef:
        child = ctx.getChild(0)
        operation_code = child.symbol.text[1:]
        return OperationRef(operation_code=operation_code)

    def create_var_id(
        self,
        ctx_list: list[Any],
        table: str | None = None,
        is_table_group: bool = False,
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
        )

    def visitTableRef(self, ctx: dpm_xlParser.TableRefContext) -> VarID:
        ctx_list = list(ctx.getChildren())
        table_reference: str = self._visit(ctx_list[0])
        is_group = False
        if table_reference[0] == TABLE_GROUP_PREFIX:
            is_group = True
        return self.create_var_id(
            ctx_list=ctx_list,
            table=table_reference[1:],
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

    def visitDefault(
        self, ctx: dpm_xlParser.DefaultContext
    ) -> Constant | None:
        third = ctx.getChild(2)
        if isinstance(third, TerminalNodeImpl) and third.symbol.text == "null":
            return None
        default_value: Constant = self.visitLiteral(
            cast(dpm_xlParser.LiteralContext, third)
        )
        return default_value

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
        return TemporaryIdentifier(value=value)

    @staticmethod
    def process_cell_element(ctx: Any) -> str:

        child = ctx.getChild(0)
        value: str = child.symbol.text
        return value[1:]
