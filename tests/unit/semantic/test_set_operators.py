"""Tests for semantic evaluation of set algebra operators.

set_of, union, intersect, setdiff, symdiff all return ScalarSet.
count(setExpression) returns Scalar(Integer).
"""

import pytest

from dpmcore.dpm_xl.ast.nodes import (
    Constant,
    CountSetOp,
    IntersectSetOp,
    Set,
    SetdiffOp,
    SetOfOp,
    SymdiffOp,
    UnionSetOp,
)
from dpmcore.dpm_xl.semantic_analyzer import InputAnalyzer
from dpmcore.dpm_xl.symbols import Scalar, ScalarSet
from dpmcore.dpm_xl.types.scalar import Integer


def _make_integer_set() -> Set:
    return Set(
        children=[
            Constant(type_="Integer", value=1),
            Constant(type_="Integer", value=2),
        ]
    )


def _make_string_set() -> Set:
    return Set(
        children=[
            Constant(type_="String", value="a"),
            Constant(type_="String", value="b"),
        ]
    )


def _analyzer() -> InputAnalyzer:
    return InputAnalyzer(expression="dummy")


# ---------------------------------------------------------------------------
# set_of
# ---------------------------------------------------------------------------

def test_visit_set_of_op_raises_not_implemented():
    node = SetOfOp(operand=_make_integer_set())
    with pytest.raises(NotImplementedError):
        _analyzer().visit(node)


# ---------------------------------------------------------------------------
# union
# ---------------------------------------------------------------------------

def test_visit_union_returns_scalar_set():
    node = UnionSetOp(operands=[_make_integer_set(), _make_integer_set()])
    result = _analyzer().visit(node)
    assert isinstance(result, ScalarSet)


def test_visit_union_three_operands_returns_scalar_set():
    node = UnionSetOp(
        operands=[_make_integer_set(), _make_integer_set(), _make_integer_set()]
    )
    result = _analyzer().visit(node)
    assert isinstance(result, ScalarSet)


def test_visit_union_mixed_types_raises_semantic_error():
    from dpmcore.errors import SemanticError

    node = UnionSetOp(operands=[_make_integer_set(), _make_string_set()])
    with pytest.raises(SemanticError):
        _analyzer().visit(node)


# ---------------------------------------------------------------------------
# intersect
# ---------------------------------------------------------------------------

def test_visit_intersect_returns_scalar_set():
    node = IntersectSetOp(operands=[_make_integer_set(), _make_integer_set()])
    result = _analyzer().visit(node)
    assert isinstance(result, ScalarSet)


def test_visit_intersect_mixed_types_raises_semantic_error():
    from dpmcore.errors import SemanticError

    node = IntersectSetOp(operands=[_make_integer_set(), _make_string_set()])
    with pytest.raises(SemanticError):
        _analyzer().visit(node)


# ---------------------------------------------------------------------------
# setdiff
# ---------------------------------------------------------------------------

def test_visit_setdiff_returns_scalar_set():
    node = SetdiffOp(left=_make_integer_set(), right=_make_integer_set())
    result = _analyzer().visit(node)
    assert isinstance(result, ScalarSet)


def test_visit_setdiff_mixed_types_raises_semantic_error():
    from dpmcore.errors import SemanticError

    node = SetdiffOp(left=_make_integer_set(), right=_make_string_set())
    with pytest.raises(SemanticError):
        _analyzer().visit(node)


# ---------------------------------------------------------------------------
# symdiff
# ---------------------------------------------------------------------------

def test_visit_symdiff_returns_scalar_set():
    node = SymdiffOp(left=_make_integer_set(), right=_make_integer_set())
    result = _analyzer().visit(node)
    assert isinstance(result, ScalarSet)


def test_visit_symdiff_mixed_types_raises_semantic_error():
    from dpmcore.errors import SemanticError

    node = SymdiffOp(left=_make_integer_set(), right=_make_string_set())
    with pytest.raises(SemanticError):
        _analyzer().visit(node)


# ---------------------------------------------------------------------------
# count(setExpression)
# ---------------------------------------------------------------------------

def test_visit_count_set_op_returns_integer_scalar():
    node = CountSetOp(operand=_make_integer_set())
    result = _analyzer().visit(node)
    assert isinstance(result, Scalar)
    assert isinstance(result.type, Integer)


def test_visit_count_set_op_on_union_returns_integer_scalar():
    inner = UnionSetOp(operands=[_make_integer_set(), _make_integer_set()])
    node = CountSetOp(operand=inner)
    result = _analyzer().visit(node)
    assert isinstance(result, Scalar)
    assert isinstance(result.type, Integer)
