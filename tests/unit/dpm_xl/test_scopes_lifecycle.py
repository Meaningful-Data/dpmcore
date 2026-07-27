"""Tests for lifecycle-aware scope supplement (Fix 1).

Verifies that when table codes undergo lifecycle transitions,
non-transitioning table codes are supplemented into both the
starting and ending module groups.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _patch_orm(monkeypatch):
    """Prevent ORM import chain on Python 3.10."""
    # Must mock sub-packages as proper MagicMocks with
    # attribute access chaining.
    pkg = MagicMock()
    dpm_xl = MagicMock()
    pkg.dpm_xl = dpm_xl
    # Provide real token values so DataFrame lookups work
    tokens_stub = MagicMock()
    tokens_stub.VARIABLE_VID = "variable_vid"
    tokens_stub.WARNING_SEVERITY = "warning"
    tokens_stub.VALID_SEVERITIES = {
        "error",
        "warning",
        "info",
    }

    # calculate_operation_scope now filters precondition_items down to
    # filing indicators up front via ModuleVersionQuery. These lifecycle
    # tests intend every precondition to be a filing indicator, so mock the
    # classifier as an identity filter (returns the codes it is given).
    model_queries_stub = MagicMock()
    model_queries_stub.ModuleVersionQuery.get_filing_indicator_codes.side_effect = (
        lambda session, codes: set(codes)
    )

    stubs = {
        "dpmcore": pkg,
        "dpmcore.connection": MagicMock(),
        "dpmcore.orm": MagicMock(),
        "dpmcore.orm.infrastructure": MagicMock(),
        "dpmcore.orm.packaging": MagicMock(),
        "dpmcore.orm.operations": MagicMock(),
        "dpmcore.orm.rendering": MagicMock(),
        "dpmcore.orm.variables": MagicMock(),
        "dpmcore.errors": MagicMock(),
        "dpmcore.dpm_xl": dpm_xl,
        "dpmcore.dpm_xl.model_queries": model_queries_stub,
        "dpmcore.dpm_xl.utils": MagicMock(),
        "dpmcore.dpm_xl.utils.tokens": tokens_stub,
    }
    for mod_name, stub in stubs.items():
        monkeypatch.setitem(sys.modules, mod_name, stub)


def _make_module_df(rows):
    """Build DataFrame matching ModuleVersionQuery output."""
    return pd.DataFrame(
        rows,
        columns=[
            "ModuleVID",
            "variable_vid",
            "TableCode",
            "ModuleCode",
            "VersionNumber",
            "StartReleaseID",
            "EndReleaseID",
            "FromReferenceDate",
            "ToReferenceDate",
        ],
    )


def _make_combined_df(rows):
    """Build a DataFrame mirroring the concat of table-code and
    precondition queries.

    Table rows carry their code in ``TableCode`` (``Code`` is NaN);
    precondition rows carry it in ``Code`` (``TableCode`` is NaN) — the
    exact shape ``extract_module_info`` produces when both table codes
    and precondition items are present.
    """
    return pd.DataFrame(
        rows,
        columns=[
            "ModuleVID",
            "variable_vid",
            "TableCode",
            "Code",
            "ModuleCode",
            "VersionNumber",
            "StartReleaseID",
            "EndReleaseID",
            "FromReferenceDate",
            "ToReferenceDate",
        ],
    )


def _get_svc_class():
    """Import OperationScopeService avoiding ORM chain."""
    mod_name = "dpmcore.dpm_xl.utils.scopes_calculator"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    spec = importlib.util.spec_from_file_location(
        mod_name,
        _REPO_ROOT / "src/dpmcore/dpm_xl/utils/scopes_calculator.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod.OperationScopeService


class TestLifecycleSupplement:
    """Supplement ensures both lifecycle groups complete."""

    def test_non_transitioning_codes_supplement(self):
        """Table codes without transitions added to both.

        Scenario: 3 table codes (A, B, C).
        - Table A: lifecycle transition (mod 10 ending,
          mod 20 starting).
        - Tables B and C: only mod 30 (no transition).
        """
        rows = [
            (10, 100, "A", "MOD_OLD", "1.0", 1, 5, "2020-01-01", "2024-12-31"),
            (20, 100, "A", "MOD_NEW", "2.0", 5, None, "2025-01-01", None),
            (30, 200, "B", "MOD_X", "1.0", 1, None, "2020-01-01", None),
            (30, 300, "C", "MOD_X", "1.0", 1, None, "2020-01-01", None),
        ]
        df = _make_module_df(rows)

        SvcClass = _get_svc_class()
        svc = SvcClass(session=MagicMock())

        captured_calls = []

        def capture_cross_module(**kwargs):
            captured_calls.append(kwargs["cross_modules"])

        svc.process_cross_module = capture_cross_module
        svc.get_scopes_with_status = MagicMock(return_value=([], []))
        svc.extract_module_info = MagicMock(return_value=df)

        svc.calculate_operation_scope(
            tables_vids=[],
            precondition_items=[],
            release_id=5,
            table_codes=["A", "B", "C"],
        )

        assert len(captured_calls) == 2

        starting_modules = captured_calls[0]
        ending_modules = captured_calls[1]

        # Starting: A (mod 20) + supplemented B,C (mod 30)
        assert "A" in starting_modules
        assert "B" in starting_modules
        assert "C" in starting_modules

        # Ending: A (mod 10) + supplemented B,C (mod 30)
        assert "A" in ending_modules
        assert "B" in ending_modules
        assert "C" in ending_modules

    def test_no_supplement_when_no_lifecycle_separation(
        self,
    ):
        """When no transition, modules are combined."""
        rows = [
            (10, 100, "A", "MOD_X", "1.0", 1, None, "2020-01-01", None),
            (10, 200, "B", "MOD_X", "1.0", 1, None, "2020-01-01", None),
        ]
        df = _make_module_df(rows)

        SvcClass = _get_svc_class()
        svc = SvcClass(session=MagicMock())

        captured_repeated = []
        svc.process_repeated = lambda mvids, minfo: captured_repeated.append(
            mvids
        )
        svc.get_scopes_with_status = MagicMock(return_value=([], []))
        svc.extract_module_info = MagicMock(return_value=df)

        svc.calculate_operation_scope(
            tables_vids=[],
            precondition_items=[],
            release_id=1,
            table_codes=["A", "B"],
        )

        assert len(captured_repeated) == 1
        assert 10 in captured_repeated[0]


class TestPreconditionCoverage:
    """Precondition codes count toward intra coverage (not the NaN
    bucket of the TableCode column).
    """

    def test_full_module_with_two_preconditions_is_intra(self):
        """A module covering every table code AND every precondition
        code is intra, even with two preconditions.

        Regression: previously ``unique_operands_number`` summed tables
        and preconditions while the membership test counted
        ``TableCode.unique()``, where all precondition rows collapse to
        a single NaN. With two preconditions the full module failed the
        test and was wrongly pushed into the cross-module pool.
        """
        rows = [
            # Full module: tables A, B + preconditions pA, pB.
            (
                10,
                100,
                "A",
                None,
                "MOD_FULL",
                "1.0",
                1,
                None,
                "2020-01-01",
                None,
            ),
            (
                10,
                200,
                "B",
                None,
                "MOD_FULL",
                "1.0",
                1,
                None,
                "2020-01-01",
                None,
            ),
            (
                10,
                0,
                None,
                "pA",
                "MOD_FULL",
                "1.0",
                1,
                None,
                "2020-01-01",
                None,
            ),
            (
                10,
                0,
                None,
                "pB",
                "MOD_FULL",
                "1.0",
                1,
                None,
                "2020-01-01",
                None,
            ),
            # Partial sibling: only table A + precondition pA.
            (
                20,
                100,
                "A",
                None,
                "MOD_PART",
                "1.0",
                1,
                None,
                "2020-01-01",
                None,
            ),
            (
                20,
                0,
                None,
                "pA",
                "MOD_PART",
                "1.0",
                1,
                None,
                "2020-01-01",
                None,
            ),
        ]
        df = _make_combined_df(rows)

        SvcClass = _get_svc_class()
        svc = SvcClass(session=MagicMock())

        captured_intra = []
        captured_cross = []
        svc.process_repeated = lambda mvids, minfo: captured_intra.extend(
            mvids
        )
        svc.process_cross_module = lambda **kwargs: captured_cross.append(
            kwargs
        )
        svc.get_scopes_with_status = MagicMock(return_value=([], []))
        svc.extract_module_info = MagicMock(return_value=df)

        svc.calculate_operation_scope(
            tables_vids=[],
            precondition_items=["pA", "pB"],
            release_id=1,
            table_codes=["A", "B"],
        )

        # Full module is intra; partial module is not.
        assert 10 in captured_intra
        assert 20 not in captured_intra
        # The partial module (20) contributes table code "A"; the missing
        # code "B" is supplemented from the full module (10) so the cross
        # pool covers the full operand set {A, B} and the product pairs
        # 20 with 10 into a complete cross-instance scope (Issue #119/#120).
        # No spurious NaN key leaks in from the precondition rows.
        assert captured_cross
        cross_modules = captured_cross[0]["cross_modules"]
        assert set(cross_modules) == {"A", "B"}
        assert cross_modules["A"] == [20]
        assert 10 in cross_modules["B"]


class TestCrossModuleCoverage:
    """process_cross_module only emits combinations that cover every
    required operand key.
    """

    @staticmethod
    def _modules_df():
        return pd.DataFrame(
            [
                (10, "MOD_A", "1.0", "2020-01-01", None),
                (20, "MOD_B", "1.0", "2020-01-01", None),
            ],
            columns=[
                "ModuleVID",
                "ModuleCode",
                "VersionNumber",
                "FromReferenceDate",
                "ToReferenceDate",
            ],
        )

    def test_incomplete_coverage_emits_no_scope(self):
        """A pool missing a required key produces no scope.

        ``{"A": [20]}`` cannot satisfy required keys ``{"A", "B"}`` — the
        partial module 20 would otherwise become a spurious single-module
        scope that cannot evaluate the operation.
        """
        SvcClass = _get_svc_class()
        svc = SvcClass(session=MagicMock())
        svc.process_cross_module(
            cross_modules={"A": [20]},
            modules_dataframe=self._modules_df(),
            required_keys={"A", "B"},
        )
        assert svc.operation_scopes == []

    def test_complete_coverage_emits_scope(self):
        """A pool spanning every required key produces a scope."""
        SvcClass = _get_svc_class()
        svc = SvcClass(session=MagicMock())
        svc.process_cross_module(
            cross_modules={"A": [10], "B": [20]},
            modules_dataframe=self._modules_df(),
            required_keys={"A", "B"},
        )
        assert len(svc.operation_scopes) == 1

    def test_none_required_keys_disables_guard(self):
        """``required_keys=None`` keeps the legacy unguarded behaviour."""
        SvcClass = _get_svc_class()
        svc = SvcClass(session=MagicMock())
        svc.process_cross_module(
            cross_modules={"A": [20]},
            modules_dataframe=self._modules_df(),
            required_keys=None,
        )
        assert len(svc.operation_scopes) == 1

    def test_empty_cross_modules_emits_no_scope(self):
        """An empty pool is a safe no-op rather than a hard crash.

        With no provider lists, ``product()`` would yield a single empty
        combination whose empty module set has no reference dates and
        would raise on ``from_dates.max()``. The method must instead
        return without emitting a scope.
        """
        SvcClass = _get_svc_class()
        svc = SvcClass(session=MagicMock())
        svc.process_cross_module(
            cross_modules={},
            modules_dataframe=self._modules_df(),
            required_keys=None,
        )
        assert svc.operation_scopes == []

    def test_non_overlapping_dates_emit_no_scope(self):
        """Modules whose reference-date windows do not overlap are never
        reported together (e.g. different lifecycle generations), so the
        combination is dropped rather than emitted (Issue #119/#120).
        """
        df = pd.DataFrame(
            [
                (10, "MOD_OLD", "1.0", "2020-01-01", "2024-12-31"),
                (30, "MOD_NEW", "2.0", "2025-01-01", None),
            ],
            columns=[
                "ModuleVID",
                "ModuleCode",
                "VersionNumber",
                "FromReferenceDate",
                "ToReferenceDate",
            ],
        )
        SvcClass = _get_svc_class()
        svc = SvcClass(session=MagicMock())
        svc.process_cross_module(
            cross_modules={"A": [10], "B": [30]},
            modules_dataframe=df,
            required_keys={"A", "B"},
        )
        assert svc.operation_scopes == []

    @staticmethod
    def _modules_df_with_preconditions():
        # Module 10 reports filing indicator "P1"; module 20 reports none.
        return pd.DataFrame(
            [
                (10, "MOD_A", "1.0", "2020-01-01", None, "P1"),
                (20, "MOD_B", "1.0", "2020-01-01", None, None),
            ],
            columns=[
                "ModuleVID",
                "ModuleCode",
                "VersionNumber",
                "FromReferenceDate",
                "ToReferenceDate",
                "Code",
            ],
        )

    def test_missing_precondition_emits_no_scope(self):
        """A combination that does not report a gating precondition cannot
        evaluate the operation, so it is dropped (Issue #120).
        """
        SvcClass = _get_svc_class()
        svc = SvcClass(session=MagicMock())
        svc.process_cross_module(
            cross_modules={"T": [20]},  # module 20 reports no precondition
            modules_dataframe=self._modules_df_with_preconditions(),
            required_keys={"T"},
            required_precondition_codes={"P1"},
        )
        assert svc.operation_scopes == []

    def test_precondition_covered_emits_scope(self):
        """A combination reporting every gating precondition is emitted."""
        SvcClass = _get_svc_class()
        svc = SvcClass(session=MagicMock())
        svc.process_cross_module(
            cross_modules={"T": [10]},  # module 10 reports P1
            modules_dataframe=self._modules_df_with_preconditions(),
            required_keys={"T"},
            required_precondition_codes={"P1"},
        )
        assert len(svc.operation_scopes) == 1

    @staticmethod
    def _two_provider_df():
        # Modules 100 and 200 both host every table; 300 hosts the last.
        # All three overlap in time (open-ended windows from the same date).
        return pd.DataFrame(
            [
                (100, "MOD_A", "1.0", "2026-03-31", None),
                (200, "MOD_B", "1.0", "2026-03-31", None),
                (300, "MOD_C", "1.0", "2026-03-31", None),
            ],
            columns=[
                "ModuleVID",
                "ModuleCode",
                "VersionNumber",
                "FromReferenceDate",
                "ToReferenceDate",
            ],
        )

    @staticmethod
    def _capture_scope_sets(svc):
        """Record each emitted scope's module set.

        The mocked ORM back-populates neither
        ``operation_scope_compositions`` nor distinct ``OperationScope``
        objects (the mocked class returns one shared instance), so both
        ``create_operation_scope`` and
        ``create_operation_scope_composition`` are stubbed: the former
        hands out a unique sentinel per scope, the latter records module
        VIDs grouped by that sentinel's identity.
        """
        members: dict[int, set] = {}

        def make_scope(submission_date):
            scope = object()
            svc.operation_scopes.append(scope)
            return scope

        def spy(operation_scope, module_vid, module_info=None):
            members.setdefault(id(operation_scope), set()).add(module_vid)

        svc.create_operation_scope = make_scope
        svc.create_operation_scope_composition = spy
        return members

    def test_shared_provider_lists_do_not_explode(self):
        """Many codes sharing one provider list must not multiply scopes.

        Regression: the Cartesian product picked a provider per code
        independently, so N codes each hosted by the same two modules
        emitted the identical module set 2**N times. Here ten codes share
        ``[100, 200]`` and one code is hosted by ``300`` — the engine must
        emit the two minimal covers (``{100, 300}`` / ``{200, 300}``), not
        2**10 duplicates nor the bloated ``{100, 200, 300}`` superset.
        """
        codes = [f"T{i}" for i in range(10)]
        cross_modules = {c: [100, 200] for c in codes}
        cross_modules["LAST"] = [300]
        required = set(codes) | {"LAST"}

        SvcClass = _get_svc_class()
        svc = SvcClass(session=MagicMock())
        members = self._capture_scope_sets(svc)
        svc.process_cross_module(
            cross_modules=cross_modules,
            modules_dataframe=self._two_provider_df(),
            required_keys=required,
        )

        assert len(svc.operation_scopes) == 2
        scope_sets = {frozenset(m) for m in members.values()}
        assert scope_sets == {frozenset({100, 300}), frozenset({200, 300})}

    def test_non_minimal_superset_is_dropped(self):
        """A combination strictly containing another is not emitted.

        ``A`` is hosted by both 10 and 20; ``B`` only by 20. The covers are
        ``{10, 20}`` and ``{20}`` — but ``{20}`` alone covers both keys, so
        the superset ``{10, 20}`` is redundant and dropped.
        """
        df = pd.DataFrame(
            [
                (10, "MOD_A", "1.0", "2026-03-31", None),
                (20, "MOD_B", "1.0", "2026-03-31", None),
            ],
            columns=[
                "ModuleVID",
                "ModuleCode",
                "VersionNumber",
                "FromReferenceDate",
                "ToReferenceDate",
            ],
        )
        SvcClass = _get_svc_class()
        svc = SvcClass(session=MagicMock())
        members = self._capture_scope_sets(svc)
        svc.process_cross_module(
            cross_modules={"A": [10, 20], "B": [20]},
            modules_dataframe=df,
            required_keys={"A", "B"},
        )
        assert len(svc.operation_scopes) == 1
        assert [frozenset(m) for m in members.values()] == [frozenset({20})]
