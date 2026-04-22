from typing import Callable, ClassVar, Union, cast

import pandas as pd

from dpmcore.dpm_xl.symbols import (
    ConstantOperand,
    FactComponent,
    Operand,
    RecordSet,
    Scalar,
    ScalarSet,
    Structure,
)
from dpmcore.dpm_xl.types.promotion import (
    binary_implicit_type_promotion,
    binary_implicit_type_promotion_with_mixed_types,
    check_operator,
    unary_implicit_type_promotion,
    unary_implicit_type_promotion_with_mixed_types,
)
from dpmcore.dpm_xl.types.scalar import (
    Mixed,
    Number,
    ScalarFactory,
    ScalarType,
)
from dpmcore.dpm_xl.utils.operands_mapping import (
    generate_new_label,
    set_operand_label,
)
from dpmcore.dpm_xl.warning_collector import add_semantic_warning
from dpmcore.errors import SemanticError

# A py_op can be any callable; operators set it to a concrete function
# (e.g. ``operator.add``). Subclasses narrow the signature at the call
# site via ``isinstance`` checks.
PyOp = Callable[..., object]


class Operator:
    """Superclass for all operators. Defines the flags and methods to be used to create the scalars and recordsets.

    Attributes:
        op: Token used to represent the operator
        py_op: Python function to calculate the value (if necessary)
        type_to_check: Data type to be checked to comply with the operator specification
        do_not_check_with_return_type: On Comparison operators, we enforce only that operands involved have the same data type
        return_type: Data type to be checked. Operands must comply with this Data type by having it or by applying the Type Promotion.
    """

    op: ClassVar[str | None] = None
    py_op: ClassVar[PyOp | None] = None
    type_to_check: ClassVar[type[ScalarType] | None] = None
    do_not_check_with_return_type: ClassVar[bool] = False
    return_type: ClassVar[type[ScalarType] | None] = None
    propagate_attributes: ClassVar[bool] = False
    interval_allowed: ClassVar[bool] = False

    @staticmethod
    def _create_labeled_scalar(origin: str, result_type: ScalarType) -> Scalar:
        new_label = generate_new_label()

        interval = getattr(result_type, "interval", None)
        scalar = Scalar(
            type_=ScalarFactory().scalar_factory(str(result_type), interval),
            name=new_label,
            origin=origin,
        )
        set_operand_label(new_label, origin)
        return scalar

    @classmethod
    def _create_labeled_recordset(
        cls,
        origin: str,
        rslt_type: ScalarType,
        rslt_structure: Structure,
        result_dataframe: pd.DataFrame | None = None,
    ) -> RecordSet:
        new_recordset_label = generate_new_label()
        fact_component = FactComponent(
            type_=rslt_type, parent=new_recordset_label
        )
        rslt_structure.components["f"] = fact_component
        if not cls.propagate_attributes:
            rslt_structure.remove_attributes()
        rslt_structure.replace_components_parent(new_recordset_label)
        recordset = RecordSet(
            structure=rslt_structure, name=new_recordset_label, origin=origin
        )
        recordset.records = result_dataframe
        set_operand_label(label=new_recordset_label, operand=origin)
        return recordset

    @classmethod
    def check_operator_well_defined(cls) -> None:
        """ """
        return_type = (
            None
            if cls.return_type is None
            else ScalarFactory().scalar_factory(cls.return_type.__name__)
        )
        op_check_type = (
            None
            if cls.type_to_check is None
            else ScalarFactory().scalar_factory(cls.type_to_check.__name__)
        )
        well_defined = check_operator(
            return_type=return_type, op_check_type=op_check_type
        )
        if not well_defined:
            raise Exception("Review this operator {} ".format(cls.op))


# Type alias for operands handled by the binary operator pipeline.
BinaryOperand = Union[Scalar, RecordSet, ConstantOperand, ScalarSet]


