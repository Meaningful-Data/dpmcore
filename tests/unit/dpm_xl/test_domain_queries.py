"""Unit tests for the domain-resolution queries.

``get_item_domains``/``get_property_domains`` back the DPM-XL
domain-membership warning, and ``SubCategoryQuery`` narrows it from a
domain to the items a particular column offers. The empty-input paths
must cost no query at all; everything else runs against an in-memory
SQLite database so the joins, the super-category expansion and the
release windows are covered without the fixture DB (issues #332, #359).

Seed model, three releases 1..3:

    Category  qTU    enumerated, composes qFI and qAI from release 1
    Category  qFI    enumerated, holds item 11 (``eba_qFI:qx1``)
    Category  qAI    enumerated, holds item 12 (``eba_qAI:qx2``)
    Category  qDT    not enumerated (a date), holds item 13
    qTU holds one item of its own, 10 (``eba_qTU:qx0``)

    Property 91 is typed on qTU, property 92 on qDT (so it has no
    domain at all) and property 93 on the plain category qFI.

    Table version 500 has column header 700 (property 91), whose
    header version names subcategory 60 — items 10 is *not* in it, 11
    is.  Cell 800 sits in that column.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.dpm_xl.model_queries import (
    ItemCategoryQuery,
    PropertyCategoryQuery,
    SubCategoryQuery,
)
from dpmcore.orm.base import Base
from dpmcore.orm.glossary import (
    Category,
    Item,
    ItemCategory,
    Property,
    PropertyCategory,
    SubCategory,
    SubCategoryItem,
    SubCategoryVersion,
    SupercategoryComposition,
)
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.rendering import (
    Cell,
    Header,
    HeaderVersion,
    Table,
    TableVersion,
    TableVersionCell,
    TableVersionHeader,
)

QTU, QFI, QAI, QDT = 1, 2, 3, 4


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
        Release(
            release_id=rid,
            code=f"4.{rid}",
            date=date(2024, rid, 1),
            status="Final",
            is_current=rid == 3,
        )
        for rid in (1, 2, 3)
    )
    s.add_all(
        Category(
            category_id=cid,
            code=code,
            name=code,
            is_enumerated=enumerated,
            is_active=True,
            is_external_ref_data=False,
            created_release_id=1,
        )
        for cid, code, enumerated in [
            (QTU, "qTU", True),
            (QFI, "qFI", True),
            (QAI, "qAI", True),
            (QDT, "qDT", False),
        ]
    )
    s.add_all(
        SupercategoryComposition(
            supercategory_id=QTU,
            category_id=member,
            start_release_id=1,
            end_release_id=None,
        )
        for member in (QFI, QAI)
    )
    s.add_all(
        Item(
            item_id=iid, name=f"Item {iid}", is_property=False, is_active=True
        )
        for iid in (10, 11, 12, 13)
    )
    s.add_all(
        [
            Item(item_id=91, name="Type", is_property=True, is_active=True),
            Item(item_id=92, name="Date", is_property=True, is_active=True),
            Item(item_id=93, name="Plain", is_property=True, is_active=True),
            Property(property_id=91, is_composite=False, is_metric=False),
            Property(property_id=92, is_composite=False, is_metric=False),
            Property(property_id=93, is_composite=False, is_metric=False),
        ]
    )
    s.flush()
    s.add_all(
        ItemCategory(
            item_id=iid,
            category_id=cid,
            code=code,
            signature=signature,
            is_default_item=iid == 10,
            start_release_id=1,
            end_release_id=None,
        )
        for iid, cid, code, signature in [
            (10, QTU, "qx0", "eba_qTU:qx0"),
            (11, QFI, "qx1", "eba_qFI:qx1"),
            (12, QAI, "qx2", "eba_qAI:qx2"),
            (13, QDT, "d1", "eba_qDT:d1"),
        ]
    )
    s.add_all(
        [
            PropertyCategory(
                property_id=91,
                category_id=QTU,
                start_release_id=1,
                end_release_id=None,
            ),
            PropertyCategory(
                property_id=92,
                category_id=QDT,
                start_release_id=1,
                end_release_id=None,
            ),
            PropertyCategory(
                property_id=93,
                category_id=QFI,
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )
    # A subcategory of qTU listing only item 11.
    s.add_all(
        [
            SubCategory(subcategory_id=6, category_id=QTU, code="new_qTU"),
            SubCategoryVersion(subcategory_vid=60, subcategory_id=6),
            SubCategoryItem(subcategory_vid=60, item_id=11, order=1),
        ]
    )
    # Table 500 / column header 700 / cell 800.
    s.add_all(
        [
            Table(table_id=50),
            TableVersion(table_vid=500, table_id=50, code="C_14.00"),
            Header(header_id=700, table_id=50, direction="Column"),
            HeaderVersion(
                header_vid=7000,
                header_id=700,
                code="0160",
                property_id=91,
                subcategory_vid=60,
            ),
            TableVersionHeader(
                table_vid=500, header_id=700, header_vid=7000, order=1
            ),
            Cell(cell_id=800, table_id=50, column_id=700),
            TableVersionCell(
                table_vid=500, cell_id=800, cell_code="{C_14.00, c0160}"
            ),
        ]
    )
    s.commit()
    yield s
    s.close()


class TestEmptyInput:
    def test_no_items_does_not_query(self):
        session = MagicMock()
        assert ItemCategoryQuery.get_item_domains(session, []) == {}
        session.query.assert_not_called()

    def test_no_properties_does_not_query(self):
        session = MagicMock()
        assert PropertyCategoryQuery.get_property_domains(session, []) == {}
        session.query.assert_not_called()

    def test_no_cells_does_not_query(self):
        session = MagicMock()
        assert SubCategoryQuery.get_cell_subcategory_vids(session, []) == {}
        session.query.assert_not_called()

    def test_no_subcategories_does_not_query(self):
        session = MagicMock()
        assert SubCategoryQuery.get_subcategory_signatures(session, []) == {}
        session.query.assert_not_called()


class TestItemDomains:
    def test_an_item_resolves_to_its_filing_category(self, session):
        domains = ItemCategoryQuery.get_item_domains(
            session, ["eba_qFI:qx1"], 3
        )

        assert domains == {"eba_qFI:qx1": {"qFI"}}

    def test_a_non_enumerated_category_is_not_a_domain(self, session):
        assert (
            ItemCategoryQuery.get_item_domains(session, ["eba_qDT:d1"], 3)
            == {}
        )

    def test_items_are_never_widened_to_a_super_category(self, session):
        """An item belongs where it is filed, not to what composes it."""
        domains = ItemCategoryQuery.get_item_domains(
            session, ["eba_qTU:qx0"], 3
        )

        assert domains == {"eba_qTU:qx0": {"qTU"}}


class TestPropertyDomains:
    def test_a_plain_property_has_no_members(self, session):
        domains = PropertyCategoryQuery.get_property_domains(session, [93], 3)[
            93
        ]

        assert domains.own == frozenset({"qFI"})
        assert domains.members == frozenset()
        assert domains.codes == frozenset({"qFI"})

    def test_a_super_category_reports_own_and_members_apart(self, session):
        domains = PropertyCategoryQuery.get_property_domains(session, [91], 3)[
            91
        ]

        assert domains.own == frozenset({"qTU"})
        assert domains.members == frozenset({"qFI", "qAI"})
        assert domains.codes == frozenset({"qTU", "qFI", "qAI"})

    def test_a_property_with_no_enumerated_category_is_absent(self, session):
        assert 92 not in PropertyCategoryQuery.get_property_domains(
            session, [92], 3
        )

    def test_the_composition_window_is_honoured(self, session):
        session.query(SupercategoryComposition).filter(
            SupercategoryComposition.category_id == QAI
        ).update({"start_release_id": 3})
        session.commit()

        domains = PropertyCategoryQuery.get_property_domains(session, [91], 1)[
            91
        ]

        assert domains.members == frozenset({"qFI"})

    def test_the_member_join_does_not_drop_plain_domains(self, session):
        """An outer join, so both kinds resolve in the same statement."""
        domains = PropertyCategoryQuery.get_property_domains(
            session, [91, 93], 3
        )

        assert set(domains) == {91, 93}


class TestCellSubcategories:
    def test_a_cells_column_header_names_its_subcategory(self, session):
        found = SubCategoryQuery.get_cell_subcategory_vids(
            session, [(500, 800)], 3
        )

        assert found == {(500, 800, 91): 60}

    def test_a_cell_of_another_table_version_is_not_returned(self, session):
        assert (
            SubCategoryQuery.get_cell_subcategory_vids(
                session, [(999, 800)], 3
            )
            == {}
        )

    def test_a_header_without_a_subcategory_is_skipped(self, session):
        session.query(HeaderVersion).filter(
            HeaderVersion.header_vid == 7000
        ).update({"subcategory_vid": None})
        session.commit()

        assert (
            SubCategoryQuery.get_cell_subcategory_vids(
                session, [(500, 800)], 3
            )
            == {}
        )

    def test_the_listed_items_are_returned(self, session):
        assert SubCategoryQuery.get_subcategory_signatures(
            session, [60], 3
        ) == {60: {"eba_qFI:qx1"}}

    def test_an_item_with_no_code_at_the_release_is_left_out(self, session):
        session.query(ItemCategory).filter(ItemCategory.item_id == 11).update(
            {"start_release_id": 3}
        )
        session.commit()

        assert (
            SubCategoryQuery.get_subcategory_signatures(session, [60], 1) == {}
        )
