"""Empty-input guards on the domain lookups (issue #332).

Both helpers are asked for the signatures/properties a single expression
mentions, so an empty request is normal; it must not reach the database.
"""

from dpmcore.dpm_xl.model_queries import (
    ItemCategoryQuery,
    PropertyCategoryQuery,
)


def test_no_items_needs_no_session():
    assert ItemCategoryQuery.get_item_domains(None, []) == {}


def test_no_properties_needs_no_session():
    assert PropertyCategoryQuery.get_property_domains(None, []) == {}
