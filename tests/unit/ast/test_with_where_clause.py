"""Parsing of the ``[where ...]`` block of a ``with`` clause.

Two defects, both in ``visitExprWithSelection``:

Issue #281 -- the block was consumed by the parser and then discarded. The
node had no field for the condition and the constructor read only the
partial selection and the body, so the clause filtered nothing and no error
was raised: the engine payload was byte-identical to the same expression
written without the filter.

The earlier one -- the body was read from a hard-coded ``ctx_list[3]``. With
the optional block present that index lands on the WHERE terminal, so
``WithExpression.expression`` came out None and the semantic analyzer then
raised ``NotImplementedError: No visit_NoneType method``. The fix uses
``ctx_list[-1]``, which is the body in both cases.

The clause is now captured and grafted onto every body selection, so
``with {tX}[where A = 1]: {c0010} = {c0020}`` builds exactly the AST of
``with {tX}: {c0010}[where A = 1] = {c0020}[where A = 1]`` (DPM-XL §3.2.5),
unless an operand carries its own ``where`` or ``sub`` (§3.2.6).
"""

from typing import Any

from dpmcore.dpm_xl.ast.nodes import (
    AggregationOp,
    CondExpr,
    GetOp,
    RenameOp,
    Start,
    SubOp,
    TimeShiftOp,
    VarID,
    WhereClauseOp,
    WithExpression,
)
from dpmcore.dpm_xl.utils.serialization import serialize_ast
from dpmcore.services.syntax import SyntaxService

CONDITION = "id1 = 1"


def _with_expression(expression: str) -> WithExpression:
    """Parse ``expression`` and return its ``WithExpression`` root."""
    ast = SyntaxService().parse(expression)
    assert isinstance(ast, Start)
    with_expr = ast.children[0]
    assert isinstance(with_expr, WithExpression)
    return with_expr


def _dimension_codes(node: Any) -> list[str]:
    """Dimension codes of the where condition wrapping ``node``, if any."""
    if not isinstance(node, WhereClauseOp):
        return []
    return [node.condition.left.dimension_code]


def test_with_where_clause_body_is_not_none() -> None:
    """Body expression of ``with { } [ where ]: body`` must not be None."""
    expression = (
        "with {tR_04.00.a, c*, default: 0, interval: true}"
        " [where qPYB = [eba_qIA:qx2090]]:"
        " {r0100} >= 0"
    )
    assert _with_expression(expression).expression is not None


def test_condition_is_stored_on_the_node() -> None:
    """The condition survives parsing instead of being discarded."""
    with_expr = _with_expression(
        f"with {{tX}}[where {CONDITION}]: {{c0010}} = {{c0020}}"
    )
    condition = with_expr.where_condition
    assert condition is not None
    assert condition.op == "="
    assert condition.left.dimension_code == "id1"


def test_no_where_block_leaves_the_body_untouched() -> None:
    """Expressions without the block keep their previous AST exactly."""
    with_expr = _with_expression("with {tX}: {c0010} = {c0020}")
    assert with_expr.where_condition is None
    assert isinstance(with_expr.expression.left, VarID)
    assert isinstance(with_expr.expression.right, VarID)


def test_clause_is_grafted_onto_every_body_selection() -> None:
    """§3.2.5: the clause reaches every operand from a selection operator."""
    body = _with_expression(
        f"with {{tX}}[where {CONDITION}]: {{c0010}} = {{c0020}}"
    ).expression
    for side in (body.left, body.right):
        assert isinstance(side, WhereClauseOp)
        assert isinstance(side.operand, VarID)
        assert _dimension_codes(side) == ["id1"]


def test_each_selection_gets_its_own_copy_of_the_condition() -> None:
    """Sharing one subtree would let the passes annotate over each other.

    ``OperandsChecking`` writes ``property_id`` onto condition nodes and
    ``MLGeneration`` writes ``parent``/``argument``/``num``, all in place.
    """
    with_expr = _with_expression(
        f"with {{tX}}[where {CONDITION}]: {{c0010}} = {{c0020}}"
    )
    left, right = with_expr.expression.left, with_expr.expression.right
    assert left.condition is not right.condition
    assert left.condition is not with_expr.where_condition
    assert serialize_ast(left.condition) == serialize_ast(right.condition)


def test_inner_where_overrides_the_clause_for_that_operand() -> None:
    """§3.2.6: an operand's own where wins, even naming another property."""
    body = _with_expression(
        f"with {{tX}}[where {CONDITION}]: {{c0010}}[where id2 = 2] = {{c0020}}"
    ).expression
    assert _dimension_codes(body.left) == ["id2"]
    assert _dimension_codes(body.right) == ["id1"]


