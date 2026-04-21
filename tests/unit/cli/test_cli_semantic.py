from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from py_dpm.api.dpm_xl.semantic import SemanticValidationResult
from py_dpm.api.dpm_xl.syntax import SyntaxValidationResult
from py_dpm.cli.main import main


@pytest.fixture
def runner():
    return CliRunner()


# Mock py_dpm.models before importing client or running tests that might trigger it
import sys

sys.modules["py_dpm.models"] = MagicMock()


def test_semantic_no_release_id(runner):
    """Test semantic command without release_id (valid case)"""
    expression = "{tC_01.00, r0100, c0010}"

    with patch("py_dpm.cli.main.SemanticAPI") as MockAPI:
        mock_api_instance = MockAPI.return_value
        mock_api_instance.validate_expression.return_value = (
            SemanticValidationResult(
                is_valid=True,
                error_message=None,
                error_code=None,
                expression=expression,
                validation_type="SEMANTIC",
                warning=None,
            )
        )

        result = runner.invoke(main, ["semantic", expression])

        # Verify SemanticAPI was initialized and called correctly
        MockAPI.assert_called_once()
        mock_api_instance.validate_expression.assert_called_once_with(
            expression, release_id=None
        )

        assert result.exit_code == 0
        assert "Semantic validation completed" in result.output
        assert "Status: 200" in result.output


def test_semantic_with_release_id(runner):
    """Test semantic command with specific release_id (valid case)"""
    expression = "{tC_01.00, r0100, c0010}"
    release_id = 5

    with patch("py_dpm.cli.main.SemanticAPI") as MockAPI:
        mock_api_instance = MockAPI.return_value
        mock_api_instance.validate_expression.return_value = (
            SemanticValidationResult(
                is_valid=True,
                error_message=None,
                error_code=None,
                expression=expression,
                validation_type="SEMANTIC",
                warning=None,
            )
        )

        result = runner.invoke(
            main, ["semantic", expression, "--release-id", str(release_id)]
        )

        # Verify SemanticAPI was initialized and called correctly
        MockAPI.assert_called_once()
        mock_api_instance.validate_expression.assert_called_once_with(
            expression, release_id=release_id
        )

        assert result.exit_code == 0
        assert "Semantic validation completed" in result.output
        assert "Status: 200" in result.output


def test_semantic_invalid_validation(runner):
    """Test semantic command when validation fails"""
    expression = "invalid_expression"
    release_id = 3

    with patch("py_dpm.cli.main.SemanticAPI") as MockAPI:
        mock_api_instance = MockAPI.return_value
        mock_api_instance.validate_expression.return_value = (
            SemanticValidationResult(
                is_valid=False,
                error_message="Invalid expression",
                error_code="SEMANTIC_ERROR",
                expression=expression,
                validation_type="SEMANTIC",
                warning=None,
            )
        )

        result = runner.invoke(
            main, ["semantic", expression, "--release-id", str(release_id)]
        )

        # Verify SemanticAPI was initialized and called correctly
        MockAPI.assert_called_once()
        mock_api_instance.validate_expression.assert_called_once_with(
            expression, release_id=release_id
        )

        assert (
            result.exit_code == 0
        )  # Command entry point doesn't exit with non-zero on validation failure, it returns status 500
        assert "Semantic validation failed" in result.output
        assert "Error: Invalid expression" in result.output


def test_semantic_exception(runner):
    """Test semantic command when an exception occurs"""
    expression = "{tC_01.00}"

    with patch("py_dpm.cli.main.SemanticAPI") as MockAPI:
        mock_api_instance = MockAPI.return_value
        mock_api_instance.validate_expression.side_effect = Exception(
            "Unexpected error"
        )

        result = runner.invoke(main, ["semantic", expression])

        assert result.exit_code == 0  # Command returns 500 but exit code 0
        assert "Semantic validation failed" in result.output


