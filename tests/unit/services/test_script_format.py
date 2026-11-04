"""Unit tests for the shared Script Format 2.0 helpers."""

import pytest

from dpmcore.services.script_format import (
    FORMAT_VERSION,
    UnsupportedNode,
    script_ast,
    script_file_name,
)


class TestFormatVersion:
    def test_is_two_zero(self):
        assert FORMAT_VERSION == "2.0"


class TestScriptFileName:
    def test_owner_module_and_version(self):
        assert (
            script_file_name("ECB", "FINREP9", "3.3.0")
            == "ECB-FINREP9-3.3.0.json"
        )

    @pytest.mark.parametrize(
        ("owner", "code", "version"),
        [("", "FINREP9", "3.3.0"), ("ECB", "", "3.3.0"), ("ECB", "X", "")],
    )
    def test_rejects_a_blank_part(self, owner, code, version):
        with pytest.raises(ValueError, match="file name"):
            script_file_name(owner, code, version)


def _fact(**extra):
    node = {
        "class_name": "VarID",
        "table": "C_01.00",
        "interval": False,
        "data": [
            {
                "datapoint": 1,
                "operand_reference_id": 10,
                "x": 1,
                "row": "0010",
                "column": "0010",
                "data_type": "m",
            },
            {
                "datapoint": 2,
                "operand_reference_id": 11,
                "x": 2,
                "row": "0020",
                "column": "0010",
                "data_type": "m",
            },
        ],
        "column": "0010",
    }
    node.update(extra)
    return node


class TestScriptAstFactVarID:
    def test_renames_the_class(self):
        assert script_ast(_fact())["class_name"] == "FactVarID"

    def test_drops_the_cell_position_of_the_node(self):
        node = script_ast(_fact(row="0010", sheet="0001"))
        assert not {"row", "column", "sheet"} & set(node)

    def test_drops_the_cell_position_of_each_entry(self):
        data = script_ast(_fact())["data"]
        assert data == [
            {
                "datapoint": 1,
                "operand_reference_id": 10,
                "x": 1,
                "data_type": "m",
            },
            {
                "datapoint": 2,
                "operand_reference_id": 11,
                "x": 2,
                "data_type": "m",
            },
        ]

    def test_keeps_the_other_members(self):
        node = script_ast(_fact(default=0))
        assert (node["table"], node["interval"], node["default"]) == (
            "C_01.00",
            False,
            0,
        )

    def test_reaches_nested_operands(self):
        tree = {
            "class_name": "BinOp",
            "op": "=",
            "left": _fact(),
            "right": _fact(),
        }
        out = script_ast(tree)
        assert (
            out["left"]["class_name"]
            == out["right"]["class_name"]
            == ("FactVarID")
        )

    def test_leaves_its_input_untouched(self):
        node = _fact()
        script_ast(node)
        assert node["class_name"] == "VarID"
        assert "row" in node["data"][0]


class TestScriptAstFilingIndicator:
    def test_precondition_item_becomes_filing_indicator_var_id(self):
        node = {
            "class_name": "PreconditionItem",
            "variable_id": 7,
            "variable_code": "F_01.01",
        }
        assert script_ast(node) == {
            "class_name": "FilingIndicatorVarID",
            "code": "F_01.01",
            "variable_id": 7,
        }

    def test_rejects_an_item_without_its_code(self):
        node = {"class_name": "PreconditionItem", "variable_id": 7}
        with pytest.raises(UnsupportedNode, match="filing indicator 7"):
            script_ast(node)


class TestScriptAstOtherNodes:
    def test_date_parts_are_named_with_a_node_suffix(self):
        year = {"class_name": "Constant", "type_": "Integer", "value": 2024}
        node = {
            "class_name": "DateConstructorOp",
            "op": "date",
            "year": year,
            "month": year,
            "day": year,
        }
        assert script_ast(node) == {
            "class_name": "DateConstructorOp",
            "op": "date",
            "year_node": year,
            "month_node": year,
            "day_node": year,
        }

    def test_scalar_drops_member(self):
        node = {
            "class_name": "Scalar",
            "item": "eba_GA:x1",
            "scalar_type": "Item",
            "member": "x1",
        }
        assert script_ast(node) == {
            "class_name": "Scalar",
            "item": "eba_GA:x1",
            "scalar_type": "Item",
        }

    def test_a_window_without_period_is_kept(self):
        window = {
            "frame_type": "data_points",
            "start": {"bound_type": "n_preceding", "n": 2},
            "end": {"bound_type": "current_data_point"},
        }
        node = {
            "class_name": "AnalyticClause",
            "partition_by": [],
            "order_by": [{"key_name": "f", "direction": "asc"}],
            "window": window,
        }
        assert script_ast(node)["window"] == window

    def test_a_window_bound_period_becomes_period_indicator(self):
        node = {
            "class_name": "AnalyticClause",
            "partition_by": [],
            "order_by": [{"key_name": "refPeriod", "direction": "asc"}],
            "window": {
                "frame_type": "range",
                "start": {"bound_type": "n_preceding", "n": 4, "period": "Q"},
                "end": {"bound_type": "n_preceding", "n": 1, "period": "Q"},
            },
        }
        assert script_ast(node)["window"] == {
            "frame_type": "range",
            "start": {
                "bound_type": "n_preceding",
                "n": 4,
                "period_indicator": "Q",
            },
            "end": {
                "bound_type": "n_preceding",
                "n": 1,
                "period_indicator": "Q",
            },
        }

    @pytest.mark.parametrize("class_name", ["VarRef", "Function"])
    def test_rejects_a_class_outside_the_format(self, class_name):
        node = {
            "class_name": "UnaryOp",
            "op": "not",
            "operand": {"class_name": class_name},
        }
        with pytest.raises(UnsupportedNode, match=class_name):
            script_ast(node)
