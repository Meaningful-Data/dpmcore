"""Integration tests for /api/v1/structure/property endpoints."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, event
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
from dpmcore.orm.infrastructure import (
    Concept,
    DataType,
    Organisation,
    Release,
)
from dpmcore.server.app import create_app

# ------------------------------------------------------------------ #
# Seed model
# ------------------------------------------------------------------ #
#
# Releases 4.0 (Final) and 4.1 (Final).
#
# Meta-category `_PR` registers properties; the property's code,
# signature, and release window come from its `_PR` ItemCategory row.
#
# Three properties, all owned by EBA:
#   - 51 "BAS" (Basis) — DataType=String, no PropertyCategory link
#         (not enumerated). Has two ItemCategory rows across releases:
#         "BAS" at 4.0, "BAS2" at 4.1 (re-coded between releases) —
#         exercises the per-version code change.
#   - 52 "ASSET" (Asset type) — DataType=Enumeration, PropertyCategory
#         links to enumerated Category ASSET_TYPE. Items LOAN (alive
#         at 4.0 only) and BOND (alive throughout).
#   - 53 "PARTY" — DataType=String, no enumeration.
# ------------------------------------------------------------------ #


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
    s = Session(bind=engine)

    s.add(
        Organisation(
            org_id=1, name="European Banking Authority", acronym="EBA"
        )
    )
    s.flush()

    for guid in [
        "c-rel-1",
        "c-rel-2",
        "c-prop-51",
        "c-prop-52",
        "c-prop-53",
    ]:
        s.add(Concept(concept_guid=guid, owner_id=1))
    s.flush()

    s.add_all(
        [
            Release(
                release_id=1,
                code="4.0",
                date=date(2024, 1, 1),
                status="Final",
                is_current=False,
                row_guid="c-rel-1",
                owner_id=1,
            ),
            Release(
                release_id=2,
                code="4.1",
                date=date(2024, 6, 1),
                status="Final",
                is_current=True,
                row_guid="c-rel-2",
                owner_id=1,
            ),
        ]
    )
    s.flush()

    s.add_all(
        [
            DataType(
                data_type_id=1, code="String", name="String", is_active=True
            ),
            DataType(
                data_type_id=2,
                code="Enumeration",
                name="Enumeration",
                is_active=True,
            ),
        ]
    )
    s.flush()

    # Meta-category and enumerated category.
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
                category_id=60,
                code="ASSET_TYPE",
                name="Asset type",
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

    # Property items (subtype of Item).
    s.add_all(
        [
            Item(
                item_id=51,
                name="Basis",
                description="Accounting basis",
                is_property=True,
                is_active=True,
                row_guid="c-prop-51",
                owner_id=1,
            ),
            Item(
                item_id=52,
                name="Asset type",
                description="Type of asset",
                is_property=True,
                is_active=True,
                row_guid="c-prop-52",
                owner_id=1,
            ),
            Item(
                item_id=53,
                name="Party type",
                description="Type of counterparty",
                is_property=True,
                is_active=True,
                row_guid="c-prop-53",
                owner_id=1,
            ),
            # Enumeration members for property 52.
            Item(item_id=700, name="Loan", is_property=False, is_active=True),
            Item(item_id=701, name="Bond", is_property=False, is_active=True),
        ]
    )
    s.flush()

    s.add_all(
        [
            Property(
                property_id=51,
                is_composite=False,
                is_metric=False,
                data_type_id=1,
                owner_id=1,
            ),
            Property(
                property_id=52,
                is_composite=False,
                is_metric=False,
                data_type_id=2,
                owner_id=1,
            ),
            Property(
                property_id=53,
                is_composite=False,
                is_metric=False,
                data_type_id=1,
                owner_id=1,
            ),
        ]
    )
    s.flush()

    # ItemCategory rows — each property in the `_PR` meta-category.
    # Property 51 re-coded between releases.
    s.add_all(
        [
            ItemCategory(
                item_id=51,
                start_release_id=1,
                category_id=1,
                code="BAS",
                is_default_item=False,
                signature="_PR(BAS)",
                end_release_id=2,
            ),
            ItemCategory(
                item_id=51,
                start_release_id=2,
                category_id=1,
                code="BAS2",
                is_default_item=False,
                signature="_PR(BAS2)",
                end_release_id=None,
            ),
            ItemCategory(
                item_id=52,
                start_release_id=1,
                category_id=1,
                code="ASSET",
                is_default_item=False,
                signature="_PR(ASSET)",
                end_release_id=None,
            ),
            ItemCategory(
                item_id=53,
                start_release_id=1,
                category_id=1,
                code="PARTY",
                is_default_item=False,
                signature="_PR(PARTY)",
                end_release_id=None,
            ),
            # Enumeration members in ASSET_TYPE.
            ItemCategory(
                item_id=700,
                start_release_id=1,
                category_id=60,
                code="LOAN",
                is_default_item=False,
                signature="ASSET_TYPE(LOAN)",
                end_release_id=2,
            ),
            ItemCategory(
                item_id=701,
                start_release_id=1,
                category_id=60,
                code="BOND",
                is_default_item=False,
                signature="ASSET_TYPE(BOND)",
                end_release_id=None,
            ),
        ]
    )
    s.flush()

    # PropertyCategory — only property 52 is enumerated.
    s.add(
        PropertyCategory(
            property_id=52,
            start_release_id=1,
            category_id=60,
            end_release_id=None,
        )
    )
    s.commit()
    s.close()
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


def _count_queries(engine):
    class _Counter:
        def __init__(self):
            self.count = 0

        def __enter__(self):
            def _l(c, cur, stmt, p, ctx, m):
                self.count += 1

            self._l = _l
            event.listen(engine, "before_cursor_execute", _l)
            return self

        def __exit__(self, *exc):
            event.remove(engine, "before_cursor_execute", self._l)
            return False

    return _Counter()


# ------------------------------------------------------------------ #
# Tests — default response
# ------------------------------------------------------------------ #


class TestSingleProperty:
    def test_at_literal_release(self, client):
        resp = client.get("/api/v1/structure/property/EBA/BAS/4.0")
        assert resp.status_code == 200
        body = resp.json()
        props = body["data"]["properties"]
        assert len(props) == 1
        p = props[0]
        assert p["code"] == "BAS"
        assert p["signature"] == "_PR(BAS)"
        assert p["label"] == "Basis"
        assert p["release"] == "4.0"
        assert p["dataType"]["code"] == "String"
        assert p["definingCategory"]["code"] == "_PR"
        assert p["isEnumerated"] is False

    def test_code_change_across_releases(self, client):
        # BAS at 4.0, BAS2 at 4.1.
        r0 = client.get("/api/v1/structure/property/EBA/BAS/4.0")
        r1 = client.get("/api/v1/structure/property/EBA/BAS2/4.1")
        assert r0.json()["data"]["properties"][0]["code"] == "BAS"
        assert r1.json()["data"]["properties"][0]["code"] == "BAS2"
        # The id (item_id=51) is the same across versions.
        assert (
            r0.json()["data"]["properties"][0]["id"]
            == r1.json()["data"]["properties"][0]["id"]
            == 51
        )

    def test_old_code_gone_at_later_release(self, client):
        # BAS was alive at 4.0 only; at 4.1 it's BAS2.
        resp = client.get("/api/v1/structure/property/EBA/BAS/4.1")
        assert resp.status_code == 204

    def test_latest_returns_newer_code(self, client):
        resp = client.get("/api/v1/structure/property/EBA/BAS2/~")
        p = resp.json()["data"]["properties"][0]
        assert p["code"] == "BAS2"
        assert p["release"] == "4.1"

    def test_nonexistent_code_204(self, client):
        resp = client.get("/api/v1/structure/property/EBA/NOPE/4.0")
        assert resp.status_code == 204


class TestEnumeration:
    def test_enumerated_property_carries_enumeration(self, client):
        resp = client.get("/api/v1/structure/property/EBA/ASSET/4.0")
        p = resp.json()["data"]["properties"][0]
        assert p["isEnumerated"] is True
        enum = p["enumeration"]
        assert enum["categoryCode"] == "ASSET_TYPE"
        codes = {i["code"] for i in enum["items"]}
        # LOAN ends at 4.1 → present at 4.0. BOND alive throughout.
        assert codes == {"LOAN", "BOND"}

    def test_enumeration_items_shrink_at_4_1(self, client):
        resp = client.get("/api/v1/structure/property/EBA/ASSET/4.1")
        p = resp.json()["data"]["properties"][0]
        codes = {i["code"] for i in p["enumeration"]["items"]}
        assert codes == {"BOND"}

    def test_non_enumerated_property(self, client):
        resp = client.get("/api/v1/structure/property/EBA/PARTY/4.0")
        p = resp.json()["data"]["properties"][0]
        assert p["isEnumerated"] is False
        assert p["enumeration"] is None


class TestAllProperties:
    def test_wildcard_id_lists_all(self, client):
        resp = client.get("/api/v1/structure/property/EBA/*/4.0")
        codes = {p["code"] for p in resp.json()["data"]["properties"]}
        assert codes == {"BAS", "ASSET", "PARTY"}

    def test_release_wildcard_gives_both_BAS_versions(self, client):
        resp = client.get("/api/v1/structure/property/EBA/BAS,BAS2/*")
        codes = {p["code"] for p in resp.json()["data"]["properties"]}
        assert codes == {"BAS", "BAS2"}


class TestAllstubs:
    def test_strips_subtrees(self, client):
        resp = client.get(
            "/api/v1/structure/property/EBA/BAS/4.0?detail=allstubs"
        )
        p = resp.json()["data"]["properties"][0]
        for key in (
            "dataType",
            "definingCategory",
            "isEnumerated",
            "enumeration",
            "isComposite",
            "isMetric",
        ):
            assert key not in p
        for key in (
            "id",
            "code",
            "signature",
            "label",
            "owner",
            "release",
        ):
            assert key in p


class TestReferences:
    def test_all_includes_organisations(self, client):
        resp = client.get(
            "/api/v1/structure/property/EBA/BAS/4.0?references=all"
        )
        assert "organisations" in resp.json()["data"]

    def test_children_is_silent_noop(self, client):
        resp = client.get(
            "/api/v1/structure/property/EBA/BAS/4.0?references=children"
        )
        p = resp.json()["data"]["properties"][0]
        for key in ("tables", "modules", "children"):
            assert key not in p


class TestEmptyDatabase:
    def test_empty_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/property/EBA/BAS/4.0")
        assert resp.status_code == 204


# ------------------------------------------------------------------ #
# Performance — query budget
# ------------------------------------------------------------------ #


class TestQueryBudget:
    def test_query_count_bounded(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get("/api/v1/structure/property/EBA/*/4.0")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]["properties"]) == 3
        # Budget breakdown:
        #   3 release-resolution queries (filter_by_release internals);
        #   1 count, 1 main paginated query;
        #   2 enumeration loads (PropertyCategory+Category, then
        #     ItemCategory+Item — only when at least one property is
        #     enumerated);
        #   1 owner lookup.
        # ≤12 leaves headroom; budget is independent of property count.
        assert counter.count <= 12, (
            f"property path issued {counter.count} queries — "
            f"likely an N+1 regression."
        )
