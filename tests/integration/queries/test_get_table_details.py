"""Tests for HierarchyService.get_table_details.

Ported from the py_dpm ``HierarchicalQuery.get_table_details`` suite.

The new ``HierarchyService.get_table_details`` is intentionally leaner:
it returns the TableVersion's ``to_dict()`` output augmented with
``headers`` and ``cells`` (each serialised via their own ``to_dict``).
Property / enumeration / data-type enrichment has been removed from
the core query — the ported tests therefore focus on the behaviour that
still exists: structure lookup, release filtering, and the handling of
missing tables.
"""

from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import (
    Cell,
    Header,
    HeaderVersion,
    Table,
    TableVersion,
    TableVersionCell,
    TableVersionHeader,
)
from dpmcore.orm.variables import VariableVersion
from dpmcore.services.hierarchy import HierarchyService


def test_get_table_details_structure(memory_session):
    session = memory_session

    session.add(Framework(framework_id=1, code="FW1"))
    session.add(Module(module_id=1, framework_id=1))
    session.add(ModuleVersion(module_vid=10, module_id=1, start_release_id=1))

    session.add(Table(table_id=100))
    session.add(
        TableVersion(table_vid=1000, table_id=100, code="T1", name="Table 1")
    )

    session.add(Header(header_id=1, direction="X", is_key=True))
    session.add(
        HeaderVersion(
            header_vid=10,
            header_id=1,
            code="H1",
            label="Header 1",
            property_id=1,
        )
    )
    session.add(
        TableVersionHeader(
            table_vid=1000,
            header_vid=10,
            header_id=1,
            order=1,
            is_abstract=False,
        )
    )

    session.add(
        ModuleVersionComposition(module_vid=10, table_vid=1000, table_id=100)
    )

    session.add(VariableVersion(variable_vid=500, variable_id=50, code="V1"))
    session.add(Cell(cell_id=900, table_id=100, column_id=1))
    session.add(
        TableVersionCell(
            table_vid=1000,
            cell_id=900,
            variable_vid=500,
            is_nullable=True,
            is_void=False,
            is_excluded=False,
        )
    )
    session.commit()

    service = HierarchyService(session)
    result = service.get_table_details(table_code="T1")

    assert result is not None
    assert result["code"] == "T1"
    assert result["name"] == "Table 1"
    assert result["table_vid"] == 1000

    assert len(result["headers"]) == 1
    header = result["headers"][0]
    assert header["code"] == "H1"
    assert header["label"] == "Header 1"

    assert len(result["cells"]) == 1
    cell_res = result["cells"][0]
    assert cell_res["cell_id"] == 900
    assert cell_res["column_id"] == 1


def test_get_table_details_filtering_by_release_id(memory_session):
    """release_id filter picks the TableVersion valid at that release."""
    session = memory_session

    session.add(Table(table_id=1))
    session.add(
        TableVersion(
            table_vid=101,
            table_id=1,
            code="T_MULTI",
            name="Table V1",
            start_release_id=1,
            end_release_id=2,
        )
    )
    session.add(
        TableVersion(
            table_vid=102,
            table_id=1,
            code="T_MULTI",
            name="Table V2",
            start_release_id=2,
            end_release_id=None,
        )
    )

    # Minimal linkage so the query picks something up.
    session.add(Header(header_id=99))
    session.add(HeaderVersion(header_vid=999, header_id=99))
    session.add(
        TableVersionHeader(table_vid=101, header_vid=999, header_id=99)
    )
    session.add(
        TableVersionHeader(table_vid=102, header_vid=999, header_id=99)
    )
    session.commit()

    service = HierarchyService(session)

    res1 = service.get_table_details("T_MULTI", release_id=1)
    assert res1 is not None
    assert res1["table_vid"] == 101
    assert res1["name"] == "Table V1"

    # release_id=2 -> start<=2 AND (end>2 OR NULL); TV1 ends at 2 so 2>2 False,
    # TV2 starts 2 end NULL -> kept.
    res2 = service.get_table_details("T_MULTI", release_id=2)
    assert res2 is not None
    assert res2["table_vid"] == 102
    assert res2["name"] == "Table V2"


def test_get_table_details_missing_table_returns_none(memory_session):
    """Unknown table_code returns None (replaces py_dpm's ValueError)."""
    service = HierarchyService(memory_session)
    assert service.get_table_details("UNKNOWN_TABLE") is None
