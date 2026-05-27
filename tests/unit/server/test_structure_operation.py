"""Integration tests for /api/v1/structure/operation endpoints."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
from dpmcore.orm.infrastructure import Concept, Organisation, Release
from dpmcore.orm.operations import (
    OperandReference,
    OperandReferenceLocation,
    Operation,
    OperationNode,
    OperationVersion,
    Operator,
)
from dpmcore.orm.rendering import Cell, Table
from dpmcore.server.app import create_app

# ------------------------------------------------------------------ #
# Seed model
# ------------------------------------------------------------------ #
#
# Two releases (4.0, 4.1). Two Operations:
#
#   - V_001 (id=1): two versions
#     - version A (vid=100, start=1, end=2)  → 4.0 only
#         · 2 nodes (root + child)
#         · child node has 1 OperandReference with 1 location
#     - version B (vid=101, start=2, end=None) → 4.1+
#         · 1 node, no references
#
#   - V_002 (id=2): one version at 4.0 only (vid=200, start=1, end=2)
#     → at 4.1 this operation should disappear from the result set.
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

    for guid in ["c-rel-1", "c-rel-2", "c-tbl-1", "c-cell-1"]:
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

    # A Table + Cell so OperandReferenceLocation has a real FK target.
    s.add(
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
        )
    )
    s.flush()
    s.add(Cell(cell_id=9001, table_id=1, row_guid="c-cell-1", owner_id=1))
    s.flush()

    # An Operator (root node references it).
    s.add(Operator(operator_id=1, name="Equals", symbol="=", type="comp"))
    s.flush()

    # Operations.
    s.add_all(
        [
            Operation(
                operation_id=1,
                code="V_001",
                type="validation",
                source="EBA",
                owner_id=1,
            ),
            Operation(
                operation_id=2,
                code="V_002",
                type="validation",
                source="EBA",
                owner_id=1,
            ),
        ]
    )
    s.flush()

    # V_001 versions.
    s.add_all(
        [
            OperationVersion(
                operation_vid=100,
                operation_id=1,
                expression="a = b",
                description="V_001 at 4.0",
                endorsement="adopted",
                is_variant_approved=True,
                start_release_id=1,
                end_release_id=2,
            ),
            OperationVersion(
                operation_vid=101,
                operation_id=1,
                expression="a == b",
                description="V_001 at 4.1",
                endorsement="adopted",
                is_variant_approved=True,
                start_release_id=2,
                end_release_id=None,
            ),
        ]
    )
    s.flush()

    # V_002 has only one version at 4.0 (gone at 4.1).
    s.add(
        OperationVersion(
            operation_vid=200,
            operation_id=2,
            expression="x > 0",
            description="V_002 at 4.0",
            endorsement="adopted",
            is_variant_approved=True,
            start_release_id=1,
            end_release_id=2,
        )
    )
    s.flush()

    # Nodes for V_001 version A (vid=100): root + child.
    s.add_all(
        [
            OperationNode(
                node_id=10,
                operation_vid=100,
                parent_node_id=None,
                operator_id=1,
                is_leaf=False,
                operand_type=None,
            ),
            OperationNode(
                node_id=11,
                operation_vid=100,
                parent_node_id=10,
                operator_id=None,
                is_leaf=True,
                operand_type="datapoint",
                scalar="42",
            ),
        ]
    )
    s.flush()
    # Node for V_001 version B (vid=101): single leaf.
    s.add(
        OperationNode(
            node_id=12,
            operation_vid=101,
            parent_node_id=None,
            is_leaf=True,
            operand_type="datapoint",
            scalar="0",
        )
    )
    s.flush()
    # Node for V_002 (vid=200).
    s.add(
        OperationNode(
            node_id=20,
            operation_vid=200,
            parent_node_id=None,
            is_leaf=True,
            scalar="x",
        )
    )
    s.flush()

    # OperandReference on V_001 version A child node (id=11).
    s.add(
        OperandReference(
            operand_reference_id=300,
            node_id=11,
            x=0,
            y=10,
            z=None,
            operand_reference="ref(F_01.01, r0010, c0010)",
        )
    )
    s.flush()

    # Location for that reference.
    s.add(
        OperandReferenceLocation(
            operand_reference_id=300,
            cell_id=9001,
            table="F_01.01",
            row="r0010",
            column="c0010",
            sheet=None,
        )
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
# Tests — single release
# ------------------------------------------------------------------ #


class TestSingleOperationAtRelease:
    def test_v001_at_4_0(self, client):
        resp = client.get("/api/v1/structure/operation/EBA/V_001/4.0")
        assert resp.status_code == 200
        ops = resp.json()["data"]["operations"]
        assert len(ops) == 1
        op = ops[0]
        assert op["code"] == "V_001"
        assert op["type"] == "validation"
        assert op["source"] == "EBA"
        # Only the version active at 4.0.
        assert [v["operationVersionId"] for v in op["versions"]] == [100]
        v = op["versions"][0]
        assert v["release"] == "4.0"
        assert v["expression"] == "a = b"

    def test_v001_at_4_1_returns_only_newer_version(self, client):
        resp = client.get("/api/v1/structure/operation/EBA/V_001/4.1")
        ops = resp.json()["data"]["operations"]
        v = ops[0]["versions"][0]
        assert v["operationVersionId"] == 101
        assert v["expression"] == "a == b"

    def test_v002_at_4_1_is_filtered_out(self, client):
        """V_002 only has a version at 4.0; at 4.1 the whole Operation
        is dropped from the result set.
        """
        resp = client.get("/api/v1/structure/operation/EBA/V_002/4.1")
        assert resp.status_code == 204

    def test_nonexistent_code_204(self, client):
        resp = client.get("/api/v1/structure/operation/EBA/V_999/4.0")
        assert resp.status_code == 204


class TestNestedPayload:
    def test_version_a_nodes_present(self, client):
        resp = client.get("/api/v1/structure/operation/EBA/V_001/4.0")
        v = resp.json()["data"]["operations"][0]["versions"][0]
        nodes = v["nodes"]
        # Two nodes — flat list with parent links.
        assert len(nodes) == 2
        root = next(n for n in nodes if n["parentNodeId"] is None)
        child = next(n for n in nodes if n["parentNodeId"] == root["nodeId"])
        assert root["operatorId"] == 1
        assert root["isLeaf"] is False
        assert child["isLeaf"] is True
        assert child["scalar"] == "42"

    def test_version_a_references_and_locations(self, client):
        resp = client.get("/api/v1/structure/operation/EBA/V_001/4.0")
        v = resp.json()["data"]["operations"][0]["versions"][0]
        child = next(n for n in v["nodes"] if n["isLeaf"])
        assert len(child["references"]) == 1
        ref = child["references"][0]
        assert ref["operandReferenceId"] == 300
        assert ref["operandReference"] == "ref(F_01.01, r0010, c0010)"
        assert ref["x"] == 0
        assert ref["y"] == 10
        # Location: pointed to cell 9001.
        assert len(ref["locations"]) == 1
        loc = ref["locations"][0]
        assert loc["cellId"] == 9001
        assert loc["table"] == "F_01.01"
        assert loc["row"] == "r0010"
        assert loc["column"] == "c0010"
        assert loc["sheet"] is None

    def test_node_without_references(self, client):
        """Root node of V_001/4.0 has no references; V_001/4.1's leaf
        also has none.
        """
        resp = client.get("/api/v1/structure/operation/EBA/V_001/4.1")
        v = resp.json()["data"]["operations"][0]["versions"][0]
        leaf = v["nodes"][0]
        assert leaf["references"] == []


class TestAllVersions:
    def test_release_wildcard_returns_both_v001_versions(self, client):
        resp = client.get("/api/v1/structure/operation/EBA/V_001/*")
        op = resp.json()["data"]["operations"][0]
        vids = sorted(v["operationVersionId"] for v in op["versions"])
        assert vids == [100, 101]

    def test_release_wildcard_returns_all_operations(self, client):
        resp = client.get("/api/v1/structure/operation/EBA/*/*")
        codes = {op["code"] for op in resp.json()["data"]["operations"]}
        assert codes == {"V_001", "V_002"}


class TestAllstubs:
    def test_strips_nested_tree(self, client):
        resp = client.get(
            "/api/v1/structure/operation/EBA/V_001/4.0?detail=allstubs"
        )
        op = resp.json()["data"]["operations"][0]
        for key in ("versions", "source", "groupOperationId"):
            assert key not in op
        assert op["operationVersionIds"] == [100]
        for key in ("id", "code", "type", "owner"):
            assert key in op


class TestReferences:
    def test_all_adds_organisations(self, client):
        resp = client.get(
            "/api/v1/structure/operation/EBA/V_001/4.0?references=all"
        )
        body = resp.json()
        assert "organisations" in body["data"]

    def test_children_noop_default_already_has_payload(self, client):
        """references=children doesn't change the default response —
        the nested tree is already there.
        """
        bare = client.get("/api/v1/structure/operation/EBA/V_001/4.0").json()[
            "data"
        ]["operations"][0]
        with_children = client.get(
            "/api/v1/structure/operation/EBA/V_001/4.0?references=children"
        ).json()["data"]["operations"][0]
        assert bare == with_children


class TestEmptyDatabase:
    def test_empty_returns_204(self, empty_client):
        resp = empty_client.get("/api/v1/structure/operation/EBA/V_001/4.0")
        assert resp.status_code == 204


# ------------------------------------------------------------------ #
# Performance — query budget
# ------------------------------------------------------------------ #


class TestQueryBudget:
    def test_full_payload_bounded(self, client, seeded_engine):
        with _count_queries(seeded_engine) as counter:
            resp = client.get("/api/v1/structure/operation/EBA/*/4.0")
        assert resp.status_code == 200
        body = resp.json()
        # 2 operations at 4.0 (V_001 and V_002).
        assert len(body["data"]["operations"]) == 2
        # Budget: release resolution (3) + EXISTS-aware count + main
        # paginated query + operations versions + nodes + references +
        # locations + owner lookup. ≤15 with headroom.
        assert counter.count <= 15, (
            f"operation path issued {counter.count} queries — "
            f"likely an N+1 regression."
        )
