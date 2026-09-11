"""Operand kinds accepted by ``nvl`` (§8.2.2).

The specification types the operator as ``nvl(op1, op2)`` with both
operands ``rset | scal <*>``, so the only shapes it has to combine are
recordsets and scalars. The grammar is wider than that — ``nvl`` takes two
arbitrary expressions, and ``expression`` covers a set — so a set operand
reached ``check_structures``, matched none of the four handled
combinations, and surfaced as a bare ``Exception`` rather than a
``SemanticError``. It is now reported as ``4-6-2-2``.

The rest of the operator's contract is unchanged and covered here because
nothing else exercised it: a recordset first operand keeps its structure,
a scalar first operand cannot be filled from a recordset (``4-6-2-1``),
and two recordsets must have matching or nested structures.
"""

import pytest

import dpmcore.dpm_xl.semantic_analyzer  # noqa: F401 (resolves circular imports)
from dpmcore.dpm_xl.operators.conditional import Nvl
from dpmcore.dpm_xl.symbols import (
    FactComponent,
    KeyComponent,
    RecordSet,
    Scalar,
    ScalarSet,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import Number, String
from dpmcore.dpm_xl.utils.tokens import DPM, STANDARD
from dpmcore.errors import SemanticError

NOT_AN_OPERAND = "have to be a recordset or a scalar"
RIGHT_MUST_BE_SCALAR = "right op has to be scalar"


def _recordset(name: str, keys: list[KeyComponent]) -> RecordSet:
    structure = Structure(
        [
            KeyComponent("refPeriod", String(), DPM, name, is_global=True),
            *keys,
            FactComponent(Number(), name),
        ]
    )
    return RecordSet(structure, name, name)


def _scalar(name: str = "scalar") -> Scalar:
    return Scalar(type_=Number(), name=name, origin=name)


def _rows(name: str = "rows") -> RecordSet:
    return _recordset(name, [KeyComponent("r", String(), STANDARD, name)])


def _columns(name: str = "cols") -> RecordSet:
    return _recordset(name, [KeyComponent("c", String(), STANDARD, name)])


def _set(name: str = "set") -> ScalarSet:
    return ScalarSet(type_=Number(), name=name, origin=name)


class TestSetOperand:
    """A set is not one of the ``rset | scal`` operands of §8.2.2."""

    def test_a_set_first_operand_is_a_semantic_error(self):
        """``nvl({1, 2}, 0)`` used to raise a bare ``Exception``."""
        with pytest.raises(SemanticError, match=NOT_AN_OPERAND):
            Nvl.validate(_set(), _scalar())

    def test_a_set_second_operand_is_a_semantic_error(self):
        """``nvl(0, {1, 2})`` — the mirror shape, also reachable."""
        with pytest.raises(SemanticError, match=NOT_AN_OPERAND):
            Nvl.validate(_scalar(), _set())

    def test_a_set_operand_is_reported_by_name(self):
        with pytest.raises(SemanticError, match="my_set"):
            Nvl.validate(_set("my_set"), _scalar())

    @pytest.mark.parametrize("other", [_scalar, _rows])
    def test_a_set_is_rejected_whatever_it_is_paired_with(self, other):
        with pytest.raises(SemanticError, match=NOT_AN_OPERAND):
            Nvl.validate(_set(), other())
        with pytest.raises(SemanticError, match=NOT_AN_OPERAND):
            Nvl.validate(other(), _set())


class TestSupportedOperands:
    """The four combinations §8.2.2 does admit."""

    def test_two_scalars_stay_a_scalar(self):
        assert isinstance(Nvl.validate(_scalar("a"), _scalar("b")), Scalar)

    def test_a_recordset_filled_from_a_scalar_keeps_its_structure(self):
        result = Nvl.validate(_rows(), _scalar())
        assert isinstance(result, RecordSet)
        assert "r" in result.get_key_components_names()

    def test_a_scalar_cannot_be_filled_from_a_recordset(self):
        with pytest.raises(SemanticError, match=RIGHT_MUST_BE_SCALAR):
            Nvl.validate(_scalar(), _rows())

    def test_two_recordsets_with_the_same_structure_are_accepted(self):
        result = Nvl.validate(_rows("a"), _rows("b"))
        assert isinstance(result, RecordSet)
        assert "r" in result.get_key_components_names()

    def test_two_recordsets_with_unrelated_structures_are_rejected(self):
        with pytest.raises(SemanticError):
            Nvl.validate(_rows(), _columns())
