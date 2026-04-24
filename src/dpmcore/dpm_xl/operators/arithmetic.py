import math
import operator
from typing import ClassVar

from dpmcore.dpm_xl.operators.base import (
    Binary as _BaseBinary,
)
from dpmcore.dpm_xl.operators.base import (
    Complex as _BaseComplex,
)
from dpmcore.dpm_xl.operators.base import (
    PyOp,
)
from dpmcore.dpm_xl.operators.base import (
    Unary as _BaseUnary,
)
from dpmcore.dpm_xl.types.scalar import Number, ScalarType
from dpmcore.dpm_xl.utils import tokens


class Unary(_BaseUnary):
    op: ClassVar[str | None] = None
    type_to_check: ClassVar[type[ScalarType] | None] = Number
    return_type: ClassVar[type[ScalarType] | None] = None
    interval_allowed: ClassVar[bool] = True


class UnPlus(Unary):
    op: ClassVar[str | None] = tokens.PLUS
    py_op: ClassVar[PyOp | None] = operator.pos


class UnMinus(Unary):
    op: ClassVar[str | None] = tokens.MINUS
    py_op: ClassVar[PyOp | None] = operator.neg


class AbsoluteValue(Unary):
    op: ClassVar[str | None] = tokens.ABS
    py_op: ClassVar[PyOp | None] = operator.abs


class Exponential(Unary):
    op: ClassVar[str | None] = tokens.EXP
    py_op: ClassVar[PyOp | None] = math.exp
    return_type: ClassVar[type[ScalarType] | None] = Number
    interval_allowed: ClassVar[bool] = False


class NaturalLogarithm(Unary):
    op: ClassVar[str | None] = tokens.LN
    py_op: ClassVar[PyOp | None] = math.log
    return_type: ClassVar[type[ScalarType] | None] = Number
    interval_allowed: ClassVar[bool] = False


class SquareRoot(Unary):
    op: ClassVar[str | None] = tokens.SQRT
    py_op: ClassVar[PyOp | None] = math.sqrt
    return_type: ClassVar[type[ScalarType] | None] = Number
    interval_allowed: ClassVar[bool] = False


class NumericBinary(_BaseBinary):
    type_to_check: ClassVar[type[ScalarType] | None] = Number
    interval_allowed: ClassVar[bool] = True


class BinPlus(NumericBinary):
    op: ClassVar[str | None] = tokens.PLUS
    py_op: ClassVar[PyOp | None] = operator.add


class BinMinus(NumericBinary):
    op: ClassVar[str | None] = tokens.MINUS
    py_op: ClassVar[PyOp | None] = operator.sub


class Mult(NumericBinary):
    op: ClassVar[str | None] = tokens.MULT
    py_op: ClassVar[PyOp | None] = operator.mul


class Div(NumericBinary):
    op: ClassVar[str | None] = tokens.DIV
    py_op: ClassVar[PyOp | None] = operator.truediv
    return_type: ClassVar[type[ScalarType] | None] = Number


class Power(NumericBinary):
    op: ClassVar[str | None] = tokens.POW
    py_op: ClassVar[PyOp | None] = operator.pow
    interval_allowed: ClassVar[bool] = False


class Logarithm(NumericBinary):
    op: ClassVar[str | None] = tokens.LOG
    py_op: ClassVar[PyOp | None] = math.log
    return_type: ClassVar[type[ScalarType] | None] = Number
    interval_allowed: ClassVar[bool] = False


class NumericComplex(_BaseComplex):
    type_to_check: ClassVar[type[ScalarType] | None] = Number
    interval_allowed: ClassVar[bool] = True


class Max(NumericComplex):
    op: ClassVar[str | None] = tokens.MAX


class Min(NumericComplex):
    op: ClassVar[str | None] = tokens.MIN
