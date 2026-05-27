"""Tests for interval type validation in ScalarFactory.

Tests that the ScalarFactory correctly handles interval=true: stored for
Number and Integer types, no effect for String, Boolean, Item, etc.
"""

import pytest

from dpmcore.dpm_xl.types.scalar import (
    Boolean,
    Integer,
    Item,
    Number,
    ScalarFactory,
    String,
    TimeInterval,
)


class TestIntervalTypeValidation:
    """Test cases for interval type validation in ScalarFactory."""

    @pytest.fixture
    def scalar_factory(self):
        """Create a ScalarFactory instance for testing."""
        return ScalarFactory()

    def test_interval_with_string_type_is_valid(self, scalar_factory):
        """interval=True with String type (STR) must be accepted."""
        result = scalar_factory.from_database_to_scalar_types(
            "STR", interval=True
        )
        assert isinstance(result, String)

    def test_interval_with_uri_string_type_is_valid(self, scalar_factory):
        """interval=True with String type (URI) must be accepted."""
        result = scalar_factory.from_database_to_scalar_types(
            "URI", interval=True
        )
        assert isinstance(result, String)

    def test_interval_with_es_string_type_is_valid(self, scalar_factory):
        """interval=True with String type (es) must be accepted."""
        result = scalar_factory.from_database_to_scalar_types(
            "es", interval=True
        )
        assert isinstance(result, String)

    def test_interval_with_boolean_type_is_valid(self, scalar_factory):
        """interval=True with Boolean type (BOO) must be accepted."""
        result = scalar_factory.from_database_to_scalar_types(
            "BOO", interval=True
        )
        assert isinstance(result, Boolean)

    def test_interval_with_tru_boolean_type_is_valid(self, scalar_factory):
        """interval=True with Boolean type (TRU) must be accepted."""
        result = scalar_factory.from_database_to_scalar_types(
            "TRU", interval=True
        )
        assert isinstance(result, Boolean)

    def test_interval_with_item_type_is_valid(self, scalar_factory):
        """interval=True with Item type (ENU) must be accepted."""
        result = scalar_factory.from_database_to_scalar_types(
            "ENU", interval=True
        )
        assert isinstance(result, Item)

    def test_interval_with_timeinterval_type_is_valid(self, scalar_factory):
        """interval=True with TimeInterval type (DAT) must be accepted."""
        result = scalar_factory.from_database_to_scalar_types(
            "DAT", interval=True
        )
        assert isinstance(result, TimeInterval)

    def test_interval_with_number_type_is_valid(self, scalar_factory):
        """interval=True with Number type (DEC) should be valid."""
        result = scalar_factory.from_database_to_scalar_types(
            "DEC", interval=True
        )

        assert isinstance(result, Number)
        assert result.interval is True

    def test_interval_with_per_number_type_is_valid(self, scalar_factory):
        """interval=True with Number type (PER) should be valid."""
        result = scalar_factory.from_database_to_scalar_types(
            "PER", interval=True
        )

        assert isinstance(result, Number)
        assert result.interval is True

    def test_interval_with_mon_number_type_is_valid(self, scalar_factory):
        """interval=True with Number type (MON) should be valid."""
        result = scalar_factory.from_database_to_scalar_types(
            "MON", interval=True
        )

        assert isinstance(result, Number)
        assert result.interval is True

    def test_interval_with_integer_type_is_valid(self, scalar_factory):
        """interval=True with Integer type (INT) should be valid."""
        result = scalar_factory.from_database_to_scalar_types(
            "INT", interval=True
        )

        assert isinstance(result, Integer)
        assert result.interval is True

    def test_no_interval_with_string_type_is_valid(self, scalar_factory):
        """interval=False with String type should be valid."""
        result = scalar_factory.from_database_to_scalar_types(
            "STR", interval=False
        )

        assert isinstance(result, String)

    def test_none_interval_with_string_type_is_valid(self, scalar_factory):
        """interval=None with String type should be valid."""
        result = scalar_factory.from_database_to_scalar_types(
            "STR", interval=None
        )

        assert isinstance(result, String)

    def test_no_interval_with_boolean_type_is_valid(self, scalar_factory):
        """interval=False with Boolean type should be valid."""
        result = scalar_factory.from_database_to_scalar_types(
            "BOO", interval=False
        )

        assert isinstance(result, Boolean)

    def test_no_interval_with_item_type_is_valid(self, scalar_factory):
        """interval=False with Item type should be valid."""
        result = scalar_factory.from_database_to_scalar_types(
            "ENU", interval=False
        )

        assert isinstance(result, Item)

    def test_no_interval_with_time_interval_type_is_valid(
        self, scalar_factory
    ):
        """interval=False with TimeInterval type should be valid."""
        result = scalar_factory.from_database_to_scalar_types(
            "DAT", interval=False
        )

        assert isinstance(result, TimeInterval)

    def test_no_interval_with_number_type_is_valid(self, scalar_factory):
        """interval=False with Number type should be valid."""
        result = scalar_factory.from_database_to_scalar_types(
            "DEC", interval=False
        )

        assert isinstance(result, Number)
        assert result.interval is False

    def test_none_interval_with_number_type_is_valid(self, scalar_factory):
        """interval=None with Number type should be valid."""
        result = scalar_factory.from_database_to_scalar_types(
            "DEC", interval=None
        )

        assert isinstance(result, Number)
        assert result.interval is None
