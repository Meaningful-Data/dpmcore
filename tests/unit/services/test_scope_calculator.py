"""Tests for cross-module dependency filtering and alternative deps.

Covers Fix 2 (filter_valid_dependency_modules,
detect_cross_module_dependencies) and Fix 3
(detect_alternative_dependencies).
"""

import importlib.util
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _patch_orm(monkeypatch):
    """Prevent ORM import chain on Python 3.10."""
    for mod_name in [
        "dpmcore",
        "dpmcore.connection",
        "dpmcore.orm",
        "dpmcore.orm.infrastructure",
        "dpmcore.orm.packaging",
        "dpmcore.orm.operations",
        "dpmcore.orm.rendering",
        "dpmcore.orm.variables",
        "dpmcore.errors",
        "dpmcore.dpm_xl",
        "dpmcore.dpm_xl.ast",
        "dpmcore.dpm_xl.ast.operands",
        "dpmcore.dpm_xl.utils",
        "dpmcore.dpm_xl.utils.scopes_calculator",
        "dpmcore.services",
        "dpmcore.services.syntax",
    ]:
        if mod_name not in sys.modules:
            monkeypatch.setitem(
                sys.modules, mod_name, MagicMock()
            )


def _load_module():
    """Load scope_calculator module bypassing ORM chain."""
    mod_name = "dpmcore.services.scope_calculator"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    spec = importlib.util.spec_from_file_location(
        mod_name,
        "src/dpmcore/services/scope_calculator.py",
    )
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses can resolve module
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod.ScopeCalculatorService, mod.ScopeResult


def _scope(module_vids):
    """Build a mock scope with the given module VIDs."""
    comps = [
        SimpleNamespace(module_vid=v) for v in module_vids
    ]
    return SimpleNamespace(
        operation_scope_compositions=comps
    )


# ------------------------------------------------------------------ #
# _compute_cross_module
# ------------------------------------------------------------------ #


class TestComputeCrossModule:
    """Test the is_cross_module flag computation."""

    def test_single_module_scope_is_not_cross(self):
        Svc, _ = _load_module()
        assert not Svc._compute_cross_module([_scope([10])])

    def test_multi_module_scope_is_cross(self):
        Svc, _ = _load_module()
        assert Svc._compute_cross_module([_scope([10, 20])])

    def test_empty_scopes(self):
        Svc, _ = _load_module()
        assert not Svc._compute_cross_module([])


# ------------------------------------------------------------------ #
# filter_valid_dependency_modules (Fix 2)
# ------------------------------------------------------------------ #


class TestFilterValidDependencyModules:
    """Test sibling module filtering."""

    def test_filters_out_sibling_modules(self):
        """Modules not in any scope with primary excluded."""
        Svc, SR = _load_module()
        svc = Svc(MagicMock())
        sr = SR(
            existing_scopes=[_scope([10, 20])],
            new_scopes=[_scope([10, 30])],
        )
        valid = svc.filter_valid_dependency_modules(
            sr, primary_module_vid=10
        )
        assert valid == {20, 30}

    def test_primary_not_in_scope_returns_empty(self):
        Svc, SR = _load_module()
        svc = Svc(MagicMock())
        sr = SR(
            existing_scopes=[_scope([20, 30])],
            new_scopes=[],
        )
        valid = svc.filter_valid_dependency_modules(
            sr, primary_module_vid=10
        )
        assert valid == set()

    def test_single_module_scopes_excluded(self):
        """Intra-module scopes are ignored."""
        Svc, SR = _load_module()
        svc = Svc(MagicMock())
        sr = SR(
            existing_scopes=[_scope([10])],
            new_scopes=[_scope([10, 20])],
        )
        valid = svc.filter_valid_dependency_modules(
            sr, primary_module_vid=10
        )
        assert valid == {20}


# ------------------------------------------------------------------ #
# detect_alternative_dependencies (Fix 3)
# ------------------------------------------------------------------ #


