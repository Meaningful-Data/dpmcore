"""Tests for HierarchyService.get_table_modelling.

Mirrors the renderer-side fetch_table_modelling shape so the renderer
can drop its monkey-patched copy and call the service directly.
"""

from datetime import date

import pytest

from dpmcore.orm.glossary import (
    Context,
    ContextComposition,
    Item,
    ItemCategory,
    Property,
)
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import (
    Header,
    HeaderVersion,
    Table,
    TableVersion,
    TableVersionHeader,
)
from dpmcore.services.hierarchy import HierarchyService


def _seed_minimal_table(session):
    """Seed a release-1 module/table with a single header for modelling."""
    session.add(Release(release_id=1, code="1.0", date=date(2024, 1, 1)))
    session.add(Framework(framework_id=1, code="FW"))
    session.add(Module(module_id=1, framework_id=1))
    session.add(
        ModuleVersion(
            module_vid=10,
            module_id=1,
            code="MV1",
            start_release_id=1,
            end_release_id=None,
        )
    )
    session.add(Table(table_id=100))
    session.add(
        TableVersion(
            table_vid=1000,
            table_id=100,
            code="T1",
            name="Table 1",
            start_release_id=1,
            end_release_id=None,
        )
    )
    session.add(
        ModuleVersionComposition(module_vid=10, table_vid=1000, table_id=100)
    )
    session.add(Header(header_id=50, direction="X"))
    session.add(
        HeaderVersion(
            header_vid=500,
            header_id=50,
            code="H1",
            label="Header 1",
            property_id=200,
            context_id=300,
        )
    )
    session.add(
        TableVersionHeader(
            table_vid=1000,
            header_vid=500,
            header_id=50,
            order=1,
        )
    )


def test_unknown_table_raises(memory_session):
    service = HierarchyService(memory_session)
    with pytest.raises(ValueError, match="not found"):
        service.get_table_modelling("UNKNOWN")


def test_release_id_and_date_are_mutually_exclusive(memory_session):
    service = HierarchyService(memory_session)
    with pytest.raises(ValueError, match="maximum of one"):
        service.get_table_modelling("T1", release_id=1, date="2024-06-30")


def test_returns_main_property_entry(memory_session):
    """A header with a property yields a main_property entry."""
    session = memory_session
    _seed_minimal_table(session)

    # Property/Item rows must exist for the joins.
    session.add(Item(item_id=200, name="Main Prop"))
    session.add(Property(property_id=200))
    session.add(
        ItemCategory(
            item_id=200,
            start_release_id=1,
            end_release_id=None,
            signature="prop:main",
        )
    )
    session.commit()

    service = HierarchyService(session)
    result = service.get_table_modelling("T1")

    assert 50 in result
    entries = result[50]
    main_entries = [e for e in entries if "main_property_code" in e]
    assert main_entries == [
        {"main_property_code": "prop:main", "main_property_name": "Main Prop"}
    ]


def test_returns_context_entry(memory_session):
    """A header tied to a context composition yields a context entry."""
    session = memory_session
    _seed_minimal_table(session)

    session.add(Item(item_id=200))  # property item (no metadata)
    session.add(Property(property_id=200))
    session.add(Item(item_id=400, name="Ctx Prop"))
    session.add(Property(property_id=400))
    session.add(Item(item_id=401, name="Ctx Item"))
    session.add(Context(context_id=300, signature="ctx"))
    session.add(
        ContextComposition(context_id=300, property_id=400, item_id=401)
    )
    session.add(
        ItemCategory(
            item_id=400,
            start_release_id=1,
            end_release_id=None,
            signature="ctx:prop",
        )
    )
    session.add(
        ItemCategory(
            item_id=401,
            start_release_id=1,
            end_release_id=None,
            signature="ctx:item",
        )
    )
    session.commit()

    service = HierarchyService(session)
    result = service.get_table_modelling("T1")

    ctx_entries = [e for e in result[50] if "context_property_code" in e]
    assert ctx_entries == [
        {
            "context_property_code": "ctx:prop",
            "context_property_name": "Ctx Prop",
            "context_item_code": "ctx:item",
            "context_item_name": "Ctx Item",
        }
    ]


