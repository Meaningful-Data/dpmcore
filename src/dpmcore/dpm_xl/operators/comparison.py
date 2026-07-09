import operator
import re
from typing import ClassVar

from dpmcore.dpm_xl.operators.base import (
    Binary as _BaseBinary,
)
from dpmcore.dpm_xl.operators.base import (
    BinaryOperand,
    PyOp,
)
from dpmcore.dpm_xl.operators.base import (
    Unary as _BaseUnary,
)
from dpmcore.dpm_xl.symbols import RecordSet, ScalarSet
from dpmcore.dpm_xl.types.scalar import Boolean, ScalarType, String
from dpmcore.dpm_xl.utils import tokens
from dpmcore.errors import SemanticError


class IsNull(_BaseUnary):
    op: ClassVar[str | None] = tokens.ISNULL
    py_op: ClassVar[PyOp | None] = operator.truth
    do_not_check_with_return_type: ClassVar[bool] = True
    return_type: ClassVar[type[ScalarType] | None] = Boolean


class Binary(_BaseBinary):
    do_not_check_with_return_type: ClassVar[bool] = True
    return_type: ClassVar[type[ScalarType] | None] = Boolean


class Equal(Binary):
    op: ClassVar[str | None] = tokens.EQ
    py_op: ClassVar[PyOp | None] = operator.eq
    # §13.7: ``=`` accepts a set-valued operand on both sides (set equality).
    accepts_scalar_set_pair: ClassVar[bool] = True


class NotEqual(Binary):
    op: ClassVar[str | None] = tokens.NEQ
    py_op: ClassVar[PyOp | None] = operator.ne
    # §13.7: ``!=`` accepts a set-valued operand on both sides (set inequality).
    accepts_scalar_set_pair: ClassVar[bool] = True


class Greater(Binary):
    op: ClassVar[str | None] = tokens.GT
    py_op: ClassVar[PyOp | None] = operator.gt


class GreaterEqual(Binary):
    op: ClassVar[str | None] = tokens.GTE
    py_op: ClassVar[PyOp | None] = operator.ge


class Less(Binary):
    op: ClassVar[str | None] = tokens.LT
    py_op: ClassVar[PyOp | None] = operator.lt


class LessEqual(Binary):
    op: ClassVar[str | None] = tokens.LTE
    py_op: ClassVar[PyOp | None] = operator.le


def _py_op_in(x: object, y: object) -> bool:
    return operator.contains(y, x)  # type: ignore[arg-type]


def _py_op_match(x: object, y: object) -> bool:
    # ``re.fullmatch`` takes (pattern, string); original semantics keep
    # the arg order (x is the string, y is the pattern).
    return bool(re.fullmatch(y, x))  # type: ignore[call-overload]


class In(Binary):
    op: ClassVar[str | None] = tokens.IN
    py_op: ClassVar[PyOp | None] = _py_op_in
    # The membership operator is the only Binary whose right-hand side is
    # legitimately a set literal (``ScalarSet``).
    accepts_scalar_set_rhs: ClassVar[bool] = True

    @classmethod
    def validate(
        cls, left: BinaryOperand, right: BinaryOperand
    ) -> "Scalar | RecordSet":  # type: ignore[name-defined]  # noqa: F821
        # The MR !74 grammar widens ``in``'s RHS from ``setExpression`` to a
        # generic ``expression``; the semantic layer must reject any RHS that
        # is not set-valued (e.g. ``5 in 3``), otherwise validation would fall
        # through to runtime with a bare ``TypeError``. RecordSet operands are
        # accepted (coerced downstream to the Fact Component's ScalarSet, per
        # §13.1.5).
        if not isinstance(right, (ScalarSet, RecordSet)):
            raise SemanticError(
                "3-3",
                type_1=type(right).__name__,
                type_op="ScalarSet",
                origin="in",
            )
        return super().validate(left, right)


class Match(Binary):
    op: ClassVar[str | None] = tokens.MATCH
    type_to_check: ClassVar[type[ScalarType] | None] = String
    py_op: ClassVar[PyOp | None] = _py_op_match
    # String → Boolean. Relies on ``do_not_check_with_return_type`` inherited
    # from ``Binary`` above to opt out of the cross-promotion check.
