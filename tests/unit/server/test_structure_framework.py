"""Integration tests for /api/v1/structure/framework endpoints."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
from dpmcore.orm.infrastructure import (
    Concept,
    Organisation,
    Release,
)
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleParameters,
    ModuleVersion,
)
from dpmcore.orm.variables import Variable, VariableVersion
from dpmcore.server.app import create_app

# ------------------------------------------------------------------ #
# Seed model
# ------------------------------------------------------------------ #
#
# Two frameworks (FINREP, COREP), each with two modules. FINREP modules
# have ModuleVersions at both releases 4.0 and 4.1; COREP modules only
# at 4.0. Used to exercise the release-filters-children semantics.
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
        "c-fw-finrep",
        "c-fw-corep",
        "c-mod-a",
        "c-mod-b",
        "c-mod-c",
        "c-mod-d",
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
    s.flush()

    s.add_all(
        [
            Framework(
                framework_id=10,
                code="FINREP",
                name="Financial Reporting",
                description="FINREP framework",
                row_guid="c-fw-finrep",
                owner_id=1,
            ),
            Framework(
                framework_id=20,
                code="COREP",
                name="Common Reporting",
                description="COREP framework",
                row_guid="c-fw-corep",
                owner_id=1,
            ),
        ]
    )
    s.flush()

    # FINREP modules: FINREP9, FINREP9_RST.
    s.add_all(
        [
            Module(
                module_id=100,
                framework_id=10,
                row_guid="c-mod-a",
                is_document_module=False,
                owner_id=1,
            ),
            Module(
                module_id=101,
                framework_id=10,
                row_guid="c-mod-b",
                is_document_module=False,
                owner_id=1,
            ),
            # COREP modules.
            Module(
                module_id=200,
                framework_id=20,
                row_guid="c-mod-c",
                is_document_module=False,
                owner_id=1,
            ),
            Module(
                module_id=201,
                framework_id=20,
                row_guid="c-mod-d",
                is_document_module=False,
                owner_id=1,
            ),
        ]
    )
    s.flush()

    s.add_all(
        [
            # FINREP9 — active at both releases.
            ModuleVersion(
                module_vid=10000,
                module_id=100,
                code="FINREP9",
                name="FINREP 9",
                version_number="9.0",
                start_release_id=1,
                end_release_id=None,
            ),
            ModuleVersion(
                module_vid=10001,
                module_id=101,
                code="FINREP9_RST",
                name="FINREP 9 — restricted",
                version_number="9.0",
                start_release_id=1,
                end_release_id=None,
            ),
            # COREP modules — only at release 4.0 (end_release_id=2 →
            # excluded from 4.1 by the date-based filter).
            ModuleVersion(
                module_vid=20000,
                module_id=200,
                code="COREP_OF",
                name="COREP Own Funds",
                version_number="3.0",
                start_release_id=1,
                end_release_id=2,
            ),
            ModuleVersion(
                module_vid=20001,
                module_id=201,
                code="COREP_LR",
                name="COREP Leverage",
                version_number="3.0",
                start_release_id=1,
                end_release_id=2,
            ),
        ]
    )
    s.flush()

    # Parameter variable on FINREP9.
    s.add(Variable(variable_id=89, type="k", owner_id=1))
    s.flush()
    s.add(
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
    s.flush()
    s.add(ModuleParameters(module_vid=10000, variable_vid=7777))
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
# Tests — default (no children)
# ------------------------------------------------------------------ #


class TestDefaultResponse:
    def test_single_framework_by_code(self, client):
        resp = client.get("/api/v1/structure/framework/EBA/FINREP/*")
        assert resp.status_code == 200
        body = resp.json()
        fws = body["data"]["frameworks"]
        assert len(fws) == 1
        fw = fws[0]
        assert fw["code"] == "FINREP"
        assert fw["name"] == "Financial Reporting"
        assert fw["owner"] == "EBA"
        # No children unless requested.
        assert "modules" not in fw

    def test_release_ignored_for_selection(self, client):
        """Frameworks aren't versioned — every release literal returns
        the same set, including unknown release codes.
        """
        for path in (
            "/api/v1/structure/framework/EBA/FINREP/4.0",
            "/api/v1/structure/framework/EBA/FINREP/4.1",
            "/api/v1/structure/framework/EBA/FINREP/999.0",
        ):
            resp = client.get(path)
            assert resp.status_code == 200
            assert resp.json()["data"]["frameworks"][0]["code"] == "FINREP"

    def test_wildcard_lists_all(self, client):
        resp = client.get("/api/v1/structure/framework/EBA/*/*")
        assert resp.status_code == 200
        codes = {f["code"] for f in resp.json()["data"]["frameworks"]}
        assert codes == {"FINREP", "COREP"}

    def test_unknown_code_204(self, client):
        resp = client.get("/api/v1/structure/framework/EBA/NOPE/*")
        assert resp.status_code == 204

    def test_unknown_owner_204(self, client):
        resp = client.get("/api/v1/structure/framework/UNKNOWN/FINREP/*")
        assert resp.status_code == 204


class TestAllstubs:
    def test_strips_subtrees(self, client):
        resp = client.get(
            "/api/v1/structure/framework/EBA/FINREP/*?detail=allstubs"
        )
        f = resp.json()["data"]["frameworks"][0]
        for key in ("description", "modules"):
            assert key not in f
        for key in ("id", "code", "name", "owner"):
            assert key in f


class TestEmptyDatabase:
    def test_empty_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/framework/EBA/FINREP/*")
        assert resp.status_code == 204


# ------------------------------------------------------------------ #
# Tests — children
# ------------------------------------------------------------------ #


class TestChildren:
    def test_children_at_4_0_returns_all_finrep_modules(self, client):
        resp = client.get(
            "/api/v1/structure/framework/EBA/FINREP/4.0?references=children"
        )
        f = resp.json()["data"]["frameworks"][0]
        assert "modules" in f
        codes = {m["code"] for m in f["modules"]}
        assert codes == {"FINREP9", "FINREP9_RST"}
        # Module shape mirrors /structure/module default — includes
        # framework ref, parameterVariableVersionIds, etc.
        finrep9 = next(m for m in f["modules"] if m["code"] == "FINREP9")
        assert finrep9["framework"]["code"] == "FINREP"
        assert finrep9["parameterVariableVersionIds"] == [7777]
        # No grandchildren (modules don't carry tables here).
        assert "tables" not in finrep9

    def test_release_filters_children_only(self, client):
        """COREP modules end at release 4.1 → no children at 4.1."""
        resp = client.get(
            "/api/v1/structure/framework/EBA/COREP/4.1?references=children"
        )
        f = resp.json()["data"]["frameworks"][0]
        # Framework still present.
        assert f["code"] == "COREP"
        # Children empty since both COREP modules ended at release 2.
        assert f["modules"] == []

    def test_unknown_release_yields_empty_children(self, client):
        """Unknown literal release → framework still returns, modules
        empty.
        """
        resp = client.get(
            "/api/v1/structure/framework/EBA/FINREP/999.0?references=children"
        )
        f = resp.json()["data"]["frameworks"][0]
        assert f["code"] == "FINREP"
        assert f["modules"] == []

    def test_release_wildcard_returns_all_module_versions(self, client):
        resp = client.get(
            "/api/v1/structure/framework/EBA/FINREP/*?references=children"
        )
        f = resp.json()["data"]["frameworks"][0]
        assert {m["code"] for m in f["modules"]} == {
            "FINREP9",
            "FINREP9_RST",
        }

    def test_references_all_includes_organisations(self, client):
        resp = client.get(
            "/api/v1/structure/framework/EBA/FINREP/4.0?references=all"
        )
        body = resp.json()
        assert "organisations" in body["data"]
        assert "modules" in body["data"]["frameworks"][0]


# ------------------------------------------------------------------ #
# Performance — query budget
# ------------------------------------------------------------------ #


class TestQueryBudget:
    def test_default_path_minimal_queries(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get("/api/v1/structure/framework/EBA/*/*")
        assert resp.status_code == 200
        # Framework query + one owner lookup ≈ 2–3 (no release work
        # since wants_all_releases=True).
        assert counter.count <= 5, (
            f"default framework path issued {counter.count} queries."
        )

    def test_children_path_bounded(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get(
                "/api/v1/structure/framework/EBA/*/4.0?references=children"
            )
        assert resp.status_code == 200
        body = resp.json()
        # 4 module versions across 2 frameworks at 4.0.
        total_modules = sum(
            len(f["modules"]) for f in body["data"]["frameworks"]
        )
        assert total_modules == 4
        # Budget breakdown:
        #   3 release-resolution queries (filter_by_release internals);
        #   1 framework query, 1 ModuleVersion children query,
        #   1 ModuleParameters bulk, 1 owner lookup.
        # ≤10 leaves headroom for incidental changes while still
        # flagging N+1 regressions.
        assert counter.count <= 10, (
            f"children path issued {counter.count} queries — "
            f"likely an N+1 regression."
        )
