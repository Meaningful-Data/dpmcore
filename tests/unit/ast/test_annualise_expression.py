import pytest

from dpmcore import errors
from dpmcore.dpm_xl.ast.nodes import AnnualiseOp, Constant
from dpmcore.dpm_xl.operators.time import Annualise
from dpmcore.dpm_xl.symbols import Scalar
from dpmcore.dpm_xl.types.scalar import Number
from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor
from dpmcore.services.syntax import SyntaxService

# ---------------------------------------------------------------------------
# Syntax
# ---------------------------------------------------------------------------

VALID_FORMS = [
    "annualise({tT1, r010, c010}, 12, refPeriod)",
    "annualise({tT1, r010, c010}, 3, refPeriod)",
    "annualise({tT1}, 6, myDate)",
]

INVALID_FORMS = [
    "annualise({tT1}, 12)",
    "annualise({tT1})",
    "annualise()",
]


@pytest.mark.parametrize("source", VALID_FORMS)
def test_annualise_syntax_valid(source):
    assert SyntaxService().is_valid(source)


@pytest.mark.parametrize("source", INVALID_FORMS)
def test_annualise_wrong_arity_invalid(source):
    assert not SyntaxService().is_valid(source)


# ---------------------------------------------------------------------------
# AST node
# ---------------------------------------------------------------------------


def test_annualise_ast_node():
    ast = SyntaxService().parse("annualise({tT1, r010, c010}, 12, refPeriod)")
    node = ast.children[0]
    assert isinstance(node, AnnualiseOp)
    assert node.op == "annualise"
    assert node.operand is not None
    assert node.fy_end is not None
    assert node.component == "refPeriod"


def test_annualise_tojson():
    ast = SyntaxService().parse("annualise({tT1, r010, c010}, 12, refPeriod)")
    node = ast.children[0]
    assert isinstance(node, AnnualiseOp)
    result = node.toJSON()
    assert result["class_name"] == "AnnualiseOp"
    assert result["op"] == "annualise"
    assert "operand" in result
    assert "fy_end" in result
    assert result["component"] == "refPeriod"


def test_template_visits_fy_end_constant():
    ast = SyntaxService().parse("annualise({tT1, r010, c010}, 12, refPeriod)")
    node = ast.children[0]
    assert isinstance(node.fy_end, Constant)
    assert node.fy_end.value == 12


def test_serializer_produces_annualise_dict():
    ast = SyntaxService().parse("annualise({tT1, r010, c010}, 12, refPeriod)")
    result = ASTToJSONVisitor().visit(ast)
    node = result["children"][0]
    assert node["class_name"] == "AnnualiseOp"
    assert node["op"] == "annualise"
    assert node["component"] == "refPeriod"
    assert isinstance(node["fy_end"], dict)
    assert "class_name" in node["fy_end"]
    assert isinstance(node["operand"], dict)


# ---------------------------------------------------------------------------
# Operator validation
# ---------------------------------------------------------------------------


def _make_scalar(name: str) -> Scalar:
    return Scalar(type_=Number(), name=name, origin=name)


@pytest.mark.parametrize("fy_end", [0, 13, -1, 99])
def test_annualise_invalid_fy_end_raises_semantic_error(fy_end):
    operand = _make_scalar("x")
    with pytest.raises(errors.SemanticError):
        Annualise.validate(
            operand=operand, component_name="refPeriod", fy_end=fy_end
        )


@pytest.mark.parametrize("fy_end", [1, 3, 6, 12])
def test_annualise_valid_fy_end_returns_numeric_scalar(fy_end):
    operand = _make_scalar("x")
    result = Annualise.validate(
        operand=operand, component_name="refPeriod", fy_end=fy_end
    )
    assert isinstance(result, Scalar)
    assert isinstance(result.type, Number)
    assert str(fy_end) in result.origin
