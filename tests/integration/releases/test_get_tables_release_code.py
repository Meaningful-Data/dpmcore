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


def test_release_id_and_release_code_are_mutually_exclusive(
    service_with_releases,
):
    """Passing both release_id and release_code must raise.

    Previously ``release_code`` was silently a no-op when
    ``filter_by_release`` was given both, which masked caller bugs.
    With ``release_code`` now actually resolving via ``Release.code``,
    the two are exclusive and the resolver raises ``ValueError``.
    """
    with pytest.raises(ValueError, match="maximum of one"):
        service_with_releases.get_tables(release_code="2.0", release_id=1)


def test_get_tables_by_release_code(service_with_releases):
    """release_code resolves to the matching release_id and filters."""
    tables = service_with_releases.get_tables(release_code="1.0")
    assert "T1" in tables
    assert "T2" not in tables


def test_unknown_release_code_raises(service_with_releases):
    """An unknown release code surfaces a ValueError from the resolver."""
    with pytest.raises(ValueError, match="not found"):
        service_with_releases.get_tables(release_code="999.0")
