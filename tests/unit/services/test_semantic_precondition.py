"""Unit tests for ``validate(precondition_expression=...)`` (issue #279).

DB-free: release resolution and the per-half validation are stubbed, so these
pin the *pairing* contract — the pair-wide ``is_valid``, attribution, the single
release resolution, which half the published per-call state describes, and the
cross-half parameter check. The DB-backed behaviour (the ``2-1`` gate rule, real
expressions) is covered by
``tests/integration/services/test_precondition_expression.py``.
"""

from __future__ import annotations

import pytest

from dpmcore.errors import SemanticError
from dpmcore.services.semantic import (
    ParameterInfo,
    SemanticResult,
    SemanticService,
)


def _svc() -> SemanticService:
    # session is unused: every DB-touching step is stubbed per test.
    return SemanticService(session=None)  # type: ignore[arg-type]


def _ok(expression: str, parameters=(), warning=None) -> SemanticResult:
    return SemanticResult(
        is_valid=True,
        error_message=None,
        error_code=None,
        expression=expression,
        parameters=tuple(parameters),
        warning=warning,
    )


def _bad(expression: str, code: str = "1-2") -> SemanticResult:
    return SemanticResult(
        is_valid=False,
        error_message=f"broken: {expression}",
        error_code=code,
        expression=expression,
        error_source="expression",
    )


def _stub(svc, monkeypatch, results=None, calls=None):
    """Stub release resolution and per-half validation.

    ``results`` maps expression -> SemanticResult; anything absent validates.
    ``calls``, when given, records (expression, as_precondition, release) in
    order.
    """
    monkeypatch.setattr(svc, "_resolve_release", lambda *a, **k: 42)

    def _validate_resolved(expression, release_id, *, as_precondition=False):
        if calls is not None:
            calls.append((expression, as_precondition, release_id))
        return (results or {}).get(expression) or _ok(expression)

    monkeypatch.setattr(svc, "_validate_resolved", _validate_resolved)


class TestUngatedIsUnchanged:
    def test_no_precondition_leaves_the_field_none(self, monkeypatch):
        svc = _svc()
        _stub(svc, monkeypatch)
        result = svc.validate("main")
        assert result.precondition is None
        assert result.is_valid
        assert result.error_source is None

    def test_ungated_failure_is_reported_as_before(self, monkeypatch):
        svc = _svc()
        _stub(svc, monkeypatch, results={"main": _bad("main")})
        result = svc.validate("main")
        assert not result.is_valid
        assert result.error_code == "1-2"
        assert result.error_message == "broken: main"
        assert result.precondition is None


