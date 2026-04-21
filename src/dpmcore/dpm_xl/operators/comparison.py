import operator
import re

from dpmcore.dpm_xl.operators.base import Binary, Unary
from dpmcore.dpm_xl.types.scalar import Boolean, String
from dpmcore.dpm_xl.utils import tokens


class IsNull(Unary):
    op = tokens.ISNULL
    py_op = operator.truth
    do_not_check_with_return_type = True
    return_type = Boolean


class Binary(Binary):
    do_not_check_with_return_type = True
    return_type = Boolean


class Equal(Binary):
    op = tokens.EQ
    py_op = operator.eq


class NotEqual(Binary):
    op = tokens.NEQ
    py_op = operator.ne


class Greater(Binary):
    op = tokens.GT
    py_op = operator.gt


class GreaterEqual(Binary):
    op = tokens.GTE
    py_op = operator.ge


class Less(Binary):
    op = tokens.LT
    py_op = operator.lt


class LessEqual(Binary):
    op = tokens.LTE
    py_op = operator.le


class In(Binary):
    op = tokens.IN

    @classmethod
    def py_op(cls, x, y):
        return operator.contains(y, x)

    py_op = py_op


class Match(Binary):
    op = tokens.MATCH
    type_to_check = String

    @classmethod
    def py_op(cls, x, y):
        return bool(re.fullmatch(y, x))

    py_op = py_op
