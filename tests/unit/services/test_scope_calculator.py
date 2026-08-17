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
# precondition_expression (issue #279)
# ------------------------------------------------------------------ #


def _paired_svc(main_tables, gate_tables, gate_codes, scope_results):
    """Build a service whose two OperandsChecking passes differ.

    ``scope_results`` is consumed one entry per ``calculate_operation_scope``
    call, so a test can make the combined and baseline runs disagree.
    """
    Svc, _ = _load_module()
    mod = sys.modules["dpmcore.services.scope_calculator"]

    def _oc(tables):
        oc = MagicMock()
        oc.tables = dict.fromkeys(tables, MagicMock())
        oc.preconditions = False
        return oc

    mod.OperandsChecking.side_effect = [_oc(main_tables), _oc(gate_tables)]

    scope_svc = MagicMock()
    scope_svc.calculate_operation_scope.side_effect = [
        (scopes, []) for scopes in scope_results
    ]
    mod.OperationScopeService.return_value = scope_svc
    mod.OperationScopeService.reset_mock()

    svc = Svc(MagicMock())
    svc._syntax = MagicMock()
    svc._syntax.parse.return_value = MagicMock()
    svc._check_release_exists = MagicMock()
    svc._check_tables_hosted = MagicMock()
    mod.required_precondition_codes = MagicMock(return_value=gate_codes)
    return svc, scope_svc, mod


