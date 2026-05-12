"""Tests for the `dpmcore validate` CLI command."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from dpmcore.cli.main import main
from dpmcore.services.schema_validation import SchemaValidationResult


@pytest.fixture
def runner():
    return CliRunner()


def _result(is_valid: bool, **overrides) -> SchemaValidationResult:
    defaults = {
        "is_valid": is_valid,
        "backend": "sqlite",
        "missing_tables": [],
        "missing_columns": {},
        "empty_required_tables": [],
        "elapsed_ms": 12.3,
    }
    defaults.update(overrides)
    return SchemaValidationResult(**defaults)


class TestValidateExitCodes:
    def test_valid_exits_0(self, runner):
        with patch(
            "dpmcore.connection.DpmConnection.validate_schema",
            return_value=_result(True),
        ):
            result = runner.invoke(
                main,
                ["validate", "--database", "sqlite:///x.db"],
            )
        assert result.exit_code == 0
        assert "valid" in result.output

    def test_invalid_exits_1(self, runner):
        with patch(
            "dpmcore.connection.DpmConnection.validate_schema",
            return_value=_result(
                False,
                missing_tables=["Variable"],
            ),
        ):
            result = runner.invoke(
                main,
                ["validate", "--database", "sqlite:///x.db"],
            )
        assert result.exit_code == 1
        assert "Variable" in result.output

    def test_rich_renders_missing_columns(self, runner):
        with patch(
            "dpmcore.connection.DpmConnection.validate_schema",
            return_value=_result(
                False,
                missing_columns={"Variable": ["code", "name"]},
            ),
        ):
            result = runner.invoke(
                main,
                ["validate", "--database", "sqlite:///x.db"],
            )
        flat = "".join(result.output.split())
        assert result.exit_code == 1
        assert "Missingcolumns" in flat
        assert "Variable" in flat
        assert "code" in flat

    def test_rich_renders_empty_required_tables(self, runner):
        with patch(
            "dpmcore.connection.DpmConnection.validate_schema",
            return_value=_result(
                False,
                empty_required_tables=["Item"],
            ),
        ):
            result = runner.invoke(
                main,
                ["validate", "--database", "sqlite:///x.db"],
            )
        flat = "".join(result.output.split())
        assert result.exit_code == 1
        assert "Emptyrequiredtables" in flat
        assert "Item" in flat


class TestValidateJsonOutput:
    def test_json_flag_emits_json_and_exits_0(self, runner):
        with patch(
            "dpmcore.connection.DpmConnection.validate_schema",
            return_value=_result(True),
        ):
            result = runner.invoke(
                main,
                [
                    "validate",
                    "--database",
                    "sqlite:///x.db",
                    "--json",
                ],
            )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["is_valid"] is True
        assert payload["backend"] == "sqlite"

    def test_json_flag_exits_1_on_failure(self, runner):
        with patch(
            "dpmcore.connection.DpmConnection.validate_schema",
            return_value=_result(
                False,
                missing_columns={"Variable": ["code"]},
                empty_required_tables=["Item"],
            ),
        ):
            result = runner.invoke(
                main,
                [
                    "validate",
                    "--database",
                    "sqlite:///x.db",
                    "--json",
                ],
            )
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["is_valid"] is False
        assert payload["missing_columns"] == {"Variable": ["code"]}
        assert payload["empty_required_tables"] == ["Item"]


class TestValidateHelp:
    def test_validate_in_main_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "validate" in result.output
