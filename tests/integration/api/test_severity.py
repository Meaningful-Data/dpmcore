"""Tests for severity constants exposed in dpmcore.dpm_xl.utils.tokens.

Severity is no longer attached to ``OperationScope`` rows (the back-office
persistence path was stripped). ``ASTGeneratorService.script(...)``
threads the caller-supplied ``severity`` value into the per-validation
enriched-AST metadata; the constants below stay as documented values.
"""

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