class TestPreconditionExpression:
    """The gate's operands join the resolution by their matching channels."""

    def test_gate_tables_union_into_table_codes(self):
        svc, scope_svc, _ = _paired_svc(
            main_tables=["T_A"],
            gate_tables=["T_B"],
            gate_codes=[],
            scope_results=[[_scope([2])], [_scope([1])]],
        )
        svc.calculate_from_expression(
            expression="main", precondition_expression="gate"
        )
        combined = scope_svc.calculate_operation_scope.call_args_list[0]
        assert combined.kwargs["table_codes"] == ["T_A", "T_B"]
        # The baseline run sees the main expression's operands only.
        baseline = scope_svc.calculate_operation_scope.call_args_list[1]
        assert baseline.kwargs["table_codes"] == ["T_A"]

    def test_gate_codes_union_into_precondition_items(self):
        svc, scope_svc, _ = _paired_svc(
            main_tables=["T_A"],
            gate_tables=[],
            gate_codes=["FI_2"],
            scope_results=[[_scope([2])], [_scope([1])]],
        )
        svc.calculate_from_expression(
            expression="main",
            precondition_items=["FI_1"],
            precondition_expression="gate",
        )
        combined = scope_svc.calculate_operation_scope.call_args_list[0]
        assert combined.kwargs["precondition_items"] == ["FI_1", "FI_2"]
        assert combined.kwargs["table_codes"] == ["T_A"]

    def test_gate_operands_are_deduped_against_the_main_expression(self):
        svc, scope_svc, _ = _paired_svc(
            main_tables=["T_A"],
            gate_tables=["T_A"],
            gate_codes=["FI_1"],
            scope_results=[[_scope([1])]],
        )
        result = svc.calculate_from_expression(
            expression="main",
            precondition_items=["FI_1"],
            precondition_expression="gate",
        )
        # Nothing new: one call only, and no baseline to compare against.
        assert scope_svc.calculate_operation_scope.call_count == 1
        assert result.warning is None

    def test_no_precondition_expression_runs_once_and_warns_nothing(self):
        svc, scope_svc, _ = _paired_svc(
            main_tables=["T_A"],
            gate_tables=[],
            gate_codes=[],
            scope_results=[[_scope([1])]],
        )
        result = svc.calculate_from_expression(expression="main")
        assert scope_svc.calculate_operation_scope.call_count == 1
        assert result.warning is None
        assert result.error_source is None

    def test_warns_when_the_scope_signature_changes(self):
        svc, _, _ = _paired_svc(
            main_tables=["T_A"],
            gate_tables=["T_B"],
            gate_codes=[],
            scope_results=[[_scope([1, 2])], [_scope([1])]],
        )
        result = svc.calculate_from_expression(
            expression="main", precondition_expression="gate"
        )
        assert result.warning is not None
        assert "[1] -> [1, 2]" in result.warning
        assert "tables T_B" in result.warning

    def test_no_warning_when_the_signature_is_unchanged(self):
        # The gate adds an operand, so the baseline is computed — but the
        # resolved scope is identical, so there is nothing to report.
        svc, scope_svc, _ = _paired_svc(
            main_tables=["T_A"],
            gate_tables=["T_B"],
            gate_codes=[],
            scope_results=[[_scope([1])], [_scope([1])]],
        )
        result = svc.calculate_from_expression(
            expression="main", precondition_expression="gate"
        )
        assert scope_svc.calculate_operation_scope.call_count == 2
        assert result.warning is None

    def test_warns_on_re_partitioning_that_module_versions_alone_would_miss(
        self,
    ):
        # Same module versions before and after, but regrouped: FINREP9 alone
        # can no longer evaluate the pair. ``module_versions`` is identical, so
        # only the per-scope signature catches this.
        svc, _, _ = _paired_svc(
            main_tables=["T_A"],
            gate_tables=["T_B"],
            gate_codes=[],
            scope_results=[
                [_scope([1, 2]), _scope([2])],
                [_scope([1]), _scope([2])],
            ],
        )
        result = svc.calculate_from_expression(
            expression="main", precondition_expression="gate"
        )
        assert result.warning is not None

    def test_warns_when_the_gate_empties_the_scope(self):
        svc, _, _ = _paired_svc(
            main_tables=["T_A"],
            gate_tables=[],
            gate_codes=["FI_1"],
            scope_results=[[], [_scope([1])]],
        )
        result = svc.calculate_from_expression(
            expression="main", precondition_expression="gate"
        )
        assert result.total_scopes == 0
        assert not result.has_error
        assert "not evaluable in any module version" in result.warning
        assert "filing indicators FI_1" in result.warning

    def test_gate_parse_failure_is_attributed_and_prefixed(self):
        Svc, _ = _load_module()
        mod = sys.modules["dpmcore.services.scope_calculator"]
        oc = MagicMock()
        oc.tables = {"T_A": MagicMock()}
        oc.preconditions = False
        mod.OperandsChecking.side_effect = [oc, RuntimeError("bad gate")]
        svc = Svc(MagicMock())
        svc._syntax = MagicMock()
        svc._syntax.parse.return_value = MagicMock()
        svc._check_release_exists = MagicMock()

        result = svc.calculate_from_expression(
            expression="main", precondition_expression="gate"
        )
        assert result.has_error
        assert result.error_source == "precondition"
        assert result.error_message == "Precondition: bad gate"

    def test_main_expression_failure_is_not_prefixed(self):
        Svc, _ = _load_module()
        mod = sys.modules["dpmcore.services.scope_calculator"]
        mod.OperandsChecking.side_effect = RuntimeError("bad main")
        svc = Svc(MagicMock())
        svc._syntax = MagicMock()
        svc._syntax.parse.return_value = MagicMock()
        svc._check_release_exists = MagicMock()

        result = svc.calculate_from_expression(
            expression="main", precondition_expression="gate"
        )
        assert result.has_error
        assert result.error_source == "expression"
        assert result.error_message == "bad main"

    def test_combined_failure_blames_the_gate_only_if_the_main_resolves(self):
        svc, scope_svc, _ = _paired_svc(
            main_tables=["T_A"],
            gate_tables=["T_B"],
            gate_codes=[],
            scope_results=[],
        )
        # Combined run raises; the baseline retry succeeds.
        scope_svc.calculate_operation_scope.side_effect = [
            RuntimeError("no modules"),
            ([_scope([1])], []),
        ]
        result = svc.calculate_from_expression(
            expression="main", precondition_expression="gate"
        )
        assert result.error_source == "precondition"
        assert result.error_message == "Precondition: no modules"

    def test_combined_failure_blames_the_expression_if_it_also_fails_alone(
        self,
    ):
        svc, scope_svc, _ = _paired_svc(
            main_tables=["T_A"],
            gate_tables=["T_B"],
            gate_codes=[],
            scope_results=[],
        )
        scope_svc.calculate_operation_scope.side_effect = RuntimeError("boom")
        result = svc.calculate_from_expression(
            expression="main", precondition_expression="gate"
        )
        assert result.error_source == "expression"
        assert result.error_message == "boom"

    def test_a_fresh_scope_service_is_built_per_run(self):
        # OperationScopeService accumulates into self.operation_scopes and
        # never clears it, so sharing one instance would double-count.
        svc, _, mod = _paired_svc(
            main_tables=["T_A"],
            gate_tables=["T_B"],
            gate_codes=[],
            scope_results=[[_scope([1, 2])], [_scope([1])]],
        )
        svc.calculate_from_expression(
            expression="main", precondition_expression="gate"
        )
        assert mod.OperationScopeService.call_count == 2


