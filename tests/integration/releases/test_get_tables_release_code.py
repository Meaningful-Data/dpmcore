from datetime import date

import pytest
from py_dpm.api.dpm.data_dictionary import DataDictionaryAPI
from py_dpm.dpm.models import Base, Release, Table, TableVersion


@pytest.fixture
def api_with_releases():
    db_url = "sqlite:///:memory:"
    api = DataDictionaryAPI(connection_url=db_url)
    Base.metadata.create_all(api.session.bind)

    # Create Releases
    r1 = Release(releaseid=1, code="1.0", date=date(2023, 1, 1))
    r2 = Release(releaseid=2, code="2.0", date=date(2023, 6, 1))
    api.session.add_all([r1, r2])

    # Create Tables
    tab1 = Table(tableid=1)
    tab2 = Table(tableid=2)
    api.session.add_all([tab1, tab2])

    # TableVersions
    # T1 exists in Release 1.0 (releaseid=1)
    t1 = TableVersion(
        tablevid=1, code="T1", startreleaseid=1, endreleaseid=2, tableid=1
    )  # Ends exactly when R2 starts or before?
    # Logic in filter_by_release is: start <= release_id AND (end is NULL OR end > release_id)
    # If T1 is valid for R1(1): 1 <= 1 AND (2 > 1) -> True.
    # If T1 is valid for R2(2): 1 <= 2 AND (2 > 2) -> False.

    # T2 starts in Release 2.0 (id=2)
    t2 = TableVersion(tablevid=2, code="T2", startreleaseid=2, tableid=2)

    api.session.add_all([t1, t2])
    api.session.commit()

    yield api
    api.session.close()


def test_get_tables_by_release_code(api_with_releases):
    # Test getting tables for Release 1.0
    tables_r1 = api_with_releases.get_tables(release_code="1.0")
    # API returns list of dicts, check if T1 code is in any of them
    assert any(t["code"] == "T1" for t in tables_r1)
    assert not any(t["code"] == "T2" for t in tables_r1)

    # Test getting tables for Release 2.0
    tables_r2 = api_with_releases.get_tables(release_code="2.0")
    assert any(t["code"] == "T2" for t in tables_r2)
    assert not any(t["code"] == "T1" for t in tables_r2)


def test_get_tables_invalid_release_code(api_with_releases):
    with pytest.raises(ValueError, match="Release code '9.9' not found"):
        api_with_releases.get_tables(release_code="9.9")


def test_mutual_exclusivity_with_release_code(api_with_releases):
    with pytest.raises(ValueError, match="Specify a maximum of one"):
        api_with_releases.get_tables(release_code="1.0", release_id=1)
