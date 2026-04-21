"""
Tests for the severity parameter in AST generation and operation scope creation.

These tests cover:
- Severity constants validation
- Severity parameter in generate_validations_script
- Severity parameter in OperationScopeService.create_operation_scope
- Validation of invalid severity values
"""

import os
import pytest
from dotenv import load_dotenv
from urllib.parse import quote_plus

from py_dpm.api.dpm_xl import ASTGeneratorAPI
from py_dpm.dpm_xl.utils.tokens import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    VALID_SEVERITIES,
    DEFAULT_SEVERITY,
)


load_dotenv()


def _db_kwargs():
    """
    Build DB configuration from environment/.env.

    Prefers server databases configured via PYDPM_RDBMS/PYDPM_DB_* variables.
    Falls back to legacy USE_POSTGRES/POSTGRES_* configuration, then finally
    to SQLite via SQLITE_DB_PATH.
    """
    # Preferred unified configuration
    rdbms = os.getenv("PYDPM_RDBMS", "").strip().lower()

    if rdbms in ("postgres", "sqlserver"):
        host = os.getenv("PYDPM_DB_HOST")
        port = os.getenv("PYDPM_DB_PORT") or (
            "5432" if rdbms == "postgres" else "1433"
        )
        db = os.getenv("PYDPM_DB_NAME")
        user = os.getenv("PYDPM_DB_USER")
        password = os.getenv("PYDPM_DB_PASSWORD")

        if all([host, db, user, password]):
            if rdbms == "postgres":
                connection_url = (
                    f"postgresql://{user}:{password}@{host}:{port}/{db}"
                )
            else:
                # SQL Server connection using ODBC connection string
                server_with_port = f"{host},{port}" if port else host

                # Handling special characters in password for SQL Server
                sqlserver_password = password.replace("}", "}}")
                for x in "%&.@#/\\=;":
                    if x in sqlserver_password:
                        sqlserver_password = "{" + sqlserver_password + "}"
                        break

                if os.name == "nt":
                    driver = "{SQL Server}"
                else:
                    driver = os.getenv(
                        "SQL_DRIVER", "{ODBC Driver 18 for SQL Server}"
                    )

                connection_string = (
                    f"DRIVER={driver}",
                    f"SERVER={server_with_port}",
                    f"DATABASE={db}",
                    f"UID={user}",
                    f"PWD={sqlserver_password}",
                    "TrustServerCertificate=yes",
                )
                encoded = quote_plus(";".join(connection_string))
                connection_url = f"mssql+pyodbc:///?odbc_connect={encoded}"

            return {"connection_url": connection_url}

    return {}


class TestSeverityConstants:
    """Tests for severity constants defined in tokens.py."""

    def test_severity_constants_values(self):
        """Test that severity constants have correct values."""
        assert SEVERITY_ERROR == "error"
        assert SEVERITY_WARNING == "warning"
        assert SEVERITY_INFO == "info"

    def test_valid_severities_contains_all_values(self):
        """Test that VALID_SEVERITIES contains all severity levels."""
        assert SEVERITY_ERROR in VALID_SEVERITIES
        assert SEVERITY_WARNING in VALID_SEVERITIES
        assert SEVERITY_INFO in VALID_SEVERITIES
        assert len(VALID_SEVERITIES) == 3

    def test_default_severity_is_error(self):
        """Test that default severity is 'error'."""
        assert DEFAULT_SEVERITY == SEVERITY_ERROR


class TestSeverityValidation:
    """Tests for severity validation in ASTGeneratorAPI."""

    @pytest.fixture
    def api(self):
        """Create ASTGeneratorAPI instance with database configuration."""
        db_config = _db_kwargs()
        return ASTGeneratorAPI(**db_config, enable_semantic_validation=True)

    def test_invalid_severity_raises_error(self, api):
        """Test that invalid severity value raises ValueError."""
        expression = "{tF_01.01, r0380, c0010} > 0"

        with pytest.raises(ValueError) as exc_info:
            api.generate_validations_script(
                expressions=[(expression, "test_op", None)],
                release_code="4.2",
                module_code="FINREP9",
                severity="invalid_severity",
            )

        assert "Invalid severity" in str(exc_info.value)
        assert "invalid_severity" in str(exc_info.value)
        assert "error" in str(exc_info.value)
        assert "warning" in str(exc_info.value)
        assert "info" in str(exc_info.value)

    def test_empty_severity_raises_error(self, api):
        """Test that empty string severity raises ValueError."""
        expression = "{tF_01.01, r0380, c0010} > 0"

        with pytest.raises(ValueError) as exc_info:
            api.generate_validations_script(
                expressions=[(expression, "test_op", None)],
                release_code="4.2",
                module_code="FINREP9",
                severity="",
            )

        assert "Invalid severity" in str(exc_info.value)


