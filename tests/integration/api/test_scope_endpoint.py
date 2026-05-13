"""Tests for ``POST /api/v1/scope``."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from dpmcore.server.app import create_app


@pytest.fixture
def client(memory_engine):
    app = create_app("sqlite:///:memory:", engine=memory_engine)
    with TestClient(app) as c:
        yield c


def _scope_result(is_cross=False, has_error=False):
    return SimpleNamespace(
        scopes=[],
        total_scopes=2,
        is_cross_module=is_cross,
        module_versions=[1, 2],
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
        assert "post" in spec["paths"]["/api/v1/scope"]
