"""Tests for cross-module dependency filtering and alternative deps.

Covers Fix 2 (filter_valid_dependency_modules,
detect_cross_module_dependencies) and Fix 3
(detect_alternative_dependencies).
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _patch_orm(monkeypatch):
    """Force-stub the ORM chain.

    Always overwrites — earlier tests in the same session (e.g. CLI tests
    that import the real ``dpmcore`` package) populate ``sys.modules`` with
    the real modules, so an ``if mod_name not in sys.modules`` guard would
    leak real classes into ``_load_module``.
    """
    # Stub dpmcore.data so static CSV lookup returns None
    data_stub = MagicMock()
    data_stub.get_module_schema_ref_by_version = MagicMock(return_value=None)
    data_stub.get_module_schema_ref = MagicMock(return_value=None)
    monkeypatch.setitem(sys.modules, "dpmcore.data", data_stub)

    for mod_name in [
        "dpmcore",
        "dpmcore.connection",
        "dpmcore.orm",
        "dpmcore.orm.infrastructure",
        "dpmcore.orm.packaging",
        "dpmcore.orm.operations",
        "dpmcore.orm.rendering",
        "dpmcore.orm.variables",
        "dpmcore.orm.glossary",
        "dpmcore.errors",
        "dpmcore.dpm_xl",
        "dpmcore.dpm_xl.ast",
        "dpmcore.dpm_xl.ast.operands",
        "dpmcore.dpm_xl.utils",
        "dpmcore.dpm_xl.utils.scopes_calculator",
        "dpmcore.services",
        "dpmcore.services.syntax",
    ]:
        monkeypatch.setitem(sys.modules, mod_name, MagicMock())

    # Snapshot the canonical sys.modules entries the helpers below pollute,
    # so the teardown restores them. Both helpers register stub-deps copies
    # under the real module names; without a restore, follow-up test files
    # see those stub copies (or a missing entry) and patches no longer line
    # up with the modules the production code re-imports at call time.
    canonical_names = (
        "dpmcore.services.scope_calculator",
        "dpmcore.services.ast_generator",
    )
    snapshot = {n: sys.modules.get(n) for n in canonical_names}

    yield

    import contextlib
    import importlib

    services_pkg = sys.modules.get("dpmcore.services")
    for name in canonical_names:
        original = snapshot[name]
        if original is not None:
            sys.modules[name] = original
        else:
            sys.modules.pop(name, None)
            try:
                importlib.import_module(name)
            except Exception:
                # If the module can't be imported in the current state,
                # at least make sure no stub-deps copy lingers in sys.modules
                # or as a parent-package attribute.
                sys.modules.pop(name, None)
                if services_pkg is not None:
                    attr = name.rsplit(".", 1)[1]
                    if hasattr(services_pkg, attr):
                        with contextlib.suppress(AttributeError):
                            delattr(services_pkg, attr)


def _load_module():
    """Load scope_calculator module bypassing ORM chain."""
    mod_name = "dpmcore.services.scope_calculator"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    spec = importlib.util.spec_from_file_location(
        mod_name,
        _REPO_ROOT / "src/dpmcore/services/scope_calculator.py",
    )
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses can resolve module
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod.ScopeCalculatorService, mod.ScopeResult


def _scope(module_vids):
    """Build a mock scope with the given module VIDs."""
    comps = [SimpleNamespace(module_vid=v) for v in module_vids]
    return SimpleNamespace(operation_scope_compositions=comps)


# ------------------------------------------------------------------ #
# calculate_from_expression — pins the table_codes routing (⑱)
# ------------------------------------------------------------------ #


class TestCalculateFromExpression:
    """Lock the contract: table codes must be routed via table_codes=, not tables_vids=."""

    def test_routes_oc_tables_keys_via_table_codes(self):
        Svc, _ = _load_module()
        mod = sys.modules["dpmcore.services.scope_calculator"]

        # OperandsChecking is a MagicMock'd class (the real module is stubbed).
        # Configure the instance returned by ``OperandsChecking(...)`` so
        # ``oc.tables`` is a real dict and ``oc.preconditions`` is a real bool.
        oc_instance = MagicMock()
        oc_instance.tables = {
            "T_CODE_A": MagicMock(),
            "T_CODE_B": MagicMock(),
        }
        oc_instance.preconditions = False
        mod.OperandsChecking.return_value = oc_instance

        # Configure the OperationScopeService mock to record the call.
        scope_svc_instance = MagicMock()
        scope_svc_instance.calculate_operation_scope.return_value = ([], [])
        mod.OperationScopeService.return_value = scope_svc_instance

        # Skip _check_release_exists DB hit by passing release_id=None.
        svc = Svc(MagicMock())
        svc._syntax = MagicMock()
        svc._syntax.parse.return_value = MagicMock()  # AST stand-in
        svc._check_release_exists = MagicMock()

        result = svc.calculate_from_expression(
            expression="dummy",
            release_id=None,
        )

        # The fix: table codes flow through ``table_codes=``, not ``tables_vids=``.
        call = scope_svc_instance.calculate_operation_scope.call_args
        assert call.kwargs["table_codes"] == ["T_CODE_A", "T_CODE_B"]
        assert call.kwargs["tables_vids"] == []
        assert not result.has_error


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
            scopes=[_scope([10, 20]), _scope([10, 30])],
        )
        valid = svc.filter_valid_dependency_modules(sr, primary_module_vid=10)
        assert valid == {20, 30}

    def test_primary_not_in_scope_returns_empty(self):
        Svc, SR = _load_module()
        svc = Svc(MagicMock())
        sr = SR(
            scopes=[_scope([20, 30])],
        )
        valid = svc.filter_valid_dependency_modules(sr, primary_module_vid=10)
        assert valid == set()

    def test_single_module_scopes_excluded(self):
        """Intra-module scopes are ignored."""
        Svc, SR = _load_module()
        svc = Svc(MagicMock())
        sr = SR(
            scopes=[_scope([10]), _scope([10, 20])],
        )
        valid = svc.filter_valid_dependency_modules(sr, primary_module_vid=10)
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
            svc._get_module_uri = lambda module_vid, release_id=None, mv=None: (
                uri_map.get(module_vid)
            )
        return svc, SR

    def test_detects_alternative_pair(self):
        """A and B each sole-external, never co-occur."""
        svc, SR = self._make_svc(
            {10: "http://uri/a", 20: "http://uri/b"},
        )
        sr = SR(
            scopes=[
                _scope([1, 10]),
                _scope([1, 20]),
            ],
        )
        result = svc.detect_alternative_dependencies(
            scope_results=[sr], primary_module_vid=1
        )
        assert len(result) == 1
        assert result[0] == sorted(["http://uri/a", "http://uri/b"])

    def test_co_occurring_not_alternative(self):
        """A and B appear together -> not alternatives."""
        svc, SR = self._make_svc(
            {10: "http://uri/a", 20: "http://uri/b"},
        )
        sr = SR(
            scopes=[
                _scope([1, 10]),
                _scope([1, 20]),
                _scope([1, 10, 20]),
            ],
        )
        result = svc.detect_alternative_dependencies(
            scope_results=[sr], primary_module_vid=1
        )
        assert result == []

    def test_single_external_returns_empty(self):
        svc, SR = self._make_svc({10: "http://uri/a"})
        sr = SR(
            scopes=[_scope([1, 10])],
        )
        result = svc.detect_alternative_dependencies(
            scope_results=[sr], primary_module_vid=1
        )
        assert result == []

    def test_primary_not_in_scopes_returns_empty(self):
        svc, SR = self._make_svc({})
        sr = SR(
            scopes=[_scope([10, 20])],
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
            scopes=[_scope([1, 10])],
        )
        sr2 = SR(
            scopes=[_scope([1, 20])],
        )
        result = svc.detect_alternative_dependencies(
            scope_results=[sr1, sr2], primary_module_vid=1
        )
        assert len(result) == 1

    def test_uri_failure_skips_pair(self):
        """If URI resolution fails, skip pair."""
        svc, SR = self._make_svc({10: "http://uri/a"})
        sr = SR(
            scopes=[
                _scope([1, 10]),
                _scope([1, 20]),
            ],
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
        svc._get_module_uri = lambda module_vid, release_id=None, mv=None: (
            f"http://uri/mod_{module_vid}"
        )
        svc._get_module_tables = lambda module_vid, release_id=None: {}
        return svc, SR

    def test_intra_module_returns_op_code(self):
        svc, SR = self._make_svc()
        sr = SR(
            scopes=[_scope([10])],
            is_cross_module=False,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1234",
        )
        assert info["intra_instance_validations"] == ["v1234"]
        assert info["cross_instance_dependencies"] == []

    def test_intra_empty_when_no_op_code(self):
        svc, SR = self._make_svc()
        sr = SR(
            scopes=[_scope([10])],
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
        # Provide at least one variable-bearing table — modules with
        # only variable-less tables are now dropped.
        svc._get_module_tables = lambda vid, release_id=None: {
            "T_01": {"variables": {"v1": "x"}, "open_keys": {}},
        }

        mv = MagicMock()
        mv.module_vid = 20
        mv.code = "MOD_EXT"
        mv.version_number = "1.0"
        mv.from_reference_date = "2020-01-01"
        mv.to_reference_date = None

        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = [mv]

        sr = SR(
            scopes=[_scope([10, 20])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1234",
        )
        assert info["intra_instance_validations"] == []
        assert len(info["cross_instance_dependencies"]) == 1
        dep = info["cross_instance_dependencies"][0]
        assert dep["modules"][0]["URI"] == ("http://uri/mod_20")
        assert dep["affected_operations"] == ["v1234"]

    def test_no_valid_deps_returns_intra(self):
        svc, SR = self._make_svc()
        sr = SR(
            scopes=[_scope([20, 30])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1234",
        )
        assert info["intra_instance_validations"] == ["v1234"]
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
        q.filter.return_value.all.return_value = [mv20, mv30]

        sr = SR(
            scopes=[
                _scope([10, 20]),
                _scope([10, 30]),
            ],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1",
        )
        assert "alternative_dependencies" in info

    def test_ref_period_from_time_shifts(self):
        """ref_period uses time_shifts when provided."""
        svc, SR = self._make_svc()
        svc._get_module_tables = lambda vid, release_id=None: {
            "C_01.00": {
                "variables": {"100": "m"},  # non-empty so the table survives
                "open_keys": {},
            }
        }

        mv = MagicMock()
        mv.module_vid = 20
        mv.version_number = "1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None

        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = [mv]

        sr = SR(
            scopes=[_scope([10, 20])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            time_shifts={"C_01.00": "T-1Q"},
        )
        dep = info["cross_instance_dependencies"][0]
        assert dep["modules"][0]["ref_period"] == "T-1Q"

    def test_ref_period_defaults_to_t(self):
        """ref_period defaults to T when no time shifts."""
        svc, SR = self._make_svc()
        svc._get_module_tables = lambda vid, release_id=None: {
            "T_01": {"variables": {"v1": "x"}, "open_keys": {}},
        }

        mv = MagicMock()
        mv.module_vid = 20
        mv.version_number = "1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None

        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = [mv]

        sr = SR(
            scopes=[_scope([10, 20])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
        )
        dep = info["cross_instance_dependencies"][0]
        assert dep["modules"][0]["ref_period"] == "T"

    def test_dependency_modules_in_output(self):
        """dependency_modules dict is populated."""
        svc, SR = self._make_svc()
        svc._get_module_tables = lambda vid, release_id=None: {
            "T_01": {
                "variables": {"v1": "x"},
                "open_keys": {},
            }
        }

        mv = MagicMock()
        mv.module_vid = 20
        mv.version_number = "1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None

        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = [mv]

        sr = SR(
            scopes=[_scope([10, 20])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
        )
        dm = info["dependency_modules"]
        assert "http://uri/mod_20" in dm
        assert "T_01" in dm["http://uri/mod_20"]["tables"]
        assert dm["http://uri/mod_20"]["variables"] == {"v1": "x"}

    def test_module_with_only_variable_less_tables_is_dropped(self):
        """Modules whose tables all have empty ``variables`` are dropped.

        Regression for B6/S5: previously such modules produced an
        entry in ``dependency_modules`` with an empty ``tables`` map
        which the engine schema (``minProperties: 1``) rejects.
        """
        svc, SR = self._make_svc()
        svc._get_module_tables = lambda vid, release_id=None: {
            "T_STRUCT": {"variables": {}, "open_keys": {}},
        }

        mv = MagicMock()
        mv.module_vid = 20
        mv.version_number = "1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None

        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = [mv]

        sr = SR(
            scopes=[_scope([10, 20])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1234",
        )
        assert info["cross_instance_dependencies"] == []
        assert info["dependency_modules"] == {}

    def test_empty_dependency_modules_when_not_cross(self):
        """dependency_modules is empty for intra-module."""
        svc, SR = self._make_svc()
        sr = SR(
            scopes=[_scope([10])],
            is_cross_module=False,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
        )
        assert info["dependency_modules"] == {}


class TestGetModuleTables:
    """Exercise the real ``_get_module_tables`` (not the stub)."""

    def _chained_session(self):
        svc_session = MagicMock()
        q = svc_session.query.return_value
        q.join.return_value = q
        q.filter.return_value = q
        q.select_from.return_value = q
        q.distinct.return_value = q
        return svc_session, q

    def test_empty_when_no_tables(self):
        """When the first query returns no rows, returns ``{}``."""
        Svc, _ = _load_module()
        session, q = self._chained_session()
        q.all.return_value = []

        svc = Svc(session)
        assert svc._get_module_tables(10) == {}

    def test_populated_with_variables(self):
        """Table rows with variables are collected into the result."""
        Svc, _ = _load_module()
        session, q = self._chained_session()

        tv_row = SimpleNamespace(code="T_01", table_vid=100)
        var_row = (100, 42, "X")
        q.all.side_effect = [[tv_row], [var_row]]

        svc = Svc(session)
        tables = svc._get_module_tables(10)
        assert tables == {
            "T_01": {"variables": {"42": "X"}, "open_keys": {}},
        }

    def test_rows_without_code_are_filtered(self):
        """Rows without a code are dropped from the output mapping."""
        Svc, _ = _load_module()
        session, q = self._chained_session()

        rows = [
            SimpleNamespace(code="T_OK", table_vid=100),
            SimpleNamespace(code=None, table_vid=101),
        ]
        q.all.side_effect = [rows, []]

        svc = Svc(session)
        tables = svc._get_module_tables(10)
        assert list(tables) == ["T_OK"]
        assert tables["T_OK"]["variables"] == {}

    def test_var_row_with_unknown_tvid_is_skipped(self):
        """Variable rows whose tvid isn't in the module are ignored."""
        Svc, _ = _load_module()
        session, q = self._chained_session()

        tv_row = SimpleNamespace(code="T_01", table_vid=100)
        stray = (999, 42, "X")  # tvid not in variables_by_tvid
        q.all.side_effect = [[tv_row], [stray]]

        svc = Svc(session)
        tables = svc._get_module_tables(10)
        assert tables["T_01"]["variables"] == {}

    def test_null_data_type_code_becomes_empty_string(self):
        """A null type code on the var row is normalised to ``""``."""
        Svc, _ = _load_module()
        session, q = self._chained_session()

        tv_row = SimpleNamespace(code="T_01", table_vid=100)
        var_row = (100, 42, None)
        q.all.side_effect = [[tv_row], [var_row]]

        svc = Svc(session)
        tables = svc._get_module_tables(10)
        assert tables["T_01"]["variables"] == {"42": ""}


