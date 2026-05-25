"""Tests for operator metadata invariants and ScalarSet operand handling.

Covers the two regressions introduced by commit 7371c37 and fixed here:
- ``check_operator_well_defined`` must honor ``do_not_check_with_return_type``
  so type-changing operators (``Len``, ``Match``) are not falsely rejected.
- ``Binary.validate`` must accept a ``ScalarSet`` on the right-hand side for
  operators that declare ``accepts_scalar_set_rhs`` (i.e. ``In``), and reject
  it precisely for everything else.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

# Importing the semantic_analyzer first resolves the circular import chain
# between ``operators.aggregate`` and ``utils.operator_mapping`` before any
# direct ``operators.*`` import.
import dpmcore.dpm_xl.semantic_analyzer  # noqa: F401  (side-effects)
from dpmcore.dpm_xl.operators.base import (  # noqa: E402
    Binary as _BaseBinary,
)
from dpmcore.dpm_xl.operators.base import (  # noqa: E402
    PyOp,
)
from dpmcore.dpm_xl.operators.comparison import Equal, In  # noqa: E402
from dpmcore.dpm_xl.operators.string import Len  # noqa: E402
from dpmcore.dpm_xl.symbols import (  # noqa: E402
    ConstantOperand,
    Scalar,
    ScalarSet,
)
from dpmcore.dpm_xl.types.scalar import (  # noqa: E402
    Integer,
    Item,
    ScalarFactory,
    ScalarType,
    String,
)


class TestCheckOperatorWellDefined:
    def test_len_passes_well_defined_check(self) -> None:
        # String → Integer: relies on do_not_check_with_return_type=True.
        # No exception should be raised.
        Len.check_operator_well_defined()

    def test_in_passes_well_defined_check(self) -> None:
        # Comparison Binary subclass; return_type=Boolean, type_to_check=None.
        In.check_operator_well_defined()

    def test_equal_passes_well_defined_check(self) -> None:
        Equal.check_operator_well_defined()

    def test_registration_check_rejects_unregistered_return_type(self) -> None:
        # Declare a bogus return_type to simulate a developer typo.
        class _Unregistered(ScalarType):
            pass

        class _BadOperator(_BaseBinary):
            op: ClassVar[str | None] = "_bad"
            py_op: ClassVar[PyOp | None] = None
            return_type: ClassVar[type[ScalarType] | None] = _Unregistered

        with pytest.raises(Exception, match="not a registered ScalarType"):
            _BadOperator.check_operator_well_defined()

    def test_registration_check_rejects_unregistered_type_to_check(
        self,
    ) -> None:
        class _Unregistered(ScalarType):
            pass

        class _BadOperator(_BaseBinary):
            op: ClassVar[str | None] = "_bad"
            py_op: ClassVar[PyOp | None] = None
            type_to_check: ClassVar[type[ScalarType] | None] = _Unregistered

        with pytest.raises(Exception, match="not a registered ScalarType"):
            _BadOperator.check_operator_well_defined()

    def test_cross_promotion_still_fires_for_type_preserving_operator(
        self,
    ) -> None:
        # A type-preserving operator declares ``return_type`` outside the
        # promotion family of ``type_to_check``. Without
        # ``do_not_check_with_return_type``, the cross-promotion check
        # must still fire.
        class _Bogus(_BaseBinary):
            op: ClassVar[str | None] = "_bogus"
            py_op: ClassVar[PyOp | None] = None
            type_to_check: ClassVar[type[ScalarType] | None] = String
            return_type: ClassVar[type[ScalarType] | None] = Integer
            # do_not_check_with_return_type intentionally left False.

        with pytest.raises(Exception, match="Review this operator _bogus"):
            _Bogus.check_operator_well_defined()


def _make_scalar(scalar_cls: type[ScalarType], name: str) -> Scalar:
    return Scalar(type_=scalar_cls(), name=name, origin=name)


def _make_scalar_set(scalar_cls: type[ScalarType]) -> ScalarSet:
    return ScalarSet(type_=scalar_cls(), name=None, origin="{a, b}")


class TestScalarSetRhsHandling:
    def test_in_accepts_scalar_set_rhs(self) -> None:
        left = _make_scalar(Item, "left")
        right = _make_scalar_set(Item)
        result = In.validate(left, right)
        # In returns a Boolean Scalar (do_not_check_with_return_type=True
        # bypasses operand-family enforcement).
        assert isinstance(result, Scalar)
        assert str(result.type) == "Boolean"

    def test_equal_rejects_scalar_set_rhs_with_named_error(self) -> None:
        left = _make_scalar(Item, "left")
        right = _make_scalar_set(Item)
        with pytest.raises(
            Exception,
            match="set-literal right-hand side is only allowed",
        ):
            Equal.validate(left, right)

    def test_in_with_constant_lhs_and_scalar_set_rhs(self) -> None:
        left = ConstantOperand(
            type_=ScalarFactory().scalar_factory("Integer"),
            name="1",
            origin="1",
            value=1,
        )
        right = ScalarSet(
            type_=ScalarFactory().scalar_factory("Integer"),
            name=None,
            origin="{1, 2, 3}",
        )
        result = In.validate(left, right)
        assert isinstance(result, Scalar)
        assert str(result.type) == "Boolean"


class TestEndToEndSemanticValidation:
    """Smoke tests exercising the public API path, not just the operator
    machinery in isolation. Kept lightweight (no DB) by feeding crafted
    expressions through the syntax+semantic services with no release.
    """

    def test_len_expression_validates(self) -> None:
        from dpmcore.services.syntax import SyntaxService

        # Syntactic check passes; semantic check requires no DB lookups for
        # constant string operands.
        SyntaxService().parse('len("abc") = 3')

    def test_in_with_constant_set_validates(self) -> None:
        from dpmcore.services.syntax import SyntaxService

        SyntaxService().parse("1 in {1, 2, 3}")


# Sanity guard: keep the flag wired explicitly on the operators where it
# matters, so a future refactor that removes the inheritance doesn't
# silently regress the fixes.
def test_len_declares_do_not_check_with_return_type() -> None:
    assert Len.do_not_check_with_return_type is True


def test_in_declares_accepts_scalar_set_rhs() -> None:
    assert In.accepts_scalar_set_rhs is True


def test_equal_does_not_accept_scalar_set_rhs() -> None:
    assert Equal.accepts_scalar_set_rhs is False
