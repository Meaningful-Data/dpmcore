"""Unit tests for DPM-XL Parameter Selection (``{p_code, type [, default]}``).

These cover parsing/AST construction, the ``ParameterRef`` node and its
serialization, the semantic typing of parameters and the default-compatibility
checks — none of which require a database session.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dpmcore.dpm_xl.ast.nodes import (
    AST,
    BinOp,
    Constant,
    ParameterRef,
    Scalar,
    Set,
    VarRef,
    parameter_default_value,
)
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.dpm_xl.symbols import Scalar as ScalarSym
from dpmcore.dpm_xl.symbols import ScalarSet
from dpmcore.dpm_xl.types.scalar import (
    Boolean,
    Date,
    Integer,
    Item,
    Number,
    String,
)
from dpmcore.dpm_xl.utils.serialization import serialize_ast
from dpmcore.errors import SemanticError
from dpmcore.services.ast_generator import ASTGeneratorService
from dpmcore.services.dpm_xl import DpmXlService
from dpmcore.services.semantic import ParameterInfo, _parameters_from_oc
from dpmcore.services.syntax import SyntaxService

_SCALAR_TYPES = ["number", "integer", "string", "date", "boolean", "item"]
_SET_TYPES = [f"set-{t}" for t in _SCALAR_TYPES]

_ELEMENT_TYPE = {
    "number": Number,
    "integer": Integer,
    "string": String,
    "date": Date,
    "boolean": Boolean,
    "item": Item,
}


def _find_param_refs(node: object, out: list[ParameterRef] | None = None):
    out = [] if out is None else out
    if isinstance(node, ParameterRef):
        out.append(node)
    if isinstance(node, AST):
        for value in vars(node).values():
            _find_param_refs(value, out)
    elif isinstance(node, list):
        for item in node:
            _find_param_refs(item, out)
    return out


def _only_param(expression: str) -> ParameterRef:
    ast = SyntaxService().parse(expression)
    params = _find_param_refs(ast)
    assert len(params) == 1
    return params[0]


def _analyze(expression: str):
    ast = SyntaxService().parse(expression)
    return InputAnalyzer(expression).visit(ast)


# ------------------------------------------------------------------ #
# Parsing / AST construction
# ------------------------------------------------------------------ #


class TestParsing:
    @pytest.mark.parametrize("kw", _SCALAR_TYPES)
    def test_scalar_types_parse(self, kw):
        p = _only_param(f"{{p_x, {kw}}}")
        assert p.code == "x"
        assert p.param_type == kw
        assert p.is_set is False
        assert p.default is None

    @pytest.mark.parametrize("kw", _SET_TYPES)
    def test_set_types_parse(self, kw):
        p = _only_param(f"{{p_x, {kw}}}")
        assert p.param_type == kw
        assert p.is_set is True

    def test_cosmetic_underscore_equivalence(self):
        assert _only_param("{p_threshold, number}").code == "threshold"
        assert _only_param("{pthreshold, number}").code == "threshold"

    def test_backtick_escaped_code_preserves_inner_underscore(self):
        assert _only_param("{p`_legacy_param`, number}").code == (
            "_legacy_param"
        )

    def test_set_parameter_as_in_rhs_is_bare_parameter_ref(self):
        # ``setElements`` must return the lone ParameterRef (not a Set wrapper)
        # so the semantic pass turns it into a ScalarSet.
        ast = SyntaxService().parse("1 in {p_ccys, set-item}")
        binop = ast.children[0]
        assert isinstance(binop, BinOp)
        assert binop.op == "in"
        assert isinstance(binop.right, ParameterRef)


# ------------------------------------------------------------------ #
# Defaults + parameter_default_value
# ------------------------------------------------------------------ #


class TestDefaults:
    def test_literal_default(self):
        assert _only_param("{p_x, number, default: 0}").default is not None
        assert (
            parameter_default_value(
                _only_param("{p_x, integer, default: 5}").default
            )
            == 5
        )

    def test_null_default(self):
        p = _only_param("{p_x, number, default: null}")
        assert isinstance(p.default, Constant)
        assert parameter_default_value(p.default) is None

    def test_item_default(self):
        p = _only_param("{p_x, item, default: [eba_CU:EUR]}")
        assert isinstance(p.default, Scalar)
        assert parameter_default_value(p.default) == "eba_CU:EUR"

    def test_set_default(self):
        p = _only_param("{p_x, set-number, default: {1, 2}}")
        assert isinstance(p.default, Set)
        assert parameter_default_value(p.default) == [1, 2]

    def test_set_item_default(self):
        p = _only_param("{p_x, set-item, default: {[eba_CU:EUR]}}")
        assert parameter_default_value(p.default) == ["eba_CU:EUR"]

    def test_default_value_helpers_cover_all_shapes(self):
        assert parameter_default_value(None) is None
        assert parameter_default_value(Constant("Integer", 7)) == 7
        assert parameter_default_value(Constant("Null", None)) is None
        assert parameter_default_value(Scalar("ns:c", "Item")) == "ns:c"
        assert parameter_default_value(
            Set([Constant("Integer", 1), Constant("Integer", 2)])
        ) == [1, 2]
        # Fallback: an unexpected node type reduces to None.
        assert parameter_default_value(VarRef("v")) is None


# ------------------------------------------------------------------ #
# Node + serialization
# ------------------------------------------------------------------ #


class TestNodeSerialization:
    def test_to_json(self):
        node = ParameterRef("x", "number", False, Constant("Integer", 0))
        assert node.toJSON() == {
            "class_name": "ParameterRef",
            "code": "x",
            "param_type": "number",
            "is_set": False,
            "default": 0,
        }

    def test_repr(self):
        node = ParameterRef("x", "set-item", True, None)
        text = repr(node)
        assert "ParameterRef" in text
        assert "set-item" in text

    def test_serialize_ast_emits_parameter_ref(self):
        ast = SyntaxService().parse(
            "{tF_00.01, r010, c010} > {p_threshold, number, default: 0}"
        )
        right = serialize_ast(ast)["right"]
        assert right == {
            "class_name": "ParameterRef",
            "code": "threshold",
            "param_type": "number",
            "is_set": False,
            "default": 0,
        }


# ------------------------------------------------------------------ #
# Semantic typing + default-compatibility
# ------------------------------------------------------------------ #


class TestSemantics:
    @pytest.mark.parametrize("kw", _SCALAR_TYPES)
    def test_scalar_parameter_yields_scalar(self, kw):
        result = _analyze(f"{{p_x, {kw}}}")
        assert isinstance(result, ScalarSym)
        assert isinstance(result.type, _ELEMENT_TYPE[kw])

    @pytest.mark.parametrize("kw", _SCALAR_TYPES)
    def test_set_parameter_yields_scalar_set(self, kw):
        result = _analyze(f"{{p_x, set-{kw}}}")
        assert isinstance(result, ScalarSet)
        assert isinstance(result.type, _ELEMENT_TYPE[kw])

    def test_set_parameter_is_valid_in_rhs(self):
        result = _analyze("1 in {p_ns, set-number}")
        assert result is not None

    @pytest.mark.parametrize(
        "expression",
        [
            "{p_x, number, default: 0}",
            '{p_x, string, default: "a"}',
            "{p_x, boolean, default: true}",
            "{p_x, date, default: #2024-01-01#}",
            "{p_x, item, default: [eba_CU:EUR]}",
            "{p_x, number, default: null}",
            "{p_x, set-item, default: {[eba_CU:EUR]}}",
            "{p_x, set-number, default: {1, 2}}",
        ],
    )
    def test_compatible_defaults_pass(self, expression):
        assert _analyze(expression) is not None

    def test_incompatible_literal_default_raises_3_6(self):
        with pytest.raises(SemanticError) as exc:
            _analyze("{p_x, number, default: true}")
        assert exc.value.code == "3-6"

    @pytest.mark.parametrize(
        "expression",
        [
            "{p_x, item, default: 5}",  # item declared, literal default
            "{p_x, set-item, default: 5}",  # set declared, scalar default
            "{p_x, set-number, default: {[eba_CU:EUR]}}",  # wrong element
        ],
    )
    def test_incompatible_parameter_default_raises_3_7(self, expression):
        with pytest.raises(SemanticError) as exc:
            _analyze(expression)
        assert exc.value.code == "3-7"


# ------------------------------------------------------------------ #
# Base template + service helpers (no DB)
# ------------------------------------------------------------------ #


class TestHelpers:
    def test_base_template_visit_is_noop(self):
        assert ASTTemplate().visit(ParameterRef("x", "number", False)) is None

    def test_parameters_from_oc_dedupes_by_code(self):
        oc = SimpleNamespace(
            parameters=[
                ParameterRef("x", "number", False, Constant("Integer", 0)),
                ParameterRef("x", "number", False, None),  # duplicate code
                ParameterRef("y", "set-item", True, None),
            ]
        )
        infos = _parameters_from_oc(oc)
        assert infos == (
            ParameterInfo("x", "number", False, 0),
            ParameterInfo("y", "set-item", True, None),
        )

    def test_parameters_from_oc_raises_on_conflicting_type(self):
        # Same code, different declared type -> 3-8 (type is intrinsic to the
        # parameter; one bound value cannot satisfy two types).
        oc = SimpleNamespace(
            parameters=[
                ParameterRef("x", "number", False, None),
                ParameterRef("x", "set-number", True, None),
            ]
        )
        with pytest.raises(SemanticError) as exc:
            _parameters_from_oc(oc)
        assert exc.value.code == "3-8"

    def test_parameters_from_oc_allows_differing_defaults_same_type(self):
        # Defaults are per-reference fallbacks: differing values are fine as
        # long as the declared type matches; first-seen default is kept.
        oc = SimpleNamespace(
            parameters=[
                ParameterRef("x", "number", False, Constant("Integer", 0)),
                ParameterRef("x", "number", False, Constant("Integer", 5)),
            ]
        )
        assert _parameters_from_oc(oc) == (
            ParameterInfo("x", "number", False, 0),
        )

    def test_extract_referenced_parameters_from_serialised_ast(self):
        ast_dict = {
            "class_name": "BinOp",
            "left": {"class_name": "VarID", "table": "C_01.00"},
            "right": {
                "class_name": "ParameterRef",
                "code": "threshold",
                "param_type": "number",
                "is_set": False,
                "default": 0,
            },
        }
        found = ASTGeneratorService._extract_referenced_parameters(ast_dict)
        assert found == {
            "threshold": ParameterInfo("threshold", "number", False, 0)
        }

    def test_extract_referenced_parameters_ignores_other_nodes(self):
        assert (
            ASTGeneratorService._extract_referenced_parameters(
                {"class_name": "Constant", "value": 0}
            )
            == {}
        )

    def test_extract_referenced_parameters_recurses_into_lists(self):
        # ParameterRef nested inside a list-valued field (e.g. Set children).
        ast_dict = {
            "class_name": "Set",
            "children": [
                {"class_name": "Constant", "value": 1},
                {
                    "class_name": "ParameterRef",
                    "code": "x",
                    "param_type": "set-number",
                    "is_set": True,
                    "default": None,
                },
            ],
        }
        found = ASTGeneratorService._extract_referenced_parameters(ast_dict)
        assert found == {"x": ParameterInfo("x", "set-number", True, None)}

    def test_get_parameters_without_session_raises(self):
        with pytest.raises(RuntimeError):
            DpmXlService().get_parameters("{p_x, number}")

    @staticmethod
    def _param_node(code: str, param_type: str) -> dict:
        return {
            "class_name": "ParameterRef",
            "code": code,
            "param_type": param_type,
            "is_set": param_type.startswith("set-"),
            "default": None,
        }

    def test_accumulate_parameters_raises_on_cross_expression_conflict(self):
        # script() merges parameters across operations: the same code with a
        # different declared type cannot live in the flat registry -> 3-8.
        svc = ASTGeneratorService.__new__(ASTGeneratorService)
        accumulated: dict = {}
        svc._accumulate_parameters(
            accumulated, self._param_node("x", "number")
        )
        with pytest.raises(SemanticError) as exc:
            svc._accumulate_parameters(
                accumulated, self._param_node("x", "string")
            )
        assert exc.value.code == "3-8"

    def test_accumulate_parameters_merges_distinct_and_dedupes(self):
        svc = ASTGeneratorService.__new__(ASTGeneratorService)
        accumulated: dict = {}
        svc._accumulate_parameters(
            accumulated, self._param_node("x", "number")
        )
        svc._accumulate_parameters(
            accumulated, self._param_node("y", "set-item")
        )
        # Same code + same type across expressions is fine (no conflict).
        svc._accumulate_parameters(
            accumulated, self._param_node("x", "number")
        )
        assert set(accumulated) == {"x", "y"}
        assert accumulated["x"].declared_type == "number"
        assert accumulated["y"].declared_type == "set-item"
