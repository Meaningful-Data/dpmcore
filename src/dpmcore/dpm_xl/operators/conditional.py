from typing import ClassVar, Union

import pandas as pd

from dpmcore import errors
from dpmcore.dpm_xl.operators.base import Binary, Operator
from dpmcore.dpm_xl.symbols import (
    ConstantOperand,
    Operand,
    RecordSet,
    Scalar,
    Structure,
)
from dpmcore.dpm_xl.types.promotion import (
    binary_implicit_type_promotion,
    binary_implicit_type_promotion_with_mixed_types,
    unary_implicit_type_promotion,
)
from dpmcore.dpm_xl.types.scalar import Mixed, ScalarFactory, ScalarType
from dpmcore.dpm_xl.utils import tokens
from dpmcore.dpm_xl.warning_collector import add_semantic_warning
from dpmcore.errors import SemanticError

# Type aliases used throughout the conditional operators pipeline.
CondOperand = Union[RecordSet, Scalar]


class ConditionalOperator(Operator):
    propagate_attributes: ClassVar[bool] = False

    @classmethod
    def validate(cls, *args: object) -> None:
        # Abstract-ish placeholder; concrete subclasses override with their
        # own signatures. Kept for runtime parity.
        pass

    @classmethod
    def create_labeled_scalar(
        cls,
        rslt_structure: CondOperand | ConstantOperand,
        rslt_type: ScalarType,
        origin: str,
    ) -> Scalar:
        """ """
        if not isinstance(rslt_structure, ConstantOperand):
            scalar = cls._create_labeled_scalar(
                origin=origin, result_type=rslt_type
            )
            return scalar
        else:
            value = rslt_structure.value
            return ConstantOperand(
                type_=ScalarFactory().scalar_factory(str(rslt_type)),
                name=None,
                origin=origin,
                value=value,
            )

    @classmethod
    def _check_same_recordset_structures(
        cls, left: RecordSet, right: RecordSet, origin: str
    ) -> bool:
        """Used for recordset-recordset."""
        left_structure = left.structure
        right_structure = right.structure
        if len(left_structure.get_key_components()) == len(
            right_structure.get_key_components()
        ):
            # For better error management
            class_check = Binary()
            # Binary.op is a ClassVar; overriding on the instance preserves
            # existing runtime behavior of piping cls.op into downstream
            # errors.
            class_check.op = cls.op  # type: ignore[misc]
            class_check.check_same_components(
                left_structure, right_structure, origin
            )
            return True
        return False

    @classmethod
    def _check_structures(
        cls,
        left: RecordSet,
        right: RecordSet,
        origin: str,
        subset_allowed: bool = True,
    ) -> bool:
        """Used for recordset-recordset."""
        left_records = left.records
        right_records = right.records
        if cls._check_same_recordset_structures(left, right, origin):
            # validation for records
            if left_records is not None and right_records is not None:
                result_dataframe = pd.merge(
                    left_records,
                    right_records,
                    on=[
                        col
                        for col in left_records.columns
                        if col != "data_type"
                    ],
                )
                if len(result_dataframe) != len(left_records):
                    raise SemanticError("4-6-0-1")

            return True

        if subset_allowed:
            # operand_is_subset = cls.check_condition_is_subset(selection=left, condition=right)
            operand_is_subset = cls.check_condition_is_subset(
                selection=right, condition=left
            )
            if cls.op in (tokens.NVL, tokens.IF):
                operand_is_subset = cls.check_condition_is_subset(
                    selection=right, condition=left
                )
            else:
                operand_is_subset = cls.check_condition_is_subset(
                    selection=left, condition=right
                )
            if operand_is_subset:
                return True
            raise errors.SemanticError(
                "4-6-0-2", condition=left.name, operand=right.name
            )

        raise SemanticError(
            "2-3",
            op=cls.op,
            structure_1=left.get_key_components_names(),
            structure_2=right.get_key_components_names(),
            origin=origin,
        )

    @classmethod
    def check_condition_is_subset(
        cls, selection: RecordSet, condition: RecordSet
    ) -> bool:

        selection_dpm_components = selection.get_dpm_components()
        condition_dpm_components = condition.get_dpm_components()

        if set(condition.get_key_components_names()) <= set(
            selection.get_key_components_names()
        ):
            for comp_key, comp_value in condition_dpm_components.items():
                if comp_key not in selection_dpm_components:
                    return False
                if (
                    comp_value.type.__class__
                    != selection_dpm_components[comp_key].type.__class__
                ):
                    return False
            return True
        return False

    @staticmethod
    def generate_result_dataframe(
        left: RecordSet, right: RecordSet
    ) -> pd.DataFrame | None:
        if left.records is not None and right.records is not None:
            result_dataframe = pd.merge(
                left.records,
                right.records,
                on=[
                    col for col in right.records.columns if col != "data_type"
                ],
                suffixes=("_left", "_right"),
            )

            result_dataframe["data_type"] = result_dataframe["data_type_left"]
            result_dataframe = result_dataframe.drop(
                columns=["data_type_left", "data_type_right"]
            )

            return result_dataframe

        return None


