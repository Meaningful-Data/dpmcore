"""Shared helpers: the variable codes a precondition expression references.

Kept as module-level functions rather than service methods so both
:class:`~dpmcore.services.ast_generator.ASTGeneratorService` and
:class:`~dpmcore.services.scope_calculator.ScopeCalculatorService` can use
them without one service reaching into the private surface of the other.

Two functions, because scope calculation and payload emission need different
answers:

* :func:`extract_precondition_codes` — *every* code the gate mentions. What
  ``ASTGeneratorService`` has always used.
* :func:`required_precondition_codes` — only the codes a module **must**
  provide to evaluate the gate. Scope calculation needs this one: it counts
  each precondition code as an operand a module has to supply
  (``unique_operands_number`` in ``OperationScopeService``), so feeding it the
  flat set makes a disjunctive gate demand every alternative at once. On the
  real EBA dictionary that is not theoretical — of 965 persisted precondition
  expressions, 62 use ``or``, and the widest flattens to 20 filing indicators
  spanning frameworks, which resolves to a hard ``1-14``.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Set

logger = logging.getLogger(__name__)


def extract_precondition_codes(ast: Any) -> List[str]:
    """Return the variable codes referenced by a precondition AST.

    Walks the AST collecting:
    - ``PreconditionItem.variable_code``
    - ``VarRef.variable``

    Either kind unambiguously identifies a precondition variable for
    scope-calculation purposes. Deduplicated, first-seen order preserved.
    Classifying those codes into genuine filing indicators (the only ones
    that constrain module scope) happens downstream, in
    ``OperationScopeService.calculate_operation_scope``.
    """
    from dpmcore.dpm_xl.ast.template import ASTTemplate

    codes: List[str] = []

    class _Extractor(ASTTemplate):
        def visit_PreconditionItem(self, node: Any) -> None:
            vc = getattr(node, "variable_code", None)
            if vc and vc not in codes:
                codes.append(vc)

        def visit_VarRef(self, node: Any) -> None:
            v = getattr(node, "variable", None)
            if v and v not in codes:
                codes.append(v)

    try:
        _Extractor().visit(ast)
    except Exception:
        logger.exception(
            "Failed to extract precondition codes; continuing without them.",
        )
        return []
    return codes


def _code_of(node: Any) -> Optional[str]:
    """Return the variable code a leaf precondition node names, if any."""
    for attr in ("variable_code", "variable"):
        value = getattr(node, attr, None)
        if value:
            return str(value)
    return None


def _mandatory(node: Any) -> Set[str]:
    """Codes that must be **true** for *node* to hold.

    The criterion is "must be true", not "must be readable". That is what
    scope needs: a module hosts the operation only if the gate can be true
    there, and ``precondition_items`` excludes any module that does not carry
    the code. Requiring a code the gate needs to be *false* would exclude
    exactly the modules the rule targets.

    So ``or``/``xor`` intersects its operands — either side alone can satisfy
    the gate, so neither is individually mandatory — and ``not`` contributes
    nothing, since its operand has to be false. Those are one rule, not two:
    ``{v_A} or {v_B}`` yields ``[]`` for the same reason ``not {v_A}`` does.
    Consequently ``not {v_A} and {v_B}`` yields only ``B`` — ``A`` is dropped
    on purpose, because the gate is *for* the modules that do not file ``A``.

    Everything else — ``and``, comparisons, arithmetic, function calls —
    unions its children, since a code inside one genuinely has to hold. That
    makes the union the default and the only special cases the two that
    weaken a requirement.
    """
    # Deferred like the ``ASTTemplate`` import above, so this module pulls in
    # nothing from the engine at import time.
    from dpmcore.dpm_xl.utils.tokens import NOT, OR, XOR

    code = _code_of(node)
    if code is not None:
        return {code}

    op = getattr(node, "op", None)
    left = getattr(node, "left", None)
    right = getattr(node, "right", None)

    if op == NOT:
        return set()
    if op in (OR, XOR) and left is not None and right is not None:
        return _mandatory(left) & _mandatory(right)

    # Union over every child: Start.children, ParExpr.expression, BinOp's
    # left/right, UnaryOp.operand, and any other node's AST-valued attributes.
    required: Set[str] = set()
    for child in _children(node):
        required |= _mandatory(child)
    return required


def _children(node: Any) -> List[Any]:
    """AST-valued attributes of *node*, flattening lists."""
    from dpmcore.dpm_xl.ast.nodes import AST

    found: List[Any] = []
    if not isinstance(node, AST):
        return found
    for value in vars(node).values():
        if isinstance(value, AST):
            found.append(value)
        elif isinstance(value, list):
            found.extend(item for item in value if isinstance(item, AST))
    return found


def required_precondition_codes(ast: Any) -> List[str]:
    """Return the codes a module must provide to evaluate a precondition AST.

    Scope calculation counts every precondition code as an operand the module
    has to supply, so only codes that must be **true** for the gate to hold
    may be passed to it (see :func:`_mandatory`). A disjunctive gate such as
    ``{v_A} or {v_B}`` requires neither code specifically, and returns ``[]``
    — the gate then constrains scope exactly as much as it should, which is
    not at all. A negated one behaves the same way: ``not {v_A}`` returns
    ``[]``, and ``not {v_A} and {v_B}`` returns only ``B``, because a module
    that never files ``A`` is precisely where such a gate is meant to fire.

    Order follows :func:`extract_precondition_codes` (first-seen), so the
    result is deterministic. Returns ``[]`` on any walk failure, matching
    :func:`extract_precondition_codes`: under-approximating can only fall back
    to the pre-existing behaviour of ignoring the gate for scoping, never
    invent a constraint.
    """
    try:
        required = _mandatory(ast)
    except Exception:
        logger.exception(
            "Failed to derive required precondition codes; "
            "continuing without them.",
        )
        return []
    return [c for c in extract_precondition_codes(ast) if c in required]
