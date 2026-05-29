"""Tests for binary_implicit_type_promotion in promotion.py."""

from dpmcore.dpm_xl.types.promotion import binary_implicit_type_promotion
from dpmcore.dpm_xl.types.scalar import Boolean, Item, Number, String


class TestBinaryImplicitTypePromotion:
    def test_number_eq_item_with_boolean_return_type_is_valid(self):
        """Number = Item must be accepted when return_type=Boolean"""
        result = binary_implicit_type_promotion(
            Number(), Item(), return_type=Boolean()
        )
        assert isinstance(result, Boolean)

    def test_item_eq_number_with_boolean_return_type_is_valid(self):
        """Item = Number must be accepted when return_type=Boolean (symmetric)."""
        result = binary_implicit_type_promotion(
            Item(), Number(), return_type=Boolean()
        )
        assert isinstance(result, Boolean)

    def test_compatible_types_with_return_type_still_returns_return_type(self):
        """When types are compatible and return_type given, return_type is returned."""
        result = binary_implicit_type_promotion(
            Number(), String(), return_type=Boolean()
        )
        assert isinstance(result, Boolean)

    def test_compatible_types_without_return_type_resolves_normally(self):
        """Without return_type, compatible types resolve via normal promotion."""
        result = binary_implicit_type_promotion(Number(), String())
        assert isinstance(result, (Number, String))
