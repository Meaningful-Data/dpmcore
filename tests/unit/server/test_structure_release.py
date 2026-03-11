"""Integration tests for /api/v1/structure/release endpoints."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
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
    """Engine with sample releases pre-seeded."""
    session = Session(bind=engine)

    # Create an organisation + concept for owner filtering
    org = Organisation(
        org_id=1, name="European Banking Authority", acronym="EBA",
    )
    session.add(org)
    session.flush()

    concept = Concept(concept_guid="c-rel-1", owner_id=1)
    session.add(concept)
    concept2 = Concept(concept_guid="c-rel-2", owner_id=1)
    session.add(concept2)
    concept3 = Concept(concept_guid="c-rel-3")
    session.add(concept3)
    session.flush()

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


class TestListAllReleases:
    def test_default_returns_latest(self, client):
        """Bare /structure/release defaults to version=~ (latest)."""
        resp = client.get("/api/v1/structure/release")
        assert resp.status_code == 200
        body = resp.json()
        assert "meta" in body
        assert "data" in body
        assert "releases" in body["data"]
        # Default version is ~ (latest) → single most recent release
        assert len(body["data"]["releases"]) == 1
        assert body["data"]["releases"][0]["code"] == "3.5-draft"

    def test_all_versions(self, client):
        """Explicit version=* returns all releases."""
        resp = client.get("/api/v1/structure/release/*/*/*")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]["releases"]) == 3
        assert body["meta"]["totalCount"] == 3

    def test_pagination(self, client):
        resp = client.get("/api/v1/structure/release/*/*/*?offset=1&limit=1")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]["releases"]) == 1
        assert body["meta"]["offset"] == 1
        assert body["meta"]["limit"] == 1


class TestFilterByOwner:
    def test_filter_by_eba_default_latest(self, client):
        """Owner filter with default version=~ returns latest."""
        resp = client.get("/api/v1/structure/release/EBA")
        assert resp.status_code == 200
        body = resp.json()
        releases = body["data"]["releases"]
        assert len(releases) == 1
        assert releases[0]["code"] == "3.4"

    def test_filter_by_eba_all_versions(self, client):
        """Owner filter with version=* returns all for that owner."""
        resp = client.get("/api/v1/structure/release/EBA/*/*")
        assert resp.status_code == 200
        body = resp.json()
        codes = [r["code"] for r in body["data"]["releases"]]
        assert "3.3" in codes
        assert "3.4" in codes


class TestSingleRelease:
    def test_by_code(self, client):
        resp = client.get("/api/v1/structure/release/*/3.4")
        assert resp.status_code == 200
        body = resp.json()
        assert "release" in body["data"]  # singular key
        assert body["data"]["release"]["code"] == "3.4"
        assert body["meta"]["totalCount"] == 1

    def test_by_owner_and_code(self, client):
        resp = client.get("/api/v1/structure/release/EBA/3.4")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["release"]["code"] == "3.4"


class TestVersionKeywords:
    def test_latest_stable(self, client):
        resp = client.get("/api/v1/structure/release/*/*/+")
        assert resp.status_code == 200
        body = resp.json()
        releases = body["data"]["releases"]
        assert len(releases) == 1
        assert releases[0]["code"] == "3.4"
        assert releases[0]["status"] == "Final"

    def test_latest_any(self, client):
        resp = client.get("/api/v1/structure/release/*/*/~")
        assert resp.status_code == 200
        body = resp.json()
        releases = body["data"]["releases"]
        assert len(releases) == 1
        assert releases[0]["code"] == "3.5-draft"

    def test_all_versions(self, client):
        resp = client.get("/api/v1/structure/release/*/*/*")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]["releases"]) == 3


class TestEmptyResults:
    def test_empty_database_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/release")
        assert resp.status_code == 204
        assert resp.content == b""

    def test_nonexistent_code_returns_204(self, client):
        resp = client.get("/api/v1/structure/release/*/99.99")
        assert resp.status_code == 204


class TestInvalidArtefactType:
    def test_returns_422_for_invalid_enum(self, client):
        """FastAPI rejects unknown artefact types via enum validation (422)."""
        resp = client.get("/api/v1/structure/invalidtype")
        assert resp.status_code == 422


class TestDetailParameter:
    def test_allstubs(self, client):
        resp = client.get("/api/v1/structure/release?detail=allstubs")
        assert resp.status_code == 200
        body = resp.json()
        release = body["data"]["releases"][0]
        assert "id" in release
        assert "code" in release
        assert "description" not in release
        assert "status" not in release


class TestOwnerIdField:
    def test_full_detail_includes_owner_id(self, client):
        resp = client.get("/api/v1/structure/release/*/3.4")
        assert resp.status_code == 200
        release = resp.json()["data"]["release"]
        assert "ownerId" in release
        assert release["ownerId"] == 1

    def test_allstubs_omits_owner_id(self, client):
        resp = client.get(
            "/api/v1/structure/release?detail=allstubs",
        )
        assert resp.status_code == 200
        release = resp.json()["data"]["releases"][0]
        assert "ownerId" not in release


class TestReferencesAll:
    def test_collection_includes_organisations(self, client):
        resp = client.get(
            "/api/v1/structure/release/*/*/*?references=all",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "organisations" in body["data"]
        orgs = body["data"]["organisations"]
        assert len(orgs) >= 1
        org = orgs[0]
        assert "id" in org
        assert "name" in org
        assert "acronym" in org
        assert "idPrefix" in org

    def test_single_includes_organisations(self, client):
        resp = client.get(
            "/api/v1/structure/release/*/3.4?references=all",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "organisations" in body["data"]
        assert body["data"]["organisations"][0]["acronym"] == "EBA"

    def test_none_omits_organisations(self, client):
        resp = client.get(
            "/api/v1/structure/release/*/*/*?references=none",
        )
        assert resp.status_code == 200
        assert "organisations" not in resp.json()["data"]

    def test_default_omits_organisations(self, client):
        resp = client.get("/api/v1/structure/release/*/*/*")
        assert resp.status_code == 200
        assert "organisations" not in resp.json()["data"]


class TestExistingEndpoints:
    """Verify non-structure routes still work."""

    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
