"""Tests for DataDictionaryService release lookups.

Ported from the py_dpm DataDictionaryAPI suite. Exercises
``get_releases``, ``get_release_by_id`` and their ordering/empty-db
semantics using dpmcore's service layer.
"""

from datetime import date

import pytest

from dpmcore.orm.infrastructure import Release
from dpmcore.services.data_dictionary import DataDictionaryService


@pytest.fixture
def service_with_data(memory_session):
    """Provide a service with three releases spanning the year."""
    session = memory_session

    session.add_all(
        [
            Release(
                release_id=1,
                code="R1",
                date=date(2023, 1, 1),
                description="Old Release",
                status="archived",
                is_current=False,
            ),
            Release(
                release_id=2,
                code="R2",
                date=date(2023, 6, 1),
                description="Current Release",
                status="active",
                is_current=True,
            ),
            Release(
                release_id=3,
                code="R3",
                date=date(2023, 12, 1),
                description="Future Release",
                status="planned",
                is_current=False,
            ),
        ]
    )
    session.commit()
    return DataDictionaryService(session)


def test_get_releases_returns_list_of_dicts(service_with_data):
    releases = service_with_data.get_releases()
    assert isinstance(releases, list)
    assert all(isinstance(r, dict) for r in releases)


def test_get_releases_returns_all_releases(service_with_data):
    releases = service_with_data.get_releases()
    assert len(releases) == 3


def test_get_releases_ordered_by_date_desc(service_with_data):
    releases = service_with_data.get_releases()
    dates = [r["date"] for r in releases]
    assert dates == sorted(dates, reverse=True)
    assert releases[0]["code"] == "R3"
    assert releases[1]["code"] == "R2"
    assert releases[2]["code"] == "R1"


def test_get_releases_content_mapping(service_with_data):
    """to_dict uses the Python attribute names (snake_case)."""
    releases = service_with_data.get_releases()
    r2 = next(r for r in releases if r["code"] == "R2")

    assert r2["release_id"] == 2
    assert r2["code"] == "R2"
    assert r2["date"] == date(2023, 6, 1)
    assert r2["description"] == "Current Release"
    assert r2["status"] == "active"
    assert r2["is_current"] is True


def test_get_releases_empty_db(memory_session):
    service = DataDictionaryService(memory_session)
    assert service.get_releases() == []


def test_get_release_by_id_returns_correct_release(service_with_data):
    release = service_with_data.get_release_by_id(2)
    assert release is not None
    assert release["release_id"] == 2
    assert release["code"] == "R2"
    assert release["description"] == "Current Release"


def test_get_release_by_id_returns_none_if_not_found(service_with_data):
    assert service_with_data.get_release_by_id(999) is None
