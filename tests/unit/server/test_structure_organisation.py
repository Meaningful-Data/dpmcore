"""Integration tests for /api/v1/structure/organisation endpoints."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
from dpmcore.orm.infrastructure import Organisation
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
    """Three organisations: EBA, ECB, BIS."""
    s = Session(bind=engine)
    s.add_all(
        [
            Organisation(
                org_id=1,
                name="European Banking Authority",
                acronym="EBA",
                id_prefix=101,
            ),
            Organisation(
                org_id=2,
                name="European Central Bank",
                acronym="ECB",
                id_prefix=102,
            ),
            Organisation(
                org_id=3,
                name="Bank for International Settlements",
                acronym="BIS",
                id_prefix=103,
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
    def test_all_orgs_wildcards(self, client):
        resp = client.get("/api/v1/structure/organisation/*/*/*")
        assert resp.status_code == 200
        orgs = resp.json()["data"]["organisations"]
        acronyms = {o["acronym"] for o in orgs}
        assert acronyms == {"EBA", "ECB", "BIS"}

    def test_fields_present(self, client):
        resp = client.get("/api/v1/structure/organisation/*/EBA/*")
        o = resp.json()["data"]["organisations"][0]
        for key in ("id", "name", "acronym", "idPrefix"):
            assert key in o
        assert o["acronym"] == "EBA"
        assert o["idPrefix"] == 101


class TestFiltering:
    def test_owner_segment_filters_by_acronym(self, client):
        resp = client.get("/api/v1/structure/organisation/EBA/*/*")
        orgs = resp.json()["data"]["organisations"]
        assert len(orgs) == 1
        assert orgs[0]["acronym"] == "EBA"

    def test_id_segment_filters_by_acronym(self, client):
        resp = client.get("/api/v1/structure/organisation/*/BIS/*")
        orgs = resp.json()["data"]["organisations"]
        assert {o["acronym"] for o in orgs} == {"BIS"}

    def test_id_segment_filters_by_numeric_id(self, client):
        resp = client.get("/api/v1/structure/organisation/*/2/*")
        orgs = resp.json()["data"]["organisations"]
        assert len(orgs) == 1
        assert orgs[0]["id"] == 2
        assert orgs[0]["acronym"] == "ECB"

    def test_release_segment_ignored(self, client):
        """Release isn't versioned — every release literal works."""
        for path in (
            "/api/v1/structure/organisation/*/EBA/4.0",
            "/api/v1/structure/organisation/*/EBA/4.1",
            "/api/v1/structure/organisation/*/EBA/999.0",
        ):
            resp = client.get(path)
            assert resp.status_code == 200
            assert resp.json()["data"]["organisations"][0]["acronym"] == "EBA"

    def test_owner_and_id_combined(self, client):
        # Owner=EBA AND id=EBA → matches EBA only.
        resp = client.get("/api/v1/structure/organisation/EBA/EBA/*")
        orgs = resp.json()["data"]["organisations"]
        assert {o["acronym"] for o in orgs} == {"EBA"}

    def test_owner_and_id_disagree_204(self, client):
        # Owner=EBA AND id=BIS → empty intersection.
        resp = client.get("/api/v1/structure/organisation/EBA/BIS/*")
        assert resp.status_code == 204

    def test_comma_separated_ids(self, client):
        resp = client.get("/api/v1/structure/organisation/*/EBA,BIS/*")
        acronyms = {o["acronym"] for o in resp.json()["data"]["organisations"]}
        assert acronyms == {"EBA", "BIS"}


class TestAllstubs:
    def test_strips_extra_fields(self, client):
        resp = client.get(
            "/api/v1/structure/organisation/*/EBA/*?detail=allstubs"
        )
        o = resp.json()["data"]["organisations"][0]
        assert set(o.keys()) == {"id", "acronym"}


class TestReferences:
    def test_all_noop(self, client):
        """references=all is a no-op for organisations themselves."""
        resp = client.get(
            "/api/v1/structure/organisation/*/EBA/*?references=all"
        )
        body = resp.json()
        # The data wrapper has only the organisations key — no nested
        # 'organisations' enrichment (since we're already that list).
        assert set(body["data"].keys()) == {"organisations"}

    def test_children_noop(self, client):
        resp = client.get(
            "/api/v1/structure/organisation/*/EBA/*?references=children"
        )
        body = resp.json()
        assert set(body["data"].keys()) == {"organisations"}


class TestEmptyDatabase:
    def test_empty_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/organisation/*/*/*")
        assert resp.status_code == 204


class TestQueryBudget:
    def test_minimal_query_count(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get("/api/v1/structure/organisation/*/*/*")
        assert resp.status_code == 200
        # count + main query = 2; cap at 4 for headroom.
        assert counter.count <= 4, (
            f"organisation path issued {counter.count} queries."
        )