def test_semantic_with_release_code(runner):
    expression = "{tC_01.00, r0100, c0010}"
    release_code = "4.2"
    release_id = 5

    with patch("py_dpm.cli.main.SemanticAPI") as MockAPI:
        mock_api_instance = MockAPI.return_value

        # Mock session query results
        # mock_release = MagicMock()
        # mock_release.releaseid = release_id
        # mock_api_instance.session.query.return_value.filter.return_value.first.return_value = mock_release

        # Now we use scalar() and loop query(Release.releaseid)
        mock_api_instance.session.query.return_value.filter.return_value.scalar.return_value = release_id

        mock_api_instance.validate_expression.return_value = (
            SemanticValidationResult(
                is_valid=True,
                error_message=None,
                error_code=None,
                expression=expression,
                validation_type="SEMANTIC",
                warning=None,
            )
        )

        result = runner.invoke(
            main, ["semantic", expression, "--release-code", release_code]
        )

        # Verify SemanticAPI was initialized and called correctly
        # Verify query was made
        mock_api_instance.session.query.assert_called()

        mock_api_instance.validate_expression.assert_called_once_with(
            expression, release_id=release_id
        )

        assert result.exit_code == 0


def test_semantic_release_code_not_found(runner):
    expression = "{}"
    release_code = "99.9"

    with patch("py_dpm.cli.main.SemanticAPI") as MockAPI:
        mock_api_instance = MockAPI.return_value
        # Mock finding nothing (scalar returns None)
        mock_api_instance.session.query.return_value.filter.return_value.scalar.return_value = None

        result = runner.invoke(
            main, ["semantic", expression, "--release-code", release_code]
        )

        assert result.exit_code == 1
        assert (
            f"Error: Release code '{release_code}' not found." in result.output
        )


def test_semantic_conflict_flags(runner):
    expression = "{}"

    result = runner.invoke(
        main,
        ["semantic", expression, "--release-code", "4.2", "--release-id", "5"],
    )

    assert result.exit_code != 0
    assert (
        "Cannot provide both --release-id and --release-code" in result.output
    )


def test_semantic_valid_with_warning(runner):
    """Test semantic command returns valid with a warning message."""
    expression = "{tC_01.00, r0100, c0010}"
    warning_message = "Implicit promotion between Integer and Number."

    with patch("py_dpm.cli.main.SemanticAPI") as MockAPI:
        mock_api_instance = MockAPI.return_value
        mock_api_instance.validate_expression.return_value = (
            SemanticValidationResult(
                is_valid=True,
                error_message=None,
                error_code=None,
                expression=expression,
                validation_type="SEMANTIC",
                warning=warning_message,
            )
        )

        result = runner.invoke(main, ["semantic", expression])

        MockAPI.assert_called_once()
        mock_api_instance.validate_expression.assert_called_once_with(
            expression, release_id=None
        )

        # Validation should still pass even with a warning
        assert result.exit_code == 0
        assert "Semantic validation completed" in result.output
        assert "Status: 200" in result.output


def test_syntax_valid_expression(runner):
    """Test syntax command with a valid expression."""
    expression = "{tC_01.00, r0100, c0010}"

    with patch("py_dpm.cli.main.SyntaxAPI") as MockAPI:
        mock_api_instance = MockAPI.return_value
        mock_api_instance.validate_expression.return_value = (
            SyntaxValidationResult(
                is_valid=True,
                error_message=None,
                expression=expression,
            )
        )

        result = runner.invoke(main, ["syntax", expression])

        MockAPI.assert_called_once()
        mock_api_instance.validate_expression.assert_called_once_with(
            expression
        )

        assert result.exit_code == 0
        assert "Syntax OK" in result.output


def test_syntax_invalid_expression(runner):
    """Test syntax command with an invalid expression."""
    expression = "invalid_expression"

    with patch("py_dpm.cli.main.SyntaxAPI") as MockAPI:
        mock_api_instance = MockAPI.return_value
        mock_api_instance.validate_expression.return_value = (
            SyntaxValidationResult(
                is_valid=False,
                error_message="Syntax errors detected",
                expression=expression,
            )
        )

        result = runner.invoke(main, ["syntax", expression])

        MockAPI.assert_called_once()
        mock_api_instance.validate_expression.assert_called_once_with(
            expression
        )

        assert result.exit_code == 0
        assert "Syntax Error: Syntax errors detected" in result.output


def test_syntax_unexpected_exception(runner):
    """Test syntax command when an unexpected exception occurs."""
    expression = "{tC_01.00}"

    with patch("py_dpm.cli.main.SyntaxAPI") as MockAPI:
        mock_api_instance = MockAPI.return_value
        mock_api_instance.validate_expression.side_effect = Exception(
            "Unexpected error"
        )

        result = runner.invoke(main, ["syntax", expression])

        assert result.exit_code == 0
        assert "Unexpected Error: Unexpected error" in result.output
