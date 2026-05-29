"""Integration tests for /api/v1/structure/table endpoints."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
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
# Releases: 3.3 (Final), 3.4 (Final), 3.5 (Draft).
#
# A single Table (F_01.01) has two TableVersions:
#   - tvid=1000: active 3.3 only (start=1, end=2)
#   - tvid=2000: active 3.4+    (start=2, end=None)
#
# Headers: a column header (header_id=11) and a row header
# (header_id=22). The row header carries:
#   - key_variable_vid=7777 (a key variable)
#   - subcategory_vid=4441  (the row's allowed-values restriction)
# Both the key variable AND the fact variable in cells of that row
# inherit the row header's subcategory as their enumeration.
#
# Subcategory AT_SUB lives under category ASSET_TYPE and lists items
# LOAN, BOND, DEPOSIT via SubCategoryItem rows. The release-aware
# filter on each item's parent ItemCategory then yields:
#   - LOAN     valid at 3.3 only        (start=1, end=2)
#   - BOND     valid at all releases    (start=1, end=None)
#   - DEPOSIT  valid from 3.4 onward    (start=2, end=None)
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
    """Engine with the table fixture model pre-seeded."""
    session = Session(bind=engine)

    # Owner organisation + concepts.
    session.add(
        Organisation(
            org_id=1, name="European Banking Authority", acronym="EBA"
        )
    )
    session.flush()

    for guid in [
        "c-rel-1",
        "c-rel-2",
        "c-rel-3",
        "c-table-1",
        "c-header-c",
        "c-header-r",
        "c-cell-1",
        "c-var-1",
    ]:
        session.add(Concept(concept_guid=guid, owner_id=1))
    session.flush()

    # Releases.
    session.add_all(
        [
            Release(
                release_id=1,
                code="3.3",
                date=date(2024, 1, 1),
                description="Release 3.3",
                status="Final",
                is_current=False,
                row_guid="c-rel-1",
                owner_id=1,
            ),
            Release(
                release_id=2,
                code="3.4",
                date=date(2024, 6, 1),
                description="Release 3.4",
                status="Final",
                is_current=True,
                row_guid="c-rel-2",
                owner_id=1,
            ),
            Release(
                release_id=3,
                code="3.5",
                date=date(2024, 12, 1),
                description="Release 3.5 draft",
                status="Draft",
                is_current=False,
                row_guid="c-rel-3",
                owner_id=1,
            ),
        ]
    )
    session.flush()

    # DataType (required for Property FK target).
    session.add(
        DataType(data_type_id=1, code="String", name="String", is_active=True)
    )
    session.flush()

    # Table + two TableVersions (release windows differ).
    session.add(
        Table(
            table_id=100,
            is_abstract=False,
            has_open_columns=False,
            has_open_rows=False,
            has_open_sheets=False,
            is_normalised=False,
            is_flat=False,
            row_guid="c-table-1",
            owner_id=1,
        )
    )
    session.flush()
    session.add_all(
        [
            TableVersion(
                table_vid=1000,
                code="F_01.01",
                name="Balance sheet (v1)",
                description="Assets — first version",
                table_id=100,
                start_release_id=1,
                end_release_id=2,
            ),
            TableVersion(
                table_vid=2000,
                code="F_01.01",
                name="Balance sheet (v2)",
                description="Assets — second version",
                table_id=100,
                start_release_id=2,
                end_release_id=None,
            ),
        ]
    )
    session.flush()

    # Headers (one column, one row).
    session.add_all(
        [
            Header(
                header_id=11,
                table_id=100,
                direction="x",
                is_key=False,
                is_attribute=False,
                row_guid="c-header-c",
                owner_id=1,
            ),
            Header(
                header_id=22,
                table_id=100,
                direction="y",
                is_key=True,
                is_attribute=False,
                row_guid="c-header-r",
                owner_id=1,
            ),
        ]
    )
    session.flush()

    # Key variable used by the row header. Created early so the
    # HeaderVersion below can FK into it.
    session.add(Variable(variable_id=89, type="k", owner_id=1))
    session.flush()
    session.add(
        VariableVersion(
            variable_vid=7777,
            variable_id=89,
            property_id=None,
            code="kv01",
            name="Row key",
            is_multi_valued=False,
            start_release_id=1,
            end_release_id=None,
        )
    )
    session.flush()

    # Enumerated parent category (must exist before the SubCategory
    # FK below can resolve).
    session.add(
        Category(
            category_id=60,
            code="ASSET_TYPE",
            name="Asset type",
            description="Domain of assets",
            is_enumerated=True,
            is_active=True,
            is_external_ref_data=False,
            created_release_id=1,
            owner_id=1,
        )
    )
    session.flush()

    # SubCategory under ASSET_TYPE + a SubCategoryVersion that the
    # row header will reference. The version spans the whole timeline;
    # which items are visible at a given release is then governed by
    # each item's ItemCategory window (see below).
    session.add(
        SubCategory(
            subcategory_id=400,
            category_id=60,
            code="AT_SUB",
            name="Asset type subset",
            description="Allowed asset types for the row dimension",
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

    # HeaderVersions — row header carries key_variable_vid + the
    # subcategory that defines the row dimension's enumeration.
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

    # Bind headers to both table versions.
    session.add_all(
        [
            TableVersionHeader(
                table_vid=1000, header_id=11, header_vid=111, order=0
            ),
            TableVersionHeader(
                table_vid=1000, header_id=22, header_vid=222, order=1
            ),
            TableVersionHeader(
                table_vid=2000, header_id=11, header_vid=111, order=0
            ),
            TableVersionHeader(
                table_vid=2000, header_id=22, header_vid=222, order=1
            ),
        ]
    )
    session.flush()

    # Items + their (release-versioned) presence in ASSET_TYPE.
    session.add_all(
        [
            Item(item_id=700, name="Loan", is_property=False, is_active=True),
            Item(item_id=701, name="Bond", is_property=False, is_active=True),
            Item(
                item_id=702,
                name="Deposit",
                is_property=False,
                is_active=True,
            ),
            # The Property is itself an Item (subtype) — needs an Item row.
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
                end_release_id=2,  # alive at 3.3 only
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
            ItemCategory(
                item_id=702,
                start_release_id=2,
                category_id=60,
                code="DEPOSIT",
                is_default_item=True,
                signature="ASSET_TYPE(DEPOSIT)",
                end_release_id=None,
            ),
        ]
    )
    session.flush()

    # Items 700/701/702 become the SubCategoryVersion's members.
    session.add_all(
        [
            SubCategoryItem(item_id=700, subcategory_vid=4441, order=1),
            SubCategoryItem(item_id=701, subcategory_vid=4441, order=2),
            SubCategoryItem(item_id=702, subcategory_vid=4441, order=3),
        ]
    )
    session.flush()

    # Property kept for variable.property reference (no longer the
    # enumeration source).
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

    # Fact variables: one per TableVersion to exercise dedup and
    # version-aware enumeration windows.
    session.add(Variable(variable_id=88, type="d", owner_id=1))
    session.flush()
    session.add_all(
        [
            VariableVersion(
                variable_vid=8888,
                variable_id=88,
                property_id=51,
                code="ei001",
                name="Asset value (v1)",
                is_multi_valued=False,
                start_release_id=1,
                end_release_id=2,
            ),
            VariableVersion(
                variable_vid=9999,
                variable_id=88,
                property_id=51,
                code="ei002",
                name="Asset value (v2)",
                is_multi_valued=False,
                start_release_id=2,
                end_release_id=None,
            ),
        ]
    )
    session.flush()

    # One cell at (col=11, row=22), bound to each TableVersion with
    # its own variable_vid.
    session.add(
        Cell(
            cell_id=9001,
            table_id=100,
            column_id=11,
            row_id=22,
            sheet_id=None,
            row_guid="c-cell-1",
            owner_id=1,
        )
    )
    session.flush()
    session.add_all(
        [
            TableVersionCell(
                table_vid=1000,
                cell_id=9001,
                cell_code="{r010,c0010}",
                is_nullable=False,
                is_excluded=False,
                is_void=False,
                sign=None,
                variable_vid=8888,
            ),
            TableVersionCell(
                table_vid=2000,
                cell_id=9001,
                cell_code="{r010,c0010}",
                is_nullable=False,
                is_excluded=False,
                is_void=False,
                sign=None,
                variable_vid=9999,
            ),
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


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #


class TestSingleTable:
    def test_at_literal_release(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/3.3")
        assert resp.status_code == 200
        body = resp.json()
        assert "tables" in body["data"]
        tables = body["data"]["tables"]
        assert len(tables) == 1
        t = tables[0]
        assert t["code"] == "F_01.01"
        assert t["owner"] == "EBA"
        assert t["release"] == "3.3"
        assert t["tableVersionId"] == 1000

    def test_latest_returns_v2(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/~")
        assert resp.status_code == 200
        tables = resp.json()["data"]["tables"]
        assert len(tables) == 1
        assert tables[0]["tableVersionId"] == 2000

    def test_latest_stable_returns_v2(self, client):
        # 3.4 is the latest with status=Final; 3.5-draft is Draft.
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/+")
        assert resp.status_code == 200
        tables = resp.json()["data"]["tables"]
        assert len(tables) == 1
        assert tables[0]["tableVersionId"] == 2000
        assert tables[0]["release"] == "3.4"

    def test_nonexistent_code_returns_204(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_99.99/3.4")
        assert resp.status_code == 204

    def test_nonexistent_owner_returns_204(self, client):
        resp = client.get("/api/v1/structure/table/UNKNOWN/F_01.01/3.4")
        assert resp.status_code == 204

    def test_unknown_release_returns_204(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/9.9")
        assert resp.status_code == 204


class TestAllReleases:
    def test_release_wildcard_returns_both_versions(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/*")
        assert resp.status_code == 200
        body = resp.json()
        tables = body["data"]["tables"]
        assert len(tables) == 2
        vids = sorted(t["tableVersionId"] for t in tables)
        assert vids == [1000, 2000]
        # Each entry exposes its own start release.
        rels = sorted(t["release"] for t in tables)
        assert rels == ["3.3", "3.4"]
        assert body["meta"]["totalCount"] == 2

    def test_all_owners_wildcard_id(self, client):
        resp = client.get("/api/v1/structure/table/*/*/*")
        assert resp.status_code == 200
        assert resp.json()["meta"]["totalCount"] == 2


class TestHeadersAndCells:
    def test_headers_present_with_full_structural_set(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/3.4")
        t = resp.json()["data"]["tables"][0]
        headers = t["headers"]
        assert len(headers) == 2
        col = next(h for h in headers if h["direction"] == "x")
        assert col["code"] == "0010"
        assert col["label"] == "Carrying amount"
        assert col["isKey"] is False
        # locked-in shape — every header must expose these keys
        for key in (
            "headerVersionId",
            "property",
            "context",
            "subcategoryVersionId",
            "keyVariableVersionId",
            "startReleaseId",
            "endReleaseId",
        ):
            assert key in col

    def test_cells_reference_variable_version(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/3.3")
        t = resp.json()["data"]["tables"][0]
        assert len(t["cells"]) == 1
        cell = t["cells"][0]
        assert cell["cellCode"] == "{r010,c0010}"
        assert cell["columnHeaderId"] == 11
        assert cell["rowHeaderId"] == 22
        assert cell["variableVersionId"] == 8888

    def test_v2_cell_points_to_v2_variable(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/3.4")
        t = resp.json()["data"]["tables"][0]
        assert t["cells"][0]["variableVersionId"] == 9999


class TestFactVariableEnumeration:
    def test_fact_variable_is_enumerated(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/3.3")
        t = resp.json()["data"]["tables"][0]
        assert len(t["factVariables"]) == 1
        v = t["factVariables"][0]
        assert v["versionId"] == 8888
        assert v["isEnumerated"] is True
        # The enumeration is sourced from the row header's subcategory.
        enum = v["enumeration"]
        assert enum["subcategoryVersionId"] == 4441
        assert enum["subcategoryCode"] == "AT_SUB"
        assert enum["categoryCode"] == "ASSET_TYPE"

    def test_enumeration_items_at_3_3(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/3.3")
        t = resp.json()["data"]["tables"][0]
        codes = {
            i["code"] for i in t["factVariables"][0]["enumeration"]["items"]
        }
        # LOAN ends at 3.4 → still valid at 3.3. DEPOSIT not yet alive.
        assert codes == {"LOAN", "BOND"}

    def test_enumeration_items_at_3_4(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/3.4")
        t = resp.json()["data"]["tables"][0]
        codes = {
            i["code"] for i in t["factVariables"][0]["enumeration"]["items"]
        }
        # LOAN gone (end=2), DEPOSIT now alive.
        assert codes == {"BOND", "DEPOSIT"}

    def test_enumeration_items_carry_signature(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/3.4")
        t = resp.json()["data"]["tables"][0]
        items = t["factVariables"][0]["enumeration"]["items"]
        for it in items:
            assert "signature" in it
            assert it["signature"].startswith("ASSET_TYPE(")

    def test_release_wildcard_uses_per_version_window(self, client):
        """Each TableVersion in the response carries the enumeration
        active at its own start_release (not a single shared window).
        """
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/*")
        tables = resp.json()["data"]["tables"]
        by_vid = {t["tableVersionId"]: t for t in tables}
        v1_codes = {
            i["code"]
            for i in by_vid[1000]["factVariables"][0]["enumeration"]["items"]
        }
        v2_codes = {
            i["code"]
            for i in by_vid[2000]["factVariables"][0]["enumeration"]["items"]
        }
        assert v1_codes == {"LOAN", "BOND"}
        assert v2_codes == {"BOND", "DEPOSIT"}


class TestKeyVariables:
    def test_key_variable_present_and_separated(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/3.4")
        t = resp.json()["data"]["tables"][0]
        # Row header (header_id=22) carries key_variable_vid=7777 →
        # that variable must land in keyVariables, not factVariables.
        assert len(t["keyVariables"]) == 1
        k = t["keyVariables"][0]
        assert k["versionId"] == 7777
        assert k["code"] == "kv01"
        # The key variable also inherits the row header's subcategory
        # enumeration — same source as the fact variable in cells of
        # this row.
        assert k["isEnumerated"] is True
        assert k["enumeration"]["subcategoryVersionId"] == 4441
        # And the fact bucket holds the cell-referenced variable only.
        assert {v["versionId"] for v in t["factVariables"]} == {9999}

    def test_header_links_back_to_key_variable(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/3.4")
        t = resp.json()["data"]["tables"][0]
        row_header = next(h for h in t["headers"] if h["direction"] == "y")
        assert row_header["keyVariableVersionId"] == 7777
        assert row_header["subcategoryVersionId"] == 4441


class TestDetailParameter:
    def test_allstubs_strips_subtrees(self, client):
        resp = client.get(
            "/api/v1/structure/table/EBA/F_01.01/3.4?detail=allstubs"
        )
        t = resp.json()["data"]["tables"][0]
        for key in ("headers", "cells", "keyVariables", "factVariables"):
            assert key not in t
        # but identifiers are still present
        for key in ("id", "tableVersionId", "code", "owner", "release"):
            assert key in t


class TestReferencesAll:
    def test_includes_organisations(self, client):
        resp = client.get(
            "/api/v1/structure/table/EBA/F_01.01/3.4?references=all"
        )
        body = resp.json()
        assert "organisations" in body["data"]
        assert body["data"]["organisations"][0]["acronym"] == "EBA"

    def test_default_omits_organisations(self, client):
        resp = client.get("/api/v1/structure/table/EBA/F_01.01/3.4")
        assert "organisations" not in resp.json()["data"]


class TestEmptyDatabase:
    def test_empty_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/table/EBA/F_01.01/3.4")
        assert resp.status_code == 204
