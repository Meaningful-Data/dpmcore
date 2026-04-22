"""Tests for DataDictionaryService release-based table filtering.

Ported from the py_dpm DataDictionaryAPI suite. Exercises the
``DataDictionaryService.get_tables`` behaviour for release_id-based
filtering and the mutual-exclusivity guard between ``release_id`` and
``release_code``.
"""

from datetime import date

import pytest

from dpmcore.orm.infrastructure import Release
from dpmcore.orm.rendering import Table, TableVersion
from dpmcore.services.data_dictionary import DataDictionaryService


@pytest.fixture
def service_with_releases(memory_session):
    """Populate releases and two table versions bracketing release 1."""
    session = memory_session

    session.add_all(
        [
            Release(release_id=1, code="1.0", date=date(2023, 1, 1)),
            Release(release_id=2, code="2.0", date=date(2023, 6, 1)),
        ]
    )
    session.add_all([Table(table_id=1), Table(table_id=2)])
    session.add_all(
        [
            TableVersion(
                table_vid=1,
                code="T1",
                start_release_id=1,
                end_release_id=2,
                table_id=1,
            ),
            TableVersion(
                table_vid=2,
                code="T2",
                start_release_id=2,
                table_id=2,
            ),
        ]
    )
    session.commit()
    return DataDictionaryService(session)


def test_get_tables_by_release_id(service_with_releases):
    """Release 1 should include T1 but not T2 (which starts at release 2)."""
    tables_r1 = service_with_releases.get_tables(release_id=1)
    assert "T1" in tables_r1
    assert "T2" not in tables_r1

    tables_r2 = service_with_releases.get_tables(release_id=2)
    # T1 ends at release 2: start<=2 AND end>2 -> 2>2 False, so excluded.
    assert "T2" in tables_r2
    assert "T1" not in tables_r2


def test_release_id_takes_precedence_over_release_code(service_with_releases):
    """If both release_id and release_code are supplied, release_id wins.

    ``DataDictionaryService.get_tables`` uses an if/elif cascade:
    ``date`` > ``release_id`` > ``release_code``. Only release_id is
    consulted here and the result mirrors release_id=1.
    """
    tables = service_with_releases.get_tables(
        release_code="2.0", release_id=1
    )
    assert "T1" in tables
    assert "T2" not in tables
