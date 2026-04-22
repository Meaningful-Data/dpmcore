import operator
import re
from typing import ClassVar

from dpmcore.dpm_xl.operators.base import (
    Binary as _BaseBinary,
)
from dpmcore.dpm_xl.operators.base import (
    PyOp,
)
from dpmcore.dpm_xl.operators.base import (
    Unary as _BaseUnary,
)
from dpmcore.dpm_xl.types.scalar import Boolean, ScalarType, String
from dpmcore.dpm_xl.utils import tokens


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


class NotEqual(Binary):
    op: ClassVar[str | None] = tokens.NEQ
    py_op: ClassVar[PyOp | None] = operator.ne


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


class Match(Binary):
    op: ClassVar[str | None] = tokens.MATCH
    type_to_check: ClassVar[type[ScalarType] | None] = String
    py_op: ClassVar[PyOp | None] = _py_op_match