class TestPairWideIsValid:
    def test_both_halves_valid(self, monkeypatch):
        svc = _svc()
        _stub(svc, monkeypatch)
        result = svc.validate("main", precondition_expression="gate")
        assert result.is_valid
        assert result.precondition.is_valid

    def test_broken_gate_invalidates_the_pair(self, monkeypatch):
        # The expression itself is fine, but the row is not evaluable, so the
        # pair-wide verdict is False.
        svc = _svc()
        _stub(svc, monkeypatch, results={"gate": _bad("gate", "2-1")})
        result = svc.validate("main", precondition_expression="gate")
        assert not result.is_valid
        assert result.error_source == "precondition"
        assert result.error_code == "2-1"
        assert result.error_message == "Precondition: broken: gate"
        # The gate's own independent verdict is still reachable.
        assert not result.precondition.is_valid
        assert result.precondition.error_message == "broken: gate"

    def test_nested_gate_verdict_names_its_own_half(self, monkeypatch):
        # A standalone failure attributes itself to "expression" — the only
        # half it knows about. Nested under ``precondition`` that would read
        # as a claim about the main expression, so it is restamped.
        svc = _svc()
        _stub(svc, monkeypatch, results={"gate": _bad("gate")})
        result = svc.validate("main", precondition_expression="gate")
        assert result.precondition.error_source == "precondition"

    def test_a_healthy_gate_carries_no_attribution(self, monkeypatch):
        svc = _svc()
        _stub(svc, monkeypatch)
        result = svc.validate("main", precondition_expression="gate")
        assert result.precondition.error_source is None

    def test_broken_expression_is_attributed_to_the_expression(
        self, monkeypatch
    ):
        svc = _svc()
        _stub(svc, monkeypatch, results={"main": _bad("main")})
        result = svc.validate("main", precondition_expression="gate")
        assert not result.is_valid
        assert result.error_source == "expression"
        assert result.error_message == "broken: main"
        assert result.precondition.is_valid

    def test_both_broken_names_both_failures(self, monkeypatch):
        # Naming only the expression would read as "the gate is fine" and cost
        # the caller a round trip to discover otherwise.
        svc = _svc()
        _stub(
            svc,
            monkeypatch,
            results={"main": _bad("main"), "gate": _bad("gate", "2-1")},
        )
        result = svc.validate("main", precondition_expression="gate")
        assert not result.is_valid
        assert result.error_source == "both"
        assert result.error_message == (
            "broken: main\nPrecondition: broken: gate"
        )
        # error_code holds one value; the expression's takes precedence.
        assert result.error_code == "1-2"
        assert result.precondition.error_code == "2-1"

    def test_error_source_never_implies_a_healthy_gate(self, monkeypatch):
        # "expression" must mean the gate passed, so a broken gate can never be
        # reported under it.
        svc = _svc()
        for results in (
            {"main": _bad("main")},
            {"gate": _bad("gate")},
            {"main": _bad("main"), "gate": _bad("gate")},
        ):
            _stub(svc, monkeypatch, results=results)
            result = svc.validate("main", precondition_expression="gate")
            if result.error_source == "expression":
                assert result.precondition.is_valid

    def test_an_invalid_pair_always_carries_a_message(self, monkeypatch):
        svc = _svc()
        _stub(svc, monkeypatch, results={"gate": _bad("gate")})
        result = svc.validate("main", precondition_expression="gate")
        assert not result.is_valid
        assert result.error_message
        assert result.error_code

    def test_gate_warnings_are_merged_onto_the_pair(self, monkeypatch):
        # A caller reading only result.warning must not miss the gate's.
        svc = _svc()
        _stub(
            svc,
            monkeypatch,
            results={
                "main": _ok("main", warning="main is odd"),
                "gate": _ok("gate", warning="gate is odd"),
            },
        )
        result = svc.validate("main", precondition_expression="gate")
        assert result.warning == "main is odd\nPrecondition: gate is odd"

    def test_gate_warning_alone_still_surfaces(self, monkeypatch):
        svc = _svc()
        _stub(
            svc, monkeypatch, results={"gate": _ok("gate", warning="odd gate")}
        )
        assert (
            svc.validate("main", precondition_expression="gate").warning
            == "Precondition: odd gate"
        )

    def test_no_warnings_stays_none(self, monkeypatch):
        svc = _svc()
        _stub(svc, monkeypatch)
        assert (
            svc.validate("main", precondition_expression="gate").warning
            is None
        )

    def test_error_source_distinguishes_which_half_broke(self, monkeypatch):
        # Without this field a caller could not tell "the expression is broken"
        # from "only the gate is broken" except by matching on the prefix.
        svc = _svc()
        _stub(svc, monkeypatch, results={"gate": _bad("gate")})
        assert (
            svc.validate("main", precondition_expression="gate").error_source
            == "precondition"
        )
        _stub(svc, monkeypatch, results={"main": _bad("main")})
        assert (
            svc.validate("main", precondition_expression="gate").error_source
            == "expression"
        )


class TestSignatureIsBackwardCompatible:
    """The gate is appended, keyword-only: positional callers are untouched.

    Inserting it as the second parameter would have silently reinterpreted
    every existing ``validate(expression, 5)`` call as a gated validation
    against release ``None``.
    """

    def _capture(self, svc, monkeypatch, seen):
        monkeypatch.setattr(
            svc,
            "_resolve_release",
            lambda release_id, release_code: (
                seen.append((release_id, release_code)) or 42
            ),
        )
        monkeypatch.setattr(
            svc,
            "_validate_resolved",
            lambda expression, release_id, **_kw: _ok(expression),
        )

    def test_second_positional_is_still_release_id(self, monkeypatch):
        svc = _svc()
        seen: list = []
        self._capture(svc, monkeypatch, seen)
        result = svc.validate("main", 5)
        assert seen == [(5, None)]
        assert result.precondition is None

    def test_third_positional_is_still_release_code(self, monkeypatch):
        svc = _svc()
        seen: list = []
        self._capture(svc, monkeypatch, seen)
        svc.validate("main", None, "4.2.1")
        assert seen == [(None, "4.2.1")]

    def test_is_valid_keeps_its_positional_order_too(self, monkeypatch):
        svc = _svc()
        seen: list = []
        self._capture(svc, monkeypatch, seen)
        assert svc.is_valid("main", 5)
        assert seen == [(5, None)]

    @pytest.mark.parametrize("method", ["validate", "is_valid"])
    def test_gate_cannot_be_passed_positionally(self, method):
        svc = _svc()
        with pytest.raises(TypeError):
            getattr(svc, method)("main", None, None, "gate")


