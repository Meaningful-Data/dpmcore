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


def _success_payload():
    return {
        "success": True,
        "enriched_ast": {
            "owner": "EBA",
            "module_code": "FINREP_Con",
            "module_version": "2.0.1",
            "module_owner": "EBA",
            "module_uri": "http://example.org/mod",
            "framework_code": "FINREP",
            "format_version": "2.0",
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
            "preconditions": {},
            "modules": {
                "FINREP_Con": {
                    "versions": [
                        {
                            "version": "2.0.1",
                            "URI": "http://example.org/mod",
                            "from": "2026-03-31",
                            "to": None,
                            "tables": {
                                "F_01.01": {
                                    "variables": {
                                        "100": {
                                            "data_type": "m",
                                            "cells": [
                                                {
                                                    "row": "0010",
                                                    "column": "0010",
                                                }
                                            ],
                                        }
                                    },
                                    "open_keys": {},
                                }
                            },
                            "filing_indicators": {
                                "F_01.01": {"variable_id": 9, "data_type": "b"}
                            },
                        }
                    ]
                }
            },
            "parameters": {},
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
        },
        "error": None,
    }


class TestPostScripts:
    def test_success_returns_the_script_document(self, client):
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
        assert body["enriched_ast"] == _success_payload()["enriched_ast"]

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
                    "from_submission_dates": {"v0001": "2026-06-30"},
                    "release": "4.2",
                    "owner": "ECB",
                },
            )

        kwargs = Svc.return_value.script.call_args.kwargs
        assert kwargs["module_code"] == "FINREP_Con"
        assert kwargs["module_version"] == "2.0.1"
        assert kwargs["severity"] == "error"
        assert kwargs["severities"] == {"v0001": "warning"}
        assert kwargs["from_submission_dates"] == {"v0001": "2026-06-30"}
        assert kwargs["release"] == "4.2"
        assert kwargs["owner"] == "ECB"
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

    def test_failed_operations_exposed_in_response(self, client):
        """failed_operations from the service are forwarded to the caller."""
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.script.return_value = {
                "success": True,
                "enriched_ast": {"owner": "EBA"},
                "error": None,
                "failed_operations": {
                    "v1": "Grey cells {F_32.03.a, r0040, c0010} were found."
                },
            }
            response = client.post(
                "/api/v1/scripts",
                json={
                    "expressions": [["e", "v1"]],
                    "module_code": "FINREP_Con",
                    "module_version": "2.0.1",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["failed_operations"] == {
            "v1": "Grey cells {F_32.03.a, r0040, c0010} were found."
        }

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

    def test_invalid_body_returns_422_malformed_expression_pair(self, client):
        """Regression for B3: a single-element ``expressions`` item used
        to raise ``IndexError`` and surface as a 500. The Pydantic
        validator should now reject it with a clean 422.
        """
        response = client.post(
            "/api/v1/scripts",
            json={
                "expressions": [["only_one_element"]],
                "module_code": "FINREP_Con",
                "module_version": "2.0.1",
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
