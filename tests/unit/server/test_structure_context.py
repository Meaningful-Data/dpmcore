"""Integration tests for /api/v1/structure/context endpoints."""

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
    Context,
    ContextComposition,
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
# Three releases (4.0, 4.1, 4.2). Two contexts:
#
#   - context 100: composes property 51 (Accounting Standard) with
#     item 700 (IFRS) AND property 52 (Geographical Area) with
#     item 701 (EU).
#
#     Property 51 has its `_PR` code "AS" at 4.0/4.1 and is recoded
#     to "ACC" at 4.2 → first version transition.
#     Item 700's code in ASSET_TYPE is "IFRS" at 4.0 only and
#     "IFRS_NEW" at 4.1 onwards → second version transition.
#     So context 100 has 3 virtual versions across 3 releases.
#
#   - context 200: composes only property 53 with no item (item_id
#     null) → fingerprint is one (propertyCode, None) pair. No
#     code changes for property 53 → exactly one virtual version.
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
        "c-rel-3",
        "c-prop-51",
        "c-prop-52",
        "c-prop-53",
        "c-ctx-100",
        "c-ctx-200",
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
                row_guid="c-rel-1",
                owner_id=1,
            ),
            Release(
                release_id=2,
                code="4.1",
                date=date(2024, 6, 1),
                status="Final",
                row_guid="c-rel-2",
                owner_id=1,
            ),
            Release(
                release_id=3,
                code="4.2",
                date=date(2024, 12, 1),
                status="Final",
                row_guid="c-rel-3",
                owner_id=1,
            ),
        ]
    )
    s.flush()

    s.add(
        DataType(data_type_id=1, code="String", name="String", is_active=True)
    )
    s.flush()

    # Meta-category for properties + two enumerated domains.
    s.add_all(
        [
            Category(
                category_id=1,
                code="_PR",
                name="Property",
                is_enumerated=False,
                is_active=True,
                is_external_ref_data=False,
                created_release=1,
                owner_id=1,
            ),
            Category(
                category_id=60,
                code="ACC_STD",
                name="Accounting standard",
                is_enumerated=True,
                is_active=True,
                is_external_ref_data=False,
                created_release=1,
                owner_id=1,
            ),
            Category(
                category_id=61,
                code="GEO",
                name="Geographical area",
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
                name="Accounting Standard",
                is_property=True,
                is_active=True,
                row_guid="c-prop-51",
                owner_id=1,
            ),
            Item(
                item_id=52,
                name="Geographical Area",
                is_property=True,
                is_active=True,
                row_guid="c-prop-52",
                owner_id=1,
            ),
            Item(
                item_id=53,
                name="Reporting Frequency",
                is_property=True,
                is_active=True,
                row_guid="c-prop-53",
                owner_id=1,
            ),
            # Items for the domain categories.
            Item(item_id=700, name="IFRS", is_property=False, is_active=True),
            Item(item_id=701, name="EU", is_property=False, is_active=True),
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
                data_type_id=1,
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

    # Property codes in _PR, with property 51 recoded at 4.2.
    s.add_all(
        [
            ItemCategory(
                item_id=51,
                start_release_id=1,
                category_id=1,
                code="AS",
                signature="_PR(AS)",
                is_default_item=False,
                end_release_id=2,  # alive 4.0 and 4.1
            ),
            ItemCategory(
                item_id=51,
                start_release_id=3,
                category_id=1,
                code="ACC",
                signature="_PR(ACC)",
                is_default_item=False,
                end_release_id=None,  # alive 4.2+
            ),
            ItemCategory(
                item_id=52,
                start_release_id=1,
                category_id=1,
                code="GA",
                signature="_PR(GA)",
                is_default_item=False,
                end_release_id=None,
            ),
            ItemCategory(
                item_id=53,
                start_release_id=1,
                category_id=1,
                code="RF",
                signature="_PR(RF)",
                is_default_item=False,
                end_release_id=None,
            ),
            # Item 700 (IFRS) in ACC_STD — recoded at 4.1.
            ItemCategory(
                item_id=700,
                start_release_id=1,
                category_id=60,
                code="IFRS",
                signature="ACC_STD(IFRS)",
                is_default_item=False,
                end_release_id=1,  # alive 4.0 only
            ),
            ItemCategory(
                item_id=700,
                start_release_id=2,
                category_id=60,
                code="IFRS_NEW",
                signature="ACC_STD(IFRS_NEW)",
                is_default_item=False,
                end_release_id=None,  # alive 4.1+
            ),
            # Item 701 (EU) in GEO — stable.
            ItemCategory(
                item_id=701,
                start_release_id=1,
                category_id=61,
                code="EU",
                signature="GEO(EU)",
                is_default_item=False,
                end_release_id=None,
            ),
        ]
    )
    s.flush()

    # PropertyCategory — link property→enumerated category at the release.
    s.add_all(
        [
            PropertyCategory(
                property_id=51,
                start_release_id=1,
                category_id=60,
                end_release_id=None,
            ),
            PropertyCategory(
                property_id=52,
                start_release_id=1,
                category_id=61,
                end_release_id=None,
            ),
            # Property 53 has no PropertyCategory → its item lookups
            # would fail (we test that this still emits a version with
            # itemCode=None).
        ]
    )
    s.flush()

    # Two contexts.
    s.add_all(
        [
            Context(
                context_id=100,
                signature="(AS, IFRS)(GA, EU)",
                row_guid="c-ctx-100",
                owner_id=1,
            ),
            Context(
                context_id=200,
                signature="(RF, *)",
                row_guid="c-ctx-200",
                owner_id=1,
            ),
        ]
    )
    s.flush()

    s.add_all(
        [
            ContextComposition(context_id=100, property_id=51, item_id=700),
            ContextComposition(context_id=100, property_id=52, item_id=701),
            ContextComposition(context_id=200, property_id=53, item_id=None),
        ]
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


def _pairs(context_dict):
    return {
        (c["propertyCode"], c["itemCode"])
        for c in context_dict["compositions"]
    }


# ------------------------------------------------------------------ #
# Tests — single release
# ------------------------------------------------------------------ #


class TestSingleContextAtRelease:
    def test_context_100_at_4_0(self, client):
        resp = client.get("/api/v1/structure/context/EBA/100/4.0")
        assert resp.status_code == 200
        ctx = resp.json()["data"]["contexts"][0]
        assert ctx["id"] == 100
        assert ctx["owner"] == "EBA"
        assert ctx["release"] == "4.0"
        # AS+IFRS, GA+EU
        assert _pairs(ctx) == {("AS", "IFRS"), ("GA", "EU")}

    def test_context_100_at_4_1_item_recoded(self, client):
        resp = client.get("/api/v1/structure/context/EBA/100/4.1")
        ctx = resp.json()["data"]["contexts"][0]
        # IFRS → IFRS_NEW.
        assert _pairs(ctx) == {("AS", "IFRS_NEW"), ("GA", "EU")}

    def test_context_100_at_4_2_property_recoded(self, client):
        resp = client.get("/api/v1/structure/context/EBA/100/4.2")
        ctx = resp.json()["data"]["contexts"][0]
        # AS → ACC; item still IFRS_NEW.
        assert _pairs(ctx) == {("ACC", "IFRS_NEW"), ("GA", "EU")}

    def test_context_200_pair_with_null_item(self, client):
        resp = client.get("/api/v1/structure/context/EBA/200/4.0")
        ctx = resp.json()["data"]["contexts"][0]
        # Property 53 (RF) has no PropertyCategory → no item code
        # resolvable. Pair surfaces as (propertyCode, None).
        assert _pairs(ctx) == {("RF", None)}

    def test_nonexistent_id_204(self, client):
        resp = client.get("/api/v1/structure/context/EBA/9999/4.0")
        assert resp.status_code == 204


# ------------------------------------------------------------------ #
# Tests — virtual versioning
# ------------------------------------------------------------------ #


class TestVirtualVersioning:
    def test_context_100_has_three_virtual_versions(self, client):
        resp = client.get("/api/v1/structure/context/EBA/100/*")
        ctxs = resp.json()["data"]["contexts"]
        assert len(ctxs) == 3
        # Versions emitted in chronological order of release.
        releases = [c["release"] for c in ctxs]
        assert releases == ["4.0", "4.1", "4.2"]
        assert _pairs(ctxs[0]) == {("AS", "IFRS"), ("GA", "EU")}
        assert _pairs(ctxs[1]) == {("AS", "IFRS_NEW"), ("GA", "EU")}
        assert _pairs(ctxs[2]) == {("ACC", "IFRS_NEW"), ("GA", "EU")}

    def test_context_200_has_one_virtual_version(self, client):
        resp = client.get("/api/v1/structure/context/EBA/200/*")
        ctxs = resp.json()["data"]["contexts"]
        # No code change in property 53 → one version only.
        assert len(ctxs) == 1
        assert ctxs[0]["release"] == "4.0"
        assert _pairs(ctxs[0]) == {("RF", None)}

    def test_latest_returns_newest_virtual_version(self, client):
        resp = client.get("/api/v1/structure/context/EBA/100/~")
        ctx = resp.json()["data"]["contexts"][0]
        assert ctx["release"] == "4.2"
        assert _pairs(ctx) == {("ACC", "IFRS_NEW"), ("GA", "EU")}

    def test_all_contexts_wildcard(self, client):
        resp = client.get("/api/v1/structure/context/EBA/*/*")
        total = resp.json()["meta"]["totalCount"]
        # 3 versions for context 100 + 1 for context 200 = 4.
        assert total == 4


# ------------------------------------------------------------------ #
# Tests — detail / references / empty
# ------------------------------------------------------------------ #


class TestAllstubs:
    def test_strips_compositions(self, client):
        resp = client.get(
            "/api/v1/structure/context/EBA/100/4.0?detail=allstubs"
        )
        ctx = resp.json()["data"]["contexts"][0]
        for key in ("compositions", "signature"):
            assert key not in ctx
        for key in ("id", "owner", "release", "startReleaseId"):
            assert key in ctx


class TestReferences:
    def test_all_includes_organisations(self, client):
        resp = client.get(
            "/api/v1/structure/context/EBA/100/4.0?references=all"
        )
        assert "organisations" in resp.json()["data"]

    def test_children_is_silent_noop(self, client):
        resp = client.get(
            "/api/v1/structure/context/EBA/100/4.0?references=children"
        )
        ctx = resp.json()["data"]["contexts"][0]
        for key in ("tables", "modules", "children"):
            assert key not in ctx


class TestNonNumericIdRejected:
    def test_alpha_id_204(self, client):
        # Contexts have no code field — alpha ids match nothing.
        resp = client.get("/api/v1/structure/context/EBA/foo/4.0")
        assert resp.status_code == 204


class TestEmptyDatabase:
    def test_empty_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/context/EBA/100/4.0")
        assert resp.status_code == 204


# ------------------------------------------------------------------ #
# Performance — query budget
# ------------------------------------------------------------------ #


class TestQueryBudget:
    def test_query_count_bounded(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get("/api/v1/structure/context/EBA/*/*")
        assert resp.status_code == 200
        assert resp.json()["meta"]["totalCount"] == 4
        # Budget: release resolution + context query +
        # ContextComposition + 3 bulk loaders + owner lookup +
        # _get_all_releases (already cached after first hit). Total
        # ≤9 in practice; cap at 12 for headroom.
        assert counter.count <= 12, (
            f"context path issued {counter.count} queries — "
            f"likely an N+1 regression."
        )