class IfOperator(ConditionalOperator):
    """ """

    op: ClassVar[str | None] = tokens.IF

    @classmethod
    def create_origin_expression(
        cls,
        condition: Operand,
        then_op: Operand,
        else_op: Operand | None = None,
    ) -> str:
        condition_name = getattr(condition, "name", None) or condition.origin
        then_name = getattr(then_op, "name", None) or then_op.origin
        if else_op:
            else_name = getattr(else_op, "name", None) or else_op.origin
            origin = f"If {condition_name} then {then_name} else {else_name}"
        else:
            origin = f"If {condition_name} then {then_name}"
        return origin

    @classmethod
    def check_condition(cls, condition: CondOperand) -> bool:
        """Check if the condition has Boolean type."""
        if isinstance(condition, RecordSet):
            condition_type = condition.structure.components["f"].type
        else:
            condition_type = condition.type
        # unary implicit promotion
        error_info = {"operand_name": condition.name, "op": cls.op}
        boolean_type = ScalarFactory().scalar_factory("Boolean")
        type_promotion = unary_implicit_type_promotion(
            operand=condition_type,
            op_type_to_check=boolean_type,
            error_info=error_info,
        )
        if type_promotion.strictly_same_class(boolean_type):
            return True

        raise SemanticError("4-6-1-1")

    @classmethod
    def check_structures(
        cls,
        condition: CondOperand,
        first: CondOperand,
        second: CondOperand | None,
        origin: str,
    ) -> tuple[Structure | CondOperand, pd.DataFrame | None]:
        """ """
        if isinstance(condition, Scalar):
            if second is not None:
                # Helper: treat recordsets with only global key components as scalars
                # Per DPM-XL spec, single-cell selections have only global keys
                # ``CondOperand`` narrows to RecordSet when not Scalar, so the
                # ``isinstance(..., RecordSet)`` check on the right of ``or``
                # is technically redundant; the short-circuit still guards
                # attribute access at runtime if CondOperand is widened later.
                first_is_scalar = isinstance(first, Scalar) or (
                    first.has_only_global_components
                )
                second_is_scalar = isinstance(second, Scalar) or (
                    second.has_only_global_components
                )

                if (
                    isinstance(first, RecordSet)
                    and isinstance(second, RecordSet)
                    and not (first_is_scalar or second_is_scalar)
                ):
                    # Both are true recordsets (with standard key components r/c/s)
                    if cls._check_structures(
                        first, second, origin, subset_allowed=False
                    ):
                        return first.structure, first.records
                    raise SemanticError("4-6-1-3")
                elif first_is_scalar and second_is_scalar:
                    # Both are scalars (or single-cell recordsets with only global keys)
                    return first, None
                else:
                    raise SemanticError("4-6-1-3")
            else:
                if isinstance(first, RecordSet):
                    if first.has_only_global_components:
                        return first, None
                    return first.structure, first.records
                return first, None
        else:  # RecordSet condition
            if second is not None:
                # Determine structure for each recordset operand
                then_struct: Structure | None = None
                then_records: pd.DataFrame | None = None
                if isinstance(first, RecordSet):
                    then_struct, then_records = cls._check_if_structures(
                        condition, first, origin
                    )

                else_struct: Structure | None = None
                else_records: pd.DataFrame | None = None
                if isinstance(second, RecordSet):
                    else_struct, else_records = cls._check_if_structures(
                        condition, second, origin
                    )

                # Pick the largest result structure
                if then_struct is not None and else_struct is not None:
                    is_sub, largest = Binary.check_is_subset(
                        then_struct, else_struct
                    )
                    if not is_sub:
                        raise SemanticError(
                            "2-3",
                            op=cls.op,
                            structure_1=then_struct.get_key_components_names(),
                            structure_2=else_struct.get_key_components_names(),
                            origin=origin,
                        )
                    if largest is then_struct:
                        return then_struct, then_records
                    return else_struct, else_records
                elif then_struct is not None:
                    return then_struct, then_records
                elif else_struct is not None:
                    return else_struct, else_records
                else:
                    return condition.structure, condition.records
            else:
                if isinstance(first, RecordSet):
                    return cls._check_if_structures(condition, first, origin)
                return condition.structure, condition.records

    @classmethod
    def _check_if_structures(
        cls, condition: RecordSet, operand: RecordSet, origin: str
    ) -> tuple[Structure, pd.DataFrame | None]:
        """Bidirectional structure check for IF operator.
        Returns (result_structure, result_records) where result is the superset.
        """
        # Same structure: return condition's
        if cls._check_same_recordset_structures(condition, operand, origin):
            if condition.records is not None and operand.records is not None:
                result_df = pd.merge(
                    condition.records,
                    operand.records,
                    on=[
                        c
                        for c in condition.records.columns
                        if c != "data_type"
                    ],
                )
                if len(result_df) != len(condition.records):
                    raise SemanticError("4-6-0-1")
            return condition.structure, condition.records

        # Bidirectional subset check
        is_subset, superset = Binary.check_is_subset(
            condition.structure, operand.structure
        )
        if is_subset and superset is not None:
            if superset is condition.structure:
                return condition.structure, condition.records
            else:
                return operand.structure, operand.records

        raise SemanticError(
            "4-6-0-2", condition=condition.name, operand=operand.name
        )

    @classmethod
    def check_types(
        cls,
        first: CondOperand,
        result_dataframe: pd.DataFrame | None,
        second: CondOperand | None = None,
    ) -> tuple[ScalarType, pd.DataFrame | None]:
        first_type: ScalarType
        if second is not None:
            if isinstance(first, RecordSet):
                first_type = first.structure.components["f"].type
            else:
                first_type = first.type
            second_type: ScalarType
            if isinstance(second, RecordSet):
                second_type = second.structure.components["f"].type
            else:
                second_type = second.type
            if isinstance(first_type, Mixed) or isinstance(second_type, Mixed):
                if isinstance(first, RecordSet) and isinstance(
                    second, RecordSet
                ):
                    result_dataframe = cls.generate_result_dataframe(
                        first, second
                    )
        else:
            if isinstance(first, RecordSet):
                first_type = first.structure.components["f"].type
            else:
                first_type = first.type
            return first_type, result_dataframe

        if isinstance(first_type, Mixed) or isinstance(second_type, Mixed):
            if result_dataframe is None:
                raise Exception(
                    "Mixed type promotion requires a result dataframe"
                )
            type_promotion, result_dataframe = (
                binary_implicit_type_promotion_with_mixed_types(
                    result_dataframe, first_type, second_type
                )
            )
        else:
            type_promotion = binary_implicit_type_promotion(
                first_type, second_type
            )

        return type_promotion, result_dataframe

    @classmethod
    def validate(  # type: ignore[override]
        cls,
        condition: CondOperand,
        then_op: CondOperand,
        else_op: CondOperand | None = None,
    ) -> CondOperand:
        """ """
        origin = cls.create_origin_expression(condition, then_op, else_op)
        # check condition
        cls.check_condition(condition)
        # check structures
        rslt_structure, rslt_dataframe = cls.check_structures(
            condition, then_op, else_op, origin
        )
        # check_types (with implicit cast)
        rslt_type, rslt_dataframe = cls.check_types(
            then_op, rslt_dataframe, else_op
        )
        # Create the result structure with label
        if isinstance(rslt_structure, Structure):
            recordset = cls._create_labeled_recordset(
                origin=origin,
                rslt_type=rslt_type,
                rslt_structure=rslt_structure,
                result_dataframe=rslt_dataframe,
            )
            return recordset
        labeled_scalar = cls.create_labeled_scalar(
            rslt_structure, rslt_type, origin
        )
        return labeled_scalar


