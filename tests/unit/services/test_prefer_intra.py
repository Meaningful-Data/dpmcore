"""Prefer-intra classification in detect_cross_module_dependencies.

Issue #120: when a validation yields both an intra-instance scope (the
primary module can evaluate it alone) and cross-instance scopes (a sibling
module needs the primary to complete coverage), the primary module's script
must treat it as intra-instance, while the sibling's script treats it as a
cross-instance dependency.

Since #304 the engine no longer emits a cross scope that strictly
contains an intra one, so the exact pairing these tests feed in is not
reachable from ``OperationScopeService`` any more. The override still
fires for a cross scope disjoint from the intra module, and these tests
now pin it as an invariant of ``detect_cross_module_dependencies``
rather than as an observed engine output.

Imports the service normally (works on Python 3.11+) to avoid the legacy
ORM-stubbing shim used elsewhere in the suite.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dpmcore.services import scope_calculator as sc_mod
from dpmcore.services.scope_calculator import (
    ScopeCalculatorService,
    ScopeResult,
)

pytestmark = pytest.mark.unit


def _scope(module_vids):
    """A scope whose compositions cover *module_vids*."""
    return SimpleNamespace(
        operation_scope_compositions=[
            SimpleNamespace(module_vid=v) for v in module_vids
        ]
    )


@pytest.fixture
def svc(monkeypatch):
    monkeypatch.setattr(
        sc_mod,
        "resolve_release_id",
        lambda session, release_id=None, release_code=None: release_id,
    )
    service = ScopeCalculatorService(MagicMock())
    service._get_module_uri = lambda module_vid, mv=None: f"uri/{module_vid}"
    service._get_module_tables = lambda module_vid, release_id=None: {
        "T_01": {"variables": {"v1": "x"}, "open_keys": {}},
    }
    return service


class TestPreferIntra:
    """A validation with both intra and cross scopes for the same module."""

    def test_primary_with_intra_scope_is_intra_despite_cross(self, svc):
        # COREP(10) has an intra scope AND a cross scope [10, 20].
        sr = ScopeResult(
            scopes=[_scope([10]), _scope([10, 20])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1",
        )
        assert info["intra_instance_validations"] == ["v1"]
        assert info["cross_instance_dependencies"] == []

    def test_primary_only_in_cross_is_a_dependency(self, svc):
        # IF(20) appears only in the cross scope [10, 20] -> depends on 10.
        mv = MagicMock()
        mv.module_vid = 10
        mv.code = "COREP_OF"
        mv.version_number = "4.1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None
        svc.session.query.return_value.filter.return_value.all.return_value = [
            mv
        ]
        sr = ScopeResult(
            scopes=[_scope([10]), _scope([10, 20])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=20,
            operation_code="v1",
        )
        assert info["intra_instance_validations"] == []
        uris = [
            m["URI"]
            for c in info["cross_instance_dependencies"]
            for m in c["modules"]
        ]
        assert "uri/10" in uris

    def test_missing_single_module_scope_still_intra_via_table_ownership(
        self, svc
    ):
        """Regression for dpmcore#364 (IF_CLASS2-1.4.0/v09808_m): a
        DB-native ``scope_result`` built from persisted ``OperationScope``
        rows can omit a genuine single-module combination the live engine
        would have found — only the cross scope [10, 20] was ever
        persisted, even though 10 hosts every table the operation
        references and can evaluate it alone. Table ownership overrides
        the missing scope row, mirroring mdpm's ``is_intra_operation``.
        """
        sr = ScopeResult(
            scopes=[_scope([10, 20])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1",
            referenced_tables={"T_01"},
            home_module_tables={"T_01"},
        )
        assert info["intra_instance_validations"] == ["v1"]
        assert info["cross_instance_dependencies"] == []

    def test_partial_table_ownership_stays_cross(self, svc):
        """The primary must host *every* referenced table, not just
        some — a partial overlap is still a genuine dependency.
        """
        mv = MagicMock()
        mv.module_vid = 20
        mv.code = "IF"
        mv.version_number = "1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None
        svc.session.query.return_value.filter.return_value.all.return_value = [
            mv
        ]
        sr = ScopeResult(
            scopes=[_scope([10, 20])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1",
            referenced_tables={"T_01", "T_02"},
            home_module_tables={"T_01"},
        )
        assert info["intra_instance_validations"] == []

    def test_no_referenced_tables_leaves_missing_scope_as_cross(self, svc):
        """Without ``referenced_tables``/``home_module_tables`` (the
        common case for every caller that predates dpmcore#364's
        DB-native scope), a missing single-module scope row stays a
        genuine cross-instance dependency — the ownership check never
        fires on ``None``/empty inputs.
        """
        mv = MagicMock()
        mv.module_vid = 20
        mv.code = "IF"
        mv.version_number = "1.0"
        mv.from_reference_date = None
        mv.to_reference_date = None
        svc.session.query.return_value.filter.return_value.all.return_value = [
            mv
        ]
        sr = ScopeResult(
            scopes=[_scope([10, 20])],
            is_cross_module=True,
        )
        info = svc.detect_cross_module_dependencies(
            scope_result=sr,
            primary_module_vid=10,
            operation_code="v1",
        )
        assert info["intra_instance_validations"] == []
