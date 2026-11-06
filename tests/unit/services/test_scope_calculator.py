"""Tests for ScopeCalculatorService.

Covers the scope calculation and its precondition expression, the #182
ghost module versions and the module URI resolution.
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

    # ghost_fallbacks defaults to "no ghosts this release" so every
    # test not specifically exercising #182 ghost-fallback handling
    # sees the old, pre-#182-fix behavior unchanged.
    model_queries_stub = MagicMock()
    model_queries_stub.ModuleVersionQuery.ghost_fallbacks = MagicMock(
        return_value={}
    )
    monkeypatch.setitem(
        sys.modules, "dpmcore.dpm_xl.model_queries", model_queries_stub
    )

    for mod_name in [
        "dpmcore",
        "dpmcore.connection",
        "dpmcore.orm",
        "dpmcore.orm.infrastructure",
        "dpmcore.orm.packaging",
        "dpmcore.orm.operations",
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

    # Snapshot the canonical sys.modules entry the helper below pollutes,
    # so the teardown restores it. The helper registers a stub-deps copy
    # under the real module name; without a restore, follow-up test files
    # see that stub copy (or a missing entry) and patches no longer line
    # up with the modules the production code re-imports at call time.
    canonical_names = ("dpmcore.services.scope_calculator",)
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
# build_scope_result_from_db (dpmcore#364)
# ------------------------------------------------------------------ #


def _op_scope(scope_id, module_vids):
    """A fake ``OperationScope`` row: id + composed module VIDs."""
    return SimpleNamespace(
        operation_scope_id=scope_id,
        operation_scope_compositions=[
            SimpleNamespace(operation_scope_id=scope_id, module_vid=v)
            for v in module_vids
        ],
    )


class TestBuildScopeResultFromDb:
    """Rebuilding a ``ScopeResult`` from persisted ``OperationScope``
    rows instead of re-parsing the expression (dpmcore#364).
    """

    def _make_svc(self):
        Svc, _ = _load_module()
        return Svc(MagicMock())

    @staticmethod
    def _wire_scopes(svc, scopes, phantom_rows=None):
        """Wire the two distinct query shapes this method issues.

        The scope fetch goes through ``.filter(...).all()``; the
        phantom check goes through ``.join(...).filter(...)
        .filter(...).all()`` — a different mock attribute chain, so
        both are configured independently on the same shared
        ``session.query`` mock without colliding.
        """
        q = svc.session.query.return_value
        q.filter.return_value.all.return_value = scopes
        (
            q.join.return_value.filter.return_value.filter.return_value.all.return_value
        ) = phantom_rows or []

    def test_single_module_scope(self):
        svc = self._make_svc()
        self._wire_scopes(svc, [_op_scope(1, [10])])
        result = svc.build_scope_result_from_db(
            operation_vid=100, primary_module_vid=10
        )
        assert result.total_scopes == 1
        assert not result.is_cross_module
        assert result.module_versions == [10]
        assert not result.has_error

    def test_cross_module_scope(self):
        svc = self._make_svc()
        self._wire_scopes(svc, [_op_scope(1, [10, 20])])
        result = svc.build_scope_result_from_db(
            operation_vid=100, primary_module_vid=10
        )
        assert result.is_cross_module
        assert result.module_versions == [10, 20]

    def test_no_active_scope_raises(self):
        svc = self._make_svc()
        self._wire_scopes(svc, [])
        mod = sys.modules["dpmcore.services.scope_calculator"]
        with pytest.raises(mod.UnsupportedDbScope):
            svc.build_scope_result_from_db(
                operation_vid=100, primary_module_vid=10
            )

    def test_only_phantom_paired_scope_raises(self):
        """The sole scope pairs the primary with a phantom module
        version — nothing usable survives the exclusion.
        """
        svc = self._make_svc()
        self._wire_scopes(
            svc,
            [_op_scope(1, [10, 20])],
            phantom_rows=[(1, 20, "2026-01-01", "2026-01-01")],
        )
        mod = sys.modules["dpmcore.services.scope_calculator"]
        with pytest.raises(mod.UnsupportedDbScope):
            svc.build_scope_result_from_db(
                operation_vid=100, primary_module_vid=10
            )

    def test_phantom_scope_excluded_genuine_one_kept(self):
        svc = self._make_svc()
        self._wire_scopes(
            svc,
            [_op_scope(1, [10, 20]), _op_scope(2, [10, 30])],
            phantom_rows=[
                (1, 20, "2026-01-01", "2026-01-01"),
                (2, 30, "2020-01-01", None),
            ],
        )
        result = svc.build_scope_result_from_db(
            operation_vid=100, primary_module_vid=10
        )
        assert result.total_scopes == 1
        assert result.module_versions == [10, 30]

    def test_phantom_with_fallback_not_rescued_without_a_release(self):
        """No *release_id* at all means no #182 fallback map can be
        built (there is no release to look ghost-fallbacks up for), so
        a phantom "other" module still voids the scope — matches the
        pre-#182 behaviour exactly (mdpm's reference, which has no
        #182 equivalent, always ends up here).
        """
        svc = self._make_svc()
        self._wire_scopes(
            svc,
            [_op_scope(1, [10, 999])],
            phantom_rows=[(1, 999, "2026-01-01", "2026-01-01")],
        )
        mq = sys.modules["dpmcore.dpm_xl.model_queries"]
        mq.ModuleVersionQuery.ghost_fallbacks = MagicMock(
            return_value={777: [999]}
        )
        mod = sys.modules["dpmcore.services.scope_calculator"]
        with pytest.raises(mod.UnsupportedDbScope):
            svc.build_scope_result_from_db(
                operation_vid=100,
                primary_module_vid=10,
            )

    def test_phantom_with_fallback_rescued(self):
        """Given a *release_id*, a phantom "other" module with a #182
        fallback is rescued, and the composition's ``module_vid`` is
        substituted for the fallback's, since the ghost itself has no
        table/URI structure to resolve a cross-module dependency
        against (Andrés's review on PR #396 — COREP_OF 4.0.0 losing
        v0655_m/v0656_m, paired with ghost COREP_LE 3.2.0). Applies
        regardless of whether the caller named an explicit ``--release``
        or one was auto-resolved — per issue #182, the fallback must
        apply consistently on every path.
        """
        svc = self._make_svc()
        self._wire_scopes(
            svc,
            [_op_scope(1, [10, 999])],
            phantom_rows=[(1, 999, "2026-01-01", "2026-01-01")],
        )
        mq = sys.modules["dpmcore.dpm_xl.model_queries"]
        mq.ModuleVersionQuery.ghost_fallbacks = MagicMock(
            return_value={777: [999]}
        )
        result = svc.build_scope_result_from_db(
            operation_vid=100,
            primary_module_vid=10,
            release_id=1,
        )
        assert result.total_scopes == 1
        assert result.module_versions == [10, 777]


class TestPhantomPairedScopeIds:
    """Direct coverage of the exclusion rule ``build_scope_result_from_db``
    and ``ASTGeneratorService._discover_module_validations`` share.
    """

    def _make_svc(self):
        Svc, _ = _load_module()
        return Svc, Svc(MagicMock())

    @staticmethod
    def _wire(svc, rows):
        q = svc.session.query.return_value
        chain = q.join.return_value.filter.return_value.filter.return_value
        chain.all.return_value = rows

    def test_scope_with_only_the_primary_module_is_never_phantom(self):
        Svc, svc = self._make_svc()
        self._wire(svc, [])
        result = Svc._phantom_paired_scope_ids(svc.session, {1}, 10, {})
        assert result == set()

    def test_scope_whose_only_other_module_is_phantom_is_excluded(self):
        Svc, svc = self._make_svc()
        self._wire(svc, [(1, 20, "2026-01-01", "2026-01-01")])
        result = Svc._phantom_paired_scope_ids(svc.session, {1}, 10, {})
        assert result == {1}

    def test_scope_with_one_live_other_module_is_not_excluded(self):
        """Only void when *every* other module is phantom."""
        Svc, svc = self._make_svc()
        self._wire(
            svc,
            [
                (1, 20, "2026-01-01", "2026-01-01"),
                (1, 30, "2020-01-01", None),
            ],
        )
        result = Svc._phantom_paired_scope_ids(svc.session, {1}, 10, {})
        assert result == set()

    def test_phantom_other_module_with_fallback_is_not_excluded(self):
        """A phantom other module isn't a dead end when
        *ghost_fallback_map* names a fallback for it (Andrés's review
        on PR #396) — empty only when no release could be resolved at
        all, so this fires whenever a release is known, explicit or not.
        """
        Svc, svc = self._make_svc()
        self._wire(svc, [(1, 20, "2026-01-01", "2026-01-01")])
        result = Svc._phantom_paired_scope_ids(svc.session, {1}, 10, {20: 777})
        assert result == set()


class TestGhostFallbackMap:
    """Direct coverage of the #182 inversion and its per-release cache."""

    def _make_svc(self):
        Svc, _ = _load_module()
        return Svc(MagicMock())

    def test_inverts_a_fallback_covering_several_ghosts(self):
        """A fallback stands in for more than one ghost — every ghost
        VID must map back to it (COREP_LE-3.1.0 covers both of its
        pre-1.0.0-restatement ghost siblings, for instance).
        """
        svc = self._make_svc()
        mq = sys.modules["dpmcore.dpm_xl.model_queries"]
        mq.ModuleVersionQuery.ghost_fallbacks = MagicMock(
            return_value={777: [111, 999]}
        )
        assert svc._ghost_fallback_map(release_id=5) == {111: 777, 999: 777}

    def test_memoises_per_release_id(self):
        """A second call for the same release must not re-query —
        ``build_scope_result_from_db`` and ``_phantom_paired_scope_ids``
        both call this once per operation, release-wide.
        """
        svc = self._make_svc()
        mq = sys.modules["dpmcore.dpm_xl.model_queries"]
        mq.ModuleVersionQuery.ghost_fallbacks = MagicMock(
            return_value={777: [999]}
        )
        first = svc._ghost_fallback_map(release_id=5)
        again = svc._ghost_fallback_map(release_id=5)
        assert again == first == {999: 777}
        mq.ModuleVersionQuery.ghost_fallbacks.assert_called_once_with(
            svc.session, 5
        )

    def test_different_releases_are_not_conflated(self):
        svc = self._make_svc()
        mq = sys.modules["dpmcore.dpm_xl.model_queries"]
        mq.ModuleVersionQuery.ghost_fallbacks = MagicMock(
            side_effect=[{777: [999]}, {888: [222]}]
        )
        at_five = svc._ghost_fallback_map(release_id=5)
        at_six = svc._ghost_fallback_map(release_id=6)
        assert at_five == {999: 777}
        assert at_six == {222: 888}
        assert mq.ModuleVersionQuery.ghost_fallbacks.call_count == 2


class TestSubstituteGhostCompositions:
    """Direct coverage of the ``module_vid`` substitution
    ``build_scope_result_from_db`` applies to a rescued ghost-paired
    scope (Andrés's review on PR #396).
    """

    def test_noop_when_no_composition_is_a_ghost(self):
        Svc, _ = _load_module()
        scope = _op_scope(1, [10, 20])
        out = Svc._substitute_ghost_compositions(scope, {999: 777})
        assert out is scope

    def test_substitutes_only_the_ghost_composition(self):
        """A scope composed with both the primary module and a ghost
        gets only the ghost's ``module_vid`` rewritten — the other
        composition, and the scope's own id, are left alone.
        """
        Svc, _ = _load_module()
        scope = _op_scope(1, [10, 999])
        out = Svc._substitute_ghost_compositions(scope, {999: 777})
        assert out is not scope
        assert out.operation_scope_id == 1
        vids = [c.module_vid for c in out.operation_scope_compositions]
        assert vids == [10, 777]

    def test_multiple_ghost_compositions_all_substituted(self):
        Svc, _ = _load_module()
        scope = _op_scope(1, [999, 111])
        out = Svc._substitute_ghost_compositions(scope, {999: 777, 111: 777})
        vids = [c.module_vid for c in out.operation_scope_compositions]
        assert vids == [777, 777]


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
