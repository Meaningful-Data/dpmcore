import pytest

from dpmcore.dpm_xl.ast.nodes import VarID
from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.errors import SemanticError


def _varid(table: str, rows=None, cols=None, sheets=None) -> VarID:
    return VarID(
        table=table,
        rows=rows,
        cols=cols,
        sheets=sheets,
        default=None,
        interval=False,
    )


def _make_oc(
    operands: list[VarID],
    partial_selection: VarID | None = None,
) -> OperandsChecking:
    oc = object.__new__(OperandsChecking)
    table = operands[0].table
    assert table is not None
    oc.operands = {table: operands}
    oc.partial_selection = partial_selection
    return oc


class TestCheckHeaderPresentUniformOmission:
    """Uniform omission of a header means 'apply to all', must NOT raise 1-20."""

    def test_all_operands_omit_cols_no_raise(self):
        """All operands omit cols (row-only expression) are valid."""
        nodes = [
            _varid("C_02.00.a", rows=["r0010"]),
            _varid("C_02.00.a", rows=["r0040"]),
            _varid("C_02.00.a", rows=["r0490"]),
        ]
        oc = _make_oc(nodes)
        oc._check_header_present("C_02.00.a", "cols")  # must not raise

    def test_all_operands_omit_rows_no_raise(self):
        """All operands omit rows (column-only expression) are valid."""
        nodes = [
            _varid("C_07.00.a", cols=["c0215"]),
            _varid("C_07.00.a", cols=["c0216"]),
            _varid("C_07.00.a", cols=["c0220"]),
        ]
        oc = _make_oc(nodes)
        oc._check_header_present("C_07.00.a", "rows")  # must not raise

    def test_single_operand_omits_cols_no_raise(self):
        """Single operand without cols (e.g. {tTable, c0020} <= 1) are valid."""
        nodes = [_varid("C_34.07", cols=["c0020"])]
        oc = _make_oc(nodes)
        oc._check_header_present("C_34.07", "rows")  # must not raise

    def test_partial_selection_without_cols_all_operands_omit_no_raise(self):
        """partial_selection without cols and all operands omit cols must be valid."""
        ps = _varid("C_02.00.a")  # partial_selection: no cols
        nodes = [
            _varid("C_02.00.a", rows=["r0010"]),
            _varid("C_02.00.a", rows=["r0040"]),
        ]
        oc = _make_oc(nodes, partial_selection=ps)
        oc._check_header_present("C_02.00.a", "cols")  # must not raise


class TestCheckHeaderPresentMixedSpecification:
    """Mixed specification raises 1-20."""

    def test_mixed_cols_raises(self):
        """Some operands have cols and one does not must raise 1-20."""
        nodes = [
            _varid("SomeTable", rows=["r0010"], cols=["c0010"]),
            _varid("SomeTable", rows=["r0040"]),  # no cols
        ]
        oc = _make_oc(nodes)
        with pytest.raises(SemanticError, match="Missing explicit"):
            oc._check_header_present("SomeTable", "cols")

    def test_partial_selection_with_cols_skips_check(self):
        """partial_selection that specifies cols must skip the check entirely."""
        ps = _varid("SomeTable", cols=["c0010"])
        nodes = [
            _varid("SomeTable", rows=["r0010"]),  # no cols in operand
        ]
        oc = _make_oc(nodes, partial_selection=ps)
        oc._check_header_present("SomeTable", "cols")  # must not raise