class Binary(Operator):
    op: ClassVar[str | None] = None
    py_op: ClassVar[PyOp | None] = None
    type_to_check: ClassVar[type[ScalarType] | None] = None
    do_not_check_with_return_type: ClassVar[bool] = False
    return_type: ClassVar[type[ScalarType] | None] = None

    @classmethod
    def create_origin_expression(
        cls, first_operand: Operand, second_operand: Operand
    ) -> str:
        first_operand_origin = first_operand.origin
        second_operand_origin = second_operand.origin
        origin = f"{first_operand_origin} {cls.op} {second_operand_origin}"
        return origin

    @classmethod
    def create_labeled_scalar(
        cls,
        first_operand: Union[Scalar, ConstantOperand],
        second_operand: Union[Scalar, ConstantOperand],
        result_type: ScalarType | None = None,
    ) -> Scalar:
        """ """
        origin: str = cls.create_origin_expression(
            first_operand, second_operand
        )
        if isinstance(first_operand, ConstantOperand) and isinstance(
            second_operand, ConstantOperand
        ):
            if cls.py_op is None:
                raise Exception(f"Operator {cls.op} has no py_op defined")
            value = cls.py_op(first_operand.value, second_operand.value)
            return ConstantOperand(
                type_=ScalarFactory().scalar_factory(str(result_type)),
                # ``name`` here preserves the original runtime behavior of
                # assigning the computed value directly; downstream code
                # stringifies as needed. See latent-bug note in the module.
                name=cast(str, value),
                origin=origin,
                value=value,
            )

        if result_type is None:
            raise Exception(
                f"Operator {cls.op} requires a result_type for labeled scalar"
            )
        scalar = cls._create_labeled_scalar(
            origin=origin, result_type=result_type
        )
        return scalar

    @classmethod
    def create_labeled_recordset(
        cls,
        first_operand: Operand,
        second_operand: Operand,
        rslt_structure: Structure,
        rslt_type: ScalarType,
        result_dataframe: pd.DataFrame | None = None,
    ) -> RecordSet:
        origin: str = cls.create_origin_expression(
            first_operand, second_operand
        )
        recordset = cls._create_labeled_recordset(
            origin=origin,
            rslt_type=rslt_type,
            rslt_structure=rslt_structure,
            result_dataframe=result_dataframe,
        )
        return recordset

    @classmethod
    def create_labeled_precondition(
        cls, first_operand: ConstantOperand, second_operand: ConstantOperand
    ) -> object:
        # Latent bug: ``_create_labeled_precondition`` is not defined on any
        # subclass. This method is currently unreachable — kept for parity
        # with the original source; the attribute access is intentionally
        # ignored.
        if cls.py_op is None:
            raise Exception(f"Operator {cls.op} has no py_op defined")
        value = cls.py_op(first_operand.value, second_operand.value)
        origin: str = cls.create_origin_expression(
            first_operand, second_operand
        )
        precondition = cls._create_labeled_precondition(  # type: ignore[attr-defined]
            origin=origin, value=value
        )
        return precondition

    @classmethod
    def types_given_structures(
        cls, left: BinaryOperand, right: BinaryOperand
    ) -> tuple[ScalarType, ScalarType, ScalarType | None]:

        op_type_to_check = (
            None
            if cls.type_to_check is None
            else ScalarFactory().scalar_factory(cls.type_to_check.__name__)
        )

        if isinstance(left, Scalar) and isinstance(right, Scalar):
            return left.type, right.type, op_type_to_check

        elif isinstance(left, RecordSet) and isinstance(right, RecordSet):
            fact_left_component = left.get_fact_component()
            fact_right_component = right.get_fact_component()

            return (
                fact_left_component.type,
                fact_right_component.type,
                op_type_to_check,
            )

        elif isinstance(left, RecordSet) and isinstance(right, Scalar):
            fact_component = left.get_fact_component()
            return fact_component.type, right.type, op_type_to_check
        elif isinstance(left, Scalar) and isinstance(right, RecordSet):
            fact_component = right.get_fact_component()
            return left.type, fact_component.type, op_type_to_check

        elif isinstance(left, RecordSet) and isinstance(right, ScalarSet):
            fact_component = left.get_fact_component()
            return fact_component.type, right.type, op_type_to_check
        elif isinstance(left, Scalar) and isinstance(right, ScalarSet):
            return left.type, right.type, op_type_to_check
        else:
            raise NotImplementedError

    @classmethod
    def validate_types(
        cls,
        left: BinaryOperand,
        right: BinaryOperand,
        result_dataframe: pd.DataFrame | None,
    ) -> tuple[ScalarType, pd.DataFrame | None]:
        """Here the Structures has been validated."""
        cls.check_operator_well_defined()
        left_type, right_type, op_type_to_check = cls.types_given_structures(
            left, right
        )
        return_type = (
            None
            if cls.return_type is None
            else ScalarFactory().scalar_factory(cls.return_type.__name__)
        )
        error_info: dict[str, object] = {
            "left_name": left.name if left.name is not None else left.origin,
            "right_name": right.name
            if right.name is not None
            else right.origin,
            "op": cls.op,
        }
        interval_allowed = getattr(cls, "interval_allowed", False)
        if isinstance(left_type, Mixed) or isinstance(right_type, Mixed):
            if result_dataframe is None:
                raise Exception(
                    "Mixed type promotion requires a result dataframe"
                )
            final_type, result_dataframe = (
                binary_implicit_type_promotion_with_mixed_types(
                    result_dataframe=result_dataframe,
                    left_type=left_type,
                    right_type=right_type,
                    op_type_to_check=op_type_to_check,
                    return_type=return_type,
                    interval_allowed=interval_allowed,
                    error_info=error_info,
                )
            )
        else:
            final_type = binary_implicit_type_promotion(
                left_type,
                right_type,
                op_type_to_check,
                return_type,
                interval_allowed=interval_allowed,
                error_info=error_info,
            )
            if result_dataframe is not None:
                if "data_type_left" in result_dataframe.columns:
                    result_dataframe = result_dataframe.drop(
                        columns=["data_type_left", "data_type_right"]
                    )
                result_dataframe = result_dataframe.assign(
                    data_type=final_type
                )

        return final_type, result_dataframe

    @classmethod
    def validate_structures(
        cls, left: BinaryOperand, right: BinaryOperand
    ) -> tuple[Structure | None, pd.DataFrame | None]:
        """ """
        if isinstance(left, RecordSet) and isinstance(right, RecordSet):
            result_dataframe: pd.DataFrame | None = None
            # structure
            origin = cls.create_origin_expression(left, right)
            result_structure = cls._check_structures(
                left.structure, right.structure, origin
            )
            if left.records is not None and right.records is not None:
                if (
                    len(left.records) != len(right.records)
                    and len(left.records) != 0
                    and len(right.records) != 0
                ):
                    raise SemanticError("2-9", op=cls.op)
                if len(left.structure.get_standard_components()) == len(
                    right.structure.get_standard_components()
                ):
                    result_dataframe = pd.merge(
                        left=left.records,
                        right=right.records,
                        suffixes=("_left", "_right"),
                        on=[
                            col
                            for col in left.records.columns
                            if col != "data_type"
                        ],
                    )
                else:
                    if len(left.structure.get_standard_components()) == len(
                        result_structure.get_standard_components()
                    ):
                        result_dataframe = pd.merge(
                            left=left.records,
                            right=right.records,
                            suffixes=("_left", "_right"),
                            on=[
                                col
                                for col in right.records.columns
                                if col != "data_type"
                            ],
                        )
                    else:
                        result_dataframe = pd.merge(
                            left=right.records,
                            right=left.records,
                            suffixes=("_right", "_left"),
                            on=[
                                col
                                for col in left.records.columns
                                if col != "data_type"
                            ],
                        )
                if len(result_dataframe) == 0:
                    raise SemanticError(
                        "2-2", op=cls.op, left=left.name, right=right.name
                    )
                if len(result_dataframe) < len(left.records):
                    add_semantic_warning(
                        f"There is no correspondence between recordset {left.name} and recordset {right.name}."
                    )

            return result_structure, result_dataframe
        elif isinstance(left, RecordSet) and isinstance(right, Scalar):
            return left.structure, left.records
        elif isinstance(left, Scalar) and isinstance(right, RecordSet):
            return right.structure, right.records
        elif isinstance(left, RecordSet) and isinstance(right, ScalarSet):
            return left.structure, left.records
        else:
            return None, None

    @classmethod
    def check_same_components(
        cls, left: Structure, right: Structure, origin: str
    ) -> None:
        if set(left.get_key_components_names()) != set(
            right.get_key_components_names()
        ):
            raise SemanticError(
                "2-3",
                op=cls.op,
                structure_1=left.get_key_components_names(),
                structure_2=right.get_key_components_names(),
                origin=origin,
            )

        left_dpm_components = left.get_dpm_components()
        right_dpm_components = right.get_dpm_components()
        for comp_key, comp_value in left_dpm_components.items():
            if comp_key not in right_dpm_components:
                raise SemanticError(
                    "2-4", op=cls.op, name=comp_key, origin=origin
                )
            if (
                comp_value.type.__class__
                != right_dpm_components[comp_key].type.__class__
            ):
                # We do not do here the implicit cast, they have to have exactly the same types
                raise SemanticError(
                    "2-5",
                    op=cls.op,
                    name=comp_key,
                    type_1=comp_value.type,
                    type_2=right_dpm_components[comp_key].type,
                    origin=origin,
                )

    @classmethod
    def _check_structures(
        cls, left: Structure, right: Structure, origin: str
    ) -> Structure:
        """Used for recordset-recordset."""
        if len(left.get_key_components()) == len(right.get_key_components()):
            cls.check_same_components(left, right, origin)
            return left
        else:
            is_subset, final_structure = cls.check_is_subset(left, right)
            if is_subset and final_structure is not None:
                return final_structure
            raise SemanticError(
                "2-3",
                op=cls.op,
                structure_1=left.get_key_components_names(),
                structure_2=right.get_key_components_names(),
                origin=origin,
            )

    @staticmethod
    def check_is_subset(
        left: Structure, right: Structure
    ) -> tuple[bool, Structure | None]:
        """Take two Structures and return a True is one is other's subset and the greatest Structure
        False, None in other case.
        """
        left_dpm_components = left.get_dpm_components()
        right_dpm_components = right.get_dpm_components()
        if set(left.get_key_components_names()) <= set(
            right.get_key_components_names()
        ):  # <= is subset
            for comp_key, comp_value in left_dpm_components.items():
                if (
                    comp_value.type.__class__
                    != right_dpm_components[comp_key].type.__class__
                ):
                    return False, None
            return True, right
        elif set(right.get_key_components_names()) <= set(
            left.get_key_components_names()
        ):
            for comp_key, comp_value in right_dpm_components.items():
                if (
                    comp_value.type.__class__
                    != left_dpm_components[comp_key].type.__class__
                ):
                    return False, None
            return True, left
        else:
            return False, None

    @classmethod
    def validate(
        cls, left: BinaryOperand, right: BinaryOperand
    ) -> Scalar | RecordSet:
        """ """
        rslt_structure, result_dataframe = cls.validate_structures(left, right)
        rslt_type, result_dataframe = cls.validate_types(
            left, right, result_dataframe
        )
        if isinstance(rslt_structure, Structure):
            recordset = cls.create_labeled_recordset(
                left, right, rslt_structure, rslt_type, result_dataframe
            )
            return recordset
        # Scalar path: left/right are Scalars or ConstantOperands at this point.
        if not isinstance(left, (Scalar, ConstantOperand)) or not isinstance(
            right, (Scalar, ConstantOperand)
        ):
            raise Exception(
                "Invalid operand types for scalar binary operation"
            )
        labeled_scalar = cls.create_labeled_scalar(
            left, right, result_type=rslt_type
        )
        return labeled_scalar


