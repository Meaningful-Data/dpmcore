"""A ``time_shift`` over a table of the reporting module (#325).

The shifted operand needs another instance of the home module itself, so
the operation is not intra-instance: the shifted instance has to be
declared in ``cross_instance_dependencies`` under the home module's own
URI, carrying the shift's reference period. Before #325 the operation was
declared intra with no dependency at all, and the computed reference
period — correct internally — was only ever read off a *dependency*
module's tables, so it never reached the output.

Imports the service normally (as ``test_prefer_intra`` does) instead of
the legacy ORM-stubbing shim used elsewhere in the suite.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dpmcore.services import scope_calculator as sc_mod
from dpmcore.services.scope_calculator import (
    ScopeCalculatorService,
    ScopeResult,
)

pytestmark = pytest.mark.unit

HOME = 10
EXTERNAL = 20


def _scope(module_vids):
    """A scope whose compositions cover *module_vids*."""
    return SimpleNamespace(
        operation_scope_compositions=[
            SimpleNamespace(module_vid=v) for v in module_vids
        ]
    )


def _mv(module_vid, version_number="3.1.0"):
    return SimpleNamespace(
        module_vid=module_vid,
        version_number=version_number,
        from_reference_date=date(2022, 12, 31),
        to_reference_date=date(2025, 3, 30),
    )


@pytest.fixture
def svc(monkeypatch):
    """Service whose home module (10) owns C_48.02 and an external (20) T_20."""
    monkeypatch.setattr(
        sc_mod,
        "resolve_release_id",
        lambda session, release_id=None, release_code=None: release_id,
    )
    service = ScopeCalculatorService(MagicMock())
    service._get_module_uri = lambda module_vid, mv=None: f"uri/{module_vid}"
    tables = {
        HOME: {"C_48.02": {"variables": {"v1": "m"}, "open_keys": {}}},
        EXTERNAL: {"T_20": {"variables": {"v2": "m"}, "open_keys": {}}},
    }
    service._get_module_tables = lambda module_vid, release_id=None: tables[
        module_vid
    ]
    query = service.session.query.return_value
    # ``_build_home_instance_deps`` resolves the home module version;
    # ``detect_cross_module_dependencies`` resolves the dependency ones.
    query.filter.return_value.first.return_value = _mv(HOME)
    query.filter.return_value.all.return_value = [_mv(EXTERNAL, "1.0.0")]
    return service


class TestHomeShiftIsCrossInstance:
    """The reported case: a single-module scope with a shifted home table."""

    def test_shifted_home_table_is_not_intra(self, svc):
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(scopes=[_scope([HOME])]),
            primary_module_vid=HOME,
            operation_code="EGDQ_0896",
            time_shifts={"C_48.02": ["T-1Q"]},
        )
        assert info["intra_instance_validations"] == []

    def test_shifted_home_instance_is_declared(self, svc):
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(scopes=[_scope([HOME])]),
            primary_module_vid=HOME,
            operation_code="EGDQ_0896",
            time_shifts={"C_48.02": ["T-1Q"]},
        )
        assert info["cross_instance_dependencies"] == [
            {
                "modules": [
                    {
                        "URI": "uri/10",
                        "ref_period": "T-1Q",
                        "module_version": "3.1.0",
                    }
                ],
                "affected_operations": ["EGDQ_0896"],
                "from_reference_date": "2022-12-31",
                "to_reference_date": "2025-03-30",
            }
        ]

    def test_home_module_is_not_a_dependency_module(self, svc):
        """Its tables and variables are declared at the script's top level."""
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(scopes=[_scope([HOME])]),
            primary_module_vid=HOME,
            operation_code="EGDQ_0896",
            time_shifts={"C_48.02": ["T-1Q"]},
        )
        assert info["dependency_modules"] == {}

    def test_unshifted_operation_stays_intra(self, svc):
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(scopes=[_scope([HOME])]),
            primary_module_vid=HOME,
            operation_code="EGDQ_0896",
        )
        assert info["intra_instance_validations"] == ["EGDQ_0896"]
        assert info["cross_instance_dependencies"] == []

    def test_ref_period_t_is_not_a_shift(self, svc):
        """``T`` is the default reference period, not a shifted instance."""
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(scopes=[_scope([HOME])]),
            primary_module_vid=HOME,
            operation_code="EGDQ_0896",
            time_shifts={"C_48.02": ["T"]},
        )
        assert info["intra_instance_validations"] == ["EGDQ_0896"]
        assert info["cross_instance_dependencies"] == []

    def test_shift_on_a_table_the_home_does_not_own_is_ignored(self, svc):
        """An external module's shift belongs to that module's entry."""
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(scopes=[_scope([HOME])]),
            primary_module_vid=HOME,
            operation_code="EGDQ_0896",
            time_shifts={"T_20": ["T-1Q"]},
        )
        assert info["intra_instance_validations"] == ["EGDQ_0896"]
        assert info["cross_instance_dependencies"] == []

    def test_caller_supplied_home_tables_are_used(self, svc):
        """The pre-computed set spares the per-table lookup (script path)."""
        svc._get_module_tables = MagicMock(
            side_effect=AssertionError("should not be queried")
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(scopes=[_scope([HOME])]),
            primary_module_vid=HOME,
            operation_code="EGDQ_0896",
            time_shifts={"C_48.02": ["T-1Q"]},
            home_module_tables={"C_48.02"},
        )
        assert (
            info["cross_instance_dependencies"][0]["modules"][0]["ref_period"]
            == "T-1Q"
        )

    def test_two_distinct_home_shifts_are_both_declared(self, svc):
        """One entry per distinct period — the schema has no per-table one."""
        svc._get_module_tables = lambda module_vid, release_id=None: {
            "C_48.02": {"variables": {"v1": "m"}, "open_keys": {}},
            "C_47.00": {"variables": {"v2": "m"}, "open_keys": {}},
        }
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(scopes=[_scope([HOME])]),
            primary_module_vid=HOME,
            operation_code="OP_BOTH",
            time_shifts={"C_48.02": ["T-1Q"], "C_47.00": ["T-4Q"]},
        )
        periods = [
            m["ref_period"]
            for dep in info["cross_instance_dependencies"]
            for m in dep["modules"]
        ]
        assert periods == ["T-1Q", "T-4Q"]

    def test_module_version_omitted_when_the_row_has_none(self, svc):
        """A version-less module version declares only URI and period."""
        svc.session.query.return_value.filter.return_value.first.return_value = _mv(  # noqa: E501
            HOME, version_number=None
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(scopes=[_scope([HOME])]),
            primary_module_vid=HOME,
            operation_code="EGDQ_0896",
            time_shifts={"C_48.02": ["T-1Q"]},
        )
        assert info["cross_instance_dependencies"][0]["modules"] == [
            {"URI": "uri/10", "ref_period": "T-1Q"}
        ]

    def test_unresolvable_uri_keeps_the_intra_classification(self, svc):
        """Better a wrong-but-present classification than no entry at all."""
        svc._get_module_uri = lambda module_vid, mv=None: None
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(scopes=[_scope([HOME])]),
            primary_module_vid=HOME,
            operation_code="EGDQ_0896",
            time_shifts={"C_48.02": ["T-1Q"]},
        )
        assert info["intra_instance_validations"] == ["EGDQ_0896"]
        assert info["cross_instance_dependencies"] == []

    def test_scope_error_declares_nothing(self, svc):
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(has_error=True, error_message="boom"),
            primary_module_vid=HOME,
            operation_code="EGDQ_0896",
            time_shifts={"C_48.02": ["T-1Q"]},
        )
        assert info["intra_instance_validations"] == []
        assert info["cross_instance_dependencies"] == []

    def test_module_hosting_no_referenced_table_declares_nothing(self, svc):
        """No scope of its own: neither intra owner nor shifted reporter."""
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(scopes=[_scope([EXTERNAL])]),
            primary_module_vid=HOME,
            operation_code="EGDQ_0896",
            time_shifts={"C_48.02": ["T-1Q"]},
        )
        assert info["intra_instance_validations"] == []
        assert info["cross_instance_dependencies"] == []


