from __future__ import annotations

from dpmcore.dpm_xl.ast.nodes import (
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
    RenameOp,
    Scalar,
    Set,
    Start,
    SubOp,
    TemporaryAssignment,
    TimeShiftOp,
    UnaryOp,
    VarID,
    VarRef,
    WhereClauseOp,
    WithExpression,
)
from dpmcore.dpm_xl.ast.visitor import NodeVisitor


class ASTTemplate(NodeVisitor):
    """Template to start a new visitor for the AST."""

    def __init__(self) -> None:
        pass

    def visit_Start(self, node: Start) -> None:
        for child in node.children:
            self.visit(child)

    def visit_ParExpr(self, node: ParExpr) -> None:
        self.visit(node.expression)

    def visit_BinOp(self, node: BinOp) -> None:
        self.visit(node.left)
        self.visit(node.right)

    def visit_UnaryOp(self, node: UnaryOp) -> None:
        self.visit(node.operand)

    def visit_CondExpr(self, node: CondExpr) -> None:
        self.visit(node.condition)
        self.visit(node.then_expr)
        if node.else_expr:
            self.visit(node.else_expr)

    def visit_VarRef(self, node: VarRef) -> None:
        pass

    def visit_VarID(self, node: VarID) -> None:
        pass

    def visit_Constant(self, node: Constant) -> None:
        pass

    def visit_WithExpression(self, node: WithExpression) -> None:
        self.visit(node.partial_selection)
        self.visit(node.expression)

    def visit_AggregationOp(self, node: AggregationOp) -> None:
        self.visit(node.operand)
        if node.grouping_clause:
            self.visit(node.grouping_clause)

    def visit_GroupingClause(self, node: GroupingClause) -> None:
        pass

    def visit_Dimension(self, node: Dimension) -> None:
        pass

    def visit_Set(self, node: Set) -> None:
        for child in node.children:
            self.visit(child)

    def visit_Scalar(self, node: Scalar) -> None:
        pass

    def visit_ComplexNumericOp(self, node: ComplexNumericOp) -> None:
        for operand in node.operands:
            self.visit(operand)

    def visit_RenameOp(self, node: RenameOp) -> None:
        self.visit(node.operand)

    def visit_TimeShiftOp(self, node: TimeShiftOp) -> None:
        self.visit(node.operand)

    def visit_FilterOp(self, node: FilterOp) -> None:
        self.visit(node.selection)
        self.visit(node.condition)

    def visit_WhereClauseOp(self, node: WhereClauseOp) -> None:
        self.visit(node.operand)
        # Historical callers construct WhereClauseOp with a BinOp condition;
        # keep the original ``.right`` descent while raising a clear error
        # if an unexpected condition shape is ever routed through the base
        # template. All real-world visitors override this method.
        condition = node.condition
        if not isinstance(condition, BinOp):
            raise TypeError(
                "WhereClauseOp condition must be a BinOp; "
                f"got {type(condition).__name__}"
            )
        self.visit(condition.right)

    def visit_GetOp(self, node: GetOp) -> None:
        self.visit(node.operand)

    def visit_SubOp(self, node: SubOp) -> None:
        self.visit(node.operand)
        self.visit(node.value)

    def visit_PreconditionItem(self, node: PreconditionItem) -> None:
        pass

    def visit_PropertyReference(self, node: PropertyReference) -> None:
        pass

    def visit_OperationRef(self, node: OperationRef) -> None:
        pass

    def visit_PersistentAssignment(self, node: PersistentAssignment) -> None:
        self.visit(node.left)
        self.visit(node.right)

    def visit_TemporaryAssignment(self, node: TemporaryAssignment) -> None:
        self.visit(node.right)