# Operand type accepted by Unary operator methods.
UnaryOperand = Union[Scalar, RecordSet, ConstantOperand]


class Unary(Operator):
    op: ClassVar[str | None] = None
    py_op: ClassVar[PyOp | None] = None
    type_to_check: ClassVar[type[ScalarType] | None] = None
    check_specific_type: ClassVar[bool] = False
    return_type: ClassVar[type[ScalarType] | None] = None

    @classmethod
    def create_origin_expression(cls, operand: Operand, *args: object) -> str:
        operand_origin = operand.origin
        origin = f"{cls.op}({operand_origin})"
        return origin

    @classmethod
    def create_labeled_scalar(
        cls,
        first_operand: Union[Scalar, ConstantOperand],
        result_type: ScalarType,
    ) -> Scalar:
        """ """
        origin: str = cls.create_origin_expression(first_operand)
        if isinstance(first_operand, ConstantOperand):
            if cls.py_op is None:
                raise Exception(f"Operator {cls.op} has no py_op defined")
            value = cls.py_op(first_operand.value)
            return ConstantOperand(
                type_=ScalarFactory().scalar_factory(str(result_type)),
                # See note above: ``name`` mirrors the runtime value.
                name=cast(str, value),
                origin=origin,
                value=value,
            )

        scalar = cls._create_labeled_scalar(
            origin=origin, result_type=result_type
        )
        return scalar

    @classmethod
    def create_labeled_recordset(
        cls,
        first_operand: Operand,
        rslt_structure: Structure,
        rslt_type: ScalarType,
        result_dataframe: pd.DataFrame | None = None,
    ) -> RecordSet:
        """ """
        origin: str = cls.create_origin_expression(first_operand)
        recordset = cls._create_labeled_recordset(
            origin=origin,
            rslt_type=rslt_type,
            rslt_structure=rslt_structure,
            result_dataframe=result_dataframe,
        )
        return recordset

    @classmethod
    def create_labeled_precondition(cls, operand: ConstantOperand) -> object:
        # Latent bug: ``_create_labeled_precondition`` is not defined on any
        # subclass. This method is currently unreachable — kept for parity
        # with the original source; the attribute access is intentionally
        # ignored.
        if cls.py_op is None:
            raise Exception(f"Operator {cls.op} has no py_op defined")
        value = cls.py_op(operand.value)
        origin: str = cls.create_origin_expression(operand)

        precondition = cls._create_labeled_precondition(  # type: ignore[attr-defined]
            origin=origin, value=value
        )
        return precondition

    @classmethod
    def validate_types(cls, operand: UnaryOperand) -> Scalar | RecordSet:

        # First we check the operator
        cls.check_operator_well_defined()
        return_type = (
            None
            if cls.return_type is None
            else ScalarFactory().scalar_factory(cls.return_type.__name__)
        )
        op_type_to_check = (
            None
            if cls.type_to_check is None
            else ScalarFactory().scalar_factory(cls.type_to_check.__name__)
        )
        error_info: dict[str, object] = {
            "operand_name": operand.name,
            "op": cls.op,
        }

        if isinstance(operand, Scalar):
            final_type = unary_implicit_type_promotion(
                operand.type,
                op_type_to_check,
                return_type=return_type,
                error_info=error_info,
            )
            labeled_scalar = cls.create_labeled_scalar(
                operand, result_type=final_type
            )
            return labeled_scalar

        elif isinstance(operand, RecordSet):
            fact_component_type = operand.structure.components["f"].type

            if isinstance(fact_component_type, Mixed):
                if operand.records is None:
                    raise Exception(
                        "Mixed type promotion requires operand records"
                    )
                final_type, operand.records = (
                    unary_implicit_type_promotion_with_mixed_types(
                        operand.records,
                        op_type_to_check,
                        return_type,
                        error_info=error_info,
                    )
                )
            else:
                final_type = unary_implicit_type_promotion(
                    fact_component_type,
                    op_type_to_check,
                    return_type=return_type,
                    error_info=error_info,
                )
                if operand.records is not None:
                    operand.records["data_type"] = final_type

            recordset = cls.create_labeled_recordset(
                operand,
                rslt_structure=operand.structure,
                rslt_type=final_type,
                result_dataframe=operand.records,
            )

            return recordset

        else:
            raise Exception(
                "Unary operators only works for Recordset or Scalars"
            )