class Nvl(ConditionalOperator):
    """ """

    op: ClassVar[str | None] = tokens.NVL

    @classmethod
    def create_origin_expression(cls, left: Operand, right: Operand) -> str:
        left_name = getattr(left, "name", None) or left.origin
        right_name = getattr(right, "name", None) or right.origin

        origin = f"{cls.op}({left_name},{right_name})"
        return origin

    @classmethod
    def check_structures(
        cls,
        left: CondOperand,
        right: CondOperand,
        origin: str,
    ) -> tuple[Structure | CondOperand | None, pd.DataFrame | None]:
        if isinstance(left, RecordSet) and isinstance(right, RecordSet):
            if cls._check_structures(left, right, origin):
                result_dataframe = cls.generate_result_dataframe(left, right)
                return left.structure, result_dataframe
        elif isinstance(left, RecordSet) and isinstance(right, Scalar):
            return left.structure, left.records
        elif isinstance(left, Scalar) and isinstance(right, RecordSet):
            raise SemanticError("4-6-2-1")
        elif isinstance(left, Scalar) and isinstance(right, Scalar):
            return left, None
        return None, None

    @classmethod
    def check_types(
        cls,
        first: CondOperand,
        result_dataframe: pd.DataFrame | None,
        second: CondOperand | None = None,
    ) -> tuple[ScalarType, pd.DataFrame | None]:
        """ """
        first_type: ScalarType
        if isinstance(first, RecordSet):
            first_type = first.structure.components["f"].type
        else:
            first_type = first.type

        second_type: ScalarType
        if isinstance(second, RecordSet):
            second_type = second.structure.components["f"].type
        elif isinstance(second, Scalar):
            second_type = second.type
        else:
            raise Exception("Nvl requires a second operand")

        if isinstance(first_type, Mixed) or isinstance(second_type, Mixed):
            if result_dataframe is None:
                raise Exception(
                    "Mixed type promotion requires a result dataframe"
                )
            type_promotion, result_dataframe = (
                binary_implicit_type_promotion_with_mixed_types(
                    result_dataframe, first_type, second_type
                )
            )
        else:
            type_promotion = binary_implicit_type_promotion(
                first_type, second_type
            )
            if result_dataframe is not None:
                if "data_type_left" in result_dataframe.columns:
                    result_dataframe = result_dataframe.drop(
                        columns=["data_type_left", "data_type_right"]
                    )
                result_dataframe = result_dataframe.assign(
                    data_type=type_promotion
                )

        return type_promotion, result_dataframe

    @classmethod
    def validate(  # type: ignore[override]
        cls, left: CondOperand, right: CondOperand
    ) -> CondOperand:
        """ """
        origin: str = cls.create_origin_expression(left, right)
        # check structures
        rslt_structure, rslt_dataframe = cls.check_structures(
            left, right, origin
        )
        # check_types
        rslt_type, rslt_dataframe = cls.check_types(
            first=left, result_dataframe=rslt_dataframe, second=right
        )
        # Create the result structure with label
        if isinstance(rslt_structure, Structure):
            recordset = cls._create_labeled_recordset(
                origin=origin,
                rslt_type=rslt_type,
                rslt_structure=rslt_structure,
                result_dataframe=rslt_dataframe,
            )
            return recordset
        if rslt_structure is None:
            raise Exception(
                "Nvl produced no result structure; unhandled operand combination"
            )
        labeled_scalar = cls.create_labeled_scalar(
            rslt_structure=rslt_structure, rslt_type=rslt_type, origin=origin
        )
        return labeled_scalar


