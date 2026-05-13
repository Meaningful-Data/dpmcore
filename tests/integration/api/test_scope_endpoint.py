"""Tests for ``POST /api/v1/scope``."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from dpmcore.server.app import create_app


@pytest.fixture
def client(memory_engine):
    app = create_app("sqlite:///:memory:", engine=memory_engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fixture_client(fixture_db_url):
    """Client backed by the real fixture database for end-to-end tests."""
    engine = create_engine(fixture_db_url)
    app = create_app(fixture_db_url, engine=engine)
    with TestClient(app) as c:
        yield c
    engine.dispose()


def _scope_result(is_cross=False, has_error=False, module_versions=None):
    return SimpleNamespace(
        scopes=[],
        total_scopes=2,
        is_cross_module=is_cross,
        module_versions=module_versions
        if module_versions is not None
        else [1, 2],
        has_error=has_error,
        error_message="boom" if has_error else None,
    )


class TestPostScope:
    def test_success_returns_scope_result(self, client):
        with patch(
            "dpmcore.services.scope_calculator.ScopeCalculatorService"
        ) as Svc:
            Svc.return_value.calculate_from_expression.return_value = (
                _scope_result()
            )
            response = client.post(
                "/api/v1/scope",
                json={
                    "expression": "{tC_01.00, r0010, c0010} = 0",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["has_error"] is False
        assert body["total_scopes"] == 2
        assert body["is_cross_module"] is False

    def test_passes_release_id_and_preconditions(self, client):
        with patch(
            "dpmcore.services.scope_calculator.ScopeCalculatorService"
        ) as Svc:
            Svc.return_value.calculate_from_expression.return_value = (
                _scope_result()
            )
            client.post(
                "/api/v1/scope",
                json={
                    "expression": "{tC_01.00, r0010, c0010} = 0",
                    "release_id": 5,
                    "precondition_items": ["item1", "item2"],
                },
            )

        kwargs = Svc.return_value.calculate_from_expression.call_args.kwargs
        assert kwargs["expression"] == "{tC_01.00, r0010, c0010} = 0"
        assert kwargs["release_id"] == 5
        assert kwargs["precondition_items"] == ["item1", "item2"]
        assert kwargs["release_code"] is None

    def test_passes_release_code(self, client):
        """release_code is forwarded to the service like /validate/semantic."""
        with patch(
            "dpmcore.services.scope_calculator.ScopeCalculatorService"
        ) as Svc:
            Svc.return_value.calculate_from_expression.return_value = (
                _scope_result()
            )
            client.post(
                "/api/v1/scope",
                json={
                    "expression": "{tC_01.00, r0010, c0010} = 0",
                    "release_code": "3.4",
                },
            )

        kwargs = Svc.return_value.calculate_from_expression.call_args.kwargs
        assert kwargs["release_code"] == "3.4"
        assert kwargs["release_id"] is None

    def test_empty_precondition_items_accepted(self, client):
        """Passing ``[]`` explicitly is valid and distinct from omitting."""
        with patch(
            "dpmcore.services.scope_calculator.ScopeCalculatorService"
        ) as Svc:
            Svc.return_value.calculate_from_expression.return_value = (
                _scope_result()
            )
            response = client.post(
                "/api/v1/scope",
                json={
                    "expression": "{tC_01.00, r0010, c0010} = 0",
                    "precondition_items": [],
                },
            )

        assert response.status_code == 200
        kwargs = Svc.return_value.calculate_from_expression.call_args.kwargs
        assert kwargs["precondition_items"] == []

    def test_cross_module_scope_returns_flag_and_versions(self, client):
        """Cross-module scope: is_cross_module=True, module_versions populated."""
        with patch(
            "dpmcore.services.scope_calculator.ScopeCalculatorService"
        ) as Svc:
            Svc.return_value.calculate_from_expression.return_value = (
                _scope_result(is_cross=True, module_versions=[10, 20, 30])
            )
            response = client.post(
                "/api/v1/scope",
                json={"expression": "{tC_01.00, r0010, c0010} = 0"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["is_cross_module"] is True
        assert body["module_versions"] == [10, 20, 30]
        assert body["has_error"] is False

    def test_service_error_returns_has_error_true(self, client):
        with patch(
            "dpmcore.services.scope_calculator.ScopeCalculatorService"
        ) as Svc:
            Svc.return_value.calculate_from_expression.return_value = (
                _scope_result(has_error=True)
            )
            response = client.post(
                "/api/v1/scope",
                json={"expression": "bad expression"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["has_error"] is True
        assert body["error_message"] == "boom"

    def test_missing_expression_returns_422(self, client):
        response = client.post("/api/v1/scope", json={})
        assert response.status_code == 422

    def test_endpoint_appears_in_openapi(self, client):
        response = client.get("/api/v1/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        assert "/api/v1/scope" in spec["paths"]
        post = spec["paths"]["/api/v1/scope"]["post"]
        assert post["tags"] == ["Scope"]

        request_schema = spec["components"]["schemas"]["ScopeRequest"][
            "properties"
        ]
        assert set(request_schema.keys()) == {
            "expression",
            "release_id",
            "release_code",
            "precondition_items",
        }
        response_schema = spec["components"]["schemas"]["ScopeResponse"][
            "properties"
        ]
        assert {
            "total_scopes",
            "is_cross_module",
            "module_versions",
            "has_error",
            "error_message",
        } == set(response_schema.keys())


# ------------------------------------------------------------------ #
# Real-engine tests against the fixture database.
# These exercise the full router → service → ORM path; they auto-skip
# when tests/fixtures/test_data.db is not present.
# ------------------------------------------------------------------ #


class TestPostScopeRealEngine:
    def test_invalid_expression_returns_has_error_not_500(
        self, fixture_client
    ):
        """A syntactically broken expression must surface as has_error=True,
        not as a 500 stack trace.
        """
        response = fixture_client.post(
            "/api/v1/scope",
            json={"expression": "this is not a DPM-XL expression"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["has_error"] is True
        assert body["error_message"]

    def test_unknown_release_id_returns_has_error(self, fixture_client):
        """An unknown release_id must come back as has_error=True with a
        message that references the missing release.
        """
        response = fixture_client.post(
            "/api/v1/scope",
            json={
                "expression": "{tC_01.00, r0010, c0010} = 0",
                "release_id": 9_999_999,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["has_error"] is True
        assert "9999999" in (body["error_message"] or "")

    def test_valid_expression_real_engine(self, fixture_client):
        """Happy path end-to-end: a real expression resolves to a scope
        without errors.
        """
        response = fixture_client.post(
            "/api/v1/scope",
            json={
                "expression": "{tC_09.02, r0042, c0105}",
                "release_id": 1,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["has_error"] is False, body.get("error_message")
        assert isinstance(body["total_scopes"], int)
        assert isinstance(body["module_versions"], list)
