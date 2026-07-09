from abc import ABC
from typing import Any, cast

import pandas as pd

from dpmcore import errors
from dpmcore.dpm_xl.ast.nodes import (
    AggregationOp,
    AnnualiseOp,
    BinOp,
    ComplexNumericOp,
    CondExpr,
    Constant,
    CountSetOp,
    DateConstructorOp,
    Dimension,
    FilterOp,
    GetOp,
    IntersectSetOp,
    OperationRef,
    ParameterRef,
    ParExpr,
    PersistentAssignment,
    PreconditionItem,
    PropertyReference,
    RankOp,
    RenameOp,
    Set,
    SetdiffOp,
    SetOfOp,
    Start,
    SubOp,
    SubstrOp,
    SymdiffOp,
    TemporaryAssignment,
    TimeShiftOp,
    UnaryOp,
    UnionSetOp,
    VarID,
    VarRef,
    WhereClauseOp,
    WithExpression,
)
from dpmcore.dpm_xl.ast.nodes import (
    Scalar as ScalarNode,
)
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.ast.where_clause import (
    collect_where_equality_pins,
    merge_where_constraints,
)
from dpmcore.dpm_xl.operators.clause import Sub as SubOperator
from dpmcore.dpm_xl.symbols import (
    Component,
    ConstantOperand,
    FactComponent,
    KeyComponent,
    Operand,
    RecordSet,
    Scalar,
    ScalarSet,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import (
    Boolean,
    Integer,
    Item,
    Mixed,
    Null,
    ScalarFactory,
    ScalarType,
)
from dpmcore.dpm_xl.utils.data_handlers import filter_all_data
from dpmcore.dpm_xl.utils.operands_mapping import set_operand_label
from dpmcore.dpm_xl.utils.operator_mapping import (
    AGGR_OP_MAPPING,
    BIN_OP_MAPPING,
    CLAUSE_OP_MAPPING,
    COMPLEX_OP_MAPPING,
    CONDITIONAL_OP_MAPPING,
    RANK_OP_MAPPING,
    STRING_OPERATORS,
    TIME_OPERATORS,
    UNARY_OP_MAPPING,
)
from dpmcore.dpm_xl.utils.tokens import (
    ANNUALISE,
    DATE,
    DPM,
    FILTER,
    GET,
    IF,
    RENAME,
    STANDARD,
    SUB,
    SUBSTR,
    TIME_SHIFT,
    WHERE,
)
from dpmcore.dpm_xl.warning_collector import add_semantic_warning
from dpmcore.errors import SemanticError

# Maps a (scalar) parameter type keyword to its ScalarFactory type name. The
# ``set-*`` variants reuse these via their element keyword (``set-item`` ->
# ``item``). The grammar restricts parameter types to exactly these keywords.
_PARAMETER_SCALAR_TYPES: dict[str, str] = {
    "number": "Number",
    "integer": "Integer",
    "string": "String",
    "date": "Date",
    "boolean": "Boolean",
    "item": "Item",
}


class InputAnalyzer(ASTTemplate, ABC):
    def __init__(self, expression: str) -> None:
        super().__init__()
        self.data: pd.DataFrame | None = None
        self.key_components: dict[str, pd.DataFrame] = {}
        self.open_keys: pd.DataFrame | None = None
        self.result: bool = False
        self._expression: str = expression  # For debugging purposes only
        self.preconditions: bool = False

        self.calculations_outputs: dict[str, Operand] = {}

        # Implicit open keys that are always available without being declared
        # These are special dimensions that arise from the reporting context itself
        self.global_variables: dict[str, ScalarType] = {
            "refPeriod": ScalarFactory().database_types_mapping(
                "d"
            )(),  # date type
            "entityID": ScalarFactory().database_types_mapping(
                "s"
            )(),  # string type
        }

    # Start of visiting nodes.

    def visit_Start(  # type: ignore[override]
        self, node: Start
    ) -> Operand | list[Operand]:

        result: list[Operand] = []
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
                return cast(Operand, result_symbol)
            result.append(cast(Operand, result_symbol))

        return result

    def visit_PersistentAssignment(  # type: ignore[override]
        self, node: PersistentAssignment
    ) -> Operand:
        return cast(Operand, self.visit(node.right))

    def visit_TemporaryAssignment(  # type: ignore[override]
        self, node: TemporaryAssignment
    ) -> Operand:

        right = cast(Operand, self.visit(node.right))
        right.name = cast(str, node.left.value)
        self.calculations_outputs[right.name] = right
        return right

    def visit_ParExpr(  # type: ignore[override]
        self, node: ParExpr
    ) -> Operand:
        return cast(Operand, self.visit(node.expression))

    def visit_BinOp(  # type: ignore[override]
        self, node: BinOp
    ) -> Operand:
        left_symbol = self.visit(node.left)
        right_symbol = self.visit(node.right)
        # node.op is declared ``str | None`` on the AST base, but BinOp always
        # constructs with a concrete str; narrow via cast so lookups type-check.
        op = cast(str, node.op)
        # BIN_OP_MAPPING is typed as ``dict[str, type[Operator]]`` after mypy
        # inference, and the Operator base class does not declare ``validate``
        # (Binary/ConditionalOperator subclasses do). Runtime dispatch is safe.
        operator_cls = cast(Any, BIN_OP_MAPPING[op])
        result = operator_cls.validate(left_symbol, right_symbol)

        return cast(Operand, result)

    def visit_UnaryOp(  # type: ignore[override]
        self, node: UnaryOp
    ) -> Operand:
        operand_symbol = self.visit(node.operand)
        op = cast(str, node.op)
        if op in UNARY_OP_MAPPING:
            result = UNARY_OP_MAPPING[op].validate_types(operand_symbol)
        else:
            if not isinstance(
                operand_symbol, (RecordSet, Scalar, ConstantOperand)
            ):
                raise errors.SemanticError("4-7-1", op=op)
            result = cast(Any, TIME_OPERATORS[op]).validate_types(
                operand_symbol
            )

        return result

    def visit_CondExpr(  # type: ignore[override]
        self, node: CondExpr
    ) -> Operand:
        condition_symbol = self.visit(node.condition)
        then_symbol = self.visit(node.then_expr)
        else_symbol = (
            None if node.else_expr is None else self.visit(node.else_expr)
        )
        result = CONDITIONAL_OP_MAPPING[IF].validate(
            condition_symbol, then_symbol, else_symbol
        )
        return cast(Operand, result)

    def visit_VarRef(  # type: ignore[override]
        self, node: VarRef
    ) -> Scalar:
        type_ = ScalarFactory().scalar_factory(code="Boolean")
        label = cast(str, node.label)
        return Scalar(type_=type_, name=label, origin=label)

    def visit_PropertyReference(self, node: PropertyReference) -> None:
        raise SemanticError("7-1")

    @staticmethod
    def __check_default_value(default_value: Any, type_: ScalarType) -> None:
        if default_value is None:
            return
        default_type = ScalarFactory().scalar_factory(code=default_value.type)
        from dpmcore.dpm_xl.types.promotion import implicit_type_promotion_dict

        default_implicities = implicit_type_promotion_dict.get(
            default_type.__class__, set()
        )
        cell_implicities = implicit_type_promotion_dict.get(
            type_.__class__, set()
        )
        # A default fills the cell, so its type must be implicitly castable
        # *to* the cell type (spec §2.3.2) — a one-directional check. The
        # reverse direction is meaningless: every type is implicitly castable
        # to String, so a bidirectional check wrongly accepts e.g. a String
        # default on a Number cell (String → Number is an Explicit cast).
        # Null already promotes to every type; a Mixed cell has unknown type
        # (no dict entry, empty ``cell_implicities``) and accepts any default.
        if cell_implicities and not type_.is_included(default_implicities):
            raise errors.SemanticError(
                "3-6", expected_type=type_, default_type=default_type
            )

    def visit_VarID(  # type: ignore[override]
        self, node: VarID
    ) -> Operand:

        # node.type is ScalarType | None on AST base but ``visit_VarID`` is only
        # reached after operand checks populate it; same for label/table.
        node_type = cast(ScalarType, node.type)
        # A cell reference shares the grammar's ``default`` rule with parameter
        # references, so a set default (``default: {...}``) parses here too.
        # Set defaults are not supported on any selection: reject with the same
        # meaningful 3-9. Item/literal/null defaults stay valid below.
        # A single-element set default (``default: {p_x, number}``) is unwrapped
        # to a bare ``ParameterRef`` by ``visitSetElements``, so guard both shapes.
        if isinstance(node.default, (Set, ParameterRef)):
            raise errors.SemanticError(
                "3-9", reference=f"cell selection {node.table or node.label}"
            )
        self.__check_default_value(node.default, node_type)

        table_code = cast(str, node.table)
        rows = list(node.rows) if node.rows is not None else []
        cols = list(node.cols) if node.cols is not None else []
        sheets = list(node.sheets) if node.sheets is not None else []

        # filter by table_code
        df = filter_all_data(
            cast(pd.DataFrame, self.data),
            table_code,
            rows,
            cols,
            sheets,
        )

        scalar_factory = ScalarFactory()
        interval = getattr(node, "interval", None) or False

        # pandas' typeshed declares Series.apply to return scalar literal
        # types, but downstream code expects the column to hold live
        # ScalarType objects; cast at the boundary only.
        def _to_scalar_type(x: Any) -> Any:
            return scalar_factory.from_database_to_scalar_types(x, interval)

        data_types = df["data_type"].apply(_to_scalar_type)
        df["data_type"] = data_types

        label = cast(str, node.label)
        components: list[Component] = []
        if self.key_components and table_code in self.key_components:
            dpm_keys = self.key_components[table_code]
            if len(dpm_keys) > 0:
                for key_name, key_type in zip(
                    dpm_keys["property_code"],
                    dpm_keys["data_type"],
                    strict=False,
                ):
                    type_: ScalarType
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

        standard_keys: list[KeyComponent] = []
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
            return Scalar(type_=node_type, name=label, origin=label)
        fact_component = FactComponent(type_=node_type, parent=label)

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
    def _check_standard_key(
        key_components: list[KeyComponent],
        elements: "pd.Series[Any]",
        name: str,
        parent: str,
    ) -> None:
        if len(elements) > 1 and len(elements.unique()) > 1:
            key_component = KeyComponent(
                name=name, type_=Null(), subtype=STANDARD, parent=parent
            )
            key_components.append(key_component)

    def visit_Constant(  # type: ignore[override]
        self, node: Constant
    ) -> ConstantOperand:
        # ``Constant.type`` legacy-shares the AST ``type`` attribute but stores
        # a string code (see nodes.py comment). Reflect that at the call site.
        constant_type = ScalarFactory().scalar_factory(
            code=cast(str | None, node.type)
        )
        return ConstantOperand(
            type_=constant_type, name=None, origin=node.value, value=node.value
        )

    def visit_AggregationOp(  # type: ignore[override]
        self, node: AggregationOp
    ) -> Operand:
        operand = self.visit(node.operand)
        if not isinstance(operand, RecordSet):
            raise errors.SemanticError("4-4-0-1", op=node.op)

        if operand.has_only_global_components:
            add_semantic_warning(
                f"Performing an aggregation on recordset: {operand.name} which has only global key components"
            )

        op = cast(str, node.op)

        if node.analytic_clause is not None:
            if isinstance(operand.get_fact_component().type, Mixed):
                raise errors.SemanticError("4-4-0-3", origin=f"{op}(...)")
            result = AGGR_OP_MAPPING[op].validate_analytic(
                operand, node.analytic_clause
            )
            return cast(Operand, result)

        grouping_clause = None
        if node.grouping_clause:
            grouping_clause = node.grouping_clause.components

        if isinstance(operand.get_fact_component().type, Mixed):
            origin_expression = AGGR_OP_MAPPING[op].generate_origin_expression(
                operand, grouping_clause
            )
            raise errors.SemanticError("4-4-0-3", origin=origin_expression)

        reducing_result: RecordSet | Scalar = AGGR_OP_MAPPING[op].validate(
            operand, grouping_clause
        )
        return cast(Operand, reducing_result)

    def visit_RankOp(  # type: ignore[override]
        self, node: RankOp
    ) -> Operand:
        operand = self.visit(node.operand)
        if not isinstance(operand, RecordSet):
            raise errors.SemanticError("4-4-0-1", op="rank")
        if operand.has_only_global_components:
            add_semantic_warning(
                f"Performing an aggregation on recordset: {operand.name} which has only global key components"
            )
        op = cast(str, node.op)
        result = RANK_OP_MAPPING[op].validate_analytic(
            operand, node.analytic_clause
        )
        return cast(Operand, result)

    def visit_Dimension(  # type: ignore[override]
        self, node: Dimension
    ) -> Scalar:
        # Check if this is an implicit open key (refPeriod, entityID)
        if node.dimension_code in self.global_variables:
            gtype = self.global_variables[node.dimension_code]
            return Scalar(type_=gtype, name=None, origin=node.dimension_code)

        # Otherwise, look up from the database-backed open_keys
        open_keys = cast(pd.DataFrame, self.open_keys)
        dimension_data = open_keys[
            open_keys["property_code"] == node.dimension_code
        ].reset_index(drop=True)
        type_: ScalarType
        if dimension_data["data_type"][0] is not None:
            type_code = dimension_data["data_type"][0]
            type_ = ScalarFactory().database_types_mapping(code=type_code)()
        else:
            type_ = ScalarFactory().scalar_factory(code="Item")
        return Scalar(type_=type_, name=None, origin=node.dimension_code)

    def visit_Set(  # type: ignore[override]
        self, node: Set
    ) -> ScalarSet:

        common_type_code: str
        if not node.children:
            common_type = ScalarFactory().scalar_factory("Item")
            return ScalarSet(type_=common_type, name=None, origin="{}")
        if isinstance(node.children[0], Constant):
            # ``Constant.type`` is stored as a str (see visit_Constant); the
            # shared AST annotation is ScalarType | None, so narrow at use.
            constant_children = cast(list[Constant], node.children)
            types: set[str] = {
                cast(str, child.type) for child in constant_children
            }
            if len(types) > 1:
                raise errors.SemanticError(
                    "3-3",
                    type_1=", ".join(types),
                    type_op="homogeneous scalar type",
                    origin="set literal",
                )
            common_type_code = types.pop()
            origin_elements = [str(child.value) for child in constant_children]
        else:
            common_type_code = "Item"
            # Non-constant set members are AST.Scalar (via ASTTemplate); they
            # expose ``item``. We keep the runtime attribute access but tell
            # mypy about the underlying type.
            scalar_children = cast(list[ScalarNode], node.children)
            origin_elements = [
                "[" + child.item + "]" for child in scalar_children
            ]
        common_type = ScalarFactory().scalar_factory(common_type_code)
        origin = ", ".join(origin_elements)
        origin = "{" + origin + "}"

        return ScalarSet(type_=common_type, name=None, origin=origin)

    def visit_Scalar(  # type: ignore[override]
        self, node: ScalarNode
    ) -> Scalar:
        type_ = ScalarFactory().scalar_factory(node.scalar_type)
        return Scalar(type_=type_, origin=node.item, name=None)

    def visit_ParameterRef(  # type: ignore[override]
        self, node: ParameterRef
    ) -> Operand:
        element_keyword = (
            node.param_type[len("set-") :] if node.is_set else node.param_type
        )
        element_type = ScalarFactory().scalar_factory(
            code=_PARAMETER_SCALAR_TYPES[element_keyword]
        )
        self.__check_parameter_default(node, element_keyword, element_type)
        if node.is_set:
            return ScalarSet(type_=element_type, name=None, origin=node.code)
        return Scalar(type_=element_type, name=None, origin=node.code)

    def __check_parameter_default(
        self,
        node: ParameterRef,
        element_keyword: str,
        element_type: ScalarType,
    ) -> None:
        default = node.default
        if default is None:
            return
        # Explicit null is always accepted (the implicit default is null too).
        if isinstance(default, Constant) and default.type == "Null":
            return
        if node.is_set:
            # A set-typed parameter takes a set default (``default: {...}``)
            # whose elements each match the declared element type, per the
            # DPM-XL spec. (A set default on a *cell* selection is a different
            # rule and stays rejected with 3-9 in ``visit_VarID``.)
            self.__check_set_parameter_default(
                default, element_keyword, element_type, node.param_type
            )
            return
        self.__check_scalar_parameter_default(
            default, element_keyword, element_type, node.param_type
        )

    def __check_set_parameter_default(
        self,
        default: Any,
        element_keyword: str,
        element_type: ScalarType,
        declared_type: str,
    ) -> None:
        # A set-typed default must be a literal set; each element is then
        # validated like a scalar default of the element type. A single
        # parameter ref (``default: {p_x, number}``) is unwrapped to a bare
        # ``ParameterRef`` by the constructor, so it is not a ``Set`` and is
        # rejected here as incompatible with the declared type.
        if not isinstance(default, Set):
            raise SemanticError("3-7", declared_type=declared_type)
        for element in default.children:
            self.__check_scalar_parameter_default(
                element, element_keyword, element_type, declared_type
            )

    def __check_scalar_parameter_default(
        self,
        default: Any,
        element_keyword: str,
        element_type: ScalarType,
        declared_type: str,
    ) -> None:
        if element_keyword == "item":
            if not (
                isinstance(default, ScalarNode)
                and default.scalar_type == "Item"
            ):
                raise SemanticError("3-7", declared_type=declared_type)
            return
        # number / integer / string / date / boolean: a compatible literal.
        if not isinstance(default, Constant):
            raise SemanticError("3-7", declared_type=declared_type)
        self.__check_default_value(default, element_type)

    def visit_ComplexNumericOp(  # type: ignore[override]
        self, node: ComplexNumericOp
    ) -> Operand:
        op = cast(str, node.op)
        if op not in COMPLEX_OP_MAPPING:
            raise NotImplementedError

        symbols = [self.visit(operand) for operand in node.operands]

        result = COMPLEX_OP_MAPPING[op].validate(symbols)
        return cast(Operand, result)

    def visit_FilterOp(  # type: ignore[override]
        self, node: FilterOp
    ) -> Operand:
        selection = self.visit(node.selection)
        condition = self.visit(node.condition)
        result = CONDITIONAL_OP_MAPPING[FILTER].validate(selection, condition)
        return cast(Operand, result)

    def visit_TimeShiftOp(  # type: ignore[override]
        self, node: TimeShiftOp
    ) -> Operand:
        shift_operand = self.visit(node.shift_number)
        if not isinstance(shift_operand, Scalar) or not isinstance(
            shift_operand.type, Integer
        ):
            raise errors.SemanticError("4-7-4")

        operand = self.visit(node.operand)
        if not isinstance(operand, (RecordSet, Scalar, ConstantOperand)):
            raise errors.SemanticError("4-7-1", op=TIME_SHIFT)
        component_name = cast(str, node.component)
        shift_number = (
            node.shift_number.value
            if isinstance(node.shift_number, Constant)
            else 0
        )
        result = cast(Any, TIME_OPERATORS[TIME_SHIFT]).validate(
            operand=operand,
            component_name=component_name,
            period=node.period_indicator,
            shift_number=shift_number,
        )
        return result

    def visit_AnnualiseOp(  # type: ignore[override]
        self, node: AnnualiseOp
    ) -> Operand:
        fy_end_sym = self.visit(node.fy_end)
        if not isinstance(
            fy_end_sym, (Scalar, ConstantOperand)
        ) or not isinstance(fy_end_sym.type, Integer):
            raise errors.SemanticError("4-7-4")

        fy_end_value = (
            int(node.fy_end.value)
            if isinstance(node.fy_end, Constant)
            else None
        )

        operand = self.visit(node.operand)
        if not isinstance(operand, (RecordSet, Scalar, ConstantOperand)):
            raise errors.SemanticError("4-7-1", op=ANNUALISE)

        result = cast(Any, TIME_OPERATORS[ANNUALISE]).validate(
            operand=operand,
            component_name=node.component,
            fy_end=fy_end_value,
        )
        return cast(Operand, result)

    def visit_DateConstructorOp(  # type: ignore[override]
        self, node: DateConstructorOp
    ) -> Operand:
        year_sym = self.visit(node.year)
        month_sym = self.visit(node.month)
        day_sym = self.visit(node.day)
        result = cast(Any, TIME_OPERATORS[DATE]).validate(
            year_sym, month_sym, day_sym
        )
        return cast(Operand, result)

    def visit_SubstrOp(  # type: ignore[override]
        self, node: SubstrOp
    ) -> Operand:
        operand = self.visit(node.operand)
        if not isinstance(operand, (RecordSet, Scalar, ConstantOperand)):
            raise errors.SemanticError("4-7-1", op=SUBSTR)
        result = cast(Any, STRING_OPERATORS[SUBSTR]).validate(
            operand, node.start, node.length
        )
        return cast(Operand, result)

    def visit_WhereClauseOp(  # type: ignore[override]
        self, node: WhereClauseOp
    ) -> RecordSet:

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
        # Record which dimensions this filter pins to a single value, merged
        # with any carried by the inner operand (e.g. chained where clauses),
        # so a binary operator can spot a contradictory inner join.
        result.where_constraints = merge_where_constraints(
            getattr(operand, "where_constraints", {}),
            collect_where_equality_pins(node.condition),
        )
        return result

    def visit_RenameOp(  # type: ignore[override]
        self, node: RenameOp
    ) -> RecordSet:
        operand = self.visit(node.operand)
        names: list[str] = []
        new_names: list[str] = []
        for rename_node in node.rename_nodes:
            names.append(rename_node.old_name)
            new_names.append(rename_node.new_name)
        result = CLAUSE_OP_MAPPING[RENAME].validate(
            operand=operand, key_names=names, new_names=new_names
        )
        return result

    def visit_GetOp(  # type: ignore[override]
        self, node: GetOp
    ) -> RecordSet:
        operand = self.visit(node.operand)
        key_names = [node.component]
        result = CLAUSE_OP_MAPPING[GET].validate(operand, key_names)
        return result

    def visit_SubOp(  # type: ignore[override]
        self, node: SubOp
    ) -> RecordSet:
        # CLAUSE_OP_MAPPING[SUB] is the ``Sub`` subclass at runtime, whose
        # ``validate`` intentionally narrows the base signature (see
        # operators/clause.py). Call it directly so mypy sees the correct
        # signature; the mapping lookup would yield the erased base type.
        _ = CLAUSE_OP_MAPPING[SUB]
        # Reject duplicate property codes up-front. Otherwise the chain
        # below would drop the component on the first iteration and the
        # second would fail with a misleading "key not on recordset" error
        # (code 2-8) from operators/clause.py.
        seen: set[str] = set()
        for sub in node.substitutions:
            if sub.property_code in seen:
                raise errors.SemanticError(
                    "4-5-3-1", property_code=sub.property_code
                )
            seen.add(sub.property_code)
        result = self.visit(node.operand)
        for sub in node.substitutions:
            value = self.visit(sub.value)
            result = SubOperator.validate(
                operand=result, property_code=sub.property_code, value=value
            )
        return result

    def visit_PreconditionItem(  # type: ignore[override]
        self, node: PreconditionItem
    ) -> Scalar:
        """Return a ScalarType Boolean with True value is precondition is satisfied otherwise False.
        Example:
        "table_code","ColumnID","RowID","SheetID","column_code","row_code","sheet_code","cell_code","CellID","VariableVID","data_type_code"
        S.01.01.01.01,,,,,,,,,xxxxxxx,BOO
        We can check with table_code or VariableVID, here for now, we use table_code.
        """
        type_ = ScalarFactory().scalar_factory(code="Boolean")

        label = cast(str, node.label)
        return Scalar(type_=type_, name=label, origin=label)

    def visit_OperationRef(  # type: ignore[override]
        self, node: OperationRef
    ) -> Operand:

        operation_code = node.operation_code
        if operation_code not in self.calculations_outputs:
            raise errors.SemanticError("1-9", operation_code=operation_code)
        return self.calculations_outputs[operation_code]

    def visit_WithExpression(  # type: ignore[override]
        self, node: WithExpression
    ) -> Operand:
        return cast(Operand, self.visit(node.expression))

    def visit_SetOfOp(  # type: ignore[override]
        self, node: SetOfOp
    ) -> ScalarSet:
        operand = self.visit(node.operand)
        if not isinstance(operand, RecordSet):
            raise errors.SemanticError("4-7-1", op="set_of")
        fact_type = operand.get_fact_component().type
        return ScalarSet(type_=fact_type, name=None, origin="set_of")

    def _visit_set_operands(self, operands: list[Any]) -> ScalarSet:
        """Validate that all operands are ScalarSet with a common type and return one."""
        symbols: list[ScalarSet] = []
        for op in operands:
            result = self.visit(op)
            # §13.1.5: a RecordSet operand is implicitly treated as the
            # ScalarSet of its Fact Component values, as if wrapped in set_of.
            if isinstance(result, RecordSet):
                fact_type = result.get_fact_component().type
                result = ScalarSet(type_=fact_type, name=None, origin="set_of")
            if not isinstance(result, ScalarSet):
                raise errors.SemanticError(
                    "3-3",
                    type_1=type(result).__name__,
                    type_op="ScalarSet",
                    origin="set operator",
                )
            symbols.append(result)
        types = {sym.type.__class__ for sym in symbols}
        if len(types) > 1:
            type_names = ", ".join(t.__name__ for t in types)
            raise errors.SemanticError(
                "3-3",
                type_1=type_names,
                type_op="homogeneous scalar type",
                origin="set operator",
            )
        return symbols[0]

    def visit_UnionSetOp(  # type: ignore[override]
        self, node: UnionSetOp
    ) -> ScalarSet:
        return self._visit_set_operands(node.operands)

    def visit_IntersectSetOp(  # type: ignore[override]
        self, node: IntersectSetOp
    ) -> ScalarSet:
        return self._visit_set_operands(node.operands)

    def visit_SetdiffOp(  # type: ignore[override]
        self, node: SetdiffOp
    ) -> ScalarSet:
        return self._visit_set_operands([node.left, node.right])

    def visit_SymdiffOp(  # type: ignore[override]
        self, node: SymdiffOp
    ) -> ScalarSet:
        return self._visit_set_operands([node.left, node.right])

    def visit_CountSetOp(  # type: ignore[override]
        self, node: CountSetOp
    ) -> Scalar:
        operand = self.visit(node.operand)
        if not isinstance(operand, ScalarSet):
            raise errors.SemanticError(
                "3-3",
                type_1=type(operand).__name__,
                type_op="ScalarSet",
                origin="count",
            )
        return Scalar(type_=Integer(), name=None, origin="count")
