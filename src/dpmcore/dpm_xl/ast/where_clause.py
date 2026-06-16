from __future__ import annotations

from dpmcore.dpm_xl.ast.nodes import (
    AST,
    BinOp,
    Constant,
    Dimension,
    ParExpr,
    Scalar,
)
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.utils import tokens


class WhereClauseChecker(ASTTemplate):
    def __init__(self) -> None:
        super().__init__()
        self.key_components: list[str] = []

    def visit_Dimension(self, node: Dimension) -> None:
        self.key_components.append(node.dimension_code)


def _equality_value(node: AST) -> str | None:
    """Return the literal value of a where-condition equality operand.

    Only operands that denote a single concrete value are recognised: an
    item reference (``Scalar``) or a literal (``Constant``). Anything else
    (a dimension, a sub-expression, ...) returns ``None`` so the equality
    is not treated as a pin.

    Args:
        node: One side of an ``=`` condition.

    Returns:
        The value as a string, or ``None`` when it is not a literal value.
    """
    if isinstance(node, Scalar):
        return node.item
    if isinstance(node, Constant):
        return str(node.value)
    return None


def _equality_pin(node: BinOp) -> tuple[str, str] | None:
    """Return ``(dimension_code, value)`` for a ``dimension = value`` node.

    The dimension may appear on either side of the ``=``. Returns ``None``
    when the equality is not between exactly one ``Dimension`` and one
    literal value (e.g. ``value = value`` or ``dimension = dimension``).

    Args:
        node: An ``=`` ``BinOp`` from a where condition.

    Returns:
        The pinned dimension code and value, or ``None``.
    """
    if isinstance(node.left, Dimension):
        value = _equality_value(node.right)
        if value is not None:
            return node.left.dimension_code, value
    if isinstance(node.right, Dimension):
        value = _equality_value(node.left)
        if value is not None:
            return node.right.dimension_code, value
    return None


def _accumulate_pins(
    node: AST, pins: dict[str, str], ambiguous: set[str]
) -> None:
    """Collect ``dimension = value`` pins guaranteed by ``node``.

    Walks the conjunctive (``and``) skeleton of a where condition. Each
    literal equality contributes a pin; a dimension pinned to two different
    values within the same condition is recorded as ``ambiguous`` and later
    dropped. Disjunctions (``or``) and every other shape contribute nothing,
    so the result only ever lists values that *must* hold for every record.

    Args:
        node: The condition (sub-)tree to inspect.
        pins: Accumulator of dimension -> pinned value.
        ambiguous: Accumulator of dimensions seen with conflicting values.
    """
    if isinstance(node, ParExpr):
        _accumulate_pins(node.expression, pins, ambiguous)
        return
    if not isinstance(node, BinOp):
        return
    if node.op == tokens.AND:
        _accumulate_pins(node.left, pins, ambiguous)
        _accumulate_pins(node.right, pins, ambiguous)
        return
    if node.op == tokens.EQ:
        pin = _equality_pin(node)
        if pin is not None:
            dim, value = pin
            if dim in pins and pins[dim] != value:
                ambiguous.add(dim)
            else:
                pins[dim] = value


def collect_where_equality_pins(condition: AST) -> dict[str, str]:
    """Map each dimension a where condition pins to a single literal value.

    Only top-level ``dimension = value`` equalities (optionally joined by
    ``and`` or wrapped in parentheses) are reported. Any other shape -- an
    ``or``, a ``!=``, a comparison, an ``in`` set, or a dimension pinned to
    two conflicting values -- contributes no pin. The conservative result
    lets a binary operator detect a guaranteed-empty inner join (two
    operands pinning a shared key to different values) without false
    positives.

    Args:
        condition: The where-clause condition AST.

    Returns:
        Dimension code -> the single value every record must take for it.
    """
    pins: dict[str, str] = {}
    ambiguous: set[str] = set()
    _accumulate_pins(condition, pins, ambiguous)
    for dim in ambiguous:
        pins.pop(dim, None)
    return pins


def merge_where_constraints(
    base: dict[str, str], new: dict[str, str]
) -> dict[str, str]:
    """Combine the pins of a nested operand with those of an outer where.

    Both sets of pins must hold simultaneously, so a dimension pinned to two
    different values (e.g. ``[where qA = X][where qA = Y]``) is dropped
    rather than picking a winner -- the operand is then treated as having no
    reliable pin for it.

    Args:
        base: Pins already carried by the inner operand.
        new: Pins added by the enclosing where clause.

    Returns:
        The merged pin mapping.
    """
    merged = dict(base)
    for dim, value in new.items():
        if dim in merged and merged[dim] != value:
            del merged[dim]
        else:
            merged[dim] = value
    return merged
