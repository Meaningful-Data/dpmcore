"""Tests for the shared-home-table exclusion added in PR #276.

Kept in a separate module because the stub chain in
``test_scope_calculator.py`` is intentionally minimal (it lets the
existing tests target very specific paths); asserting on
``dependency_modules[<uri>].tables`` needs a slightly wider stub set
plus a real ``chunked_in`` pass-through so the ``ModuleVersion`` batch
lookup actually materialises. Isolating the setup here avoids
regressing any of those existing tests.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _patch_orm(monkeypatch):
    """Stub the ORM/service chain the module pulls in at import time.

    Same shape as ``test_scope_calculator._patch_orm`` plus the two
    modules that ``scope_calculator`` transitively imports and that
    ``test_scope_calculator`` intentionally leaves real
    (``dpm_xl.utils.filters`` for ``resolve_release_id``,
    ``orm.query_utils`` for ``chunked_in``). Those two only exist to
    let the code under test reach the branches we exercise below.
    """
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
        "dpmcore.orm.query_utils",
        "dpmcore.orm.rendering",
        "dpmcore.orm.variables",
        "dpmcore.orm.glossary",
        "dpmcore.errors",
        "dpmcore.dpm_xl",
        "dpmcore.dpm_xl.ast",
        "dpmcore.dpm_xl.ast.operands",
        "dpmcore.dpm_xl.utils",
        "dpmcore.dpm_xl.utils.filters",
        "dpmcore.dpm_xl.utils.scopes_calculator",
        "dpmcore.services",
        "dpmcore.services.syntax",
    ]:
        monkeypatch.setitem(sys.modules, mod_name, MagicMock())

    canonical = "dpmcore.services.scope_calculator"
    snapshot = sys.modules.get(canonical)
    yield
    # Restore whatever the outer test session had registered so
    # follow-up files (which import the real module) aren't left
    # with our stub-deps copy.
    if snapshot is not None:
        sys.modules[canonical] = snapshot
    else:
        sys.modules.pop(canonical, None)


def _load_module():
    mod_name = "dpmcore.services.scope_calculator"
    sys.modules.pop(mod_name, None)
    spec = importlib.util.spec_from_file_location(
        mod_name,
        _REPO_ROOT / "src/dpmcore/services/scope_calculator.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    # ``chunked_in`` is stubbed at the parent module scope by
    # ``_patch_orm`` (its parent ``dpmcore.orm.query_utils`` is a
    # ``MagicMock``), so a naked call returns a ``MagicMock`` that
    # iterates as empty. Bind a real pass-through so the loop that
    # materialises ``ModuleVersion`` rows in
    # ``detect_cross_module_dependencies`` actually sees them.
    mod.chunked_in = lambda query, col, values: query.filter(
        col.in_(values)
    ).all()
    return mod.ScopeCalculatorService, mod.ScopeResult


def _scope(module_vids):
    comps = [SimpleNamespace(module_vid=v) for v in module_vids]
    return SimpleNamespace(operation_scope_compositions=comps)


class TestSharedHomeTableExclusion:
    """PR #276 review follow-up: shared home-module tables must be
    excluded from ``dependency_modules[<dep>].tables``, unconditionally
    where the dep is still declarable via other means.
    """

    def _make_svc(self):
        Svc, SR = _load_module()
        svc = Svc(MagicMock())
        svc._get_module_uri = lambda module_vid, mv=None: (
            f"http://uri/mod_{module_vid}"
        )
        svc._get_module_tables = lambda module_vid, release_id=None: {}
        return svc, SR

    def _cross_pair(self, SR, home_vid, dep_vid):
        return SR(
            scopes=[_scope([home_vid, dep_vid])],
            is_cross_module=True,
        )

    def _wire_dep_mv(self, svc, dep_vid, code="MOD_EXT"):
        mv = MagicMock()
        mv.module_vid = dep_vid
        mv.code = code
        mv.version_number = "1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None
        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = [mv]

    def test_shared_home_table_excluded_from_dep_module(self):
        """A table declared by both home and dep must appear only under
        the home declaration — ``dependency_modules[<dep>].tables`` must
        drop it (PR #276).
        """
        svc, SR = self._make_svc()
        home_tables = {
            "SHARED_T": {"variables": {"v_shared": "x"}, "open_keys": {}},
            "HOME_ONLY": {"variables": {"v_home": "x"}, "open_keys": {}},
        }
        dep_tables = {
            "SHARED_T": {"variables": {"v_shared": "x"}, "open_keys": {}},
            "DEP_ONLY": {"variables": {"v_dep": "x"}, "open_keys": {}},
        }
        svc._get_module_tables = lambda vid, release_id=None: (
            home_tables if vid == 10 else dep_tables
        )
        self._wire_dep_mv(svc, dep_vid=20)

        info = svc.detect_cross_module_dependencies(
            scope_result=self._cross_pair(SR, 10, 20),
            primary_module_vid=10,
            operation_code="v1234",
        )
        dep_module = next(iter(info["dependency_modules"].values()))
        assert "SHARED_T" not in dep_module["tables"]
        assert "DEP_ONLY" in dep_module["tables"]

    def test_full_overlap_dep_still_declared_via_referenced_variables(self):
        """Regression: when *every* dep table is shared with the home
        AND ``referenced_variables`` is populated, the exclusion must
        still fire. The previous ``if filtered:`` fallback kept the
        shared rows, re-introducing the duplicate-declaration bug this
        PR closes. The dep stays declarable via ``referenced_variables``
        (#251) populating its ``variables`` map even with an empty
        ``tables`` map.
        """
        svc, SR = self._make_svc()
        shared_table = {"variables": {"v1": "x"}, "open_keys": {}}
        svc._get_module_tables = lambda vid, release_id=None: {
            "SHARED_T": shared_table,
        }
        self._wire_dep_mv(svc, dep_vid=20)

        info = svc.detect_cross_module_dependencies(
            scope_result=self._cross_pair(SR, 10, 20),
            primary_module_vid=10,
            operation_code="v1234",
            referenced_variables={"v1": "x"},
            referenced_tables={"SHARED_T"},
        )
        dep_module = next(iter(info["dependency_modules"].values()))
        assert dep_module["tables"] == {}
        assert dep_module["variables"] == {"v1": "x"}

    def test_full_overlap_dep_stripped_when_no_referenced_variables(self):
        """When *every* dep table is shared with the home, the exclusion
        still applies unconditionally — the shared tables never leak onto
        the dep side, even when the caller supplied no
        ``referenced_variables`` to repopulate ``variables``. The dep
        still surfaces in ``cross_instance_dependencies`` via its
        ``URI``, so a genuine cross-instance dependency is not silently
        dropped; it just carries an empty ``tables``/``variables`` pair
        the caller can fill in downstream.
        """
        svc, SR = self._make_svc()
        svc._get_module_tables = lambda vid, release_id=None: {
            "SHARED_T": {"variables": {"v1": "x"}, "open_keys": {}},
        }
        self._wire_dep_mv(svc, dep_vid=20)

        info = svc.detect_cross_module_dependencies(
            scope_result=self._cross_pair(SR, 10, 20),
            primary_module_vid=10,
            operation_code="v1234",
        )
        # The dep is still declared as a cross-instance dependency (URI
        # in the cross_deps list), only its ``tables``/``variables``
        # payload is empty.
        cross_uris = [
            m["URI"]
            for c in info["cross_instance_dependencies"]
            for m in c["modules"]
        ]
        assert cross_uris, (
            "dep must still surface in cross_instance_dependencies"
        )
        dep_module = next(iter(info["dependency_modules"].values()))
        assert dep_module["tables"] == {}, (
            "shared table must not leak onto the dep side"
        )

    def test_home_module_tables_parameter_skips_internal_recompute(self):
        """When the caller supplies ``home_module_tables`` the method
        must use it directly rather than re-running
        ``_get_module_tables`` for the primary vid — the per-script
        single-fetch contract the reviewer requested. The caller loops
        over N ops with a fixed ``primary_module_vid`` and the
        home-table lookup should not repeat N times.
        """
        svc, SR = self._make_svc()

        get_calls: list[int] = []

        def _tracking_get(vid, release_id=None):
            get_calls.append(vid)
            if vid == 10:
                return {
                    "HOME_ONLY": {
                        "variables": {"v_home": "x"},
                        "open_keys": {},
                    },
                }
            return {
                "SHARED_T": {
                    "variables": {"v_shared": "x"},
                    "open_keys": {},
                },
                "DEP_ONLY": {"variables": {"v_dep": "x"}, "open_keys": {}},
            }

        svc._get_module_tables = _tracking_get
        self._wire_dep_mv(svc, dep_vid=20)

        info = svc.detect_cross_module_dependencies(
            scope_result=self._cross_pair(SR, 10, 20),
            primary_module_vid=10,
            operation_code="v1234",
            home_module_tables={"SHARED_T"},
        )
        # The primary vid was NOT fetched to derive its table set: the
        # only remaining ``_get_module_tables`` call is the dep-side
        # composition query.
        assert 10 not in get_calls
        dep_module = next(iter(info["dependency_modules"].values()))
        assert "SHARED_T" not in dep_module["tables"]
        assert "DEP_ONLY" in dep_module["tables"]

    def test_op_referencing_only_a_shared_table_narrows_before_exclusion(self):
        """Regression @andres-sole: the shared-table exclusion must run
        *after* ``_narrow_dependency_tables``. When an operation
        references only a shared table (the classic
        ``IF_CLASS2 - COREP_OF`` shape at the fixture DB, op referencing
        only ``C_18.00``) running exclusion first drops the referenced
        table before narrowing sees it: narrowing then finds no matching
        referenced table and falls back to the un-narrowed
        (already-excluded) set, so the dep either declares nothing at
        all or reintroduces the shared table via the module-wide
        fallback. The correct order is narrow → exclude, so the operand
        is captured by narrowing and only the *narrowed* result is
        stripped of its shared entries — leaving an empty ``tables``
        map that ``referenced_variables`` (#251) still fills.
        """
        svc, SR = self._make_svc()
        shared_table = {"variables": {"v_shared_var": "x"}, "open_keys": {}}
        home_tables = {
            "SHARED_T": shared_table,
            "HOME_ONLY": {"variables": {"v_home": "x"}, "open_keys": {}},
        }
        dep_tables = {
            "SHARED_T": shared_table,
            "DEP_ONLY_UNREF": {
                "variables": {"v_unref": "x"},
                "open_keys": {},
            },
        }
        svc._get_module_tables = lambda vid, release_id=None: (
            home_tables if vid == 10 else dep_tables
        )
        self._wire_dep_mv(svc, dep_vid=20)

        info = svc.detect_cross_module_dependencies(
            scope_result=self._cross_pair(SR, 10, 20),
            primary_module_vid=10,
            operation_code="v1234",
            # The op references only the shared table's datapoint.
            referenced_tables={"SHARED_T"},
            referenced_variables={"v_shared_var": "x"},
        )
        dep_module = next(iter(info["dependency_modules"].values()))
        # The shared table is stripped from the dep declaration.
        assert "SHARED_T" not in dep_module["tables"]
        # And the un-referenced dep-only table is NOT re-introduced by a
        # narrowing-empty fallback (which would happen if exclusion ran
        # before narrowing, dropping the operand's only table so
        # narrowing returns empty and the module-wide fallback kicks in).
        assert "DEP_ONLY_UNREF" not in dep_module["tables"]
        assert dep_module["tables"] == {}
        # The operand still resolves via ``variables`` (#251).
        assert dep_module["variables"] == {"v_shared_var": "x"}
