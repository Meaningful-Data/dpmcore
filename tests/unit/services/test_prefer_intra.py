"""Prefer-intra classification in detect_cross_module_dependencies.

Issue #120: when a validation yields both an intra-instance scope (the
primary module can evaluate it alone) and cross-instance scopes (a sibling
module needs the primary to complete coverage), the primary module's script
must treat it as intra-instance, while the sibling's script treats it as a
cross-instance dependency.

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
    service._get_module_uri = lambda module_vid, release_id=None, mv=None: (
        f"uri/{module_vid}"
    )
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
