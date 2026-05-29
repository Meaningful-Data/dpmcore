"""Integration tests for /api/v1/structure/datatype endpoints."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
from dpmcore.orm.infrastructure import DataType
from dpmcore.server.app import create_app

# ------------------------------------------------------------------ #
# Seed model
# ------------------------------------------------------------------ #
#
# A small hierarchy:
#
#   Decimal (id=1)
#     ├── Integer (id=3)
#     └── Boolean (id=4)
#   String  (id=2)
#   Inactive (id=5, is_active=False)
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
    s.add_all(
        [
            DataType(
                data_type_id=1, code="Decimal", name="Decimal", is_active=True
            ),
            DataType(
                data_type_id=2, code="String", name="String", is_active=True
            ),
            DataType(
                data_type_id=3,
                code="Integer",
                name="Integer",
                parent_data_type_id=1,
                is_active=True,
            ),
            DataType(
                data_type_id=4,
                code="Boolean",
                name="Boolean",
                parent_data_type_id=1,
                is_active=True,
            ),
            DataType(
                data_type_id=5,
                code="LegacyType",
                name="Legacy Type",
                is_active=False,
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


class TestDefaultResponse:
    def test_wildcard_lists_all(self, client):
        resp = client.get("/api/v1/structure/datatype/*/*/*")
        assert resp.status_code == 200
        codes = {d["code"] for d in resp.json()["data"]["dataTypes"]}
        assert codes == {
            "Decimal",
            "String",
            "Integer",
            "Boolean",
            "LegacyType",
        }

    def test_single_by_code(self, client):
        resp = client.get("/api/v1/structure/datatype/*/Decimal/*")
        dts = resp.json()["data"]["dataTypes"]
        assert len(dts) == 1
        dt = dts[0]
        assert dt["code"] == "Decimal"
        assert dt["parentDataTypeId"] is None
        assert sorted(dt["childDataTypeIds"]) == [3, 4]
        # No children expansion unless requested.
        assert "childDataTypes" not in dt

    def test_child_carries_parent_id(self, client):
        resp = client.get("/api/v1/structure/datatype/*/Integer/*")
        dt = resp.json()["data"]["dataTypes"][0]
        assert dt["parentDataTypeId"] == 1
        assert dt["childDataTypeIds"] == []

    def test_single_by_numeric_id(self, client):
        resp = client.get("/api/v1/structure/datatype/*/2/*")
        dts = resp.json()["data"]["dataTypes"]
        assert len(dts) == 1
        assert dts[0]["code"] == "String"

    def test_inactive_still_listed(self, client):
        resp = client.get("/api/v1/structure/datatype/*/LegacyType/*")
        dt = resp.json()["data"]["dataTypes"][0]
        assert dt["isActive"] is False


class TestOwnerRejection:
    def test_concrete_owner_204(self, client):
        """DataTypes have no owner — a concrete owner returns 204."""
        for owner in ("EBA", "ECB", "anything"):
            resp = client.get(f"/api/v1/structure/datatype/{owner}/*/*")
            assert resp.status_code == 204

    def test_release_segment_ignored(self, client):
        for path in (
            "/api/v1/structure/datatype/*/Decimal/4.0",
            "/api/v1/structure/datatype/*/Decimal/4.1",
            "/api/v1/structure/datatype/*/Decimal/999.0",
        ):
            resp = client.get(path)
            assert resp.status_code == 200
            assert resp.json()["data"]["dataTypes"][0]["code"] == "Decimal"


class TestChildrenExpansion:
    def test_children_expanded(self, client):
        resp = client.get(
            "/api/v1/structure/datatype/*/Decimal/*?references=children"
        )
        dt = resp.json()["data"]["dataTypes"][0]
        assert "childDataTypes" in dt
        codes = {c["code"] for c in dt["childDataTypes"]}
        assert codes == {"Integer", "Boolean"}
        # Stubs carry id, code, name, isActive.
        for c in dt["childDataTypes"]:
            assert set(c.keys()) == {"id", "code", "name", "isActive"}

    def test_leaf_has_empty_children(self, client):
        resp = client.get(
            "/api/v1/structure/datatype/*/Integer/*?references=children"
        )
        dt = resp.json()["data"]["dataTypes"][0]
        assert dt["childDataTypes"] == []


class TestAllstubs:
    def test_strips_subtrees(self, client):
        resp = client.get(
            "/api/v1/structure/datatype/*/Decimal/*?detail=allstubs"
        )
        dt = resp.json()["data"]["dataTypes"][0]
        for key in (
            "parentDataTypeId",
            "childDataTypeIds",
            "childDataTypes",
        ):
            assert key not in dt
        for key in ("id", "code", "name", "isActive"):
            assert key in dt


class TestEmptyDatabase:
    def test_empty_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/datatype/*/*/*")
        assert resp.status_code == 204


class TestQueryBudget:
    def test_minimal_query_count(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get("/api/v1/structure/datatype/*/*/*")
        assert resp.status_code == 200
        # count + main + child IDs = 3; cap at 5.
        assert counter.count <= 5, (
            f"default datatype path issued {counter.count} queries."
        )

    def test_children_path_minimal(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get(
                "/api/v1/structure/datatype/*/*/*?references=children"
            )
        assert resp.status_code == 200
        # +1 query for child expansions; cap at 6.
        assert counter.count <= 6, (
            f"children datatype path issued {counter.count} queries."
        )
