"""Integration tests for /api/v1/structure/module endpoints."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
from dpmcore.orm.glossary import (
    Category,
    Item,
    ItemCategory,
    Property,
    SubCategory,
    SubCategoryItem,
    SubCategoryVersion,
)
from dpmcore.orm.infrastructure import (
    Concept,
    DataType,
    Organisation,
    Release,
)
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleParameters,
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
from dpmcore.orm.variables import Variable, VariableVersion
from dpmcore.server.app import create_app

# ------------------------------------------------------------------ #
# Seed model
# ------------------------------------------------------------------ #
#
# Two modules in one framework, each with 3 tables. Module FINREP9 has
# parameter variables and full table structure on its first table
# (headers, cells, key + fact variables, ASSET_TYPE subcategory
# enumeration). The remaining tables are skeletal but real — enough
# for query-budget assertions to scale meaningfully.
# ------------------------------------------------------------------ #


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def seeded_engine(engine):
    session = Session(bind=engine)

    session.add(
        Organisation(
            org_id=1, name="European Banking Authority", acronym="EBA"
        )
    )
    session.flush()

    for guid in [
        "c-rel-1",
        "c-rel-2",
        "c-fw-1",
        "c-mod-1",
        "c-mod-2",
        "c-table-1",
        "c-table-2",
        "c-table-3",
        "c-table-4",
        "c-table-5",
        "c-table-6",
        "c-header-c",
        "c-header-r",
        "c-cell-1",
    ]:
        session.add(Concept(concept_guid=guid, owner_id=1))
    session.flush()

    session.add_all(
        [
            Release(
                release_id=1,
                code="4.0",
                date=date(2024, 1, 1),
                status="Final",
                is_current=False,
                row_guid="c-rel-1",
                owner_id=1,
            ),
            Release(
                release_id=2,
                code="4.1",
                date=date(2024, 6, 1),
                status="Final",
                is_current=True,
                row_guid="c-rel-2",
                owner_id=1,
            ),
        ]
    )
    session.flush()

    session.add(
        DataType(data_type_id=1, code="String", name="String", is_active=True)
    )
    session.flush()

    # Framework owning both modules.
    session.add(
        Framework(
            framework_id=10,
            code="FINREP",
            name="FINREP",
            description="Financial reporting",
            row_guid="c-fw-1",
            owner_id=1,
        )
    )
    session.flush()

    # Two modules.
    session.add_all(
        [
            Module(
                module_id=100,
                framework_id=10,
                row_guid="c-mod-1",
                is_document_module=False,
                owner_id=1,
            ),
            Module(
                module_id=101,
                framework_id=10,
                row_guid="c-mod-2",
                is_document_module=False,
                owner_id=1,
            ),
        ]
    )
    session.flush()

    session.add_all(
        [
            ModuleVersion(
                module_vid=10000,
                module_id=100,
                code="FINREP9",
                name="FINREP 9",
                description="Financial Reporting v9",
                version_number="9.0",
                start_release_id=1,
                end_release_id=None,
                from_reference_date=date(2024, 1, 1),
                to_reference_date=None,
                is_reported=True,
                is_calculated=False,
            ),
            ModuleVersion(
                module_vid=20000,
                module_id=101,
                code="COREP",
                name="COREP",
                description="Common Reporting",
                version_number="3.0",
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )
    session.flush()

    # 3 tables per module.
    table_specs = [
        (1, "F_01.01", "c-table-1"),
        (2, "F_02.00", "c-table-2"),
        (3, "F_03.00", "c-table-3"),
        (4, "C_01.00", "c-table-4"),
        (5, "C_02.00", "c-table-5"),
        (6, "C_03.00", "c-table-6"),
    ]
    for tid, _code, guid in table_specs:
        session.add(
            Table(
                table_id=tid,
                is_abstract=False,
                has_open_columns=False,
                has_open_rows=False,
                has_open_sheets=False,
                is_normalised=False,
                is_flat=False,
                row_guid=guid,
                owner_id=1,
            )
        )
    session.flush()
    for tid, code, _ in table_specs:
        session.add(
            TableVersion(
                table_vid=tid * 1000,
                code=code,
                name=f"Table {code}",
                description="",
                table_id=tid,
                start_release_id=1,
                end_release_id=None,
            )
        )
    session.flush()

    # ModuleVersionComposition — 3 tables per module in order.
    session.add_all(
        [
            ModuleVersionComposition(
                module_vid=10000, table_id=1, table_vid=1000, order=1
            ),
            ModuleVersionComposition(
                module_vid=10000, table_id=2, table_vid=2000, order=2
            ),
            ModuleVersionComposition(
                module_vid=10000, table_id=3, table_vid=3000, order=3
            ),
            ModuleVersionComposition(
                module_vid=20000, table_id=4, table_vid=4000, order=1
            ),
            ModuleVersionComposition(
                module_vid=20000, table_id=5, table_vid=5000, order=2
            ),
            ModuleVersionComposition(
                module_vid=20000, table_id=6, table_vid=6000, order=3
            ),
        ]
    )
    session.flush()

    # Full structure for table_vid=1000 (F_01.01) only.
    session.add_all(
        [
            Header(
                header_id=11,
                table_id=1,
                direction="x",
                is_key=False,
                is_attribute=False,
                row_guid="c-header-c",
                owner_id=1,
            ),
            Header(
                header_id=22,
                table_id=1,
                direction="y",
                is_key=True,
                is_attribute=False,
                row_guid="c-header-r",
                owner_id=1,
            ),
        ]
    )
    session.flush()

    # Key variable referenced by the row header.
    session.add(Variable(variable_id=89, type="k", owner_id=1))
    session.flush()
    session.add(
        VariableVersion(
            variable_vid=7777,
            variable_id=89,
            code="kv01",
            name="Row key",
            is_multi_valued=False,
            start_release_id=1,
            end_release_id=None,
        )
    )
    session.flush()

    # Enumerated category + subcategory the row header references.
    session.add(
        Category(
            category_id=60,
            code="ASSET_TYPE",
            name="Asset type",
            description="",
            is_enumerated=True,
            is_active=True,
            is_external_ref_data=False,
            created_release_id=1,
            owner_id=1,
        )
    )
    session.flush()
    session.add(
        SubCategory(
            subcategory_id=400,
            category_id=60,
            code="AT_SUB",
            name="Asset type subset",
            description="",
            owner_id=1,
        )
    )
    session.flush()
    session.add(
        SubCategoryVersion(
            subcategory_vid=4441,
            subcategory_id=400,
            start_release_id=1,
            end_release_id=None,
        )
    )
    session.flush()

    session.add_all(
        [
            HeaderVersion(
                header_vid=111,
                header_id=11,
                code="0010",
                label="Carrying amount",
                start_release_id=1,
                end_release_id=None,
            ),
            HeaderVersion(
                header_vid=222,
                header_id=22,
                code="010",
                label="Loans",
                key_variable_vid=7777,
                subcategory_vid=4441,
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )
    session.flush()

    session.add_all(
        [
            TableVersionHeader(
                table_vid=1000, header_id=11, header_vid=111, order=0
            ),
            TableVersionHeader(
                table_vid=1000, header_id=22, header_vid=222, order=1
            ),
        ]
    )
    session.flush()

    # Items + ItemCategory in the parent category.
    session.add_all(
        [
            Item(item_id=700, name="Loan", is_property=False, is_active=True),
            Item(item_id=701, name="Bond", is_property=False, is_active=True),
            Item(
                item_id=51,
                name="Asset property",
                is_property=True,
                is_active=True,
            ),
        ]
    )
    session.flush()
    session.add_all(
        [
            ItemCategory(
                item_id=700,
                start_release_id=1,
                category_id=60,
                code="LOAN",
                is_default_item=False,
                signature="ASSET_TYPE(LOAN)",
                end_release_id=None,
            ),
            ItemCategory(
                item_id=701,
                start_release_id=1,
                category_id=60,
                code="BOND",
                is_default_item=False,
                signature="ASSET_TYPE(BOND)",
                end_release_id=None,
            ),
        ]
    )
    session.flush()
    session.add_all(
        [
            SubCategoryItem(item_id=700, subcategory_vid=4441, order=1),
            SubCategoryItem(item_id=701, subcategory_vid=4441, order=2),
        ]
    )
    session.flush()

    session.add(
        Property(
            property_id=51,
            is_composite=False,
            is_metric=False,
            data_type_id=1,
            owner_id=1,
        )
    )
    session.flush()

    # Fact variable held by the cell.
    session.add(Variable(variable_id=88, type="d", owner_id=1))
    session.flush()
    session.add(
        VariableVersion(
            variable_vid=8888,
            variable_id=88,
            property_id=51,
            code="ei001",
            name="Asset value",
            is_multi_valued=False,
            start_release_id=1,
            end_release_id=None,
        )
    )
    session.flush()

    session.add(
        Cell(
            cell_id=9001,
            table_id=1,
            column_id=11,
            row_id=22,
            row_guid="c-cell-1",
            owner_id=1,
        )
    )
    session.flush()
    session.add(
        TableVersionCell(
            table_vid=1000,
            cell_id=9001,
            cell_code="{r010,c0010}",
            is_nullable=False,
            is_excluded=False,
            is_void=False,
            sign=None,
            variable_vid=8888,
        )
    )
    session.flush()

    # ModuleParameters — bind two variable versions as parameters of
    # FINREP9.
    session.add_all(
        [
            ModuleParameters(module_vid=10000, variable_vid=7777),
            ModuleParameters(module_vid=10000, variable_vid=8888),
        ]
    )
    session.commit()
    session.close()
    return engine


@pytest.fixture
def client(seeded_engine):
    from starlette.testclient import TestClient

    app = create_app("sqlite:///:memory:", engine=seeded_engine)
    return TestClient(app)


@pytest.fixture
def empty_client(engine):
    from starlette.testclient import TestClient

    app = create_app("sqlite:///:memory:", engine=engine)
    return TestClient(app)


def _count_queries(engine):
    """Context manager counting SQL statements issued on *engine*."""

    class _Counter:
        def __init__(self) -> None:
            self.count = 0

        def __enter__(self) -> "_Counter":
            def listener(
                conn, cursor, statement, params, context, executemany
            ):
                self.count += 1

            self._listener = listener
            event.listen(engine, "before_cursor_execute", listener)
            return self

        def __exit__(self, *exc):
            event.remove(engine, "before_cursor_execute", self._listener)
            return False

    return _Counter()


# ------------------------------------------------------------------ #
# Tests — default response (no children)
# ------------------------------------------------------------------ #


class TestSingleModule:
    def test_at_literal_release(self, client):
        resp = client.get("/api/v1/structure/module/EBA/FINREP9/4.0")
        assert resp.status_code == 200
        body = resp.json()
        assert "modules" in body["data"]
        modules = body["data"]["modules"]
        assert len(modules) == 1
        m = modules[0]
        assert m["code"] == "FINREP9"
        assert m["owner"] == "EBA"
        assert m["release"] == "4.0"
        assert m["moduleVersionId"] == 10000
        # No children by default.
        assert "tables" not in m
        # parameterVariableVersionIds always present.
        assert sorted(m["parameterVariableVersionIds"]) == [7777, 8888]
        # framework reference populated.
        assert m["framework"]["code"] == "FINREP"
        assert m["versionNumber"] == "9.0"
        assert m["isDocumentModule"] is False

    def test_latest_returns_module(self, client):
        resp = client.get("/api/v1/structure/module/EBA/FINREP9/~")
        assert resp.status_code == 200
        assert resp.json()["data"]["modules"][0]["moduleVersionId"] == 10000

    def test_latest_stable(self, client):
        resp = client.get("/api/v1/structure/module/EBA/FINREP9/+")
        assert resp.status_code == 200
        assert resp.json()["data"]["modules"][0]["release"] == "4.1"

    def test_nonexistent_code(self, client):
        resp = client.get("/api/v1/structure/module/EBA/NOPE/4.0")
        assert resp.status_code == 204

    def test_nonexistent_owner(self, client):
        resp = client.get("/api/v1/structure/module/UNKNOWN/FINREP9/4.0")
        assert resp.status_code == 204


class TestAllModules:
    def test_wildcard_returns_both(self, client):
        resp = client.get("/api/v1/structure/module/EBA/*/4.0")
        assert resp.status_code == 200
        codes = {m["code"] for m in resp.json()["data"]["modules"]}
        assert codes == {"FINREP9", "COREP"}

    def test_release_wildcard(self, client):
        resp = client.get("/api/v1/structure/module/EBA/*/*")
        assert resp.status_code == 200
        # Both modules have one ModuleVersion each → 2 entries total.
        assert resp.json()["meta"]["totalCount"] == 2


class TestAllstubs:
    def test_strips_subtrees(self, client):
        resp = client.get(
            "/api/v1/structure/module/EBA/FINREP9/4.0?detail=allstubs"
        )
        m = resp.json()["data"]["modules"][0]
        for key in (
            "tables",
            "parameterVariableVersionIds",
            "framework",
            "versionNumber",
        ):
            assert key not in m
        for key in ("id", "moduleVersionId", "code", "owner", "release"):
            assert key in m


class TestEmptyDatabase:
    def test_empty_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/module/EBA/FINREP9/4.0")
        assert resp.status_code == 204


# ------------------------------------------------------------------ #
# Tests — children
# ------------------------------------------------------------------ #


class TestChildren:
    def test_children_listed_in_composition_order(self, client):
        resp = client.get(
            "/api/v1/structure/module/EBA/FINREP9/4.0?references=children"
        )
        m = resp.json()["data"]["modules"][0]
        assert "tables" in m
        # ModuleVersionComposition.order: F_01.01, F_02.00, F_03.00.
        assert [t["code"] for t in m["tables"]] == [
            "F_01.01",
            "F_02.00",
            "F_03.00",
        ]

    def test_children_carry_full_table_shape(self, client):
        resp = client.get(
            "/api/v1/structure/module/EBA/FINREP9/4.0?references=children"
        )
        t = resp.json()["data"]["modules"][0]["tables"][0]  # F_01.01
        assert len(t["headers"]) == 2
        assert len(t["cells"]) == 1
        assert len(t["keyVariables"]) == 1
        assert len(t["factVariables"]) == 1
        # The fact variable inherits the row header's subcategory.
        fact = t["factVariables"][0]
        assert fact["isEnumerated"] is True
        enum = fact["enumeration"]
        assert enum["subcategoryCode"] == "AT_SUB"
        assert {i["code"] for i in enum["items"]} == {"LOAN", "BOND"}

    def test_references_all_includes_organisations(self, client):
        resp = client.get(
            "/api/v1/structure/module/EBA/FINREP9/4.0?references=all"
        )
        body = resp.json()
        assert "organisations" in body["data"]
        # Children also present under references=all.
        assert "tables" in body["data"]["modules"][0]


# ------------------------------------------------------------------ #
# Performance — query budget
# ------------------------------------------------------------------ #


class TestQueryBudget:
    """Guard against N+1 regressions in the children path.

    With 2 modules × 3 tables seeded, the children path must issue a
    bounded number of SQL statements independent of N×M.
    """

    def test_children_query_count_is_bounded(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get(
                "/api/v1/structure/module/EBA/*/4.0?references=children"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["totalCount"] == 2
        # Sanity: 6 tables total exposed across the two modules.
        total_tables = sum(len(m["tables"]) for m in body["data"]["modules"])
        assert total_tables == 6
        # Budget breakdown for the children path (current ≈ 18):
        #   3 release-resolution queries (filter_by_release internals,
        #     fired up to twice — once for the module query, once for
        #     subcategory ItemCategory windowing);
        #   1 ModuleVersion main, 1 ModuleParameters,
        #   1 Framework refs, 1 ModuleVersionComposition,
        #   1 TableVersion (Table joinedload), 1 headers, 1 cells,
        #   1 VariableVersion, 1 property names,
        #   3 SubCategory enumeration loads (SCV+SC+Cat / SCI+Item /
        #     ItemCategory), 1 Organisation lookup.
        # ≤22 leaves headroom for incidental changes while still
        # flagging the N+1 regressions this test exists to catch:
        # if the budget scaled with N modules × M tables it would
        # quickly exceed 100.
        assert counter.count <= 22, (
            f"children path issued {counter.count} queries — "
            f"likely an N+1 regression."
        )

    def test_default_path_minimal_queries(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get("/api/v1/structure/module/EBA/*/4.0")
        assert resp.status_code == 200
        # Without children: 3 release-resolution + module query +
        # parameters + framework refs + one owner lookup ≈ 7.
        assert counter.count <= 9, (
            f"default module path issued {counter.count} queries."
        )
