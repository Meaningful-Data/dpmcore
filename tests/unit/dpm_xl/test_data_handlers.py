"""Unit tests for cell-element filtering, including range endpoint checks."""

import pandas as pd
import pytest

from dpmcore.dpm_xl.utils.data_handlers import (
    filter_all_data,
    filter_data_by_cell_element,
    generate_xyz,
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


def _ordered_columns(*codes: str) -> pd.DataFrame:
    """Column frame carrying a ``column_order`` = display position (1-based)."""
    return pd.DataFrame(
        {
            "column_code": list(codes),
            "column_order": list(range(1, len(codes) + 1)),
        }
    )


class TestOrderBasedRangeMembership:
    """Ranges resolve by stored display order when an ``order_map`` is given.

    Regression for issue #209: non-padded codes such as ``10``/``11`` sort
    before ``2`` as text, so the string ``between`` drops them; the order map
    fixes membership.
    """

    def test_non_padded_range_includes_high_codes(self):
        codes = [str(i) for i in range(1, 12)]  # "1".."11" in display order
        df = _ordered_columns(*codes)
        order_map = dict(zip(codes, range(1, 12), strict=False))
        result = filter_data_by_cell_element(
            df, ["2-11"], "column_code", "T", set(codes), order_map
        )
        # 10 and 11 are inside the range and 1 is outside -- the whole point.
        assert set(result["column_code"]) == {str(i) for i in range(2, 12)}

    def test_reversed_range_selects_nothing(self):
        codes = [str(i) for i in range(1, 12)]
        df = _ordered_columns(*codes)
        order_map = dict(zip(codes, range(1, 12), strict=False))
        result = filter_data_by_cell_element(
            df, ["11-2"], "column_code", "T", set(codes), order_map
        )
        assert result.empty

    def test_range_within_list_uses_order(self):
        codes = [str(i) for i in range(1, 12)]
        df = _ordered_columns(*codes)
        order_map = dict(zip(codes, range(1, 12), strict=False))
        result = filter_data_by_cell_element(
            df, ["1", "9-11"], "column_code", "T", set(codes), order_map
        )
        assert set(result["column_code"]) == {"1", "9", "10", "11"}

    def test_no_order_map_falls_back_to_text_between(self):
        # Zero-padded codes still resolve correctly via the string path.
        df = _columns("0010", "0020", "0030")
        result = filter_data_by_cell_element(
            df, ["0010-0030"], "column_code", "T"
        )
        assert sorted(result["column_code"]) == ["0010", "0020", "0030"]


def _xyz_frame(row_codes: list[str], with_order: bool) -> pd.DataFrame:
    """Single-column frame of rows, optionally carrying display-order columns."""
    data: dict[str, list] = {
        "row_code": row_codes,
        "column_code": ["1"] * len(row_codes),
        "sheet_code": [None] * len(row_codes),
        "variable_id": list(range(len(row_codes))),
        "cell_id": list(range(len(row_codes))),
    }
    if with_order:
        # Display order = 1-based position in the given (already sorted) list.
        data["row_order"] = list(range(1, len(row_codes) + 1))
        data["column_order"] = [1] * len(row_codes)
        data["sheet_order"] = [None] * len(row_codes)
    return pd.DataFrame(data)


class TestGenerateXyzOrdering:
    """X/Y/Z coordinates follow the stored display order, not the code text.

    This ranking path applies to whatever codes are present, so it fixes
    wildcard (``r*``) and explicit-list selections as well as ranges.
    """

    def test_x_follows_display_order_for_non_padded_rows(self):
        # Rows given in display order r1..r11; r10/r11 must rank last.
        rows = [str(i) for i in range(1, 12)]
        result = generate_xyz(_xyz_frame(rows, with_order=True))
        x_by_row = {r["row_code"]: r["x"] for r in result}
        assert x_by_row["1"] == 1
        assert x_by_row["2"] == 2
        assert x_by_row["10"] == 10
        assert x_by_row["11"] == 11

    def test_order_helper_columns_are_not_leaked(self):
        rows = [str(i) for i in range(1, 4)]
        result = generate_xyz(_xyz_frame(rows, with_order=True))
        assert "row_order" not in result[0]
        assert "column_order" not in result[0]
        assert "sheet_order" not in result[0]

    def test_without_order_columns_falls_back_to_text_rank(self):
        # No order columns -> previous text-based ranking: "10" sorts second.
        rows = [str(i) for i in range(1, 12)]
        result = generate_xyz(_xyz_frame(rows, with_order=False))
        x_by_row = {r["row_code"]: r["x"] for r in result}
        assert x_by_row["10"] == 2  # lexicographic: "1","10","11","2",...