def test_inner_sub_overrides_the_clause_for_that_operand() -> None:
    """§3.2.6: a ``sub`` overrides the clause just as a ``where`` does."""
    body = _with_expression(
        f"with {{tX}}[where {CONDITION}]: {{c0010}}[sub id2 = 2] = {{c0020}}"
    ).expression
    assert isinstance(body.left, SubOp)
    assert isinstance(body.left.operand, VarID)
    assert _dimension_codes(body.right) == ["id1"]


def test_override_survives_a_clause_chained_after_the_inner_where() -> None:
    """``[where ...][get ...]`` still counts as an override."""
    body = _with_expression(
        f"with {{tX}}[where {CONDITION}]:"
        f" {{c0010}}[where id2 = 2][get id3] = 0"
    ).expression
    assert isinstance(body.left, GetOp)
    assert _dimension_codes(body.left.operand) == ["id2"]


def test_graft_sits_inside_get_and_rename() -> None:
    """Filter before projecting or renaming.

    The condition names the components the operand had before the clause
    reshaped it, so the where has to be the inner node.
    """
    get_body = _with_expression(
        f"with {{tX}}[where {CONDITION}]: {{c0010}}[get id2] = 0"
    ).expression
    assert isinstance(get_body.left, GetOp)
    assert _dimension_codes(get_body.left.operand) == ["id1"]

    rename_body = _with_expression(
        f"with {{tX}}[where {CONDITION}]: {{c0010}}[rename id2 to id3] = 0"
    ).expression
    assert isinstance(rename_body.left, RenameOp)
    assert _dimension_codes(rename_body.left.operand) == ["id1"]


def test_graft_reaches_selections_nested_in_operators() -> None:
    """Aggregations, time shifts and every branch of a conditional."""
    aggr = _with_expression(
        f"with {{tX}}[where {CONDITION}]: sum({{c0010}}) = 0"
    ).expression
    assert isinstance(aggr.left, AggregationOp)
    assert _dimension_codes(aggr.left.operand) == ["id1"]

    shift = _with_expression(
        f"with {{tX}}[where {CONDITION}]: time_shift({{c0010}}, Q, 1) = 0"
    ).expression
    assert isinstance(shift.left, TimeShiftOp)
    assert _dimension_codes(shift.left.operand) == ["id1"]

    cond = _with_expression(
        f"with {{tX}}[where {CONDITION}]:"
        f" if {{c0010}} > 0 then {{c0020}} else {{c0030}} endif = 1"
    ).expression.left
    assert isinstance(cond, CondExpr)
    assert _dimension_codes(cond.condition.left) == ["id1"]
    assert _dimension_codes(cond.then_expr) == ["id1"]
    assert _dimension_codes(cond.else_expr) == ["id1"]


def test_payload_differs_from_the_unfiltered_expression() -> None:
    """The reported symptom: identical payloads with and without the block."""
    parse = SyntaxService().parse
    with_filter = 'with {tEXM, r0010}[where id1 = "ABC"]: {c0010} = {c0020}'
    no_filter = "with {tEXM, r0010}: {c0010} = {c0020}"
    assert serialize_ast(parse(with_filter)) != serialize_ast(parse(no_filter))


def test_payload_matches_the_explicit_per_operand_form() -> None:
    """The clause desugars to what the author would have written by hand."""
    parse = SyntaxService().parse
    implicit = 'with {tEXM, r0010}[where id1 = "ABC"]: {c0010} = {c0020}'
    explicit = (
        'with {tEXM, r0010}: {c0010}[where id1 = "ABC"]'
        ' = {c0020}[where id1 = "ABC"]'
    )
    assert serialize_ast(parse(implicit)) == serialize_ast(parse(explicit))


def test_payload_emits_a_where_clause_op_per_selection() -> None:
    """Wire shape the engine expects, with no new ``class_name``."""
    payload = serialize_ast(
        SyntaxService().parse(
            'with {tEXM, r0010}[where id1 = "ABC"]: {c0010} = {c0020}'
        )
    )
    for side in (payload["left"], payload["right"]):
        assert side["class_name"] == "WhereClauseOp"
        assert side["operand"]["class_name"] == "VarID"
        assert side["condition"]["left"] == {
            "class_name": "Dimension",
            "dimension_code": "id1",
        }
