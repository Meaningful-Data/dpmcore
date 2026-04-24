import operator
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
from dpmcore.dpm_xl.types.scalar import Integer, ScalarType, String
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


class Concatenate(Binary):
    op: ClassVar[str | None] = tokens.CONCATENATE
    py_op: ClassVar[PyOp | None] = operator.concat
    return_type: ClassVar[type[ScalarType] | None] = String
