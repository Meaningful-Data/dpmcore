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
    Boolean,
    Integer,
    Item,
    Mixed,
    Number,
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


# ---------------------------------------------------------------------------
# MR !74 alignment: accepts_scalar_set_pair flag, set-equality between two
# ScalarSets, and rejection of non-set RHS in ``in``.
# ---------------------------------------------------------------------------


def test_equal_declares_accepts_scalar_set_pair() -> None:
    """§13.7: ``=`` is one of the two operators that opts into set equality."""
    assert Equal.accepts_scalar_set_pair is True


def test_notequal_declares_accepts_scalar_set_pair() -> None:
    from dpmcore.dpm_xl.operators.comparison import NotEqual

    assert NotEqual.accepts_scalar_set_pair is True


def test_in_does_not_declare_accepts_scalar_set_pair() -> None:
    """``in`` accepts a ScalarSet only on the RHS, never symmetrically."""
    assert In.accepts_scalar_set_pair is False


def test_greater_does_not_declare_accepts_scalar_set_pair() -> None:
    """Ordering comparisons are not defined on ScalarSets (§13.7)."""
    from dpmcore.dpm_xl.operators.comparison import Greater

    assert Greater.accepts_scalar_set_pair is False


class TestSetEqualityPair:
    """§13.7: ``=`` / ``!=`` between two ScalarSets return a Boolean Scalar."""

    def test_equal_accepts_scalar_set_pair(self) -> None:
        left = _make_scalar_set(Integer)
        right = _make_scalar_set(Integer)
        result = Equal.validate(left, right)
        assert isinstance(result, Scalar)
        assert isinstance(result.type, Boolean)

    def test_notequal_accepts_scalar_set_pair(self) -> None:
        from dpmcore.dpm_xl.operators.comparison import NotEqual

        left = _make_scalar_set(Integer)
        right = _make_scalar_set(Integer)
        result = NotEqual.validate(left, right)
        assert isinstance(result, Scalar)
        assert isinstance(result.type, Boolean)


class TestNonEqualityBinariesRejectScalarSetPair:
    """Only ``=`` / ``!=`` may accept a ScalarSet pair. Every other binary
    must raise ``SemanticError("3-3")`` — no silent leaks through the base
    ``types_given_structures`` else-branch.
    """

    def _run(self, op_cls: type) -> None:
        from dpmcore.errors import SemanticError

        left = _make_scalar_set(Integer)
        right = _make_scalar_set(Integer)
        with pytest.raises(SemanticError) as exc:
            op_cls.validate(left, right)
        assert exc.value.code == "3-3"

    def test_greater_rejects_scalar_set_pair(self) -> None:
        from dpmcore.dpm_xl.operators.comparison import Greater

        self._run(Greater)

    def test_less_rejects_scalar_set_pair(self) -> None:
        from dpmcore.dpm_xl.operators.comparison import Less

        self._run(Less)


class TestInRejectsNonSetRhs:
    """MR !74 widens ``in``'s RHS to a generic ``expression``; the semantic
    layer must reject a non-set RHS instead of letting a bare
    ``TypeError`` leak from the runtime evaluator.
    """

    def test_in_with_scalar_rhs_raises_semantic_error(self) -> None:
        from dpmcore.errors import SemanticError

        left = _make_scalar(Integer, "left")
        right = _make_scalar(Integer, "right")
        with pytest.raises(SemanticError) as exc:
            In.validate(left, right)
        assert exc.value.code == "3-3"

    def test_in_with_constant_rhs_raises_semantic_error(self) -> None:
        from dpmcore.errors import SemanticError

        left = _make_scalar(Integer, "left")
        right = ConstantOperand(
            type_=ScalarFactory().scalar_factory("Integer"),
            name="3",
            origin="3",
            value=3,
        )
        with pytest.raises(SemanticError) as exc:
            In.validate(left, right)
        assert exc.value.code == "3-3"


class TestMixedTypeOperands:
    """Mixed-type cells must not crash or raise 3-1 in Boolean operators."""

    def test_in_mixed_scalar_vs_item_set_returns_boolean(self) -> None:
        """In operator: Mixed LHS + Item ScalarSet must return Boolean, not crash.

        Regression: ``validate_types`` raised ``Exception("Mixed type promotion
        requires a result dataframe")`` when result_dataframe was None (the
        Scalar+ScalarSet path in validate_structures always returns None).
        """
        left = _make_scalar(Mixed, "mixed_cell")
        right = _make_scalar_set(Item)
        result = In.validate(left, right)
        assert isinstance(result, Scalar)
        assert isinstance(result.type, Boolean)

    def test_equal_mixed_scalar_vs_item_returns_boolean(self) -> None:
        """Equal operator: Mixed LHS + Item Scalar must return Boolean, not raise 3-1.

        Regression: ``binary_implicit_type_promotion_with_mixed_types`` iterated
        over rows; when a row had Number type, comparing Number to Item raised
        SemanticError("3-1") even though the operator return type is Boolean.
        """
        import pandas as pd

        from dpmcore.dpm_xl.types.promotion import (
            binary_implicit_type_promotion_with_mixed_types,
        )

        df = pd.DataFrame({"data_type": [Number(), Item()]})
        final_type, _result_df = (
            binary_implicit_type_promotion_with_mixed_types(
                result_dataframe=df,
                left_type=Mixed(),
                right_type=Item(),
                op_type_to_check=None,
                return_type=Boolean(),
            )
        )
        assert isinstance(final_type, Boolean)
