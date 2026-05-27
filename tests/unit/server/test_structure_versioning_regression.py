"""Regression tests for release-aware versioning in the structure API.

Covers two correctness fixes:

* Release ordering must use the semver-parsed ``sort_order`` of
  ``Release.code``, NOT the opaque ``release_id`` FK (non-monotonic
  from DPM 4.2.1) nor ``date``. A chronological backport published
  with a high id / late date must still sort inside its semver
  lineage. (``_get_all_releases`` / ``_window_alive`` /
  ``_version_at_release``.)
* At ``release=*`` a property's enumeration window is keyed per
  ItemCategory *version*, not per ``property_id`` — so two versions of
  the same property each surface the enumeration valid at their own
  release. (``query_properties``.)
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
from dpmcore.orm.glossary import (
    Category,
    Item,
    ItemCategory,
    Property,
    PropertyCategory,
)
from dpmcore.orm.infrastructure import DataType, Organisation, Release
from dpmcore.server.app import create_app


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


# ------------------------------------------------------------------ #
# Fixture 1 — non-monotonic release ids (backport scenario)
# ------------------------------------------------------------------ #
#
# Three releases whose release_id AND date order disagree with semver:
#   code 4.0 -> release_id 100, date 2024-01
#   code 4.2 -> release_id 101, date 2024-06
#   code 4.1 -> release_id 200, date 2024-09   (a backport: highest id
#                                                and latest date, but
#                                                semver-wise between).
#
# Category MC (created at 4.0) with two items:
#   A: alive from 4.0 onward.
#   B: added at 4.1 (release_id 200) onward.
#
# Correct (sort_order) walk => versions {A} @4.0, {A,B} @4.1, and the
# version active at 4.2 is {A,B}. A release_id/date walk would break
# early and report {A} at 4.2.
# ------------------------------------------------------------------ #


@pytest.fixture
def backport_engine(engine):
    s = Session(bind=engine)
    s.add(
        Organisation(
            org_id=1, name="European Banking Authority", acronym="EBA"
        )
    )
    s.flush()

    s.add_all(
        [
            Release(
                release_id=100,
                code="4.0",
                date=date(2024, 1, 1),
                status="Final",
                is_current=False,
            ),
            Release(
                release_id=101,
                code="4.2",
                date=date(2024, 6, 1),
                status="Final",
                is_current=True,
            ),
            Release(
                release_id=200,
                code="4.1",
                date=date(2024, 9, 1),
                status="Final",
                is_current=False,
            ),
        ]
    )
    s.flush()

    s.add(
        Category(
            category_id=1,
            code="MC",
            name="Main Category",
            description="",
            is_enumerated=True,
            is_active=True,
            is_external_ref_data=False,
            ref_data_source=None,
            row_guid=None,
            created_release=100,
            owner_id=1,
        )
    )
    s.flush()

    s.add_all(
        [
            Item(
                item_id=10,
                name="Item Alpha",
                description="",
                is_property=False,
                is_active=True,
            ),
            Item(
                item_id=11,
                name="Item Beta",
                description="",
                is_property=False,
                is_active=True,
            ),
        ]
    )
    s.flush()

    s.add_all(
        [
            ItemCategory(
                item_id=10,
                start_release_id=100,  # 4.0 onward
                category_id=1,
                code="A",
                is_default_item=False,
                signature="MC(A)",
                end_release_id=None,
            ),
            ItemCategory(
                item_id=11,
                start_release_id=200,  # 4.1 (backport id) onward
                category_id=1,
                code="B",
                is_default_item=False,
                signature="MC(B)",
                end_release_id=None,
            ),
        ]
    )
    s.commit()
    s.close()
    return engine


@pytest.fixture
def backport_client(backport_engine):
    from starlette.testclient import TestClient

    app = create_app("sqlite:///:memory:", engine=backport_engine)
    return TestClient(app)


class TestSortOrderNotReleaseId:
    def test_versions_listed_in_semver_order(self, backport_client):
        resp = backport_client.get("/api/v1/structure/category/*/1/*")
        assert resp.status_code == 200
        cats = resp.json()["data"]["categories"]
        releases = [c["release"] for c in cats]
        # Semver order, not release_id (100,101,200) order.
        assert releases == ["4.0", "4.1"]

    def test_item_added_by_backport_visible_at_later_release(
        self, backport_client
    ):
        """B (added at 4.1) must be present at 4.2.

        A release_id walk breaks at the 4.1 backport (release_id 200 >
        4.2's release_id 101) and would omit B here.
        """
        resp = backport_client.get("/api/v1/structure/category/*/1/4.2")
        assert resp.status_code == 200
        cat = resp.json()["data"]["categories"][0]
        item_ids = {i["id"] for i in cat["items"]}
        assert item_ids == {10, 11}

    def test_earliest_release_excludes_later_item(self, backport_client):
        resp = backport_client.get("/api/v1/structure/category/*/1/4.0")
        assert resp.status_code == 200
        cat = resp.json()["data"]["categories"][0]
        item_ids = {i["id"] for i in cat["items"]}
        assert item_ids == {10}

    def test_latest_resolves_to_highest_semver(self, backport_client):
        resp = backport_client.get("/api/v1/structure/category/*/1/~")
        assert resp.status_code == 200
        cat = resp.json()["data"]["categories"][0]
        # Latest semver is 4.2; active version there was created at 4.1.
        assert cat["release"] == "4.1"
        assert {i["id"] for i in cat["items"]} == {10, 11}


# ------------------------------------------------------------------ #
# Fixture 2 — enumerated property with two versions
# ------------------------------------------------------------------ #
#
# Property 100 has two `_PR` ItemCategory versions (ENUMP @4.0,
# ENUMP2 @4.1) and links to enumerated category ECAT. ECAT's members
# change across releases:
#   XC: alive 4.0 only      YC: alive throughout      ZC: 4.1 onward
# so the enumeration is {XC,YC} @4.0 and {YC,ZC} @4.1. At release=*
# each property version must carry its own release's enumeration.
# ------------------------------------------------------------------ #


@pytest.fixture
def enum_versions_engine(engine):
    s = Session(bind=engine)
    s.add(
        Organisation(
            org_id=1, name="European Banking Authority", acronym="EBA"
        )
    )
    s.flush()

    s.add_all(
        [
            Release(
                release_id=1,
                code="4.0",
                date=date(2024, 1, 1),
                status="Final",
                is_current=False,
            ),
            Release(
                release_id=2,
                code="4.1",
                date=date(2024, 6, 1),
                status="Final",
                is_current=True,
            ),
        ]
    )
    s.flush()

    s.add(
        DataType(
            data_type_id=2,
            code="Enumeration",
            name="Enumeration",
            is_active=True,
        )
    )
    s.flush()

    s.add_all(
        [
            Category(
                category_id=1,
                code="_PR",
                name="Property",
                description="",
                is_enumerated=False,
                is_active=True,
                is_external_ref_data=False,
                created_release=1,
                owner_id=1,
            ),
            Category(
                category_id=10,
                code="ECAT",
                name="Enum Category",
                description="",
                is_enumerated=True,
                is_active=True,
                is_external_ref_data=False,
                created_release=1,
                owner_id=1,
            ),
        ]
    )
    s.flush()

    s.add_all(
        [
            Item(
                item_id=100,
                name="Enumerated Property",
                description="",
                is_property=True,
                is_active=True,
                owner_id=1,
            ),
            Item(item_id=101, name="X", is_property=False, is_active=True),
            Item(item_id=102, name="Y", is_property=False, is_active=True),
            Item(item_id=103, name="Z", is_property=False, is_active=True),
        ]
    )
    s.flush()

    s.add(
        Property(
            property_id=100,
            is_composite=False,
            is_metric=False,
            data_type_id=2,
            owner_id=1,
        )
    )
    s.flush()

    s.add_all(
        [
            # Two `_PR` versions of the property.
            ItemCategory(
                item_id=100,
                start_release_id=1,
                category_id=1,
                code="ENUMP",
                is_default_item=False,
                signature="_PR(ENUMP)",
                end_release_id=2,
            ),
            ItemCategory(
                item_id=100,
                start_release_id=2,
                category_id=1,
                code="ENUMP2",
                is_default_item=False,
                signature="_PR(ENUMP2)",
                end_release_id=None,
            ),
            # Enumeration members of ECAT (exclusive end semantics).
            ItemCategory(
                item_id=101,
                start_release_id=1,
                category_id=10,
                code="XC",
                is_default_item=False,
                signature="ECAT(XC)",
                end_release_id=2,  # alive 4.0 only
            ),
            ItemCategory(
                item_id=102,
                start_release_id=1,
                category_id=10,
                code="YC",
                is_default_item=False,
                signature="ECAT(YC)",
                end_release_id=None,  # alive throughout
            ),
            ItemCategory(
                item_id=103,
                start_release_id=2,
                category_id=10,
                code="ZC",
                is_default_item=False,
                signature="ECAT(ZC)",
                end_release_id=None,  # 4.1 onward
            ),
        ]
    )
    s.flush()

    s.add(
        PropertyCategory(
            property_id=100,
            start_release_id=1,
            category_id=10,
            end_release_id=None,
        )
    )
    s.commit()
    s.close()
    return engine


@pytest.fixture
def enum_versions_client(enum_versions_engine):
    from starlette.testclient import TestClient

    app = create_app("sqlite:///:memory:", engine=enum_versions_engine)
    return TestClient(app)


class TestPropertyEnumerationPerVersion:
    def test_each_version_carries_its_own_enumeration(
        self, enum_versions_client
    ):
        resp = enum_versions_client.get("/api/v1/structure/property/*/100/*")
        assert resp.status_code == 200
        props = resp.json()["data"]["properties"]
        by_release = {p["release"]: p for p in props}
        assert set(by_release) == {"4.0", "4.1"}

        codes_40 = {
            i["code"] for i in by_release["4.0"]["enumeration"]["items"]
        }
        codes_41 = {
            i["code"] for i in by_release["4.1"]["enumeration"]["items"]
        }

        # Per-version windows — NOT both pinned to the last version's
        # release (which would make 4.0 wrongly show {YC, ZC}).
        assert codes_40 == {"XC", "YC"}
        assert codes_41 == {"YC", "ZC"}
