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
from dpmcore.dpm_xl.symbols import RecordSet, Scalar, ScalarSet
from dpmcore.dpm_xl.types.scalar import Boolean, Item, ScalarType, String
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


def _reject_scalarset_mixed_with_recordset(
    left: BinaryOperand, right: BinaryOperand, op: str
) -> None:
    """Reject ``=`` / ``!=`` between a ``ScalarSet`` and a ``RecordSet``.

    §13.7.5 / §5.2.1.5: set equality applies only when *both* operands are
    set-valued. A comparison that mixes a Scalar Set with a Recordset (or a
    Scalar) is explicitly rejected by semantic analysis.
    """
    if (isinstance(left, ScalarSet) and isinstance(right, RecordSet)) or (
        isinstance(left, RecordSet) and isinstance(right, ScalarSet)
    ):
        raise SemanticError(
            "3-3",
            type_1=(f"{type(left).__name__}, {type(right).__name__}"),
            type_op="matching set-valued or non-set operands",
            origin=op,
        )


def _is_empty_set_placeholder(op: BinaryOperand) -> bool:
    """True only for the empty set literal ``{}``.

    ``visit_Set`` builds the origin string by joining stringified
    children with ``", "``, so the singleton ``{""}`` (a set with one
    empty string element) *also* renders as ``"{}"`` — the origin string
    alone cannot distinguish it from the truly empty literal. The
    unambiguous marker is the pair ``(origin == "{}", type is Item)``:
    ``visit_Set`` assigns the ``Item`` placeholder only when the set has
    no children, and no genuinely-typed literal reaches that origin
    string.
    """
    return (
        isinstance(op, ScalarSet)
        and op.origin == "{}"
        and isinstance(op.type, Item)
    )


def _element_type_of(op: BinaryOperand) -> ScalarType | None:
    """Return the element type of ``op`` if it is genuinely typed.

    The empty set literal ``{}`` carries the placeholder ``Item`` type
    from :func:`visit_Set`; treat it as untyped so its type is inferred
    from the *other* operand rather than propagated onto it.
    """
    if isinstance(op, ScalarSet):
        return None if _is_empty_set_placeholder(op) else op.type
    if isinstance(op, Scalar):
        return op.type
    if isinstance(op, RecordSet):
        return op.get_fact_component().type
    return None


def _propagate_empty_set_type(
    left: BinaryOperand, right: BinaryOperand
) -> tuple[BinaryOperand, BinaryOperand]:
    """Unify the type of the empty set literal ``{}`` to the other operand.

    ``visit_Set`` gives the empty set literal a placeholder ``Item`` type
    because there are no elements from which to infer one. That
    placeholder is not a real element type; ``_visit_set_operands``
    already filters it out of the homogeneity check for
    ``union``/``intersect``/``setdiff``/``symdiff``. Apply the same
    convention to any binary op with a ``{}`` operand so patterns like
    ``setdiff(A, B) = {}`` (ScalarSet = ScalarSet) and ``5 in {}``
    (Scalar in ScalarSet) do not raise a spurious "Implicit promotion
    between <T> and Item" warning against the placeholder.
    """
    if _is_empty_set_placeholder(left):
        other = _element_type_of(right)
        if other is not None:
            left = ScalarSet(type_=other, name=left.name, origin=left.origin)
    if _is_empty_set_placeholder(right):
        other = _element_type_of(left)
        if other is not None:
            right = ScalarSet(
                type_=other, name=right.name, origin=right.origin
            )
    return left, right


class Equal(Binary):
    op: ClassVar[str | None] = tokens.EQ
    py_op: ClassVar[PyOp | None] = operator.eq
    # §13.7: ``=`` accepts a set-valued operand on both sides (set equality).
    accepts_scalar_set_pair: ClassVar[bool] = True

    @classmethod
    def validate(
        cls, left: BinaryOperand, right: BinaryOperand
    ) -> Scalar | RecordSet:
        _reject_scalarset_mixed_with_recordset(left, right, cls.op or "=")
        left, right = _propagate_empty_set_type(left, right)
        return super().validate(left, right)


class NotEqual(Binary):
    op: ClassVar[str | None] = tokens.NEQ
    py_op: ClassVar[PyOp | None] = operator.ne
    # §13.7: ``!=`` accepts a set-valued operand on both sides (set inequality).
    accepts_scalar_set_pair: ClassVar[bool] = True

    @classmethod
    def validate(
        cls, left: BinaryOperand, right: BinaryOperand
    ) -> Scalar | RecordSet:
        _reject_scalarset_mixed_with_recordset(left, right, cls.op or "!=")
        left, right = _propagate_empty_set_type(left, right)
        return super().validate(left, right)


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
    ) -> Scalar | RecordSet:
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
        left, right = _propagate_empty_set_type(left, right)
        return super().validate(left, right)


class Match(Binary):
    op: ClassVar[str | None] = tokens.MATCH
    type_to_check: ClassVar[type[ScalarType] | None] = String
    py_op: ClassVar[PyOp | None] = _py_op_match
    # String → Boolean. Relies on ``do_not_check_with_return_type`` inherited
    # from ``Binary`` above to opt out of the cross-promotion check.
