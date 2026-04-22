import pytest
from py_dpm.api.dpm.data_dictionary import DataDictionaryAPI
from py_dpm.dpm.models import (
    Base,
    ModuleVersion,
    ModuleVersionComposition,
    Table,
    TableVersion,
)


@pytest.fixture
def api_with_module_tables():
    """Set up an in-memory database with a module containing concrete and abstract tables."""
    db_url = "sqlite:///:memory:"
    api = DataDictionaryAPI(connection_url=db_url)
    Base.metadata.create_all(api.session.bind)

    # Module version
    mv = ModuleVersion(modulevid=10, moduleid=1, startreleaseid=1)

    # Concrete tables
    t1 = Table(tableid=1, isabstract=False)
    tv1 = TableVersion(
        tablevid=100, tableid=1, code="T01", name="Concrete Table 1"
    )

    t2 = Table(tableid=2, isabstract=False)
    tv2 = TableVersion(
        tablevid=200, tableid=2, code="T02", name="Concrete Table 2"
    )

    # Abstract table
    t3 = Table(tableid=3, isabstract=True)
    tv3 = TableVersion(
        tablevid=300, tableid=3, code="T03_ABS", name="Abstract Table"
    )

    # Link all tables to the module
    mvc1 = ModuleVersionComposition(modulevid=10, tableid=1, tablevid=100)
    mvc2 = ModuleVersionComposition(modulevid=10, tableid=2, tablevid=200)
    mvc3 = ModuleVersionComposition(modulevid=10, tableid=3, tablevid=300)

    api.session.add_all([mv, t1, t2, t3, tv1, tv2, tv3, mvc1, mvc2, mvc3])
    api.session.commit()

    yield api
    api.session.close()


def test_include_abstract_default_returns_all_tables(api_with_module_tables):
    """Default include_abstract=True returns both concrete and abstract tables."""
    result = api_with_module_tables.get_all_tables_for_module(module_vid=10)

    assert len(result) == 3
    codes = {r["table_code"] for r in result}
    assert codes == {"T01", "T02", "T03_ABS"}


def test_include_abstract_false_excludes_abstract_tables(
    api_with_module_tables,
):
    """include_abstract=False excludes abstract tables."""
    result = api_with_module_tables.get_all_tables_for_module(
        module_vid=10, include_abstract=False
    )

    assert len(result) == 2
    codes = {r["table_code"] for r in result}
    assert codes == {"T01", "T02"}


def test_include_abstract_true_returns_all_tables(api_with_module_tables):
    """Explicitly passing include_abstract=True returns all tables."""
    result = api_with_module_tables.get_all_tables_for_module(
        module_vid=10, include_abstract=True
    )

    assert len(result) == 3


def test_results_ordered_by_code(api_with_module_tables):
    """Results are ordered alphabetically by table code."""
    result = api_with_module_tables.get_all_tables_for_module(module_vid=10)

    codes = [r["table_code"] for r in result]
    assert codes == sorted(codes)


def test_result_structure(api_with_module_tables):
    """Each result dict contains table_vid, table_code, and table_name."""
    result = api_with_module_tables.get_all_tables_for_module(module_vid=10)

    for row in result:
        assert "table_vid" in row
        assert "table_code" in row
        assert "table_name" in row
        assert len(row) == 3


def test_nonexistent_module_returns_empty():
    """Querying a non-existent module returns an empty list."""
    db_url = "sqlite:///:memory:"
    api = DataDictionaryAPI(connection_url=db_url)
    Base.metadata.create_all(api.session.bind)

    result = api.get_all_tables_for_module(module_vid=999)
    assert result == []
    api.session.close()


def test_module_with_only_abstract_tables():
    """A module with only abstract tables returns empty when include_abstract=False."""
    db_url = "sqlite:///:memory:"
    api = DataDictionaryAPI(connection_url=db_url)
    Base.metadata.create_all(api.session.bind)

    mv = ModuleVersion(modulevid=20, moduleid=2, startreleaseid=1)
    t = Table(tableid=10, isabstract=True)
    tv = TableVersion(
        tablevid=1000, tableid=10, code="ABS_ONLY", name="Abstract Only"
    )
    mvc = ModuleVersionComposition(modulevid=20, tableid=10, tablevid=1000)

    api.session.add_all([mv, t, tv, mvc])
    api.session.commit()

    assert len(api.get_all_tables_for_module(module_vid=20)) == 1
    assert (
        api.get_all_tables_for_module(module_vid=20, include_abstract=False)
        == []
    )

    api.session.close()


def test_isabstract_null_treated_as_non_abstract():
    """Tables with isabstract=None (NULL) are included when include_abstract=False."""
    db_url = "sqlite:///:memory:"
    api = DataDictionaryAPI(connection_url=db_url)
    Base.metadata.create_all(api.session.bind)

    mv = ModuleVersion(modulevid=30, moduleid=3, startreleaseid=1)
    t = Table(tableid=20, isabstract=None)
    tv = TableVersion(
        tablevid=2000, tableid=20, code="NULL_ABS", name="Null Abstract"
    )
    mvc = ModuleVersionComposition(modulevid=30, tableid=20, tablevid=2000)

    api.session.add_all([mv, t, tv, mvc])
    api.session.commit()

    result = api.get_all_tables_for_module(
        module_vid=30, include_abstract=False
    )
    assert len(result) == 1
    assert result[0]["table_code"] == "NULL_ABS"

    api.session.close()