class TestGetModuleUri:
    """Test URI resolution helper."""

    def test_returns_none_for_missing_module(self):
        Svc, _ = _load_module()
        svc = Svc(MagicMock())
        q = svc.session.query.return_value
        q.filter.return_value.first.return_value = None
        assert svc._get_module_uri(999) is None

    def test_constructs_uri_correctly(self):
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.code = "COREP"
        mv.start_release_id = 5
        mv.module = MagicMock()
        mv.module.framework = MagicMock()
        mv.module.framework.code = "CRR"

        release = MagicMock()
        release.code = "3.4"

        q = svc.session.query.return_value
        q.filter.return_value.first.side_effect = [
            mv,
            release,
        ]

        uri = svc._get_module_uri(10, release_id=5)
        expected = (
            "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/crr/3.4/mod/corep"
        )
        assert uri == expected

    def test_skips_query_when_mv_provided(self):
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.code = "COREP"
        mv.start_release_id = 5
        mv.module = MagicMock()
        mv.module.framework = MagicMock()
        mv.module.framework.code = "CRR"

        release = MagicMock()
        release.code = "3.4"

        q = svc.session.query.return_value
        # Only one query (for Release), not two
        q.filter.return_value.first.return_value = release

        uri = svc._get_module_uri(10, release_id=5, mv=mv)
        assert uri is not None
        assert "corep" in uri

    def test_returns_none_when_no_framework(self):
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.module = MagicMock()
        mv.module.framework = None

        assert svc._get_module_uri(10, mv=mv) is None

    def test_static_csv_hit_strips_json_suffix(self, monkeypatch):
        """Static-mapping hit wins and has its ``.json`` suffix removed."""
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.code = "COREP_Con"
        mv.version_number = "2.0.1"
        mv.module = MagicMock()

        data_stub = sys.modules["dpmcore.data"]
        data_stub.get_module_schema_ref_by_version = MagicMock(
            return_value="http://example.org/corep_con.json",
        )

        uri = svc._get_module_uri(10, mv=mv)
        assert uri == "http://example.org/corep_con"
        data_stub.get_module_schema_ref_by_version.assert_called_once_with(
            "COREP_Con", "2.0.1"
        )

    def test_static_csv_miss_falls_through_to_dynamic(self):
        """When the static lookup returns ``None`` the dynamic path runs.

        ``release_id`` is intentionally omitted here so that the
        ad-hoc-lookup branch (which still consults the CSV) is
        exercised. The script-generation path bypasses the CSV
        entirely; that contract is pinned by
        ``test_release_id_bypasses_static_csv``.
        """
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.code = "COREP"
        mv.version_number = "2.0.1"
        mv.start_release_id = 5
        mv.module = MagicMock()
        mv.module.framework = MagicMock()
        mv.module.framework.code = "CRR"

        data_stub = sys.modules["dpmcore.data"]
        data_stub.get_module_schema_ref_by_version = MagicMock(
            return_value=None,
        )

        release = MagicMock()
        release.code = "3.4"
        q = svc.session.query.return_value
        q.filter.return_value.first.return_value = release

        uri = svc._get_module_uri(10, mv=mv)
        assert uri is not None
        assert uri.endswith("/corep")
        data_stub.get_module_schema_ref_by_version.assert_called_once_with(
            "COREP", "2.0.1"
        )

    def test_release_id_bypasses_static_csv(self):
        """When ``release_id`` is given the CSV mapping is *not* consulted.

        The script-generation path must always root URIs at the target
        release's segment so every module in a script shares the same
        ``/{release}/`` segment as the matching XBRL Report Packages.
        Letting CSV intercept the lookup would reintroduce the skew
        that breaks cross-instance dependency resolution.
        """
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.code = "COREP_Con"
        mv.version_number = "2.0.1"
        mv.start_release_id = 5
        mv.module = MagicMock()
        mv.module.framework = MagicMock()
        mv.module.framework.code = "CRR"

        data_stub = sys.modules["dpmcore.data"]
        # If the CSV were consulted, this would short-circuit the URI.
        data_stub.get_module_schema_ref_by_version = MagicMock(
            return_value="http://example.org/corep_con.json",
        )

        release = MagicMock()
        release.code = "4.2.1"
        q = svc.session.query.return_value
        q.filter.return_value.first.return_value = release

        uri = svc._get_module_uri(10, release_id=42, mv=mv)
        assert uri == (
            "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/crr/4.2.1/mod/"
            "corep_con"
        )
        data_stub.get_module_schema_ref_by_version.assert_not_called()

    def test_release_id_overrides_module_start_release(self):
        """The URI's release segment uses ``release_id``, not start_release.

        Pins the cross-module fix: a module version whose
        ``start_release_id`` predates the script's target release must
        still be rendered with the *target* release in its URI so it
        matches the engine's package URIs.
        """
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.code = "AE"
        mv.version_number = "1.4.0"
        mv.start_release_id = 11  # release 4.2 — older
        mv.module = MagicMock()
        mv.module.framework = MagicMock()
        mv.module.framework.code = "AE"

        data_stub = sys.modules["dpmcore.data"]
        data_stub.get_module_schema_ref_by_version = MagicMock(
            return_value=None,
        )

        target_release = MagicMock()
        target_release.code = "4.2.1"
        q = svc.session.query.return_value
        q.filter.return_value.first.return_value = target_release

        uri = svc._get_module_uri(10, release_id=12, mv=mv)
        assert uri == (
            "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/ae/4.2.1/mod/ae"
        )

    def test_missing_module_code_returns_none(self):
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.code = None
        mv.module = MagicMock()

        assert svc._get_module_uri(10, mv=mv) is None

    def test_no_release_id_falls_back_to_start_release(self):
        """No release_id, no version_number → uses ``mv.start_release_id``.

        Covers the legacy ad-hoc-lookup path where the CSV mapping is
        skipped (no version) and resolution falls through to the
        module version's start release.
        """
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.code = "COREP"
        mv.version_number = None
        mv.start_release_id = 7
        mv.module = MagicMock()
        mv.module.framework = MagicMock()
        mv.module.framework.code = "CRR"

        release = MagicMock()
        release.code = "3.4"
        q = svc.session.query.return_value
        q.filter.return_value.first.return_value = release

        uri = svc._get_module_uri(10, mv=mv)
        assert uri == (
            "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/crr/3.4/mod/corep"
        )

    def test_no_resolvable_release_id_returns_none(self):
        """When no release can be resolved at all, returns ``None``.

        Both ``release_id`` and ``mv.start_release_id`` are missing
        and the CSV mapping doesn't apply (no version) — the resolver
        bottoms out and returns ``None`` rather than constructing a
        URI with a missing segment.
        """
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.code = "COREP"
        mv.version_number = None
        mv.start_release_id = None
        mv.module = MagicMock()
        mv.module.framework = MagicMock()
        mv.module.framework.code = "CRR"

        assert svc._get_module_uri(10, mv=mv) is None

    def test_missing_release_row_returns_none(self):
        """Dynamic path returns None when Release row can't be found."""
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.code = "COREP"
        mv.version_number = None
        mv.start_release_id = 5
        mv.module = MagicMock()
        mv.module.framework = MagicMock()
        mv.module.framework.code = "CRR"

        q = svc.session.query.return_value
        q.filter.return_value.first.return_value = None

        assert svc._get_module_uri(10, release_id=5, mv=mv) is None

    def test_exception_is_logged_and_returns_none(self):
        """Unexpected errors are caught and produce ``None``."""
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        type(mv).code = PropertyMock(side_effect=RuntimeError("boom"))

        assert svc._get_module_uri(10, mv=mv) is None


