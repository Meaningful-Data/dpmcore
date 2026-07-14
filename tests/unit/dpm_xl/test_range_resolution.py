"""Unit tests for order-based range resolution helpers.

These cover the core of issue #209: ranges must be resolved by the stored
display order, not by comparing the code text, so non-padded / mixed-width /
non-numeric codes span and sort correctly.
"""

import math

from dpmcore.dpm_xl.utils.range_resolution import (
    build_axis_order_map,
    resolve_range_codes,
    sort_by_order,
)

# Rows r1..r11 in display order -- the classic case where text order
# ("r10" < "r2") disagrees with display order.
NON_PADDED = {f"r{i}": i for i in range(1, 12)}


class TestResolveRangeCodes:
    def test_non_padded_range_spans_by_order(self):
        # r2-r11 must include r10 and r11 (which sort before r2 as text).
        result = resolve_range_codes(NON_PADDED, "r2", "r11")
        assert result == [f"r{i}" for i in range(2, 12)]

    def test_result_is_in_display_order_not_text_order(self):
        result = resolve_range_codes(NON_PADDED, "r8", "r11")
        assert result == ["r8", "r9", "r10", "r11"]

    def test_zero_padded_range_unchanged(self):
        padded = {"0010": 1, "0020": 2, "0030": 3}
        assert resolve_range_codes(padded, "0010", "0030") == [
            "0010",
            "0020",
            "0030",
        ]

    def test_single_code_range(self):
        assert resolve_range_codes(NON_PADDED, "r5", "r5") == ["r5"]

    def test_reversed_range_returns_empty(self):
        # Per the agreed behaviour, a reversed range selects nothing so the
        # caller still raises the pre-existing "cell not found" error.
        assert resolve_range_codes(NON_PADDED, "r11", "r2") == []

    def test_missing_low_endpoint_returns_empty(self):
        assert resolve_range_codes(NON_PADDED, "rX", "r5") == []

    def test_missing_high_endpoint_returns_empty(self):
        assert resolve_range_codes(NON_PADDED, "r5", "rX") == []

    def test_alphabetic_codes_span_by_order(self):
        sheets = {"alpha": 1, "beta": 2, "gamma": 3, "delta": 4}
        assert resolve_range_codes(sheets, "beta", "delta") == [
            "beta",
            "gamma",
            "delta",
        ]


class TestSortByOrder:
    def test_sorts_by_display_order(self):
        codes = ["r10", "r2", "r1", "r11"]
        assert sort_by_order(codes, NON_PADDED) == ["r1", "r2", "r10", "r11"]

    def test_unmapped_codes_sort_last_lexicographically(self):
        codes = ["r2", "zzz", "r1", "aaa"]
        assert sort_by_order(codes, NON_PADDED) == ["r1", "r2", "aaa", "zzz"]

    def test_deduplicates(self):
        assert sort_by_order(["r2", "r2", "r1"], NON_PADDED) == ["r1", "r2"]


class TestBuildAxisOrderMap:
    def test_fully_ordered_axis(self):
        result = build_axis_order_map(["r1", "r2"], [1, 2])
        assert result == {"r1": 1, "r2": 2}

    def test_missing_order_returns_none(self):
        # r2 has no stored order -> axis is not fully ordered -> fall back.
        assert build_axis_order_map(["r1", "r2"], [1, None]) is None

    def test_nan_order_returns_none(self):
        assert build_axis_order_map(["r1", "r2"], [1, math.nan]) is None

    def test_conflicting_orders_returns_none(self):
        # A code that maps to two different orders is untrustworthy.
        assert build_axis_order_map(["r1", "r1"], [1, 2]) is None

    def test_repeated_consistent_order_is_kept(self):
        assert build_axis_order_map(["r1", "r1", "r2"], [1, 1, 2]) == {
            "r1": 1,
            "r2": 2,
        }

    def test_missing_codes_are_skipped(self):
        # A cell that lacks this axis (e.g. no sheets) carries a null code.
        result = build_axis_order_map(["r1", None, math.nan], [1, None, None])
        assert result == {"r1": 1}

    def test_no_codes_returns_empty_map(self):
        assert build_axis_order_map([None, math.nan], [None, None]) == {}

    def test_float_orders_are_coerced_to_int(self):
        # pandas surfaces a nullable int column as float64.
        assert build_axis_order_map(["r1", "r2"], [1.0, 2.0]) == {
            "r1": 1,
            "r2": 2,
        }
