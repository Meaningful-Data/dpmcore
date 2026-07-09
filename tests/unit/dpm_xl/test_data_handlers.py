"""Unit tests for cell-element filtering, including range endpoint checks."""

import pandas as pd
import pytest

from dpmcore.dpm_xl.utils.data_handlers import (
    filter_all_data,
    filter_data_by_cell_element,
)
from dpmcore.errors import SemanticError


def _columns(*codes: str) -> pd.DataFrame:
    """Build a minimal cell frame carrying only ``column_code`` values."""
    return pd.DataFrame({"column_code": list(codes)})


def _cells(table_code: str, *rcs: tuple[str, str]) -> pd.DataFrame:
    """Build a cell frame from ``(row_code, column_code)`` pairs.

    A single sheet ``0000`` is assumed; this models a sparse table where
    not every ``(row, column)`` intersection carries a datapoint.
    """
    return pd.DataFrame(
        [
            {
                "table_code": table_code,
                "row_code": row,
                "column_code": col,
                "sheet_code": "0000",
            }
            for row, col in rcs
        ]
    )


class TestRangeEndpointExistence:
    """A range endpoint that is not a real code must raise ``1-2``.

    A range resolves via a between-comparison, so a bogus endpoint (e.g. the
    typo ``c0010-c0030``, read as the range from code ``0010`` to code
    ``c0030``) is silently accepted: the comparison still spans the real codes
    in between. The endpoints themselves must therefore be checked.
    """

    def test_valid_range_keeps_spanned_codes(self):
        df = _columns("0010", "0020", "0030")
        result = filter_data_by_cell_element(
            df, ["0010-0030"], "column_code", "F_11.03"
        )
        assert sorted(result["column_code"]) == ["0010", "0020", "0030"]

    def test_bogus_second_endpoint_raises(self):
        df = _columns("0010", "0020", "0030")
        with pytest.raises(SemanticError) as exc:
            filter_data_by_cell_element(
                df, ["0010-c0030"], "column_code", "F_11.03"
            )
        assert exc.value.code == "1-2"
        # The missing column code (c0030) is echoed in selector notation.
        assert "c0030" in str(exc.value)

    def test_bogus_first_endpoint_raises(self):
        df = _columns("0010", "0020", "0030")
        with pytest.raises(SemanticError) as exc:
            filter_data_by_cell_element(
                df, ["9990-0030"], "column_code", "F_11.03"
            )
        assert exc.value.code == "1-2"
        assert "c9990" in str(exc.value)

    def test_both_endpoints_bogus_reports_both(self):
        df = _columns("0010", "0020", "0030")
        with pytest.raises(SemanticError) as exc:
            filter_data_by_cell_element(
                df, ["9990-9999"], "column_code", "F_11.03"
            )
        message = str(exc.value)
        assert "c9990" in message
        assert "c9999" in message

    def test_range_endpoint_checked_within_element_list(self):
        df = _columns("0010", "0020", "0030")
        with pytest.raises(SemanticError) as exc:
            filter_data_by_cell_element(
                df, ["0010-c0030", "0020"], "column_code", "F_11.03"
            )
        assert exc.value.code == "1-2"

    def test_valid_range_within_element_list(self):
        df = _columns("0010", "0020", "0030", "0040")
        result = filter_data_by_cell_element(
            df, ["0010-0030", "0040"], "column_code", "F_11.03"
        )
        assert sorted(result["column_code"]) == [
            "0010",
            "0020",
            "0030",
            "0040",
        ]

    def test_valid_codes_widens_endpoint_check(self):
        """An endpoint absent from ``series`` but present in ``valid_codes``.

        ``series`` here has only ``0010``/``0020`` (e.g. the frame was
        already narrowed to a row that lacks ``0030``), but ``0030`` is a
        real column of the table, so the range must resolve without error.
        """
        df = _columns("0010", "0020")
        result = filter_data_by_cell_element(
            df,
            ["0010-0030"],
            "column_code",
            "F_11.03",
            valid_codes={"0010", "0020", "0030"},
        )
        assert sorted(result["column_code"]) == ["0010", "0020"]


class TestSparseTableRangeEndpoints:
    """Range endpoints are validated against the table's full code set.

    Regression test: ``filter_all_data`` narrows one axis after another on a
    single frame, so by the time a column range is checked the frame only
    holds columns that intersect the already-selected rows. A range whose
    endpoint is a real table column but is grey (no datapoint) for those rows
    must still resolve -- it must not be misreported as a missing cell.
    """

    def test_range_endpoint_missing_from_selected_rows_is_valid(self):
        # Column 0030 exists in the table (via row 0020) but has no
        # datapoint in row 0010, which is the only selected row.
        data = _cells(
            "T1",
            ("0010", "0010"),
            ("0010", "0020"),
            ("0020", "0010"),
            ("0020", "0020"),
            ("0020", "0030"),
        )
        result = filter_all_data(data, "T1", ["0010"], ["0010-0030"], ["0000"])
        # The range spans only the columns present for row 0010; no error.
        assert sorted(set(result["column_code"])) == ["0010", "0020"]

    def test_bogus_range_endpoint_still_rejected(self):
        # 0099 is not a column of the table at all -> genuine error.
        data = _cells(
            "T1",
            ("0010", "0010"),
            ("0010", "0020"),
            ("0020", "0030"),
        )
        with pytest.raises(SemanticError) as exc:
            filter_all_data(data, "T1", ["0010"], ["0010-0099"], ["0000"])
        assert exc.value.code == "1-2"
        assert "c0099" in str(exc.value)
