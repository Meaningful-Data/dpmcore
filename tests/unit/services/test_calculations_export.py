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

import dpmcore.services.calculations_export.exporter as exporter_mod
from dpmcore.dpm_xl.ast.nodes import Constant, VarID
from dpmcore.errors import Invalid
from dpmcore.services.calculations_export.exporter import (
    CalculationsExporter,
    _build_datapoint_mapping,
    _build_expression,
    _merge_version_windows,
    _narrow_candidate_tables,
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
        from dpmcore.errors import Invalid

        exporter = CalculationsExporter.__new__(CalculationsExporter)
        exporter._syntax = SyntaxService()

        calculations = [_calc("x := 1; y := 2", "c1")]
        with pytest.raises(Invalid, match="do not pair"):
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

        with pytest.raises(Invalid, match="cycle"):
            DAGAnalyzer().create_dag(ast)

    def test_assigning_the_same_output_twice_is_reported(self):
        ast = _parse(
            f"{_CELL_A} <- 1;\n{_CELL_A} <- 2;\n{_CELL_B} <- {_CELL_A} + 1;"
        )

        with pytest.raises(Invalid, match="assigned by more than one"):
            DAGAnalyzer().create_dag(ast)

    def test_a_duplicate_output_is_reported_without_any_edge(self):
        """The check is about the statements, not about their order.

        Two independent calculations writing the same cell produce no
        dependency edge, so nothing needs reordering -- the conflict
        still has to be reported.
        """
        ast = _parse(f"{_CELL_A} <- 1;\n{_CELL_A} <- 2;")

        with pytest.raises(Invalid, match="assigned by more than one"):
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
        from dpmcore.errors import Invalid

        ast = _parse(
            "x := time_shift({tA, r0010, c0010}, Q, 1 + 1, refPeriod);"
        )

        with pytest.raises(Invalid, match="not a literal"):
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

    def test_a_grey_cell_is_left_out_of_the_data(self):
        """A grey cell has no variable, so it has no datapoint to report.

        ``get_table_data`` sorts the frame with ``na_position="last"``,
        so a NaN ``variable_id`` is an expected part of it -- and the
        id it stands in for cannot be reported, nor passed to ``int()``.
        """
        frame = self._frame(
            [
                {
                    "table_code": "A",
                    "row_code": "0010",
                    "row_order": 1,
                    "column_code": "0010",
                    "column_order": 1,
                    "sheet_code": None,
                    "sheet_order": None,
                    "variable_id": 1,
                    "cell_id": 1,
                    "data_type": "m",
                    "cell_code": "{A, r0010, c0010}",
                },
                {
                    "table_code": "A",
                    "row_code": "0020",
                    "row_order": 2,
                    "column_code": "0010",
                    "column_order": 1,
                    "sheet_code": None,
                    "sheet_order": None,
                    "variable_id": None,
                    "cell_id": 2,
                    "data_type": "m",
                    "cell_code": "{A, r0020, c0010}",
                },
            ]
        )
        ast = _parse("x := {tA, r*, c0010};")

        enricher = VarIDDataEnricher(frame)
        enricher.visit(ast)

        payload = next(iter(enricher.payloads.values()))
        assert [entry["datapoint"] for entry in payload["data"]] == [1]

    def test_x_follows_the_display_order_not_the_code_text(self):
        """Ranking a row axis by code text is the pre-#209 behaviour.

        This table displays 0100 between 0010 and 0020, so the exported
        x coordinates must be 1, 2, 3 in *display* order -- which is a
        different answer from sorting the codes as strings.
        """
        frame = self._frame(
            [
                {
                    "table_code": "A",
                    "row_code": code,
                    "row_order": order,
                    "column_code": "0010",
                    "column_order": 1,
                    "sheet_code": None,
                    "sheet_order": None,
                    "variable_id": variable_id,
                    "cell_id": variable_id,
                    "data_type": "m",
                    "cell_code": f"{{A, r{code}, c0010}}",
                }
                for code, order, variable_id in (
                    ("0010", 1, 1),
                    ("0100", 2, 2),
                    ("0020", 3, 3),
                )
            ]
        )
        ast = _parse("x := {tA, r*, c0010};")

        enricher = VarIDDataEnricher(frame)
        enricher.visit(ast)

        payload = next(iter(enricher.payloads.values()))
        assert [(entry["x"], entry["row"]) for entry in payload["data"]] == [
            (1, "0010"),
            (2, "0100"),
            (3, "0020"),
        ]


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


class TestDependencyTableExtractorPeriods:
    """Exercise the ``ref_period`` tracking a ``TimeShiftOp`` needs."""

    @staticmethod
    def _extractor(monkeypatch, variable_ids=(1,)):
        from dpmcore.services.calculations_export.visitors import (
            DependencyTableExtractor,
        )

        extractor = DependencyTableExtractor(session=None)
        monkeypatch.setattr(
            extractor,
            "_variable_ids",
            lambda table, node: list(variable_ids),
        )
        monkeypatch.setattr(extractor, "_get_open_keys", lambda table: {})
        return extractor

    def test_plain_reference_is_recorded_as_t(self, monkeypatch):
        extractor = self._extractor(monkeypatch)

        extractor.visit(_parse("x := {tA, r0010, c0010};"))

        assert extractor.periods == {"A": {"T"}}

    def test_a_shifted_reference_is_recorded_by_its_period(self, monkeypatch):
        extractor = self._extractor(monkeypatch)

        extractor.visit(
            _parse("x := time_shift({tA, r0010, c0010}, A, 1, refPeriod);")
        )

        assert extractor.periods == {"A": {"T-1A"}}

    def test_a_forward_shift_flips_to_a_plus_period(self, monkeypatch):
        """``time_shift(x, Q, -1, refPeriod)`` needs ``T+1Q``."""
        extractor = self._extractor(monkeypatch)

        extractor.visit(
            _parse("x := time_shift({tA, r0010, c0010}, Q, -1, refPeriod);")
        )

        assert extractor.periods == {"A": {"T+1Q"}}

    def test_same_table_plain_and_shifted_keeps_both_periods(
        self, monkeypatch
    ):
        """One table read at two instances needs both periods (#326)."""
        extractor = self._extractor(monkeypatch)

        extractor.visit(
            _parse(
                "x := {tA, r0010, c0010} + "
                "time_shift({tA, r0020, c0010}, Q, 1, refPeriod);"
            )
        )

        assert extractor.periods == {"A": {"T", "T-1Q"}}

    def test_ambient_period_is_restored_after_the_shift(self, monkeypatch):
        extractor = self._extractor(monkeypatch)

        extractor.visit(
            _parse(
                "x := time_shift({tA, r0010, c0010}, A, 1, refPeriod) + "
                "{tB, r0010, c0010};"
            )
        )

        assert extractor.periods == {"A": {"T-1A"}, "B": {"T"}}

    def test_a_non_literal_shift_is_rejected(self, monkeypatch):
        extractor = self._extractor(monkeypatch)

        with pytest.raises(Invalid, match="not a literal"):
            extractor.visit(
                _parse(
                    "x := time_shift({tA, r0010, c0010}, Q, 1 + 1, refPeriod);"
                )
            )


class TestNarrowCandidateTables:
    """Exercise ``_narrow_candidate_tables``."""

    def test_groups_by_the_candidate_s_own_table(self):
        """Table name is not part of the identity test."""
        candidate_tables = {
            "C_14.00_renamed": {
                "variables": {"1": "m", "2": "m"},
                "open_keys": {"qSIC": "c"},
            }
        }

        result = _narrow_candidate_tables(candidate_tables, {"1": "m"})

        assert result == {
            "C_14.00_renamed": {
                "variables": {"1": "m"},
                "open_keys": {"qSIC": "c"},
            }
        }

    def test_a_table_with_no_matching_variable_is_dropped(self):
        candidate_tables = {
            "A": {"variables": {"9": "m"}, "open_keys": {}},
        }

        assert _narrow_candidate_tables(candidate_tables, {"1": "m"}) == {}


class TestMergeVersionWindows:
    """Exercise ``_merge_version_windows`` (multiple ref_periods)."""

    def test_a_single_entry_passes_through(self):
        entry = {
            "URI": "http://uri/old",
            "module_version": "1.0.0",
            "from_reference_date": "2025-03-31",
            "to_reference_date": "2026-03-30",
            "tables": {"A": {"variables": {"1": "m"}, "open_keys": {}}},
        }

        assert _merge_version_windows([entry]) == [entry]

    def test_same_candidate_from_two_periods_unions_dates_and_tables(self):
        older_shift = {
            "URI": "http://uri/old",
            "module_version": "1.0.0",
            "from_reference_date": "2023-03-31",
            "to_reference_date": "2026-03-30",
            "tables": {"A": {"variables": {"1": "m"}, "open_keys": {}}},
        }
        nearer_shift = {
            "URI": "http://uri/old",
            "module_version": "1.0.0",
            "from_reference_date": "2025-03-31",
            "to_reference_date": "2026-03-30",
            "tables": {"A": {"variables": {"2": "m"}, "open_keys": {}}},
        }

        merged = _merge_version_windows([nearer_shift, older_shift])

        assert merged == [
            {
                "URI": "http://uri/old",
                "module_version": "1.0.0",
                "from_reference_date": "2023-03-31",
                "to_reference_date": "2026-03-30",
                "tables": {
                    "A": {"variables": {"1": "m", "2": "m"}, "open_keys": {}}
                },
            }
        ]

    def test_an_open_ended_to_date_wins_over_a_concrete_one(self):
        bounded = {
            "URI": "http://uri/old",
            "from_reference_date": "2025-03-31",
            "to_reference_date": "2026-03-30",
            "tables": {},
        }
        open_ended = {
            "URI": "http://uri/old",
            "from_reference_date": "2025-03-31",
            "to_reference_date": None,
            "tables": {},
        }

        merged = _merge_version_windows([bounded, open_ended])

        assert merged[0]["to_reference_date"] is None

    def test_different_candidates_are_kept_apart(self):
        first = {
            "URI": "http://uri/a",
            "from_reference_date": "2025-03-31",
            "to_reference_date": "2026-03-30",
            "tables": {},
        }
        second = {
            "URI": "http://uri/b",
            "from_reference_date": "2024-03-31",
            "to_reference_date": "2025-03-30",
            "tables": {},
        }

        assert _merge_version_windows([first, second]) == [first, second]


class _FakeScopeCalc:
    """Stand-in for ``ScopeCalculatorService._find_version_window_candidate``.

    ``candidate_by_period`` maps a ``ref_period`` to the candidate dict
    it resolves to (``URI``, ``module_version``, ``tables``,
    ``from_reference_date``, ``to_reference_date``), or leaves it out
    for "no candidate found".
    """

    def __init__(self, candidate_by_period):
        self.candidate_by_period = candidate_by_period
        self.calls = []
        self.current_tables_by_call = []

    def _find_version_window_candidate(
        self,
        module_id,
        d0,
        ref_period,
        window_to,
        current_tables,
        current_variables,
        current_uri=None,
    ):
        self.calls.append(ref_period)
        self.current_tables_by_call.append(current_tables)
        return self.candidate_by_period.get(ref_period)


class TestResolveDependencyVersionWindows:
    """Exercise ``CalculationsExporter._resolve_dependency_version_windows``."""

    @staticmethod
    def _dep_info(tables):
        from datetime import date

        return {
            "tables": tables,
            "from_date": date(2026, 3, 31),
            "to_date": None,
            "module_id": 7,
        }

    def test_one_period_resolves_a_window_with_narrowed_tables(self):
        from datetime import date

        candidate_tables = {
            "A_old": {"variables": {"1": "m", "9": "m"}, "open_keys": {}}
        }
        fake = _FakeScopeCalc(
            {
                "T-1A": {
                    "URI": "http://uri/old",
                    "module_version": "1.0.0",
                    "tables": candidate_tables,
                    "from_reference_date": date(2025, 3, 31),
                    "to_reference_date": date(2026, 3, 30),
                }
            }
        )
        exporter = CalculationsExporter.__new__(CalculationsExporter)
        exporter._scope_calc = fake
        dep_info = self._dep_info(
            {"A": {"variables": {"1": "m"}, "open_keys": {}}}
        )

        result = exporter._resolve_dependency_version_windows(
            dep_info,
            {"A": {"T-1A"}},
            release_id=1,
            current_uri="http://uri/current",
        )

        assert result == [
            {
                "URI": "http://uri/old",
                "module_version": "1.0.0",
                "from_reference_date": "2025-03-31",
                "to_reference_date": "2026-03-30",
                "tables": {
                    "A_old": {"variables": {"1": "m"}, "open_keys": {}}
                },
            }
        ]
        assert fake.calls == ["T-1A"]

    def test_a_period_with_no_candidate_contributes_nothing(self):
        fake = _FakeScopeCalc({})
        exporter = CalculationsExporter.__new__(CalculationsExporter)
        exporter._scope_calc = fake
        dep_info = self._dep_info(
            {"A": {"variables": {"1": "m"}, "open_keys": {}}}
        )

        result = exporter._resolve_dependency_version_windows(
            dep_info,
            {"A": {"T-1A"}},
            release_id=1,
            current_uri="http://uri/current",
        )

        assert result == []

    def test_two_periods_on_the_same_candidate_are_merged(self):
        from datetime import date

        candidate_tables = {
            "A_old": {"variables": {"1": "m"}, "open_keys": {}}
        }
        fake = _FakeScopeCalc(
            {
                "T-1A": {
                    "URI": "http://uri/old",
                    "module_version": "1.0.0",
                    "tables": candidate_tables,
                    "from_reference_date": date(2025, 3, 31),
                    "to_reference_date": date(2026, 3, 30),
                },
                "T-2A": {
                    "URI": "http://uri/old",
                    "module_version": "1.0.0",
                    "tables": candidate_tables,
                    "from_reference_date": date(2024, 3, 31),
                    "to_reference_date": date(2026, 3, 30),
                },
            }
        )
        exporter = CalculationsExporter.__new__(CalculationsExporter)
        exporter._scope_calc = fake
        dep_info = self._dep_info(
            {"A": {"variables": {"1": "m"}, "open_keys": {}}}
        )

        result = exporter._resolve_dependency_version_windows(
            dep_info,
            {"A": {"T-1A", "T-2A"}},
            release_id=1,
            current_uri="http://uri/current",
        )

        assert len(result) == 1
        assert result[0]["from_reference_date"] == "2024-03-31"
        assert fake.calls == ["T-1A", "T-2A"]

    def test_a_table_read_at_a_different_period_does_not_contaminate(self):
        """A table read at a different period must not reach this check."""
        from datetime import date

        dep_info = self._dep_info(
            {
                "A": {"variables": {"1": "m"}, "open_keys": {}},
                "B": {"variables": {"2": "m"}, "open_keys": {"SIC": "c"}},
            }
        )
        fake = _FakeScopeCalc(
            {
                "T-1A": {
                    "URI": "http://uri/old",
                    "module_version": "1.0.0",
                    "tables": {
                        "A_old": {"variables": {"1": "m"}, "open_keys": {}}
                    },
                    "from_reference_date": date(2025, 3, 31),
                    "to_reference_date": date(2026, 3, 30),
                }
                # No candidate for T-4Q: B's shift resolves nothing,
                # but must not prevent A's from resolving either.
            }
        )
        exporter = CalculationsExporter.__new__(CalculationsExporter)
        exporter._scope_calc = fake

        result = exporter._resolve_dependency_version_windows(
            dep_info,
            {"A": {"T-1A"}, "B": {"T-4Q"}},
            release_id=1,
            current_uri="http://uri/current",
        )

        assert fake.calls == ["T-1A", "T-4Q"]
        tables_seen_per_call = dict(
            zip(fake.calls, fake.current_tables_by_call, strict=True)
        )
        assert set(tables_seen_per_call["T-1A"]) == {"A"}
        assert set(tables_seen_per_call["T-4Q"]) == {"B"}
        assert result == [
            {
                "URI": "http://uri/old",
                "module_version": "1.0.0",
                "from_reference_date": "2025-03-31",
                "to_reference_date": "2026-03-30",
                "tables": {
                    "A_old": {"variables": {"1": "m"}, "open_keys": {}}
                },
            }
        ]


class TestDependencyModulesVersionWindows:
    """Exercise ``_dependency_modules``'s ``version_windows`` wiring."""

    @staticmethod
    def _extractor_stub(tables, periods):
        from types import SimpleNamespace

        return SimpleNamespace(
            tables=tables, all_datapoints=[], periods=periods
        )

    @staticmethod
    def _patch_queries(monkeypatch, dep_info):
        monkeypatch.setattr(exporter_mod, "get_data_types", lambda *a, **k: {})
        monkeypatch.setattr(
            exporter_mod,
            "group_tables_by_module",
            lambda *a, **k: {"DEP": dep_info},
        )
        monkeypatch.setattr(
            exporter_mod,
            "get_module_uri",
            lambda session, module_vid: ("http://uri/dep", "fw"),
        )

    def test_a_dependency_read_only_at_t_has_no_version_windows_key(
        self, monkeypatch
    ):
        from datetime import date

        dep_info = {
            "module_vid": 20,
            "module_id": 2,
            "from_date": date(2026, 3, 31),
            "to_date": None,
            "tables": {"A": {"variables": {"1": "m"}, "open_keys": {}}},
        }
        self._patch_queries(monkeypatch, dep_info)

        exporter = CalculationsExporter.__new__(CalculationsExporter)
        exporter.session = None
        dependencies = self._extractor_stub(
            tables={"A": {"variables": {1}, "open_keys": {}}},
            periods={"A": {"T"}},
        )

        result = exporter._dependency_modules("HOME", dependencies, 1)

        assert set(result["http://uri/dep"]) == {"tables"}

    def test_a_cross_time_dependency_gets_version_windows(self, monkeypatch):
        from datetime import date

        dep_info = {
            "module_vid": 20,
            "module_id": 2,
            "from_date": date(2026, 3, 31),
            "to_date": None,
            "tables": {"A": {"variables": {"1": "m"}, "open_keys": {}}},
        }
        self._patch_queries(monkeypatch, dep_info)

        exporter = CalculationsExporter.__new__(CalculationsExporter)
        exporter.session = None
        exporter._scope_calc = _FakeScopeCalc(
            {
                "T-1A": {
                    "URI": "http://uri/dep-old",
                    "module_version": "1.0.0",
                    "tables": {
                        "A": {"variables": {"1": "m"}, "open_keys": {}}
                    },
                    "from_reference_date": date(2025, 3, 31),
                    "to_reference_date": date(2026, 3, 30),
                }
            }
        )
        dependencies = self._extractor_stub(
            tables={"A": {"variables": {1}, "open_keys": {}}},
            periods={"A": {"T-1A"}},
        )

        result = exporter._dependency_modules("HOME", dependencies, 1)

        assert result["http://uri/dep"]["version_windows"] == [
            {
                "URI": "http://uri/dep-old",
                "module_version": "1.0.0",
                "from_reference_date": "2025-03-31",
                "to_reference_date": "2026-03-30",
                "tables": {"A": {"variables": {"1": "m"}, "open_keys": {}}},
            }
        ]
