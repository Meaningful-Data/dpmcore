"""
Tests for default value type checking in semantic analyzer.

Tests that the semantic analyzer correctly validates that default value types
are compatible with the operand's expected data type.
"""

import pytest

from py_dpm.dpm_xl.ast.nodes import Constant
from py_dpm.dpm_xl.semantic_analyzer import InputAnalyzer
from py_dpm.dpm_xl.types.scalar import (
    Boolean,
    Integer,
    Item,
    Number,
    String,
)
from py_dpm.exceptions.exceptions import SemanticError


class TestCheckDefaultValue:
    """Test cases for __check_default_value static method."""

    @staticmethod
    def _create_constant(type_code: str, value) -> Constant:
        """Helper to create a Constant node for testing."""
        return Constant(type_=type_code, value=value)

    def test_string_default_for_boolean_raises_error(self):
        """String default for Boolean operand should raise SemanticError 3-6."""
        default_value = self._create_constant("String", "")
        expected_type = Boolean()

        with pytest.raises(SemanticError) as exc_info:
            InputAnalyzer._InputAnalyzer__check_default_value(
                default_value, expected_type
            )

        assert "Invalid default type" in str(exc_info.value)
        assert "String" in str(exc_info.value)
        assert "Boolean" in str(exc_info.value)

    def test_string_default_for_number_raises_error(self):
        """String default for Number operand should raise SemanticError 3-6."""
        default_value = self._create_constant("String", "")
        expected_type = Number()

        with pytest.raises(SemanticError) as exc_info:
            InputAnalyzer._InputAnalyzer__check_default_value(
                default_value, expected_type
            )

        assert "Invalid default type" in str(exc_info.value)
        assert "String" in str(exc_info.value)
        assert "Number" in str(exc_info.value)

    def test_string_default_for_integer_raises_error(self):
        """String default for Integer operand should raise SemanticError 3-6."""
        default_value = self._create_constant("String", "")
        expected_type = Integer()

        with pytest.raises(SemanticError) as exc_info:
            InputAnalyzer._InputAnalyzer__check_default_value(
                default_value, expected_type
            )

        assert "Invalid default type" in str(exc_info.value)
        assert "String" in str(exc_info.value)
        assert "Integer" in str(exc_info.value)

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

    def test_string_default_for_item_raises_error(self):
        """String default for Item operand should raise SemanticError 3-6."""
        default_value = self._create_constant("String", "")
        expected_type = Item()

        with pytest.raises(SemanticError) as exc_info:
            InputAnalyzer._InputAnalyzer__check_default_value(
                default_value, expected_type
            )

        assert "Invalid default type" in str(exc_info.value)
        assert "String" in str(exc_info.value)
        assert "Item" in str(exc_info.value)

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
