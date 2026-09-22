"""Tests for dpmcore.services.script_fixups.

Ported from mdpm's ``mdm-fix-json-values.py``: known EBA source-data
errors that recur in every generated script for a fixed set of
validations.
"""

import copy

import pytest

from dpmcore.services.script_fixups import (
    fix_module_operations,
    fix_operation_ast,
)

pytestmark = pytest.mark.unit


def _varid(datapoint, default="__unset__", interval=None):
    node = {
        "class_name": "VarID",
        "data": [{"datapoint": datapoint}],
        "interval": interval,
    }
    if default != "__unset__":
        node["default"] = default
    return node


def _constant(type_, value):
    return {"class_name": "Constant", "type_": type_, "value": value}


def _binop(left, right):
    return {"class_name": "BinOp", "left": left, "right": right}


class TestUnknownOperation:
    def test_unrelated_op_code_is_untouched(self):
        ast = {"class_name": "VarID", "data": [{"datapoint": 1}]}
        before = copy.deepcopy(ast)
        changed = fix_operation_ast("v_not_in_any_registry", ast)
        assert changed is False
        assert ast == before


class TestWrongDefaults:
    def test_matching_default_is_removed(self):
        ast = _varid(55299, default="")
        changed = fix_operation_ast("v8713_m", ast)
        assert changed is True
        assert "default" not in ast

    def test_non_matching_datapoint_is_untouched(self):
        ast = _varid(999, default="")
        changed = fix_operation_ast("v8713_m", ast)
        assert changed is False
        assert ast["default"] == ""

    def test_already_correct_default_is_untouched(self):
        # The wrong-value guard means a VarID that never had the bad
        # default (no "default" key at all) reports no change.
        ast = _varid(55299)
        changed = fix_operation_ast("v8713_m", ast)
        assert changed is False
        assert "default" not in ast

    def test_nested_inside_binop_is_found(self):
        ast = _binop(_varid(55299, default=""), _constant("Boolean", True))
        changed = fix_operation_ast("v8713_m", ast)
        assert changed is True
        assert "default" not in ast["left"]

    def test_zero_wrong_value_matches_only_zero(self):
        ast = _varid(487511, default=0)
        changed = fix_operation_ast("v8803_m", ast)
        assert changed is True
        assert "default" not in ast

    def test_zero_wrong_value_does_not_match_empty_string(self):
        ast = _varid(487511, default="")
        changed = fix_operation_ast("v8803_m", ast)
        assert changed is False

    def test_match_inside_a_list_is_found(self):
        ast = {
            "class_name": "FunctionCall",
            "args": [_varid(55299, default="")],
        }
        changed = fix_operation_ast("v8713_m", ast)
        assert changed is True
        assert "default" not in ast["args"][0]


class TestConstantTrueFixes:
    def test_unconditional_flip(self):
        ast = _constant("Integer", 0)
        changed = fix_operation_ast("v7364_m", ast)
        assert changed is True
        assert ast == {"class_name": "Constant", "type_": "Boolean", "value": True}

    def test_predicate_gates_the_flip(self):
        # v8713_m's predicate only fires for an Integer-typed Constant.
        ast = _constant("String", "x")
        changed = fix_operation_ast("v8713_m", ast)
        assert changed is False
        assert ast["type_"] == "String"

    def test_predicate_matches_and_flips(self):
        ast = _constant("Integer", 0)
        changed = fix_operation_ast("v8713_m", ast)
        assert changed is True
        assert ast["type_"] == "Boolean"
        assert ast["value"] is True

    def test_already_boolean_true_reports_no_change(self):
        # value == 1 matches Python's True too (bool is an int
        # subtype) — must not report a spurious change.
        ast = _constant("Boolean", True)
        changed = fix_operation_ast("v10726_m", ast)
        assert changed is False
        assert ast == {"class_name": "Constant", "type_": "Boolean", "value": True}

    def test_value_one_gets_flipped_to_real_boolean(self):
        ast = _constant("Integer", 1)
        changed = fix_operation_ast("v10726_m", ast)
        assert changed is True
        assert ast["type_"] == "Boolean"
        assert ast["value"] is True

    def test_match_inside_a_list_is_found(self):
        ast = {"class_name": "FunctionCall", "args": [_constant("Integer", 0)]}
        changed = fix_operation_ast("v7364_m", ast)
        assert changed is True
        assert ast["args"][0]["value"] is True


