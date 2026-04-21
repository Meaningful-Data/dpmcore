"""AST.ASTObjects.py.
=================

Description
-----------
AST nodes
"""


class AST:
    """Superclass of all AST objects."""

    def __init__(self):
        self.num = None
        self.prev = None

    def __str__(self):
        return "<AST(name='{name}')>".format(name=self.__class__.__name__)

    __repr__ = __str__


class Start(AST):
    """Starting point of the AST."""

    def __init__(self, children):
        super().__init__()
        self.children = children

    def __str__(self):
        return "<AST(name='{name}', children={children})>".format(
            name=self.__class__.__name__, children=self.children
        )

    __repr__ = __str__

    def toJSON(self):
        result = {"class_name": self.__class__.__name__}

        # Check if this Start node has left/right/op structure (expanded from WithExpression)
        if hasattr(self, "left") and hasattr(self, "right"):
            result["left"] = self.left
            result["right"] = self.right
            if hasattr(self, "op"):
                result["op"] = self.op
        else:
            # Use original children structure
            result["children"] = self.children

        return result


class ParExpr(AST):
    """ParExpr. Parenthesis Expression used to group expressions inside parenthesis to give more priority.
    Example: (A + B) * C.
    """

    def __init__(self, expression):
        super().__init__()
        self.expression = expression

    def __str__(self):
        return "<AST(Expression={expression})>".format(
            expression=self.expression
        )

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "expression": self.expression,
        }

    __repr__ = __str__


class BinOp(AST):
    """All binary operators are analysed using this AST Object. Check BIN_OP_MAPPING on Utils/operator_mapping.py
    for the complete list.
    """

    def __init__(self, left, op, right):
        super().__init__()
        self.left = left
        self.op = op
        self.right = right

    def __str__(self):
        return "<AST(name='{name}', op='{op}', left={left}, right={right})>".format(
            name=self.__class__.__name__,
            op=self.op,
            left=self.left,
            right=self.right,
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "left": self.left,
            "right": self.right,
        }


class UnaryOp(AST):
    """All unary operators are analysed using this AST Object. Check UNARY_OP_MAPPING on Utils/operator_mapping.py
    for the complete list.
    """

    def __init__(self, op, operand):
        super().__init__()
        self.op = op
        self.operand = operand

    def __str__(self):
        return "<AST(name='{name}', op='{op}', operand={operand})>".format(
            name=self.__class__.__name__, op=self.op, operand=self.operand
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "operand": self.operand,
        }


class CondExpr(AST):
    """AST Object for if-then-else operation."""

    def __init__(self, condition, then_expr, else_expr):
        super().__init__()
        self.condition = condition
        self.then_expr = then_expr
        self.else_expr = else_expr

    def __str__(self):
        return "<AST(name='{name}', condition={condition}, then_expr={then_expr}, else_expr={else_expr})>".format(
            name=self.__class__.__name__,
            condition=self.condition,
            then_expr=self.then_expr,
            else_expr=self.else_expr,
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "condition": self.condition,
            "then_expr": self.then_expr,
            "else_expr": self.else_expr,
        }


class VarRef(AST):
    """Checks the reference to a specific variable in DB."""

    def __init__(self, variable):
        super().__init__()
        self.variable = variable

    def __str__(self):
        return "<AST(name='{name}', variable={variable})>".format(
            name=self.__class__.__name__, variable=self.variable
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "variable": self.variable,
        }