class TestSeverityInGenerateValidationsScript:
    """Integration tests for severity parameter in generate_validations_script."""

    @pytest.fixture
    def api(self):
        """Create ASTGeneratorAPI instance with database configuration."""
        db_config = _db_kwargs()
        return ASTGeneratorAPI(**db_config, enable_semantic_validation=True)

    def test_default_severity_is_error(self, api):
        """Test that default severity is 'error' when not specified."""
        expression = "{tF_01.01, r0380, c0010} > 0"

        result = api.generate_validations_script(
            expressions=[(expression, "test_op", None)],
            release_code="4.2",
            module_code="FINREP9",
            # severity not specified - should default to 'error'
        )

        assert result["success"] is True, (
            f"Expected success, got error: {result['error']}"
        )

        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        # Check severity in operation
        assert "test_op" in module_data["operations"]
        assert module_data["operations"]["test_op"]["severity"] == "error"

    def test_severity_error(self, api):
        """Test that severity='error' is correctly applied."""
        expression = "{tF_01.01, r0380, c0010} > 0"

        result = api.generate_validations_script(
            expressions=[(expression, "test_op", None)],
            release_code="4.2",
            module_code="FINREP9",
            severity="error",
        )

        assert result["success"] is True, (
            f"Expected success, got error: {result['error']}"
        )

        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        assert module_data["operations"]["test_op"]["severity"] == "error"

    def test_severity_warning(self, api):
        """Test that severity='warning' is correctly applied."""
        expression = "{tF_01.01, r0380, c0010} > 0"

        result = api.generate_validations_script(
            expressions=[(expression, "test_op", None)],
            release_code="4.2",
            module_code="FINREP9",
            severity="warning",
        )

        assert result["success"] is True, (
            f"Expected success, got error: {result['error']}"
        )

        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        assert module_data["operations"]["test_op"]["severity"] == "warning"

    def test_severity_info(self, api):
        """Test that severity='info' is correctly applied."""
        expression = "{tF_01.01, r0380, c0010} > 0"

        result = api.generate_validations_script(
            expressions=[(expression, "test_op", None)],
            release_code="4.2",
            module_code="FINREP9",
            severity="info",
        )

        assert result["success"] is True, (
            f"Expected success, got error: {result['error']}"
        )

        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        assert module_data["operations"]["test_op"]["severity"] == "info"

    def test_severity_case_insensitive(self, api):
        """Test that severity is case-insensitive."""
        expression = "{tF_01.01, r0380, c0010} > 0"

        # Test uppercase
        result_upper = api.generate_validations_script(
            expressions=[(expression, "test_op", None)],
            release_code="4.2",
            module_code="FINREP9",
            severity="ERROR",
        )

        assert result_upper["success"] is True

        enriched_ast = result_upper["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        # Should be normalized to lowercase
        assert module_data["operations"]["test_op"]["severity"] == "error"

        # Test mixed case
        result_mixed = api.generate_validations_script(
            expressions=[(expression, "test_op", None)],
            release_code="4.2",
            module_code="FINREP9",
            severity="Warning",
        )

        assert result_mixed["success"] is True

        enriched_ast = result_mixed["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        assert module_data["operations"]["test_op"]["severity"] == "warning"

    def test_severity_applied_to_all_operations(self, api):
        """Test that severity is applied to all operations in multi-expression call."""
        expressions = [
            ("{tF_01.01, r0380, c0010} > 0", "op_1", None),
            ("{tF_01.01, r0390, c0010} >= 0", "op_2", None),
            ("{tF_01.01, r0340, c0010} != 0", "op_3", None),
        ]

        result = api.generate_validations_script(
            expressions=expressions,
            release_code="4.2",
            module_code="FINREP9",
            severity="warning",
        )

        assert result["success"] is True, (
            f"Expected success, got error: {result['error']}"
        )

        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        # All operations should have the same severity
        for op_code in ["op_1", "op_2", "op_3"]:
            assert op_code in module_data["operations"]
            assert module_data["operations"][op_code]["severity"] == "warning"


class TestSeverityInOperationScopeService:
    """Tests for severity parameter in OperationScopeService.create_operation_scope."""

    def test_create_operation_scope_default_severity(self):
        """Test that create_operation_scope uses 'warning' as default severity."""
        from unittest.mock import MagicMock, patch
        from py_dpm.dpm_xl.utils.scopes_calculator import OperationScopeService

        # Mock session and dependencies
        with patch(
            "py_dpm.dpm_xl.utils.scopes_calculator.get_session"
        ) as mock_session:
            mock_session.return_value = MagicMock()

            service = OperationScopeService(operation_version_id=123)

            # Mock the OperationScope class to capture the severity argument
            with patch(
                "py_dpm.dpm_xl.utils.scopes_calculator.OperationScope"
            ) as mock_scope:
                mock_scope.return_value = MagicMock()

                service.create_operation_scope(submission_date="2024-01-01")

                # Check that OperationScope was called with default severity ('warning')
                call_kwargs = mock_scope.call_args[1]
                assert call_kwargs["severity"] == "warning"

    def test_create_operation_scope_custom_severity_error(self):
        """Test that create_operation_scope accepts 'error' severity."""
        from unittest.mock import MagicMock, patch
        from py_dpm.dpm_xl.utils.scopes_calculator import OperationScopeService

        with patch(
            "py_dpm.dpm_xl.utils.scopes_calculator.get_session"
        ) as mock_session:
            mock_session.return_value = MagicMock()

            service = OperationScopeService(operation_version_id=123)

            with patch(
                "py_dpm.dpm_xl.utils.scopes_calculator.OperationScope"
            ) as mock_scope:
                mock_scope.return_value = MagicMock()

                service.create_operation_scope(
                    submission_date="2024-01-01", severity="error"
                )

                call_kwargs = mock_scope.call_args[1]
                assert call_kwargs["severity"] == "error"

    def test_create_operation_scope_custom_severity_warning(self):
        """Test that create_operation_scope accepts 'warning' severity."""
        from unittest.mock import MagicMock, patch
        from py_dpm.dpm_xl.utils.scopes_calculator import OperationScopeService

        with patch(
            "py_dpm.dpm_xl.utils.scopes_calculator.get_session"
        ) as mock_session:
            mock_session.return_value = MagicMock()

            service = OperationScopeService(operation_version_id=123)

            with patch(
                "py_dpm.dpm_xl.utils.scopes_calculator.OperationScope"
            ) as mock_scope:
                mock_scope.return_value = MagicMock()

                service.create_operation_scope(
                    submission_date="2024-01-01", severity="warning"
                )

                call_kwargs = mock_scope.call_args[1]
                assert call_kwargs["severity"] == "warning"

    def test_create_operation_scope_custom_severity_info(self):
        """Test that create_operation_scope accepts 'info' severity."""
        from unittest.mock import MagicMock, patch
        from py_dpm.dpm_xl.utils.scopes_calculator import OperationScopeService

        with patch(
            "py_dpm.dpm_xl.utils.scopes_calculator.get_session"
        ) as mock_session:
            mock_session.return_value = MagicMock()

            service = OperationScopeService(operation_version_id=123)

            with patch(
                "py_dpm.dpm_xl.utils.scopes_calculator.OperationScope"
            ) as mock_scope:
                mock_scope.return_value = MagicMock()

                service.create_operation_scope(
                    submission_date="2024-01-01", severity="info"
                )

                call_kwargs = mock_scope.call_args[1]
                assert call_kwargs["severity"] == "info"

    def test_create_operation_scope_invalid_severity_raises_error(self):
        """Test that create_operation_scope raises ValueError for invalid severity."""
        from unittest.mock import MagicMock, patch
        from py_dpm.dpm_xl.utils.scopes_calculator import OperationScopeService

        with patch(
            "py_dpm.dpm_xl.utils.scopes_calculator.get_session"
        ) as mock_session:
            mock_session.return_value = MagicMock()

            service = OperationScopeService(operation_version_id=123)

            with pytest.raises(ValueError) as exc_info:
                service.create_operation_scope(
                    submission_date="2024-01-01", severity="invalid"
                )

            assert "Invalid severity" in str(exc_info.value)
            assert "invalid" in str(exc_info.value)

    def test_create_operation_scope_severity_normalized_to_lowercase(self):
        """Test that severity is normalized to lowercase."""
        from unittest.mock import MagicMock, patch
        from py_dpm.dpm_xl.utils.scopes_calculator import OperationScopeService

        with patch(
            "py_dpm.dpm_xl.utils.scopes_calculator.get_session"
        ) as mock_session:
            mock_session.return_value = MagicMock()

            service = OperationScopeService(operation_version_id=123)

            with patch(
                "py_dpm.dpm_xl.utils.scopes_calculator.OperationScope"
            ) as mock_scope:
                mock_scope.return_value = MagicMock()

                # Pass uppercase severity
                service.create_operation_scope(
                    submission_date="2024-01-01", severity="ERROR"
                )

                call_kwargs = mock_scope.call_args[1]
                # Should be normalized to lowercase
                assert call_kwargs["severity"] == "error"
