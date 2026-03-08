# Generated from dpm_xlParser.g4 by ANTLR 4.9.2
from antlr4 import *
if __name__ is not None and "." in __name__:
    from .dpm_xlParser import dpm_xlParser
else:
    from dpm_xlParser import dpm_xlParser

# This class defines a complete listener for a parse tree produced by dpm_xlParser.
class dpm_xlParserListener(ParseTreeListener):

    # Enter a parse tree produced by dpm_xlParser#start.
    def enterStart(self, ctx:dpm_xlParser.StartContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#start.
    def exitStart(self, ctx:dpm_xlParser.StartContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#statements.
    def enterStatements(self, ctx:dpm_xlParser.StatementsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#statements.
    def exitStatements(self, ctx:dpm_xlParser.StatementsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#exprWithoutAssignment.
    def enterExprWithoutAssignment(self, ctx:dpm_xlParser.ExprWithoutAssignmentContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#exprWithoutAssignment.
    def exitExprWithoutAssignment(self, ctx:dpm_xlParser.ExprWithoutAssignmentContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#assignmentExpr.
    def enterAssignmentExpr(self, ctx:dpm_xlParser.AssignmentExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#assignmentExpr.
    def exitAssignmentExpr(self, ctx:dpm_xlParser.AssignmentExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#persistentExpression.
    def enterPersistentExpression(self, ctx:dpm_xlParser.PersistentExpressionContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#persistentExpression.
    def exitPersistentExpression(self, ctx:dpm_xlParser.PersistentExpressionContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#exprWithoutPartialSelection.
    def enterExprWithoutPartialSelection(self, ctx:dpm_xlParser.ExprWithoutPartialSelectionContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#exprWithoutPartialSelection.
    def exitExprWithoutPartialSelection(self, ctx:dpm_xlParser.ExprWithoutPartialSelectionContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#exprWithSelection.
    def enterExprWithSelection(self, ctx:dpm_xlParser.ExprWithSelectionContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#exprWithSelection.
    def exitExprWithSelection(self, ctx:dpm_xlParser.ExprWithSelectionContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#partialSelect.
    def enterPartialSelect(self, ctx:dpm_xlParser.PartialSelectContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#partialSelect.
    def exitPartialSelect(self, ctx:dpm_xlParser.PartialSelectContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#temporaryAssignmentExpression.
    def enterTemporaryAssignmentExpression(self, ctx:dpm_xlParser.TemporaryAssignmentExpressionContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#temporaryAssignmentExpression.
    def exitTemporaryAssignmentExpression(self, ctx:dpm_xlParser.TemporaryAssignmentExpressionContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#persistentAssignmentExpression.
    def enterPersistentAssignmentExpression(self, ctx:dpm_xlParser.PersistentAssignmentExpressionContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#persistentAssignmentExpression.
    def exitPersistentAssignmentExpression(self, ctx:dpm_xlParser.PersistentAssignmentExpressionContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#funcExpr.
    def enterFuncExpr(self, ctx:dpm_xlParser.FuncExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#funcExpr.
    def exitFuncExpr(self, ctx:dpm_xlParser.FuncExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#itemReferenceExpr.
    def enterItemReferenceExpr(self, ctx:dpm_xlParser.ItemReferenceExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#itemReferenceExpr.
    def exitItemReferenceExpr(self, ctx:dpm_xlParser.ItemReferenceExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#propertyReferenceExpr.
    def enterPropertyReferenceExpr(self, ctx:dpm_xlParser.PropertyReferenceExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#propertyReferenceExpr.
    def exitPropertyReferenceExpr(self, ctx:dpm_xlParser.PropertyReferenceExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#inExpr.
    def enterInExpr(self, ctx:dpm_xlParser.InExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#inExpr.
    def exitInExpr(self, ctx:dpm_xlParser.InExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#keyNamesExpr.
    def enterKeyNamesExpr(self, ctx:dpm_xlParser.KeyNamesExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#keyNamesExpr.
    def exitKeyNamesExpr(self, ctx:dpm_xlParser.KeyNamesExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#concatExpr.
    def enterConcatExpr(self, ctx:dpm_xlParser.ConcatExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#concatExpr.
    def exitConcatExpr(self, ctx:dpm_xlParser.ConcatExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#parExpr.
    def enterParExpr(self, ctx:dpm_xlParser.ParExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#parExpr.
    def exitParExpr(self, ctx:dpm_xlParser.ParExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#unaryExpr.
    def enterUnaryExpr(self, ctx:dpm_xlParser.UnaryExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#unaryExpr.
    def exitUnaryExpr(self, ctx:dpm_xlParser.UnaryExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#notExpr.
    def enterNotExpr(self, ctx:dpm_xlParser.NotExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#notExpr.
    def exitNotExpr(self, ctx:dpm_xlParser.NotExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#selectExpr.
    def enterSelectExpr(self, ctx:dpm_xlParser.SelectExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#selectExpr.
    def exitSelectExpr(self, ctx:dpm_xlParser.SelectExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#numericExpr.
    def enterNumericExpr(self, ctx:dpm_xlParser.NumericExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#numericExpr.
    def exitNumericExpr(self, ctx:dpm_xlParser.NumericExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#literalExpr.
    def enterLiteralExpr(self, ctx:dpm_xlParser.LiteralExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#literalExpr.
    def exitLiteralExpr(self, ctx:dpm_xlParser.LiteralExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#compExpr.
    def enterCompExpr(self, ctx:dpm_xlParser.CompExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#compExpr.
    def exitCompExpr(self, ctx:dpm_xlParser.CompExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#ifExpr.
    def enterIfExpr(self, ctx:dpm_xlParser.IfExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#ifExpr.
    def exitIfExpr(self, ctx:dpm_xlParser.IfExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#clauseExpr.
    def enterClauseExpr(self, ctx:dpm_xlParser.ClauseExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#clauseExpr.
    def exitClauseExpr(self, ctx:dpm_xlParser.ClauseExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#boolExpr.
    def enterBoolExpr(self, ctx:dpm_xlParser.BoolExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#boolExpr.
    def exitBoolExpr(self, ctx:dpm_xlParser.BoolExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#setOperand.
    def enterSetOperand(self, ctx:dpm_xlParser.SetOperandContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#setOperand.
    def exitSetOperand(self, ctx:dpm_xlParser.SetOperandContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#setElements.
    def enterSetElements(self, ctx:dpm_xlParser.SetElementsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#setElements.
    def exitSetElements(self, ctx:dpm_xlParser.SetElementsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#aggregateFunctions.
    def enterAggregateFunctions(self, ctx:dpm_xlParser.AggregateFunctionsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#aggregateFunctions.
    def exitAggregateFunctions(self, ctx:dpm_xlParser.AggregateFunctionsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#numericFunctions.
    def enterNumericFunctions(self, ctx:dpm_xlParser.NumericFunctionsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#numericFunctions.
    def exitNumericFunctions(self, ctx:dpm_xlParser.NumericFunctionsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#comparisonFunctions.
    def enterComparisonFunctions(self, ctx:dpm_xlParser.ComparisonFunctionsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#comparisonFunctions.
    def exitComparisonFunctions(self, ctx:dpm_xlParser.ComparisonFunctionsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#filterFunctions.
    def enterFilterFunctions(self, ctx:dpm_xlParser.FilterFunctionsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#filterFunctions.
    def exitFilterFunctions(self, ctx:dpm_xlParser.FilterFunctionsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#conditionalFunctions.
    def enterConditionalFunctions(self, ctx:dpm_xlParser.ConditionalFunctionsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#conditionalFunctions.
    def exitConditionalFunctions(self, ctx:dpm_xlParser.ConditionalFunctionsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#timeFunctions.
    def enterTimeFunctions(self, ctx:dpm_xlParser.TimeFunctionsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#timeFunctions.
    def exitTimeFunctions(self, ctx:dpm_xlParser.TimeFunctionsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#stringFunctions.
    def enterStringFunctions(self, ctx:dpm_xlParser.StringFunctionsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#stringFunctions.
    def exitStringFunctions(self, ctx:dpm_xlParser.StringFunctionsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#unaryNumericFunctions.
    def enterUnaryNumericFunctions(self, ctx:dpm_xlParser.UnaryNumericFunctionsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#unaryNumericFunctions.
    def exitUnaryNumericFunctions(self, ctx:dpm_xlParser.UnaryNumericFunctionsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#binaryNumericFunctions.
    def enterBinaryNumericFunctions(self, ctx:dpm_xlParser.BinaryNumericFunctionsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#binaryNumericFunctions.
    def exitBinaryNumericFunctions(self, ctx:dpm_xlParser.BinaryNumericFunctionsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#complexNumericFunctions.
    def enterComplexNumericFunctions(self, ctx:dpm_xlParser.ComplexNumericFunctionsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#complexNumericFunctions.
    def exitComplexNumericFunctions(self, ctx:dpm_xlParser.ComplexNumericFunctionsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#matchExpr.
    def enterMatchExpr(self, ctx:dpm_xlParser.MatchExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#matchExpr.
    def exitMatchExpr(self, ctx:dpm_xlParser.MatchExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#isnullExpr.
    def enterIsnullExpr(self, ctx:dpm_xlParser.IsnullExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#isnullExpr.
    def exitIsnullExpr(self, ctx:dpm_xlParser.IsnullExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#filterOperators.
    def enterFilterOperators(self, ctx:dpm_xlParser.FilterOperatorsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#filterOperators.
    def exitFilterOperators(self, ctx:dpm_xlParser.FilterOperatorsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#timeShiftFunction.
    def enterTimeShiftFunction(self, ctx:dpm_xlParser.TimeShiftFunctionContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#timeShiftFunction.
    def exitTimeShiftFunction(self, ctx:dpm_xlParser.TimeShiftFunctionContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#nvlFunction.
    def enterNvlFunction(self, ctx:dpm_xlParser.NvlFunctionContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#nvlFunction.
    def exitNvlFunction(self, ctx:dpm_xlParser.NvlFunctionContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#unaryStringFunction.
    def enterUnaryStringFunction(self, ctx:dpm_xlParser.UnaryStringFunctionContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#unaryStringFunction.
    def exitUnaryStringFunction(self, ctx:dpm_xlParser.UnaryStringFunctionContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#commonAggrOp.
    def enterCommonAggrOp(self, ctx:dpm_xlParser.CommonAggrOpContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#commonAggrOp.
    def exitCommonAggrOp(self, ctx:dpm_xlParser.CommonAggrOpContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#groupingClause.
    def enterGroupingClause(self, ctx:dpm_xlParser.GroupingClauseContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#groupingClause.
    def exitGroupingClause(self, ctx:dpm_xlParser.GroupingClauseContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#itemSignature.
    def enterItemSignature(self, ctx:dpm_xlParser.ItemSignatureContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#itemSignature.
    def exitItemSignature(self, ctx:dpm_xlParser.ItemSignatureContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#itemReference.
    def enterItemReference(self, ctx:dpm_xlParser.ItemReferenceContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#itemReference.
    def exitItemReference(self, ctx:dpm_xlParser.ItemReferenceContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#rowElem.
    def enterRowElem(self, ctx:dpm_xlParser.RowElemContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#rowElem.
    def exitRowElem(self, ctx:dpm_xlParser.RowElemContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#colElem.
    def enterColElem(self, ctx:dpm_xlParser.ColElemContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#colElem.
    def exitColElem(self, ctx:dpm_xlParser.ColElemContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#sheetElem.
    def enterSheetElem(self, ctx:dpm_xlParser.SheetElemContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#sheetElem.
    def exitSheetElem(self, ctx:dpm_xlParser.SheetElemContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#rowHandler.
    def enterRowHandler(self, ctx:dpm_xlParser.RowHandlerContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#rowHandler.
    def exitRowHandler(self, ctx:dpm_xlParser.RowHandlerContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#colHandler.
    def enterColHandler(self, ctx:dpm_xlParser.ColHandlerContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#colHandler.
    def exitColHandler(self, ctx:dpm_xlParser.ColHandlerContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#sheetHandler.
    def enterSheetHandler(self, ctx:dpm_xlParser.SheetHandlerContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#sheetHandler.
    def exitSheetHandler(self, ctx:dpm_xlParser.SheetHandlerContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#interval.
    def enterInterval(self, ctx:dpm_xlParser.IntervalContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#interval.
    def exitInterval(self, ctx:dpm_xlParser.IntervalContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#default.
    def enterDefault(self, ctx:dpm_xlParser.DefaultContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#default.
    def exitDefault(self, ctx:dpm_xlParser.DefaultContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#rowArg.
    def enterRowArg(self, ctx:dpm_xlParser.RowArgContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#rowArg.
    def exitRowArg(self, ctx:dpm_xlParser.RowArgContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#colArg.
    def enterColArg(self, ctx:dpm_xlParser.ColArgContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#colArg.
    def exitColArg(self, ctx:dpm_xlParser.ColArgContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#sheetArg.
    def enterSheetArg(self, ctx:dpm_xlParser.SheetArgContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#sheetArg.
    def exitSheetArg(self, ctx:dpm_xlParser.SheetArgContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#intervalArg.
    def enterIntervalArg(self, ctx:dpm_xlParser.IntervalArgContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#intervalArg.
    def exitIntervalArg(self, ctx:dpm_xlParser.IntervalArgContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#defaultArg.
    def enterDefaultArg(self, ctx:dpm_xlParser.DefaultArgContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#defaultArg.
    def exitDefaultArg(self, ctx:dpm_xlParser.DefaultArgContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#select.
    def enterSelect(self, ctx:dpm_xlParser.SelectContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#select.
    def exitSelect(self, ctx:dpm_xlParser.SelectContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#selectOperand.
    def enterSelectOperand(self, ctx:dpm_xlParser.SelectOperandContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#selectOperand.
    def exitSelectOperand(self, ctx:dpm_xlParser.SelectOperandContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#varID.
    def enterVarID(self, ctx:dpm_xlParser.VarIDContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#varID.
    def exitVarID(self, ctx:dpm_xlParser.VarIDContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#cellRef.
    def enterCellRef(self, ctx:dpm_xlParser.CellRefContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#cellRef.
    def exitCellRef(self, ctx:dpm_xlParser.CellRefContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#preconditionElem.
    def enterPreconditionElem(self, ctx:dpm_xlParser.PreconditionElemContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#preconditionElem.
    def exitPreconditionElem(self, ctx:dpm_xlParser.PreconditionElemContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#varRef.
    def enterVarRef(self, ctx:dpm_xlParser.VarRefContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#varRef.
    def exitVarRef(self, ctx:dpm_xlParser.VarRefContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#operationRef.
    def enterOperationRef(self, ctx:dpm_xlParser.OperationRefContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#operationRef.
    def exitOperationRef(self, ctx:dpm_xlParser.OperationRefContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#tableRef.
    def enterTableRef(self, ctx:dpm_xlParser.TableRefContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#tableRef.
    def exitTableRef(self, ctx:dpm_xlParser.TableRefContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#compRef.
    def enterCompRef(self, ctx:dpm_xlParser.CompRefContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#compRef.
    def exitCompRef(self, ctx:dpm_xlParser.CompRefContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#tableReference.
    def enterTableReference(self, ctx:dpm_xlParser.TableReferenceContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#tableReference.
    def exitTableReference(self, ctx:dpm_xlParser.TableReferenceContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#whereExpr.
    def enterWhereExpr(self, ctx:dpm_xlParser.WhereExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#whereExpr.
    def exitWhereExpr(self, ctx:dpm_xlParser.WhereExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#getExpr.
    def enterGetExpr(self, ctx:dpm_xlParser.GetExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#getExpr.
    def exitGetExpr(self, ctx:dpm_xlParser.GetExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#renameExpr.
    def enterRenameExpr(self, ctx:dpm_xlParser.RenameExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#renameExpr.
    def exitRenameExpr(self, ctx:dpm_xlParser.RenameExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#subExpr.
    def enterSubExpr(self, ctx:dpm_xlParser.SubExprContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#subExpr.
    def exitSubExpr(self, ctx:dpm_xlParser.SubExprContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#renameClause.
    def enterRenameClause(self, ctx:dpm_xlParser.RenameClauseContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#renameClause.
    def exitRenameClause(self, ctx:dpm_xlParser.RenameClauseContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#comparisonOperators.
    def enterComparisonOperators(self, ctx:dpm_xlParser.ComparisonOperatorsContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#comparisonOperators.
    def exitComparisonOperators(self, ctx:dpm_xlParser.ComparisonOperatorsContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#literal.
    def enterLiteral(self, ctx:dpm_xlParser.LiteralContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#literal.
    def exitLiteral(self, ctx:dpm_xlParser.LiteralContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#keyNames.
    def enterKeyNames(self, ctx:dpm_xlParser.KeyNamesContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#keyNames.
    def exitKeyNames(self, ctx:dpm_xlParser.KeyNamesContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#propertyReference.
    def enterPropertyReference(self, ctx:dpm_xlParser.PropertyReferenceContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#propertyReference.
    def exitPropertyReference(self, ctx:dpm_xlParser.PropertyReferenceContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#propertyCode.
    def enterPropertyCode(self, ctx:dpm_xlParser.PropertyCodeContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#propertyCode.
    def exitPropertyCode(self, ctx:dpm_xlParser.PropertyCodeContext):
        pass


    # Enter a parse tree produced by dpm_xlParser#temporaryIdentifier.
    def enterTemporaryIdentifier(self, ctx:dpm_xlParser.TemporaryIdentifierContext):
        pass

    # Exit a parse tree produced by dpm_xlParser#temporaryIdentifier.
    def exitTemporaryIdentifier(self, ctx:dpm_xlParser.TemporaryIdentifierContext):
        pass



del dpm_xlParser