"""Unit tests for the calculations export's DB-free pieces.

The script assembly, the dependency sort, the with-unwrapping walk, the
datapoint mapping and the serializer overrides all work on a parsed AST
alone, so they are exercised here without a dictionary. The parts that
need one are covered by
``tests/integration/services/test_calculations_export.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from dpmcore.dpm_xl.ast.nodes import Constant, VarID
from dpmcore.services.calculations_export.exporter import (
    CalculationsExporter,
    _build_datapoint_mapping,
    _build_expression,
)
from dpmcore.services.calculations_export.visitors import (
    CalculationsJSONVisitor,
    DAGAnalyzer,
    VarIDDataEnricher,
    _constant_value,
    _sole_code,
    unwrap_with_expressions,
)
from dpmcore.services.syntax import SyntaxService


def _parse(script):
    return SyntaxService().parse(script)


def _calc(expression, code=None):
    return {"expression": expression, "operation_code": code}


class TestBuildExpression:
    def test_terminates_every_statement(self):
        script = _build_expression(
            [_calc("x := 1"), _calc("y := 2")],
        )

        assert script == "x := 1;\ny := 2;"

    def test_keeps_an_existing_terminator(self):
        assert _build_expression([_calc("x := 1;")]) == "x := 1;"

    def test_trailing_whitespace_does_not_swallow_the_next_statement(self):
        """A terminator followed by spaces still ends the statement."""
        script = _build_expression([_calc("x := 1;  "), _calc("y := 2")])

        assert _parse(script).children.__len__() == 2

    def test_an_embedded_semicolon_still_gets_a_terminator(self):
        """A ``;`` inside the expression is not a statement terminator."""
        script = _build_expression(
            [_calc('x := "a;b"'), _calc("y := 2")],
        )

        assert script == 'x := "a;b";\ny := 2;'
        assert len(_parse(script).children) == 2


class TestOperationCodePairing:
    def test_pairs_one_code_per_statement(self):
        exporter = CalculationsExporter.__new__(CalculationsExporter)
        exporter._syntax = SyntaxService()

        calculations = [_calc("x := 1", "c1"), _calc("y := 2", "c2")]
        ast, codes = exporter._parse(
            _build_expression(calculations), calculations
        )

        assert codes == ["c1", "c2"]
        assert len(ast.children) == 2

    def test_a_multi_statement_expression_is_rejected(self):
        """Positional pairing cannot attribute two statements to one code."""
        from dpmcore.errors import InternalError

        exporter = CalculationsExporter.__new__(CalculationsExporter)
        exporter._syntax = SyntaxService()

        calculations = [_calc("x := 1; y := 2", "c1")]
        with pytest.raises(InternalError, match="do not pair"):
            exporter._parse(_build_expression(calculations), calculations)


_CELL_A = "{tA, r0010, c0010}"
_CELL_B = "{tA, r0020, c0010}"
_CELL_C = "{tB, r0010, c0010}"


class TestDAGAnalyzer:
    def test_a_producer_is_moved_before_its_consumer(self):
        ast = _parse(
            f"{_CELL_A} <- {_CELL_B} * 2;\n{_CELL_B} <- {_CELL_C} + 1;"
        )

        DAGAnalyzer().create_dag(ast)

        assert [child.left.rows[0] for child in ast.children] == [
            "0020",
            "0010",
        ]

    def test_independent_calculations_keep_their_order(self):
        ast = _parse(f"{_CELL_A} <- 1;\n{_CELL_B} <- 2;")

        DAGAnalyzer().create_dag(ast)

        assert [child.left.rows[0] for child in ast.children] == [
            "0010",
            "0020",
        ]

    def test_a_cycle_is_reported(self):
        ast = _parse(
            f"{_CELL_A} <- {_CELL_B} + 1;\n{_CELL_B} <- {_CELL_A} + 1;"
        )

        with pytest.raises(ValueError, match="Cyclic dependency"):
            DAGAnalyzer().create_dag(ast)

    def test_assigning_the_same_output_twice_is_reported(self):
        # The third statement consumes the cell, so the DAG has edges
        # and the overwrite check runs.
        ast = _parse(
            f"{_CELL_A} <- 1;\n{_CELL_A} <- 2;\n{_CELL_B} <- {_CELL_A} + 1;"
        )

        with pytest.raises(ValueError, match="assigned more than once"):
            DAGAnalyzer().create_dag(ast)

    def test_a_statement_that_assigns_nothing_is_kept(self):
        """Reordering must never drop a statement it cannot constrain."""
        ast = _parse(
            f"{_CELL_A} <- 1;\n"
            f"{_CELL_B} <- {_CELL_A} + 1;\n"
            f"{_CELL_C} = {_CELL_A};"
        )

        DAGAnalyzer().create_dag(ast)

        assert len(ast.children) == 3

    def test_a_cell_is_keyed_by_its_selection(self):
        ast = _parse("{tA, r0010, c0010} <- {tA, r0020, c0010};")

        analyzer = DAGAnalyzer()
        analyzer.visit(ast)

        assert analyzer.dependencies[1]["outputs"] == [
            "tA-['0010']-['0010']-None"
        ]


class TestUnwrapWithExpressions:
    def test_the_wrapper_is_replaced_by_its_expression(self):
        ast = _parse("with {tA, c0010}: {r0010} + 1;")

        unwrap_with_expressions(ast)

        assert type(ast.children[0]).__name__ == "BinOp"

    def test_a_nested_wrapper_chain_collapses(self):
        """Two wrappers in a row collapse to the innermost expression."""
        from dpmcore.dpm_xl.ast.nodes import WithExpression

        ast = _parse("{tA, r0010, c0010} <- {tB, r0010, c0010};")
        inner = ast.children[0].right
        context = VarID("B", None, ["0010"], None, None, None)
        ast.children[0].right = WithExpression(
            context, WithExpression(context, inner)
        )

        unwrap_with_expressions(ast)

        assert ast.children[0].right is inner

    def test_a_shared_subtree_is_walked_once(self):
        """The same node reachable twice must not re-trigger the walk."""
        ast = _parse("{tA, r0010, c0010} <- {tA, r0020, c0010};")
        shared = ast.children[0].right
        # Reachable from two parents, as the operand registry allows.
        ast.children.append(shared)

        unwrap_with_expressions(ast)

        assert ast.children[-1] is shared

    def test_a_back_reference_does_not_recurse_forever(self):
        ast = _parse("x := 1;")
        ast.children[0].parent = ast

        unwrap_with_expressions(ast)

        assert ast.children[0].parent is ast

    def test_non_ast_attributes_are_left_alone(self):
        """A frame attached to an operand is data, not a subtree to walk."""
        ast = _parse("{tA, r0010, c0010} <- {tA, r0020, c0010};")
        frame = pd.DataFrame({"variable_id": [1]})
        ast.children[0].right.data = frame

        unwrap_with_expressions(ast)

        assert ast.children[0].right.data is frame


class TestSerializer:
    def test_an_if_without_else_still_emits_else_expr(self):
        ast = _parse("x := if {tA, r0010, c0010} > 0 then 1 endif;")

        result = CalculationsJSONVisitor().visit(ast)

        cond = result["children"][0]["right"]
        assert cond["class_name"] == "CondExpr"
        assert cond["else_expr"] is None

    def test_an_aggregation_without_analytic_clause_omits_the_key(self):
        ast = _parse("x := sum({tA, r0010, c0010});")

        result = CalculationsJSONVisitor().visit(ast)

        agg = result["children"][0]["right"]
        assert agg["class_name"] == "AggregationOp"
        assert "analytic_clause" not in agg

    @pytest.mark.parametrize(
        ("written", "expected"),
        [("-1", "-1"), ("1", "1"), ("( -1 )", "-1"), ("(-1)", "-1")],
    )
    def test_a_time_shift_is_flat(self, written, expected):
        """Every literal shape of the same shift renders the same string."""
        ast = _parse(
            f"x := time_shift({{tA, r0010, c0010}}, Q, {written}, refPeriod);"
        )

        result = CalculationsJSONVisitor().visit(ast)

        shift = result["children"][0]["right"]
        assert shift["class_name"] == "TimeShiftOp"
        assert shift["period_indicator"] == "Q"
        assert shift["shift_number"] == expected
        assert shift["component"] == "refPeriod"

    def test_a_computed_shift_is_rejected(self):
        """The exported shape has nowhere to put an expression."""
        from dpmcore.errors import InternalError

        ast = _parse(
            "x := time_shift({tA, r0010, c0010}, Q, 1 + 1, refPeriod);"
        )

        with pytest.raises(InternalError, match="not a literal"):
            CalculationsJSONVisitor().visit(ast)

    def test_a_precomputed_operand_is_emitted_verbatim(self):
        ast = _parse("x := {tA, r0010, c0010};")
        operand = ast.children[0].right
        payload = {"class_name": "VarID", "table": "A", "data": []}

        result = CalculationsJSONVisitor({id(operand): payload}).visit(ast)

        assert result["children"][0]["right"] == payload

    def test_an_operand_with_no_payload_falls_back(self):
        ast = _parse("x := {tA, r0010, c0010};")

        result = CalculationsJSONVisitor().visit(ast)

        assert result["children"][0]["right"]["table"] == "A"


class TestVarIDDataEnricher:
    def _frame(self, rows):
        return pd.DataFrame(rows)

    def test_no_data_means_no_payload(self):
        ast = _parse("x := {tA, r0010, c0010};")

        enricher = VarIDDataEnricher(None)
        enricher.visit(ast)

        assert enricher.payloads == {}

    def test_an_all_null_axis_does_not_raise(self):
        """A table whose row codes are all null must not index an empty array."""
        frame = self._frame(
            [
                {
                    "table_code": "A",
                    "row_code": None,
                    "column_code": "0010",
                    "sheet_code": None,
                    "variable_id": 1,
                    "cell_id": 1,
                    "data_type": "m",
                    "cell_code": "{A, c0010}",
                }
            ]
        )
        ast = _parse("x := {tA, r*, c0010};")

        enricher = VarIDDataEnricher(frame)
        enricher.visit(ast)

        payload = next(iter(enricher.payloads.values()))
        assert "row" not in payload
        assert payload["column"] == "0010"


class TestHelpers:
    def test_sole_code_needs_exactly_one(self):
        assert _sole_code(["0010"]) == "0010"
        assert _sole_code([]) is None
        assert _sole_code(["0010", "0020"]) is None

    def test_constant_value_unwraps_by_type(self):
        assert _constant_value(Constant("Integer", "3")) == 3
        assert _constant_value(Constant("Integer", "3.0")) == 3
        assert _constant_value(Constant("Number", "1.5")) == 1.5
        assert _constant_value(Constant("String", "x")) == "x"

    def test_constant_value_passes_other_nodes_through(self):
        node = VarID("A", ["0010"], ["0010"], None, None, None)
        assert _constant_value(node) is node


class TestBuildDatapointMapping:
    def test_maps_one_entry_per_datapoint(self):
        frame = pd.DataFrame(
            [
                {
                    "variable_id": 7,
                    "table_code": "A",
                    "row_code": "0010",
                    "column_code": "0010",
                    "sheet_code": None,
                },
                {
                    "variable_id": 7,
                    "table_code": "A",
                    "row_code": "0010",
                    "column_code": "0010",
                    "sheet_code": None,
                },
            ]
        )

        assert _build_datapoint_mapping(frame) == {
            "7": {
                "table": "A",
                "row": "0010",
                "column": "0010",
                "sheet": None,
            }
        }

    def test_grey_cells_are_dropped(self):
        frame = pd.DataFrame(
            [
                {
                    "variable_id": None,
                    "table_code": "A",
                    "row_code": "0010",
                    "column_code": "0010",
                    "sheet_code": None,
                }
            ]
        )

        assert _build_datapoint_mapping(frame) == {}

    def test_no_data_means_no_mapping(self):
        assert _build_datapoint_mapping(None) == {}
        assert _build_datapoint_mapping(pd.DataFrame()) == {}


class TestUnresolvableOperands:
    def test_a_failed_selection_is_logged_not_raised(self, caplog):
        """One operand that cannot be filtered must not abort the export."""
        ast = _parse("x := {tA, r0010, c0010};")
        # A frame without the axis columns: filter_all_data raises.
        enricher = VarIDDataEnricher(pd.DataFrame({"variable_id": [1]}))

        with caplog.at_level("WARNING"):
            enricher.visit(ast)

        assert enricher.payloads == {}
        assert "Failed to filter data" in caplog.text

    def test_an_operand_without_a_table_is_skipped(self):
        """A with-context operand never reaches the database untouched."""
        from dpmcore.services.calculations_export.visitors import (
            DependencyTableExtractor,
        )

        extractor = DependencyTableExtractor(session=None)
        extractor.visit_VarID(VarID(None, ["0010"], None, None, None, None))

        assert extractor.tables == {}
        assert extractor.all_datapoints == []