class VarID(AST):
    """AST Object for operand including a Cell Reference from DB."""

    def __init__(
        self,
        table,
        rows,
        cols,
        sheets,
        interval,
        default,
        is_table_group=False,
    ):
        super().__init__()
        self.table = table
        self.rows = rows
        self.cols = cols
        self.sheets = sheets
        self.interval = interval
        self.default = default
        self.label = None
        self.is_table_group = is_table_group

    def __str__(self):
        return (
            "<AST(name='{name}', table={table}, rows={rows}, cols={cols}, sheets={sheets}, interval={interval}, "
            "default={default}, is_table_group={is_table_group})>".format(
                name=self.__class__.__name__,
                table=self.table,
                rows=self.rows,
                cols=self.cols,
                sheets=self.sheets,
                interval=self.interval,
                default=self.default,
                is_table_group=self.is_table_group,
            )
        )

    __repr__ = __str__

    def toJSON(self):
        result = {
            "class_name": self.__class__.__name__,
        }

        # If data has been populated (after operand checking), use that
        if hasattr(self, "data") and self.data is not None:
            # Convert DataFrame to list of dictionaries
            data_records = None
            try:
                if hasattr(self.data, "to_dict"):
                    data_records = self.data.to_dict("records")
                    result["data"] = data_records
                else:
                    result["data"] = self.data
            except Exception:
                # Fallback: try to convert to list if it's iterable
                try:
                    result["data"] = list(self.data)
                except Exception:
                    result["data"] = str(self.data)
            result["table"] = self.table

            # Interval handling: determine from data_type in data records
            # According to DPM-XL spec, interval only applies to Number types
            interval_value = False  # default

            # First check if type attribute is set (from semantic validation)
            if hasattr(self, "type") and self.type is not None:
                from dpmcore.dpm_xl.types.scalar import Number

                if isinstance(self.type, Number):
                    interval_value = (
                        self.interval if self.interval is not None else False
                    )
                else:
                    interval_value = None
            # Otherwise, infer from data_type in data records
            elif (
                data_records
                and len(data_records) > 0
                and "data_type" in data_records[0]
            ):
                data_type = data_records[0]["data_type"]
                # Map database data types to determine if numeric
                # Numeric types: 'i' (integer), 'r' (decimal), 'm' (monetary), 'p' (percentage)
                # Non-numeric types: 'b' (boolean), 's' (string), 'e' (enumeration/item), etc.
                numeric_data_types = {
                    "i",
                    "r",
                    "m",
                    "p",
                    "INT",
                    "DEC",
                    "MON",
                    "PER",
                }
                if data_type in numeric_data_types:
                    interval_value = (
                        self.interval if self.interval is not None else False
                    )
                else:
                    interval_value = None
            else:
                # No type info available - use explicit interval or default to False
                interval_value = (
                    self.interval if self.interval is not None else False
                )

            result["interval"] = interval_value
        else:
            # Use original structure for unexpanded VarID
            # When there's no data (no semantic validation), default interval to False
            result.update(
                {
                    "table": self.table,
                    "rows": self.rows,
                    "cols": self.cols,
                    "sheets": self.sheets,
                    "interval": self.interval
                    if self.interval is not None
                    else False,
                    "default": self.default,
                    "is_table_group": self.is_table_group,
                }
            )

        return result


class Constant(AST):
    """AST Object for Constants included in code. Example: 0, "A"
    :parameter type_: Data Type of the Constant
    :parameter value: Value to be hold by the Constant.
    """

    def __init__(self, type_, value):
        super().__init__()
        self.type = type_
        self.value = value

    def __str__(self):
        return "<AST(name='{name}', type='{type_}', value={value})>".format(
            name=self.__class__.__name__, type_=self.type, value=self.value
        )

    __repr__ = __str__

    def toJSON(self):
        if self.type == "Integer":
            if isinstance(self.value, str) and "." in self.value:
                self.value = float(self.value)
            value = int(self.value)
        elif self.type == "Number":
            value = float(self.value)
        else:
            value = self.value
        return {
            "class_name": self.__class__.__name__,
            "type_": self.type,
            "value": value,
        }


class WithExpression(AST):
    """AST Object for expressions including a With clause, which simplifies the expressions over a common
    group of cell references.

    Example: {Table 1, row 1} + {Table 1, row 2} -> with {Table 1}: {row 1} + {row 2}
    :parameter partial_selection: Cell reference to be used
    :parameter expression: Expression after the double points to be modified by the partial selection
    """

    def __init__(self, partial_selection, expression):
        super().__init__()
        self.partial_selection = partial_selection
        self.expression = expression

    def __str__(self):
        return "<AST(name='{name}', partial_selection={partial_selection}, expression={expression})>".format(
            name=self.__class__.__name__,
            partial_selection=self.partial_selection,
            expression=self.expression,
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "partial_selection": self.partial_selection,
            "expression": self.expression,
        }


class AggregationOp(AST):
    """All aggregate operators are analysed using this AST Object. Check AGGR_OP_MAPPING on Utils/operator_mapping.py
    for the complete list.
    """

    def __init__(self, op, operand, grouping_clause):
        super().__init__()
        self.op = op
        self.operand = operand
        self.grouping_clause = grouping_clause

    def __str__(self):
        return "<AST(name='{name}', op='{op}', operand={operand}, grouping_clause={grouping_clause})>".format(
            name=self.__class__.__name__,
            op=self.op,
            operand=self.operand,
            grouping_clause=self.grouping_clause,
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "operand": self.operand,
            "grouping_clause": self.grouping_clause,
        }


