"""Tests for semantic evaluation of set algebra operators.

set_of, union, intersect, setdiff, symdiff all return ScalarSet.
count(setExpression) returns Scalar(Integer).
"""

import pandas as pd
import pytest

import dpmcore.dpm_xl.semantic_analyzer  # noqa: F401
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
from dpmcore.dpm_xl.symbols import (
    FactComponent,
    KeyComponent,
    RecordSet,
    Scalar,
    ScalarSet,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import Integer, Number
from dpmcore.dpm_xl.utils.tokens import STANDARD


def _make_integer_set() -> Set:
    return Set(
        children=[
            Constant(type_="Integer", value=1),
            Constant(type_="Integer", value=2),
        ]
    )


def _make_number_set() -> Set:
    return Set(
        children=[
            Constant(type_="Number", value=1.5),
            Constant(type_="Number", value=2.5),
        ]
    )


def _make_string_set() -> Set:
    return Set(
        children=[
            Constant(type_="String", value="a"),
            Constant(type_="String", value="b"),
        ]
    )


def _make_recordset() -> RecordSet:
    structure = Structure(
        [
            KeyComponent("r", Number(), STANDARD, "test"),
            FactComponent(Number(), "test"),
        ]
    )
    rs = RecordSet(structure, "test", "test")
    rs.records = pd.DataFrame(
        {"r": ["1", "2"], "data_type": [Number(), Number()]}
    )
    return rs


def _analyzer() -> InputAnalyzer:
    return InputAnalyzer(expression="dummy")


# ---------------------------------------------------------------------------
# set_of
# ---------------------------------------------------------------------------


def test_visit_set_of_op_returns_scalar_set_from_recordset():
    from dpmcore.dpm_xl.ast.nodes import AST

    class _RecordSetNode(AST):
        pass

    analyzer = _analyzer()
    analyzer.visit = lambda node: (
        _make_recordset()
        if isinstance(node, _RecordSetNode)
        else InputAnalyzer.visit(analyzer, node)
    )  # type: ignore[method-assign]

    node = SetOfOp(operand=_RecordSetNode())
    result = analyzer.visit(node)
    assert isinstance(result, ScalarSet)
    assert isinstance(result.type, Number)


def test_visit_set_of_op_raises_when_operand_not_recordset():
    from dpmcore.errors import SemanticError

    node = SetOfOp(operand=_make_integer_set())
    with pytest.raises(SemanticError):
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
        operands=[
            _make_integer_set(),
            _make_integer_set(),
            _make_integer_set(),
        ]
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


# ---------------------------------------------------------------------------
# Strict type homogeneity, no implicit promotion between compatible types
# ---------------------------------------------------------------------------


def test_union_integer_and_number_raises_semantic_error():
    """Integer and Number are compatible but not identical — must be rejected."""
    from dpmcore.errors import SemanticError

    node = UnionSetOp(operands=[_make_integer_set(), _make_number_set()])
    with pytest.raises(SemanticError):
        _analyzer().visit(node)


def test_intersect_integer_and_number_raises_semantic_error():
    from dpmcore.errors import SemanticError

    node = IntersectSetOp(operands=[_make_integer_set(), _make_number_set()])
    with pytest.raises(SemanticError):
        _analyzer().visit(node)


def test_setdiff_integer_and_number_raises_semantic_error():
    from dpmcore.errors import SemanticError

    node = SetdiffOp(left=_make_integer_set(), right=_make_number_set())
    with pytest.raises(SemanticError):
        _analyzer().visit(node)


def test_symdiff_integer_and_number_raises_semantic_error():
    from dpmcore.errors import SemanticError

    node = SymdiffOp(left=_make_integer_set(), right=_make_number_set())
    with pytest.raises(SemanticError):
        _analyzer().visit(node)


# ---------------------------------------------------------------------------
# MR !74 alignment: empty set literal, count via AggregationOp, arithmetic
# on ScalarSets, and set equality with mixed ScalarSet/RecordSet.
# ---------------------------------------------------------------------------


def _make_empty_set() -> Set:
    return Set(children=[])


def test_empty_set_operand_skipped_from_homogeneity_check_in_union():
    """§13.1.5: an empty set literal has no elements from which to infer a
    type, so it must not clash with any other operand's element type.
    """
    node = UnionSetOp(operands=[_make_empty_set(), _make_integer_set()])
    result = _analyzer().visit(node)
    assert isinstance(result, ScalarSet)
    assert isinstance(result.type, Integer)


def test_empty_set_operand_skipped_from_homogeneity_check_in_setdiff():
    node = SetdiffOp(left=_make_integer_set(), right=_make_empty_set())
    result = _analyzer().visit(node)
    assert isinstance(result, ScalarSet)
    assert isinstance(result.type, Integer)


def test_empty_set_operand_skipped_from_homogeneity_check_in_intersect():
    node = IntersectSetOp(operands=[_make_empty_set(), _make_number_set()])
    result = _analyzer().visit(node)
    assert isinstance(result, ScalarSet)
    assert isinstance(result.type, Number)


def test_empty_set_operand_skipped_from_homogeneity_check_in_symdiff():
    node = SymdiffOp(left=_make_empty_set(), right=_make_string_set())
    result = _analyzer().visit(node)
    assert isinstance(result, ScalarSet)


def test_all_empty_set_operands_still_return_scalar_set():
    """When every operand is ``{}`` the operator must not raise — it just
    returns the placeholder-typed empty ScalarSet.
    """
    node = UnionSetOp(operands=[_make_empty_set(), _make_empty_set()])
    result = _analyzer().visit(node)
    assert isinstance(result, ScalarSet)


def test_count_over_scalar_set_via_aggregation_op_returns_integer():
    """MR !74 dropped the ``#countSetOp`` grammar rule; ``count(<set>)`` now
    routes through ``visit_AggregationOp`` which must accept a ScalarSet
    operand and emit an ``Integer`` Scalar (like the old ``CountSetOp``).
    """
    from dpmcore.services.syntax import SyntaxService

    ast = SyntaxService().parse("count({1, 2, 3})")
    result = _analyzer().visit(ast)
    assert isinstance(result, Scalar)
    assert isinstance(result.type, Integer)


def test_count_over_union_via_aggregation_op_returns_integer():
    from dpmcore.services.syntax import SyntaxService

    ast = SyntaxService().parse("count(union({1, 2}, {3, 4}))")
    result = _analyzer().visit(ast)
    assert isinstance(result, Scalar)
    assert isinstance(result.type, Integer)


def test_count_over_empty_set_via_aggregation_op_returns_integer():
    from dpmcore.services.syntax import SyntaxService

    ast = SyntaxService().parse("count({})")
    result = _analyzer().visit(ast)
    assert isinstance(result, Scalar)
    assert isinstance(result.type, Integer)


def test_scalar_set_arithmetic_raises_semantic_error_3_3():
    """§13 forbids arithmetic on ScalarSets. Previously leaked a bare
    ``NotImplementedError`` (``error_code="UNKNOWN"``); must raise
    ``SemanticError("3-3")`` from ``types_given_structures``.
    """
    from dpmcore.errors import SemanticError
    from dpmcore.services.syntax import SyntaxService

    ast = SyntaxService().parse("{1, 2} + {3, 4}")
    with pytest.raises(SemanticError) as exc:
        _analyzer().visit(ast)
    assert exc.value.code == "3-3"


def test_scalar_set_ordering_raises_semantic_error_3_3():
    from dpmcore.errors import SemanticError
    from dpmcore.services.syntax import SyntaxService

    ast = SyntaxService().parse("{1, 2} > {3, 4}")
    with pytest.raises(SemanticError) as exc:
        _analyzer().visit(ast)
    assert exc.value.code == "3-3"


def test_scalar_set_boolean_raises_semantic_error_3_3():
    from dpmcore.errors import SemanticError
    from dpmcore.services.syntax import SyntaxService

    ast = SyntaxService().parse("{1, 2} and {3, 4}")
    with pytest.raises(SemanticError) as exc:
        _analyzer().visit(ast)
    assert exc.value.code == "3-3"


def test_scalar_set_equality_between_two_scalar_sets_returns_boolean_scalar():
    """§13.7: set equality on two ScalarSets returns a Boolean Scalar."""
    from dpmcore.services.syntax import SyntaxService

    ast = SyntaxService().parse("{1, 2, 3} = {3, 2, 1}")
    result = _analyzer().visit(ast)
    assert isinstance(result, Scalar)
    assert str(result.type) == "Boolean"


def test_scalar_set_inequality_between_two_scalar_sets_returns_boolean_scalar():
    from dpmcore.services.syntax import SyntaxService

    ast = SyntaxService().parse("{1, 2} != {3, 4}")
    result = _analyzer().visit(ast)
    assert isinstance(result, Scalar)
    assert str(result.type) == "Boolean"


def test_equal_scalar_set_and_recordset_rejected_ss_lhs():
    """§13.7.5 / §5.2.1.5: mixing a ScalarSet with a Recordset in ``=`` is
    explicitly rejected — even though the grammar accepts it, the semantic
    layer must not silently return a valid result.
    """
    from dpmcore.dpm_xl.operators.comparison import Equal
    from dpmcore.errors import SemanticError

    ss = ScalarSet(type_=Integer(), name=None, origin="{1,2,3}")
    rs = _make_recordset()
    with pytest.raises(SemanticError) as exc:
        Equal.validate(ss, rs)
    assert exc.value.code == "3-3"


def test_equal_scalar_set_and_recordset_rejected_rs_lhs():
    from dpmcore.dpm_xl.operators.comparison import Equal
    from dpmcore.errors import SemanticError

    ss = ScalarSet(type_=Integer(), name=None, origin="{1,2,3}")
    rs = _make_recordset()
    with pytest.raises(SemanticError) as exc:
        Equal.validate(rs, ss)
    assert exc.value.code == "3-3"


def test_notequal_scalar_set_and_recordset_rejected_both_directions():
    from dpmcore.dpm_xl.operators.comparison import NotEqual
    from dpmcore.errors import SemanticError

    ss = ScalarSet(type_=Integer(), name=None, origin="{1,2,3}")
    rs = _make_recordset()
    with pytest.raises(SemanticError) as exc:
        NotEqual.validate(ss, rs)
    assert exc.value.code == "3-3"
    with pytest.raises(SemanticError) as exc2:
        NotEqual.validate(rs, ss)
    assert exc2.value.code == "3-3"
