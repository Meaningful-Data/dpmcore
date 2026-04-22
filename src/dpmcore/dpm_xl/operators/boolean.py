import operator
from typing import ClassVar

from dpmcore.dpm_xl.operators.base import (
    Binary as _BaseBinary,
)
from dpmcore.dpm_xl.operators.base import (
    PyOp,
)
from dpmcore.dpm_xl.operators.base import (
    Unary,
)
from dpmcore.dpm_xl.types.scalar import Boolean, ScalarType
from dpmcore.dpm_xl.utils import tokens


class Binary(_BaseBinary):
    type_to_check: ClassVar[type[ScalarType] | None] = Boolean


class And(Binary):
    op: ClassVar[str | None] = tokens.AND
    py_op: ClassVar[PyOp | None] = operator.and_


class Or(Binary):
    op: ClassVar[str | None] = tokens.OR
    py_op: ClassVar[PyOp | None] = operator.or_


class Xor(Binary):
    op: ClassVar[str | None] = tokens.XOR
    py_op: ClassVar[PyOp | None] = operator.xor


class Not(Unary):
    type_to_check: ClassVar[type[ScalarType] | None] = Boolean
    op: ClassVar[str | None] = tokens.NOT
    py_op: ClassVar[PyOp | None] = operator.not_
