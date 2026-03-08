import math
import operator

from dpmcore.dpm_xl.types.scalar import Number
from dpmcore.dpm_xl.operators.base import Operator, Binary, Unary, Complex
from dpmcore.dpm_xl.utils import tokens


class Unary(Unary):
    op = None
    type_to_check = Number
    return_type = None
    interval_allowed: bool = True


class UnPlus(Unary):
    op = tokens.PLUS
    py_op = operator.pos


class UnMinus(Unary):
    op = tokens.MINUS
    py_op = operator.neg


class AbsoluteValue(Unary):
    op = tokens.ABS
    py_op = operator.abs


class Exponential(Unary):
    op = tokens.EXP
    py_op = math.exp
    return_type = Number
    interval_allowed: bool = False


class NaturalLogarithm(Unary):
    op = tokens.LN
    py_op = math.log
    return_type = Number
    interval_allowed: bool = False


class SquareRoot(Unary):
    op = tokens.SQRT
    py_op = math.sqrt
    return_type = Number
    interval_allowed: bool = False


class NumericBinary(Binary):
    type_to_check = Number
    interval_allowed:bool = True


class BinPlus(NumericBinary):
    op = tokens.PLUS
    py_op = operator.add


class BinMinus(NumericBinary):
    op = tokens.MINUS
    py_op = operator.sub


class Mult(NumericBinary):
    op = tokens.MULT
    py_op = operator.mul


class Div(NumericBinary):
    op = tokens.DIV
    py_op = operator.truediv
    return_type = Number


class Power(NumericBinary):
    op = tokens.POW
    py_op = operator.pow
    interval_allowed:bool = False


class Logarithm(NumericBinary):
    op = tokens.LOG
    py_op = math.log
    return_type = Number
    interval_allowed:bool = False


class NumericComplex(Complex):
    type_to_check = Number
    interval_allowed:bool = True


class Max(NumericComplex):
    op = tokens.MAX


class Min(NumericComplex):
    op = tokens.MIN
