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
    """
    Template to start a new visitor for the AST
    """

    def __init__(self):
        pass

    def visit_Start(self, node: Start):
        for child in node.children:
            self.visit(child)

    def visit_ParExpr(self, node: ParExpr):
        self.visit(node.expression)

    def visit_BinOp(self, node: BinOp):
        self.visit(node.left)
        self.visit(node.right)

    def visit_UnaryOp(self, node: UnaryOp):
        self.visit(node.operand)

    def visit_CondExpr(self, node: CondExpr):
        self.visit(node.condition)
        self.visit(node.then_expr)
        if node.else_expr:
            self.visit(node.else_expr)

    def visit_VarRef(self, node: VarRef):
        pass

    def visit_VarID(self, node: VarID):
        pass

    def visit_Constant(self, node: Constant):
        pass

    def visit_WithExpression(self, node: WithExpression):
        self.visit(node.partial_selection)
        self.visit(node.expression)

    def visit_AggregationOp(self, node: AggregationOp):
        self.visit(node.operand)
        if node.grouping_clause:
            self.visit(node.grouping_clause)

    def visit_GroupingClause(self, node: GroupingClause):
        pass

    def visit_Dimension(self, node: Dimension):
        pass

    def visit_Set(self, node: Set):
        for child in node.children:
            self.visit(child)

    def visit_Scalar(self, node: Scalar):
        pass

    def visit_ComplexNumericOp(self, node: ComplexNumericOp):
        for operand in node.operands:
            self.visit(operand)

    def visit_RenameOp(self, node: RenameOp):
        self.visit(node.operand)

    def visit_TimeShiftOp(self, node: TimeShiftOp):
        self.visit(node.operand)

    def visit_FilterOp(self, node: FilterOp):
        self.visit(node.selection)
        self.visit(node.condition)

    def visit_WhereClauseOp(self, node: WhereClauseOp):
        self.visit(node.operand)
        self.visit(node.condition.right)

    def visit_GetOp(self, node: GetOp):
        self.visit(node.operand)

    def visit_SubOp(self, node: SubOp):
        self.visit(node.operand)
        self.visit(node.value)

    def visit_PreconditionItem(self, node: PreconditionItem):
        pass

    def visit_PropertyReference(self, node: PropertyReference):
        pass

    def visit_OperationRef(self, node: OperationRef):
        pass

    def visit_PersistentAssignment(self, node: PersistentAssignment):
        self.visit(node.left)
        self.visit(node.right)

    def visit_TemporaryAssignment(self, node: TemporaryAssignment):
        self.visit(node.right)
