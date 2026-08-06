"""Structural rules for the Fact Component in clause operators (#266).

``where`` accepts the Fact Component ("f") as a condition target; ``get``,
``rename`` and ``sub`` reject it, as do all four for Standard *Key
Components* ("r", "c", "s"). These tests drive the operators directly, so no
database is involved.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import BinOp, Constant, Dimension
from dpmcore.dpm_xl.ast.where_clause import collect_where_equality_pins
from dpmcore.dpm_xl.operators.arithmetic import BinPlus
from dpmcore.dpm_xl.operators.clause import Get, Rename, Sub, Where
from dpmcore.dpm_xl.symbols import (
    ConstantOperand,
    FactComponent,
    KeyComponent,
    RecordSet,
    Scalar,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import Boolean, Item, Number, String
from dpmcore.dpm_xl.utils.tokens import DPM, EQ, FACT, STANDARD
from dpmcore.errors import SemanticError


def _make_rs(fact_type=None) -> RecordSet:
    """Recordset with one standard key ("r"), one DPM key ("qA") and a fact."""
    structure = Structure(
        [
            KeyComponent("r", Number(), STANDARD, "test"),
            KeyComponent("qA", Item(), DPM, "test"),
            FactComponent(fact_type or Number(), "test"),
        ]
    )
    return RecordSet(structure, "ds", "ds")


def _boolean_condition() -> Scalar:
    return Scalar(type_=Boolean(), name="cond", origin="cond")


class TestWhereAcceptsTheFact:
    def test_fact_only_condition_is_accepted(self):
        result = Where.validate(
            operand=_make_rs(),
            key_names=[FACT],
            new_names=None,
            condition=_boolean_condition(),
        )
        assert isinstance(result, RecordSet)

    def test_structure_is_unchanged(self):
        """A filter changes records, never components."""
        operand = _make_rs()
        before = dict(operand.structure.components)
        result = Where.validate(
            operand=operand,
            key_names=[FACT],
            new_names=None,
            condition=_boolean_condition(),
        )
        assert set(result.structure.components) == set(before)
        assert isinstance(result.get_fact_component(), FactComponent)

    def test_fact_alongside_a_dpm_key_is_accepted(self):
        result = Where.validate(
            operand=_make_rs(),
            key_names=[FACT, "qA"],
            new_names=None,
            condition=_boolean_condition(),
        )
        assert isinstance(result, RecordSet)

    def test_unknown_component_still_raises_2_8(self):
        """Allowing the Fact must not weaken resolution of real components."""
        with pytest.raises(SemanticError) as exc:
            Where.validate(
                operand=_make_rs(),
                key_names=[FACT, "qMissing"],
                new_names=None,
                condition=_boolean_condition(),
            )
        assert exc.value.code == "2-8"

    def test_standard_key_still_raises_4_5_0_1(self):
        with pytest.raises(SemanticError) as exc:
            Where.validate(
                operand=_make_rs(),
                key_names=["r"],
                new_names=None,
                condition=_boolean_condition(),
            )
        assert exc.value.code == "4-5-0-1"


class TestOtherClausesRejectTheFact:
    def test_get_raises_4_5_0_1(self):
        with pytest.raises(SemanticError) as exc:
            Get.validate(operand=_make_rs(), key_names=[FACT])
        assert exc.value.code == "4-5-0-1"

    def test_rename_from_the_fact_raises_4_5_0_1(self):
        with pytest.raises(SemanticError) as exc:
            Rename.validate(
                operand=_make_rs(), key_names=[FACT], new_names=["qB"]
            )
        assert exc.value.code == "4-5-0-1"

    def test_rename_to_the_fact_still_raises_4_5_1_3(self):
        with pytest.raises(SemanticError) as exc:
            Rename.validate(
                operand=_make_rs(), key_names=["qA"], new_names=[FACT]
            )
        assert exc.value.code == "4-5-1-3"

    def test_sub_on_the_fact_raises_4_5_0_1(self):
        """A sub clause substitutes DPM *Key Components* only."""
        with pytest.raises(SemanticError) as exc:
            Sub.validate(
                operand=_make_rs(),
                property_code=FACT,
                value=ConstantOperand(
                    type_=Number(), name=None, origin="1", value=1
                ),
            )
        assert exc.value.code == "4-5-0-1"

    def test_sub_on_a_standard_key_raises_4_5_0_1(self):
        """Reachable via the backtick form (`` [sub `r` = ...] ``)."""
        with pytest.raises(SemanticError) as exc:
            Sub.validate(
                operand=_make_rs(),
                property_code="r",
                value=ConstantOperand(
                    type_=Number(), name=None, origin="1", value=1
                ),
            )
        assert exc.value.code == "4-5-0-1"


class TestGetRetypesTheFact:
    """The result Fact Component takes the Data Type of the selected one."""

    def test_fact_takes_the_selected_components_type(self):
        operand = _make_rs(fact_type=Number())
        result = Get.validate(operand=operand, key_names=["qA"])
        assert isinstance(result.get_fact_component().type, Item)

    def test_string_key_yields_a_string_fact(self):
        structure = Structure(
            [
                KeyComponent("r", Number(), STANDARD, "test"),
                KeyComponent("qA", String(), DPM, "test"),
                FactComponent(Number(), "test"),
            ]
        )
        result = Get.validate(
            operand=RecordSet(structure, "ds", "ds"), key_names=["qA"]
        )
        assert isinstance(result.get_fact_component().type, String)


class TestFactPinsDoNotKillTheJoin:
    """Two operands filtering on different fact values must still join."""

    def test_disjoint_fact_filters_do_not_raise_2_2(self):
        """``{tA}[where f = 1] + {tB}[where f = 2]`` is a live operation.

        The pins are derived the same way ``visit_WhereClauseOp`` derives
        them, so this exercises the real path rather than a hand-written
        constraint dict.
        """
        left, right = _make_rs(), _make_rs()
        left.where_constraints = collect_where_equality_pins(
            BinOp(Dimension(FACT), EQ, Constant("Integer", 1))
        )
        right.where_constraints = collect_where_equality_pins(
            BinOp(Dimension(FACT), EQ, Constant("Integer", 2))
        )
        assert left.where_constraints == {}
        BinPlus.validate_structures(left, right)  # must not raise

    def test_shared_key_pin_conflict_still_raises_2_2(self):
        """Regression guard: the key-based check keeps working."""
        left = _make_rs()
        right = _make_rs()
        left.where_constraints = {"qA": "X"}
        right.where_constraints = {"qA": "Y"}
        with pytest.raises(SemanticError) as exc:
            BinPlus.validate_structures(left, right)
        assert exc.value.code == "2-2"
