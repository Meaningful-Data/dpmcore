from typing import ClassVar, Union

from dpmcore import errors
from dpmcore.dpm_xl.operators.base import Operator, Unary
from dpmcore.dpm_xl.symbols import ConstantOperand, RecordSet, Scalar
from dpmcore.dpm_xl.types.promotion import unary_implicit_type_promotion
from dpmcore.dpm_xl.types.scalar import (
    Date,
    Integer,
    ScalarFactory,
    ScalarType,
    TimeInterval,
)
from dpmcore.dpm_xl.utils import tokens


class TimeShift(Operator):
    op: ClassVar[str | None] = tokens.TIME_SHIFT
    type_to_check: ClassVar[type[ScalarType] | None] = TimeInterval
    propagate_attributes: ClassVar[bool] = True

    @classmethod
    def validate(
        cls,
        operand: Union[RecordSet, Scalar, ConstantOperand],
        component_name: str,
        period: str,
        shift_number: int,
    ) -> RecordSet | Scalar | ConstantOperand:

        if cls.type_to_check is None:
            raise Exception("TimeShift requires type_to_check to be set")
        type_to_check = ScalarFactory().scalar_factory(
            cls.type_to_check.__name__
        )
        error_info = {"operand_name": operand.name, "op": cls.op}

        if isinstance(operand, RecordSet):
            if not component_name:
                raise errors.SemanticError("4-7-3")

            if component_name != tokens.FACT:
                components = {
                    **operand.get_dpm_components(),
                    **operand.get_attributes(),
                }
                if not components or component_name not in components:
                    raise errors.SemanticError(
                        "2-8",
                        op=cls.op,
                        dpm_keys=component_name,
                        recordset=operand.name,
                    )

            component = operand.structure.components[component_name]

            unary_implicit_type_promotion(
                operand=component.type,
                op_type_to_check=type_to_check,
                error_info=error_info,
            )

            origin = f"{cls.op} ( {operand.name}, {period}, {shift_number}, {component_name} )"
            return cls._create_labeled_recordset(
                origin,
                operand.get_fact_component().type,
                operand.structure,
                operand.records,
            )

        if component_name:
            raise errors.SemanticError("4-7-2")

        final_type = unary_implicit_type_promotion(
            operand=operand.type,
            op_type_to_check=type_to_check,
            error_info=error_info,
        )
        if isinstance(operand, ConstantOperand):
            return operand

        origin = f"{cls.op}({operand.name}, {period}, {shift_number})"
        return cls._create_labeled_scalar(origin, result_type=final_type)


class DateExtractionBase(Unary):
    type_to_check: ClassVar[type[ScalarType] | None] = TimeInterval
    return_type: ClassVar[type[ScalarType] | None] = Integer
    do_not_check_with_return_type: ClassVar[bool] = True

    @classmethod
    def validate_types(
        cls, operand: Union[RecordSet, Scalar, ConstantOperand]
    ) -> "Scalar | RecordSet":
        if isinstance(operand, ConstantOperand):
            op_type = ScalarFactory().scalar_factory(TimeInterval.__name__)
            ret_type = ScalarFactory().scalar_factory(Integer.__name__)
            error_info: dict[str, object] = {
                "operand_name": operand.name,
                "op": cls.op,
            }
            unary_implicit_type_promotion(
                operand.type,
                op_type,
                return_type=ret_type,
                error_info=error_info,
            )
            origin = f"{cls.op}({operand.origin})"
            return cls._create_labeled_scalar(origin, result_type=Integer())
        return super().validate_types(operand)


class Year(DateExtractionBase):
    op: ClassVar[str | None] = tokens.YEAR_OP


class Semester(DateExtractionBase):
    op: ClassVar[str | None] = tokens.SEMESTER_OP


class Quarter(DateExtractionBase):
    op: ClassVar[str | None] = tokens.QUARTER_OP


class Month(DateExtractionBase):
    op: ClassVar[str | None] = tokens.MONTH_OP


class Week(DateExtractionBase):
    op: ClassVar[str | None] = tokens.WEEK_OP


class Day(DateExtractionBase):
    op: ClassVar[str | None] = tokens.DAY_OP


class DateConstructor(Operator):
    op: ClassVar[str | None] = tokens.DATE_OP

    @classmethod
    def validate(
        cls,
        year_sym: Union[Scalar, ConstantOperand],
        month_sym: Union[Scalar, ConstantOperand],
        day_sym: Union[Scalar, ConstantOperand],
    ) -> "Scalar":
        op_type = ScalarFactory().scalar_factory(Integer.__name__)
        for sym in (year_sym, month_sym, day_sym):
            if isinstance(sym, RecordSet):
                raise errors.SemanticError("4-7-1", op=cls.op)
            error_info: dict[str, object] = {
                "operand_name": sym.name,
                "op": cls.op,
            }
            unary_implicit_type_promotion(
                sym.type, op_type, error_info=error_info
            )
        origin = (
            f"date({year_sym.origin}, {month_sym.origin}, {day_sym.origin})"
        )
        return cls._create_labeled_scalar(origin, result_type=Date())
