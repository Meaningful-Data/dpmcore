"""Tests for HierarchyService.get_all_frameworks.

Covers both the flat shape (default) and the ``deep=True`` tree shape
(framework → module_versions → table_versions) used by the renderer.
"""

from datetime import date

import pytest

from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import Table, TableVersion
from dpmcore.services.hierarchy import HierarchyService


def _seed_two_frameworks(session):
    """Two frameworks; FW1 has 1 module/table, FW2 has 1 module/table."""
    session.add_all(
        [
            Release(release_id=1, code="1.0", date=date(2024, 1, 1)),
            Release(release_id=2, code="2.0", date=date(2025, 1, 1)),
            Framework(
                framework_id=1,
                code="FW1",
                name="Framework 1",
                description="Desc FW1",
            ),
            Framework(
                framework_id=2,
                code="FW2",
                name="Framework 2",
                description="Desc FW2",
            ),
            Module(module_id=1, framework_id=1),
            Module(module_id=2, framework_id=2),
            ModuleVersion(
                module_vid=10,
                module_id=1,
                code="MV1",
                name="Module Ver 1",
                start_release_id=1,
                end_release_id=None,
                version_number="1.0",
                from_reference_date=date(2024, 1, 1),
                to_reference_date=date(2025, 12, 31),
            ),
            ModuleVersion(
                module_vid=20,
                module_id=2,
                code="MV2",
                name="Module Ver 2",
                start_release_id=1,
                end_release_id=None,
                version_number="1.0",
            ),
            Table(table_id=100, is_abstract=False, is_flat=True),
            Table(table_id=200),
            TableVersion(
                table_vid=1000,
                table_id=100,
                code="TV1",
                name="Table Ver 1",
                start_release_id=1,
            ),
            TableVersion(
                table_vid=2000,
                table_id=200,
                code="TV2",
                name="Table Ver 2",
                start_release_id=1,
            ),
            ModuleVersionComposition(
                module_vid=10, table_vid=1000, table_id=100
            ),
            ModuleVersionComposition(
                module_vid=20, table_vid=2000, table_id=200
            ),
        ]
    )
    session.commit()


def test_get_all_frameworks_returns_framework_rows(memory_session):
    """Default (flat) call: round-trip through Framework.to_dict."""
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
    # Flat mode does not nest module_versions
    assert "module_versions" not in fw


def test_get_all_frameworks_empty_db_returns_empty_list(memory_session):
    service = HierarchyService(memory_session)
    assert service.get_all_frameworks() == []
    assert service.get_all_frameworks(deep=True) == []


def test_get_all_frameworks_deep_returns_tree(memory_session):
    """deep=True returns framework -> module_versions -> table_versions."""
    session = memory_session
    _seed_two_frameworks(session)

    service = HierarchyService(session)
    result = service.get_all_frameworks(deep=True)

    by_code = {fw["code"]: fw for fw in result}
    assert set(by_code) == {"FW1", "FW2"}

    fw1 = by_code["FW1"]
    assert fw1["framework_id"] == 1
    assert fw1["name"] == "Framework 1"
    assert len(fw1["module_versions"]) == 1

    mv = fw1["module_versions"][0]
    assert mv["module_vid"] == 10
    assert mv["code"] == "MV1"
    assert mv["version_number"] == "1.0"
    assert mv["from_reference_date"] == date(2024, 1, 1)

    assert len(mv["table_versions"]) == 1
    tv = mv["table_versions"][0]
    assert tv["table_vid"] == 1000
    assert tv["code"] == "TV1"
    assert tv["is_flat"] is True


