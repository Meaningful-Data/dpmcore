"""Integration tests for /api/v1/structure/tablegroup endpoints."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
from dpmcore.orm.infrastructure import Concept, Organisation, Release
from dpmcore.orm.rendering import (
    Table,
    TableGroup,
    TableGroupComposition,
    TableVersion,
)
from dpmcore.server.app import create_app

# ------------------------------------------------------------------ #
# Seed model
# ------------------------------------------------------------------ #
#
# Two releases (4.0, 4.1). Hierarchy:
#
#   ROOT_BS (id=100, no parent)
#     ├── BS_ASSETS  (id=200, parent=100)
#     └── BS_LIABS   (id=201, parent=100)
#
# Compositions:
#   ROOT_BS contains tables 1 + 2 at 4.0 only (TableGroupComposition
#     end_release_id=2 → gone at 4.1).
#   BS_ASSETS contains table 1 at both releases.
#   BS_LIABS  contains table 2 at both releases.
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
    s = Session(bind=engine)

    s.add(
        Organisation(
            org_id=1, name="European Banking Authority", acronym="EBA"
        )
    )
    s.flush()

    for guid in [
        "c-rel-1",
        "c-rel-2",
        "c-tbl-1",
        "c-tbl-2",
    ]:
        s.add(Concept(concept_guid=guid, owner_id=1))
    s.flush()

    s.add_all(
        [
            Release(
                release_id=1,
                code="4.0",
                date=date(2024, 1, 1),
                status="Final",
                row_guid="c-rel-1",
                owner_id=1,
            ),
            Release(
                release_id=2,
                code="4.1",
                date=date(2024, 6, 1),
                status="Final",
                row_guid="c-rel-2",
                owner_id=1,
            ),
        ]
    )
    s.flush()

    # Hierarchy: ROOT_BS with two children.
    s.add(
        TableGroup(
            table_group_id=100,
            code="ROOT_BS",
            name="Balance Sheet — root",
            description="Top-level balance sheet group",
            type="navigation",
            owner_id=1,
            parent_table_group_id=None,
            start_release_id=1,
            end_release_id=None,
        )
    )
    s.flush()
    s.add_all(
        [
            TableGroup(
                table_group_id=200,
                code="BS_ASSETS",
                name="Balance Sheet — assets",
                type="navigation",
                owner_id=1,
                parent_table_group_id=100,
                start_release_id=1,
                end_release_id=None,
            ),
            TableGroup(
                table_group_id=201,
                code="BS_LIABS",
                name="Balance Sheet — liabilities",
                type="navigation",
                owner_id=1,
                parent_table_group_id=100,
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )
    s.flush()

    # Tables + TableVersions.
    s.add_all(
        [
            Table(
                table_id=1,
                is_abstract=False,
                has_open_columns=False,
                has_open_rows=False,
                has_open_sheets=False,
                is_normalised=False,
                is_flat=False,
                row_guid="c-tbl-1",
                owner_id=1,
            ),
            Table(
                table_id=2,
                is_abstract=False,
                has_open_columns=False,
                has_open_rows=False,
                has_open_sheets=False,
                is_normalised=False,
                is_flat=False,
                row_guid="c-tbl-2",
                owner_id=1,
            ),
        ]
    )
    s.flush()
    s.add_all(
        [
            TableVersion(
                table_vid=1000,
                code="F_01.01",
                name="Assets",
                table_id=1,
                start_release_id=1,
                end_release_id=None,
            ),
            TableVersion(
                table_vid=2000,
                code="F_02.00",
                name="Liabilities",
                table_id=2,
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )
    s.flush()

    # Compositions: ROOT_BS contains both tables but only at 4.0
    # (end_release_id=2 → gone at 4.1).
    s.add_all(
        [
            TableGroupComposition(
                table_group_id=100,
                table_id=1,
                order=1,
                start_release_id=1,
                end_release_id=2,
            ),
            TableGroupComposition(
                table_group_id=100,
                table_id=2,
                order=2,
                start_release_id=1,
                end_release_id=2,
            ),
            # Child groups carry their own tables across both releases.
            TableGroupComposition(
                table_group_id=200,
                table_id=1,
                order=1,
                start_release_id=1,
                end_release_id=None,
            ),
            TableGroupComposition(
                table_group_id=201,
                table_id=2,
                order=1,
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )
    s.commit()
    s.close()
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
    class _Counter:
        def __init__(self):
            self.count = 0

        def __enter__(self):
            def _l(c, cur, stmt, p, ctx, m):
                self.count += 1

            self._l = _l
            event.listen(engine, "before_cursor_execute", _l)
            return self

        def __exit__(self, *exc):
            event.remove(engine, "before_cursor_execute", self._l)
            return False

    return _Counter()


# ------------------------------------------------------------------ #
# Tests — default response
# ------------------------------------------------------------------ #


class TestDefaultResponse:
    def test_root_group_at_4_0(self, client):
        resp = client.get("/api/v1/structure/tablegroup/EBA/ROOT_BS/4.0")
        assert resp.status_code == 200
        body = resp.json()
        groups = body["data"]["tableGroups"]
        assert len(groups) == 1
        g = groups[0]
        assert g["code"] == "ROOT_BS"
        assert g["parentTableGroupId"] is None
        assert sorted(g["childTableGroupIds"]) == [200, 201]
        # No children expansion unless requested.
        assert "tables" not in g
        assert "childTableGroups" not in g

    def test_child_group_has_parent(self, client):
        resp = client.get("/api/v1/structure/tablegroup/EBA/BS_ASSETS/4.0")
        g = resp.json()["data"]["tableGroups"][0]
        assert g["parentTableGroupId"] == 100
        assert g["childTableGroupIds"] == []

    def test_wildcard_lists_all(self, client):
        resp = client.get("/api/v1/structure/tablegroup/EBA/*/4.0")
        codes = {g["code"] for g in resp.json()["data"]["tableGroups"]}
        assert codes == {"ROOT_BS", "BS_ASSETS", "BS_LIABS"}

    def test_nonexistent_code_204(self, client):
        resp = client.get("/api/v1/structure/tablegroup/EBA/NOPE/4.0")
        assert resp.status_code == 204


class TestChildrenExpansion:
    def test_root_at_4_0_has_tables_and_child_stubs(self, client):
        resp = client.get(
            "/api/v1/structure/tablegroup/EBA/ROOT_BS/4.0?references=children"
        )
        g = resp.json()["data"]["tableGroups"][0]
        # Tables in composition order.
        assert [t["code"] for t in g["tables"]] == ["F_01.01", "F_02.00"]
        # Tables carry the full table shape (headers/cells/variables).
        for t in g["tables"]:
            for key in ("headers", "cells", "keyVariables", "factVariables"):
                assert key in t
        # Child group stubs.
        child_codes = {c["code"] for c in g["childTableGroups"]}
        assert child_codes == {"BS_ASSETS", "BS_LIABS"}

    def test_root_at_4_1_loses_its_direct_tables(self, client):
        """ROOT_BS compositions end at release 4.1 → empty tables[],
        but the child group stubs (still alive) remain.
        """
        resp = client.get(
            "/api/v1/structure/tablegroup/EBA/ROOT_BS/4.1?references=children"
        )
        g = resp.json()["data"]["tableGroups"][0]
        assert g["tables"] == []
        child_codes = {c["code"] for c in g["childTableGroups"]}
        assert child_codes == {"BS_ASSETS", "BS_LIABS"}

    def test_child_group_with_no_subgroups(self, client):
        resp = client.get(
            "/api/v1/structure/tablegroup/EBA/BS_ASSETS/4.0?references=children"
        )
        g = resp.json()["data"]["tableGroups"][0]
        assert [t["code"] for t in g["tables"]] == ["F_01.01"]
        assert g["childTableGroups"] == []

    def test_references_all_includes_organisations(self, client):
        resp = client.get(
            "/api/v1/structure/tablegroup/EBA/ROOT_BS/4.0?references=all"
        )
        body = resp.json()
        assert "organisations" in body["data"]
        # Children also expanded.
        assert "tables" in body["data"]["tableGroups"][0]


class TestAllstubs:
    def test_strips_subtrees(self, client):
        resp = client.get(
            "/api/v1/structure/tablegroup/EBA/ROOT_BS/4.0?detail=allstubs"
        )
        g = resp.json()["data"]["tableGroups"][0]
        for key in (
            "tables",
            "childTableGroups",
            "childTableGroupIds",
            "parentTableGroupId",
            "description",
            "type",
        ):
            assert key not in g
        for key in ("id", "code", "name", "owner", "release"):
            assert key in g


class TestEmptyDatabase:
    def test_empty_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/tablegroup/EBA/ROOT_BS/4.0")
        assert resp.status_code == 204


# ------------------------------------------------------------------ #
# Performance — query budget
# ------------------------------------------------------------------ #


class TestQueryBudget:
    def test_default_path_minimal(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get("/api/v1/structure/tablegroup/EBA/*/4.0")
        assert resp.status_code == 200
        # Budget: 3 release resolution + tablegroup query +
        # child-id lookup + owner lookup ≈ 6–7. Cap at 10.
        assert counter.count <= 10, (
            f"default tablegroup path issued {counter.count} queries."
        )

    def test_children_path_bounded(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get(
                "/api/v1/structure/tablegroup/EBA/*/4.0?references=children"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]["tableGroups"]) == 3
        # Children path adds composition + TableVersion + the batch
        # table builder's headers/cells/variables/property/subcat
        # loads + child-group stubs. Bounded — typically ~17.
        assert counter.count <= 22, (
            f"children path issued {counter.count} queries — "
            f"likely an N+1 regression."
        )