class TestHomeShiftAlongsideExternalDependency:
    """A genuinely cross-module operation that also shifts a home table."""

    def test_external_and_home_instances_are_both_declared(self, svc):
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(
                scopes=[_scope([HOME, EXTERNAL])],
                is_cross_module=True,
            ),
            primary_module_vid=HOME,
            operation_code="X_BOTH",
            time_shifts={"C_48.02": ["T-1Q"]},
        )
        assert info["intra_instance_validations"] == []
        declared = [
            (m["URI"], m["ref_period"])
            for dep in info["cross_instance_dependencies"]
            for m in dep["modules"]
        ]
        # The external entry keeps its position: callers reading the
        # first entry see the same module they saw before #325.
        assert declared == [("uri/20", "T"), ("uri/10", "T-1Q")]
        assert set(info["dependency_modules"]) == {"uri/20"}

    def test_external_dependency_alone_is_unchanged(self, svc):
        info = svc.detect_cross_module_dependencies(
            scope_result=ScopeResult(
                scopes=[_scope([HOME, EXTERNAL])],
                is_cross_module=True,
            ),
            primary_module_vid=HOME,
            operation_code="X_CROSS",
        )
        declared = [
            (m["URI"], m["ref_period"])
            for dep in info["cross_instance_dependencies"]
            for m in dep["modules"]
        ]
        assert declared == [("uri/20", "T")]