class GroupingClause(AST):
    """Grouping clause inside an aggregation operation."""

    def __init__(self, components):
        super().__init__()
        self.components = components

    def __str__(self):
        return "<AST(name='{name}', components={components})>".format(
            name=self.__class__.__name__, components=self.components
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "components": self.components,
        }


class Dimension(AST):
    """AST object only included in a Where clause. Specifies the component to be filtered."""

    def __init__(self, dimension_code, property_id=None):
        super().__init__()
        self.dimension_code = dimension_code
        self.property_id = property_id

    def __str__(self):
        return (
            "<AST(name='{name}', dimension_code='{dimension_code}')>".format(
                name=self.__class__.__name__,
                dimension_code=self.dimension_code,
                )
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "dimension_code": self.dimension_code,
        }


class Set(AST):
    """AST object for Set operands. Used only in 'IN' operator."""

    def __init__(self, children):
        super().__init__()
        self.children = children

    def __str__(self):
        return "<AST(name='{name}', children={children})>".format(
            name=self.__class__.__name__, children=self.children
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "children": self.children,
        }


class Scalar(AST):
    """AST object representing an Item. Must be validated against the ItemCategory.Signature column.

    :parameter item: Item Signature to be validated
    :parameter scalar_type: Data type of the item referenced
    """

    def __init__(self, item, scalar_type):
        super().__init__()
        self.item = item
        self.scalar_type = scalar_type

    def __str__(self):
        return "<AST(name='{name}', item={item}, scalar_type='{scalar_type}')>".format(
            name=self.__class__.__name__,
            item=self.item,
            scalar_type=self.scalar_type,
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "item": self.item,
            "scalar_type": self.scalar_type,
        }


class ComplexNumericOp(AST):
    """AST Object for max and min operations. Could have more than one operand without any other size restrictions."""

    def __init__(self, op, operands):
        super().__init__()
        self.op = op
        self.operands = operands

    def __str__(self):
        return "<AST(name='{name}', op='{op}', operands={operands})>".format(
            name=self.__class__.__name__, op=self.op, operands=self.operands
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "operands": self.operands,
        }


class FilterOp(AST):
    """AST Object for filtering operations.

    :parameter selection: operand or expression over the filter is applied
    :parameter condition: boolean operation to filter the operand
    """

    def __init__(self, selection, condition):
        super().__init__()
        self.selection = selection
        self.condition = condition

    def __str__(self):
        return "<AST(name='{name}', selection={selection}, condition={condition})>".format(
            name=self.__class__.__name__,
            selection=self.selection,
            condition=self.condition,
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "selection": self.selection,
            "condition": self.condition,
        }


class TimeShiftOp(AST):
    """AST Object of the TimeShift operator.

    :parameter operand: Recordset where the operation is applied
    :parameter component: Component inside the Recordset to be selected
    :parameter period_indicator: Period to be used based on specification.
    :parameter shift_number: Number of times to apply the specified time period over the operand.
    """

    def __init__(self, operand, period_indicator, component, shift_number):
        super().__init__()
        self.operand = operand
        self.component = component
        self.period_indicator = period_indicator
        self.shift_number = shift_number

    def __str__(self):
        return (
            "<AST(name='{name}', operand={operand}, component={component}, period_indicator={period_indicator}, "
            "shift_number={shift_number})>".format(
                name=self.__class__.__name__,
                operand=self.operand,
                component=self.component,
                period_indicator=self.period_indicator,
                shift_number=self.shift_number,
            )
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "operand": self.operand,
            "period_indicator": self.period_indicator,
            "component": self.component,
            "shift_number": self.shift_number,
        }


class WhereClauseOp(AST):
    """AST object for the Where clause.

    :parameter operand: Operand where the filter is applied based on condition
    :parameter condition: Boolean expression to be used to filter information in the operand.
    """

    def __init__(self, operand, condition):
        super().__init__()
        self.operand = operand
        self.condition = condition
        self.key_components = []

    def __str__(self):
        return "<AST(name='{name}', operand={operand}, condition={condition}, key_components={components})>".format(
            name=self.__class__.__name__,
            operand=self.operand,
            condition=self.condition,
            components=self.key_components,
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "operand": self.operand,
            "condition": self.condition,
        }


class GetOp(AST):
    """AST Object for the Get operator. Replaces the Fact component with the specified component.

    :parameter operand: Recordset to be changed
    :parameter component: Component specified to replace the Fact component.
    """

    def __init__(self, operand, component):
        super().__init__()
        self.operand = operand
        self.component = component

    def __str__(self):
        return "<AST(name='{name}', operand={operand}, component='{component}')>".format(
            name=self.__class__.__name__,
            operand=self.operand,
            component=self.component,
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "operand": self.operand,
            "component": self.component,
        }


