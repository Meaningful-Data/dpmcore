"""Tests for validate_structures record count check in binary operators."""

import pandas as pd
import pytest

import dpmcore.dpm_xl.semantic_analyzer  # noqa: F401 (resolves circular imports)
from dpmcore.dpm_xl.operators.arithmetic import BinPlus
from dpmcore.dpm_xl.operators.comparison import LessEqual
from dpmcore.dpm_xl.symbols import (
    FactComponent,
    KeyComponent,
    RecordSet,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import Item, Number
from dpmcore.dpm_xl.utils.tokens import DPM, STANDARD
from dpmcore.errors import SemanticError


def _make_recordset(n_rows: int) -> RecordSet:
    structure = Structure(
        [
            KeyComponent("r", Number(), STANDARD, "test"),
            FactComponent(Number(), "test"),
        ]
    )
    rs = RecordSet(structure, "test", "test")
    rs.records = pd.DataFrame(
        {
            "r": [str(i) for i in range(n_rows)],
            "data_type": [Number() for _ in range(n_rows)],
        }
    )
    return rs


class TestValidateStructuresDifferentRecordCounts:
    def test_comparison_allows_different_record_counts(self):
        """LessEqual must not raise 2-9 when record counts differ."""
        left = _make_recordset(5)
        right = _make_recordset(3)
        LessEqual.validate_structures(left, right)  # must not raise

    def test_arithmetic_raises_2_9_for_different_record_counts(self):
        """BinPlus must raise 2-9 when record counts differ."""
        left = _make_recordset(5)
        right = _make_recordset(3)
        with pytest.raises(SemanticError, match="different number of headers"):
            BinPlus.validate_structures(left, right)


def _make_pinned_recordset(pins: dict[str, str]) -> RecordSet:
    """Recordset sharing one DPM key (``qEEA``) with given where-pins."""
    structure = Structure(
        [
            KeyComponent("r", Number(), STANDARD, "test"),
            KeyComponent("qEEA", Item(), DPM, "test"),
            FactComponent(Number(), "test"),
        ]
    )
    rs = RecordSet(structure, "test", "test")
    rs.where_constraints = pins
    return rs


class TestValidateStructuresContradictoryWhere:
    """Issue #121: disjoint where-pins on a shared key are a dead join."""

    def test_disjoint_pins_raise_2_2(self):
        left = _make_pinned_recordset({"qEEA": "qx2023"})
        right = _make_pinned_recordset({"qEEA": "qx2022"})
        with pytest.raises(SemanticError, match="no match between"):
            BinPlus.validate_structures(left, right)

    def test_disjoint_pins_raise_2_2_for_comparison(self):
        left = _make_pinned_recordset({"qEEA": "qx2023"})
        right = _make_pinned_recordset({"qEEA": "qx2022"})
        with pytest.raises(SemanticError, match="no match between"):
            LessEqual.validate_structures(left, right)

    def test_same_pin_value_does_not_raise(self):
        left = _make_pinned_recordset({"qEEA": "qx2023"})
        right = _make_pinned_recordset({"qEEA": "qx2023"})
        BinPlus.validate_structures(left, right)  # must not raise

    def test_pin_on_one_side_only_does_not_raise(self):
        left = _make_pinned_recordset({"qEEA": "qx2023"})
        right = _make_pinned_recordset({})
        BinPlus.validate_structures(left, right)  # must not raise

    def test_no_pins_does_not_raise(self):
        left = _make_pinned_recordset({})
        right = _make_pinned_recordset({})
        BinPlus.validate_structures(left, right)  # must not raise
