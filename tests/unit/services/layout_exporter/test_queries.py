"""Tests for the layout exporter's member-code lookup.

``MemberCode`` is read from the ``ItemCategory`` row that files the item
under the dimension's domain. Two things make that lookup subtle:

* a *super-category* domain files almost none of its value set under
  itself, so the categories composing it have to be searched too (#359);
* one export spans many domains, and the same item can be filed in two
  of them, so the answer has to be per (item, domain) rather than per
  item.

Seed model — dimension ``ATY`` is typed on the super-category
``ASSET_TYPE``, which composes ``EQUITY_TYPE``; dimension ``OTH`` is
typed on the plain domain ``OTHER``. Item 700 is filed in
``EQUITY_TYPE`` (as ``SHARE``) and, with a different code, in ``OTHER``
(as ``OTHER_CODE``).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
from dpmcore.orm.glossary import (
    Category,
    Context,
    ContextComposition,
    Item,
    ItemCategory,
    Property,
    PropertyCategory,
    SupercategoryComposition,
)
from dpmcore.services.layout_exporter.queries import (
    _load_member_codes,
    load_categorisations,
)

ASSET_TYPE, EQUITY_TYPE, OTHER, PR = 60, 61, 62, 1
ATY, OTH = 50, 51
SHARE_ITEM = 700


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = Session(bind=engine)
    s.add_all(
        Category(
            category_id=cid,
            code=code,
            name=code,
            is_enumerated=True,
            is_active=True,
            is_external_ref_data=False,
        )
        for cid, code in [
            (PR, "_PR"),
            (ASSET_TYPE, "ASSET_TYPE"),
            (EQUITY_TYPE, "EQUITY_TYPE"),
            (OTHER, "OTHER"),
        ]
    )
    s.add(
        SupercategoryComposition(
            supercategory_id=ASSET_TYPE,
            category_id=EQUITY_TYPE,
            start_release_id=None,
            end_release_id=None,
        )
    )
    s.add_all(
        [
            Item(
                item_id=ATY,
                name="Asset type",
                is_property=True,
                is_active=True,
            ),
            Item(item_id=OTH, name="Other", is_property=True, is_active=True),
            Item(
                item_id=SHARE_ITEM,
                name="Share",
                is_property=False,
                is_active=True,
            ),
            Property(property_id=ATY, is_composite=False, is_metric=False),
            Property(property_id=OTH, is_composite=False, is_metric=False),
        ]
    )
    s.flush()
    s.add_all(
        ItemCategory(
            item_id=item_id,
            category_id=category_id,
            code=code,
            signature=f"{code}",
            is_default_item=False,
            start_release_id=start,
            end_release_id=None,
        )
        # ItemCategory's PK is (ItemID, StartReleaseID), so an item
        # in two categories at once needs two start releases.
        for item_id, category_id, code, start in [
            (ATY, PR, "ATY", 1),
            (OTH, PR, "OTH", 1),
            (SHARE_ITEM, EQUITY_TYPE, "SHARE", 1),
            (SHARE_ITEM, OTHER, "OTHER_CODE", 2),
        ]
    )
    s.add_all(
        [
            PropertyCategory(
                property_id=ATY,
                category_id=ASSET_TYPE,
                start_release_id=1,
                end_release_id=None,
            ),
            PropertyCategory(
                property_id=OTH,
                category_id=OTHER,
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )
    s.add_all(
        [
            Context(context_id=900, signature="ctx"),
            ContextComposition(
                context_id=900, property_id=ATY, item_id=SHARE_ITEM
            ),
            ContextComposition(
                context_id=900, property_id=OTH, item_id=SHARE_ITEM
            ),
        ]
    )
    s.commit()
    yield s
    s.close()


class TestMemberCodes:
    def test_a_super_category_member_resolves(self, session):
        """SHARE is filed in EQUITY_TYPE, never in ASSET_TYPE (#359)."""
        codes = _load_member_codes(session, {SHARE_ITEM}, {ASSET_TYPE})

        assert codes == {(SHARE_ITEM, ASSET_TYPE): "SHARE"}

    def test_a_plain_domain_resolves_from_its_own_category(self, session):
        codes = _load_member_codes(session, {SHARE_ITEM}, {OTHER})

        assert codes == {(SHARE_ITEM, OTHER): "OTHER_CODE"}

    def test_each_domain_gets_its_own_code(self, session):
        """A per-item key would hand one domain the other's code."""
        codes = _load_member_codes(session, {SHARE_ITEM}, {ASSET_TYPE, OTHER})

        assert codes == {
            (SHARE_ITEM, ASSET_TYPE): "SHARE",
            (SHARE_ITEM, OTHER): "OTHER_CODE",
        }

    def test_the_domains_own_category_wins_over_a_member(self, session):
        """Filed in both the super-category and one of its members.

        The domain's own category wins whatever its ID — EBA's ``qTU``
        (1111) outranks all four categories composing it (1007..1037),
        so ordering by ID alone would pick the wrong one.
        """
        session.add(
            ItemCategory(
                item_id=SHARE_ITEM,
                category_id=ASSET_TYPE,
                code="OWN",
                signature="OWN",
                is_default_item=False,
                start_release_id=3,
                end_release_id=None,
            )
        )
        session.commit()

        codes = _load_member_codes(session, {SHARE_ITEM}, {ASSET_TYPE})

        assert codes == {(SHARE_ITEM, ASSET_TYPE): "OWN"}

    def test_a_closed_item_category_row_is_ignored(self, session):
        session.query(ItemCategory).filter(
            ItemCategory.item_id == SHARE_ITEM,
            ItemCategory.category_id == EQUITY_TYPE,
        ).update({"end_release_id": 2})
        session.commit()

        assert _load_member_codes(session, {SHARE_ITEM}, {ASSET_TYPE}) == {}

    def test_no_items_costs_no_query(self):
        from unittest.mock import MagicMock

        session = MagicMock()

        assert _load_member_codes(session, set(), {ASSET_TYPE}) == {}
        session.query.assert_not_called()

    def test_no_domains_costs_no_query(self):
        from unittest.mock import MagicMock

        session = MagicMock()

        assert _load_member_codes(session, {SHARE_ITEM}, set()) == {}
        session.query.assert_not_called()


class TestCategorisations:
    def test_each_dimension_reports_its_own_member_code(self, session):
        members = load_categorisations(session, {900})

        by_dimension = {m.dimension_code: m for m in members[900]}
        assert by_dimension["ATY"].member_code == "SHARE"
        assert by_dimension["ATY"].domain_code == "ASSET_TYPE"
        assert by_dimension["OTH"].member_code == "OTHER_CODE"
        assert by_dimension["OTH"].domain_code == "OTHER"
