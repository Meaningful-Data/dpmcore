"""AST.ASTObjects.py.
=================

Description
-----------
AST nodes
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dpmcore.dpm_xl.types.scalar import ScalarType


class AST:
    """Superclass of all AST objects."""

    def __init__(self) -> None:
        self.num: int | None = None
        self.prev: AST | None = None
        # Dynamically-assigned attributes hoisted here so subclasses inherit
        # them for type checking. These are populated by visitor passes
        # (operand checking, ML generation) and must not require ``hasattr``
        # guards downstream.
        self.label: str | None = None
        self.type: ScalarType | None = None
        self.data: Any = None
        self.source_reference: str | None = None
        self.parent: Any = None
        self.argument: str | None = None
        self.operator_name: str | None = None
        self.op: str | None = None
        self.scalar: Any = None
        self.operand_type: str | None = None
        self.value: Any = None

    def __str__(self) -> str:
        return "<AST(name='{name}')>".format(name=self.__class__.__name__)

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {"class_name": self.__class__.__name__}


class Start(AST):
    """Starting point of the AST."""

    def __init__(self, children: list[AST]) -> None:
        super().__init__()
        self.children = children
        # Some passes (WithExpression expansion) assign left/right/op to Start
        self.left: AST | None = None
        self.right: AST | None = None

    def __str__(self) -> str:
        return "<AST(name='{name}', children={children})>".format(
            name=self.__class__.__name__, children=self.children
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        result: dict[str, Any] = {"class_name": self.__class__.__name__}

        # Check if this Start node has left/right/op structure (expanded from WithExpression)
        if self.left is not None and self.right is not None:
            result["left"] = self.left
            result["right"] = self.right
            if self.op is not None:
                result["op"] = self.op
        else:
            # Use original children structure
            result["children"] = self.children

        return result


class ParExpr(AST):
    """ParExpr. Parenthesis Expression used to group expressions inside parenthesis to give more priority.
    Example: (A + B) * C.
    """

    def __init__(self, expression: AST) -> None:
        super().__init__()
        self.expression: AST = expression

    def __str__(self) -> str:
        return "<AST(Expression={expression})>".format(
            expression=self.expression
        )

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "expression": self.expression,
        }

    __repr__ = __str__


class BinOp(AST):
    """All binary operators are analysed using this AST Object. Check BIN_OP_MAPPING on Utils/operator_mapping.py
    for the complete list.
    """

    def __init__(self, left: AST, op: str, right: AST) -> None:
        super().__init__()
        self.left: AST = left
        self.op = op
        self.right: AST = right

    def __str__(self) -> str:
        return "<AST(name='{name}', op='{op}', left={left}, right={right})>".format(
            name=self.__class__.__name__,
            op=self.op,
            left=self.left,
            right=self.right,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
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

    def __init__(self, op: str, operand: AST) -> None:
        super().__init__()
        self.op = op
        self.operand: AST = operand

    def __str__(self) -> str:
        return "<AST(name='{name}', op='{op}', operand={operand})>".format(
            name=self.__class__.__name__, op=self.op, operand=self.operand
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "operand": self.operand,
        }


class CondExpr(AST):
    """AST Object for if-then-else operation."""

    def __init__(
        self,
        condition: AST,
        then_expr: AST,
        else_expr: AST | None,
    ) -> None:
        super().__init__()
        self.condition: AST = condition
        self.then_expr: AST = then_expr
        self.else_expr: AST | None = else_expr

    def __str__(self) -> str:
        return "<AST(name='{name}', condition={condition}, then_expr={then_expr}, else_expr={else_expr})>".format(
            name=self.__class__.__name__,
            condition=self.condition,
            then_expr=self.then_expr,
            else_expr=self.else_expr,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "condition": self.condition,
            "then_expr": self.then_expr,
            "else_expr": self.else_expr,
        }


class VarRef(AST):
    """Checks the reference to a specific variable in DB."""

    def __init__(self, variable: str) -> None:
        super().__init__()
        self.variable = variable

    def __str__(self) -> str:
        return "<AST(name='{name}', variable={variable})>".format(
            name=self.__class__.__name__, variable=self.variable
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "variable": self.variable,
        }


class VarID(AST):
    """AST Object for operand including a Cell Reference from DB."""

    def __init__(
        self,
        table: str | None,
        rows: list[str] | None,
        cols: list[str] | None,
        sheets: list[str] | None,
        interval: bool | None,
        default: Any,
        is_table_group: bool = False,
        operation: str | None = None,
    ) -> None:
        super().__init__()
        self.table = table
        self.rows = rows
        self.cols = cols
        self.sheets = sheets
        self.interval = interval
        self.default = default
        self.is_table_group = is_table_group
        self.operation = operation

    def __str__(self) -> str:
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

    def toJSON(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "class_name": self.__class__.__name__,
        }

        # If data has been populated (after operand checking), use that
        if self.data is not None:
            # Convert DataFrame to list of dictionaries
            data_records: Any = None
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
            interval_value: bool | None = False  # default

            # First check if type attribute is set (from semantic validation)
            if self.type is not None:
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

    def __init__(self, type_: str, value: Any) -> None:
        super().__init__()
        # Note: ``self.type`` exists on AST base as ``ScalarType | None`` for
        # runtime inference. Constants instead store the literal category
        # label (e.g. "Integer", "String", "Null") in the same attribute —
        # this is legacy behaviour relied on by downstream passes.
        self.type = type_  # type: ignore[assignment]
        self.value = value

    def __str__(self) -> str:
        return "<AST(name='{name}', type='{type_}', value={value})>".format(
            name=self.__class__.__name__, type_=self.type, value=self.value
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        value: Any
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

    def __init__(self, partial_selection: "VarID", expression: AST) -> None:
        super().__init__()
        self.partial_selection: VarID = partial_selection
        self.expression: AST = expression

    def __str__(self) -> str:
        return "<AST(name='{name}', partial_selection={partial_selection}, expression={expression})>".format(
            name=self.__class__.__name__,
            partial_selection=self.partial_selection,
            expression=self.expression,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "partial_selection": self.partial_selection,
            "expression": self.expression,
        }


class AggregationOp(AST):
    """All aggregate operators are analysed using this AST Object. Check AGGR_OP_MAPPING on Utils/operator_mapping.py
    for the complete list.
    """

    def __init__(
        self,
        op: str,
        operand: AST,
        grouping_clause: "GroupingClause | None",
        analytic_clause: "AnalyticClause | None" = None,
    ) -> None:
        super().__init__()
        self.op = op
        self.operand: AST = operand
        self.grouping_clause: GroupingClause | None = grouping_clause
        self.analytic_clause: AnalyticClause | None = analytic_clause

    def __str__(self) -> str:
        return (
            "<AST(name='{name}', op='{op}', operand={operand}, "
            "grouping_clause={grouping_clause}, "
            "analytic_clause={analytic_clause})>".format(
                name=self.__class__.__name__,
                op=self.op,
                operand=self.operand,
                grouping_clause=self.grouping_clause,
                analytic_clause=self.analytic_clause,
            )
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "operand": self.operand,
            "grouping_clause": self.grouping_clause,
            "analytic_clause": (
                self.analytic_clause.toJSON()
                if self.analytic_clause is not None
                else None
            ),
        }


class GroupingClause(AST):
    """Grouping clause inside an aggregation operation."""

    def __init__(self, components: list[str]) -> None:
        super().__init__()
        self.components = components

    def __str__(self) -> str:
        return "<AST(name='{name}', components={components})>".format(
            name=self.__class__.__name__, components=self.components
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "components": self.components,
        }


class OrderItem(AST):
    """One item in an analytic order by clause: keyName [asc|desc]."""

    def __init__(self, key_name: str, direction: str = "asc") -> None:
        super().__init__()
        self.key_name = key_name
        self.direction = direction  # 'asc' | 'desc'

    def __str__(self) -> str:
        return f"<OrderItem(key_name='{self.key_name}', direction='{self.direction}')>"

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "key_name": self.key_name,
            "direction": self.direction,
        }


class WindowBoundary(AST):
    """One bound of an analytic window frame.

    bound_type: 'unbounded_preceding' | 'n_preceding' | 'current_data_point'
                | 'n_following' | 'unbounded_following'
    n: integer offset for n_preceding / n_following; None otherwise.
    """

    def __init__(self, bound_type: str, n: int | None = None) -> None:
        super().__init__()
        self.bound_type = bound_type
        self.n = n

    def __str__(self) -> str:
        return f"<WindowBoundary(bound_type='{self.bound_type}', n={self.n})>"

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "bound_type": self.bound_type,
            "n": self.n,
        }


class WindowClause(AST):
    """Window frame definition inside an analytic clause.

    frame_type: 'data_points' | 'range'
    """

    def __init__(
        self,
        frame_type: str,
        start: "WindowBoundary",
        end: "WindowBoundary",
    ) -> None:
        super().__init__()
        self.frame_type = frame_type
        self.start: WindowBoundary = start
        self.end: WindowBoundary = end

    def __str__(self) -> str:
        return (
            f"<WindowClause(frame_type='{self.frame_type}', "
            f"start={self.start}, end={self.end})>"
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "frame_type": self.frame_type,
            "start": self.start.toJSON(),
            "end": self.end.toJSON(),
        }


class AnalyticClause(AST):
    """Analytical invocation clause: over(partition_by? order_by? window?)."""

    def __init__(
        self,
        partition_by: list[str],
        order_by: "list[OrderItem]",
        window: "WindowClause | None",
    ) -> None:
        super().__init__()
        self.partition_by: list[str] = partition_by
        self.order_by: list[OrderItem] = order_by
        self.window: WindowClause | None = window

    def __str__(self) -> str:
        return (
            f"<AnalyticClause(partition_by={self.partition_by}, "
            f"order_by={self.order_by}, window={self.window})>"
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "partition_by": self.partition_by,
            "order_by": [item.toJSON() for item in self.order_by],
            "window": self.window.toJSON() if self.window else None,
        }


class RankOp(AST):
    """rank(expression over(...)) operator node."""

    def __init__(
        self, operand: AST, analytic_clause: "AnalyticClause"
    ) -> None:
        super().__init__()
        self.op = "rank"
        self.operand: AST = operand
        self.analytic_clause: AnalyticClause = analytic_clause

    def __str__(self) -> str:
        return (
            f"<RankOp(operand={self.operand}, "
            f"analytic_clause={self.analytic_clause})>"
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "operand": self.operand,
            "analytic_clause": self.analytic_clause.toJSON(),
        }


class Dimension(AST):
    """AST object only included in a Where clause. Specifies the component to be filtered."""

    def __init__(
        self, dimension_code: str, property_id: int | None = None
    ) -> None:
        super().__init__()
        self.dimension_code = dimension_code
        self.property_id = property_id

    def __str__(self) -> str:
        return (
            "<AST(name='{name}', dimension_code='{dimension_code}')>".format(
                name=self.__class__.__name__,
                dimension_code=self.dimension_code,
            )
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "dimension_code": self.dimension_code,
        }


class Set(AST):
    """AST object for Set operands. Used only in 'IN' operator."""

    def __init__(self, children: list[AST]) -> None:
        super().__init__()
        self.children = children

    def __str__(self) -> str:
        return "<AST(name='{name}', children={children})>".format(
            name=self.__class__.__name__, children=self.children
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "children": self.children,
        }


class Scalar(AST):
    """AST object representing an Item. Must be validated against the ItemCategory.Signature column.

    :parameter item: Item Signature to be validated
    :parameter scalar_type: Data type of the item referenced
    """

    def __init__(self, item: str, scalar_type: str) -> None:
        super().__init__()
        self.item = item
        self.scalar_type = scalar_type
        # Optional member attribute used by some serialization paths.
        self.member: str | None = None

    def __str__(self) -> str:
        return "<AST(name='{name}', item={item}, scalar_type='{scalar_type}')>".format(
            name=self.__class__.__name__,
            item=self.item,
            scalar_type=self.scalar_type,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "item": self.item,
            "scalar_type": self.scalar_type,
        }


class ComplexNumericOp(AST):
    """AST Object for max and min operations. Could have more than one operand without any other size restrictions."""

    def __init__(self, op: str, operands: list[AST]) -> None:
        super().__init__()
        self.op = op
        self.operands = operands

    def __str__(self) -> str:
        return "<AST(name='{name}', op='{op}', operands={operands})>".format(
            name=self.__class__.__name__, op=self.op, operands=self.operands
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
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

    def __init__(self, selection: AST, condition: AST) -> None:
        super().__init__()
        self.selection: AST = selection
        self.condition: AST = condition

    def __str__(self) -> str:
        return "<AST(name='{name}', selection={selection}, condition={condition})>".format(
            name=self.__class__.__name__,
            selection=self.selection,
            condition=self.condition,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
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

    def __init__(
        self,
        operand: AST,
        period_indicator: str,
        component: str | None,
        shift_number: "AST",
    ) -> None:
        super().__init__()
        self.operand: AST = operand
        self.component = component
        self.period_indicator = period_indicator
        self.shift_number: AST = shift_number

    def __str__(self) -> str:
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

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "operand": self.operand,
            "period_indicator": {
                "class_name": "Constant",
                "type_": "String",
                "value": self.period_indicator,
            },
            "shift_number": self.shift_number.toJSON(),
            "reference_period": self.component,
        }


class AnnualiseOp(AST):
    """AST node for the annualise(op, fyEnd, var) operator.

    :parameter operand: Recordset or Scalar of numeric type to annualise.
    :parameter fy_end: Integer expression — month code (1-12) of financial year end.
    :parameter component: Property code of the Date-type component of op.
    """

    def __init__(self, operand: "AST", fy_end: "AST", component: str) -> None:
        super().__init__()
        self.op: str = "annualise"
        self.operand: "AST" = operand
        self.fy_end: "AST" = fy_end
        self.component: str = component

    def __str__(self) -> str:
        return "<AST(name='{name}', operand={operand}, fy_end={fy_end}, component={component})>".format(
            name=self.__class__.__name__,
            operand=self.operand,
            fy_end=self.fy_end,
            component=self.component,
        )

    __repr__ = __str__

    def toJSON(self) -> "dict[str, Any]":
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "operand": self.operand,
            "fy_end": self.fy_end,
            "component": self.component,
        }


class DateConstructorOp(AST):
    """AST node for the date(year, month, day) constructor operator.

    :parameter year: Integer expression for the year.
    :parameter month: Integer expression for the month.
    :parameter day: Integer expression for the day.
    """

    def __init__(self, year: "AST", month: "AST", day: "AST") -> None:
        super().__init__()
        self.op: str = "date"
        self.year: "AST" = year
        self.month: "AST" = month
        self.day: "AST" = day

    def __str__(self) -> str:
        return "<AST(name='{name}', year={year}, month={month}, day={day})>".format(
            name=self.__class__.__name__,
            year=self.year,
            month=self.month,
            day=self.day,
        )

    __repr__ = __str__

    def toJSON(self) -> "dict[str, Any]":
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "year": self.year,
            "month": self.month,
            "day": self.day,
        }


class SubstrOp(AST):
    """AST node for the substr(op, start, length) string operator.

    :parameter operand: String expression the substring is extracted from.
    :parameter start: 1-based start position (optional integer).
    :parameter length: number of characters to extract (optional integer).
    """

    def __init__(
        self, operand: "AST", start: int | None, length: int | None
    ) -> None:
        super().__init__()
        self.op: str = "substr"
        self.operand: "AST" = operand
        self.start: int | None = start
        self.length: int | None = length

    def __str__(self) -> str:
        return "<AST(name='{name}', operand={operand}, start={start}, length={length})>".format(
            name=self.__class__.__name__,
            operand=self.operand,
            start=self.start,
            length=self.length,
        )

    __repr__ = __str__

    def toJSON(self) -> "dict[str, Any]":
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "operand": self.operand,
            "start": self.start,
            "length": self.length,
        }


class WhereClauseOp(AST):
    """AST object for the Where clause.

    :parameter operand: Operand where the filter is applied based on condition
    :parameter condition: Boolean expression to be used to filter information in the operand.
    """

    def __init__(self, operand: AST, condition: AST) -> None:
        super().__init__()
        self.operand: AST = operand
        self.condition: AST = condition
        self.key_components: list[str] = []

    def __str__(self) -> str:
        return "<AST(name='{name}', operand={operand}, condition={condition}, key_components={components})>".format(
            name=self.__class__.__name__,
            operand=self.operand,
            condition=self.condition,
            components=self.key_components,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
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

    def __init__(self, operand: AST, component: str) -> None:
        super().__init__()
        self.operand: AST = operand
        self.component = component
        # Populated by OperandsChecking.check_getop_components for adam-engine.
        self.property_id: int | None = None

    def __str__(self) -> str:
        return "<AST(name='{name}', operand={operand}, component='{component}')>".format(
            name=self.__class__.__name__,
            operand=self.operand,
            component=self.component,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "operand": self.operand,
            "component": self.component,
        }


class PreconditionItem(AST):
    """AST Object only used in Preconditions.

    :parameter value: Sets to True or False if the desired table is present in the DB.
    """

    def __init__(
        self, variable_id: str, variable_code: str | None = None
    ) -> None:
        super().__init__()
        self.variable_id = variable_id
        self.variable_code = variable_code

    def __str__(self) -> str:
        return "<AST(name='{name}', variable_id='{variable_id}')>".format(
            name=self.__class__.__name__, variable_id=self.variable_id
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
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

    def __init__(self, operand: AST, rename_nodes: list["RenameNode"]) -> None:
        super().__init__()
        self.operand: AST = operand
        self.rename_nodes = rename_nodes

    def __str__(self) -> str:
        return "<AST(name='{name}', rename_nodes={rename_nodes})>".format(
            name=self.__class__.__name__, rename_nodes=self.rename_nodes
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
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

    def __init__(self, old_name: str, new_name: str) -> None:
        super().__init__()
        self.old_name = old_name
        self.new_name = new_name

    def __str__(self) -> str:
        return "<AST(name='{name}', old_name='{old_name}', new_name='{new_name}')>".format(
            name=self.__class__.__name__,
            old_name=self.old_name,
            new_name=self.new_name,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "old_name": self.old_name,
            "new_name": self.new_name,
        }


class SubAssignment(AST):
    """A single property substitution within a sub clause.

    :parameter property_code: Property code to substitute
    :parameter value: Value to substitute (can be a literal, select, or itemReference)
    """

    def __init__(self, property_code: str, value: AST) -> None:
        super().__init__()
        self.property_code = property_code
        self.value = value

    def __str__(self) -> str:
        return "<AST(name='{name}', property_code='{property_code}', value={value})>".format(
            name=self.__class__.__name__,
            property_code=self.property_code,
            value=self.value,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "property_code": self.property_code,
            "value": self.value,
        }


class SubOp(AST):
    """AST Object for the Sub operator. Filters a recordset based on one or more property substitutions.

    :parameter operand: Recordset to be filtered
    :parameter substitutions: List of SubAssignment nodes (property_code = value)
    """

    def __init__(
        self, operand: AST, substitutions: list[SubAssignment]
    ) -> None:
        super().__init__()
        self.operand: AST = operand
        self.substitutions = substitutions

    def __str__(self) -> str:
        return "<AST(name='{name}', operand={operand}, substitutions={substitutions})>".format(
            name=self.__class__.__name__,
            operand=self.operand,
            substitutions=self.substitutions,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "operand": self.operand,
            "substitutions": self.substitutions,
        }


class PropertyReference(AST):
    def __init__(self, code: str) -> None:
        super().__init__()
        self.code = code

    def __str__(self) -> str:
        return "<AST(name='{name}', code={code})>".format(
            name=self.__class__.__name__, code=self.code
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {"class_name": self.__class__.__name__, "code": self.code}


class OperationRef(AST):
    def __init__(self, operation_code: str) -> None:
        super().__init__()
        self.operation_code = operation_code

    def __str__(self) -> str:
        return (
            "<AST(name='{name}', operation_code='{operation_code}')>".format(
                name=self.__class__.__name__,
                operation_code=self.operation_code,
            )
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "operation_code": self.operation_code,
        }


class PersistentAssignment(AST):
    def __init__(self, left: AST, op: str, right: AST) -> None:
        super().__init__()
        self.left: AST = left
        self.op = op
        self.right: AST = right

    def __str__(self) -> str:
        return "<AST(name='{name}', op='{op}', left={left}, right={right})>".format(
            name=self.__class__.__name__,
            op=self.op,
            left=self.left,
            right=self.right,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "left": self.left,
            "right": self.right,
        }


class TemporaryAssignment(AST):
    def __init__(self, left: AST, op: str, right: AST) -> None:
        super().__init__()
        self.left: AST = left
        self.op = op
        self.right: AST = right

    def __str__(self) -> str:
        return "<AST(name='{name}', op='{op}', left={left}, right={right})>".format(
            name=self.__class__.__name__,
            op=self.op,
            left=self.left,
            right=self.right,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "left": self.left,
            "right": self.right,
        }


class TemporaryIdentifier(AST):
    def __init__(self, value: str) -> None:
        super().__init__()
        self.value = value

    def __str__(self) -> str:
        return "<AST(name='{name}', value='{value}')>".format(
            name=self.__class__.__name__, value=self.value
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {"class_name": self.__class__.__name__, "value": self.value}


class SetOfOp(AST):
    """AST node for ``set_of(...)`` / ``setof(...)``.

    Two shapes are supported:

    - ``set_of(recordset)`` — projects the recordset's fact values to a
      ``ScalarSet`` (unary coercion, ``component=None``).
    - ``set_of(recordset, component)`` — projects the recordset to the
      scalar set of a single component (a property/dimension code, e.g.
      ``INC``). Emits the values of that component instead of the fact
      column.

    Both spellings ``set_of`` and ``setof`` are accepted by the lexer as
    aliases of the same token.
    """

    def __init__(self, operand: AST, component: str | None = None) -> None:
        super().__init__()
        self.op: str = "set_of"
        self.operand: AST = operand
        self.component: str | None = component

    def __str__(self) -> str:
        return (
            "<AST(name='{name}', operand={operand}, "
            "component={component})>".format(
                name=self.__class__.__name__,
                operand=self.operand,
                component=self.component,
            )
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "operand": self.operand,
            "component": self.component,
        }


class UnionSetOp(AST):
    """AST node for union(s1, s2, …), variadic set union."""

    def __init__(self, operands: list[AST]) -> None:
        super().__init__()
        self.op: str = "union"
        self.operands: list[AST] = operands

    def __str__(self) -> str:
        return "<AST(name='{name}', op='{op}', operands={operands})>".format(
            name=self.__class__.__name__, op=self.op, operands=self.operands
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "operands": self.operands,
        }


class IntersectSetOp(AST):
    """AST node for intersect(s1, s2, …), variadic set intersection."""

    def __init__(self, operands: list[AST]) -> None:
        super().__init__()
        self.op: str = "intersect"
        self.operands: list[AST] = operands

    def __str__(self) -> str:
        return "<AST(name='{name}', op='{op}', operands={operands})>".format(
            name=self.__class__.__name__, op=self.op, operands=self.operands
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "operands": self.operands,
        }


class SetdiffOp(AST):
    """AST node for setdiff(left, right), elements in left that are not in right."""

    def __init__(self, left: AST, right: AST) -> None:
        super().__init__()
        self.op: str = "setdiff"
        self.left: AST = left
        self.right: AST = right

    def __str__(self) -> str:
        return "<AST(name='{name}', op='{op}', left={left}, right={right})>".format(
            name=self.__class__.__name__,
            op=self.op,
            left=self.left,
            right=self.right,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "left": self.left,
            "right": self.right,
        }


class SymdiffOp(AST):
    """AST node for symdiff(left, right), elements in exactly one of left or right."""

    def __init__(self, left: AST, right: AST) -> None:
        super().__init__()
        self.op: str = "symdiff"
        self.left: AST = left
        self.right: AST = right

    def __str__(self) -> str:
        return "<AST(name='{name}', op='{op}', left={left}, right={right})>".format(
            name=self.__class__.__name__,
            op=self.op,
            left=self.left,
            right=self.right,
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "left": self.left,
            "right": self.right,
        }


class CountSetOp(AST):
    """AST node for count(setExpression), cardinality of a ScalarSet."""

    def __init__(self, operand: AST) -> None:
        super().__init__()
        self.op: str = "count"
        self.operand: AST = operand

    def __str__(self) -> str:
        return "<AST(name='{name}', operand={operand})>".format(
            name=self.__class__.__name__, operand=self.operand
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        return {
            "class_name": self.__class__.__name__,
            "op": self.op,
            "operand": self.operand,
        }


class ParameterRef(AST):
    """AST object for a Parameter Selection.

    Two spellings are accepted by the grammar:

    - **Verbose**: ``{p_code, type [, default: value]}`` — the parameter's
      scalar type is declared inline.
    - **Simplified**: ``{p_code}`` — the type is left ``None`` and the
      semantic analyser resolves it later from the taxonomy's parameter
      registry.

    A parameter is an execution-time input supplied to an Operation at
    runtime; the verbose form is what the AST-only tooling has always
    used, while the simplified form matches the historical DPM-XL corpus
    where parameters are declared once at the module level.

    :parameter code: Parameter code (the ``p``/``p_``/backtick prefix stripped).
    :parameter param_type: Declared type keyword, e.g. ``"number"`` or
        ``"set-item"`` (the full keyword, including the ``set-`` prefix),
        or ``None`` when the simplified form is used.
    :parameter default: Declared default as an AST node (``Constant``/``Scalar``/
        ``Set``) or ``None`` when omitted (implicit ``null``).

    ``is_set`` is a derived property (``set-*`` prefix of ``param_type``),
    not a stored field, so there is one source of truth for set-ness; a
    simplified reference without a declared type is not a set by default.
    """

    def __init__(
        self,
        code: str,
        param_type: "str | None",
        default: "AST | None" = None,
    ) -> None:
        super().__init__()
        self.code = code
        self.param_type = param_type
        self.default = default

    @property
    def is_set(self) -> bool:
        """``True`` for the ``set-*`` variants (derived from ``param_type``).

        A simplified reference (``param_type is None``) is not classified
        as a set here; the semantic analyser upgrades the classification
        after resolving the parameter's registered type.
        """
        return self.param_type is not None and self.param_type.startswith(
            "set-"
        )

    def __str__(self) -> str:
        return (
            "<AST(name='{name}', code='{code}', param_type='{param_type}', "
            "is_set={is_set}, default={default})>".format(
                name=self.__class__.__name__,
                code=self.code,
                param_type=self.param_type,
                is_set=self.is_set,
                default=self.default,
            )
        )

    __repr__ = __str__

    def toJSON(self) -> dict[str, Any]:
        # ``is_set`` is not serialised (derivable from the ``set-`` prefix).
        # ``param_type`` is emitted in the engine's canonical PascalCase
        # (``number`` -> ``Number``); a ``None`` type stays ``None`` in the
        # payload, so downstream consumers can distinguish the simplified
        # form and defer resolution to the same registry the semantic
        # analyser used. ``default`` IS serialised: it is the per-reference
        # fallback carried on the node (it has no home in the flat
        # ``{code: type}`` parameters meta-dictionary, which stays type-only).
        return {
            "class_name": self.__class__.__name__,
            "code": self.code,
            "param_type": (
                canonical_param_type(self.param_type)
                if self.param_type is not None
                else None
            ),
            "default": parameter_default_value(self.default),
        }


# Grammar parameter-type keyword -> engine canonical (PascalCase) scalar name.
_CANONICAL_PARAM_SCALAR = {
    "number": "Number",
    "integer": "Integer",
    "string": "String",
    "date": "Date",
    "boolean": "Boolean",
    "item": "Item",
}


def canonical_param_type(param_type: str) -> str:
    """Map a grammar parameter-type keyword to the engine's canonical name.

    The engine names scalar types in PascalCase (``Number``, ``Integer``, …),
    so a parameter's declared type is surfaced that way: ``number`` -> ``Number``.
    Set variants become ``Set`` + the PascalCase element, with no separator:
    ``set-number`` -> ``SetNumber``. Idempotent — applying it to an
    already-canonical value is a no-op.
    """
    if param_type.startswith("set-"):
        element = param_type[len("set-") :]
        return "Set" + _CANONICAL_PARAM_SCALAR.get(element, element)
    return _CANONICAL_PARAM_SCALAR.get(param_type, param_type)


def parameter_default_value(default: "AST | None") -> Any:
    """Reduce a parameter ``default`` AST node to a JSON-friendly value.

    Used by both the serialization layer and the service surface so the
    reported default is a single, consistent representation:
    ``None`` for an omitted/``null`` default, the literal value for a
    ``Constant``, the item signature for an item ``Scalar``, and a list of the
    above for a ``Set``.
    """
    if default is None:
        return None
    if isinstance(default, Constant):
        return None if default.type == "Null" else default.value
    if isinstance(default, Scalar):
        return default.item
    if isinstance(default, Set):
        return [parameter_default_value(child) for child in default.children]
    return None
