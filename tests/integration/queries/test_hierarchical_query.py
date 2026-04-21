import pytest
from py_dpm.api.dpm.data_dictionary import DataDictionaryAPI
from py_dpm.dpm.models import (
    Base,
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
    Table,
    TableVersion,
)
from py_dpm.dpm.queries.hierarchical_queries import HierarchicalQuery


@pytest.fixture
def session():
    db_url = "sqlite:///:memory:"
    api = DataDictionaryAPI(connection_url=db_url)
    Base.metadata.create_all(api.session.bind)
    yield api.session
    api.session.close()


def test_get_all_frameworks_structure(session):
    # Setup Data
    fw = Framework(
        frameworkid=1, code="FW1", name="Framework 1", description="Desc FW1"
    )

    mod = Module(moduleid=1, frameworkid=1)

    mv = ModuleVersion(
        modulevid=10,
        moduleid=1,
        code="MV1",
        name="Module Ver 1",
        startreleaseid=1,
        endreleaseid=None,
        versionnumber="1.0",
    )

    t = Table(tableid=100, isabstract=False)

    tv = TableVersion(
        tablevid=1000,
        tableid=100,
        code="TV1",
        name="Table Ver 1",
        startreleaseid=1,
        endreleaseid=None,
    )

    mvc = ModuleVersionComposition(modulevid=10, tablevid=1000, tableid=100)

    session.add_all([fw, mod, mv, t, tv, mvc])
    session.commit()

    # Test Query
    result = HierarchicalQuery.get_all_frameworks(session)

    # Assertions
    assert len(result) == 1
    fw_res = result[0]

    # Check Framework Fields (renaming logic)
    assert fw_res["code"] == "FW1"
    assert fw_res["name"] == "Framework 1"
    assert fw_res["description"] == "Desc FW1"

    # Check Nested Module Version
    assert len(fw_res["module_versions"]) == 1
    mv_res = fw_res["module_versions"][0]
    assert mv_res["code"] == "MV1"
    assert mv_res["name"] == "Module Ver 1"
    assert mv_res["versionnumber"] == "1.0"

    # Check Nested Table Version
    assert len(mv_res["table_versions"]) == 1
    tv_res = mv_res["table_versions"][0]
    assert tv_res["code"] == "TV1"
    assert tv_res["name"] == "Table Ver 1"
    assert tv_res["tableid"] == 100
    assert tv_res["isabstract"] is False


def test_get_all_frameworks_filtering(session):
    # Setup Data for Filtering
    fw = Framework(frameworkid=1, code="FW1")
    mod = Module(moduleid=1, frameworkid=1)

    # Active in Release 1
    mv1 = ModuleVersion(
        modulevid=11, moduleid=1, startreleaseid=1, endreleaseid=2
    )
    # Active in Release 2
    mv2 = ModuleVersion(
        modulevid=12, moduleid=1, startreleaseid=2, endreleaseid=None
    )

    # Setup meaningless table associations just to satisfy join
    t = Table(tableid=1)
    tv = TableVersion(tablevid=101, tableid=1, startreleaseid=1)
    mvc1 = ModuleVersionComposition(modulevid=11, tablevid=101, tableid=1)
    mvc2 = ModuleVersionComposition(modulevid=12, tablevid=101, tableid=1)

    session.add_all([fw, mod, mv1, mv2, t, tv, mvc1, mvc2])
    session.commit()

    # Filter by Release 1
    res_r1 = HierarchicalQuery.get_all_frameworks(session, release_id=1)
    # Expect mv1 (1<=1, 2>1)
    # mv2 (2<=1 False) -> Excluded

    assert len(res_r1) == 1
    mvs_r1 = res_r1[0]["module_versions"]
    assert len(mvs_r1) == 1
    assert mvs_r1[0]["modulevid"] == 11

    # Filter by Release 2
    res_r2 = HierarchicalQuery.get_all_frameworks(session, release_id=2)
    # Expect mv2 (2<=2, None)
    # mv1 (1<=2, 2>2 False) -> Excluded (standard logic: end_release > release_id)

    assert len(res_r2) == 1
    mvs_r2 = res_r2[0]["module_versions"]
    assert len(mvs_r2) == 1
    assert mvs_r2[0]["modulevid"] == 12