class TestHomeModuleResolutionIsMemoised:
    """The home module is resolved once, not once per operation.

    ``detect_cross_module_dependencies`` runs per operation with a fixed
    ``primary_module_vid``, so the row fetch and URI resolution behind
    the shifted home instance repeated for every shifting operation in
    a script.
    """

    def test_repeated_operations_resolve_the_home_module_once(self, svc):
        resolver = MagicMock(
            side_effect=lambda module_vid, mv=None: f"uri/{module_vid}"
        )
        svc._get_module_uri = resolver
        declared = []
        for code in ("OP_1", "OP_2", "OP_3"):
            info = svc.detect_cross_module_dependencies(
                scope_result=ScopeResult(scopes=[_scope([HOME])]),
                primary_module_vid=HOME,
                operation_code=code,
                time_shifts={"C_48.02": "T-1Q"},
            )
            declared.append(info["cross_instance_dependencies"])
        assert resolver.call_count == 1
        # Memoising must not change what is declared: same entry every
        # time, only the operation it affects differs.
        assert [d[0]["modules"] for d in declared] == [
            [
                {
                    "URI": "uri/10",
                    "ref_period": "T-1Q",
                    "module_version": "3.1.0",
                }
            ]
        ] * 3
        assert [d[0]["affected_operations"] for d in declared] == [
            ["OP_1"],
            ["OP_2"],
            ["OP_3"],
        ]

    def test_a_different_home_module_is_resolved_on_its_own(self, svc):
        resolver = MagicMock(
            side_effect=lambda module_vid, mv=None: f"uri/{module_vid}"
        )
        svc._get_module_uri = resolver
        for vid, table in ((HOME, "C_48.02"), (EXTERNAL, "T_20")):
            info = svc.detect_cross_module_dependencies(
                scope_result=ScopeResult(scopes=[_scope([vid])]),
                primary_module_vid=vid,
                operation_code="OP",
                time_shifts={table: "T-1Q"},
            )
            assert (
                info["cross_instance_dependencies"][0]["modules"][0]["URI"]
                == f"uri/{vid}"
            )
        assert resolver.call_count == 2
