"""One dependency module needed at more than one instance (#326).

The reference period is a property of a declared *module*, and only one
was kept per module: the last shifted table of the dependency won, so an
operation reading two tables of the same module at different instances —
or one table both plain and shifted — was declared against a single
instance and evaluated against the wrong one. Nothing downstream could
detect the loss, because the script stayed structurally valid.

Every distinct period is now declared as its own
``cross_instance_dependencies`` entry, which is the shape the schema
allows: it carries a period per declared module, not per table.

Follows ``test_home_instance_shift`` in importing the service normally
rather than through the legacy ORM-stubbing shim.
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
    """Home (10) owns C_47.00; the external module (20) owns two tables."""
    monkeypatch.setattr(
        sc_mod,
        "resolve_release_id",
        lambda session, release_id=None, release_code=None: release_id,
    )
    service = ScopeCalculatorService(MagicMock())
    service._get_module_uri = lambda module_vid, mv=None: f"uri/{module_vid}"
    tables = {
        HOME: {"C_47.00": {"variables": {"v1": "m"}, "open_keys": {}}},
        EXTERNAL: {
            "C_01.00": {"variables": {"v2": "m"}, "open_keys": {}},
            "C_05.01": {"variables": {"v3": "m"}, "open_keys": {}},
        },
    }
    service._get_module_tables = lambda module_vid, release_id=None: tables[
        module_vid
    ]
    query = service.session.query.return_value
    query.filter.return_value.first.return_value = _mv(HOME)
    query.filter.return_value.all.return_value = [_mv(EXTERNAL, "1.0.0")]
    return service


def _periods(info):
    """The (URI, ref_period) pairs declared, in declared order."""
    return [
        (m["URI"], m["ref_period"])
        for dep in info["cross_instance_dependencies"]
        for m in dep["modules"]
    ]


def _cross(svc, time_shifts, operation_code="OP"):
    return svc.detect_cross_module_dependencies(
        scope_result=ScopeResult(
            scopes=[_scope([HOME, EXTERNAL])], is_cross_module=True
        ),
        primary_module_vid=HOME,
        operation_code=operation_code,
        time_shifts=time_shifts,
    )


class TestOneModuleAtSeveralPeriods:
    def test_two_tables_shifted_differently_declare_both(self, svc):
        """The issue's single-expression case: no merging is involved."""
        info = _cross(svc, {"C_01.00": ["T-1Q"], "C_05.01": ["T-4Q"]})
        assert _periods(info) == [
            (f"uri/{EXTERNAL}", "T-1Q"),
            (f"uri/{EXTERNAL}", "T-4Q"),
        ]

    def test_a_table_read_plain_and_shifted_declares_both(self, svc):
        info = _cross(svc, {"C_01.00": ["T", "T-1Q"]})
        assert _periods(info) == [
            (f"uri/{EXTERNAL}", "T"),
            (f"uri/{EXTERNAL}", "T-1Q"),
        ]

    def test_a_table_shifted_twice_declares_both(self, svc):
        info = _cross(svc, {"C_01.00": ["T-1Q", "T-4Q"]})
        assert _periods(info) == [
            (f"uri/{EXTERNAL}", "T-1Q"),
            (f"uri/{EXTERNAL}", "T-4Q"),
        ]

    def test_a_shifted_and_a_plain_table_declare_both(self, svc):
        info = _cross(svc, {"C_01.00": ["T-1Q"], "C_05.01": ["T"]})
        assert _periods(info) == [
            (f"uri/{EXTERNAL}", "T"),
            (f"uri/{EXTERNAL}", "T-1Q"),
        ]

    def test_declaration_order_does_not_follow_visit_order(self, svc):
        """The same shifts in the opposite mapping order declare the same."""
        forward = _periods(
            _cross(svc, {"C_01.00": ["T-1Q"], "C_05.01": ["T-4Q"]})
        )
        reverse = _periods(
            _cross(svc, {"C_05.01": ["T-4Q"], "C_01.00": ["T-1Q"]})
        )
        assert forward == reverse

    def test_every_entry_lists_the_operation(self, svc):
        info = _cross(svc, {"C_01.00": ["T-1Q"], "C_05.01": ["T-4Q"]})
        assert [
            dep["affected_operations"]
            for dep in info["cross_instance_dependencies"]
        ] == [["OP"], ["OP"]]

    def test_the_module_is_declared_once_in_dependency_modules(self, svc):
        """Table and datapoint definitions do not vary by instance."""
        info = _cross(svc, {"C_01.00": ["T-1Q"], "C_05.01": ["T-4Q"]})
        assert list(info["dependency_modules"]) == [f"uri/{EXTERNAL}"]


class TestUnshiftedIsUnchanged:
    def test_no_shifts_declares_a_single_t_entry(self, svc):
        info = _cross(svc, {})
        assert _periods(info) == [(f"uri/{EXTERNAL}", "T")]

    def test_a_shift_on_an_unrelated_table_is_ignored(self, svc):
        """A table no declared module owns contributes no period."""
        info = _cross(svc, {"T_99": ["T-1Q"]})
        assert _periods(info) == [(f"uri/{EXTERNAL}", "T")]


class TestLegacyStringShape:
    """A bare string is one period, not a sequence of characters."""

    def test_string_value_is_read_as_a_single_period(self, svc):
        info = _cross(svc, {"C_01.00": "T-1Q"})
        assert _periods(info) == [(f"uri/{EXTERNAL}", "T-1Q")]

    def test_string_value_matches_the_list_form(self, svc):
        assert _periods(_cross(svc, {"C_01.00": "T-1Q"})) == _periods(
            _cross(svc, {"C_01.00": ["T-1Q"]})
        )
