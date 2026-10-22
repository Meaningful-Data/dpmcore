"""Never-null check for DPM-XL expressions.

Some expressions can never evaluate to ``null`` by definition, so
``isnull(...)`` over them is ``false`` for every record it can produce: a
constant in disguise, and almost always an authoring mistake (#443).

``never_null_reason`` answers "can this expression be null?" for one AST
node. It returns a short reason when the definitions rule a null out, and
``None`` otherwise. It is a conservative check: ``None`` means "might be
null", never "is null".

Never null by definition:

- ``count(...)`` in every form (plain, ``group by``, ``over (...)``): an
  operand with no records or only null values yields ``0``, and a group by
  over no records yields an empty recordset rather than a null.
- ``rank(... over (...))``: records with a null order value still receive
  a rank.
- ``isnull(...)``: returns only ``true`` or ``false``.
- Non-null literals, including the empty string, which is a distinct
  String value and not ``null``.
- A cell or parameter selection with a non-null ``default:``.

Looked through, because they keep the never-null property of their operand:

- Parentheses, ``not``, and the value-preserving clauses ``where``,
  ``rename`` and ``sub``.
- ``nvl(x, y)`` when ``y`` can never be null.
- ``if c then a else b`` when both branches can never be null. A false or
  null condition selects the else branch, and an omitted ``else`` drops
  records instead of producing nulls, so then it is enough for ``a``.

Other operators are deliberately not propagated through: some (``/``,
``date(y, m, d)``) produce null from non-null inputs, so that needs an
explicit allowlist of its own.
"""

from __future__ import annotations

from dpmcore.dpm_xl.ast.nodes import (
    AST,
    AggregationOp,
    BinOp,
    CondExpr,
    Constant,
    CountSetOp,
    ParameterRef,
    ParExpr,
    RenameOp,
    Scalar,
    SubOp,
    UnaryOp,
    VarID,
    WhereClauseOp,
)
from dpmcore.dpm_xl.utils.operands_mapping import generate_operand_expression
from dpmcore.dpm_xl.utils.tokens import ISNULL, NOT, NVL, RANK

_PASS_THROUGH_CLAUSES = (WhereClauseOp, RenameOp, SubOp)

_CLAUSE_KEYWORDS: dict[type[AST], str] = {
    WhereClauseOp: "where",
    RenameOp: "rename",
    SubOp: "sub",
}


def never_null_reason(node: AST | None) -> str | None:
    """Return why *node* can never evaluate to null, or ``None``.

    Args:
        node: The AST node to inspect.

    Returns:
        A short human-readable reason when *node* is never null by
        definition, otherwise ``None``.
    """
    if node is None:
        return None
    if isinstance(node, ParExpr):
        return never_null_reason(node.expression)
    if isinstance(node, _PASS_THROUGH_CLAUSES):
        return never_null_reason(node.operand)
    if isinstance(node, (VarID, ParameterRef)):
        return _default_reason(node.default)
    if isinstance(node, (Constant, Scalar)):
        return _literal_reason(node)
    if isinstance(node, (AggregationOp, CountSetOp)):
        if node.op == "count":
            return "count never returns null"
        if node.op == RANK:
            return "rank never returns null"
        return None
    if isinstance(node, UnaryOp):
        if node.op == ISNULL:
            return "isnull returns only true or false"
        if node.op == NOT:
            return never_null_reason(node.operand)
        return None
    if isinstance(node, BinOp):
        if node.op == NVL and never_null_reason(node.right) is not None:
            return "the nvl fallback can never be null"
        return None
    if isinstance(node, CondExpr):
        return _conditional_reason(node)
    return None


def _default_reason(default: AST | None) -> str | None:
    """Reason for a selection whose ``default:`` rules a null out."""
    # ``default:null`` materialises as ``Constant(type_="Null")``.
    if default is None or getattr(default, "type", None) == "Null":
        return None
    value = getattr(default, "value", "?")
    return f"operand has a non-null default (default:{value})"


def _literal_reason(node: Constant | Scalar) -> str | None:
    """Reason for a literal; only the ``null`` literal can be null."""
    if isinstance(node, Constant) and node.type == "Null":
        return None
    return "operand is a non-null literal"


def _conditional_reason(node: CondExpr) -> str | None:
    """Reason for an ``if-then-else`` whose branches are never null."""
    if never_null_reason(node.then_expr) is None:
        return None
    if node.else_expr is None:
        return "the then branch can never be null and there is no else"
    if never_null_reason(node.else_expr) is None:
        return None
    return "both if-then-else branches can never be null"


def render_operand(node: AST) -> str:
    """Render *node* compactly for a warning message.

    Selections and literals are written out in full so two warnings in one
    expression stay distinguishable; the operators the never-null check
    looks through keep their own shape, and anything else is ``...``.

    Args:
        node: The AST node to render.

    Returns:
        A short DPM-XL-like rendering of *node*.
    """
    if isinstance(node, VarID):
        return generate_operand_expression(node)
    if isinstance(node, ParameterRef):
        return f"{{p_{node.code}, {node.param_type}}}"
    if isinstance(node, Constant):
        if node.type == "String":
            return f'"{node.value}"'
        if node.type == "Boolean":
            return "true" if node.value else "false"
        return str(node.value)
    if isinstance(node, Scalar):
        return f"[{node.item}]"
    if isinstance(node, ParExpr):
        return f"({render_operand(node.expression)})"
    if isinstance(node, _PASS_THROUGH_CLAUSES):
        keyword = _CLAUSE_KEYWORDS[type(node)]
        return f"{render_operand(node.operand)}[{keyword} ...]"
    if isinstance(node, (AggregationOp, CountSetOp)):
        return _render_aggregation(node)
    if isinstance(node, UnaryOp):
        inner = render_operand(node.operand)
        return f"not {inner}" if node.op == NOT else f"{node.op}({inner})"
    if isinstance(node, BinOp) and node.op == NVL:
        left = render_operand(node.left)
        return f"nvl({left}, {render_operand(node.right)})"
    if isinstance(node, CondExpr):
        return "if ... endif"
    return "..."


def _render_aggregation(node: AggregationOp | CountSetOp) -> str:
    """Render an aggregation with its grouping or analytic clause."""
    inner = render_operand(node.operand)
    if isinstance(node, AggregationOp):
        if node.grouping_clause is not None:
            components = ", ".join(node.grouping_clause.components)
            inner = f"{inner} group by {components}"
        elif node.analytic_clause is not None:
            inner = f"{inner} over (...)"
    return f"{node.op}({inner})"
