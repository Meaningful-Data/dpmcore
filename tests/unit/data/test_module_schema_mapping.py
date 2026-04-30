"""Tests for ``dpmcore.data`` static module URL mapping helpers."""

from datetime import datetime
from unittest.mock import patch

import pytest

from dpmcore.data import (
    _load_module_schema_mapping,
    _parse_date,
    get_module_schema_ref,
    get_module_schema_ref_by_version,
)

FAKE_MAPPINGS = [
    {
        "module_code": "COREP_Con",
        "xbrl_schema_ref": "http://example.org/corep_con_v1.json",
        "from_date": datetime(2014, 1, 1),
        "to_date": datetime(2014, 6, 30),
        "version": "1.0.0",
    },
    {
        "module_code": "COREP_Con",
        "xbrl_schema_ref": "http://example.org/corep_con_v2.json",
        "from_date": datetime(2014, 7, 1),
        "to_date": None,
        "version": "2.0.0",
    },
    {
        "module_code": "FINREP",
        "xbrl_schema_ref": "http://example.org/finrep_v1.json",
        "from_date": None,
        "to_date": None,
        "version": "1.0.0",
    },
]


@pytest.fixture
def fake_loader():
    """Patch the cached CSV loader so tests don't depend on real CSV."""
    with patch(
        "dpmcore.data._load_module_schema_mapping",
        return_value=FAKE_MAPPINGS,
    ):
        yield


class TestLoadMapping:
    def test_loads_real_csv(self):
        """Exercise the real CSV load (lru_cache cleared first)."""
        _load_module_schema_mapping.cache_clear()
        mappings = _load_module_schema_mapping()
        assert len(mappings) > 0
        assert set(mappings[0]) == {
            "module_code",
            "xbrl_schema_ref",
            "from_date",
            "to_date",
            "version",
        }

    def test_cache_returns_immutable_collection(self):
        """The cached result must not be mutable through callers.

        Regression for S8: a previous version returned a plain
        ``list`` of plain ``dict`` objects, so any caller that
        sorted/popped/reassigned the result poisoned the cache for
        the rest of the process.
        """
        _load_module_schema_mapping.cache_clear()
        mappings = _load_module_schema_mapping()
        with pytest.raises((AttributeError, TypeError)):
            mappings.append({})  # type: ignore[attr-defined]
        with pytest.raises(TypeError):
            mappings[0]["module_code"] = "tampered"  # type: ignore[index]


class TestParseDate:
    def test_returns_none_for_empty_string(self):
        assert _parse_date("") is None

    def test_parses_valid_format(self):
        assert _parse_date("01-Jan-2014") == datetime(2014, 1, 1)

    def test_parses_far_future_sentinel(self):
        """The IF_TM v1.2.0 row uses 9999 as a 'no specific date' sentinel."""
        assert _parse_date("31-Dec-9999") == datetime(9999, 12, 31)

    def test_returns_none_for_invalid(self):
        assert _parse_date("not-a-date") is None

    def test_two_digit_year_is_rejected(self):
        """Legacy DD-Mon-YY format is no longer accepted."""
        assert _parse_date("01-Jan-14") is None


@pytest.mark.usefixtures("fake_loader")
class TestGetModuleSchemaRefByVersion:
    def test_exact_match(self):
        url = get_module_schema_ref_by_version("COREP_Con", "1.0.0")
        assert url == "http://example.org/corep_con_v1.json"

    def test_case_insensitive_module_code(self):
        url = get_module_schema_ref_by_version("corep_con", "2.0.0")
        assert url == "http://example.org/corep_con_v2.json"

    def test_returns_none_for_unknown_module(self):
        assert get_module_schema_ref_by_version("UNKNOWN", "1.0.0") is None

    def test_returns_none_for_unknown_version(self):
        assert get_module_schema_ref_by_version("COREP_Con", "9.9.9") is None


@pytest.mark.usefixtures("fake_loader")
class TestGetModuleSchemaRef:
    def test_no_candidates_returns_none(self):
        assert get_module_schema_ref("UNKNOWN") is None

    def test_no_date_returns_latest_open_ended(self):
        url = get_module_schema_ref("COREP_Con")
        assert url == "http://example.org/corep_con_v2.json"

    def test_date_in_first_window(self):
        url = get_module_schema_ref("COREP_Con", "2014-03-15")
        assert url == "http://example.org/corep_con_v1.json"

    def test_date_in_open_ended_window(self):
        url = get_module_schema_ref("COREP_Con", "2025-01-15")
        assert url == "http://example.org/corep_con_v2.json"

    def test_invalid_date_returns_none(self):
        assert get_module_schema_ref("COREP_Con", "not-a-date") is None

    def test_date_outside_any_window_returns_none(self):
        """Date before any from_date falls through the loop."""
        assert get_module_schema_ref("COREP_Con", "2010-01-01") is None

    def test_entry_without_from_date_is_skipped(self):
        """A candidate with no from_date is not selected by a date query."""
        assert get_module_schema_ref("FINREP", "2020-01-01") is None


class TestGetModuleSchemaRefNoOpenEnded:
    """Covers the fallback branch when no entry is open-ended."""

    def test_no_date_no_open_ended_falls_back_to_last(self):
        only_closed = [
            {
                "module_code": "X",
                "xbrl_schema_ref": "http://x/old.json",
                "from_date": datetime(2020, 1, 1),
                "to_date": datetime(2020, 12, 31),
                "version": "1.0.0",
            },
            {
                "module_code": "X",
                "xbrl_schema_ref": "http://x/new.json",
                "from_date": datetime(2021, 1, 1),
                "to_date": datetime(2021, 12, 31),
                "version": "2.0.0",
            },
        ]
        with patch(
            "dpmcore.data._load_module_schema_mapping",
            return_value=only_closed,
        ):
            assert get_module_schema_ref("X") == "http://x/new.json"
