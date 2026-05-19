# Generated from dpm_xlParser.g4 by ANTLR 4.9.2
from antlr4 import *
if __name__ is not None and "." in __name__:
    from .dpm_xlParser import dpm_xlParser
else:
    from dpm_xlParser import dpm_xlParser

# This class defines a complete generic visitor for a parse tree produced by dpm_xlParser.

class dpm_xlParserVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by dpm_xlParser#start.
    def visitStart(self, ctx:dpm_xlParser.StartContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#statements.
    def visitStatements(self, ctx:dpm_xlParser.StatementsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#exprWithoutAssignment.
    def visitExprWithoutAssignment(self, ctx:dpm_xlParser.ExprWithoutAssignmentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#assignmentExpr.
    def visitAssignmentExpr(self, ctx:dpm_xlParser.AssignmentExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#persistentExpression.
    def visitPersistentExpression(self, ctx:dpm_xlParser.PersistentExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#exprWithoutPartialSelection.
    def visitExprWithoutPartialSelection(self, ctx:dpm_xlParser.ExprWithoutPartialSelectionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#exprWithSelection.
    def visitExprWithSelection(self, ctx:dpm_xlParser.ExprWithSelectionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#partialSelect.
    def visitPartialSelect(self, ctx:dpm_xlParser.PartialSelectContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#temporaryAssignmentExpression.
    def visitTemporaryAssignmentExpression(self, ctx:dpm_xlParser.TemporaryAssignmentExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#persistentAssignmentExpression.
    def visitPersistentAssignmentExpression(self, ctx:dpm_xlParser.PersistentAssignmentExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#funcExpr.
    def visitFuncExpr(self, ctx:dpm_xlParser.FuncExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#itemReferenceExpr.
    def visitItemReferenceExpr(self, ctx:dpm_xlParser.ItemReferenceExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#propertyReferenceExpr.
    def visitPropertyReferenceExpr(self, ctx:dpm_xlParser.PropertyReferenceExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#inExpr.
    def visitInExpr(self, ctx:dpm_xlParser.InExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#keyNamesExpr.
    def visitKeyNamesExpr(self, ctx:dpm_xlParser.KeyNamesExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#concatExpr.
    def visitConcatExpr(self, ctx:dpm_xlParser.ConcatExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#parExpr.
    def visitParExpr(self, ctx:dpm_xlParser.ParExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#unaryExpr.
    def visitUnaryExpr(self, ctx:dpm_xlParser.UnaryExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#notExpr.
    def visitNotExpr(self, ctx:dpm_xlParser.NotExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#selectExpr.
    def visitSelectExpr(self, ctx:dpm_xlParser.SelectExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#numericExpr.
    def visitNumericExpr(self, ctx:dpm_xlParser.NumericExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#literalExpr.
    def visitLiteralExpr(self, ctx:dpm_xlParser.LiteralExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#compExpr.
    def visitCompExpr(self, ctx:dpm_xlParser.CompExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#ifExpr.
    def visitIfExpr(self, ctx:dpm_xlParser.IfExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#clauseExpr.
    def visitClauseExpr(self, ctx:dpm_xlParser.ClauseExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#boolExpr.
    def visitBoolExpr(self, ctx:dpm_xlParser.BoolExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#setOperand.
    def visitSetOperand(self, ctx:dpm_xlParser.SetOperandContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#setElements.
    def visitSetElements(self, ctx:dpm_xlParser.SetElementsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#aggregateFunctions.
    def visitAggregateFunctions(self, ctx:dpm_xlParser.AggregateFunctionsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#numericFunctions.
    def visitNumericFunctions(self, ctx:dpm_xlParser.NumericFunctionsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#comparisonFunctions.
    def visitComparisonFunctions(self, ctx:dpm_xlParser.ComparisonFunctionsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#filterFunctions.
    def visitFilterFunctions(self, ctx:dpm_xlParser.FilterFunctionsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#conditionalFunctions.
    def visitConditionalFunctions(self, ctx:dpm_xlParser.ConditionalFunctionsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#timeFunctions.
    def visitTimeFunctions(self, ctx:dpm_xlParser.TimeFunctionsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#stringFunctions.
    def visitStringFunctions(self, ctx:dpm_xlParser.StringFunctionsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#unaryNumericFunctions.
    def visitUnaryNumericFunctions(self, ctx:dpm_xlParser.UnaryNumericFunctionsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#binaryNumericFunctions.
    def visitBinaryNumericFunctions(self, ctx:dpm_xlParser.BinaryNumericFunctionsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#complexNumericFunctions.
    def visitComplexNumericFunctions(self, ctx:dpm_xlParser.ComplexNumericFunctionsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#matchExpr.
    def visitMatchExpr(self, ctx:dpm_xlParser.MatchExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#isnullExpr.
    def visitIsnullExpr(self, ctx:dpm_xlParser.IsnullExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#filterOperators.
    def visitFilterOperators(self, ctx:dpm_xlParser.FilterOperatorsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#timeShiftFunction.
    def visitTimeShiftFunction(self, ctx:dpm_xlParser.TimeShiftFunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#nvlFunction.
    def visitNvlFunction(self, ctx:dpm_xlParser.NvlFunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#unaryStringFunction.
    def visitUnaryStringFunction(self, ctx:dpm_xlParser.UnaryStringFunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#commonAggrOp.
    def visitCommonAggrOp(self, ctx:dpm_xlParser.CommonAggrOpContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#groupingClause.
    def visitGroupingClause(self, ctx:dpm_xlParser.GroupingClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#itemSignature.
    def visitItemSignature(self, ctx:dpm_xlParser.ItemSignatureContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#itemReference.
    def visitItemReference(self, ctx:dpm_xlParser.ItemReferenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#rowElem.
    def visitRowElem(self, ctx:dpm_xlParser.RowElemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#colElem.
    def visitColElem(self, ctx:dpm_xlParser.ColElemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#sheetElem.
    def visitSheetElem(self, ctx:dpm_xlParser.SheetElemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#rowHandler.
    def visitRowHandler(self, ctx:dpm_xlParser.RowHandlerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#colHandler.
    def visitColHandler(self, ctx:dpm_xlParser.ColHandlerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#sheetHandler.
    def visitSheetHandler(self, ctx:dpm_xlParser.SheetHandlerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#interval.
    def visitInterval(self, ctx:dpm_xlParser.IntervalContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#default.
    def visitDefault(self, ctx:dpm_xlParser.DefaultContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#rowArg.
    def visitRowArg(self, ctx:dpm_xlParser.RowArgContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#colArg.
    def visitColArg(self, ctx:dpm_xlParser.ColArgContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#sheetArg.
    def visitSheetArg(self, ctx:dpm_xlParser.SheetArgContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#intervalArg.
    def visitIntervalArg(self, ctx:dpm_xlParser.IntervalArgContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#defaultArg.
    def visitDefaultArg(self, ctx:dpm_xlParser.DefaultArgContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#select.
    def visitSelect(self, ctx:dpm_xlParser.SelectContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#selectOperand.
    def visitSelectOperand(self, ctx:dpm_xlParser.SelectOperandContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#varID.
    def visitVarID(self, ctx:dpm_xlParser.VarIDContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#cellRef.
    def visitCellRef(self, ctx:dpm_xlParser.CellRefContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#preconditionElem.
    def visitPreconditionElem(self, ctx:dpm_xlParser.PreconditionElemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#varRef.
    def visitVarRef(self, ctx:dpm_xlParser.VarRefContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#operationRef.
    def visitOperationRef(self, ctx:dpm_xlParser.OperationRefContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#tableRef.
    def visitTableRef(self, ctx:dpm_xlParser.TableRefContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#compRef.
    def visitCompRef(self, ctx:dpm_xlParser.CompRefContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#tableReference.
    def visitTableReference(self, ctx:dpm_xlParser.TableReferenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#whereExpr.
    def visitWhereExpr(self, ctx:dpm_xlParser.WhereExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#getExpr.
    def visitGetExpr(self, ctx:dpm_xlParser.GetExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#renameExpr.
    def visitRenameExpr(self, ctx:dpm_xlParser.RenameExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#subExpr.
    def visitSubExpr(self, ctx:dpm_xlParser.SubExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#renameClause.
    def visitRenameClause(self, ctx:dpm_xlParser.RenameClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#comparisonOperators.
    def visitComparisonOperators(self, ctx:dpm_xlParser.ComparisonOperatorsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#literal.
    def visitLiteral(self, ctx:dpm_xlParser.LiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#keyNames.
    def visitKeyNames(self, ctx:dpm_xlParser.KeyNamesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#propertyReference.
    def visitPropertyReference(self, ctx:dpm_xlParser.PropertyReferenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#propertyCode.
    def visitPropertyCode(self, ctx:dpm_xlParser.PropertyCodeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by dpm_xlParser#temporaryIdentifier.
    def visitTemporaryIdentifier(self, ctx:dpm_xlParser.TemporaryIdentifierContext):
        return self.visitChildren(ctx)



del dpm_xlParser