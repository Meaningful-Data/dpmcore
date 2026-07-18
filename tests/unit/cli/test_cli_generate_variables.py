"""CLI tests for ``dpmcore generate-variables``."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from dpmcore.cli.main import main
from dpmcore.services.model_validation import (
    SEVERITY_ERROR,
    ModelValidationResult,
    Violation,
)
from dpmcore.services.variable_generation.types import (
    CellOutcome,
    GenerationStatus,
    GenerationSummaryRow,
    VariableGenerationResult,
)


def _result(
    status: GenerationStatus = GenerationStatus.COMPLETED,
    validation: ModelValidationResult | None = None,
    consistency: tuple = (),
    summary: tuple = (),
) -> VariableGenerationResult:
    return VariableGenerationResult(
        status=status,
        release_id=1,
        release_code="4.0",
        validation=validation,
        consistency_violations=consistency,
        new_variables=(),
        new_variable_versions=(),
        new_contexts=(),
        new_compound_keys=(),
        new_filing_indicators=(),
        cell_assignments=(),
        header_deduplications=(),
        summary=summary,
        elapsed_ms=5.0,
    )


def _fake_db(result: VariableGenerationResult):
    db = MagicMock()
    db.services.variable_generation.generate.return_value = result
    cm = MagicMock()
    cm.__enter__.return_value = db
    cm.__exit__.return_value = False
    return cm, db


def test_generate_variables_json_completed():
    runner = CliRunner()
    cm, db = _fake_db(_result())
    with patch("dpmcore.connection.connect", return_value=cm):
        outcome = runner.invoke(
            main,
            [
                "generate-variables",
                "--database",
                "sqlite:///:memory:",
                "--json",
            ],
        )
    assert outcome.exit_code == 0
    payload = json.loads(outcome.output)
    assert payload["status"] == "completed"


def test_generate_variables_json_summary_only():
    runner = CliRunner()
    cm, db = _fake_db(_result())
    with patch("dpmcore.connection.connect", return_value=cm):
        outcome = runner.invoke(
            main,
            [
                "generate-variables",
                "--database",
                "sqlite:///:memory:",
                "--json",
                "--summary-only",
            ],
        )
    assert outcome.exit_code == 0
    payload = json.loads(outcome.output)
    assert "cell_assignments" not in payload


def test_generate_variables_rich_completed_with_summary():
    runner = CliRunner()
    row = GenerationSummaryRow(
        outcome=CellOutcome.NEW_VARIABLE,
        message="New variable",
        count=3,
        min_cell_code="C1",
        max_cell_code="C3",
    )
    cm, db = _fake_db(_result(summary=(row,)))
    with patch("dpmcore.connection.connect", return_value=cm):
        outcome = runner.invoke(
            main,
            ["generate-variables", "--database", "sqlite:///:memory:"],
        )
    assert outcome.exit_code == 0
    assert "new_variable" in outcome.output
    assert "completed" in outcome.output


def test_generate_variables_blocked_by_validation():
    runner = CliRunner()
    validation = ModelValidationResult(
        is_valid=False,
        release_id=1,
        release_code="4.0",
        violations=(
            Violation("1_5", "1_5", "dup", SEVERITY_ERROR),
        ),
        error_count=1,
        warning_count=0,
        rules_run=119,
        elapsed_ms=1.0,
    )
    cm, db = _fake_db(
        _result(
            status=GenerationStatus.BLOCKED_BY_VALIDATION,
            validation=validation,
        )
    )
    with patch("dpmcore.connection.connect", return_value=cm):
        outcome = runner.invoke(
            main,
            ["generate-variables", "--database", "sqlite:///:memory:"],
        )
    assert outcome.exit_code == 1
    assert "blocking model" in outcome.output


def test_generate_variables_blocked_by_consistency():
    runner = CliRunner()
    violation = Violation(
        "5_3", "5_3", "same new aspect", SEVERITY_ERROR
    )
    cm, db = _fake_db(
        _result(
            status=GenerationStatus.BLOCKED_BY_CONSISTENCY,
            consistency=(violation,),
        )
    )
    with patch("dpmcore.connection.connect", return_value=cm):
        outcome = runner.invoke(
            main,
            ["generate-variables", "--database", "sqlite:///:memory:"],
        )
    assert outcome.exit_code == 1
    assert "5_3" in outcome.output


def test_generate_variables_passes_options_through():
    runner = CliRunner()
    cm, db = _fake_db(_result())
    with patch("dpmcore.connection.connect", return_value=cm):
        outcome = runner.invoke(
            main,
            [
                "generate-variables",
                "--database",
                "sqlite:///:memory:",
                "--release",
                "3.0",
                "--no-validate",
                "--json",
            ],
        )
    assert outcome.exit_code == 0
    db.services.variable_generation.generate.assert_called_once_with(
        release_id=None,
        release_code="3.0",
        validate_first=False,
    )


def test_generate_variables_rich_completed_empty_summary():
    runner = CliRunner()
    cm, db = _fake_db(_result())
    with patch("dpmcore.connection.connect", return_value=cm):
        outcome = runner.invoke(
            main,
            ["generate-variables", "--database", "sqlite:///:memory:"],
        )
    assert outcome.exit_code == 0
    assert "completed" in outcome.output
    assert "Generation summary" not in outcome.output
