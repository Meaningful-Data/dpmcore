"""Empty-input guards on the domain lookups (issue #332).

Both helpers are asked for the signatures/properties a single expression
mentions, so an empty request is normal; it must not reach the database.
"""

from unittest.mock import MagicMock

from dpmcore.dpm_xl.model_queries import (
    ItemCategoryQuery,
    PropertyCategoryQuery,
)


def test_no_items_does_not_query():
    session = MagicMock()
    assert ItemCategoryQuery.get_item_domains(session, []) == {}
    session.query.assert_not_called()


def test_no_properties_does_not_query():
    session = MagicMock()
    assert PropertyCategoryQuery.get_property_domains(session, []) == {}
    session.query.assert_not_called()
