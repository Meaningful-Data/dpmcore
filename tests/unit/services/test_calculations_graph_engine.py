"""Unit tests for the engine/DB-backed calculations graph (in-memory DB)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import dpmcore.orm  # noqa: F401 — register all ORM mappers
import dpmcore.services.calculations_graph.engine as eng
from dpmcore.errors import Invalid
from dpmcore.orm.base import Base
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.operations import (
    OperandReference,
    OperandReferenceLocation,
    Operation,
    OperationNode,
    OperationScope,
    OperationScopeComposition,
    OperationVersion,
    Operator,
    OperatorArgument,
)
from dpmcore.orm.packaging import ModuleVersion
from dpmcore.services.calculations_graph import CalculationsGraphService

# Release ids: 100 -> "4.0", 101 -> "4.2".
_R40, _R42 = 100, 101


def _node(node_id, vid, parent, operator_id=None, argument_id=None):
    return OperationNode(
        node_id=node_id,
        operation_vid=vid,
        parent_node_id=parent,
        operator_id=operator_id,
        argument_id=argument_id,
        is_leaf=argument_id is not None and operator_id is None,
    )


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = Session(engine)

    rows = [
        Release(release_id=_R40, code="4.0"),
        Release(release_id=_R42, code="4.2"),
        # Operators: 1 = equals, 2 = >= (no output), 3 = + (inner).
        Operator(operator_id=1, name="Equal", symbol="="),
        Operator(operator_id=2, name="GE", symbol=">="),
        Operator(operator_id=3, name="Add", symbol="+"),
        OperatorArgument(argument_id=10, operator_id=1, order=1, name="left"),
        OperatorArgument(argument_id=11, operator_id=1, order=2, name="right"),
        # Operations (code lives on Operation).
        Operation(operation_id=1, code="calcA"),
        Operation(operation_id=2, code="calcB"),
        Operation(operation_id=3, code="calcC"),
        Operation(operation_id=4, code="calcD"),
        Operation(operation_id=5, code="calcE"),
        Operation(operation_id=6, code="calcF"),
        Operation(operation_id=9, code="calcMod"),
        # Versions.
        OperationVersion(
            operation_vid=1,
            operation_id=1,
            start_release_id=_R42,
            expression="A",
        ),
        OperationVersion(
            operation_vid=2,
            operation_id=2,
            start_release_id=_R42,
            expression="B",
        ),
        OperationVersion(
            operation_vid=3,
            operation_id=3,
            start_release_id=_R42,
            expression="C",
        ),
        OperationVersion(
            operation_vid=4,
            operation_id=4,
            start_release_id=_R42,
            expression="D",
        ),
        OperationVersion(
            operation_vid=5,
            operation_id=5,
            start_release_id=_R40,
            end_release_id=_R40,
            expression="E-old",
        ),
        OperationVersion(
            operation_vid=6,
            operation_id=5,
            start_release_id=_R42,
            expression="E-new",
        ),
        OperationVersion(
            operation_vid=7,
            operation_id=6,
            start_release_id=_R42,
            expression="F",
        ),
        OperationVersion(
            operation_vid=11,
            operation_id=9,
            start_release_id=_R42,
            expression="Mod",
        ),
        # A: out 1000, in 2000.
        _node(1, 1, None, operator_id=1),
        _node(2, 1, 1, argument_id=10),
        _node(3, 1, 1, argument_id=11),
        # B: out 2000, in 3000.
        _node(4, 2, None, operator_id=1),
        _node(5, 2, 4, argument_id=10),
        _node(6, 2, 4, argument_id=11),
        # C: >= (non-equality) over 1000, 4000 -> all inputs.
        _node(7, 3, None, operator_id=2),
        _node(8, 3, 7, argument_id=10),
        _node(9, 3, 7, argument_id=11),
        # D: out 5000, in 5000 (self).
        _node(10, 4, None, operator_id=1),
        _node(11, 4, 10, argument_id=10),
        _node(12, 4, 10, argument_id=11),
        # F: out 8000 = (right '+' subtree of 2000, 8001) -> nested.
        _node(13, 7, None, operator_id=1),
        _node(14, 7, 13, argument_id=10),
        _node(15, 7, 13, operator_id=3, argument_id=11),
        _node(16, 7, 15, argument_id=10),
        _node(17, 7, 15, argument_id=11),
        # E-new: out 6000, in 7000.
        _node(18, 6, None, operator_id=1),
        _node(19, 6, 18, argument_id=10),
        _node(20, 6, 18, argument_id=11),
        # E-old: out 9000, in 9001 (dropped by dedup).
        _node(21, 5, None, operator_id=1),
        _node(22, 5, 21, argument_id=10),
        _node(23, 5, 21, argument_id=11),
        # Mod: out 8200, in 8000 (F's output).
        _node(24, 11, None, operator_id=1),
        _node(25, 11, 24, argument_id=10),
        _node(26, 11, 24, argument_id=11),
        # Operand references (leaf node -> variable).
        OperandReference(operand_reference_id=1, node_id=2, variable_id=1000),
        OperandReference(operand_reference_id=2, node_id=3, variable_id=2000),
        OperandReference(operand_reference_id=3, node_id=5, variable_id=2000),
        OperandReference(operand_reference_id=4, node_id=6, variable_id=3000),
        OperandReference(operand_reference_id=5, node_id=8, variable_id=1000),
        OperandReference(operand_reference_id=6, node_id=9, variable_id=4000),
        OperandReference(operand_reference_id=7, node_id=11, variable_id=5000),
        OperandReference(operand_reference_id=8, node_id=12, variable_id=5000),
        OperandReference(operand_reference_id=9, node_id=14, variable_id=8000),
        OperandReference(
            operand_reference_id=10, node_id=16, variable_id=2000
        ),
        OperandReference(
            operand_reference_id=11, node_id=17, variable_id=8001
        ),
        OperandReference(
            operand_reference_id=12, node_id=19, variable_id=6000
        ),
        OperandReference(
            operand_reference_id=13, node_id=20, variable_id=7000
        ),
        OperandReference(
            operand_reference_id=14, node_id=22, variable_id=9000
        ),
        OperandReference(
            operand_reference_id=15, node_id=23, variable_id=9001
        ),
        OperandReference(
            operand_reference_id=16, node_id=25, variable_id=8200
        ),
        OperandReference(
            operand_reference_id=17, node_id=26, variable_id=8000
        ),
        # Locations only on A and C's var-1000 operands -> table filter.
        OperandReferenceLocation(operand_reference_id=1, table="TBL_A"),
        OperandReferenceLocation(operand_reference_id=5, table="TBL_A"),
        # Module MOD1 contains calcMod (vid 11).
        ModuleVersion(module_vid=500, code="MOD1"),
        OperationScope(operation_scope_id=900, operation_vid=11),
        OperationScopeComposition(operation_scope_id=900, module_vid=500),
    ]
    sess.add_all(rows)
    sess.commit()
    yield sess
    sess.close()
    engine.dispose()


# --------------------------------------------------------------------------- #
# Full path via the service
# --------------------------------------------------------------------------- #


def test_no_filter_graph(session):
    result = CalculationsGraphService().generate_from_database(session)
    codes = {n.code for n in result.nodes}
    assert codes == {
        "calcA",
        "calcB",
        "calcC",
        "calcD",
        "calcE",
        "calcF",
        "calcMod",
    }
    edges = {(e.source, e.target) for e in result.edges}
    assert ("calcB", "calcA") in edges  # implicit, shared var 2000
    assert ("calcA", "calcC") in edges  # non-equality consumer
    assert ("calcB", "calcF") in edges  # nested '+' subtree input
    assert ("calcF", "calcMod") in edges
    assert ("calcD", "calcD") not in edges  # self-edge skipped
    roots = {n.code for n in result.nodes if n.is_root}
    assert roots == {"calcB", "calcD", "calcE"}
    # dedup keeps the latest (4.2) version of calcE.
    e_node = next(n for n in result.nodes if n.code == "calcE")
    assert e_node.expression == "E-new"
    assert "cytoscape" in result.html


def test_module_filter(session):
    result = CalculationsGraphService().generate_from_database(
        session, module_code="MOD1"
    )
    assert {n.code for n in result.nodes} == {"calcMod"}
    assert result.edges == ()


def test_table_filter(session):
    result = CalculationsGraphService().generate_from_database(
        session, table_code="TBL_A"
    )
    assert {n.code for n in result.nodes} == {"calcA", "calcC"}
    assert {(e.source, e.target) for e in result.edges} == {("calcA", "calcC")}


def test_release_filter_old(session):
    result = CalculationsGraphService().generate_from_database(
        session, release_code="4.0"
    )
    # Only the 4.0-window operation (calcE-old) is active.
    assert {n.code for n in result.nodes} == {"calcE"}
    e_node = result.nodes[0]
    assert e_node.expression == "E-old"


def test_empty_result_warns(session):
    result = CalculationsGraphService().generate_from_database(
        session, module_code="NOPE"
    )
    assert result.nodes == ()
    assert any("No operations matched" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# Direct helper coverage
# --------------------------------------------------------------------------- #


def test_operation_cells_empty(session):
    assert eng.operation_cells(session, []) == {}


def test_filter_by_release_bad_code(session):
    with pytest.raises(Invalid):
        eng._filter_by_release(session, [], "not-a-version")


def test_filter_by_release_windows(session):
    rows = [
        (1, "a", "e", _R42, None),  # start 4.2, open end
        (2, "b", "e", _R40, _R40),  # start 4.0, end 4.0
        (3, "c", "e", 999, None),  # unknown start release -> excluded
    ]
    at_42 = eng._filter_by_release(session, rows, "4.2")
    assert {r[0] for r in at_42} == {1}  # row2 end<4.2, row3 unknown
    at_40 = eng._filter_by_release(session, rows, "4.0")
    assert {r[0] for r in at_40} == {2}  # row1 start>4.0, row3 unknown


def test_dedupe_latest(session):
    rows = [
        (1, "x", "x-old", _R40, None),
        (2, "x", "x-new", _R42, None),  # replaces (newer)
        (3, "y", "y-new", _R42, None),
        (4, "y", "y-old", _R40, None),  # kept: not newer than vid 3
        (5, None, "skip", _R42, None),  # empty code skipped
        (6, "z", "z", 777, None),  # unknown release -> rank -1
    ]
    result = eng._dedupe_latest(session, rows)
    assert result == {
        2: ("x", "x-new"),
        3: ("y", "y-new"),
        6: ("z", "z"),
    }


def test_root_child():
    parent = {1: None, 2: 1, 3: 2, 4: 1}
    assert eng._root_child(1, parent) == 1  # the root itself
    assert eng._root_child(4, parent) == 4  # direct child of root
    assert eng._root_child(3, parent) == 2  # nested -> walks up to root child


@pytest.mark.parametrize(
    ("module_code", "table_code", "release_code", "expected"),
    [
        (None, None, None, "Execution graph — all operations"),
        ("M", None, None, "Execution graph — module M"),
        (None, "T", None, "Execution graph — table T"),
        (None, None, "4.2", "Execution graph — release 4.2"),
        ("M", "T", "4.2", "Execution graph — module M, table T, release 4.2"),
    ],
)
def test_default_title(module_code, table_code, release_code, expected):
    assert eng.default_title(module_code, table_code, release_code) == expected
