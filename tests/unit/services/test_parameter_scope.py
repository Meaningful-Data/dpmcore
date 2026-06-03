"""Unit tests for the scope-wide parameter type-consistency index.

These exercise the in-memory logic of :class:`ParameterScopeIndex` — walking,
extraction, grouping, and the conflict check — without a database session. The
DB-backed paths (``_query_parameter_rows``, ``module_vids_for`` against real
data, and the end-to-end ``validate`` flow) are covered by the integration
tests in ``tests/integration/validation/test_parameter_selection.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from dpmcore.errors import SemanticError
from dpmcore.services.parameter_scope import (
    ParameterScopeIndex,
    _walk_parameter_refs,
)
from dpmcore.services.syntax import SyntaxService


def _idx() -> ParameterScopeIndex:
    # session is unused by the methods exercised here.
    return ParameterScopeIndex(session=None)  # type: ignore[arg-type]


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
        assert _idx()._declarations("1 in {p_ccys, set-item}") == {
            "ccys": "set-item"
        }

    def test_declarations_returns_empty_on_parse_failure(self, monkeypatch):
        idx = _idx()

        def boom(_expr):
            raise ValueError("unparseable")

        monkeypatch.setattr(idx._syntax, "parse", boom)
        assert idx._declarations("{p_x, number}") == {}


# ------------------------------------------------------------------ #
# _index_from_rows
# ------------------------------------------------------------------ #


class TestIndexFromRows:
    def test_groups_module_vids_per_operation(self, monkeypatch):
        idx = _idx()
        monkeypatch.setattr(idx, "_declarations", lambda _e: {"a": "number"})
        # op 1 spans two module_vids; op 2 is a separate scope.
        rows = [(1, "e1", 10), (1, "e1", 11), (2, "e2", 20)]
        assert idx._index_from_rows(rows) == {
            "a": [
                ("number", frozenset({10, 11})),
                ("number", frozenset({20})),
            ]
        }

    def test_operation_without_declarations_is_skipped(self, monkeypatch):
        idx = _idx()
        monkeypatch.setattr(
            idx,
            "_declarations",
            lambda e: {} if e == "skip" else {"a": "number"},
        )
        rows = [(1, "good", 10), (2, "skip", 20)]
        assert idx._index_from_rows(rows) == {
            "a": [("number", frozenset({10}))]
        }


# ------------------------------------------------------------------ #
# check()
# ------------------------------------------------------------------ #


class TestCheck:
    def test_no_module_vids_is_noop(self):
        idx = _idx()
        idx._index = {"a": [("number", frozenset({10}))]}
        # No scope -> cannot co-execute -> not even the index is consulted.
        idx.check({"a": "string"}, frozenset())

    def test_conflict_raises_3_8(self):
        idx = _idx()
        idx._index = {"a": [("number", frozenset({10}))]}
        with pytest.raises(SemanticError) as exc:
            idx.check({"a": "string"}, frozenset({10}))
        assert exc.value.code == "3-8"

    def test_same_type_does_not_conflict(self):
        idx = _idx()
        idx._index = {"a": [("number", frozenset({10}))]}
        idx.check({"a": "number"}, frozenset({10}))

    def test_disjoint_modules_do_not_conflict(self):
        idx = _idx()
        idx._index = {"a": [("number", frozenset({10}))]}
        # Different type but no shared module version -> disjoint scope, allowed.
        idx.check({"a": "string"}, frozenset({99}))

    def test_unknown_code_does_not_conflict(self):
        idx = _idx()
        idx._index = {"a": [("number", frozenset({10}))]}
        idx.check({"b": "number"}, frozenset({10}))

    def test_index_is_built_lazily_on_first_check(self, monkeypatch):
        idx = _idx()
        built = {"a": [("number", frozenset({10}))]}
        monkeypatch.setattr(idx, "_build", lambda: built)
        with pytest.raises(SemanticError):
            idx.check({"a": "string"}, frozenset({10}))
        assert idx._index is built

    def test_reset_clears_cache(self):
        idx = _idx()
        idx._index = {"a": []}
        idx.reset()
        assert idx._index is None


# ------------------------------------------------------------------ #
# module_vids_for (DB-free branch)
# ------------------------------------------------------------------ #


class TestModuleVidsFor:
    _QUERY = (
        "dpmcore.dpm_xl.model_queries.ModuleVersionQuery.get_from_table_codes"
    )

    def test_empty_table_codes_returns_empty(self):
        # Short-circuits before any query.
        assert _idx().module_vids_for([], release_id=1) == frozenset()

    def test_empty_dataframe_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            self._QUERY, lambda **_kw: pd.DataFrame(columns=["ModuleVID"])
        )
        assert _idx().module_vids_for(["X"], release_id=1) == frozenset()

    def test_resolves_module_vids_from_dataframe(self, monkeypatch):
        monkeypatch.setattr(
            self._QUERY,
            lambda **_kw: pd.DataFrame({"ModuleVID": [10, 11, 10]}),
        )
        assert _idx().module_vids_for(["X"], release_id=1) == frozenset(
            {10, 11}
        )
