"""Integration tests for /api/v1/structure/category endpoints."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
from dpmcore.orm.glossary import Category, Item, ItemCategory
from dpmcore.orm.infrastructure import Concept, Organisation, Release
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


@pytest.fixture
def seeded_engine(engine):
    """Engine with categories, items, releases pre-seeded."""
    session = Session(bind=engine)

    # Organisation
    org = Organisation(
        org_id=1, name="European Banking Authority", acronym="EBA",
    )
    session.add(org)
    session.flush()

    # Concepts for releases and categories
    for guid in [
        "c-rel-1", "c-rel-2", "c-rel-3",
        "c-cat-1", "c-cat-2",
    ]:
        owner = 1 if guid != "c-rel-3" else None
        session.add(Concept(concept_guid=guid, owner_id=owner))
    session.flush()

    # Releases
    session.add_all([
        Release(
            release_id=1,
            code="3.3",
            date=date(2024, 1, 1),
            description="Release 3.3",
            status="Final",
            is_current=False,
            row_guid="c-rel-1",
            owner_id=1,
        ),
        Release(
            release_id=2,
            code="3.4",
            date=date(2024, 6, 1),
            description="Release 3.4",
            status="Final",
            is_current=True,
            row_guid="c-rel-2",
            owner_id=1,
        ),
        Release(
            release_id=3,
            code="3.5-draft",
            date=date(2024, 12, 1),
            description="Release 3.5 draft",
            status="Draft",
            is_current=False,
            row_guid="c-rel-3",
        ),
    ])
    session.flush()

    # Categories
    session.add_all([
        Category(
            category_id=1,
            code="MC",
            name="Main Category",
            description="The main category",
            is_enumerated=True,
            is_active=True,
            is_external_ref_data=False,
            ref_data_source=None,
            row_guid="c-cat-1",
            created_release=1,
            owner_id=1,
        ),
        Category(
            category_id=2,
            code="SC",
            name="Second Category",
            description="Another category",
            is_enumerated=False,
            is_active=True,
            is_external_ref_data=False,
            ref_data_source=None,
            row_guid="c-cat-2",
            created_release=2,
            owner_id=1,
        ),
    ])
    session.flush()

    # Items
    session.add_all([
        Item(
            item_id=10,
            name="Item Alpha",
            description="First item",
            is_property=False,
            is_active=True,
        ),
        Item(
            item_id=11,
            name="Item Beta",
            description="Second item",
            is_property=False,
            is_active=True,
        ),
        Item(
            item_id=12,
            name="Item Gamma",
            description="Third item (added in 3.4)",
            is_property=False,
            is_active=True,
        ),
    ])
    session.flush()

    # ItemCategory — release-versioned links
    session.add_all([
        # Item 10 in MC from release 1 onward (no end)
        ItemCategory(
            item_id=10,
            start_release_id=1,
            category_id=1,
            code="IC_001",
            is_default_item=False,
            signature="MC(IC_001)",
            end_release_id=None,
        ),
        # Item 11 in MC only for release 1 (ends at 1)
        ItemCategory(
            item_id=11,
            start_release_id=1,
            category_id=1,
            code="IC_002",
            is_default_item=False,
            signature="MC(IC_002)",
            end_release_id=1,
        ),
        # Item 12 in MC from release 2 onward
        ItemCategory(
            item_id=12,
            start_release_id=2,
            category_id=1,
            code="IC_003",
            is_default_item=True,
            signature="MC(IC_003)",
            end_release_id=None,
        ),
        # Item 10 also in SC from release 2 onward
        ItemCategory(
            item_id=10,
            start_release_id=2,
            category_id=2,
            code="SC_001",
            is_default_item=False,
            signature="SC(SC_001)",
            end_release_id=None,
        ),
    ])
    session.commit()
    session.close()
    return engine


@pytest.fixture
def client(seeded_engine):
    from starlette.testclient import TestClient

    app = create_app("sqlite:///:memory:", engine=seeded_engine)
    return TestClient(app)


@pytest.fixture
def empty_client(engine):
    from starlette.testclient import TestClient

    app = create_app("sqlite:///:memory:", engine=engine)
    return TestClient(app)


class TestListAllCategories:
    def test_default_returns_all_categories_latest(self, client):
        """Bare /structure/category defaults to release=~ (latest)."""
        resp = client.get("/api/v1/structure/category")
        assert resp.status_code == 200
        body = resp.json()
        assert "categories" in body["data"]
        cats = body["data"]["categories"]
        assert len(cats) == 2

    def test_all_releases(self, client):
        """Explicit release=* returns virtual versions for all cats."""
        resp = client.get("/api/v1/structure/category/*/*/*")
        assert resp.status_code == 200
        body = resp.json()
        cats = body["data"]["categories"]
        # MC has 2 versions (items change at 3.4), SC has 1 version
        assert len(cats) == 3
        assert body["meta"]["totalCount"] == 3

    def test_numeric_id_all_releases(self, client):
        """Numeric id with release=* returns all virtual versions."""
        resp = client.get("/api/v1/structure/category/*/1/*")
        assert resp.status_code == 200
        cats = resp.json()["data"]["categories"]
        # MC (id=1) has 2 versions with release=*
        assert len(cats) == 2
        assert all(c["id"] == 1 for c in cats)


class TestFilterByOwner:
    def test_filter_by_eba(self, client):
        resp = client.get("/api/v1/structure/category/EBA/*/*")
        assert resp.status_code == 200
        cats = resp.json()["data"]["categories"]
        # MC(2 versions) + SC(1 version) = 3 entries with release=*
        assert len(cats) == 3
        assert all(c["owner"] == "EBA" for c in cats)


class TestSingleCategory:
    def test_by_code(self, client):
        resp = client.get("/api/v1/structure/category/*/MC")
        assert resp.status_code == 200
        body = resp.json()
        # Always plural key
        assert "categories" in body["data"]
        cats = body["data"]["categories"]
        assert len(cats) == 1
        assert cats[0]["code"] == "MC"
        assert body["meta"]["totalCount"] == 1

    def test_by_numeric_id(self, client):
        """Numeric value matches category_id."""
        resp = client.get("/api/v1/structure/category/*/1")
        assert resp.status_code == 200
        cats = resp.json()["data"]["categories"]
        assert len(cats) == 1
        assert cats[0]["id"] == 1
        assert cats[0]["code"] == "MC"

    def test_by_owner_and_code(self, client):
        resp = client.get("/api/v1/structure/category/EBA/MC")
        assert resp.status_code == 200
        cats = resp.json()["data"]["categories"]
        assert len(cats) == 1
        assert cats[0]["code"] == "MC"

    def test_nonexistent_code_returns_204(self, client):
        resp = client.get("/api/v1/structure/category/*/ZZ")
        assert resp.status_code == 204


class TestReleaseFiltering:
    def test_items_for_release_3_3(self, client):
        """Release 3.3 → MC has items 10, 11 (both active at rel 1)."""
        resp = client.get(
            "/api/v1/structure/category/*/MC/3.3",
        )
        assert resp.status_code == 200
        cat = resp.json()["data"]["categories"][0]
        item_ids = [i["id"] for i in cat["items"]]
        assert 10 in item_ids
        assert 11 in item_ids
        assert 12 not in item_ids
        assert cat["release"] == "3.3"

    def test_items_for_release_3_4(self, client):
        """Release 3.4 → MC has items 10, 12 (11 ended at rel 1)."""
        resp = client.get(
            "/api/v1/structure/category/*/MC/3.4",
        )
        assert resp.status_code == 200
        cat = resp.json()["data"]["categories"][0]
        item_ids = [i["id"] for i in cat["items"]]
        assert 10 in item_ids
        assert 12 in item_ids
        assert 11 not in item_ids
        assert cat["release"] == "3.4"

    def test_latest_stable_release(self, client):
        """release=+ → latest stable (3.4)."""
        resp = client.get(
            "/api/v1/structure/category/*/MC/+",
        )
        assert resp.status_code == 200
        cat = resp.json()["data"]["categories"][0]
        assert cat["release"] == "3.4"

    def test_latest_any_release(self, client):
        """release=~ → version active at latest (3.5-draft) was created at 3.4."""
        resp = client.get(
            "/api/v1/structure/category/*/MC/~",
        )
        assert resp.status_code == 200
        cat = resp.json()["data"]["categories"][0]
        assert cat["release"] == "3.4"


class TestDetailParameter:
    def test_allstubs_no_items(self, client):
        resp = client.get(
            "/api/v1/structure/category?detail=allstubs",
        )
        assert resp.status_code == 200
        cats = resp.json()["data"]["categories"]
        for cat in cats:
            assert "items" not in cat
            assert "id" in cat
            assert "code" in cat
            assert "owner" in cat

    def test_full_has_items(self, client):
        resp = client.get("/api/v1/structure/category")
        assert resp.status_code == 200
        cats = resp.json()["data"]["categories"]
        for cat in cats:
            assert "items" in cat


class TestItemFields:
    def test_item_fields_present(self, client):
        resp = client.get(
            "/api/v1/structure/category/*/MC/3.4",
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["categories"][0]["items"]
        assert len(items) > 0
        item = items[0]
        assert "id" in item
        assert "name" in item
        assert "description" in item
        assert "isActive" in item
        assert "code" in item
        assert "isDefaultItem" in item
        assert "signature" in item
        assert "startReleaseId" in item
        assert "endReleaseId" in item
        # isProperty should NOT be in the output
        assert "isProperty" not in item


class TestEmptyResults:
    def test_empty_database_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/category")
        assert resp.status_code == 204
        assert resp.content == b""

    def test_nonexistent_owner_returns_204(self, client):
        resp = client.get(
            "/api/v1/structure/category/UNKNOWN/*/*",
        )
        assert resp.status_code == 204


class TestReferencesAll:
    def test_collection_includes_organisations(self, client):
        resp = client.get(
            "/api/v1/structure/category/*/*/*?references=all",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "organisations" in body["data"]
        orgs = body["data"]["organisations"]
        assert len(orgs) >= 1
        assert orgs[0]["acronym"] == "EBA"

    def test_default_omits_organisations(self, client):
        resp = client.get("/api/v1/structure/category/*/*/*")
        assert resp.status_code == 200
        assert "organisations" not in resp.json()["data"]


class TestVirtualVersioning:
    def test_mc_has_two_versions(self, client):
        """MC changes between 3.3 and 3.4 → 2 virtual versions."""
        resp = client.get("/api/v1/structure/category/*/MC/*")
        assert resp.status_code == 200
        cats = resp.json()["data"]["categories"]
        assert len(cats) == 2
        releases = [c["release"] for c in cats]
        assert releases == ["3.3", "3.4"]

    def test_sc_has_one_version(self, client):
        """SC is unchanged after creation → 1 virtual version."""
        resp = client.get("/api/v1/structure/category/*/SC/*")
        assert resp.status_code == 200
        cats = resp.json()["data"]["categories"]
        assert len(cats) == 1
        assert cats[0]["release"] == "3.4"

    def test_category_created_later_absent_at_earlier_release(
        self, client,
    ):
        """SC created at release 2 (3.4) has no version at 3.3."""
        resp = client.get(
            "/api/v1/structure/category/*/SC/3.3",
        )
        assert resp.status_code == 204

    def test_total_versions_all_categories(self, client):
        """Total virtual versions: MC(2) + SC(1) = 3."""
        resp = client.get("/api/v1/structure/category/*/*/*")
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["totalCount"] == 3
        assert len(body["data"]["categories"]) == 3