class Complex(Binary):
    @classmethod
    def validate(  # type: ignore[override]
        cls, operands: list[BinaryOperand]
    ) -> Scalar | RecordSet:

        origin = f"{cls.op}({','.join([str(x.value) if isinstance(x, ConstantOperand) else str(x.name) for x in operands])})"
        recordsets: list[RecordSet] = [
            operand for operand in operands if isinstance(operand, RecordSet)
        ]
        if len(recordsets) == 0:
            types: list[ScalarType] = []
            ref_operand = operands.pop(0)
            final_type: ScalarType
            for operand in operands:
                rslt_type = cls.validate_types(ref_operand, operand, None)
                if rslt_type[0] not in types:
                    types.append(rslt_type[0])
            if len(types) == 1:
                final_type = types[0]
            else:
                final_type = Number()  # TODO: review this
            return cls._create_labeled_scalar(
                origin=origin, result_type=final_type
            )

        ref_recordset = recordsets[0]
        operands.remove(ref_recordset)
        rslt_type_final: ScalarType | None = None
        for operand in operands:
            rslt_structure, rslt_dataframe = cls.validate_structures(
                ref_recordset, operand
            )
            rslt_type_final, rslt_dataframe = cls.validate_types(
                ref_recordset, operand, rslt_dataframe
            )
            if rslt_structure is not None:
                ref_recordset.structure = rslt_structure
            ref_recordset.records = rslt_dataframe

        if rslt_type_final is None:
            raise Exception(
                "Complex operator evaluated over empty operand list"
            )
        return cls._create_labeled_recordset(
            origin=origin,
            rslt_type=rslt_type_final,
            rslt_structure=ref_recordset.structure,
            result_dataframe=ref_recordset.records,
        )
