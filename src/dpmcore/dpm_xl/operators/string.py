import operator
from typing import ClassVar, Union

from dpmcore.dpm_xl.operators.base import (
    Binary as _BaseBinary,
)
from dpmcore.dpm_xl.operators.base import (
    PyOp,
)
from dpmcore.dpm_xl.operators.base import (
    Unary as _BaseUnary,
)
from dpmcore.dpm_xl.symbols import ConstantOperand, RecordSet, Scalar
from dpmcore.dpm_xl.types.promotion import (
    unary_implicit_type_promotion,
    unary_implicit_type_promotion_with_mixed_types,
)
from dpmcore.dpm_xl.types.scalar import (
    Integer,
    Mixed,
    ScalarFactory,
    ScalarType,
    String,
)
from dpmcore.dpm_xl.utils import tokens
from dpmcore.errors import SemanticError


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


class Substr(Unary):
    """substr(op, {start}, {length}) -> String.

    ``start`` and ``length`` are optional integer literals.
    Accepts a Scalar or a Recordset operand (String -> String).

    A ``Unary`` subclass so it's grouped with the other unary string
    operators; ``validate`` stays fully custom (rather than delegating to
    ``Unary.validate_types``/``create_labeled_scalar``) because those
    assume a plain 1-argument ``py_op`` and don't know about ``start``/
    ``length``. The Mixed-typed-recordset branch below mirrors
    ``Unary.validate_types`` exactly, reusing the same promotion helper,
    so a recordset with a ``Mixed`` fact type doesn't crash with a
    ``KeyError`` (``Mixed`` has no entry in ``implicit_type_promotion_dict``).
    """

    op: ClassVar[str | None] = tokens.SUBSTR
    return_type: ClassVar[type[ScalarType] | None] = String

    @classmethod
    def validate(
        cls,
        operand: Union[Scalar, RecordSet, ConstantOperand],
        start: int | None = None,
        length: int | None = None,
    ) -> "Scalar | RecordSet":
        if start is not None and start < 1:
            raise SemanticError(
                "4-8-1",
                op=cls.op,
                parameter_name="start",
                constraint="a positive integer (>= 1)",
            )
        if length is not None and length < 0:
            raise SemanticError(
                "4-8-1",
                op=cls.op,
                parameter_name="length",
                constraint="a non-negative integer (>= 0)",
            )

        op_type = ScalarFactory().scalar_factory(String.__name__)
        error_info: dict[str, object] = {
            "operand_name": operand.name,
            "op": cls.op,
        }
        args = [
            str(v) for v in (operand.origin, start, length) if v is not None
        ]
        origin = f"{cls.op}({', '.join(args)})"

        if isinstance(operand, RecordSet):
            fact_type = operand.get_fact_component().type
            if isinstance(fact_type, Mixed):
                if operand.records is None:
                    raise Exception(
                        "Mixed type promotion requires operand records"
                    )
                _, operand.records = (
                    unary_implicit_type_promotion_with_mixed_types(
                        operand.records,
                        op_type,
                        op_type,
                        error_info=error_info,
                    )
                )
            else:
                unary_implicit_type_promotion(
                    fact_type, op_type, error_info=error_info
                )
            return cls._create_labeled_recordset(
                origin, String(), operand.structure, operand.records
            )

        unary_implicit_type_promotion(
            operand.type, op_type, error_info=error_info
        )
        if isinstance(operand, ConstantOperand):
            value = cls._substring(str(operand.value), start, length)
            return ConstantOperand(
                type_=String(), name=value, origin=origin, value=value
            )
        return cls._create_labeled_scalar(origin, result_type=String())

    @staticmethod
    def _substring(text: str, start: int | None, length: int | None) -> str:
        # ``start`` is already validated to be >= 1 (or None) by ``validate``.
        start_index = start - 1 if start is not None else 0
        if length is None:
            return text[start_index:]
        return text[start_index : start_index + length]
