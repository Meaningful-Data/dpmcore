"""Integration tests for /api/v1/structure/operator endpoints."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
from dpmcore.orm.operations import Operator, OperatorArgument
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
    s = Session(bind=engine)
    s.add_all(
        [
            Operator(
                operator_id=1, name="Equals", symbol="=", type="comparison"
            ),
            Operator(
                operator_id=2, name="Plus", symbol="+", type="arithmetic"
            ),
            Operator(operator_id=3, name="And", symbol="AND", type="logical"),
        ]
    )
    s.flush()
    s.add_all(
        [
            OperatorArgument(
                argument_id=10,
                operator_id=1,
                order=0,
                is_mandatory=True,
                name="left",
            ),
            OperatorArgument(
                argument_id=11,
                operator_id=1,
                order=1,
                is_mandatory=True,
                name="right",
            ),
            OperatorArgument(
                argument_id=20,
                operator_id=2,
                order=0,
                is_mandatory=True,
                name="lhs",
            ),
            OperatorArgument(
                argument_id=21,
                operator_id=2,
                order=1,
                is_mandatory=True,
                name="rhs",
            ),
            OperatorArgument(
                argument_id=30,
                operator_id=3,
                order=0,
                is_mandatory=True,
                name="a",
            ),
            OperatorArgument(
                argument_id=31,
                operator_id=3,
                order=1,
                is_mandatory=True,
                name="b",
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
# Tests
# ------------------------------------------------------------------ #


class TestDefaultResponse:
    def test_all_operators_wildcards(self, client):
        resp = client.get("/api/v1/structure/operator/*/*/*")
        assert resp.status_code == 200
        names = {o["name"] for o in resp.json()["data"]["operators"]}
        assert names == {"Equals", "Plus", "And"}

    def test_single_by_name(self, client):
        resp = client.get("/api/v1/structure/operator/*/Equals/*")
        ops = resp.json()["data"]["operators"]
        assert len(ops) == 1
        op = ops[0]
        assert op["name"] == "Equals"
        assert op["symbol"] == "="
        assert op["type"] == "comparison"
        # Arguments inline in order.
        assert [a["name"] for a in op["arguments"]] == ["left", "right"]
        for a in op["arguments"]:
            assert a["isMandatory"] is True

    def test_single_by_numeric_id(self, client):
        resp = client.get("/api/v1/structure/operator/*/3/*")
        op = resp.json()["data"]["operators"][0]
        assert op["name"] == "And"

    def test_comma_separated_names(self, client):
        resp = client.get("/api/v1/structure/operator/*/Plus,And/*")
        names = {o["name"] for o in resp.json()["data"]["operators"]}
        assert names == {"Plus", "And"}

    def test_release_segment_ignored(self, client):
        for path in (
            "/api/v1/structure/operator/*/Plus/4.0",
            "/api/v1/structure/operator/*/Plus/4.1",
            "/api/v1/structure/operator/*/Plus/999.0",
        ):
            resp = client.get(path)
            assert resp.status_code == 200
            assert resp.json()["data"]["operators"][0]["name"] == "Plus"


class TestOwnerRejection:
    def test_concrete_owner_204(self, client):
        """Operators have no owner — concrete owners return 204."""
        for owner in ("EBA", "ECB", "anything"):
            resp = client.get(f"/api/v1/structure/operator/{owner}/*/*")
            assert resp.status_code == 204


class TestAllstubs:
    def test_strips_arguments_and_type(self, client):
        resp = client.get(
            "/api/v1/structure/operator/*/Equals/*?detail=allstubs"
        )
        op = resp.json()["data"]["operators"][0]
        for key in ("type", "arguments"):
            assert key not in op
        assert set(op.keys()) == {"id", "name", "symbol"}


class TestEmptyDatabase:
    def test_empty_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/operator/*/*/*")
        assert resp.status_code == 204


class TestNonexistent:
    def test_unknown_name_204(self, client):
        resp = client.get("/api/v1/structure/operator/*/NOPE/*")
        assert resp.status_code == 204


class TestQueryBudget:
    def test_minimal_query_count(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get("/api/v1/structure/operator/*/*/*")
        assert resp.status_code == 200
        # count + main + arguments bulk = 3; cap at 5.
        assert counter.count <= 5, (
            f"operator path issued {counter.count} queries."
        )
