"""Tests for DataDictionaryService.get_tables release-versioning logic.

Ported from the py_dpm suite, which exercised both the public
``DataDictionaryAPI.get_tables`` and the internal ``TableQuery`` helper.
``TableQuery`` has been removed: the service and the underlying
``filter_by_release`` helper are now the only entry points, so the
ported tests exercise the service directly.
"""

from datetime import date

import pytest

from dpmcore.orm.glossary import ItemCategory
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.rendering import TableVersion
from dpmcore.services.data_dictionary import DataDictionaryService


@pytest.fixture
def service_with_data(memory_session):
    """Insert three TableVersions spanning three releases."""
    session = memory_session
    # Release-range filter resolves the target's sort_order (parsed
    # from semver code), so each release_id used in a filter must
    # correspond to a real Release row with a parseable code.
    session.add_all(
        [
            Release(release_id=1, code="1.0", date=date(2024, 1, 1)),
            Release(release_id=2, code="2.0", date=date(2024, 6, 1)),
            Release(release_id=3, code="3.0", date=date(2025, 1, 1)),
        ]
    )

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
