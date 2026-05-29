"""Tests for default value type checking in semantic analyzer.

Tests that the semantic analyzer correctly validates that default value types
are compatible with the operand's expected data type.
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import Constant
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.dpm_xl.types.scalar import (
    Boolean,
    Item,
    Mixed,
    Number,
    String,
    TimeInterval,
)
from dpmcore.errors import SemanticError


class TestCheckDefaultValue:
    """Test cases for __check_default_value static method."""

    @staticmethod
    def _create_constant(type_code: str, value) -> Constant:
        """Helper to create a Constant node for testing."""
        return Constant(type_=type_code, value=value)

    def test_integer_default_for_number_is_valid(self):
        """Integer default for Number operand should be valid (Integer can be promoted to Number)."""
        default_value = self._create_constant("Integer", 0)
        expected_type = Number()

        # Should not raise any exception
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, expected_type
        )

    def test_integer_default_for_string_is_valid(self):
        """Integer default for String operand should be valid (Integer can be promoted to String)."""
        default_value = self._create_constant("Integer", 0)
        expected_type = String()

        # Should not raise any exception
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, expected_type
        )

    def test_number_default_for_string_is_valid(self):
        """Number default for String operand should be valid (Number can be promoted to String)."""
        default_value = self._create_constant("Number", 0.0)
        expected_type = String()

        # Should not raise any exception
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, expected_type
        )

    def test_boolean_default_for_string_is_valid(self):
        """Boolean default for String operand should be valid (Boolean can be promoted to String)."""
        default_value = self._create_constant("Boolean", True)
        expected_type = String()

        # Should not raise any exception
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, expected_type
        )

    def test_boolean_default_for_boolean_is_valid(self):
        """Boolean default for Boolean operand should be valid."""
        default_value = self._create_constant("Boolean", True)
        expected_type = Boolean()

        # Should not raise any exception
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, expected_type
        )

    def test_string_default_for_string_is_valid(self):
        """String default for String operand should be valid."""
        default_value = self._create_constant("String", "")
        expected_type = String()

        # Should not raise any exception
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, expected_type
        )

    def test_string_default_for_boolean_is_valid(self):
        """String default for Boolean cell must be accepted.

        Boolean is string-representable (Boolean promotes to String).
        """
        default_value = self._create_constant("String", "")
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, Boolean()
        )

    def test_string_default_for_number_is_valid(self):
        """String default for Number cell must be accepted.

        Number is string-representable (Number promotes to String).
        """
        default_value = self._create_constant("String", "")
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, Number()
        )

    def test_string_default_for_item_is_valid(self):
        """String default for Item cell must be accepted.

        Item columns are string-representable (Item promotes to String),
        so ``default: ""`` is a valid sentinel for a missing enumeration value.
        """
        default_value = self._create_constant("String", "")
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, Item()
        )

    def test_string_default_for_timeinterval_is_valid(self):
        """String default for TimeInterval cell must be accepted.

        TimeInterval is string-representable (TimeInterval promotes to String).
        """
        default_value = self._create_constant("String", "")
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, TimeInterval()
        )

    def test_integer_default_for_item_is_valid(self):
        """Integer default for Item cell must be accepted.

        Both Integer and Item are string-representable, so integer 0 is a valid
        numeric sentinel for a missing enumeration value.
        Regression: 5 operations raised 3-6 with this pattern.
        """
        default_value = self._create_constant("Integer", 0)
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, Item()
        )

    def test_integer_default_for_timeinterval_is_valid(self):
        """Integer default for TimeInterval cell must be accepted.

        Both Integer and TimeInterval are string-representable, so integer 0 is
        a valid numeric sentinel for a missing time-interval value.
        Regression: 1 operation raised 3-6 with this pattern.
        """
        default_value = self._create_constant("Integer", 0)
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, TimeInterval()
        )

    def test_item_default_for_string_is_valid(self):
        """Item default for String operand should be valid (Item can be promoted to String)."""
        default_value = self._create_constant("Item", "[x1]")
        expected_type = String()

        # Should not raise any exception
        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, expected_type
        )

    def test_none_default_value_is_valid(self):
        """None default value should be valid (no check performed)."""
        # Should not raise any exception
        InputAnalyzer._InputAnalyzer__check_default_value(None, Boolean())
        InputAnalyzer._InputAnalyzer__check_default_value(None, String())
        InputAnalyzer._InputAnalyzer__check_default_value(None, Number())

    def test_number_default_for_boolean_raises_error(self):
        """Number default for Boolean operand should raise SemanticError 3-6."""
        default_value = self._create_constant("Number", 0.0)
        expected_type = Boolean()

        with pytest.raises(SemanticError) as exc_info:
            InputAnalyzer._InputAnalyzer__check_default_value(
                default_value, expected_type
            )

        assert "Invalid default type" in str(exc_info.value)
        assert "Number" in str(exc_info.value)
        assert "Boolean" in str(exc_info.value)

    def test_boolean_default_for_number_raises_error(self):
        """Boolean default for Number operand should raise SemanticError 3-6."""
        default_value = self._create_constant("Boolean", True)
        expected_type = Number()

        with pytest.raises(SemanticError) as exc_info:
            InputAnalyzer._InputAnalyzer__check_default_value(
                default_value, expected_type
            )

        assert "Invalid default type" in str(exc_info.value)
        assert "Boolean" in str(exc_info.value)
        assert "Number" in str(exc_info.value)

    def test_integer_default_for_boolean_raises_error(self):
        """Integer default for Boolean operand should raise SemanticError 3-6."""
        default_value = self._create_constant("Integer", 0)
        expected_type = Boolean()

        with pytest.raises(SemanticError) as exc_info:
            InputAnalyzer._InputAnalyzer__check_default_value(
                default_value, expected_type
            )

        assert "Invalid default type" in str(exc_info.value)
        assert "Integer" in str(exc_info.value)
        assert "Boolean" in str(exc_info.value)

    def test_null_default_for_item_is_valid(self):
        """Null default for Item operand should be valid.

        Null is the universal default and can be promoted to any type.
        Regression test for issue #2: ``default: null`` was returning
        Python ``None`` from the constructor, allowing an outer ``with``
        clause's default to leak in and trigger a spurious 3-6 error.
        """
        default_value = self._create_constant("Null", None)
        expected_type = Item()

        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, expected_type
        )

    def test_null_default_for_boolean_is_valid(self):
        """Null default for Boolean operand should be valid."""
        default_value = self._create_constant("Null", None)
        expected_type = Boolean()

        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, expected_type
        )

    def test_null_default_for_number_is_valid(self):
        """Null default for Number operand should be valid."""
        default_value = self._create_constant("Null", None)
        expected_type = Number()

        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, expected_type
        )

    def test_null_default_for_mixed_is_valid(self):
        """Null default for Mixed operand should be valid."""
        default_value = self._create_constant("Null", None)
        expected_type = Mixed()

        InputAnalyzer._InputAnalyzer__check_default_value(
            default_value, expected_type
        )
