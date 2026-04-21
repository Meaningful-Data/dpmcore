from abc import ABC

import pandas as pd

from dpmcore import errors
from dpmcore.dpm_xl.ast.nodes import (
    AggregationOp,
    BinOp,
    ComplexNumericOp,
    CondExpr,
    Constant,
    Dimension,
    FilterOp,
    GetOp,
    OperationRef,
    ParExpr,
    PersistentAssignment,
    PreconditionItem,
    PropertyReference,
    RenameOp,
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
from dpmcore.dpm_xl.ast.nodes import (
    Scalar as ScalarNode,
)
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.symbols import (
    ConstantOperand,
    FactComponent,
    KeyComponent,
    RecordSet,
    Scalar,
    ScalarSet,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import Item, Mixed, Null, ScalarFactory
from dpmcore.dpm_xl.utils.data_handlers import filter_all_data
from dpmcore.dpm_xl.utils.operands_mapping import set_operand_label
from dpmcore.dpm_xl.utils.operator_mapping import (
    AGGR_OP_MAPPING,
    BIN_OP_MAPPING,
    CLAUSE_OP_MAPPING,
    COMPLEX_OP_MAPPING,
    CONDITIONAL_OP_MAPPING,
    TIME_OPERATORS,
    UNARY_OP_MAPPING,
)
from dpmcore.dpm_xl.utils.tokens import (
    DPM,
    FILTER,
    GET,
    IF,
    RENAME,
    STANDARD,
    SUB,
    TIME_SHIFT,
    WHERE,
)
from dpmcore.dpm_xl.warning_collector import add_semantic_warning
from dpmcore.errors import SemanticError


class InputAnalyzer(ASTTemplate, ABC):
    def __init__(self, expression):
        super().__init__()
        self.data = None
        self.key_components = {}
        self.open_keys = None
        self.result: bool = False
        self._expression: str = expression  # For debugging purposes only
        self.preconditions: bool = False

        self.calculations_outputs = {}

        # Implicit open keys that are always available without being declared
        # These are special dimensions that arise from the reporting context itself
        self.global_variables = {
            "refPeriod": ScalarFactory().database_types_mapping(
                "d"
            )(),  # date type
            "entityID": ScalarFactory().database_types_mapping(
                "s"
            )(),  # string type
        }

    # Start of visiting nodes.

    def visit_Start(self, node: Start):

        result = []
        for child in node.children:
            result_symbol = self.visit(child)

            if self.preconditions:
                if isinstance(
                    result_symbol, Scalar
                ) and not result_symbol.type.strictly_same_class(
                    ScalarFactory().scalar_factory("Boolean")
                ):
                    raise errors.SemanticError("2-1")
                elif isinstance(result_symbol, RecordSet):
                    if (not result_symbol.has_only_global_components) or (
                        not result_symbol.get_fact_component().type.strictly_same_class(
                            ScalarFactory().scalar_factory("Boolean")
                        )
                    ):
                        raise errors.SemanticError("2-1")

            if len(node.children) == 1:
                return result_symbol
            result.append(result_symbol)

        return result

    def visit_PersistentAssignment(self, node: PersistentAssignment):
        return self.visit(node.right)

    def visit_TemporaryAssignment(self, node: TemporaryAssignment):

        right = self.visit(node.right)
        right.name = node.left.value
        self.calculations_outputs[right.name] = right
        return right

    def visit_ParExpr(self, node: ParExpr):
        return self.visit(node.expression)

    def visit_BinOp(self, node: BinOp):
        left_symbol = self.visit(node.left)
        right_symbol = self.visit(node.right)
        result = BIN_OP_MAPPING[node.op].validate(left_symbol, right_symbol)

        return result

    def visit_UnaryOp(self, node: UnaryOp):
        operand_symbol = self.visit(node.operand)
        result = UNARY_OP_MAPPING[node.op].validate_types(operand_symbol)

        return result

    def visit_CondExpr(self, node: CondExpr):
        condition_symbol = self.visit(node.condition)
        then_symbol = self.visit(node.then_expr)
        else_symbol = (
            None if node.else_expr is None else self.visit(node.else_expr)
        )
        result = CONDITIONAL_OP_MAPPING[IF].validate(
            condition_symbol, then_symbol, else_symbol
        )
        return result

    def visit_VarRef(self, node: VarRef):
        raise SemanticError("7-2")

    def visit_PropertyReference(self, node: PropertyReference):
        raise SemanticError("7-1")

    @staticmethod
    def __check_default_value(default_value, type_):
        if default_value is None:
            return
        default_type = ScalarFactory().scalar_factory(code=default_value.type)
        # Import the implicit type promotion dictionary for unidirectional check
        from dpmcore.dpm_xl.types.promotion import implicit_type_promotion_dict

        # Check if default_type can be promoted TO type_ (unidirectional check)
        # Get the set of types that default_type can be promoted to
        default_implicities = implicit_type_promotion_dict[
            default_type.__class__
        ]

        # If expected type is not in the set of types default can be promoted to,
        # raise a semantic error
        if not type_.is_included(default_implicities):
            raise errors.SemanticError(
                "3-6", expected_type=type_, default_type=default_type
            )

    def visit_VarID(self, node: VarID):

        self.__check_default_value(node.default, node.type)

        # filter by table_code
        df = filter_all_data(
            self.data, node.table, node.rows, node.cols, node.sheets
        )

        scalar_factory = ScalarFactory()
        interval = getattr(node, "interval", None)
        data_types = df["data_type"].apply(
            lambda x: scalar_factory.from_database_to_scalar_types(x, interval)
        )
        df["data_type"] = data_types

        label = getattr(node, "label", None)
        components = []
        if self.key_components and node.table in self.key_components:
            dpm_keys = self.key_components[node.table]
            if len(dpm_keys) > 0:
                for key_name, key_type in zip(
                    dpm_keys["property_code"], dpm_keys["data_type"], strict=False
                ):
                    if not key_type:
                        type_ = Item()
                    else:
                        type_ = ScalarFactory().database_types_mapping(
                            key_type
                        )()
                    components.append(
                        KeyComponent(
                            name=key_name,
                            type_=type_,
                            subtype=DPM,
                            parent=label,
                        )
                    )

        standard_keys = []
        self._check_standard_key(standard_keys, df["row_code"], "r", label)
        self._check_standard_key(standard_keys, df["column_code"], "c", label)
        self._check_standard_key(standard_keys, df["sheet_code"], "s", label)

        if len(self.global_variables):
            for var_name, var_type in self.global_variables.items():
                var_component = KeyComponent(
                    name=var_name,
                    type_=var_type,
                    subtype=DPM,
                    parent=label,
                    is_global=True,
                )
                components.append(var_component)

        components.extend(standard_keys)
        if len(components) == 0:
            set_operand_label(label=label, operand=node)
            return Scalar(
                type_=node.type, name=label, origin=label
            )
        fact_component = FactComponent(
            type_=node.type, parent=label
        )

        components.append(fact_component)
        structure = Structure(components)
        recordset = RecordSet(structure, name=label, origin=label)

        records = []
        standard_key_names = []
        if len(standard_keys) > 0:
            for key in standard_keys:
                standard_key_names.append(key.name)
                if key.name == "r":
                    records.append(df["row_code"])
                elif key.name == "c":
                    records.append(df["column_code"])
                elif key.name == "s":
                    records.append(df["sheet_code"])

            df_records = pd.concat(records, axis=1)
            df_records.columns = standard_key_names
            df_records["data_type"] = df["data_type"]

            # Check for duplicate keys, but only among non-NULL combinations
            # NULL values can repeat without being considered duplicates
            # Filter out rows where ALL standard keys are NULL
            mask_all_null = df_records[standard_key_names].isnull().all(axis=1)
            df_non_null_keys = df_records[~mask_all_null]

            if len(df_non_null_keys) > 0:
                repeated_identifiers = df_non_null_keys[
                    df_non_null_keys[standard_key_names].duplicated(keep=False)
                ]
                # Further filter: only report duplicates where NO key is NULL (fully specified duplicates)
                mask_has_null = (
                    repeated_identifiers[standard_key_names]
                    .isnull()
                    .any(axis=1)
                )
                fully_specified_duplicates = repeated_identifiers[
                    ~mask_has_null
                ]

                if len(fully_specified_duplicates) > 0:
                    repeated_values = ""
                    for value in fully_specified_duplicates.values:
                        repeated_values = (
                            ", ".join([repeated_values, str(value)])
                            if repeated_values
                            else str(value)
                        )
                    raise errors.SemanticError(
                        "2-6",
                        name=getattr(node, "label", None),
                        keys=standard_key_names,
                        values=repeated_values,
                    )

            recordset.records = df_records

        return recordset

    @staticmethod
    def _check_standard_key(key_components, elements, name, parent):
        if len(elements) > 1 and len(elements.unique()) > 1:
            key_component = KeyComponent(
                name=name, type_=Null(), subtype=STANDARD, parent=parent
            )
            key_components.append(key_component)

    def visit_Constant(self, node: Constant):
        constant_type = ScalarFactory().scalar_factory(code=node.type)
        return ConstantOperand(
            type_=constant_type, name=None, origin=node.value, value=node.value
        )

    def visit_AggregationOp(self, node: AggregationOp):
        operand = self.visit(node.operand)
        if not isinstance(operand, RecordSet):
            raise errors.SemanticError("4-4-0-1", op=node.op)

        if operand.has_only_global_components:
            add_semantic_warning(
                f"Performing an aggregation on recordset: {operand.name} which has only global key components"
            )

        grouping_clause = None
        if node.grouping_clause:
            grouping_clause = node.grouping_clause.components

        if isinstance(operand.get_fact_component().type, Mixed):
            origin_expression = AGGR_OP_MAPPING[
                node.op
            ].generate_origin_expression(operand, grouping_clause)
            raise errors.SemanticError("4-4-0-3", origin=origin_expression)

        result = AGGR_OP_MAPPING[node.op].validate(operand, grouping_clause)
        return result

    def visit_Dimension(self, node: Dimension):
        # Check if this is an implicit open key (refPeriod, entityID)
        if node.dimension_code in self.global_variables:
            type_ = self.global_variables[node.dimension_code]
            return Scalar(type_=type_, name=None, origin=node.dimension_code)

        # Otherwise, look up from the database-backed open_keys
        dimension_data = self.open_keys[
            self.open_keys["property_code"] == node.dimension_code
        ].reset_index(drop=True)
        if dimension_data["data_type"][0] is not None:
            type_code = dimension_data["data_type"][0]
            type_ = ScalarFactory().database_types_mapping(code=type_code)()
        else:
            type_ = ScalarFactory().scalar_factory(code="Item")
        return Scalar(type_=type_, name=None, origin=node.dimension_code)

    def visit_Set(self, node: Set):

        if isinstance(node.children[0], Constant):
            types = {child.type for child in node.children}
            if len(types) > 1:
                raise errors.SemanticError("11", types=", ".join(types))
            common_type_code = types.pop()
            origin_elements = [str(child.value) for child in node.children]
        else:
            common_type_code = "Item"
            origin_elements = [
                "[" + child.item + "]" for child in node.children
            ]
        common_type = ScalarFactory().scalar_factory(common_type_code)
        origin = ", ".join(origin_elements)
        origin = "{" + origin + "}"

        return ScalarSet(type_=common_type, name=None, origin=origin)

    def visit_Scalar(self, node: ScalarNode):
        type_ = ScalarFactory().scalar_factory(node.scalar_type)
        return Scalar(type_=type_, origin=node.item, name=None)

    def visit_ComplexNumericOp(self, node: ComplexNumericOp):
        if node.op not in COMPLEX_OP_MAPPING:
            raise NotImplementedError

        symbols = [self.visit(operand) for operand in node.operands]

        result = COMPLEX_OP_MAPPING[node.op].validate(symbols)
        return result

    def visit_FilterOp(self, node: FilterOp):
        selection = self.visit(node.selection)
        condition = self.visit(node.condition)
        result = CONDITIONAL_OP_MAPPING[FILTER].validate(selection, condition)
        return result

    def visit_TimeShiftOp(self, node: TimeShiftOp):
        operand = self.visit(node.operand)
        if not isinstance(operand, (RecordSet, Scalar, ConstantOperand)):
            raise errors.SemanticError("4-7-1", op=TIME_SHIFT)
        result = TIME_OPERATORS[TIME_SHIFT].validate(
            operand=operand,
            component_name=node.component,
            period=node.period_indicator,
            shift_number=node.shift_number,
        )
        return result

    def visit_WhereClauseOp(self, node: WhereClauseOp):

        operand = self.visit(node.operand)

        if len(node.key_components) == 0:
            raise errors.SemanticError("4-5-2-1", recordset=operand.name)

        condition = self.visit(node.condition)
        result = CLAUSE_OP_MAPPING[WHERE].validate(
            operand=operand,
            key_names=node.key_components,
            new_names=None,
            condition=condition,
        )
        return result

    def visit_RenameOp(self, node: RenameOp):
        operand = self.visit(node.operand)
        names = []
        new_names = []
        for rename_node in node.rename_nodes:
            names.append(rename_node.old_name)
            new_names.append(rename_node.new_name)
        result = CLAUSE_OP_MAPPING[RENAME].validate(
            operand=operand, key_names=names, new_names=new_names
        )
        return result

    def visit_GetOp(self, node: GetOp):
        operand = self.visit(node.operand)
        key_names = [node.component]
        result = CLAUSE_OP_MAPPING[GET].validate(operand, key_names)
        return result

    def visit_SubOp(self, node: SubOp):
        operand = self.visit(node.operand)
        value = self.visit(node.value)
        result = CLAUSE_OP_MAPPING[SUB].validate(
            operand=operand, property_code=node.property_code, value=value
        )
        return result

    def visit_PreconditionItem(self, node: PreconditionItem) -> Scalar:
        """Return a ScalarType Boolean with True value is precondition is satisfied otherwise False.
        Example:
        "table_code","ColumnID","RowID","SheetID","column_code","row_code","sheet_code","cell_code","CellID","VariableVID","data_type_code"
        S.01.01.01.01,,,,,,,,,xxxxxxx,BOO
        We can check with table_code or VariableVID, here for now, we use table_code.
        """
        type_ = ScalarFactory().scalar_factory(code="Boolean")

        return Scalar(type_=type_, name=node.label, origin=node.label)

    def visit_OperationRef(self, node: OperationRef):

        operation_code = node.operation_code
        if operation_code not in self.calculations_outputs:
            raise errors.SemanticError("1-9", operation_code=operation_code)
        return self.calculations_outputs[operation_code]

    def visit_WithExpression(self, node: WithExpression):
        return self.visit(node.expression)
