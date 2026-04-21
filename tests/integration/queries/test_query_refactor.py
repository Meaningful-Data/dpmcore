import pytest
from py_dpm.api.dpm.data_dictionary import DataDictionaryAPI
from py_dpm.dpm.models import Base, ItemCategory, TableVersion
from py_dpm.dpm.queries.tables import TableQuery


@pytest.fixture
def api_with_data():
    db_url = "sqlite:///:memory:"
    api = DataDictionaryAPI(connection_url=db_url)
    Base.metadata.create_all(api.session.bind)

    # Insert test data
    t1 = TableVersion(tablevid=1, code="T1", startreleaseid=1)
    t2 = TableVersion(tablevid=2, code="T2", startreleaseid=2, endreleaseid=3)
    t3 = TableVersion(tablevid=3, code="T3", startreleaseid=1, endreleaseid=1)

    api.session.add_all([t1, t2, t3])

    # Items
    i1 = ItemCategory(itemid=1, code="I1", signature="Sig1", startreleaseid=1)
    api.session.add(i1)

    api.session.commit()
    yield api
    api.session.close()


def test_get_available_tables_all(api_with_data):
    tables = api_with_data.get_tables()
    assert any(t["code"] == "T1" for t in tables)
    assert any(t["code"] == "T2" for t in tables)
    assert any(t["code"] == "T3" for t in tables)
    # Logic note: if release_id is None, it returns all in the new implementation?
    # TableQuery implementation: if release_id is None, filter_by_release returns query unmodified (all).
    # Original implementation: if release_id is None, it did NOT filter. So same behavior.

    # Wait, my logic for TableQuery filter_by_release: "if release_id is None: return query"
    # So yes, it returns all.


def test_get_available_tables_filtered(api_with_data):
    # Release 1
    tables_r1 = api_with_data.get_tables(release_id=1)
    # T1: start 1, end None -> Valid
    # T2: start 2 -> Invalid
    # T3: start 1, end 1 -> Invalid (end > release_id check: 1 > 1 False). Wait.
    # Logic: start <= release AND (end IS NULL OR end > release)
    # T3: end=1. 1 > 1 is False. So if release_id is 1, T3 (which ends at 1) should it be included?
    # Usually "end release" means it was removed IN that release or AFTER?
    # Standard DPM logic: If EndReleaseID is 1, it means it is NOT present in release 1? Or present up to 1?
    # Let's check original code logic:
    # or_(end is None, end > release_id)
    # If end == release_id, then (release_id > release_id) is False. So it is EXCLUDED.
    # Implementation: EndReleaseID is the release WHERE IT STOPPED existing (or was replaced).
    # So valid in [Start, End).

    assert any(t["code"] == "T1" for t in tables_r1)
    assert not any(t["code"] == "T2" for t in tables_r1)
    assert not any(
        t["code"] == "T3" for t in tables_r1
    )  # EndRelease 1 > 1 False.

    # Release 2
    tables_r2 = api_with_data.get_tables(release_id=2)
    assert any(t["code"] == "T1" for t in tables_r2)
    assert any(t["code"] == "T2" for t in tables_r2)  # Start 2<=2, End 3>2.
    assert not any(t["code"] == "T3" for t in tables_r2)


def test_new_query_objects_direct_usage(api_with_data):
    # Test using TableQuery directly and to_df
    q = TableQuery.get_tables(api_with_data.session, release_id=1)
    df = q.to_df()
    # df should have column matching the query
    # distinct(TableVersion.code) -> label might be 'code' or anon
    assert not df.empty
    # Just checking it runs and returns dataframe
