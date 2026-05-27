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
from dpmcore.dpm_xl.types.scalar import Number
from dpmcore.dpm_xl.utils.tokens import STANDARD
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
