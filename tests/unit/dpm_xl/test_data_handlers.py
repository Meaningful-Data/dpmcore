"""Unit tests for cell-element filtering, including range endpoint checks."""

import pandas as pd
import pytest

from dpmcore.dpm_xl.utils.data_handlers import filter_data_by_cell_element
from dpmcore.errors import SemanticError


def _columns(*codes: str) -> pd.DataFrame:
    """Build a minimal cell frame carrying only ``column_code`` values."""
    return pd.DataFrame({"column_code": list(codes)})


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