class TestScopeSignature:
    """The invariant the warning is computed from."""

    def test_empty_scopes(self):
        Svc, _ = _load_module()
        assert Svc._scope_signature([]) == frozenset()

    def test_groups_module_vids_per_scope(self):
        Svc, _ = _load_module()
        assert Svc._scope_signature([_scope([1]), _scope([2])]) == frozenset(
            {frozenset({1}), frozenset({2})}
        )

    def test_distinguishes_re_partitioning(self):
        Svc, _ = _load_module()
        split = Svc._scope_signature([_scope([1]), _scope([2])])
        merged = Svc._scope_signature([_scope([1, 2])])
        assert split != merged


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
            svc._get_module_uri = lambda module_vid, mv=None: uri_map.get(
                module_vid
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

    def test_different_operations_are_not_alternatives(self):
        """Sole-external of *different* operations is not an alternative.

        #202: two modules that are each the sole external of a separate
        operation share no operation and so are not interchangeable.
        Each ``ScopeResult`` is one operation.
        """
        svc, SR = self._make_svc(
            {10: "http://uri/a", 20: "http://uri/b"},
        )
        sr1 = SR(scopes=[_scope([1, 10])])
        sr2 = SR(scopes=[_scope([1, 20])])
        result = svc.detect_alternative_dependencies(
            scope_results=[sr1, sr2], primary_module_vid=1
        )
        assert result == []

    def test_same_pair_across_operations_deduped(self):
        """A pair that is an alternative in two operations appears once."""
        svc, SR = self._make_svc(
            {10: "http://uri/a", 20: "http://uri/b"},
        )
        sr1 = SR(scopes=[_scope([1, 10]), _scope([1, 20])])
        sr2 = SR(scopes=[_scope([1, 10]), _scope([1, 20])])
        result = svc.detect_alternative_dependencies(
            scope_results=[sr1, sr2], primary_module_vid=1
        )
        assert result == [sorted(["http://uri/a", "http://uri/b"])]

    def test_co_occurrence_in_other_operation_vetoes_pair(self):
        """Co-occurring in *any* operation disqualifies a pair."""
        svc, SR = self._make_svc(
            {10: "http://uri/a", 20: "http://uri/b"},
        )
        # Op 1: 10 and 20 look like alternatives.
        sr1 = SR(scopes=[_scope([1, 10]), _scope([1, 20])])
        # Op 2: 10 and 20 are required together -> conjunctive, not alt.
        sr2 = SR(scopes=[_scope([1, 10, 20])])
        result = svc.detect_alternative_dependencies(
            scope_results=[sr1, sr2], primary_module_vid=1
        )
        assert result == []

    def test_valid_module_uris_drops_dangling_pair(self):
        """A pair naming a non-dependency module is dropped (#202)."""
        svc, SR = self._make_svc(
            {10: "http://uri/a", 20: "http://uri/b"},
        )
        sr = SR(scopes=[_scope([1, 10]), _scope([1, 20])])
        # Only module 10's URI is a genuine dependency module.
        result = svc.detect_alternative_dependencies(
            scope_results=[sr],
            primary_module_vid=1,
            valid_module_uris={"http://uri/a"},
        )
        assert result == []

    def test_valid_module_uris_keeps_genuine_pair(self):
        """A pair whose modules are both dependencies survives (#202)."""
        svc, SR = self._make_svc(
            {10: "http://uri/a", 20: "http://uri/b"},
        )
        sr = SR(scopes=[_scope([1, 10]), _scope([1, 20])])
        result = svc.detect_alternative_dependencies(
            scope_results=[sr],
            primary_module_vid=1,
            valid_module_uris={"http://uri/a", "http://uri/b"},
        )
        assert result == [sorted(["http://uri/a", "http://uri/b"])]

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

    @staticmethod
    def _assert_disjoint(result):
        """No module URI appears in more than one group."""
        seen: set = set()
        for group in result:
            assert not (seen & set(group)), "groups overlap"
            seen |= set(group)

    def test_three_interchangeable_modules_form_one_group(self):
        """3+ interchangeable modules collapse to one disjoint group (#242).

        A, B and C are each the sole external of the same operation and
        never co-occur, so they are mutually interchangeable. This must
        surface as the single group ``[[A, B, C]]``, not the overlapping
        pairs ``[[A, B], [A, C], [B, C]]``.
        """
        svc, SR = self._make_svc(
            {10: "http://uri/a", 20: "http://uri/b", 30: "http://uri/c"},
        )
        sr = SR(
            scopes=[
                _scope([1, 10]),
                _scope([1, 20]),
                _scope([1, 30]),
            ],
        )
        result = svc.detect_alternative_dependencies(
            scope_results=[sr], primary_module_vid=1
        )
        assert result == [
            sorted(["http://uri/a", "http://uri/b", "http://uri/c"])
        ]
        self._assert_disjoint(result)

    def test_disjoint_alternative_groups(self):
        """Independent interchangeable sets stay as separate groups (#242)."""
        svc, SR = self._make_svc(
            {
                10: "http://uri/a",
                20: "http://uri/b",
                30: "http://uri/c",
                40: "http://uri/d",
            },
        )
        # Two operations, each with its own pair of interchangeables; the
        # two pairs never share an operation, so they must not merge.
        sr1 = SR(scopes=[_scope([1, 10]), _scope([1, 20])])
        sr2 = SR(scopes=[_scope([1, 30]), _scope([1, 40])])
        result = svc.detect_alternative_dependencies(
            scope_results=[sr1, sr2], primary_module_vid=1
        )
        assert result == [
            sorted(["http://uri/a", "http://uri/b"]),
            sorted(["http://uri/c", "http://uri/d"]),
        ]
        self._assert_disjoint(result)

    def test_non_transitive_merges_into_one_group(self):
        """Non-transitive alternatives merge via connected components (#242).

        A-B and B-C are interchangeable, but A and C co-occur (so they are
        conjunctive, not alternatives). Connected components keep the
        result disjoint by merging all three into one group.
        """
        svc, SR = self._make_svc(
            {10: "http://uri/a", 20: "http://uri/b", 30: "http://uri/c"},
        )
        sr = SR(
            scopes=[
                _scope([1, 10]),
                _scope([1, 20]),
                _scope([1, 30]),
                _scope([1, 10, 30]),  # A and C required together.
            ],
        )
        result = svc.detect_alternative_dependencies(
            scope_results=[sr], primary_module_vid=1
        )
        assert result == [
            sorted(["http://uri/a", "http://uri/b", "http://uri/c"])
        ]
        self._assert_disjoint(result)


# ------------------------------------------------------------------ #
# detect_cross_module_dependencies (Fix 2)
# ------------------------------------------------------------------ #


class TestDetectCrossModuleDependencies:
    """Test the full dependency_info building."""

    def _make_svc(self):
        Svc, SR = _load_module()
        svc = Svc(MagicMock())
        svc._get_module_uri = lambda module_vid, mv=None: (
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

    def test_primary_in_no_scope_is_not_intra(self):
        # Primary module 10 is in no scope (the cross-module scope is
        # 20+30), so it must not be classified intra-instance.
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
        assert info["intra_instance_validations"] == []
        assert info["cross_instance_dependencies"] == []

    @staticmethod
    def _mv(vid):
        mv = MagicMock()
        mv.module_vid = vid
        mv.version_number = "1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None
        return mv

    def test_alternative_deps_dropped_when_not_dependency_modules(self):
        """A pair naming a non-dependency module is dropped (#202).

        With no variable-carrying tables, modules 20 and 30 never become
        dependency modules, so they must not surface as alternatives even
        though they are sole-external and never co-occur.
        """
        svc, SR = self._make_svc()  # _get_module_tables -> {}

        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = [self._mv(20), self._mv(30)]

        sr = SR(
            scopes=[_scope([10, 20]), _scope([10, 30])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1",
        )
        assert info["dependency_modules"] == {}
        assert info["alternative_dependencies"] == []

    def test_alternative_deps_kept_when_dependency_modules(self):
        """Genuine dependency modules surface as alternatives (#202)."""
        svc, SR = self._make_svc()
        svc._get_module_tables = lambda vid, release_id=None: {
            "T_01": {"variables": {"v1": "x"}, "open_keys": {}},
        }

        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = [self._mv(20), self._mv(30)]

        sr = SR(
            scopes=[_scope([10, 20]), _scope([10, 30])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1",
        )
        assert set(info["dependency_modules"]) == {
            "http://uri/mod_20",
            "http://uri/mod_30",
        }
        assert info["alternative_dependencies"] == [
            sorted(["http://uri/mod_20", "http://uri/mod_30"])
        ]

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
        # Distinct home/dep tables — the PR #276 shared-table exclusion
        # would strip a fully overlapping ``T_01`` from the dep side.
        svc._get_module_tables = lambda vid, release_id=None: (
            {"HOME_T": {"variables": {"vh": "x"}, "open_keys": {}}}
            if vid == 10
            else {
                "T_01": {
                    "variables": {"v1": "x"},
                    "open_keys": {},
                }
            }
        )

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

    def test_referenced_home_variables_declared(self):
        """Regression for #251: a cross-validation's home-module operand
        datapoints must appear in the dependency module's ``variables``
        map, or the engine cannot build the home operand.
        """
        svc, SR = self._make_svc()
        # Distinct home/dep tables — with the shared-table exclusion
        # (PR #276) a full-overlap mock would drop the dep's F_01.03.
        svc._get_module_tables = lambda vid, release_id=None: (
            {"C_01.00": {"variables": {"32673": "m"}, "open_keys": {}}}
            if vid == 10
            else {
                "F_01.03": {
                    "variables": {"56987": "m"},
                    "open_keys": {},
                }
            }
        )

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
            # {tC_01.00,...} <= {tF_01.03,...}: 32673 is the home operand.
            referenced_variables={"32673": "m", "56987": "m"},
        )
        dep = info["dependency_modules"]["http://uri/mod_20"]
        assert dep["variables"] == {"32673": "m", "56987": "m"}
        # tables stay dependency-side only.
        assert set(dep["tables"]) == {"F_01.03"}

    def test_declares_only_referenced_tables_and_datapoints(self):
        """Regression for #250: a dependency module is declared as the
        subset the cross-rules reference, not whole.
        """
        svc, SR = self._make_svc()
        # Distinct home/dep tables (see PR #276 shared-table exclusion).
        svc._get_module_tables = lambda vid, release_id=None: (
            {"G_01.00": {"variables": {"500": "m"}, "open_keys": {}}}
            if vid == 10
            else {
                "F_22.02": {
                    "variables": {"1": "m", "2": "m", "3": "m"},
                    "open_keys": {"qAS": "e"},
                },
                # Referenced by no cross-rule: must not be declared.
                "F_99.00": {"variables": {"9": "m"}, "open_keys": {}},
            }
        )

        mv = MagicMock()
        mv.module_vid = 20
        mv.version_number = "1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None

        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = [mv]

        info = svc.detect_cross_module_dependencies(
            scope_result=SR(scopes=[_scope([10, 20])], is_cross_module=True),
            primary_module_vid=10,
            referenced_tables={"G_01.00", "F_22.02"},
            referenced_variables={"1": "m", "500": "m"},
        )
        dep = info["dependency_modules"]["http://uri/mod_20"]
        assert set(dep["tables"]) == {"F_22.02"}
        assert dep["tables"]["F_22.02"]["variables"] == {"1": "m"}
        # open_keys survive the narrowing (#122).
        assert dep["tables"]["F_22.02"]["open_keys"] == {"qAS": "e"}
        # 500 is the home operand grafted in by #251.
        assert dep["variables"] == {"1": "m", "500": "m"}

    def test_whole_module_declared_when_no_refs_supplied(self):
        """Callers passing no reference info keep the unnarrowed module."""
        svc, SR = self._make_svc()
        # Distinct home/dep tables (see PR #276 shared-table exclusion).
        svc._get_module_tables = lambda vid, release_id=None: (
            {"HOME_T": {"variables": {"vh": "m"}, "open_keys": {}}}
            if vid == 10
            else {
                "F_22.02": {"variables": {"1": "m"}, "open_keys": {}},
                "F_99.00": {"variables": {"9": "m"}, "open_keys": {}},
            }
        )

        mv = MagicMock()
        mv.module_vid = 20
        mv.version_number = "1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None

        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = [mv]

        info = svc.detect_cross_module_dependencies(
            scope_result=SR(scopes=[_scope([10, 20])], is_cross_module=True),
            primary_module_vid=10,
        )
        dep = info["dependency_modules"]["http://uri/mod_20"]
        assert set(dep["tables"]) == {"F_22.02", "F_99.00"}

    def test_dependency_kept_whole_when_narrowing_empties_it(self):
        """Narrowing must never drop a genuine cross-instance dependency:
        if nothing matches, the module is declared unnarrowed.
        """
        svc, SR = self._make_svc()
        # Distinct home/dep tables (see PR #276 shared-table exclusion).
        svc._get_module_tables = lambda vid, release_id=None: (
            {"G_01.00": {"variables": {"777": "m"}, "open_keys": {}}}
            if vid == 10
            else {
                "F_22.02": {"variables": {"1": "m"}, "open_keys": {}},
            }
        )

        mv = MagicMock()
        mv.module_vid = 20
        mv.version_number = "1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None

        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = [mv]

        info = svc.detect_cross_module_dependencies(
            scope_result=SR(scopes=[_scope([10, 20])], is_cross_module=True),
            primary_module_vid=10,
            referenced_tables={"Z_00.00"},
            referenced_variables={"777": "m"},
        )
        dep = info["dependency_modules"]["http://uri/mod_20"]
        assert set(dep["tables"]) == {"F_22.02"}
        assert dep["variables"] == {"1": "m", "777": "m"}

    def test_module_definition_wins_over_referenced_type(self):
        """A datapoint the dependency module defines keeps that type."""
        svc, SR = self._make_svc()
        # Distinct home/dep tables (see PR #276 shared-table exclusion).
        svc._get_module_tables = lambda vid, release_id=None: (
            {}
            if vid == 10
            else {"F_01.03": {"variables": {"56987": "m"}, "open_keys": {}}}
        )

        mv = MagicMock()
        mv.module_vid = 20
        mv.version_number = "1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None

        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = [mv]

        info = svc.detect_cross_module_dependencies(
            scope_result=SR(scopes=[_scope([10, 20])], is_cross_module=True),
            primary_module_vid=10,
            referenced_variables={"56987": ""},
        )
        dep = info["dependency_modules"]["http://uri/mod_20"]
        assert dep["variables"] == {"56987": "m"}

    def test_dependency_table_open_keys_propagate(self):
        """Regression for #122: a dependency module's table entries must
        keep their ``open_keys`` so the engine can join on them.
        """
        svc, SR = self._make_svc()
        # Distinct home/dep tables (see PR #276 shared-table exclusion).
        svc._get_module_tables = lambda vid, release_id=None: (
            {"HOME_T": {"variables": {"vh": "s"}, "open_keys": {}}}
            if vid == 10
            else {
                "C_06.02": {
                    "variables": {"5486578": "s"},
                    "open_keys": {"qEGS": "e", "qLGS": "s"},
                }
            }
        )

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
        dep = info["dependency_modules"]["http://uri/mod_20"]
        assert dep["tables"]["C_06.02"]["open_keys"] == {
            "qEGS": "e",
            "qLGS": "s",
        }

    def test_primary_module_never_a_dependency(self):
        """Regression for #122: the primary module must not appear in
        its own cross dependencies or ``dependency_modules``.
        """
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
            operation_code="EGDQ_0131",
        )
        assert "http://uri/mod_10" not in info["dependency_modules"]
        dep_uris = {
            m["URI"]
            for cd in info["cross_instance_dependencies"]
            for m in cd["modules"]
        }
        assert dep_uris == {"http://uri/mod_20"}

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

        uri = svc._get_module_uri(10)
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

        uri = svc._get_module_uri(10, mv=mv)
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

        On a CSV miss the release segment falls through to the module
        version's ``start_release_id``. The CSV is always consulted
        first; the hit-wins side of that contract is pinned by
        ``test_static_csv_hit_strips_json_suffix``.
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

    def test_start_release_seeds_segment(self):
        """The URI's release segment uses start_release, not the report.

        Pins the taxonomy-URL fix: a module version whose
        ``start_release_id`` predates the report release keeps its
        *original* release in its URI, because no taxonomy is published
        for that unchanged module under the later report release. An
        unchanged ``ae`` stays at ``.../ae/4.2/mod/ae`` inside a 4.2.1
        report. On a CSV miss the resolver returns ``mv.start_release_id``.
        """
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.code = "AE"
        mv.version_number = "1.4.0"
        mv.start_release_id = 11  # release 4.2 — older than the report
        mv.module = MagicMock()
        mv.module.framework = MagicMock()
        mv.module.framework.code = "AE"

        data_stub = sys.modules["dpmcore.data"]
        data_stub.get_module_schema_ref_by_version = MagicMock(
            return_value=None,
        )

        # On a CSV miss the segment is seeded from start_release_id (11),
        # the release the module version was introduced in.
        assert svc._resolve_uri_release_id(mv, "AE") == 11

        start_release = MagicMock()
        start_release.code = "4.2"  # 4.2, not a later 4.2.1 report release
        q = svc.session.query.return_value
        q.filter.return_value.first.return_value = start_release

        uri = svc._get_module_uri(10, mv=mv)
        assert uri == (
            "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/ae/4.2/mod/ae"
        )

    def test_missing_module_code_returns_none(self):
        Svc, _ = _load_module()
        svc = Svc(MagicMock())

        mv = MagicMock()
        mv.code = None
        mv.module = MagicMock()

        assert svc._get_module_uri(10, mv=mv) is None

    def test_falls_back_to_start_release(self):
        """No version_number → uses ``mv.start_release_id``.

        Covers the path where the CSV mapping is skipped (no version)
        and resolution falls through to the module version's start
        release.
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

    def test_no_resolvable_release_returns_none(self):
        """When no release can be resolved at all, returns ``None``.

        ``mv.start_release_id`` is missing and the CSV mapping doesn't
        apply (no version) — the resolver bottoms out and returns
        ``None`` rather than constructing a URI with a missing segment.
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

        assert svc._get_module_uri(10, mv=mv) is None

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
