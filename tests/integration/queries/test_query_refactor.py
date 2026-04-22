"""Tests for DataDictionaryService.get_tables release-versioning logic.

Ported from the py_dpm suite, which exercised both the public
``DataDictionaryAPI.get_tables`` and the internal ``TableQuery`` helper.
``TableQuery`` has been removed: the service and the underlying
``filter_by_release`` helper are now the only entry points, so the
ported tests exercise the service directly.
"""

import pytest

from dpmcore.orm.glossary import ItemCategory
from dpmcore.orm.rendering import TableVersion
from dpmcore.services.data_dictionary import DataDictionaryService


@pytest.fixture
def service_with_data(memory_session):
    """Insert three TableVersions spanning three releases."""
    session = memory_session

    session.add_all(
        [
            TableVersion(table_vid=1, code="T1", start_release_id=1),
            TableVersion(
                table_vid=2,
                code="T2",
                start_release_id=2,
                end_release_id=3,
            ),
            TableVersion(
                table_vid=3,
                code="T3",
                start_release_id=1,
                end_release_id=1,
            ),
        ]
    )
    session.add(
        ItemCategory(
            item_id=1,
            code="I1",
            signature="Sig1",
            start_release_id=1,
        )
    )
    session.commit()
    return DataDictionaryService(session)


def test_get_tables_all_no_filter(service_with_data):
    """No filter: returns all table codes."""
    tables = service_with_data.get_tables()
    assert "T1" in tables
    assert "T2" in tables
    assert "T3" in tables


def test_get_tables_release_id_filter_release_1(service_with_data):
    """Release 1: start<=1 AND (end IS NULL OR end>1)."""
    tables_r1 = service_with_data.get_tables(release_id=1)
    assert "T1" in tables_r1  # start=1, end=NULL
    assert "T2" not in tables_r1  # start=2 > 1
    assert "T3" not in tables_r1  # end=1 -> end>release (1>1) False


def test_get_tables_release_id_filter_release_2(service_with_data):
    """Release 2: picks up T1 and T2 but not T3 (already expired)."""
    tables_r2 = service_with_data.get_tables(release_id=2)
    assert "T1" in tables_r2
    assert "T2" in tables_r2  # start=2<=2, end=3>2
    assert "T3" not in tables_r2
