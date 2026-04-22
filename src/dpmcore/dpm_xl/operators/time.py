from typing import Union

from dpmcore import errors
from dpmcore.dpm_xl.operators.base import Operator
from dpmcore.dpm_xl.symbols import ConstantOperand, RecordSet, Scalar
from dpmcore.dpm_xl.types.promotion import unary_implicit_type_promotion
from dpmcore.dpm_xl.types.scalar import ScalarFactory, TimeInterval
from dpmcore.dpm_xl.utils import tokens


class TimeShift(Operator):
    op = tokens.TIME_SHIFT
    type_to_check = TimeInterval
    propagate_attributes = True

    @classmethod
    def validate(
        cls,
        operand: Union[RecordSet, Scalar, ConstantOperand],
        component_name: str,
        period: str,
        shift_number: int,
    ):

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