class Filter(ConditionalOperator):
    op: ClassVar[str | None] = tokens.FILTER
    propagate_attributes: ClassVar[bool] = False

    @classmethod
    def create_origin_expression(
        cls, selection: Operand, condition: Operand
    ) -> str:
        selection_name = getattr(selection, "name", None) or getattr(
            selection, "origin", None
        )
        condition_name = getattr(condition, "name", None) or getattr(
            condition, "origin", None
        )

        origin = f"{cls.op} ( {selection_name}, {condition_name} )"
        return origin

    @classmethod
    def _check_filter_structures(
        cls, selection: RecordSet, condition: RecordSet
    ) -> Structure:
        origin: str = cls.create_origin_expression(selection, condition)
        if cls._check_same_recordset_structures(selection, condition, origin):
            return selection.structure

        else:
            condition_is_subset = cls.check_condition_is_subset(
                selection=selection, condition=condition
            )
            if condition_is_subset:
                return selection.structure
            raise errors.SemanticError(
                "4-6-0-2", operand=selection.name, condition=condition.name
            )

    @classmethod
    def validate(  # type: ignore[override]
        cls, selection: Operand, condition: Operand
    ) -> RecordSet:

        if isinstance(selection, RecordSet) and isinstance(
            condition, RecordSet
        ):
            if selection.has_only_global_components:
                add_semantic_warning(
                    f"Performing a filter operation on recordset: {selection.name} which has only global key components"
                )

            check_condition_type = ScalarFactory().scalar_factory("Boolean")
            condition_fact_component = condition.get_fact_component()
            error_info = {"operand_name": condition.name, "op": cls.op}
            unary_implicit_type_promotion(
                condition_fact_component.type,
                check_condition_type,
                error_info=error_info,
            )
            result_structure = cls._check_filter_structures(
                selection, condition
            )

            result_dataframe: pd.DataFrame | None = None
            if selection.records is not None and condition.records is not None:
                result_dataframe = cls.generate_result_dataframe(
                    selection, condition
                )

            return cls.create_labeled_recordset(
                selection=selection,
                condition=condition,
                result_structure=result_structure,
                result_dataframe=result_dataframe,
            )

        raise errors.SemanticError("4-6-3-1")

    @classmethod
    def create_labeled_recordset(
        cls,
        selection: RecordSet,
        condition: RecordSet,
        result_structure: Structure,
        result_dataframe: pd.DataFrame | None,
    ) -> RecordSet:
        origin: str = cls.create_origin_expression(selection, condition)
        recordset = cls._create_labeled_recordset(
            origin=origin,
            rslt_type=result_structure.components["f"].type,
            rslt_structure=result_structure,
            result_dataframe=result_dataframe,
        )
        return recordset
