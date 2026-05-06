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

    def test_active_only_fallback_when_no_filter(self, memory_session):
        """No filter → only the currently-active ModuleVersion is returned.

        Pre-fix, this returned an arbitrary row when several
        ModuleVersions shared the same ``code``; the active-only
        fallback makes the no-filter case deterministic.
        """
        session = memory_session
        session.add_all(
            [
                Release(release_id=1, code="1.0", date=date(2023, 1, 1)),
                Release(release_id=2, code="2.0", date=date(2024, 1, 1)),
                Framework(framework_id=1, code="FW"),
                Module(module_id=1, framework_id=1),
                # Old version: ended at release 2.
                ModuleVersion(
                    module_vid=10,
                    module_id=1,
                    code="MV1",
                    version_number="1.0",
                    start_release_id=1,
                    end_release_id=2,
                ),
                # Currently-active version.
                ModuleVersion(
                    module_vid=11,
                    module_id=1,
                    code="MV1",
                    version_number="2.0",
                    start_release_id=2,
                    end_release_id=None,
                ),
            ]
        )
        session.commit()

        svc = HierarchyService(session)
        result = svc.get_module_version("MV1")
        assert result is not None
        assert result["module_vid"] == 11
        assert result["version_number"] == "2.0"

    def test_resolves_by_release_code(self, populated_session):
        svc = HierarchyService(populated_session)
        result = svc.get_module_version("COREP_Con", release_code="3.4")
        assert result is not None
        assert result["code"] == "COREP_Con"

    def test_unknown_release_code_raises(self, populated_session):
        svc = HierarchyService(populated_session)
        with pytest.raises(ValueError, match="not found"):
            svc.get_module_version("COREP_Con", release_code="9.9")

    def test_release_id_and_release_code_are_mutually_exclusive(
        self, populated_session
    ):
        svc = HierarchyService(populated_session)
        with pytest.raises(ValueError, match="maximum of one"):
            svc.get_module_version(
                "COREP_Con", release_id=5, release_code="3.4"
            )


class TestGetTablesForModule:
    def test_returns_tables_in_module(self, populated_session):
        svc = HierarchyService(populated_session)
        result = svc.get_tables_for_module("COREP_Con")

        codes = sorted(r["code"] for r in result)
        assert codes == ["C_01.00", "C_02.00"]

    def test_unknown_module_returns_empty(self, populated_session):
        svc = HierarchyService(populated_session)
        assert svc.get_tables_for_module("DOES_NOT_EXIST") == []

    def test_resolves_by_release_code(self, populated_session):
        svc = HierarchyService(populated_session)
        result = svc.get_tables_for_module("COREP_Con", release_code="3.4")
        codes = sorted(r["code"] for r in result)
        assert codes == ["C_01.00", "C_02.00"]

    def test_release_id_and_release_code_are_mutually_exclusive(
        self, populated_session
    ):
        svc = HierarchyService(populated_session)
        with pytest.raises(ValueError, match="maximum of one"):
            svc.get_tables_for_module(
                "COREP_Con", release_id=5, release_code="3.4"
            )
