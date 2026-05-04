"""Integration tests for HierarchyService.get_module_version + get_tables_for_module.

Pins the fix that ``module_code`` is matched against ``ModuleVersion.code``
(not the non-existent ``Module.code`` attribute).
"""

from __future__ import annotations

from datetime import date

import pytest

from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import TableVersion
from dpmcore.services.hierarchy import HierarchyService


@pytest.fixture
def populated_session(memory_session):
    """Build a minimal graph: 1 release, 1 framework, 1 module + version, 2 tables."""
    session = memory_session
    session.add_all(
        [
            Release(release_id=5, code="3.4", date=date(2024, 2, 6)),
            Framework(framework_id=1, code="COREP", name="Common Reporting"),
            Module(module_id=10, framework_id=1),
            ModuleVersion(
                module_vid=100,
                module_id=10,
                code="COREP_Con",
                version_number="2.0.1",
                start_release_id=5,
            ),
            TableVersion(
                table_vid=200,
                table_id=20,
                code="C_01.00",
                start_release_id=5,
            ),
            TableVersion(
                table_vid=201,
                table_id=21,
                code="C_02.00",
                start_release_id=5,
            ),
            ModuleVersionComposition(
                module_vid=100, table_vid=200, table_id=20
            ),
            ModuleVersionComposition(
                module_vid=100, table_vid=201, table_id=21
            ),
        ]
    )
    session.commit()
    return session


class TestGetModuleVersion:
    def test_resolves_by_module_version_code(self, populated_session):
        svc = HierarchyService(populated_session)
        result = svc.get_module_version("COREP_Con")

        assert result is not None
        assert result["code"] == "COREP_Con"
        assert result["version_number"] == "2.0.1"

    def test_unknown_code_returns_none(self, populated_session):
        svc = HierarchyService(populated_session)
        assert svc.get_module_version("DOES_NOT_EXIST") is None


class TestGetTablesForModule:
    def test_returns_tables_in_module(self, populated_session):
        svc = HierarchyService(populated_session)
        result = svc.get_tables_for_module("COREP_Con")

        codes = sorted(r["code"] for r in result)
        assert codes == ["C_01.00", "C_02.00"]

    def test_unknown_module_returns_empty(self, populated_session):
        svc = HierarchyService(populated_session)
        assert svc.get_tables_for_module("DOES_NOT_EXIST") == []
