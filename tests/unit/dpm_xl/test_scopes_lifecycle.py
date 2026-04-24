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
        "dpmcore.dpm_xl.model_queries": MagicMock(),
        "dpmcore.dpm_xl.utils": MagicMock(),
        "dpmcore.dpm_xl.utils.tokens": tokens_stub,
    }
    for mod_name, stub in stubs.items():
        if mod_name not in sys.modules:
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
        svc = SvcClass(operation_version_id=1, session=MagicMock())

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
        svc = SvcClass(operation_version_id=1, session=MagicMock())

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
