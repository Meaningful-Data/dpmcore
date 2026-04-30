"""Tests for ``POST /api/v1/scripts``."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from dpmcore.server.app import create_app


@pytest.fixture
def client(memory_engine):
    """Build a TestClient backed by the in-memory engine."""
    app = create_app("sqlite:///:memory:", engine=memory_engine)
    with TestClient(app) as c:
        yield c


_NS_URI = "http://example.org/mod"


def _success_payload():
    return {
        "success": True,
        "enriched_ast": {
            _NS_URI: {
                "module_code": "FINREP_Con",
                "module_version": "2.0.1",
                "framework_code": "FINREP",
                "dpm_release": {
                    "release": "4.2",
                    "publication_date": "2025-04-28",
                },
                "dates": {"from": "2026-03-31", "to": None},
                "operations": {
                    "v0001": {
                        "version_id": 1234,
                        "code": "v0001",
                        "expression": "{tF_01.01, r0010, c0010} = 0",
                        "root_operator_id": 24,
                        "ast": {"class_name": "BinOp"},
                        "from_submission_date": "2026-03-31",
                        "severity": "error",
                    }
                },
                "variables": {"100": "m"},
                "tables": {
                    "F_01.01": {
                        "variables": {"100": "m"},
                        "open_keys": {"BASE": "e"},
                    }
                },
                "preconditions": {},
                "precondition_variables": {},
                "dependency_information": {
                    "intra_instance_validations": ["v0001"],
                    "cross_instance_dependencies": [],
                    "alternative_dependencies": [],
                },
                "dependency_modules": {
                    "http://example.org/m1": {
                        "tables": {},
                        "variables": {},
                    },
                },
            }
        },
        "error": None,
    }


class TestPostScripts:
    def test_success_returns_namespaced_payload(self, client):
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.script.return_value = _success_payload()
            response = client.post(
                "/api/v1/scripts",
                json={
                    "expressions": [
                        ["{tF_01.01, r0010, c0010} = 0", "v0001"],
                    ],
                    "module_code": "FINREP_Con",
                    "module_version": "2.0.1",
                },
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        ns = body["enriched_ast"][_NS_URI]
        assert ns["module_code"] == "FINREP_Con"
        assert ns["operations"]["v0001"]["severity"] == "error"
        assert ns["dependency_information"]["intra_instance_validations"] == [
            "v0001"
        ]
        assert "http://example.org/m1" in ns["dependency_modules"]

    def test_passes_args_through_to_service(self, client):
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.script.return_value = _success_payload()
            client.post(
                "/api/v1/scripts",
                json={
                    "expressions": [["expr1", "v0001"]],
                    "module_code": "FINREP_Con",
                    "module_version": "2.0.1",
                    "severity": "error",
                    "severities": {"v0001": "warning"},
                    "release": "4.2",
                },
            )

        kwargs = Svc.return_value.script.call_args.kwargs
        assert kwargs["module_code"] == "FINREP_Con"
        assert kwargs["module_version"] == "2.0.1"
        assert kwargs["severity"] == "error"
        assert kwargs["severities"] == {"v0001": "warning"}
        assert kwargs["release"] == "4.2"
        assert kwargs["expressions"] == [("expr1", "v0001")]
        assert kwargs["preconditions"] is None

    def test_propagates_preconditions(self, client):
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.script.return_value = _success_payload()
            client.post(
                "/api/v1/scripts",
                json={
                    "expressions": [
                        ["e1", "v0001"],
                        ["e2", "v0002"],
                    ],
                    "module_code": "FINREP_Con",
                    "module_version": "2.0.1",
                    "preconditions": [
                        {
                            "expression": "{is_reporting_entity}",
                            "validation_codes": ["v0001", "v0002"],
                        },
                    ],
                },
            )

        kwargs = Svc.return_value.script.call_args.kwargs
        assert kwargs["preconditions"] == [
            ("{is_reporting_entity}", ["v0001", "v0002"]),
        ]

    def test_failure_payload_returned_with_200_and_success_false(self, client):
        """The service's failure path returns success=False inside a 200 envelope."""
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.script.return_value = {
                "success": False,
                "enriched_ast": None,
                "error": "boom",
            }
            response = client.post(
                "/api/v1/scripts",
                json={
                    "expressions": [["e", "v"]],
                    "module_code": "FINREP_Con",
                    "module_version": "2.0.1",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["error"] == "boom"

    def test_invalid_body_returns_422_missing_expressions(self, client):
        response = client.post(
            "/api/v1/scripts",
            json={"module_code": "FINREP_Con", "module_version": "2.0.1"},
        )
        assert response.status_code == 422

    def test_invalid_body_returns_422_missing_module_version(self, client):
        response = client.post(
            "/api/v1/scripts",
            json={
                "expressions": [["e", "v"]],
                "module_code": "FINREP_Con",
            },
        )
        assert response.status_code == 422

    def test_invalid_body_returns_422_malformed_precondition(self, client):
        response = client.post(
            "/api/v1/scripts",
            json={
                "expressions": [["e", "v"]],
                "module_code": "FINREP_Con",
                "module_version": "2.0.1",
                "preconditions": [{"expression": "x"}],  # missing codes
            },
        )
        assert response.status_code == 422


class TestEndpointDocumentation:
    def test_endpoint_appears_in_openapi(self, client):
        response = client.get("/api/v1/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        assert "/api/v1/scripts" in spec["paths"]
        assert "post" in spec["paths"]["/api/v1/scripts"]
