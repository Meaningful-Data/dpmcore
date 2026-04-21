from sqlalchemy.orm import Session

from dpmcore.dpm_xl.ast.nodes import *
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.model_queries import (
    ItemCategoryQuery,
    OperatorQuery,
    VariableVersionQuery,
)
from dpmcore.dpm_xl.utils.data_handlers import filter_all_data, generate_xyz
from dpmcore.dpm_xl.utils.scopes_calculator import OperationScopeService
from dpmcore.errors import SemanticError
from dpmcore.orm.operations import (
    OperandReference,
    OperandReferenceLocation,
    OperationNode,
)


def gather_element(node, attribute):
    if hasattr(node, attribute):
        return getattr(node, attribute)
    return None


def property_ref_period_mangement(name):
    if name == "refPeriod":
        return True
    return False


class MLGeneration(ASTTemplate):
    """DPM-ML generation is applied after checking the expression is semantically valid.

    Extracts the data provided by the semantic analysis and the Operation Version object to be associated with this expression.
    Based on the Visit pattern, creates the OperandNode, OperandReference and OperandReferenceLocation for each sub-operation and the
    involved operands.

    :parameter session: SQLAlchemy Session to be used to connect to the DB.
    :parameter data: Semantic analysis data that includes the all cell references used in the operation.
    :parameter op_version_id: ID of the Operation Version to be associated with each OperandNode.
    :parameter release_id: ID of the Release to be used
    :var df_operators: All operators present in the Operator table
    :var df_arguments: All arguments present in the OperatorArgument table.
    """

    def __init__(
        self,
        session,
        data,
        op_version_id,
        release_id,
        operations_data=None,
        store=False,
    ):
        super().__init__()
        self.session: Session = session
        self.session_queries = session
        self.data = data
        self.table_ids = (
            [int(x) for x in data["table_vid"].unique()]
            if data is not None
            else []
        )
        self.op_version_id = op_version_id
        self.df_operators = OperatorQuery.get_operators(self.session)
        self.df_arguments = OperatorQuery.get_arguments(self.session)
        self.release_id = release_id
        self.is_scripting = False if op_version_id else True

        self.operations_data = operations_data
        self.operation_tables = {}

        self.table_vid_dict = {}
        self.precondition_items = []
        self.existing_scopes = []
        self.new_scopes = []
        self.result = {}
        self.store = store

    def populate_operation_scope(self):
        operation_scope_service = OperationScopeService(
            operation_version_id=self.op_version_id, session=self.session
        )
        self.existing_scopes, self.new_scopes = (
            operation_scope_service.calculate_operation_scope(
                tables_vids=list(self.table_vid_dict.values()),
                precondition_items=self.precondition_items,
                only_last_release=False,
            )
        )

    def extract_operand_data(self, table, rows, cols, sheets):
        data_filtered = filter_all_data(self.data, table, rows, cols, sheets)
        data_filtered = data_filtered[
            ["row_code", "column_code", "sheet_code", "variable_id", "cell_id"]
        ]

        list_xyz = generate_xyz(data_filtered)

        return list_xyz

    def create_operation_node(self, node, is_leaf=False):

        parent_node = gather_element(node, "parent")
        op = gather_element(node, "op")
        scalar = gather_element(node, "scalar")
        interval = gather_element(node, "interval")
        interval = bool(interval) if interval is not None else False
        fallback_value = gather_element(node, "default")

        if isinstance(fallback_value, Constant):
            fallback_value = fallback_value.value

        if fallback_value is not None and isinstance(fallback_value, str):
            if len(fallback_value) == 0:
                fallback_value = '""'

        operator_id = None
        if not getattr(node, "operator_name", None):
            operator = self.df_operators[self.df_operators["Symbol"] == op][
                "OperatorID"
            ].values
        else:
            operator = self.df_operators[
                (self.df_operators["Symbol"] == op)
                & (
                    self.df_operators["Name"]
                    == getattr(node, "operator_name", None)
                )
            ]["OperatorID"].values

        if len(operator) > 0:
            operator_id = int(operator[0])
        argument = getattr(node, "argument", None)
        argument_id = None
        if argument:
            parent_operator_id = parent_node.OperatorID
            argument_info = self.df_arguments[
                (self.df_arguments["Name"] == argument)
                & (self.df_arguments["OperatorID"] == parent_operator_id)
            ]["ArgumentID"].values
            if len(argument_info) > 0:
                argument_id = int(argument_info[0])

        operand_node = OperationNode(
            OperatorID=operator_id,
            OperationVID=self.op_version_id,
            parent=parent_node,
            Scalar=scalar,
            UseIntervalArithmetics=interval,
            FallbackValue=fallback_value,
            IsLeaf=is_leaf,
            ArgumentID=argument_id,
        )

        self.session.add(operand_node)
        return operand_node

    def visit_Start(self, node: Start):
        for child in node.children:
            try:
                if self.is_scripting:
                    self._set_op_version_id_from_operation(child)
                self.visit(child)
                if not self.is_scripting:
                    if self.store:
                        self.session.commit()
                    if len(self.precondition_items) == 0:
                        self.populate_operation_scope()
                    self.store_objects_as_json()
                    if self.store:
                        for elto in self.new_scopes:
                            self.session.add(elto)
                        self.session.commit()
            except Exception as e:
                self.session.rollback()
                self.session.close()
                self.session_queries.close()
                raise e
        self.session_queries.close()

    def visit_PersistentAssignment(self, node: PersistentAssignment):

        operation_node = self.create_operation_node(node)

        node.left.argument = "left"
        node.right.argument = "right"

        node.left.parent = operation_node
        node.right.parent = operation_node

        self.visit(node.left)
        self.visit(node.right)

    def visit_TemporaryAssignment(self, node: TemporaryAssignment):
        self.visit(node.right)

    def visit_ParExpr(self, node: ParExpr):
        node.op = "()"
        operand_node = self.create_operation_node(node)
        node.expression.argument = "expression"
        node.expression.parent = operand_node
        self.visit(node.expression)

    def visit_BinOp(self, node: BinOp):
        if node.op == "+":
            node.operator_name = "Addition"
        elif node.op == "-":
            node.operator_name = "Subtraction"
        operand_node = self.create_operation_node(node)

        if node.op == "in":
            node.left.argument = "operand"
            node.right.argument = "set"
        elif node.op == "match":
            node.left.argument = "operand"
            node.right.argument = "pattern"
        else:
            node.left.argument = "left"
            node.right.argument = "right"
        node.left.parent = operand_node
        node.right.parent = operand_node
        self.visit(node.left)
        self.visit(node.right)

    def visit_UnaryOp(self, node: UnaryOp):
        if node.op == "+":
            node.operator_name = "Unary plus"
        elif node.op == "-":
            node.operator_name = "Unary minus"
        operand_node = self.create_operation_node(node)
        node.operand.argument = "operand"
        node.operand.parent = operand_node
        self.visit(node.operand)

    def visit_CondExpr(self, node: CondExpr):
        node.op = "if-then-else"
        operand_if = self.create_operation_node(node)
        node.condition.parent = operand_if
        node.condition.argument = "condition"
        self.visit(node.condition)
        node.then_expr.argument = "then"
        node.then_expr.parent = operand_if
        self.visit(node.then_expr)
        if node.else_expr:
            node.else_expr.argument = "else"
            node.else_expr.parent = operand_if
            self.visit(node.else_expr)

    def visit_WithExpression(self, node: WithExpression):
        parent = getattr(node, "parent", None)
        if parent:
            node.expression.parent = parent
        node.expression.argument = getattr(node, "argument", None)
        self.visit(node.expression)

    def visit_AggregationOp(self, node: AggregationOp):
        operand_node = self.create_operation_node(node)
        node.operand.parent = operand_node
        node.operand.argument = "operand"
        self.visit(node.operand)
        if node.grouping_clause:
            node.grouping_clause.op = "group by"
            node.grouping_clause.parent = operand_node
            node.grouping_clause.argument = "grouping_clause"
            self.visit(node.grouping_clause)

    def visit_GroupingClause(self, node: GroupingClause):
        gc_node = self.create_operation_node(node)
        for component in node.components:
            element = AST()
            element.parent = gc_node
            element.argument = "component"
            comp_node = self.create_operation_node(element, is_leaf=True)
            # property_id = ItemCategoryQuery.get_property_id_from_code(code=node.component, session=self.session)[0]
            if component in ("r", "c", "s"):
                op_ref = OperandReference(
                    op_node=comp_node, OperandReference=component
                )
            else:
                property_id = ItemCategoryQuery.get_property_id_from_code(
                    code=component, session=self.session_queries
                )[0]
                op_ref = OperandReference(
                    op_node=comp_node,
                    OperandReference="property",
                    PropertyID=property_id,
                )

            self.session.add(op_ref)

    def visit_ComplexNumericOp(self, node: ComplexNumericOp):
        operand_node = self.create_operation_node(node)
        for operand in node.operands:
            operand.parent = operand_node
            operand.argument = "operand"
            self.visit(operand)

    def visit_FilterOp(self, node: FilterOp):
        node.op = "filter"
        operand_node = self.create_operation_node(node)
        node.selection.parent = operand_node
        node.selection.argument = "selection"

        node.condition.parent = operand_node
        node.condition.argument = "condition"

        self.visit(node.selection)
        self.visit(node.condition)

    def visit_TimeShiftOp(self, node: TimeShiftOp):
        node.op = "time_shift"
        get_node = self.create_operation_node(node)

        node.operand.parent = get_node
        node.operand.argument = "operand"
        self.visit(node.operand)

        # period indicator
        period_indicator_node = AST()
        period_indicator_node.parent = get_node
        period_indicator_node.argument = "period_indicator"
        period_indicator_node.scalar = "Q"
        self.create_operation_node(period_indicator_node, is_leaf=True)

        # shift number
        shift_number_node = AST()
        shift_number_node.parent = get_node
        shift_number_node.argument = "shift_number"
        shift_number_node.scalar = getattr(node, "shift_number", None)
        self.create_operation_node(shift_number_node, is_leaf=True)

        # component
        ast_element = AST()
        ast_element.parent = get_node
        ast_element.argument = "dimension"
        ast_element.source_reference = "property"
        operand_node = self.create_operation_node(
            ast_element, is_leaf=True
        )  # TODO: Adapt to refPeriod
        if property_ref_period_mangement(node.component):
            op_ref = OperandReference(
                op_node=operand_node, OperandReference="refPeriod"
            )
        else:
            property_id = ItemCategoryQuery.get_property_id_from_code(
                code=node.component, session=self.session_queries
            )[0]
            op_ref = OperandReference(
                op_node=operand_node,
                OperandReference=ast_element.source_reference,
                PropertyID=property_id,
            )
        self.session.add(op_ref)

    def visit_WhereClauseOp(self, node: WhereClauseOp):
        node.op = "where"
        node_op = self.create_operation_node(node)
        node.operand.parent = node_op
        node.operand.argument = "operand"

        node.condition.parent = node_op
        node.condition.argument = "condition"
        self.visit(node.operand)
        self.visit(node.condition)

    def visit_GetOp(self, node: GetOp):
        node.op = "get"
        node_op = self.create_operation_node(node)
        node.operand.parent = node_op
        node.operand.argument = "operand"
        self.visit(node.operand)

        element = AST()
        element.parent = node_op
        element.argument = "component"
        element.source_reference = "property"
        component_node = self.create_operation_node(element, is_leaf=True)
        if property_ref_period_mangement(node.component):
            op_ref = OperandReference(
                op_node=component_node, OperandReference="refPeriod"
            )
        else:
            property_id = ItemCategoryQuery.get_property_id_from_code(
                code=node.component, session=self.session_queries
            )[0]
            op_ref = OperandReference(
                op_node=component_node,
                OperandReference=element.source_reference,
                PropertyID=property_id,
            )
        self.session.add(op_ref)

    def visit_RenameOp(self, node: RenameOp):
        node.op = "rename"
        operand_node = self.create_operation_node(node)
        node.operand.parent = operand_node
        node.operand.argument = "operand"
        self.visit(node.operand)

        for rename_node in node.rename_nodes:
            rename_node.parent = operand_node
            rename_node.argument = "node"
            self.visit(rename_node)

    def visit_RenameNode(self, node: RenameNode):
        node.op = "node"
        rename_node = self.create_operation_node(node)
        old_name = AST()
        old_name.parent = rename_node
        old_name.argument = "old_name"
        old_name.source_reference = "property"
        old_name.scalar = node.old_name
        old_property_id = ItemCategoryQuery.get_property_id_from_code(
            code=node.old_name, session=self.session_queries
        )[0]
        old_name_node = self.create_operation_node(old_name, is_leaf=True)

        old_operand_ref = OperandReference(
            op_node=old_name_node,
            OperandReference=old_name.source_reference,
            PropertyID=old_property_id,
        )

        self.session.add(old_operand_ref)

        new_name = AST()
        new_name.parent = rename_node
        new_name.argument = "new_name"
        new_name.source_reference = "property"
        new_name.scalar = node.new_name
        new_name_node = self.create_operation_node(new_name, is_leaf=True)

        new_operand_ref = OperandReference(
            op_node=new_name_node,
            OperandReference=new_name.source_reference,
            PropertyID=old_property_id,
        )
        self.session.add(new_operand_ref)

    def visit_SubOp(self, node: SubOp):
        node.op = "sub"
        operand_node = self.create_operation_node(node)
        node.operand.parent = operand_node
        node.operand.argument = "operand"
        self.visit(node.operand)

        # Visit the value (can be literal, select, or itemReference)
        node.value.parent = operand_node
        node.value.argument = "value"
        self.visit(node.value)

    def visit_PreconditionItem(self, node: PreconditionItem):
        operand_node = self.create_operation_node(node, is_leaf=True)
        operand_reference = "PreconditionItem"  # "$_{}".format(node.value)
        precondition_var = VariableVersionQuery.check_precondition(
            self.session, node.variable_code, self.release_id
        )
        variable_id = None
        precondition_code = None
        if precondition_var:
            variable_id = precondition_var.VariableID
            precondition_code = precondition_var.Code
        else:
            preconditions_vars = VariableVersionQuery.get_all_preconditions(
                self.session, self.release_id
            )
            precondition_found = False
            for precondition in preconditions_vars:
                if precondition.Code in node.variable_code:
                    variable_id = precondition.VariableID
                    precondition_found = True
                    precondition_code = precondition.Code
                    break

            if not precondition_found:
                raise SemanticError("1-3", variable=node.variable_code)

        operand_ref = OperandReference(
            op_node=operand_node,
            OperandReference=operand_reference,
            VariableID=variable_id,
        )

        self.session.add(operand_ref)
        self.precondition_items.append(precondition_code)

    def visit_VarRef(self, node: VarRef):
        node.source_reference = "variable"
        op_node = self.create_operation_node(node, is_leaf=True)
        node_value = getattr(node, "value", getattr(node, "variable", None))
        variable_id = VariableVersionQuery.get_variable_id(
            self.session, node_value, self.release_id
        )
        if variable_id:
            variable_id = variable_id[0]
        else:
            raise SemanticError("1-3", variable=node_value)
        operand_ref = OperandReference(
            op_node=op_node,
            OperandReference=node.source_reference,
            VariableID=variable_id,
        )

        self.session.add(operand_ref)

    def visit_VarID(self, node: VarID):
        node.source_reference = "variable"

        op_node = self.create_operation_node(node, is_leaf=True)

        data_xyz = self.extract_operand_data(
            node.table, node.rows, node.cols, node.sheets
        )

        # Extracting data
        significant_rows = node.rows is not None and len(node.rows) >= 1
        significant_cols = node.cols is not None and len(node.cols) >= 1
        significant_sheets = node.sheets is not None and len(node.sheets) >= 1

        for e in data_xyz:
            operand_ref = OperandReference(
                op_node=op_node,
                x=e["x"] if significant_rows else None,
                y=e["y"] if significant_cols else None,
                z=e["z"] if significant_sheets else None,
                OperandReference=node.source_reference,
                VariableID=e["variable_id"],
            )

            self.session.add(operand_ref)

            operand_ref_loc = OperandReferenceLocation(
                op_reference=operand_ref,
                CellID=e["cell_id"],
                Table=node.table,
                Row=e["row_code"],
                column=e["column_code"],
                Sheet=e["sheet_code"],
            )

            self.session.add(operand_ref_loc)

            if node.table not in self.table_vid_dict:
                table_vid = int(
                    self.data[self.data["table_code"] == node.table][
                        "table_vid"
                    ].unique()[0]
                )
                self.table_vid_dict[node.table] = table_vid

            if self.is_scripting:
                self._add_table_vid_to_operation_tables(node.table)

    def visit_Constant(self, node: Constant):
        node.scalar = node.value
        self.create_operation_node(node, is_leaf=True)

    def visit_Dimension(self, node: Dimension):
        node.source_reference = "property"
        op_node = self.create_operation_node(node, is_leaf=True)
        property = ItemCategoryQuery.get_property_from_code(
            code=node.dimension_code, session=self.session_queries
        )
        operand_ref = OperandReference(
            op_node=op_node,
            OperandReference=node.source_reference,
            PropertyID=property.ItemID,
        )
        self.session.add(operand_ref)

    def visit_Set(self, node: Set):
        node.source_reference = "item"
        node.operand_type = "set"
        op_node = self.create_operation_node(node, is_leaf=True)

        for child in node.children:
            item_id = ItemCategoryQuery.get_item_category_id_from_signature(
                signature=child.item, session=self.session_queries
            )[0]
            operand_ref = OperandReference(
                op_node=op_node,
                OperandReference=node.source_reference,
                ItemID=item_id,
            )
            self.session.add(operand_ref)

    def visit_Scalar(self, node: Scalar):
        node.source_reference = "item"
        op_node = self.create_operation_node(node, is_leaf=True)
        item_id = ItemCategoryQuery.get_item_category_id_from_signature(
            signature=node.item, session=self.session_queries
        )[0]
        operand_ref = OperandReference(
            op_node=op_node,
            OperandReference=node.source_reference,
            ItemID=item_id,
        )
        self.session.add(operand_ref)

    def visit_OperationRef(self, node: OperationRef):
        node.source_reference = "operation"
        op_node = self.create_operation_node(node, is_leaf=True)

        op_version_id = self._get_op_version_id(node.operation_code)

        operand_ref = OperandReference(
            op_node=op_node, OperandReference=op_version_id
        )
        self.session.add(operand_ref)

    def _get_op_version_id(self, operation_code):
        op_version_id = self.operations_data[
            self.operations_data["Code"] == operation_code
        ]["OperationVID"].values[0]
        op_version_id = int(op_version_id)
        return op_version_id

    def _set_op_version_id_from_operation(self, child):

        operation_code = child.left.value
        op_version_id = self._get_op_version_id(operation_code)
        self.op_version_id = op_version_id

    def _add_table_vid_to_operation_tables(self, table_code):
        if self.op_version_id not in self.operation_tables:
            self.operation_tables[self.op_version_id] = []
        table_vid = int(
            self.data[self.data["table_code"] == table_code][
                "table_vid"
            ].unique()[0]
        )
        if table_vid not in self.operation_tables[self.op_version_id]:
            self.operation_tables[self.op_version_id].append(table_vid)

    def store_objects_as_json(self):
        operation_nodes = [
            o
            for o in self.session.new
            if isinstance(o, OperationNode) and not o.parent
        ]
        self.result["operation_nodes"] = operation_nodes
        self.result["operation_scopes"] = {}
        self.result["operation_scopes"]["new"] = self.new_scopes
        self.result["operation_scopes"]["existing"] = self.existing_scopes
        self.session.expunge_all()

    def compare_ast(self, reference: OperationNode):
        """Compares the ML generated by the AST of the expression provided with the ML generated by the AST generated with the ML stored in the db.
        :return: True if the ASTs are equal, False otherwise.
        """
        op_nodes = self.result["operation_nodes"]

        if len(op_nodes) == 0:
            raise Exception("No AST Generated")

        if op_nodes[0] != reference:
            return False  # is_same_ast = False

        return True  # is_same_ast = True
