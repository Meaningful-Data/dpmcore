from datetime import date

import pytest
from py_dpm.api.dpm.data_dictionary import DataDictionaryAPI
from py_dpm.dpm.models import Base, Release


# Fixture to set up the in-memory database and API
@pytest.fixture
def api_with_data():
    # Use in-memory SQLite database
    db_url = "sqlite:///:memory:"
    api = DataDictionaryAPI(connection_url=db_url)

    # Create tables
    Base.metadata.create_all(api.session.bind)

    # Insert test data
    release1 = Release(
        releaseid=1,
        code="R1",
        date=date(2023, 1, 1),
        description="Old Release",
        status="archived",
        iscurrent=False,
    )
    release2 = Release(
        releaseid=2,
        code="R2",
        date=date(2023, 6, 1),
        description="Current Release",
        status="active",
        iscurrent=True,
    )
    release3 = Release(
        releaseid=3,
        code="R3",
        date=date(2023, 12, 1),
        description="Future Release",
        status="planned",
        iscurrent=False,
    )

    api.session.add_all([release1, release2, release3])
    api.session.commit()

    yield api

    # Teardown (close session)
    api.session.close()


def test_get_releases_returns_correct_type(api_with_data):
    """Test that get_releases returns a list of dictionaries."""
    releases = api_with_data.get_releases()
    assert isinstance(releases, list)
    assert all(isinstance(r, dict) for r in releases)


def test_get_releases_returns_all_releases(api_with_data):
    """Test that get_releases returns all releases in the database."""
    releases = api_with_data.get_releases()
    assert len(releases) == 3


def test_get_releases_ordered_by_date_desc(api_with_data):
    """Test that releases are ordered by date descending."""
    releases = api_with_data.get_releases()
    dates = [r["date"] for r in releases]
    assert dates == sorted(dates, reverse=True)
    assert releases[0]["code"] == "R3"
    assert releases[1]["code"] == "R2"
    assert releases[2]["code"] == "R1"


def test_get_releases_content_mapping(api_with_data):
    """Test that dictionary fields are correctly mapped from the database."""
    releases = api_with_data.get_releases()
    r2 = next(r for r in releases if r["code"] == "R2")

    assert r2["releaseid"] == 2
    assert r2["code"] == "R2"
    assert r2["date"] == date(2023, 6, 1)
    assert r2["description"] == "Current Release"
    assert r2["status"] == "active"
    assert r2["iscurrent"] is True


def test_get_releases_empty_db():
    """Test get_releases with an empty database."""
    db_url = "sqlite:///:memory:"
    api = DataDictionaryAPI(connection_url=db_url)
    Base.metadata.create_all(api.session.bind)

    releases = api.get_releases()
    assert releases == []
    api.session.close()


def test_get_release_by_id_returns_correct_release(api_with_data):
    """Test that get_release_by_id returns the correct release."""
    release = api_with_data.get_release_by_id(2)
    assert release is not None
    assert release["releaseid"] == 2
    assert release["code"] == "R2"
    assert release["description"] == "Current Release"


def test_get_release_by_id_returns_none_if_not_found(api_with_data):
    """Test that get_release_by_id returns None for non-existent ID."""
    release = api_with_data.get_release_by_id(999)
    assert release is None
