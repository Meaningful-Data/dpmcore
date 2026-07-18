"""Tests for the /api/v1/model endpoints (validation)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
from dpmcore.orm.infrastructure import Release
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
    session = Session(bind=engine)
    session.add(Release(release_id=1, code="4.0", is_current=True))
    session.commit()
    session.close()
    return engine


@pytest.fixture
def client(seeded_engine):
    from starlette.testclient import TestClient

    app = create_app("sqlite:///:memory:", engine=seeded_engine)
    return TestClient(app)


def test_validation_endpoint_runs(client):
    response = client.post(
        "/api/v1/model/validation",
        json={"rule_ids": []},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["is_valid"] is True
    assert payload["release_code"] == "4.0"
    assert payload["violations"] == []


def test_validation_endpoint_unknown_release(client):
    response = client.post(
        "/api/v1/model/validation",
        json={"release_code": "nope"},
    )
    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


def test_validation_endpoint_conflicting_release_args(client):
    response = client.post(
        "/api/v1/model/validation",
        json={"release_id": 1, "release_code": "4.0"},
    )
    assert response.status_code == 422
    assert "not both" in response.json()["detail"]


def test_validation_endpoint_unknown_rule(client):
    response = client.post(
        "/api/v1/model/validation",
        json={"rule_ids": ["nope"]},
    )
    assert response.status_code == 404


def test_rules_catalogue_endpoint(client):
    response = client.get("/api/v1/model/validation/rules")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    for entry in payload[:3]:
        assert {"rule_id", "legacy_code", "family", "severity"} <= set(
            entry
        )


def test_variable_generation_endpoint_runs(client):
    response = client.post(
        "/api/v1/model/variable-generation",
        json={"validate_first": False},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["release_code"] == "4.0"


def test_variable_generation_endpoint_unknown_release(client):
    response = client.post(
        "/api/v1/model/variable-generation",
        json={"release_code": "nope"},
    )
    assert response.status_code == 404


def test_variable_generation_endpoint_conflicting_args(client):
    response = client.post(
        "/api/v1/model/variable-generation",
        json={"release_id": 1, "release_code": "4.0"},
    )
    assert response.status_code == 422