def test_header_without_property_or_context_excluded(memory_session):
    """A header with no joined metadata produces no entries."""
    session = memory_session
    _seed_minimal_table(session)
    session.commit()

    service = HierarchyService(session)
    result = service.get_table_modelling("T1")

    # Header_id 50 is present in the join (one row) but yields no entries.
    assert result.get(50, []) == []


def test_resolves_table_by_release_id(memory_session):
    """release_id selects the matching ModuleVersion + TableVersion."""
    session = memory_session
    session.add(Release(release_id=1, code="1.0", date=date(2024, 1, 1)))
    session.add(Release(release_id=2, code="2.0", date=date(2025, 1, 1)))
    session.add(Framework(framework_id=1, code="FW"))
    session.add(Module(module_id=1, framework_id=1))
    session.add(
        ModuleVersion(
            module_vid=10,
            module_id=1,
            code="MV1",
            start_release_id=1,
            end_release_id=2,
        )
    )
    session.add(
        ModuleVersion(
            module_vid=11,
            module_id=1,
            code="MV1",
            start_release_id=2,
            end_release_id=None,
        )
    )
    session.add(Table(table_id=100))
    session.add(
        TableVersion(
            table_vid=1000,
            table_id=100,
            code="T1",
            start_release_id=1,
        )
    )
    session.add(
        ModuleVersionComposition(module_vid=10, table_vid=1000, table_id=100)
    )
    session.add(
        ModuleVersionComposition(module_vid=11, table_vid=1000, table_id=100)
    )
    session.add(Header(header_id=50))
    session.add(HeaderVersion(header_vid=500, header_id=50))
    session.add(
        TableVersionHeader(
            table_vid=1000, header_vid=500, header_id=50, order=1
        )
    )
    session.commit()

    service = HierarchyService(session)
    # Both release_id=1 and release_id=2 should resolve the same table version
    # but pick a different module-version on the join. The query still works.
    assert service.get_table_modelling("T1", release_id=1) == {50: []}
    assert service.get_table_modelling("T1", release_id=2) == {50: []}


def test_item_membership_evaluated_at_requested_release(memory_session):
    """Items added in a later release must appear when that release is asked.

    Regression: previously the modelling query anchored item/category
    range comparisons at ``tv.start_release_id`` regardless of the
    caller's ``release_id`` — so items that gained membership after
    the table version was first published were silently invisible at
    later releases.
    """
    session = memory_session
    session.add(Release(release_id=1, code="1.0", date=date(2024, 1, 1)))
    session.add(Release(release_id=2, code="2.0", date=date(2025, 1, 1)))
    session.add(Framework(framework_id=1, code="FW"))
    session.add(Module(module_id=1, framework_id=1))
    session.add(
        ModuleVersion(
            module_vid=10,
            module_id=1,
            code="MV1",
            start_release_id=1,
            end_release_id=None,
        )
    )
    session.add(Table(table_id=100))
    # TableVersion starts at release 1 and is still active at release 2.
    session.add(
        TableVersion(
            table_vid=1000,
            table_id=100,
            code="T1",
            start_release_id=1,
            end_release_id=None,
        )
    )
    session.add(
        ModuleVersionComposition(module_vid=10, table_vid=1000, table_id=100)
    )
    session.add(Header(header_id=50, direction="X"))
    session.add(
        HeaderVersion(
            header_vid=500,
            header_id=50,
            code="H1",
            label="Header 1",
            property_id=200,
            context_id=None,
        )
    )
    session.add(
        TableVersionHeader(
            table_vid=1000, header_vid=500, header_id=50, order=1
        )
    )
    # The property item only gains category membership at release 2.
    session.add(Item(item_id=200, name="Main Prop"))
    session.add(Property(property_id=200))
    session.add(
        ItemCategory(
            item_id=200,
            start_release_id=2,
            end_release_id=None,
            signature="prop:main",
        )
    )
    session.commit()

    service = HierarchyService(session)
    # At release 1 the item-category does not yet exist -> no entry.
    at_release_1 = service.get_table_modelling("T1", release_id=1)
    assert at_release_1[50] == []
    # At release 2 the item-category is in scope -> one main_property entry.
    at_release_2 = service.get_table_modelling("T1", release_id=2)
    assert at_release_2[50] == [
        {"main_property_code": "prop:main", "main_property_name": "Main Prop"}
    ]