class PreconditionItem(AST):
    """AST Object only used in Preconditions.

    :parameter value: Sets to True or False if the desired table is present in the DB.
    """

    def __init__(self, variable_id, variable_code=None):
        super().__init__()
        self.variable_id = variable_id
        self.variable_code = variable_code

    def __str__(self):
        return "<AST(name='{name}', variable_id='{variable_id}')>".format(
            name=self.__class__.__name__, variable_id=self.variable_id
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "variable_id": self.variable_id,
            "variable_code": self.variable_code,
        }


class RenameOp(AST):
    """AST Object for rename operation.

    :parameter operand: Recordset on which components the rename operation applies.
    :parameter rename_nodes: A collection of Rename Nodes
    """

    def __init__(self, operand, rename_nodes):
        super().__init__()
        self.operand = operand
        self.rename_nodes = rename_nodes

    def __str__(self):
        return "<AST(name='{name}', rename_nodes={rename_nodes})>".format(
            name=self.__class__.__name__, rename_nodes=self.rename_nodes
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "operand": self.operand,
            "rename_nodes": self.rename_nodes,
        }


class RenameNode(AST):
    """Used only in rename operation, specifies the component and the new name to be used.

    :parameter old_name: Component to be renamed
    :parameter new_name: New name applied to the component
    """

    def __init__(self, old_name, new_name):
        super().__init__()
        self.old_name = old_name
        self.new_name = new_name

    def __str__(self):
        return "<AST(name='{name}', old_name='{old_name}', new_name='{new_name}')>".format(
            name=self.__class__.__name__,
            old_name=self.old_name,
            new_name=self.new_name,
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "old_name": self.old_name,
            "new_name": self.new_name,
        }


class SubOp(AST):
    """AST Object for the Sub operator. Filters a recordset based on a property substitution.

    :parameter operand: Recordset to be filtered
    :parameter property_code: Property code to substitute
    :parameter value: Value to substitute (can be a literal, select, or itemReference)
    """

    def __init__(self, operand, property_code, value):
        super().__init__()
        self.operand = operand
        self.property_code = property_code
        self.value = value

    def __str__(self):
        return "<AST(name='{name}', operand={operand}, property_code='{property_code}', value={value})>".format(
            name=self.__class__.__name__,
            operand=self.operand,
            property_code=self.property_code,
            value=self.value,
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "operand": self.operand,
            "property_code": self.property_code,
            "value": self.value,
        }


class PropertyReference(AST):
    def __init__(self, code):
        super().__init__()
        self.code = code

    def __str__(self):
        return "<AST(name='{name}', code={code})>".format(
            name=self.__class__.__name__, code=self.code
        )

    __repr__ = __str__

    def toJSON(self):
        return {"class_name": self.__class__.__name__, "code": self.code}


class OperationRef(AST):
    def __init__(self, operation_code):
        super().__init__()
        self.operation_code = operation_code

    def __str__(self):
        return (
            "<AST(name='{name}', operation_code='{operation_code}')>".format(
                name=self.__class__.__name__,
                operation_code=self.operation_code,
            )
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "operation_code": self.operation_code,
        }


class PersistentAssignment(AST):
    def __init__(self, left, op, right):
        super().__init__()
        self.left = left
        self.op = op
        self.right = right

    def __str__(self):
        return "<AST(name='{name}', op='{op}', left={left}, right={right})>".format(
            name=self.__class__.__name__,
            op=self.op,
            left=self.left,
            right=self.right,
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "left": self.left,
            "right": self.right,
        }


class TemporaryAssignment(AST):
    def __init__(self, left, op, right):
        super().__init__()
        self.left = left
        self.op = op
        self.right = right

    def __str__(self):
        return "<AST(name='{name}', op='{op}', left={left}, right={right})>".format(
            name=self.__class__.__name__,
            op=self.op,
            left=self.left,
            right=self.right,
        )

    __repr__ = __str__

    def toJSON(self):
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "left": self.left,
            "right": self.right,
        }


class TemporaryIdentifier(AST):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def __str__(self):
        return "<AST(name='{name}', value='{value}')>".format(
            name=self.__class__.__name__, value=self.value
        )

    __repr__ = __str__

    def toJSON(self):
        return {"class_name": self.__class__.__name__, "value": self.value}
