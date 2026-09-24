"""Tests for dpmcore.dpm_xl.utils.db_ast (dpmcore#364).

Builds a real in-memory SQLite database (schema from ``dpmcore.orm``,
same pattern as ``tests/unit/server/test_structure_operation.py``) and
seeds the handful of ``Operator``/``OperationNode``/``OperandReference``
rows each test needs, rather than mocking the ORM layer — this module
walks real relationships (``node.operator``, ``node.operator_argument``,
release-windowed lookups), which a mocked session would not exercise
faithfully.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401 -- ensure all models are registered
from dpmcore.dpm_xl.utils.db_ast import (
    UnsupportedDbAst,
    _infer_scalar,
    _normalize_date,
    build_ast_dict_from_db,
    build_ast_from_db,
    serialize_built_ast,
)
from dpmcore.orm.base import Base
from dpmcore.orm.glossary import ItemCategory, Property
from dpmcore.orm.infrastructure import DataType, Release
from dpmcore.orm.operations import (
    OperandReference,
    OperandReferenceLocation,
    OperationNode,
    Operator,
    OperatorArgument,
)
from dpmcore.orm.variables import VariableVersion

RELEASE_ID = 1
OPERATION_VID = 100


# ------------------------------------------------------------------ #
# Fixtures
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
def session(engine):
    s = Session(bind=engine)
    s.add(Release(release_id=RELEASE_ID, code="1.0", date=date(2024, 1, 1)))
    s.flush()
    yield s
    s.close()


# ------------------------------------------------------------------ #
# Seeding helpers
# ------------------------------------------------------------------ #


def _add_operator(
    session: Session,
    operator_id: int,
    *,
    name: str,
    type_: Optional[str],
    symbol: Optional[str] = None,
    arg_names: Optional[List[str]] = None,
) -> Dict[str, List[int]]:
    """Seed an ``Operator`` plus its ``OperatorArgument`` rows.

    Returns ``{argument_name: [argument_id, ...]}`` — a list per name so
    a variadic slot (the same argument name repeated, e.g.
    ``ComplexNumericOp``'s ``operand``) can seed more than one child.
    """
    session.add(
        Operator(operator_id=operator_id, name=name, type=type_, symbol=symbol)
    )
    session.flush()
    arg_ids: Dict[str, List[int]] = {}
    for i, arg_name in enumerate(arg_names or []):
        argument_id = operator_id * 1000 + i
        session.add(
            OperatorArgument(
                argument_id=argument_id,
                operator_id=operator_id,
                name=arg_name,
                order=i,
            )
        )
        arg_ids.setdefault(arg_name, []).append(argument_id)
    session.flush()
    return arg_ids


def _add_node(
    session: Session,
    node_id: int,
    *,
    parent_node_id: Optional[int] = None,
    operator_id: Optional[int] = None,
    argument_id: Optional[int] = None,
    is_leaf: bool = False,
    scalar: Optional[str] = None,
    fallback_value: Optional[str] = None,
    use_interval_arithmetics: Optional[bool] = None,
    operation_vid: int = OPERATION_VID,
) -> None:
    session.add(
        OperationNode(
            node_id=node_id,
            operation_vid=operation_vid,
            parent_node_id=parent_node_id,
            operator_id=operator_id,
            argument_id=argument_id,
            is_leaf=is_leaf,
            scalar=scalar,
            fallback_value=fallback_value,
            use_interval_arithmetics=use_interval_arithmetics,
        )
    )
    session.flush()


def _add_ref(
    session: Session,
    ref_id: int,
    *,
    node_id: int,
    kind: str,
    x: Optional[int] = None,
    y: Optional[int] = None,
    z: Optional[int] = None,
    item_id: Optional[int] = None,
    property_id: Optional[int] = None,
    variable_id: Optional[int] = None,
) -> None:
    session.add(
        OperandReference(
            operand_reference_id=ref_id,
            node_id=node_id,
            x=x,
            y=y,
            z=z,
            operand_reference=kind,
            item_id=item_id,
            property_id=property_id,
            variable_id=variable_id,
        )
    )
    session.flush()


def _add_location(
    session: Session,
    ref_id: int,
    *,
    table: Optional[str] = None,
    row: Optional[str] = None,
    column: Optional[str] = None,
    sheet: Optional[str] = None,
) -> None:
    session.add(
        OperandReferenceLocation(
            operand_reference_id=ref_id,
            table=table,
            row=row,
            column=column,
            sheet=sheet,
        )
    )
    session.flush()


def _add_item_category(
    session: Session,
    item_id: int,
    *,
    code: str,
    signature: Optional[str] = None,
) -> None:
    session.add(
        ItemCategory(
            item_id=item_id,
            code=code,
            signature=signature or code,
            start_release_id=RELEASE_ID,
            end_release_id=None,
        )
    )
    session.flush()


def _add_variable(
    session: Session,
    variable_id: int,
    *,
    code: Optional[str] = None,
) -> None:
    """Seed a ``DataType``/``Property``/``VariableVersion`` trio for
    *variable_id*, so ``_data_type_for_variable``/``_variable_code``
    can resolve it. Each variable gets its own ``DataType``/``Property``
    row (``code``/``name`` must be unique per row) rather than sharing
    one — simpler than threading a shared id through every test.
    """
    dt_id = 9000 + variable_id
    session.add(
        DataType(
            data_type_id=dt_id,
            code=f"DT{variable_id}",
            name=f"Type{variable_id}",
        )
    )
    session.add(Property(property_id=variable_id, data_type_id=dt_id))
    session.flush()
    session.add(
        VariableVersion(
            variable_vid=variable_id,
            variable_id=variable_id,
            property_id=variable_id,
            code=code,
            start_release_id=RELEASE_ID,
            end_release_id=None,
        )
    )
    session.flush()


def _build(session: Session):
    return build_ast_dict_from_db(session, OPERATION_VID, RELEASE_ID)


def _wrap_unary(session: Session, leaf_node_id: int) -> None:
    """Add a ``UnaryOp`` root (``op == "not"``) whose single ``operand``
    is *leaf_node_id* — the standard way these tests give an isolated
    leaf shape a valid root, since :func:`build_ast_dict_from_db`
    requires the root itself to carry an ``OperatorID``.
    """
    args = _add_operator(
        session,
        1,
        name="Not",
        type_="Unary",
        symbol="not",
        arg_names=["operand"],
    )
    _add_node(session, 1, operator_id=1, argument_id=None, is_leaf=False)
    # The leaf itself is re-parented under the wrapper; its argument_id
    # must point at the wrapper's single "operand" slot.
    node = session.get(OperationNode, leaf_node_id)
    node.parent_node_id = 1
    node.argument_id = args["operand"][0]
    session.flush()


# ------------------------------------------------------------------ #
# Pure helpers
# ------------------------------------------------------------------ #


class TestInferScalar:
    def test_boolean_true(self):
        assert _infer_scalar("true") == ("Boolean", True)

    def test_boolean_false(self):
        assert _infer_scalar("false") == ("Boolean", False)

    def test_integer(self):
        assert _infer_scalar("42") == ("Integer", 42)

    def test_negative_integer(self):
        assert _infer_scalar("-7") == ("Integer", -7)

    def test_number(self):
        assert _infer_scalar("3.14") == ("Number", 3.14)

    def test_date_iso(self):
        assert _infer_scalar("2024-01-15") == ("Date", "2024-01-15")

    def test_date_dmy(self):
        assert _infer_scalar("15/01/2024") == ("Date", "2024-01-15")

    def test_string_fallback(self):
        assert _infer_scalar("hello") == ("String", "hello")


class TestNormalizeDate:
    def test_iso_format(self):
        assert _normalize_date("2024-01-15") == "2024-01-15"

    def test_dmy_format(self):
        assert _normalize_date("15/01/2024") == "2024-01-15"

    def test_invalid_returns_none(self):
        assert _normalize_date("not-a-date") is None


# ------------------------------------------------------------------ #
# Operator classification
# ------------------------------------------------------------------ #


class TestClassifyOperators:
    """Exercises ``_classify_operators`` directly through
    :func:`build_ast_dict_from_db`'s own root-operator resolution, via
    the smallest possible tree: a single unary wrapper whose operator is
    the one being classified. ``UnaryOp`` itself (``name_set ==
    {"operand"}``) is exercised implicitly by every other test in this
    module (:func:`_wrap_unary`), so it is not repeated here.
    """

    def test_binop_classified_for_left_right_args(self, session):
        args = _add_operator(
            session,
            1,
            name="Equals",
            type_="Comparison",
            symbol="=",
            arg_names=["left", "right"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["left"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=args["right"][0],
            is_leaf=True,
            scalar="1",
        )

        ast_dict, root_operator_id = _build(session)
        assert root_operator_id == 1
        assert ast_dict["class_name"] == "BinOp"
        assert ast_dict["op"] == "="

    def test_assignment_type_excluded_from_binop(self, session):
        """A ``Type == "Assignment"`` operator with ``left``/``right``
        args (e.g. DPM's real ``Persistent assignment``, symbol
        ``<-``) must not be classified as a plain ``BinOp`` — it is
        left unclassified, so using one as a root raises.
        """
        args = _add_operator(
            session,
            1,
            name="Persistent assignment",
            type_="Assignment",
            symbol="<-",
            arg_names=["left", "right"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["left"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=args["right"][0],
            is_leaf=True,
            scalar="2",
        )

        with pytest.raises(UnsupportedDbAst):
            _build(session)

    def test_unclassified_operator_raises(self, session):
        """An operator matching none of the known shapes (e.g. a
        genuinely unsupported construct) must fail loudly, not silently
        produce a wrong tree.
        """
        _add_operator(
            session,
            1,
            name="Something Unheard Of",
            type_="Mystery",
            symbol="???",
            arg_names=["a", "b", "c"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)

        with pytest.raises(UnsupportedDbAst):
            _build(session)


# ------------------------------------------------------------------ #
# Leaves, via a UnaryOp wrapper
# ------------------------------------------------------------------ #


class TestLeaves:
    def test_constant_from_scalar_text(self, session):
        _add_node(session, 2, is_leaf=True, scalar="42")
        _wrap_unary(session, 2)

        ast_dict, _ = _build(session)
        assert ast_dict["operand"] == {
            "class_name": "Constant",
            "type_": "Integer",
            "value": 42,
        }

    def test_dimension_leaf(self, session):
        _add_item_category(session, 700, code="BASE")
        _add_node(session, 2, is_leaf=True)
        _add_ref(session, 1, node_id=2, kind="property", property_id=700)
        _wrap_unary(session, 2)

        ast_dict, _ = _build(session)
        assert ast_dict["operand"] == {
            "class_name": "Dimension",
            "dimension_code": "BASE",
        }

    def test_scalar_leaf(self, session):
        _add_item_category(session, 700, code="i1", signature="sig1")
        _add_node(session, 2, is_leaf=True)
        _add_ref(session, 1, node_id=2, kind="item", item_id=700)
        _wrap_unary(session, 2)

        ast_dict, _ = _build(session)
        assert ast_dict["operand"] == {
            "class_name": "Scalar",
            "item": "sig1",
            "scalar_type": "Item",
        }

    def test_set_leaf_with_multiple_items(self, session):
        _add_item_category(session, 700, code="i1", signature="sig1")
        _add_item_category(session, 701, code="i2", signature="sig2")
        _add_node(session, 2, is_leaf=True)
        _add_ref(session, 1, node_id=2, kind="item", item_id=700)
        _add_ref(session, 2000, node_id=2, kind="item", item_id=701)
        _wrap_unary(session, 2)

        ast_dict, _ = _build(session)
        assert ast_dict["operand"]["class_name"] == "Set"
        assert ast_dict["operand"]["children"] == [
            {"class_name": "Scalar", "item": "sig1", "scalar_type": "Item"},
            {"class_name": "Scalar", "item": "sig2", "scalar_type": "Item"},
        ]

    def test_precondition_item_with_resolvable_code(self, session):
        _add_variable(session, 700, code="v_flag")
        _add_node(session, 2, is_leaf=True)
        _add_ref(
            session,
            1,
            node_id=2,
            kind="PreconditionItem",
            variable_id=700,
        )
        _wrap_unary(session, 2)

        ast_dict, _ = _build(session)
        assert ast_dict["operand"] == {
            "class_name": "PreconditionItem",
            "variable_id": 700,
            "variable_code": "v_flag",
        }

    def test_var_ref_without_location(self, session):
        _add_variable(session, 700, code="v_ref_code")
        _add_node(session, 2, is_leaf=True)
        _add_ref(session, 1, node_id=2, kind="variable", variable_id=700)
        _wrap_unary(session, 2)

        ast_dict, _ = _build(session)
        assert ast_dict["operand"] == {
            "class_name": "VarRef",
            "variable": "v_ref_code",
        }

    def test_leaf_without_scalar_or_reference_raises(self, session):
        _add_node(session, 2, is_leaf=True)
        _wrap_unary(session, 2)

        with pytest.raises(UnsupportedDbAst):
            _build(session)


# ------------------------------------------------------------------ #
# VarID
# ------------------------------------------------------------------ #


class TestVarId:
    def test_single_cell(self, session):
        _add_variable(session, 700)
        _add_node(
            session,
            2,
            is_leaf=True,
            fallback_value="0",
            use_interval_arithmetics=True,
        )
        _add_ref(
            session,
            1,
            node_id=2,
            kind="variable",
            x=0,
            y=0,
            variable_id=700,
        )
        _add_location(session, 1, table="F_01.01", row="r0010", column="c0010")
        _wrap_unary(session, 2)

        ast_dict, _ = _build(session)
        var_id = ast_dict["operand"]
        assert var_id["class_name"] == "VarID"
        assert var_id["table"] == "F_01.01"
        assert var_id["row"] == "r0010"
        assert var_id["column"] == "c0010"
        assert var_id["default"] == 0
        assert var_id["interval"] is True
        assert len(var_id["data"]) == 1
        entry = var_id["data"][0]
        assert entry["datapoint"] == 700
        assert entry["operand_reference_id"] == 1
        assert entry["x"] == 0
        assert entry["row"] == "r0010"
        assert entry["y"] == 0
        assert entry["column"] == "c0010"

    def test_multi_cell_promotes_shared_row_only(self, session):
        """Two cells share the same row but differ in column: ``row`` is
        promoted to VarID level, ``column`` is not.
        """
        _add_variable(session, 700)
        _add_variable(session, 701)
        _add_node(session, 2, is_leaf=True, use_interval_arithmetics=False)
        _add_ref(
            session, 1, node_id=2, x=0, y=0, kind="variable", variable_id=700
        )
        _add_location(session, 1, table="F_01.01", row="r0010", column="c0010")
        _add_ref(
            session, 2, node_id=2, x=0, y=1, kind="variable", variable_id=701
        )
        _add_location(session, 2, table="F_01.01", row="r0010", column="c0020")
        _wrap_unary(session, 2)

        ast_dict, _ = _build(session)
        var_id = ast_dict["operand"]
        assert var_id["row"] == "r0010"
        assert "column" not in var_id
        assert len(var_id["data"]) == 2

    def test_table_present_even_when_none(self, session):
        _add_variable(session, 700)
        _add_node(session, 2, is_leaf=True, use_interval_arithmetics=False)
        _add_ref(session, 1, node_id=2, x=0, kind="variable", variable_id=700)
        _add_location(session, 1, table=None, row="r0010")
        _wrap_unary(session, 2)

        ast_dict, _ = _build(session)
        var_id = ast_dict["operand"]
        assert "table" in var_id
        assert var_id["table"] is None

    def test_conflicting_tables_raise(self, session):
        _add_variable(session, 700)
        _add_variable(session, 701)
        _add_node(session, 2, is_leaf=True, use_interval_arithmetics=False)
        _add_ref(session, 1, node_id=2, x=0, kind="variable", variable_id=700)
        _add_location(session, 1, table="F_01.01", row="r0010")
        _add_ref(session, 2, node_id=2, x=1, kind="variable", variable_id=701)
        _add_location(session, 2, table="F_02.01", row="r0020")
        _wrap_unary(session, 2)

        with pytest.raises(UnsupportedDbAst):
            _build(session)


# ------------------------------------------------------------------ #
# Composite operator shapes
# ------------------------------------------------------------------ #


class TestCompositeShapes:
    def test_par_expr(self, session):
        args = _add_operator(
            session,
            1,
            name="Parenthesis Expression",
            type_="Function",
            symbol="()",
            arg_names=["expression"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["expression"][0],
            is_leaf=True,
            scalar="1",
        )

        ast_dict, _ = _build(session)
        assert ast_dict == {
            "class_name": "ParExpr",
            "expression": {
                "class_name": "Constant",
                "type_": "Integer",
                "value": 1,
            },
        }

    def test_cond_expr_without_else(self, session):
        # The operator itself always declares all three argument slots
        # (classification requires the exact set {"condition", "then",
        # "else"}) — a *particular* If has no else branch by simply
        # having no child node under that slot, not by the operator
        # declaring fewer arguments.
        args = _add_operator(
            session,
            1,
            name="If",
            type_="Conditional",
            symbol="if",
            arg_names=["condition", "then", "else"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["condition"][0],
            is_leaf=True,
            scalar="true",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=args["then"][0],
            is_leaf=True,
            scalar="1",
        )

        ast_dict, _ = _build(session)
        assert ast_dict["class_name"] == "CondExpr"
        assert ast_dict["condition"] == {
            "class_name": "Constant",
            "type_": "Boolean",
            "value": True,
        }
        assert ast_dict["then_expr"] == {
            "class_name": "Constant",
            "type_": "Integer",
            "value": 1,
        }
        assert "else_expr" not in ast_dict

    def test_cond_expr_with_else(self, session):
        args = _add_operator(
            session,
            1,
            name="If",
            type_="Conditional",
            symbol="if",
            arg_names=["condition", "then", "else"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["condition"][0],
            is_leaf=True,
            scalar="false",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=args["then"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            4,
            parent_node_id=1,
            argument_id=args["else"][0],
            is_leaf=True,
            scalar="2",
        )

        ast_dict, _ = _build(session)
        assert ast_dict["else_expr"] == {
            "class_name": "Constant",
            "type_": "Integer",
            "value": 2,
        }

    def test_filter_op(self, session):
        args = _add_operator(
            session,
            1,
            name="Filter",
            type_="Function",
            symbol="filter",
            arg_names=["selection", "condition"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["selection"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=args["condition"][0],
            is_leaf=True,
            scalar="true",
        )

        ast_dict, _ = _build(session)
        assert ast_dict["class_name"] == "FilterOp"
        assert ast_dict["selection"]["value"] == 1
        assert ast_dict["condition"]["value"] is True

    def test_where_clause_op(self, session):
        args = _add_operator(
            session,
            1,
            name="Where",
            type_="Clause",
            symbol="where",
            arg_names=["operand", "condition"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["operand"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=args["condition"][0],
            is_leaf=True,
            scalar="true",
        )

        ast_dict, _ = _build(session)
        assert ast_dict["class_name"] == "WhereClauseOp"

    def test_sub_clause_op(self, session):
        args = _add_operator(
            session,
            1,
            name="Sub",
            type_="Clause",
            symbol="sub",
            arg_names=["operand", "condition"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["operand"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=args["condition"][0],
            is_leaf=True,
            scalar="true",
        )

        ast_dict, _ = _build(session)
        # _DbSubClauseOp's own visitor emits it under "SubClauseOp", the
        # same wire class the engine expects from a genuinely-parsed sub.
        assert ast_dict["class_name"] == "SubClauseOp"
        assert ast_dict["operand"]["value"] == 1
        assert ast_dict["condition"]["value"] is True

    def test_get_clause_op_with_property_component(self, session):
        _add_item_category(session, 700, code="BASE")
        args = _add_operator(
            session,
            1,
            name="Get",
            type_="Clause",
            symbol="get",
            arg_names=["operand", "component"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["operand"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=args["component"][0],
            is_leaf=True,
        )
        _add_ref(session, 1, node_id=3, kind="property", property_id=700)

        ast_dict, _ = _build(session)
        assert ast_dict == {
            "class_name": "GetClauseOp",
            "operand": {
                "class_name": "Constant",
                "type_": "Integer",
                "value": 1,
            },
            "component": "BASE",
        }

    def test_complex_numeric_op(self, session):
        args = _add_operator(
            session,
            1,
            name="Numeric maximum",
            type_="Function",
            symbol="max",
            arg_names=["operand", "operand", "operand"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        for i, node_id in enumerate([2, 3, 4]):
            _add_node(
                session,
                node_id,
                parent_node_id=1,
                argument_id=args["operand"][i],
                is_leaf=True,
                scalar=str(i + 1),
            )

        ast_dict, _ = _build(session)
        assert ast_dict["class_name"] == "ComplexNumericOp"
        assert ast_dict["op"] == "max"
        assert [o["value"] for o in ast_dict["operands"]] == [1, 2, 3]

    def test_aggregation_with_grouping_clause(self, session):
        _add_item_category(session, 700, code="BASE")
        agg_args = _add_operator(
            session,
            1,
            name="Sum",
            type_="Aggregate",
            symbol="sum",
            arg_names=["operand", "grouping_clause"],
        )
        # The grouping-clause operator itself: its own children are
        # never routed through _children_by_argument (_build_grouping_
        # clause reads them directly), so they need no argument_id.
        _add_operator(
            session, 2, name="Grouping clause", type_="Clause", arg_names=[]
        )

        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=agg_args["operand"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=agg_args["grouping_clause"][0],
            operator_id=2,
            is_leaf=False,
        )
        # Component leaves of the grouping clause: an "r" axis marker
        # and a property code, mirroring what GetClauseOp/renames use.
        _add_node(session, 4, parent_node_id=3, is_leaf=True)
        _add_ref(session, 1, node_id=4, kind="r")
        _add_node(session, 5, parent_node_id=3, is_leaf=True)
        _add_ref(session, 2, node_id=5, kind="property", property_id=700)

        ast_dict, _ = _build(session)
        assert ast_dict["class_name"] == "AggregationOp"
        assert ast_dict["op"] == "sum"
        assert ast_dict["analytic_clause"] is None
        assert ast_dict["grouping_clause"] == {
            "class_name": "GroupingClause",
            "components": ["r", "BASE"],
        }

    def test_rename_op(self, session):
        """Kept for future use (not yet exercised by real DPM data —
        confirmed no ``Rename``/``RenameNode`` OperationNode rows exist
        in the reference DB), but reachable and worth a regression test
        so it does not silently rot.
        """
        rename_args = _add_operator(
            session,
            1,
            name="Rename",
            type_="Function",
            symbol="rename",
            arg_names=["operand", "node"],
        )
        _add_operator(session, 2, name="RenameNode", type_="Function")

        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=rename_args["operand"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=rename_args["node"][0],
            operator_id=2,
            is_leaf=False,
        )
        rename_node_args = {"old_name": [3001], "new_name": [3002]}
        session.add_all(
            [
                OperatorArgument(
                    argument_id=3001, operator_id=2, name="old_name"
                ),
                OperatorArgument(
                    argument_id=3002, operator_id=2, name="new_name"
                ),
            ]
        )
        session.flush()
        _add_node(
            session,
            4,
            parent_node_id=3,
            argument_id=rename_node_args["old_name"][0],
            is_leaf=True,
            scalar="OLD",
        )
        _add_node(
            session,
            5,
            parent_node_id=3,
            argument_id=rename_node_args["new_name"][0],
            is_leaf=True,
            scalar="NEW",
        )

        ast_dict, _ = _build(session)
        assert ast_dict == {
            "class_name": "RenameClauseOp",
            "operand": {
                "class_name": "Constant",
                "type_": "Integer",
                "value": 1,
            },
            "clauses": [{"from_component": "OLD", "to_component": "NEW"}],
        }

    def test_time_shift_op_with_reference_period(self, session):
        args = _add_operator(
            session,
            1,
            name="Time shift",
            type_="Function",
            symbol="time_shift",
            arg_names=[
                "operand",
                "period_indicator",
                "shift_number",
                "dimension",
            ],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["operand"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=args["period_indicator"][0],
            is_leaf=True,
            scalar="A",
        )
        _add_node(
            session,
            4,
            parent_node_id=1,
            argument_id=args["shift_number"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            5,
            parent_node_id=1,
            argument_id=args["dimension"][0],
            is_leaf=True,
        )
        _add_ref(session, 1, node_id=5, kind="refPeriod")

        ast_dict, _ = _build(session)
        assert ast_dict == {
            "class_name": "TimeShiftOp",
            "operand": {
                "class_name": "Constant",
                "type_": "Integer",
                "value": 1,
            },
            "period_indicator": {
                "class_name": "Constant",
                "type_": "String",
                "value": "A",
            },
            "shift_number": {
                "class_name": "Constant",
                "type_": "Integer",
                "value": 1,
            },
            "reference_period": "refPeriod",
        }

    def test_time_shift_op_without_reference_period(self, session):
        """The trailing ``propertyCode`` argument is optional in the
        grammar — no ``dimension`` child at all must serialise to a
        bare ``None``, not raise.
        """
        args = _add_operator(
            session,
            1,
            name="Time shift",
            type_="Function",
            symbol="time_shift",
            arg_names=["operand", "period_indicator", "shift_number"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["operand"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=args["period_indicator"][0],
            is_leaf=True,
            scalar="Q",
        )
        _add_node(
            session,
            4,
            parent_node_id=1,
            argument_id=args["shift_number"][0],
            is_leaf=True,
            scalar="2",
        )

        ast_dict, _ = _build(session)
        assert ast_dict["reference_period"] is None
        assert ast_dict["period_indicator"]["value"] == "Q"
        assert ast_dict["shift_number"]["value"] == 2

    def test_time_shift_op_preserves_real_operand_reference_id(self, session):
        """Regression: the shifted operand is a real ``VarID`` built the
        same way as any other — its ``operand_reference_id`` must be
        the persisted ``OperandReferenceID``, not a re-parse artifact.
        """
        args = _add_operator(
            session,
            1,
            name="Time shift",
            type_="Function",
            symbol="time_shift",
            arg_names=["operand", "period_indicator", "shift_number"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_variable(session, 700)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["operand"][0],
            is_leaf=True,
        )
        _add_ref(session, 42, node_id=2, kind="variable", x=0, variable_id=700)
        _add_location(session, 42, table="F_01.01", row="r0010")
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=args["period_indicator"][0],
            is_leaf=True,
            scalar="A",
        )
        _add_node(
            session,
            4,
            parent_node_id=1,
            argument_id=args["shift_number"][0],
            is_leaf=True,
            scalar="1",
        )

        ast_dict, _ = _build(session)
        operand = ast_dict["operand"]
        assert operand["class_name"] == "VarID"
        assert operand["data"][0]["operand_reference_id"] == 42

    def test_time_shift_op_missing_period_indicator_scalar_raises(
        self, session
    ):
        args = _add_operator(
            session,
            1,
            name="Time shift",
            type_="Function",
            symbol="time_shift",
            arg_names=["operand", "period_indicator", "shift_number"],
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(
            session,
            2,
            parent_node_id=1,
            argument_id=args["operand"][0],
            is_leaf=True,
            scalar="1",
        )
        _add_node(
            session,
            3,
            parent_node_id=1,
            argument_id=args["period_indicator"][0],
            is_leaf=True,
        )
        _add_node(
            session,
            4,
            parent_node_id=1,
            argument_id=args["shift_number"][0],
            is_leaf=True,
            scalar="1",
        )

        with pytest.raises(UnsupportedDbAst, match="period_indicator"):
            _build(session)


# ------------------------------------------------------------------ #
# build_ast_from_db / serialize_built_ast (dpmcore#364 follow-up)
# ------------------------------------------------------------------ #


class TestBuildAstFromDb:
    """``build_ast_dict_from_db`` is a thin ``build_ast_from_db`` +
    ``serialize_built_ast`` wrapper — callers that also need the raw
    tree (``ASTGeneratorService._extract_time_shifts``) use the split
    directly instead of re-deriving it from the serialised dict.
    """

    def test_returns_the_real_ast_node_not_a_dict(self, session):
        _add_node(session, 2, is_leaf=True, scalar="1")
        _wrap_unary(session, 2)

        built, root_operator_id = build_ast_from_db(
            session, OPERATION_VID, RELEASE_ID
        )

        assert not isinstance(built, dict)
        assert built.__class__.__name__ == "UnaryOp"
        assert root_operator_id == 1

    def test_serialize_built_ast_matches_build_ast_dict_from_db(self, session):
        _add_node(session, 2, is_leaf=True, scalar="1")
        _wrap_unary(session, 2)

        built, root_operator_id = build_ast_from_db(
            session, OPERATION_VID, RELEASE_ID
        )
        ast_dict_from_split = serialize_built_ast(built)
        ast_dict_from_wrapper, wrapper_root_id = build_ast_dict_from_db(
            session, OPERATION_VID, RELEASE_ID
        )

        assert ast_dict_from_split == ast_dict_from_wrapper
        assert root_operator_id == wrapper_root_id


# ------------------------------------------------------------------ #
# Tree-level errors
# ------------------------------------------------------------------ #


class TestTreeErrors:
    def test_no_nodes_for_operation_vid_raises(self, session):
        with pytest.raises(UnsupportedDbAst):
            _build(session)

    def test_multiple_roots_raises(self, session):
        _add_operator(
            session, 1, name="Not", type_="Unary", arg_names=["operand"]
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        _add_node(session, 2, operator_id=1, is_leaf=False)

        with pytest.raises(UnsupportedDbAst):
            _build(session)

    def test_root_without_operator_id_raises(self, session):
        _add_node(session, 1, is_leaf=False)

        with pytest.raises(UnsupportedDbAst):
            _build(session)

    def test_child_without_argument_raises(self, session):
        _add_operator(
            session, 1, name="Not", type_="Unary", arg_names=["operand"]
        )
        _add_node(session, 1, operator_id=1, is_leaf=False)
        # Child has no argument_id at all -> operator_argument is None.
        _add_node(session, 2, parent_node_id=1, is_leaf=True, scalar="1")

        with pytest.raises(UnsupportedDbAst):
            _build(session)