def test_get_all_frameworks_deep_filters_by_release(memory_session):
    """release_id restricts module_versions to the matching release."""
    session = memory_session
    _seed_two_frameworks(session)
    # A second module-version under FW1 that already ended at release 2.
    session.add(Module(module_id=3, framework_id=1))
    session.add(
        ModuleVersion(
            module_vid=99,
            module_id=3,
            code="MV1_OLD",
            start_release_id=1,
            end_release_id=2,
        )
    )
    session.add(
        ModuleVersionComposition(module_vid=99, table_vid=1000, table_id=100)
    )
    session.commit()

    service = HierarchyService(session)
    deep = service.get_all_frameworks(deep=True, release_id=2)

    fw1 = next(fw for fw in deep if fw["code"] == "FW1")
    mv_codes = {mv["code"] for mv in fw1["module_versions"]}
    # MV1 (active, no end) is kept; MV1_OLD (ends at 2 -> excluded by
    # filter_by_release because end > release_id is False).
    assert mv_codes == {"MV1"}


def test_get_all_frameworks_deep_filters_by_date(memory_session):
    """Date filter resolves via ModuleVersion's reference dates."""
    session = memory_session
    _seed_two_frameworks(session)

    service = HierarchyService(session)
    # FW1's MV is valid 2024-01-01 .. 2025-12-31; FW2's MV has no
    # to_reference_date so it is treated as still valid.
    result = service.get_all_frameworks(deep=True, date="2024-06-15")

    by_code = {fw["code"]: fw for fw in result}
    assert "FW1" in by_code
    assert len(by_code["FW1"]["module_versions"]) == 1


def test_get_all_frameworks_release_and_date_mutually_exclusive(
    memory_session,
):
    service = HierarchyService(memory_session)
    with pytest.raises(ValueError, match="maximum of one"):
        service.get_all_frameworks(release_id=1, date="2024-01-01")


def test_get_all_frameworks_deep_keeps_framework_with_no_matching_mv(
    memory_session,
):
    """Filter must not drop frameworks whose every MV is excluded.

    Regression for the bug where ``filter_by_release`` was applied as
    a WHERE predicate on the LEFT-OUTER-joined ``ModuleVersion``,
    silently turning the outer join into an inner filter and dropping
    frameworks with no matching module-version.
    """
    session = memory_session
    _seed_two_frameworks(session)
    # FW3 has one module-version that only exists at release 1 (ends
    # at 2). Querying release 2 should keep FW3 in the result with an
    # empty module_versions list, not drop it.
    session.add(
        Framework(
            framework_id=3, code="FW3", name="Framework 3", description="d"
        )
    )
    session.add(Module(module_id=33, framework_id=3))
    session.add(
        ModuleVersion(
            module_vid=330,
            module_id=33,
            code="MV3_OLD",
            start_release_id=1,
            end_release_id=2,
        )
    )
    session.commit()

    service = HierarchyService(session)
    deep = service.get_all_frameworks(deep=True, release_id=2)

    by_code = {fw["code"]: fw for fw in deep}
    assert "FW3" in by_code
    assert by_code["FW3"]["module_versions"] == []


def test_get_all_frameworks_deep_keeps_framework_with_no_matching_date(
    memory_session,
):
    """Same regression, but driven by the ``date`` filter."""
    session = memory_session
    _seed_two_frameworks(session)
    # FW3 has a module-version only valid in 2030; querying for
    # 2024-06-15 should still return FW3 with empty module_versions.
    session.add(
        Framework(
            framework_id=3, code="FW3", name="Framework 3", description="d"
        )
    )
    session.add(Module(module_id=33, framework_id=3))
    session.add(
        ModuleVersion(
            module_vid=330,
            module_id=33,
            code="MV3_FUTURE",
            start_release_id=1,
            from_reference_date=date(2030, 1, 1),
            to_reference_date=date(2030, 12, 31),
        )
    )
    session.commit()

    service = HierarchyService(session)
    deep = service.get_all_frameworks(deep=True, date="2024-06-15")

    by_code = {fw["code"]: fw for fw in deep}
    assert "FW3" in by_code
    assert by_code["FW3"]["module_versions"] == []