def _load_ast_generator():
    """Load ASTGeneratorService bypassing ORM chain."""
    # Need extra stubs for ast_generator imports
    for mod_name in [
        "dpmcore.dpm_xl.utils.serialization",
        "dpmcore.services.scope_calculator",
        "dpmcore.services.semantic",
    ]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = MagicMock()

    mod_name = "dpmcore.services.ast_generator"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    spec = importlib.util.spec_from_file_location(
        mod_name,
        _REPO_ROOT / "src/dpmcore/services/ast_generator.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod.ASTGeneratorService


class TestMergeCrossDeps:
    """Test cross-instance dependency merging."""

    def test_new_dep_appended(self):
        Cls = _load_ast_generator()
        existing = []
        new = [
            {
                "modules": [{"URI": "http://a"}],
                "affected_operations": ["v1"],
            }
        ]
        Cls._merge_cross_deps(existing, new)
        assert len(existing) == 1

    def test_duplicate_uri_merges_operations(self):
        Cls = _load_ast_generator()
        existing = [
            {
                "modules": [{"URI": "http://a"}],
                "affected_operations": ["v1"],
            }
        ]
        new = [
            {
                "modules": [{"URI": "http://a"}],
                "affected_operations": ["v2"],
            }
        ]
        Cls._merge_cross_deps(existing, new)
        assert len(existing) == 1
        assert existing[0]["affected_operations"] == [
            "v1",
            "v2",
        ]

    def test_different_uris_both_kept(self):
        Cls = _load_ast_generator()
        existing = [
            {
                "modules": [{"URI": "http://a"}],
                "affected_operations": ["v1"],
            }
        ]
        new = [
            {
                "modules": [{"URI": "http://b"}],
                "affected_operations": ["v2"],
            }
        ]
        Cls._merge_cross_deps(existing, new)
        assert len(existing) == 2

    def test_duplicate_op_not_added_twice(self):
        Cls = _load_ast_generator()
        existing = [
            {
                "modules": [{"URI": "http://a"}],
                "affected_operations": ["v1"],
            }
        ]
        new = [
            {
                "modules": [{"URI": "http://a"}],
                "affected_operations": ["v1"],
            }
        ]
        Cls._merge_cross_deps(existing, new)
        assert existing[0]["affected_operations"] == ["v1"]
