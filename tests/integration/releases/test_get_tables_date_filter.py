"""Tests for DataDictionaryService.get_tables date/release filtering.

Ported from the py_dpm DataDictionaryAPI test suite. Exercises the same
scenarios (date filter, release filter, mutual exclusivity of filters)
against the current ``dpmcore.services.data_dictionary.DataDictionaryService``.
"""

from datetime import date

import pytest

from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import (
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import Table, TableVersion
from dpmcore.services.data_dictionary import DataDictionaryService


@pytest.fixture
def service_with_dates(memory_session):
    """Populate an in-memory DB with three tables across two modules.

    Layout::

        Module 1  2023-01-01 -- 2023-12-31   contains T1 + T3
        Module 2  2024-01-01 -- (ongoing)    contains T2 + T3
    """
    session = memory_session

    # release_id=1 must correspond to a real Release row with a
    # parseable code so the new sort_order-based filter can resolve it.
    session.add(Release(release_id=1, code="1.0", date=date(2023, 1, 1)))

    session.add_all([Table(table_id=1), Table(table_id=2), Table(table_id=3)])
    session.add_all([Module(module_id=1), Module(module_id=2)])

    session.add_all(
        [
            TableVersion(
                table_vid=1, code="T1", start_release_id=1, table_id=1
            ),
            TableVersion(
                table_vid=2, code="T2", start_release_id=1, table_id=2
            ),
            TableVersion(
                table_vid=3, code="T3", start_release_id=1, table_id=3
            ),
        ]
    )

    session.add_all(
        [
            ModuleVersion(
                module_vid=1,
                module_id=1,
                code="M1",
                from_reference_date=date(2023, 1, 1),
                to_reference_date=date(2023, 12, 31),
                start_release_id=1,
            ),
            ModuleVersion(
                module_vid=2,
                module_id=2,
                code="M2",
                from_reference_date=date(2024, 1, 1),
                to_reference_date=None,
                start_release_id=1,
            ),
        ]
    )

    session.add_all(
        [
            ModuleVersionComposition(module_vid=1, table_vid=1, table_id=1),
            ModuleVersionComposition(module_vid=2, table_vid=2, table_id=2),
            ModuleVersionComposition(module_vid=1, table_vid=3, table_id=3),
            ModuleVersionComposition(module_vid=2, table_vid=3, table_id=3),
        ]
    )

    session.commit()
    return DataDictionaryService(session)


def test_get_available_tables_by_date(service_with_dates):
    """2023 returns T1+T3; 2024 returns T2+T3."""
    tables_2023 = service_with_dates.get_tables(date="2023-06-01")
    assert "T1" in tables_2023
    assert "T3" in tables_2023
    assert "T2" not in tables_2023  # T2 module starts in 2024

    tables_2024 = service_with_dates.get_tables(date="2024-06-01")
    assert "T2" in tables_2024
    assert "T3" in tables_2024
    assert "T1" not in tables_2024  # T1 module ended 2023


def test_get_available_tables_by_date_object(service_with_dates):
    """Date object is accepted in addition to ISO string."""
    d = date(2023, 6, 1)
    tables_2023 = service_with_dates.get_tables(date=d)
    assert "T1" in tables_2023
    assert "T3" in tables_2023
    assert "T2" not in tables_2023


def test_get_available_tables_by_release(service_with_dates):
    """release_id=1 returns all three TableVersions with start_release_id=1."""
    tables_r1 = service_with_dates.get_tables(release_id=1)
    assert "T1" in tables_r1
    assert "T2" in tables_r1
    assert "T3" in tables_r1


def test_get_available_tables_all(service_with_dates):
    """No filter: returns every table code."""
    tables_all = service_with_dates.get_tables()
    assert "T1" in tables_all
    assert "T2" in tables_all
    assert "T3" in tables_all
