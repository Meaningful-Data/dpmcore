from __future__ import annotations

from dpmcore.errors import SemanticError
from dpmcore.services.semantic import SemanticResult, SemanticService


def _svc() -> SemanticService:
    # session is unused: every DB-touching step is stubbed per test.
    return SemanticService(session=None)  # type: ignore[arg-type]


def _ok(expression: str) -> SemanticResult:
    return SemanticResult(
        is_valid=True,
        error_message=None,
        error_code=None,
        expression=expression,
    )


def _stub(svc, monkeypatch, result=None, link_error=None, link_calls=None):
    monkeypatch.setattr(svc, "_resolve_release", lambda *a, **k: 42)
    monkeypatch.setattr(
        svc, "_validate_resolved", lambda *a, **k: result or _ok("main")
    )

    def _check_precondition_link(precondition_operation_vid, release_id):
        if link_calls is not None:
            link_calls.append((precondition_operation_vid, release_id))
        if link_error is not None:
            raise link_error

    monkeypatch.setattr(
        svc, "_check_precondition_link", _check_precondition_link
    )


class TestNotRequested:
    def test_no_vid_never_calls_the_link_check(self, monkeypatch):
        svc = _svc()
        calls = []
        _stub(svc, monkeypatch, link_calls=calls)
        result = svc.validate("main")
        assert result.is_valid
        assert calls == []


class TestRunsOnlyWhenExpressionIsValid:
    def test_skipped_when_expression_itself_is_invalid(self, monkeypatch):
        svc = _svc()
        bad = SemanticResult(
            is_valid=False,
            error_message="broken",
            error_code="1-2",
            expression="main",
        )
        calls = []
        _stub(svc, monkeypatch, result=bad, link_calls=calls)
        result = svc.validate("main", precondition_operation_vid=7)
        assert not result.is_valid
        assert result.error_code == "1-2"
        assert calls == []

    def test_runs_with_the_resolved_release_when_expression_is_valid(
        self, monkeypatch
    ):
        svc = _svc()
        calls = []
        _stub(svc, monkeypatch, link_calls=calls)
        result = svc.validate("main", precondition_operation_vid=7)
        assert result.is_valid
        assert calls == [(7, 42)]


class TestLinkFailurePropagates:
    def test_a_failing_link_check_fails_the_result(self, monkeypatch):
        svc = _svc()
        svc.ast = "stale"
        _stub(
            svc,
            monkeypatch,
            link_error=SemanticError("7-3", precondition_variable_ids="1, 2"),
        )
        result = svc.validate("main", precondition_operation_vid=7)
        assert not result.is_valid
        assert result.error_code == "7-3"
        assert result.expression == "main"
        assert result.error_source == "precondition"
        # A link failure clears published state like any other failure.
        assert svc.ast is None

    def test_a_failing_link_check_preserves_the_expression_halves(
        self, monkeypatch
    ):
        svc = _svc()
        ok_with_warning = SemanticResult(
            is_valid=True,
            error_message=None,
            error_code=None,
            expression="main",
            warning="deprecated syntax",
        )
        _stub(
            svc,
            monkeypatch,
            result=ok_with_warning,
            link_error=SemanticError(
                "7-4", precondition_tables="A", operation_tables="B"
            ),
        )
        result = svc.validate("main", precondition_operation_vid=7)
        assert not result.is_valid
        assert result.error_code == "7-4"
        assert result.error_source == "precondition"
        # The expression already validated. Its warning isn't lost.
        assert result.warning == "deprecated syntax"

    def test_a_failing_link_check_preserves_the_precondition_verdict(
        self, monkeypatch
    ):
        # A real precondition_expression makes _combine populate
        # result.precondition before the link check runs.
        svc = _svc()
        gate_result = SemanticResult(
            is_valid=True,
            error_message=None,
            error_code=None,
            expression="gate",
            warning="gate warning",
        )
        monkeypatch.setattr(svc, "_resolve_release", lambda *a, **k: 42)

        def _validate_resolved(expression, release_id, as_precondition=False):
            return gate_result if as_precondition else _ok("main")

        monkeypatch.setattr(svc, "_validate_resolved", _validate_resolved)

        def _check_precondition_link(precondition_operation_vid, release_id):
            raise SemanticError("7-3", precondition_variable_ids="1")

        monkeypatch.setattr(
            svc, "_check_precondition_link", _check_precondition_link
        )

        result = svc.validate(
            "main",
            precondition_expression="gate",
            precondition_operation_vid=7,
        )
        assert not result.is_valid
        assert result.error_code == "7-3"
        assert result.error_source == "precondition"
        # The gate's own verdict survives instead of being wiped.
        assert result.precondition is not None
        assert result.precondition.is_valid
        assert result.warning == "Precondition: gate warning"

    def test_a_passing_link_check_leaves_the_expression_result_untouched(
        self, monkeypatch
    ):
        svc = _svc()
        _stub(svc, monkeypatch)
        result = svc.validate("main", precondition_operation_vid=7)
        assert result.is_valid
        assert result.expression == "main"

    def test_a_non_semantic_error_is_also_caught(self, monkeypatch):
        # e.g. a DB connectivity error mid-check: validate() never raises.
        svc = _svc()
        _stub(svc, monkeypatch, link_error=ValueError("boom"))
        result = svc.validate("main", precondition_operation_vid=7)
        assert not result.is_valid
        assert result.error_code == "UNKNOWN"
