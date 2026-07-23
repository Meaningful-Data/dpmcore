"""Unit tests for the simplified parameter reference ``{pCode}``.

The verbose form ``{p_code, type [, default: value]}`` is covered by
``test_parameter_selection.py``. This module pins the simplified spelling
where the scalar type is deferred to the engine's parameter registry
(no inline type declaration).

The tests cover:

- parser accepts ``{pCode}`` and builds a ``ParameterRef`` with
  ``param_type=None``,
- the verbose form keeps its previous AST shape (backward compatibility),
- the semantic analyser types a simplified reference as a ``Mixed``
  scalar so downstream operators propagate it without a false type
  clash,
- the ``SemanticService.parameters`` payload carries
  ``declared_type=None`` for a simplified-only reference and upgrades
  to the verbose type when a verbose reference to the same code follows,
- ``ASTToJSONVisitor`` emits ``param_type: None`` for the simplified
  form (the engine keys off that to hit the parameter registry).
"""

from __future__ import annotations

from dpmcore.dpm_xl.ast.nodes import ParameterRef
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.dpm_xl.symbols import Scalar as ScalarSym
from dpmcore.dpm_xl.types.scalar import Mixed
from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor
from dpmcore.services.semantic import ParameterInfo, _parameters_from_oc
from dpmcore.services.syntax import SyntaxService


def _parse_parameter_ref(expression: str) -> ParameterRef:
    ast = SyntaxService().parse(expression)
    node = ast.children[0]
    assert isinstance(node, ParameterRef), (
        f"Expected ParameterRef, got {type(node).__name__}"
    )
    return node


# ---------------------------------------------------------------------------
# Parser + AST
# ---------------------------------------------------------------------------


def test_simplified_parses_with_param_type_none():
    """``{pCode}`` parses and builds a ParameterRef with no inline type."""
    node = _parse_parameter_ref("{pFINANCIAL_YEAR_END_MONTH}")
    assert node.code == "FINANCIAL_YEAR_END_MONTH"
    assert node.param_type is None
    assert node.default is None
    # ``is_set`` must not classify an untyped reference as a set.
    assert node.is_set is False


def test_verbose_form_still_parses_unchanged():
    """The historical ``{p_code, type}`` shape remains supported."""
    node = _parse_parameter_ref("{pTHRESHOLD, integer}")
    assert node.code == "THRESHOLD"
    assert node.param_type == "integer"
    assert node.default is None


def test_verbose_form_with_default_still_parses_unchanged():
    """``{p_code, type, default: value}`` keeps its previous AST shape."""
    node = _parse_parameter_ref("{pTHRESHOLD, integer, default: 12}")
    assert node.code == "THRESHOLD"
    assert node.param_type == "integer"
    assert node.default is not None


def test_simplified_leading_underscore_stripped():
    """The ``p_``/``p`` prefix normalisation matches the verbose form."""
    node_no_underscore = _parse_parameter_ref("{pFOO}")
    node_underscore = _parse_parameter_ref("{p_FOO}")
    assert node_no_underscore.code == "FOO"
    assert node_underscore.code == "FOO"


# ---------------------------------------------------------------------------
# Semantic analyser
# ---------------------------------------------------------------------------


def _visit(expression: str, node: ParameterRef):
    analyser = InputAnalyzer(expression)
    return analyser.visit_ParameterRef(node)


def test_semantic_returns_mixed_scalar_for_simplified_reference():
    """The simplified form is typed as ``Scalar(Mixed)`` so downstream
    operators keep it as unresolved instead of clashing on a wrong type.
    """
    node = _parse_parameter_ref("{pFY_END_MONTH}")
    operand = _visit("{pFY_END_MONTH}", node)
    assert isinstance(operand, ScalarSym)
    assert isinstance(operand.type, Mixed)
    assert operand.origin == "FY_END_MONTH"


def test_semantic_still_returns_declared_type_for_verbose_reference():
    """The verbose form keeps its original semantic behaviour: the AST's
    ``param_type`` maps to the corresponding ``ScalarType`` class.
    """
    node = _parse_parameter_ref("{pTHRESHOLD, integer}")
    operand = _visit("{pTHRESHOLD, integer}", node)
    assert isinstance(operand, ScalarSym)
    # The declared type flows through unchanged; ``Mixed`` is only used
    # for simplified references.
    assert not isinstance(operand.type, Mixed)


# ---------------------------------------------------------------------------
# Parameters payload (SemanticService surface)
# ---------------------------------------------------------------------------


class _FakeOperandsChecking:
    """Minimal stand-in for ``OperandsChecking`` — only the ``parameters``
    attribute is consumed by :func:`_parameters_from_oc`.
    """

    def __init__(self, refs):
        self.parameters = list(refs)


def test_parameters_payload_carries_none_declared_type_for_simplified():
    """A simplified reference alone yields ``declared_type=None`` in the
    ``ParameterInfo`` payload; consumers key off that to hit the engine
    parameter registry.
    """
    node = _parse_parameter_ref("{pFOO}")
    infos = _parameters_from_oc(_FakeOperandsChecking([node]))
    assert infos == (
        ParameterInfo(code="FOO", declared_type=None, default=None),
    )
    assert infos[0].is_set is False


def test_parameters_payload_verbose_reference_upgrades_prior_simplified():
    """When a simplified reference is followed by a verbose one on the
    same code, the resulting payload carries the verbose declared type
    (types 3-8 mismatch does not fire against ``None``).
    """
    simplified = _parse_parameter_ref("{pX}")
    verbose = _parse_parameter_ref("{pX, number}")
    infos = _parameters_from_oc(_FakeOperandsChecking([simplified, verbose]))
    assert infos == (
        ParameterInfo(code="X", declared_type="Number", default=None),
    )


def test_parameters_payload_verbose_first_then_simplified_keeps_verbose():
    """The reverse order (verbose first, simplified second on the same
    code) still reports the verbose declared type. The simplified
    follow-up does not downgrade the entry.
    """
    verbose = _parse_parameter_ref("{pX, number}")
    simplified = _parse_parameter_ref("{pX}")
    infos = _parameters_from_oc(_FakeOperandsChecking([verbose, simplified]))
    assert infos == (
        ParameterInfo(code="X", declared_type="Number", default=None),
    )


# ---------------------------------------------------------------------------
# ASTToJSONVisitor
# ---------------------------------------------------------------------------


def test_ast_to_json_serialises_simplified_with_none_param_type():
    """The JSON payload keeps ``param_type: None`` verbatim for the
    simplified form so the engine can key off it to trigger the registry
    lookup.
    """
    ast = SyntaxService().parse("{pFOO}")
    payload = ASTToJSONVisitor().visit(ast)
    node_payload = payload["children"][0]
    assert node_payload["class_name"] == "ParameterRef"
    assert node_payload["code"] == "FOO"
    assert node_payload["param_type"] is None


def test_ast_to_json_serialises_verbose_with_canonical_type():
    """The verbose form still surfaces its type in PascalCase."""
    ast = SyntaxService().parse("{pFOO, integer}")
    payload = ASTToJSONVisitor().visit(ast)
    node_payload = payload["children"][0]
    assert node_payload["class_name"] == "ParameterRef"
    assert node_payload["param_type"] == "Integer"


def test_toJSON_on_node_matches_visitor_for_simplified():
    """``ParameterRef.toJSON`` and ``ASTToJSONVisitor.visit_ParameterRef``
    agree on the simplified payload shape.
    """
    node = _parse_parameter_ref("{pFOO}")
    from_node = node.toJSON()
    assert from_node["param_type"] is None
    assert from_node["code"] == "FOO"
