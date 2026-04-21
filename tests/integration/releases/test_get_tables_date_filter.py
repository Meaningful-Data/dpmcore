from datetime import date

import pytest
from py_dpm.api.dpm.data_dictionary import DataDictionaryAPI
from py_dpm.dpm.models import (
    Base,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
    Table,
    TableVersion,
)


@pytest.fixture
def api_with_dates():
    db_url = "sqlite:///:memory:"
    api = DataDictionaryAPI(connection_url=db_url)
    Base.metadata.create_all(api.session.bind)

    # Create root objects
    # Table model likely does not have 'code' based on error.
    # We will instantiate with minimal required fields.
    tab1 = Table(tableid=1)
    tab2 = Table(tableid=2)
    tab3 = Table(tableid=3)
    api.session.add_all([tab1, tab2, tab3])

    mod1 = Module(moduleid=1)
    mod2 = Module(moduleid=2)
    api.session.add_all([mod1, mod2])

    # Tables
    # Note: TableVersion usually links to Table via tableid
    t1 = TableVersion(tablevid=1, code="T1", startreleaseid=1, tableid=1)
    t2 = TableVersion(tablevid=2, code="T2", startreleaseid=1, tableid=2)
    t3 = TableVersion(tablevid=3, code="T3", startreleaseid=1, tableid=3)

    api.session.add_all([t1, t2, t3])

    # Modules
    # M1 active from 2023-01-01 to 2023-12-31
    m1 = ModuleVersion(
        modulevid=1,
        moduleid=1,
        code="M1",
        fromreferencedate=date(2023, 1, 1),
        toreferencedate=date(2023, 12, 31),
        startreleaseid=1,
    )
    # M2 active from 2024-01-01 (ongoing)
    m2 = ModuleVersion(
        modulevid=2,
        moduleid=2,
        code="M2",
        fromreferencedate=date(2024, 1, 1),
        toreferencedate=None,
        startreleaseid=1,
    )

    api.session.add_all([m1, m2])

    # Composition
    # T1 is in M1 (2023)
    c1 = ModuleVersionComposition(modulevid=1, tablevid=1, tableid=1)

    # T2 is in M2 (2024+)
    c2 = ModuleVersionComposition(modulevid=2, tablevid=2, tableid=2)

    # T3 is in both
    c3a = ModuleVersionComposition(modulevid=1, tablevid=3, tableid=3)
    c3b = ModuleVersionComposition(modulevid=2, tablevid=3, tableid=3)

    api.session.add_all([c1, c2, c3a, c3b])

    api.session.commit()
    yield api
    api.session.close()


def test_get_available_tables_by_date(api_with_dates):
    # Search in 2023 -> Should get T1 and T3
    tables_2023 = api_with_dates.get_tables(date="2023-06-01")
    assert any(t["code"] == "T1" for t in tables_2023)
    assert any(t["code"] == "T3" for t in tables_2023)
    assert not any(t["code"] == "T2" for t in tables_2023)  # T2 starts 2024

    # Search in 2024 -> Should get T2 and T3
    tables_2024 = api_with_dates.get_tables(date="2024-06-01")
    assert any(t["code"] == "T2" for t in tables_2024)
    assert any(t["code"] == "T3" for t in tables_2024)
    assert not any(t["code"] == "T1" for t in tables_2024)  # T1 ended 2023


def test_mutual_exclusivity(api_with_dates):
    with pytest.raises(
        ValueError,
        match="Specify a maximum of one of release_id, release_code or date",
    ):
        api_with_dates.get_tables(date="2024-01-01", release_id=1)


def test_get_available_tables_by_date_object(api_with_dates):
    # Pass date object instead of string
    d = date(2023, 6, 1)
    tables_2023 = api_with_dates.get_tables(date=d)
    assert any(t["code"] == "T1" for t in tables_2023)
    assert any(t["code"] == "T3" for t in tables_2023)
    assert not any(t["code"] == "T2" for t in tables_2023)


def test_get_available_tables_by_release(api_with_dates):
    # Release 1
    # T1: start 1
    # T2: start 1
    # T3: start 1
    tables_r1 = api_with_dates.get_tables(release_id=1)
    assert any(t["code"] == "T1" for t in tables_r1)
    assert any(t["code"] == "T2" for t in tables_r1)
    assert any(t["code"] == "T3" for t in tables_r1)


def test_get_available_tables_all(api_with_dates):
    # No params -> should return all tables
    tables_all = api_with_dates.get_tables()
    assert any(t["code"] == "T1" for t in tables_all)
    assert any(t["code"] == "T2" for t in tables_all)
    assert any(t["code"] == "T3" for t in tables_all)
