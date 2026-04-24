"""Tests for HierarchyService.get_all_frameworks.

Ported from the py_dpm ``HierarchicalQuery.get_all_frameworks`` suite.

The py_dpm method returned a deep tree of
``framework → module_versions → table_versions`` with custom field
renames; the new ``HierarchyService.get_all_frameworks`` simply returns
the Framework rows via ``to_dict``. The ported tests therefore target
the shallower surface that exists today.
"""

from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import Table, TableVersion
from dpmcore.services.hierarchy import HierarchyService


def test_get_all_frameworks_returns_framework_rows(memory_session):
    """Framework rows round-trip through Framework.to_dict."""
    session = memory_session

    session.add(
        Framework(
            framework_id=1,
            code="FW1",
            name="Framework 1",
            description="Desc FW1",
        )
    )
    session.add(Module(module_id=1, framework_id=1))
    session.add(
        ModuleVersion(
            module_vid=10,
            module_id=1,
            code="MV1",
            name="Module Ver 1",
            start_release_id=1,
            end_release_id=None,
            version_number="1.0",
        )
    )
    session.add(Table(table_id=100, is_abstract=False))
    session.add(
        TableVersion(
            table_vid=1000,
            table_id=100,
            code="TV1",
            name="Table Ver 1",
            start_release_id=1,
            end_release_id=None,
        )
    )
    session.add(
        ModuleVersionComposition(module_vid=10, table_vid=1000, table_id=100)
    )
    session.commit()

    service = HierarchyService(session)
    result = service.get_all_frameworks()

    assert len(result) == 1
    fw = result[0]
    assert fw["code"] == "FW1"
    assert fw["name"] == "Framework 1"
    assert fw["description"] == "Desc FW1"


def test_get_all_frameworks_empty_db_returns_empty_list(memory_session):
    service = HierarchyService(memory_session)
    assert service.get_all_frameworks() == []
