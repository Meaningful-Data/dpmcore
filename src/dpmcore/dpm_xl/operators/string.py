import operator
from typing import ClassVar, Union

from dpmcore.dpm_xl.operators.base import (
    Binary as _BaseBinary,
)
from dpmcore.dpm_xl.operators.base import (
    Operator,
    PyOp,
)
from dpmcore.dpm_xl.operators.base import (
    Unary as _BaseUnary,
)
from dpmcore.dpm_xl.symbols import ConstantOperand, RecordSet, Scalar
from dpmcore.dpm_xl.types.promotion import unary_implicit_type_promotion
from dpmcore.dpm_xl.types.scalar import (
    Integer,
    ScalarFactory,
    ScalarType,
    String,
)
from dpmcore.dpm_xl.utils import tokens


class Unary(_BaseUnary):
    op: ClassVar[str | None] = None
    type_to_check: ClassVar[type[ScalarType] | None] = String


class Binary(_BaseBinary):
    op: ClassVar[str | None] = None
    type_to_check: ClassVar[type[ScalarType] | None] = String


class Len(Unary):
    op: ClassVar[str | None] = tokens.LENGTH
    py_op: ClassVar[PyOp | None] = operator.length_hint
    return_type: ClassVar[type[ScalarType] | None] = Integer
    # String → Integer: return type is independent of the operand-type
    # family, so the cross-promotion well-definedness check does not apply.
    do_not_check_with_return_type: ClassVar[bool] = True


class Concatenate(Binary):
    op: ClassVar[str | None] = tokens.CONCATENATE
    py_op: ClassVar[PyOp | None] = operator.concat
    return_type: ClassVar[type[ScalarType] | None] = String


class Substr(Operator):
    """substr(op, {start}, {length}) -> String.

    ``start`` and ``length`` are optional integer literals.
    Accepts a Scalar or a Recordset operand (String -> String).
    """

    op: ClassVar[str | None] = tokens.SUBSTR
    type_to_check: ClassVar[type[ScalarType] | None] = String
    return_type: ClassVar[type[ScalarType] | None] = String

    @classmethod
    def validate(
        cls,
        operand: Union[Scalar, RecordSet, ConstantOperand],
        start: int | None = None,
        length: int | None = None,
    ) -> "Scalar | RecordSet":
        op_type = ScalarFactory().scalar_factory(String.__name__)
        error_info: dict[str, object] = {
            "operand_name": operand.name,
            "op": cls.op,
        }
        origin = f"{cls.op}({operand.origin}, {start}, {length})"

        if isinstance(operand, RecordSet):
            unary_implicit_type_promotion(
                operand.get_fact_component().type,
                op_type,
                error_info=error_info,
            )
            return cls._create_labeled_recordset(
                origin, String(), operand.structure, operand.records
            )

        unary_implicit_type_promotion(
            operand.type, op_type, error_info=error_info
        )
        if isinstance(operand, ConstantOperand):
            return operand
        return cls._create_labeled_scalar(origin, result_type=String())
