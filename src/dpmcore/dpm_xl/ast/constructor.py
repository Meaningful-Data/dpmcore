"""AST.ASTConstructor.py
=====================

Description
-----------
Generate an AST based on object of AST.ASTObjects.
"""

import re

from antlr4.tree.Tree import TerminalNodeImpl

from dpmcore import errors
from dpmcore.dpm_xl.ast.nodes import *
from dpmcore.dpm_xl.grammar.generated.dpm_xlParser import dpm_xlParser
from dpmcore.dpm_xl.grammar.generated.dpm_xlParserVisitor import (
    dpm_xlParserVisitor,
)
from dpmcore.dpm_xl.utils.tokens import TABLE_GROUP_PREFIX
from dpmcore.errors import SemanticError


class ASTVisitor(dpm_xlParserVisitor):
    """Class to walk to generate an AST which nodes are defined at AST.ASTObjects
    """

    def visitStart(self, ctx: dpm_xlParser.StartContext):
        ctx_list = list(ctx.getChildren())

        expression_nodes = []
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
                expression_nodes.append(self.visit(expression))

        start = Start(children=expression_nodes)
        return start

    def visitExprWithSelection(
        self, ctx: dpm_xlParser.ExprWithSelectionContext
    ):
        ctx_list = list(ctx.getChildren())
        partial_selection = self.visit(ctx_list[1])
        expression = self.visit(ctx_list[3])
        return WithExpression(
            partial_selection=partial_selection, expression=expression
        )

    def visitPartialSelect(self, ctx: dpm_xlParser.PartialSelectContext):
        return self.visit(ctx.getChild(1))

    def visitPersistentAssignmentExpression(
        self, ctx: dpm_xlParser.PersistentAssignmentExpressionContext
    ):

        ctx_list = list(ctx.getChildren())
        left = self.visit(ctx_list[0])
        op = ctx_list[1].symbol.text
        right = self.visit(ctx_list[2])
        return PersistentAssignment(left=left, op=op, right=right)

    def visitTemporaryAssignmentExpression(
        self, ctx: dpm_xlParser.TemporaryAssignmentExpressionContext
    ):
        ctx_list = list(ctx.getChildren())
        left = self.visit(ctx_list[0])
        op = ctx_list[1].symbol.text
        right = self.visit(ctx_list[2])
        return TemporaryAssignment(left=left, op=op, right=right)

    def visitExpr(self, ctx: dpm_xlParser.ExpressionContext):
        child = ctx.getChild(0)
        if isinstance(child, dpm_xlParser.ParExprContext):
            return self.visitParExpr(child)
        elif isinstance(child, dpm_xlParser.FuncExprContext):
            return self.visitFuncExpr(child)
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
            return self.visitItemReferenceExpr(child)
        elif isinstance(child, dpm_xlParser.BoolExprContext):
            return self.visitBoolExpr(child)
        elif isinstance(child, dpm_xlParser.IfExprContext):
            return self.visitIfExpr(child)
        elif isinstance(child, dpm_xlParser.KeyNamesExprContext):
            return self.visitKeyNamesExpr(child)
        elif isinstance(child, dpm_xlParser.LiteralExprContext):
            return self.visitLiteralExpr(child)
        elif isinstance(child, dpm_xlParser.SelectExprContext):
            return self.visitSelectExpr(child)

    def visitParExpr(self, ctx: dpm_xlParser.ParExprContext):
        expression = self.visit(ctx.getChild(1))
        return ParExpr(expression=expression)

    def visitUnaryExpr(self, ctx: dpm_xlParser.UnaryExprContext):
        ctx_list = list(ctx.getChildren())
        op = ctx_list[0].symbol.text
        operand = self.visit(ctx_list[1])
        return UnaryOp(op=op, operand=operand)

    def visitNotExpr(self, ctx: dpm_xlParser.NotExprContext):
        ctx_list = list(ctx.getChildren())
        op = ctx_list[0].symbol.text
        operand = self.visit(ctx_list[2])
        return UnaryOp(op=op, operand=operand)

    def visitCommonAggrOp(self, ctx: dpm_xlParser.CommonAggrOpContext):
        ctx_list = list(ctx.getChildren())
        op = ctx_list[0].symbol.text
        operand = None
        grouping_clause = None
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.GroupingClauseContext):
                grouping_clause = self.visitGroupingClause(child)
            elif not isinstance(child, TerminalNodeImpl):
                operand = self.visit(child)

        return AggregationOp(
            op=op, operand=operand, grouping_clause=grouping_clause
        )

    def visitGroupingClause(self, ctx: dpm_xlParser.GroupingClauseContext):
        ctx_list = list(ctx.getChildren())
        components = [
            self.visit(child)
            for child in ctx_list
            if isinstance(child, dpm_xlParser.KeyNamesContext)
        ]
        return GroupingClause(components=components)

    def visitKeyNames(self, ctx: dpm_xlParser.KeyNamesContext):
        return ctx.getChild(0).symbol.text

    def visitPropertyCode(self, ctx: dpm_xlParser.PropertyCodeContext):
        return ctx.getChild(0).symbol.text

    def visitUnaryNumericFunctions(
        self, ctx: dpm_xlParser.UnaryNumericFunctionsContext
    ):
        ctx_list = list(ctx.getChildren())
        op = ctx_list[0].symbol.text
        operand = self.visit(ctx_list[2])
        return UnaryOp(op=op, operand=operand)

    def visitBinaryNumericFunctions(
        self, ctx: dpm_xlParser.BinaryNumericFunctionsContext
    ):
        ctx_list = list(ctx.getChildren())
        op = ctx_list[0].symbol.text
        left = self.visit(ctx_list[2])
        right = self.visit(ctx_list[4])
        return BinOp(op=op, left=left, right=right)

    def visitComplexNumericFunctions(
        self, ctx: dpm_xlParser.ComplexNumericFunctionsContext
    ):
        ctx_list = list(ctx.getChildren())
        op = ctx_list[0].symbol.text
        operands = []
        for child in ctx_list:
            if not isinstance(child, TerminalNodeImpl):
                operands.append(self.visit(child))
        return ComplexNumericOp(op=op, operands=operands)

    def visitMatchExpr(self, ctx: dpm_xlParser.MatchExprContext):
        ctx_list = list(ctx.getChildren())
        op = ctx_list[0].symbol.text
        left = self.visit(ctx_list[2])
        pattern = self.visitLiteral(ctx_list[4])
        try:
            re.compile(pattern.value)
        except re.error as error:
            raise errors.SyntaxError_(code="0-1", message=error.msg)
        return BinOp(left=left, op=op, right=pattern)

    def visitIsnullExpr(self, ctx: dpm_xlParser.IsnullExprContext):
        ctx_list = list(ctx.getChildren())
        op = ctx_list[0].symbol.text
        operand = self.visit(ctx_list[2])
        return UnaryOp(op=op, operand=operand)

    def visitFilterOperators(self, ctx: dpm_xlParser.FilterOperatorsContext):
        ctx_list = list(ctx.getChildren())
        selection = self.visit(ctx_list[2])
        condition = self.visit(ctx_list[4])
        return FilterOp(selection=selection, condition=condition)

    def visitNvlFunction(self, ctx: dpm_xlParser.NvlFunctionContext):
        ctx_list = list(ctx.getChildren())
        op = ctx_list[0].symbol.text
        left = self.visit(ctx_list[2])
        right = self.visit(ctx_list[4])
        return BinOp(op=op, left=left, right=right)

    def visitTimeShiftFunction(
        self, ctx: dpm_xlParser.TimeShiftFunctionContext
    ):
        ctx_list = list(ctx.getChildren())
        operand = self.visit(ctx_list[2])
        component = None
        period_indicator = ctx_list[4].symbol.text
        shift_number = ctx_list[6].symbol.text
        if len(ctx_list) > 8:
            component = self.visit(ctx_list[8])
        return TimeShiftOp(
            operand=operand,
            component=component,
            period_indicator=period_indicator,
            shift_number=shift_number,
        )

    def visitUnaryStringFunction(
        self, ctx: dpm_xlParser.UnaryStringFunctionContext
    ):
        ctx_list = list(ctx.getChildren())
        op = ctx_list[0].symbol.text
        operand = self.visit(ctx_list[2])
        return UnaryOp(op=op, operand=operand)

    def visitClauseExpr(self, ctx: dpm_xlParser.ClauseExprContext):
        ctx_list = list(ctx.getChildren())
        operand = self.visit(ctx_list[0])
        if isinstance(ctx_list[2], dpm_xlParser.WhereExprContext):
            condition = self.visitWhereExpr(ctx_list[2])
            return WhereClauseOp(operand=operand, condition=condition)
        elif isinstance(ctx_list[2], dpm_xlParser.GetExprContext):
            component = self.visitGetExpr(ctx_list[2])
            return GetOp(operand=operand, component=component)
        elif isinstance(ctx_list[2], dpm_xlParser.RenameExprContext):
            rename_nodes = self.visitRenameExpr(ctx_list[2])
            return RenameOp(operand=operand, rename_nodes=rename_nodes)
        elif isinstance(ctx_list[2], dpm_xlParser.SubExprContext):
            property_code, value = self.visitSubExpr(ctx_list[2])
            return SubOp(
                operand=operand, property_code=property_code, value=value
            )

    def visitWhereExpr(self, ctx: dpm_xlParser.WhereExprContext):
        return self.visit(ctx.getChild(1))

    def visitGetExpr(self, ctx: dpm_xlParser.GetExprContext):
        return self.visit(ctx.getChild(1))

    def visitRenameExpr(self, ctx: dpm_xlParser.RenameExprContext):
        ctx_list = list(ctx.getChildren())
        rename_nodes = []
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.RenameClauseContext):
                rename_nodes.append(self.visit(child))
        return rename_nodes

    def visitRenameClause(self, ctx: dpm_xlParser.RenameClauseContext):
        ctx_list = list(ctx.getChildren())
        old_name = self.visit(ctx_list[0])
        new_name = self.visit(ctx_list[2])
        return RenameNode(old_name=old_name, new_name=new_name)

    def visitSubExpr(self, ctx: dpm_xlParser.SubExprContext):
        # SUB propertyCode EQ (literal | select | itemReference)
        ctx_list = list(ctx.getChildren())
        property_code = self.visit(ctx_list[1])  # propertyCode
        # ctx_list[2] is EQ
        value = self.visit(ctx_list[3])  # literal, select, or itemReference
        return property_code, value

    def create_bin_op(self, ctx: dpm_xlParser.ExpressionContext):
        ctx_list = list(ctx.getChildren())

        left = self.visit(ctx_list[0])
        if isinstance(ctx_list[1], dpm_xlParser.ComparisonOperatorsContext):
            op = self.visitComparisonOperators(ctx_list[1])
        else:
            op = ctx_list[1].symbol.text
        right = self.visit(ctx_list[2])

        return BinOp(left=left, op=op, right=right)

    def visitSelect(self, ctx: dpm_xlParser.SelectContext):
        return self.visit(ctx.getChild(1))

    def visitComparisonOperators(
        self, ctx: dpm_xlParser.ComparisonOperatorsContext
    ):
        return ctx.getChild(0).symbol.text

    def visitNumericExpr(self, ctx: dpm_xlParser.NumericExprContext):
        return self.create_bin_op(ctx)

    def visitConcatExpr(self, ctx: dpm_xlParser.ConcatExprContext):
        return self.create_bin_op(ctx)

    def visitCompExpr(self, ctx: dpm_xlParser.CompExprContext):
        return self.create_bin_op(ctx)

    def visitIfExpr(self, ctx: dpm_xlParser.IfExprContext):
        ctx_list = list(ctx.getChildren())
        condition = self.visit(ctx_list[1])
        then_expr = self.visit(ctx_list[3])
        else_expr = self.visit(ctx_list[5]) if len(ctx_list) > 5 else None
        return CondExpr(
            condition=condition, then_expr=then_expr, else_expr=else_expr
        )

    def visitInExpr(self, ctx: dpm_xlParser.InExprContext):
        ctx_list = list(ctx.getChildren())
        left = self.visit(ctx_list[0])
        op = ctx_list[1].symbol.text
        right = self.visit(ctx_list[2])
        return BinOp(left=left, op=op, right=right)

    def visitSetOperand(self, ctx: dpm_xlParser.SetOperandContext):
        return self.visit(ctx.getChild(1))

    def visitSetElements(self, ctx: dpm_xlParser.SetElementsContext):
        ctx_list = list(ctx.getChildren())
        set_elements = []
        for child in ctx_list:
            if not isinstance(child, TerminalNodeImpl):
                set_elements.append(self.visit(child))
        return Set(children=set_elements)

    def visitItemReference(self, ctx: dpm_xlParser.ItemReferenceContext):
        item = self.visit(ctx.getChild(1))
        return Scalar(item=item, scalar_type="Item")

    def visitItemSignature(self, ctx: dpm_xlParser.ItemSignatureContext):
        ctx_list = list(ctx.getChildren())
        return "".join([child.symbol.text for child in ctx_list])

    def visitBoolExpr(self, ctx: dpm_xlParser.BoolExprContext):
        return self.create_bin_op(ctx)

    def visitPropertyReferenceExpr(
        self, ctx: dpm_xlParser.PropertyReferenceExprContext
    ):
        return self.visit(ctx.getChild(0))

    def visitPropertyReference(
        self, ctx: dpm_xlParser.PropertyReferenceContext
    ):
        code = self.visit(ctx.getChild(1))
        return PropertyReference(code=code)

    def visitItemReferenceExpr(
        self, ctx: dpm_xlParser.ItemReferenceExprContext
    ):
        return self.visitChildren(ctx)

    def visitLiteral(self, ctx: dpm_xlParser.LiteralContext):

        if not hasattr(ctx, "children") and ctx.symbol.text == "null":
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

    def visitVarRef(self, ctx: dpm_xlParser.VarRefContext):
        child = ctx.getChild(0)
        variable = child.symbol.text[1:]
        return VarRef(variable=variable)

    def visitCellRef(self, ctx: dpm_xlParser.CellRefContext):
        ctx_list = list(ctx.getChildren())

        child = ctx_list[0]
        if isinstance(child, dpm_xlParser.TableRefContext):
            return self.visitTableRef(child)
        elif isinstance(child, dpm_xlParser.CompRefContext):
            return self.visitCompRef(child)

    def visitPreconditionElem(self, ctx: dpm_xlParser.PreconditionElemContext):
        child = ctx.getChild(0)
        precondition = child.symbol.text[2:]
        return PreconditionItem(
            variable_id=precondition, variable_code=precondition
        )  # This is not the variable_id but we keep the name for later

    def visitOperationRef(self, ctx: dpm_xlParser.OperationRefContext):
        child = ctx.getChild(0)
        operation_code = child.symbol.text[1:]
        return OperationRef(operation_code=operation_code)

    def create_var_id(self, ctx_list: list, table=None, is_table_group=False):
        rows = None
        cols = None
        sheets = None
        interval = None
        default = None
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

    def visitTableRef(self, ctx: dpm_xlParser.TableRefContext):
        ctx_list = list(ctx.getChildren())
        table_reference = self.visit(ctx_list[0])
        is_group = False
        if table_reference[0] == TABLE_GROUP_PREFIX:
            is_group = True
        return self.create_var_id(
            ctx_list=ctx_list,
            table=table_reference[1:],
            is_table_group=is_group,
        )

    def visitTableReference(self, ctx: dpm_xlParser.TableReferenceContext):
        return ctx.getChild(0).symbol.text

    def visitCompRef(self, ctx: dpm_xlParser.CompRefContext):
        ctx_list = list(ctx.getChildren())
        return self.create_var_id(ctx_list=ctx_list)

    def visitRowHandler(self, ctx: dpm_xlParser.RowHandlerContext):
        ctx_list = list(ctx.getChildren())

        rows = []
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.RowElemContext):
                rows.append(self.visitRowElem(child))
            elif isinstance(
                child, TerminalNodeImpl
            ) and child.symbol.text not in (",", "(", ")"):
                rows.append(child.symbol.text[1:])
        return rows

    def visitColHandler(self, ctx: dpm_xlParser.ColHandlerContext):
        ctx_list = list(ctx.getChildren())

        cols = []
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.ColElemContext):
                cols.append(self.visitColElem(child))
            elif isinstance(
                child, TerminalNodeImpl
            ) and child.symbol.text not in (",", "(", ")"):
                cols.append(child.symbol.text[1:])
        return cols

    def visitSheetHandler(self, ctx: dpm_xlParser.SheetHandlerContext):
        ctx_list = list(ctx.getChildren())

        sheets = []
        for child in ctx_list:
            if isinstance(child, dpm_xlParser.SheetElemContext):
                sheets.append(self.visitSheetElem(child))
            elif isinstance(
                child, TerminalNodeImpl
            ) and child.symbol.text not in (",", "(", ")"):
                sheets.append(child.symbol.text[1:])
        return sheets

    def visitInterval(self, ctx: dpm_xlParser.IntervalContext):
        interval = None
        ctx_list = list(ctx.getChildren())
        if (
            ctx_list[2].symbol.text
            and ctx_list[2].symbol.text.lower() == "true"
        ):
            interval = True
        if (
            ctx_list[2].symbol.text
            and ctx_list[2].symbol.text.lower() == "false"
        ):
            interval = False
        return interval

    def visitDefault(self, ctx: dpm_xlParser.DefaultContext):
        if (
            isinstance(ctx.getChild(2), TerminalNodeImpl)
            and ctx.getChild(2).symbol.text == "null"
        ):
            return None
        default_value = self.visitLiteral(ctx.getChild(2))
        return default_value

    def visitRowElem(self, ctx: dpm_xlParser.RowElemContext):
        return self.process_cell_element(ctx)

    def visitColElem(self, ctx: dpm_xlParser.ColElemContext):
        return self.process_cell_element(ctx)

    def visitSheetElem(self, ctx: dpm_xlParser.SheetElemContext):
        return self.process_cell_element(ctx)

    def visitKeyNamesExpr(self, ctx: dpm_xlParser.KeyNamesExprContext):
        child = ctx.getChild(0)
        code = self.visit(child)
        return Dimension(dimension_code=code)

    def visitVarID(self, ctx: dpm_xlParser.VarIDContext):
        return self.visit(ctx.getChild(1))

    def visitTemporaryIdentifier(
        self, ctx: dpm_xlParser.TemporaryIdentifierContext
    ):
        value = ctx.getChild(0).symbol.text
        return TemporaryIdentifier(value=value)

    @staticmethod
    def process_cell_element(ctx):

        child = ctx.getChild(0)
        value = child.symbol.text
        return value[1:]