class TestDetectAlternativeDependencies:
    """Test alternative dependency detection."""

    def _make_svc(self, uri_map=None):
        Svc, SR = _load_module()
        svc = Svc(MagicMock())
        if uri_map is not None:
            svc._get_module_uri = (
                lambda module_vid, release_id=None: (
                    uri_map.get(module_vid)
                )
            )
        return svc, SR

    def test_detects_alternative_pair(self):
        """A and B each sole-external, never co-occur."""
        svc, SR = self._make_svc(
            {10: "http://uri/a", 20: "http://uri/b"},
        )
        sr = SR(
            existing_scopes=[
                _scope([1, 10]),
                _scope([1, 20]),
            ],
            new_scopes=[],
        )
        result = svc.detect_alternative_dependencies(
            scope_results=[sr], primary_module_vid=1
        )
        assert len(result) == 1
        assert result[0] == sorted(
            ["http://uri/a", "http://uri/b"]
        )

    def test_co_occurring_not_alternative(self):
        """A and B appear together -> not alternatives."""
        svc, SR = self._make_svc(
            {10: "http://uri/a", 20: "http://uri/b"},
        )
        sr = SR(
            existing_scopes=[
                _scope([1, 10]),
                _scope([1, 20]),
                _scope([1, 10, 20]),
            ],
            new_scopes=[],
        )
        result = svc.detect_alternative_dependencies(
            scope_results=[sr], primary_module_vid=1
        )
        assert result == []

    def test_single_external_returns_empty(self):
        svc, SR = self._make_svc({10: "http://uri/a"})
        sr = SR(
            existing_scopes=[_scope([1, 10])],
            new_scopes=[],
        )
        result = svc.detect_alternative_dependencies(
            scope_results=[sr], primary_module_vid=1
        )
        assert result == []

    def test_primary_not_in_scopes_returns_empty(self):
        svc, SR = self._make_svc({})
        sr = SR(
            existing_scopes=[_scope([10, 20])],
            new_scopes=[],
        )
        result = svc.detect_alternative_dependencies(
            scope_results=[sr], primary_module_vid=1
        )
        assert result == []

    def test_multiple_scope_results(self):
        """Works across multiple scope results."""
        svc, SR = self._make_svc(
            {10: "http://uri/a", 20: "http://uri/b"},
        )
        sr1 = SR(
            existing_scopes=[_scope([1, 10])],
            new_scopes=[],
        )
        sr2 = SR(
            existing_scopes=[_scope([1, 20])],
            new_scopes=[],
        )
        result = svc.detect_alternative_dependencies(
            scope_results=[sr1, sr2], primary_module_vid=1
        )
        assert len(result) == 1

    def test_uri_failure_skips_pair(self):
        """If URI resolution fails, skip pair."""
        svc, SR = self._make_svc({10: "http://uri/a"})
        sr = SR(
            existing_scopes=[
                _scope([1, 10]),
                _scope([1, 20]),
            ],
            new_scopes=[],
        )
        result = svc.detect_alternative_dependencies(
            scope_results=[sr], primary_module_vid=1
        )
        assert result == []


# ------------------------------------------------------------------ #
# detect_cross_module_dependencies (Fix 2)
# ------------------------------------------------------------------ #


class TestDetectCrossModuleDependencies:
    """Test the full dependency_info building."""

    def _make_svc(self):
        Svc, SR = _load_module()
        svc = Svc(MagicMock())
        svc._get_module_uri = (
            lambda module_vid, release_id=None: (
                f"http://uri/mod_{module_vid}"
            )
        )
        return svc, SR

    def test_intra_module_returns_op_code(self):
        svc, SR = self._make_svc()
        sr = SR(
            existing_scopes=[_scope([10])],
            new_scopes=[],
            is_cross_module=False,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1234",
        )
        assert info["intra_instance_validations"] == [
            "v1234"
        ]
        assert info["cross_instance_dependencies"] == []

    def test_intra_empty_when_no_op_code(self):
        svc, SR = self._make_svc()
        sr = SR(
            existing_scopes=[_scope([10])],
            new_scopes=[],
            is_cross_module=False,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code=None,
        )
        assert info["intra_instance_validations"] == []

    def test_cross_module_returns_empty_intra(self):
        svc, SR = self._make_svc()

        mv = MagicMock()
        mv.module_vid = 20
        mv.code = "MOD_EXT"
        mv.version_number = "1.0"
        mv.from_reference_date = "2020-01-01"
        mv.to_reference_date = None

        q = svc.session.query.return_value
        q.filter.return_value.first.return_value = mv

        sr = SR(
            existing_scopes=[_scope([10, 20])],
            new_scopes=[],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1234",
        )
        assert info["intra_instance_validations"] == []
        assert (
            len(info["cross_instance_dependencies"]) == 1
        )
        dep = info["cross_instance_dependencies"][0]
        assert dep["modules"][0]["URI"] == (
            "http://uri/mod_20"
        )
        assert dep["affected_operations"] == ["v1234"]

    def test_no_valid_deps_returns_intra(self):
        svc, SR = self._make_svc()
        sr = SR(
            existing_scopes=[_scope([20, 30])],
            new_scopes=[],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1234",
        )
        assert info["intra_instance_validations"] == [
            "v1234"
        ]
        assert info["cross_instance_dependencies"] == []

    def test_alternative_deps_included(self):
        """Alternative deps appear in the result."""
        svc, SR = self._make_svc()

        mv20 = MagicMock()
        mv20.module_vid = 20
        mv20.version_number = "1.0"
        mv20.from_reference_date = None
        mv20.to_reference_date = None

        mv30 = MagicMock()
        mv30.module_vid = 30
        mv30.version_number = "1.0"
        mv30.from_reference_date = None
        mv30.to_reference_date = None

        q = svc.session.query.return_value
        q.filter.return_value.first.side_effect = [
            mv20,
            mv30,
        ]

        sr = SR(
            existing_scopes=[
                _scope([10, 20]),
                _scope([10, 30]),
            ],
            new_scopes=[],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1",
        )
        assert "alternative_dependencies" in info
