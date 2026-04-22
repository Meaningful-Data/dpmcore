"""Tests for interval type validation in ScalarFactory.

Tests that the ScalarFactory correctly validates that interval=true can only
be used with Number and Integer types, not with String, Boolean, Item, etc.
"""

import pytest
from py_dpm.dpm_xl.types.scalar import (
    Boolean,
    Integer,
    Item,
    Number,
    ScalarFactory,
    String,
    TimeInterval,
)
from py_dpm.exceptions.exceptions import SemanticError


class TestIntervalTypeValidation:
    """Test cases for interval type validation in ScalarFactory."""

    @pytest.fixture
    def scalar_factory(self):
        """Create a ScalarFactory instance for testing."""
        return ScalarFactory()

    def test_interval_with_string_type_raises_error(self, scalar_factory):
        """interval=True with String type (STR) should raise SemanticError 3-4."""
        with pytest.raises(SemanticError) as exc_info:
            scalar_factory.from_database_to_scalar_types("STR", interval=True)

        assert "Interval can't be used" in str(exc_info.value)
        assert "String" in str(exc_info.value)

    def test_interval_with_uri_string_type_raises_error(self, scalar_factory):
        """interval=True with String type (URI) should raise SemanticError 3-4."""
        with pytest.raises(SemanticError) as exc_info:
            scalar_factory.from_database_to_scalar_types("URI", interval=True)

        assert "Interval can't be used" in str(exc_info.value)
        assert "String" in str(exc_info.value)

    def test_interval_with_es_string_type_raises_error(self, scalar_factory):
        """interval=True with String type (es) should raise SemanticError 3-4."""
        with pytest.raises(SemanticError) as exc_info:
            scalar_factory.from_database_to_scalar_types("es", interval=True)

        assert "Interval can't be used" in str(exc_info.value)
        assert "String" in str(exc_info.value)

    def test_interval_with_boolean_type_raises_error(self, scalar_factory):
        """interval=True with Boolean type (BOO) should raise SemanticError 3-4."""
        with pytest.raises(SemanticError) as exc_info:
            scalar_factory.from_database_to_scalar_types("BOO", interval=True)

        assert "Interval can't be used" in str(exc_info.value)
        assert "Boolean" in str(exc_info.value)

    def test_interval_with_tru_boolean_type_raises_error(self, scalar_factory):
        """interval=True with Boolean type (TRU) should raise SemanticError 3-4."""
        with pytest.raises(SemanticError) as exc_info:
            scalar_factory.from_database_to_scalar_types("TRU", interval=True)

        assert "Interval can't be used" in str(exc_info.value)
        assert "Boolean" in str(exc_info.value)

    def test_interval_with_item_type_raises_error(self, scalar_factory):
        """interval=True with Item type (ENU) should raise SemanticError 3-4."""
        with pytest.raises(SemanticError) as exc_info:
            scalar_factory.from_database_to_scalar_types("ENU", interval=True)

        assert "Interval can't be used" in str(exc_info.value)
        assert "Item" in str(exc_info.value)

    def test_interval_with_time_interval_type_raises_error(
        self, scalar_factory
    ):
        """interval=True with TimeInterval type (DAT) should raise SemanticError 3-4."""
        with pytest.raises(SemanticError) as exc_info:
            scalar_factory.from_database_to_scalar_types("DAT", interval=True)

        assert "Interval can't be used" in str(exc_info.value)
        assert "TimeInterval" in str(exc_info.value)

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
