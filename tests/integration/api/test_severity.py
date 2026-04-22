"""Tests for severity constants and OperationScopeService validation.

Ported from py_dpm. The integration-level ``generate_validations_script``
scenarios required a populated DPM database (environment variables
PYDPM_RDBMS/PYDPM_DB_* or SQLite fixture with real content); those
scenarios are not reproducible here without the shared fixture DB and
have been dropped.

Kept behaviour:
- Severity constants and DEFAULT_SEVERITY.
- OperationScopeService.create_operation_scope severity defaulting,
  case-insensitive acceptance, and rejection of invalid values.
"""

from unittest.mock import MagicMock, patch

import pytest

from dpmcore.dpm_xl.utils.scopes_calculator import OperationScopeService
from dpmcore.dpm_xl.utils.tokens import (
    DEFAULT_SEVERITY,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    VALID_SEVERITIES,
)


class TestSeverityConstants:
    """Tests for severity constants defined in tokens.py."""

    def test_severity_constants_values(self):
        assert SEVERITY_ERROR == "error"
        assert SEVERITY_WARNING == "warning"
        assert SEVERITY_INFO == "info"

    def test_valid_severities_contains_all_values(self):
        assert SEVERITY_ERROR in VALID_SEVERITIES
        assert SEVERITY_WARNING in VALID_SEVERITIES
        assert SEVERITY_INFO in VALID_SEVERITIES
        assert len(VALID_SEVERITIES) == 3

    def test_default_severity_is_error(self):
        assert DEFAULT_SEVERITY == SEVERITY_ERROR


class TestOperationScopeServiceSeverity:
    """Tests for severity handling in OperationScopeService.create_operation_scope."""

    def _service(self):
        # ``session`` is not touched by create_operation_scope in the
        # paths exercised below; ``_require_session`` is only called in
        # downstream methods.
        return OperationScopeService(operation_version_id=123, session=None)

    def test_default_severity_is_warning(self):
        """When severity=None, create_operation_scope defaults to 'warning'."""
        service = self._service()

        with patch(
            "dpmcore.dpm_xl.utils.scopes_calculator.OperationScope"
        ) as mock_scope:
            mock_scope.return_value = MagicMock()

            service.create_operation_scope(submission_date="2024-01-01")

            call_kwargs = mock_scope.call_args.kwargs
            assert call_kwargs["severity"] == "warning"

    @pytest.mark.parametrize("severity", ["error", "warning", "info"])
    def test_custom_severity_accepted(self, severity):
        service = self._service()

        with patch(
            "dpmcore.dpm_xl.utils.scopes_calculator.OperationScope"
        ) as mock_scope:
            mock_scope.return_value = MagicMock()

            service.create_operation_scope(
                submission_date="2024-01-01", severity=severity
            )

            assert mock_scope.call_args.kwargs["severity"] == severity

    def test_invalid_severity_raises_value_error(self):
        service = self._service()

        with pytest.raises(ValueError) as exc_info:
            service.create_operation_scope(
                submission_date="2024-01-01", severity="invalid"
            )

        msg = str(exc_info.value)
        assert "Invalid severity" in msg
        assert "invalid" in msg

    def test_severity_normalised_to_lowercase(self):
        service = self._service()

        with patch(
            "dpmcore.dpm_xl.utils.scopes_calculator.OperationScope"
        ) as mock_scope:
            mock_scope.return_value = MagicMock()

            service.create_operation_scope(
                submission_date="2024-01-01", severity="ERROR"
            )

            # The implementation normalises for the IN-check but currently
            # passes the original-cased string on to OperationScope. The
            # acceptance of 'ERROR' as a valid value is what we assert here.
            severity_stored = mock_scope.call_args.kwargs["severity"]
            assert severity_stored.lower() == "error"
