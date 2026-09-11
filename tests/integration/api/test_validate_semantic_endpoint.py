"""Tests for ``POST /api/v1/validate/semantic`` (issue #279).

The endpoint gained ``precondition_expression`` in the request and
``error_source`` in the response, so the paired validation the service layer
supports is reachable over REST too.
"""

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


def _result(
    is_valid=True,
    error_message=None,
    error_code=None,
    expression="{tC_01.00, r0010, c0010} = 0",
    warning=None,
    error_source=None,
):
    return {
        "is_valid": is_valid,
        "error_message": error_message,
        "error_code": error_code,
        "expression": expression,
        "warning": warning,
        "error_source": error_source,
    }


class TestPostValidateSemantic:
    def test_ungated_request_forwards_no_gate(self, client):
        with patch("dpmcore.services.dpm_xl.DpmXlService") as Svc:
            Svc.return_value.validate_semantic.return_value = _result()
            response = client.post(
                "/api/v1/validate/semantic",
                json={"expression": "{tC_01.00, r0010, c0010} = 0"},
            )

        assert response.status_code == 200
        assert response.json()["is_valid"] is True
        kwargs = Svc.return_value.validate_semantic.call_args.kwargs
        assert kwargs["precondition_expression"] is None
        assert response.json()["error_source"] is None

    def test_gate_is_forwarded_verbatim(self, client):
        with patch("dpmcore.services.dpm_xl.DpmXlService") as Svc:
            Svc.return_value.validate_semantic.return_value = _result()
            client.post(
                "/api/v1/validate/semantic",
                json={
                    "expression": "{tC_01.00, r0010, c0010} = 0",
                    "precondition_expression": "{v_C_01.00}",
                    "release_code": "4.2.1",
                },
            )

        call = Svc.return_value.validate_semantic.call_args
        assert call.args == ("{tC_01.00, r0010, c0010} = 0",)
        assert call.kwargs["precondition_expression"] == "{v_C_01.00}"
        assert call.kwargs["release_code"] == "4.2.1"
        assert call.kwargs["release_id"] is None

    def test_gate_failure_is_attributed_in_the_response(self, client):
        with patch("dpmcore.services.dpm_xl.DpmXlService") as Svc:
            Svc.return_value.validate_semantic.return_value = _result(
                is_valid=False,
                error_message="Precondition: boom",
                error_code="2-1",
                error_source="precondition",
            )
            response = client.post(
                "/api/v1/validate/semantic",
                json={
                    "expression": "{tC_01.00, r0010, c0010} = 0",
                    "precondition_expression": "{tC_01.00, r0010, c0010}",
                },
            )

        body = response.json()
        assert body["is_valid"] is False
        assert body["error_source"] == "precondition"
        assert body["error_message"] == "Precondition: boom"
        assert body["error_code"] == "2-1"

    def test_merged_warning_is_returned(self, client):
        with patch("dpmcore.services.dpm_xl.DpmXlService") as Svc:
            Svc.return_value.validate_semantic.return_value = _result(
                warning="main is odd\nPrecondition: gate is odd"
            )
            response = client.post(
                "/api/v1/validate/semantic",
                json={
                    "expression": "{tC_01.00, r0010, c0010} = 0",
                    "precondition_expression": "{v_C_01.00}",
                },
            )

        assert response.json()["warning"] == (
            "main is odd\nPrecondition: gate is odd"
        )

    def test_missing_expression_returns_422(self, client):
        response = client.post("/api/v1/validate/semantic", json={})
        assert response.status_code == 422

    def test_openapi_exposes_the_new_fields(self, client):
        spec = client.get("/api/v1/openapi.json").json()
        request_schema = spec["components"]["schemas"]["SemanticRequest"][
            "properties"
        ]
        assert set(request_schema) == {
            "expression",
            "release_id",
            "release_code",
            "precondition_expression",
        }
        response_schema = spec["components"]["schemas"]["SemanticResponse"][
            "properties"
        ]
        assert set(response_schema) == {
            "is_valid",
            "error_message",
            "error_code",
            "expression",
            "warning",
            "error_source",
        }

    def test_syntax_endpoint_does_not_advertise_a_gate(self, client):
        """``/validate/syntax`` has no notion of a precondition."""
        spec = client.get("/api/v1/openapi.json").json()
        request_schema = spec["components"]["schemas"]["ExpressionRequest"][
            "properties"
        ]
        assert "precondition_expression" not in request_schema


# ------------------------------------------------------------------ #
# Real-engine tests against the fixture database; they auto-skip when
# tests/fixtures/test_data.db is not present.
# ------------------------------------------------------------------ #

_MAIN = "{tF_01.02, r0010, c0010} >= 0"
_RELEASE = "4.2.1"


class TestPostValidateSemanticRealEngine:
    def test_valid_pair_passes_end_to_end(self, fixture_client):
        response = fixture_client.post(
            "/api/v1/validate/semantic",
            json={
                "expression": _MAIN,
                "precondition_expression": "{tC_01.00, r0010, c0010} > 0",
                "release_code": _RELEASE,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["is_valid"] is True, body["error_message"]
        assert body["error_source"] is None

    def test_non_boolean_gate_fails_the_pair_with_2_1(self, fixture_client):
        """The same string is valid alone, but not *as a gate*."""
        payload = {"expression": _MAIN, "release_code": _RELEASE}
        assert fixture_client.post(
            "/api/v1/validate/semantic",
            json={**payload, "expression": "{tC_01.00, r0010, c0010}"},
        ).json()["is_valid"]

        body = fixture_client.post(
            "/api/v1/validate/semantic",
            json={
                **payload,
                "precondition_expression": "{tC_01.00, r0010, c0010}",
            },
        ).json()
        assert body["is_valid"] is False
        assert body["error_source"] == "precondition"
        assert body["error_code"] == "2-1"
        assert body["error_message"].startswith("Precondition: ")

    def test_ungated_call_is_byte_identical_to_before(self, fixture_client):
        body = fixture_client.post(
            "/api/v1/validate/semantic",
            json={"expression": _MAIN, "release_code": _RELEASE},
        ).json()
        assert body["is_valid"] is True
        assert body["error_source"] is None