class TestBinopSiblingFalseFixes:
    def test_right_constant_flipped_when_left_matches(self):
        ast = _binop(_varid(418132), _constant("Integer", 1))
        changed = fix_operation_ast("v6512_m", ast)
        assert changed is True
        assert ast["right"] == {
            "class_name": "Constant",
            "type_": "Boolean",
            "value": False,
        }

    def test_untouched_when_left_datapoint_does_not_match(self):
        ast = _binop(_varid(999), _constant("Integer", 1))
        changed = fix_operation_ast("v6512_m", ast)
        assert changed is False
        assert ast["right"] == {"class_name": "Constant", "type_": "Integer", "value": 1}

    def test_already_false_reports_no_change(self):
        ast = _binop(_varid(418132), _constant("Boolean", False))
        changed = fix_operation_ast("v6512_m", ast)
        assert changed is False

    def test_nested_binop_is_found(self):
        outer = _binop(
            _constant("Boolean", True),
            _binop(_varid(418133), _constant("Integer", 1)),
        )
        changed = fix_operation_ast("v6513_m", outer)
        assert changed is True
        assert outer["right"]["right"]["value"] is False


class TestForceIntervalFalse:
    def test_interval_true_is_forced_false(self):
        ast = _varid(1, interval=True)
        changed = fix_operation_ast("v7339_m", ast)
        assert changed is True
        assert ast["interval"] is False

    def test_already_false_reports_no_change(self):
        ast = _varid(1, interval=False)
        changed = fix_operation_ast("v7339_m", ast)
        assert changed is False

    def test_every_varid_in_tree_is_forced(self):
        ast = _binop(_varid(1, interval=True), _varid(2, interval=True))
        changed = fix_operation_ast("v7339_m", ast)
        assert changed is True
        assert ast["left"]["interval"] is False
        assert ast["right"]["interval"] is False

    def test_match_inside_a_list_is_found(self):
        ast = {"class_name": "FunctionCall", "args": [_varid(1, interval=True)]}
        changed = fix_operation_ast("v7339_m", ast)
        assert changed is True
        assert ast["args"][0]["interval"] is False


class TestCondExprChain:
    def _cond_expr(self, then_value, else_node):
        return {
            "class_name": "CondExpr",
            "then_expr": {"expression": _constant("Integer", then_value)},
            "else_expr": else_node,
        }

    def test_then_expr_flipped_true(self):
        ast = self._cond_expr(
            0, {"expression": _constant("Boolean", False)}
        )
        changed = fix_operation_ast("v6519_c", ast)
        assert changed is True
        assert ast["then_expr"]["expression"]["value"] is True

    def test_final_else_expr_flipped_false(self):
        ast = self._cond_expr(
            1, {"expression": _constant("Integer", 1)}
        )
        changed = fix_operation_ast("v6519_c", ast)
        assert changed is True
        assert ast["else_expr"]["expression"]["value"] is False

    def test_nested_else_expr_chain_recurses(self):
        inner = self._cond_expr(
            0, {"expression": _constant("Boolean", False)}
        )
        outer = {
            "class_name": "CondExpr",
            "then_expr": {"expression": _constant("Integer", 0)},
            "else_expr": inner,
        }
        changed = fix_operation_ast("v6519_c", outer)
        assert changed is True
        assert outer["then_expr"]["expression"]["value"] is True
        assert inner["then_expr"]["expression"]["value"] is True

    def test_already_correct_chain_reports_no_change(self):
        ast = self._cond_expr(
            1, {"expression": _constant("Boolean", False)}
        )
        ast["then_expr"]["expression"]["type_"] = "Boolean"
        ast["then_expr"]["expression"]["value"] = True
        changed = fix_operation_ast("v6519_c", ast)
        assert changed is False

    def test_condexpr_inside_a_list_is_found(self):
        inner = self._cond_expr(
            0, {"expression": _constant("Boolean", False)}
        )
        ast = [inner]
        changed = fix_operation_ast("v6519_c", ast)
        assert changed is True
        assert inner["then_expr"]["expression"]["value"] is True


class TestFixModuleOperations:
    def test_returns_only_changed_codes(self):
        operations = {
            "v8713_m": {"ast": _varid(55299, default="")},
            "v_untouched": {"ast": _varid(1, default="")},
        }
        changed = fix_module_operations(operations)
        assert changed == ["v8713_m"]
        assert "default" not in operations["v8713_m"]["ast"]
        assert operations["v_untouched"]["ast"]["default"] == ""

    def test_empty_operations_returns_empty_list(self):
        assert fix_module_operations({}) == []