class TestReleaseHandling:
    def test_release_is_resolved_once_for_both_halves(self, monkeypatch):
        svc = _svc()
        seen = []
        monkeypatch.setattr(
            svc, "_resolve_release", lambda *a, **k: seen.append(1) or 42
        )
        calls = []
        monkeypatch.setattr(
            svc,
            "_validate_resolved",
            lambda expression, release_id, *, as_precondition=False: (
                calls.append((expression, release_id)) or _ok(expression)
            ),
        )
        svc.validate("main", precondition_expression="gate")
        assert len(seen) == 1
        assert [release for _, release in calls] == [42, 42]

    def test_resolution_failure_is_mirrored_onto_the_gate(self, monkeypatch):
        svc = _svc()

        def boom(*_a, **_k):
            raise SemanticError("1-21", release_id=999)

        monkeypatch.setattr(svc, "_resolve_release", boom)
        result = svc.validate("main", precondition_expression="gate")
        assert not result.is_valid
        assert result.error_code == "1-21"
        assert result.error_source == "expression"
        assert result.precondition.error_code == "1-21"
        assert result.precondition.error_source == "precondition"

    def test_resolution_failure_keeps_none_when_no_gate_supplied(
        self, monkeypatch
    ):
        svc = _svc()

        def boom(*_a, **_k):
            raise ValueError("Release code '9.9' not found.")

        monkeypatch.setattr(svc, "_resolve_release", boom)
        result = svc.validate("main")
        # ``None`` means "caller shipped no gate", never "the gate failed".
        assert result.precondition is None
        assert result.error_code == "UNKNOWN"


class TestGateIsValidatedAsAGate:
    def test_only_the_gate_gets_as_precondition(self, monkeypatch):
        svc = _svc()
        calls = []
        _stub(svc, monkeypatch, calls=calls)
        svc.validate("main", precondition_expression="gate")
        assert ("gate", True, 42) in calls
        assert ("main", False, 42) in calls

    def test_gate_is_validated_before_the_main_expression(self, monkeypatch):
        # Ordering is load-bearing: the trailing published state must describe
        # the main expression, so it has to be validated last.
        svc = _svc()
        calls = []
        _stub(svc, monkeypatch, calls=calls)
        svc.validate("main", precondition_expression="gate")
        assert [expression for expression, _, _ in calls] == ["gate", "main"]


class TestCrossHalfParameterCheck:
    def test_conflicting_declaration_invalidates_the_pair(self, monkeypatch):
        svc = _svc()
        _stub(
            svc,
            monkeypatch,
            results={
                "main": _ok("main", [ParameterInfo("thr", "Number")]),
                "gate": _ok("gate", [ParameterInfo("thr", "Integer")]),
            },
        )
        result = svc.validate("main", precondition_expression="gate")
        assert not result.is_valid
        # The clash belongs to the second declaration, not the expression.
        assert result.error_source == "precondition"
        assert result.error_code == "3-8"
        assert result.precondition.error_code == "3-8"
        assert result.precondition.error_source == "precondition"

    def test_agreeing_declarations_pass(self, monkeypatch):
        svc = _svc()
        _stub(
            svc,
            monkeypatch,
            results={
                "main": _ok("main", [ParameterInfo("thr", "Number")]),
                "gate": _ok("gate", [ParameterInfo("thr", "Number")]),
            },
        )
        assert svc.validate("main", precondition_expression="gate").is_valid

    def test_disjoint_parameters_pass(self, monkeypatch):
        svc = _svc()
        _stub(
            svc,
            monkeypatch,
            results={
                "main": _ok("main", [ParameterInfo("a", "Number")]),
                "gate": _ok("gate", [ParameterInfo("b", "String")]),
            },
        )
        assert svc.validate("main", precondition_expression="gate").is_valid

    def test_not_run_when_a_half_already_failed(self, monkeypatch):
        # An already-invalid half carries no parameters worth comparing, and
        # its own failure must be what gets reported.
        svc = _svc()
        _stub(
            svc,
            monkeypatch,
            results={
                "main": _bad("main"),
                "gate": _ok("gate", [ParameterInfo("thr", "Integer")]),
            },
        )
        result = svc.validate("main", precondition_expression="gate")
        assert result.error_source == "expression"
        assert result.error_code == "1-2"


class TestPublishedState:
    def test_failure_clears_the_published_ast(self):
        svc = _svc()
        svc.ast = "stale"
        svc.oc_tables = {"T": {}}
        svc.oc_operations_data = "stale"
        result = svc._failure("expr", ValueError("boom"), "UNKNOWN")
        assert not result.is_valid
        # ``ast`` used to survive a failure, leaving stale state readable.
        assert svc.ast is None
        assert svc.oc_tables is None
        assert svc.oc_parameters is None
        assert svc.oc_operations_data is None


class TestIsValidShortcut:
    @pytest.mark.parametrize(
        ("gate", "gate_broken", "expected"),
        [(None, False, True), ("gate", False, True), ("gate", True, False)],
    )
    def test_is_valid_is_pair_wide(
        self, monkeypatch, gate, gate_broken, expected
    ):
        svc = _svc()
        _stub(
            svc,
            monkeypatch,
            results={"gate": _bad("gate")} if gate_broken else {},
        )
        assert svc.is_valid("main", precondition_expression=gate) is expected
