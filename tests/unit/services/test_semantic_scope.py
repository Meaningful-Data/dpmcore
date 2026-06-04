"""Unit tests for the scope-wide parameter type-consistency check.

These exercise the in-memory logic now inlined on :class:`SemanticService` —
walking an AST for parameter refs, resolving module versions, extracting
declarations, and the conflict comparison — without a database session. The
DB-backed query (``_co_scoped_parameter_expressions``) and the end-to-end
``validate`` flow are covered by the integration tests in
``tests/integration/validation/test_parameter_selection.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from dpmcore.errors import SemanticError
from dpmcore.services.semantic import (
    SemanticService,
    _module_vids_for,
    _walk_parameter_refs,
)
from dpmcore.services.syntax import SyntaxService


def _svc() -> SemanticService:
    # session is unused by the DB-free methods exercised here.
    return SemanticService(session=None)  # type: ignore[arg-type]


# ------------------------------------------------------------------ #
# _walk_parameter_refs + _declarations
# ------------------------------------------------------------------ #


class TestWalkAndDeclarations:
    def test_walk_finds_nested_parameter_ref(self):
        ast = SyntaxService().parse(
            "{tF_00.01, r010, c010} > {p_threshold, number, default: 0}"
        )
        assert [r.code for r in _walk_parameter_refs(ast)] == ["threshold"]

    def test_walk_empty_when_no_parameters(self):
        ast = SyntaxService().parse("{tF_00.01, r010, c010} > 0")
        assert _walk_parameter_refs(ast) == []

    def test_declarations_extracts_code_to_type(self):
        # Canonical PascalCase, matching ParameterInfo.declared_type.
        assert _svc()._declarations("1 in {p_ccys, set-item}") == {
            "ccys": "SetItem"
        }

    def test_declarations_returns_empty_on_parse_failure(self, monkeypatch):
        svc = _svc()

        def boom(_expr):
            raise ValueError("unparseable")

        monkeypatch.setattr(svc._syntax, "parse", boom)
        assert svc._declarations("{p_x, number}") == {}


# ------------------------------------------------------------------ #
# _module_vids_for
# ------------------------------------------------------------------ #


class TestModuleVidsFor:
    _QUERY = (
        "dpmcore.dpm_xl.model_queries.ModuleVersionQuery.get_from_table_codes"
    )

    def test_empty_table_codes_returns_empty(self):
        # Short-circuits before any query.
        assert _module_vids_for(None, [], release_id=1) == frozenset()

    def test_empty_dataframe_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            self._QUERY, lambda **_kw: pd.DataFrame(columns=["ModuleVID"])
        )
        assert _module_vids_for(None, ["X"], release_id=1) == frozenset()

    def test_resolves_module_vids_from_dataframe(self, monkeypatch):
        monkeypatch.setattr(
            self._QUERY,
            lambda **_kw: pd.DataFrame({"ModuleVID": [10, 11, 10]}),
        )
        assert _module_vids_for(None, ["X"], release_id=1) == frozenset(
            {10, 11}
        )


# ------------------------------------------------------------------ #
# _check_persisted_scope (conflict comparison)
# ------------------------------------------------------------------ #


class TestCheckPersistedScope:
    _MVIDS = "dpmcore.services.semantic._module_vids_for"

    def test_no_module_vids_is_noop(self, monkeypatch):
        svc = _svc()
        called = []
        monkeypatch.setattr(
            svc,
            "_co_scoped_parameter_expressions",
            lambda mvids: called.append(mvids) or [],
        )
        # No table codes -> no module versions -> the DB query is never run.
        svc._check_persisted_scope({"a": "Number"}, [], release_id=1)
        assert called == []

    def test_conflict_raises_3_8(self, monkeypatch):
        svc = _svc()
        monkeypatch.setattr(self._MVIDS, lambda *_a: frozenset({10}))
        monkeypatch.setattr(
            svc,
            "_co_scoped_parameter_expressions",
            lambda _mvids: ["{p_a, integer}"],
        )
        with pytest.raises(SemanticError) as exc:
            svc._check_persisted_scope({"a": "Number"}, ["X"], release_id=1)
        assert exc.value.code == "3-8"

    def test_same_type_does_not_conflict(self, monkeypatch):
        svc = _svc()
        monkeypatch.setattr(self._MVIDS, lambda *_a: frozenset({10}))
        monkeypatch.setattr(
            svc,
            "_co_scoped_parameter_expressions",
            lambda _mvids: ["{p_a, number}"],
        )
        svc._check_persisted_scope({"a": "Number"}, ["X"], release_id=1)

    def test_unknown_code_does_not_conflict(self, monkeypatch):
        svc = _svc()
        monkeypatch.setattr(self._MVIDS, lambda *_a: frozenset({10}))
        # The persisted op declares a code the expression never references.
        monkeypatch.setattr(
            svc,
            "_co_scoped_parameter_expressions",
            lambda _mvids: ["{p_b, number}"],
        )
        svc._check_persisted_scope({"a": "Number"}, ["X"], release_id=1)
