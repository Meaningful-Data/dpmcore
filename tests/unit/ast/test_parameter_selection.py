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
    canonical_param_type,
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
# Set-typed default control (semantic, not grammar)
# ------------------------------------------------------------------ #


class TestSetDefaultControl:
    """Set-typed parameter defaults parse but are gated by the semantic pass.

    Set defaults are not supported (and may never be). They parse only because
    they share the grammar's ``default`` rule with item defaults; a non-null
    set default is then rejected by the semantic pass with ``3-9``. ``item``
    defaults and an explicit ``null`` stay valid.
    """

    @pytest.mark.parametrize(
        "expression",
        [
            "{p_x, set-number, default: {1, 2}}",
            "{p_x, set-item, default: {[eba_CU:EUR]}}",
            "{p_x, set-item, default: 5}",  # set declared, scalar default
            "{p_x, set-number, default: {[eba_CU:EUR]}}",  # wrong element
        ],
    )
    def test_set_default_parses_but_is_rejected_semantically(self, expression):
        # Parses only because it shares the grammar's default rule with item...
        assert SyntaxService().validate(expression).is_valid is True
        # ...but the semantic pass rejects any non-null set default.
        with pytest.raises(SemanticError) as exc:
            _analyze(expression)
        assert exc.value.code == "3-9"

    def test_null_default_on_set_parameter_is_allowed(self):
        # An explicit null is always accepted (it is the implicit default too).
        assert _analyze("{p_x, set-number, default: null}") is not None

    def test_item_default_is_accepted(self):
        assert _analyze("{p_x, item, default: [eba_CU:EUR]}") is not None


# ------------------------------------------------------------------ #
# Node + serialization
# ------------------------------------------------------------------ #


class TestNodeSerialization:
    def test_to_json(self):
        # is_set is derivable (not serialised); default stays on the node;
        # param_type is the engine's canonical PascalCase name.
        node = ParameterRef("x", "number", Constant("Integer", 0))
        assert node.toJSON() == {
            "class_name": "ParameterRef",
            "code": "x",
            "param_type": "Number",
            "default": 0,
        }

    def test_repr(self):
        node = ParameterRef("x", "set-item", None)
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
            "param_type": "Number",
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
            "{p_x, number, default: [eba_CU:EUR]}",  # scalar, non-literal
        ],
    )
    def test_incompatible_scalar_parameter_default_raises_3_7(
        self, expression
    ):
        with pytest.raises(SemanticError) as exc:
            _analyze(expression)
        assert exc.value.code == "3-7"


# ------------------------------------------------------------------ #
# Base template + service helpers (no DB)
# ------------------------------------------------------------------ #


class TestCanonicalParamType:
    @pytest.mark.parametrize(
        ("keyword", "expected"),
        [
            ("number", "Number"),
            ("integer", "Integer"),
            ("string", "String"),
            ("date", "Date"),
            ("boolean", "Boolean"),
            ("item", "Item"),
            ("set-number", "SetNumber"),
            ("set-item", "SetItem"),
            ("set-date", "SetDate"),
        ],
    )
    def test_keyword_maps_to_canonical(self, keyword, expected):
        assert canonical_param_type(keyword) == expected

    def test_idempotent(self):
        # Applying it to an already-canonical value is a no-op.
        assert canonical_param_type("Number") == "Number"
        assert canonical_param_type("SetNumber") == "SetNumber"


class TestHelpers:
    def test_base_template_visit_is_noop(self):
        assert ASTTemplate().visit(ParameterRef("x", "number")) is None

    def test_parameters_from_oc_dedupes_by_code(self):
        oc = SimpleNamespace(
            parameters=[
                ParameterRef("x", "number", Constant("Integer", 0)),
                ParameterRef("x", "number", None),  # duplicate code
                ParameterRef("y", "set-item", None),
            ]
        )
        infos = _parameters_from_oc(oc)
        # declared_type is surfaced in the engine's canonical PascalCase.
        assert infos == (
            ParameterInfo("x", "Number", 0),
            ParameterInfo("y", "SetItem", None),
        )

    def test_parameters_from_oc_raises_on_conflicting_type(self):
        # Same code, different declared type -> 3-8 (type is intrinsic to the
        # parameter; one bound value cannot satisfy two types).
        oc = SimpleNamespace(
            parameters=[
                ParameterRef("x", "number", None),
                ParameterRef("x", "set-number", None),
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
                ParameterRef("x", "number", Constant("Integer", 0)),
                ParameterRef("x", "number", Constant("Integer", 5)),
            ]
        )
        assert _parameters_from_oc(oc) == (ParameterInfo("x", "Number", 0),)

    def test_get_parameters_without_session_raises(self):
        with pytest.raises(RuntimeError):
            DpmXlService().get_parameters("{p_x, number}")

    @staticmethod
    def _param_info(code: str, param_type: str) -> ParameterInfo:
        return ParameterInfo(
            code=code,
            declared_type=param_type,
            default=None,
        )

    def test_accumulate_parameters_raises_on_cross_expression_conflict(self):
        # script() merges the per-expression SemanticResult.parameters across
        # operations: the same code with a different declared type cannot live
        # in the flat registry -> 3-8.
        svc = ASTGeneratorService.__new__(ASTGeneratorService)
        accumulated: dict = {}
        svc._accumulate_parameters(
            accumulated, [self._param_info("x", "Number")]
        )
        with pytest.raises(SemanticError) as exc:
            svc._accumulate_parameters(
                accumulated, [self._param_info("x", "String")]
            )
        assert exc.value.code == "3-8"

    def test_accumulate_parameters_merges_distinct_and_dedupes(self):
        svc = ASTGeneratorService.__new__(ASTGeneratorService)
        accumulated: dict = {}
        svc._accumulate_parameters(
            accumulated, [self._param_info("x", "Number")]
        )
        svc._accumulate_parameters(
            accumulated, [self._param_info("y", "SetItem")]
        )
        # Same code + same type across expressions is fine (no conflict).
        svc._accumulate_parameters(
            accumulated, [self._param_info("x", "Number")]
        )
        assert set(accumulated) == {"x", "y"}
        assert accumulated["x"].declared_type == "Number"
        assert accumulated["y"].declared_type == "SetItem"
