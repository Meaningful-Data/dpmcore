"""Integration tests for /api/v1/structure/variable endpoints."""

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
    SubCategory,
    SubCategoryItem,
    SubCategoryVersion,
)
from dpmcore.orm.infrastructure import (
    Concept,
    DataType,
    Organisation,
    Release,
)
from dpmcore.orm.variables import (
    CompoundKey,
    Variable,
    VariableVersion,
)
from dpmcore.server.app import create_app

# ------------------------------------------------------------------ #
# Seed model
# ------------------------------------------------------------------ #
#
# Three Variables:
#   - 88  (datapoint, "ei001") with subcategory_vid → AT_SUB → ASSET_TYPE.
#         Enumeration items: LOAN (alive 4.0 only), BOND (alive all).
#   - 89  (key, "kv01") with no subcategory_vid → no enumeration.
#   - 90  (datapoint, "ei002") with compound key.
#
# All across two releases (4.0 / 4.1). Variable 88 changes its
# VariableVersion between 4.0 and 4.1 to exercise the release filter.
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
        "c-var-88",
        "c-var-89",
        "c-var-90",
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

    s.add(
        DataType(data_type_id=1, code="String", name="String", is_active=True)
    )
    s.flush()

    # ASSET_TYPE category + AT_SUB subcategory (release-scoped).
    s.add(
        Category(
            category_id=60,
            code="ASSET_TYPE",
            name="Asset type",
            is_enumerated=True,
            is_active=True,
            is_external_ref_data=False,
            created_release_id=1,
            owner_id=1,
        )
    )
    s.flush()
    s.add(
        SubCategory(
            subcategory_id=400,
            category_id=60,
            code="AT_SUB",
            name="Asset type subset",
            owner_id=1,
        )
    )
    s.flush()
    s.add(
        SubCategoryVersion(
            subcategory_vid=4441,
            subcategory_id=400,
            start_release_id=1,
            end_release_id=None,
        )
    )
    s.flush()

    # Items + ItemCategory (LOAN ends at 4.1, BOND alive throughout).
    s.add_all(
        [
            Item(item_id=700, name="Loan", is_property=False, is_active=True),
            Item(item_id=701, name="Bond", is_property=False, is_active=True),
            Item(
                item_id=51,
                name="Asset property",
                is_property=True,
                is_active=True,
            ),
        ]
    )
    s.flush()
    s.add_all(
        [
            ItemCategory(
                item_id=700,
                start_release_id=1,
                category_id=60,
                code="LOAN",
                is_default_item=False,
                signature="ASSET_TYPE(LOAN)",
                end_release_id=2,  # gone from 4.1
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
    s.add_all(
        [
            SubCategoryItem(item_id=700, subcategory_vid=4441, order=1),
            SubCategoryItem(item_id=701, subcategory_vid=4441, order=2),
        ]
    )
    s.flush()
    s.add(
        Property(
            property_id=51,
            is_composite=False,
            is_metric=False,
            data_type_id=1,
            owner_id=1,
        )
    )
    s.flush()

    # CompoundKey for variable 90.
    s.add(
        CompoundKey(
            key_id=999, signature="K(EI002)", row_guid=None, owner_id=1
        )
    )
    s.flush()

    # Variables.
    s.add_all(
        [
            Variable(
                variable_id=88,
                type="datapoint",
                row_guid="c-var-88",
                owner_id=1,
            ),
            Variable(
                variable_id=89,
                type="key",
                row_guid="c-var-89",
                owner_id=1,
            ),
            Variable(
                variable_id=90,
                type="datapoint",
                row_guid="c-var-90",
                owner_id=1,
            ),
        ]
    )
    s.flush()

    # VariableVersions. Variable 88 has two versions to exercise the
    # release filter.
    s.add_all(
        [
            VariableVersion(
                variable_vid=8880,
                variable_id=88,
                property_id=51,
                subcategory_vid=4441,
                code="ei001",
                name="Asset value (v1)",
                is_multi_valued=False,
                start_release_id=1,
                end_release_id=2,
            ),
            VariableVersion(
                variable_vid=8881,
                variable_id=88,
                property_id=51,
                subcategory_vid=4441,
                code="ei001",
                name="Asset value (v2)",
                is_multi_valued=False,
                start_release_id=2,
                end_release_id=None,
            ),
            VariableVersion(
                variable_vid=8990,
                variable_id=89,
                property_id=None,
                subcategory_vid=None,
                code="kv01",
                name="Row key",
                is_multi_valued=False,
                start_release_id=1,
                end_release_id=None,
            ),
            VariableVersion(
                variable_vid=9000,
                variable_id=90,
                property_id=51,
                subcategory_vid=None,
                key_id=999,
                code="ei002",
                name="Other datapoint",
                is_multi_valued=False,
                start_release_id=1,
                end_release_id=None,
            ),
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


# ------------------------------------------------------------------ #
# Tests — default response
# ------------------------------------------------------------------ #


class TestSingleVariable:
    def test_at_literal_release(self, client):
        resp = client.get("/api/v1/structure/variable/EBA/ei001/4.0")
        assert resp.status_code == 200
        body = resp.json()
        vs = body["data"]["variables"]
        assert len(vs) == 1
        v = vs[0]
        assert v["versionId"] == 8880
        assert v["code"] == "ei001"
        assert v["type"] == "datapoint"
        assert v["owner"] == "EBA"
        assert v["release"] == "4.0"

    def test_latest_returns_v2(self, client):
        resp = client.get("/api/v1/structure/variable/EBA/ei001/~")
        v = resp.json()["data"]["variables"][0]
        assert v["versionId"] == 8881

    def test_nonexistent_code_204(self, client):
        resp = client.get("/api/v1/structure/variable/EBA/missing/4.0")
        assert resp.status_code == 204

    def test_unknown_owner_204(self, client):
        resp = client.get("/api/v1/structure/variable/UNKNOWN/ei001/4.0")
        assert resp.status_code == 204


class TestAllVariables:
    def test_wildcards_list_all(self, client):
        resp = client.get("/api/v1/structure/variable/EBA/*/4.0")
        codes = {v["code"] for v in resp.json()["data"]["variables"]}
        assert codes == {"ei001", "kv01", "ei002"}

    def test_release_wildcard_returns_all_versions(self, client):
        resp = client.get("/api/v1/structure/variable/EBA/ei001/*")
        vids = sorted(v["versionId"] for v in resp.json()["data"]["variables"])
        # Two VariableVersions of variable 88.
        assert vids == [8880, 8881]


class TestEnumeration:
    def test_enumeration_present_for_datapoint(self, client):
        resp = client.get("/api/v1/structure/variable/EBA/ei001/4.0")
        v = resp.json()["data"]["variables"][0]
        assert v["isEnumerated"] is True
        assert v["enumeration"]["subcategoryCode"] == "AT_SUB"
        codes = {i["code"] for i in v["enumeration"]["items"]}
        # LOAN alive at 4.0; BOND alive throughout.
        assert codes == {"LOAN", "BOND"}

    def test_enumeration_items_shrink_at_4_1(self, client):
        resp = client.get("/api/v1/structure/variable/EBA/ei001/4.1")
        v = resp.json()["data"]["variables"][0]
        codes = {i["code"] for i in v["enumeration"]["items"]}
        # LOAN ends at 4.1 → only BOND remains valid.
        assert codes == {"BOND"}

    def test_no_enumeration_when_subcategory_vid_null(self, client):
        resp = client.get("/api/v1/structure/variable/EBA/kv01/4.0")
        v = resp.json()["data"]["variables"][0]
        assert v["isEnumerated"] is False
        assert v["enumeration"] is None
        assert v["subcategoryVersionId"] is None


class TestPropertyAndKey:
    def test_property_reference_present(self, client):
        resp = client.get("/api/v1/structure/variable/EBA/ei001/4.0")
        v = resp.json()["data"]["variables"][0]
        assert v["property"]["id"] == 51
        assert v["property"]["name"] == "Asset property"

    def test_property_null_when_absent(self, client):
        resp = client.get("/api/v1/structure/variable/EBA/kv01/4.0")
        v = resp.json()["data"]["variables"][0]
        assert v["property"] is None

    def test_key_signature_resolved(self, client):
        resp = client.get("/api/v1/structure/variable/EBA/ei002/4.0")
        v = resp.json()["data"]["variables"][0]
        assert v["keyId"] == 999
        assert v["keySignature"] == "K(EI002)"

    def test_key_signature_null_when_absent(self, client):
        resp = client.get("/api/v1/structure/variable/EBA/kv01/4.0")
        v = resp.json()["data"]["variables"][0]
        assert v["keyId"] is None
        assert v["keySignature"] is None


class TestAllstubs:
    def test_strips_subtrees(self, client):
        resp = client.get(
            "/api/v1/structure/variable/EBA/ei001/4.0?detail=allstubs"
        )
        v = resp.json()["data"]["variables"][0]
        for key in (
            "property",
            "enumeration",
            "isEnumerated",
            "subcategoryVersionId",
            "keyId",
            "keySignature",
        ):
            assert key not in v
        for key in ("id", "versionId", "code", "type", "owner", "release"):
            assert key in v


class TestReferences:
    def test_all_includes_organisations(self, client):
        resp = client.get(
            "/api/v1/structure/variable/EBA/ei001/4.0?references=all"
        )
        body = resp.json()
        assert "organisations" in body["data"]

    def test_children_is_silent_noop(self, client):
        resp = client.get(
            "/api/v1/structure/variable/EBA/ei001/4.0?references=children"
        )
        v = resp.json()["data"]["variables"][0]
        for key in ("tables", "modules", "children"):
            assert key not in v


class TestEmptyDatabase:
    def test_empty_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/variable/EBA/ei001/4.0")
        assert resp.status_code == 204


# ------------------------------------------------------------------ #
# Performance — query budget
# ------------------------------------------------------------------ #


class TestQueryBudget:
    def test_query_count_bounded(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get("/api/v1/structure/variable/EBA/*/4.0")
        assert resp.status_code == 200
        body = resp.json()
        # All three variables match at 4.0.
        assert len(body["data"]["variables"]) == 3
        # Budget breakdown:
        #   3 release-resolution queries (filter_by_release internals);
        #   1 variable main, 1 property names, 1 key signatures,
        #   3 subcategory enumeration sub-queries
        #     (SCV+SC+Cat / SCI+Item / ItemCategory),
        #   1 owner lookup.
        # ≤14 leaves headroom for incidental changes.
        assert counter.count <= 14, (
            f"variable path issued {counter.count} queries — "
            f"likely an N+1 regression."
        )
