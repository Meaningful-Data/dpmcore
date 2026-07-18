"""CLI tests for ``dpmcore validate-model``."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from dpmcore.cli.main import main
from dpmcore.services.model_validation import (
    SEVERITY_ERROR,
    ModelValidationResult,
    ObjectRef,
    Violation,
)


def _result(violations=()):
    errors = [v for v in violations if v.severity == SEVERITY_ERROR]
    return ModelValidationResult(
        is_valid=not errors,
        release_id=1,
        release_code="4.0",
        violations=tuple(violations),
        error_count=len(errors),
        warning_count=len(violations) - len(errors),
        rules_run=5,
        elapsed_ms=12.0,
    )


def _fake_db(result):
    db = MagicMock()
    db.services.model_validation.validate.return_value = result
    cm = MagicMock()
    cm.__enter__.return_value = db
    cm.__exit__.return_value = False
    return cm, db


def test_validate_model_json_valid():
    runner = CliRunner()
    cm, db = _fake_db(_result())
    with patch("dpmcore.connection.connect", return_value=cm):
        result = runner.invoke(
            main,
            [
                "validate-model",
                "--database",
                "sqlite:///:memory:",
                "--json",
            ],
        )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["is_valid"] is True
    assert payload["rules_run"] == 5


def test_validate_model_json_invalid_exit_code():
    runner = CliRunner()
    violation = Violation(
        rule_id="1_5",
        legacy_code="1_5",
        message="Duplicate table code",
        severity=SEVERITY_ERROR,
        objects=(ObjectRef(kind="table_version", id=1, code="T1"),),
    )
    cm, db = _fake_db(_result([violation]))
    with patch("dpmcore.connection.connect", return_value=cm):
        result = runner.invoke(
            main,
            [
                "validate-model",
                "--database",
                "sqlite:///:memory:",
                "--json",
            ],
        )
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["error_count"] == 1


def test_validate_model_rich_output_with_violations():
    runner = CliRunner()
    violations = [
        Violation(
            rule_id="1_5",
            legacy_code="1_5",
            message="Duplicate table code",
            severity=SEVERITY_ERROR,
            objects=(ObjectRef(kind="table_version", id=1, code="T1"),),
        ),
        Violation(
            rule_id="2_4",
            legacy_code="2_4",
            message="Open-row table without non-key columns",
            severity="warning",
        ),
    ]
    cm, db = _fake_db(_result(violations))
    with patch("dpmcore.connection.connect", return_value=cm):
        result = runner.invoke(
            main,
            ["validate-model", "--database", "sqlite:///:memory:"],
        )
    assert result.exit_code == 1
    assert "Duplicate table code" in result.output
    assert "1_5" in result.output


def test_validate_model_rich_output_valid():
    runner = CliRunner()
    cm, db = _fake_db(_result())
    with patch("dpmcore.connection.connect", return_value=cm):
        result = runner.invoke(
            main,
            ["validate-model", "--database", "sqlite:///:memory:"],
        )
    assert result.exit_code == 0
    assert "valid" in result.output


def test_validate_model_passes_options_through():
    runner = CliRunner()
    cm, db = _fake_db(_result())
    with patch("dpmcore.connection.connect", return_value=cm):
        result = runner.invoke(
            main,
            [
                "validate-model",
                "--database",
                "sqlite:///:memory:",
                "--release",
                "3.0",
                "--rules",
                "1_5, 2_1",
                "--no-warnings",
                "--json",
            ],
        )
    assert result.exit_code == 0
    db.services.model_validation.validate.assert_called_once_with(
        release_id=None,
        release_code="3.0",
        rule_ids=["1_5", "2_1"],
        include_warnings=False,
    )


def test_validate_model_release_id_option():
    runner = CliRunner()
    cm, db = _fake_db(_result())
    with patch("dpmcore.connection.connect", return_value=cm):
        result = runner.invoke(
            main,
            [
                "validate-model",
                "--database",
                "sqlite:///:memory:",
                "--release-id",
                "9999",
                "--json",
            ],
        )
    assert result.exit_code == 0
    kwargs = db.services.model_validation.validate.call_args.kwargs
    assert kwargs["release_id"] == 9999
    assert kwargs["rule_ids"] is None
