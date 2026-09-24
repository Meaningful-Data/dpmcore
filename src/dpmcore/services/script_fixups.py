"""Known EBA source-data errors ported from mdpm's ``mdm-fix-json-values.py``.

These are not generation bugs — dpmcore and mdpm both reproduce them
faithfully because the underlying ``OperationNode``/``OperandReference``
data in the DPM database itself is wrong for these specific
validations (an empty/zero default that should be absent, a literal
typed ``Integer`` where the engine expects ``Boolean``, an interval
flag that should be false). Confirmed against a real DB: every
datapoint listed here reproduces the same wrong value in dpmcore's own
output. This is a stopgap, not a source-side fix: EBA does not amend
already-published releases retroactively, so these values are expected
to stay wrong indefinitely for the affected releases, not to
self-correct over time. Because of that, ``fix-script`` must be run as
a required step after every ``export-script`` generation, not an
optional cleanup — a freshly generated script carries these same
errors again until patched.

Each rule matches its target by structural pattern (an ``OperandType``
plus a value predicate, e.g. "a ``VarID`` for this datapoint" or "a
``BinOp`` whose ``left`` is that ``VarID``"), not by a fixed position
in the tree — mdpm's own script reads a couple of the more elaborate
cases (``v6512_m``/``v6513_m``/``v12458_m``/``v12459_m``/``v6519_c``)
off fixed dict-key offsets, which assumes mdpm's own AST shape; dpmcore
serialises the same expressions into a differently-shaped tree (see
``dpm_xl/utils/serialization.py``), so those cases are re-expressed
here as the same underlying pattern instead of ported verbatim.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, FrozenSet, List, Tuple

# op_code -> (datapoints whose VarID.default is wrong, the wrong value).
_WRONG_DEFAULTS: Dict[str, Tuple[FrozenSet[int], Any]] = {
    "v8713_m": (frozenset({55299, 5486642}), ""),
    "v8787_m": (frozenset({109498}), ""),
    "v8803_m": (frozenset({487511}), 0),
    "v8804_m": (frozenset({487136}), 0),
    "v8805_m": (frozenset({483167, 487321}), 0),
    "v8825_m": (frozenset({3291608, 3291609}), 0),
    "v11335_m": (frozenset({5486769}), ""),
    "v11336_m": (frozenset({5486769}), ""),
    "v11337_m": (frozenset({5486769}), ""),
    "v11338_m": (frozenset({5486769}), ""),
    "v12456_m": (frozenset({470572}), ""),
    "v12457_m": (frozenset({470572}), ""),
    "v12458_m": (frozenset({470572}), ""),
    "v12459_m": (frozenset({470572}), ""),
    "v6460_m": (frozenset({410216, 418116, 5487087, 5487103}), ""),
    "v6467_m": (frozenset({428423, 428426, 5487098, 5487105}), ""),
    "v6468_m": (frozenset({423749, 428426, 5487086, 5487105}), ""),
    "v6512_m": (frozenset({418132}), ""),
    "v6513_m": (frozenset({418133}), ""),
    "v12723_m": (
        frozenset(
            {
                470662,
                470813,
                470814,
                470815,
                470816,
                470817,
                471076,
                471077,
                471078,
                471079,
                471080,
                471218,
                471219,
                471220,
                471221,
                471222,
                471266,
                471272,
                471278,
                471284,
                471290,
                471291,
                471292,
                471293,
                471294,
                471295,
                471296,
                471297,
                471298,
                471299,
                471300,
                471301,
                471302,
                471303,
                471304,
                471305,
                471306,
                471307,
                471308,
                471309,
                471310,
                471311,
                471312,
                471313,
                471314,
                471315,
                471316,
                471317,
                471318,
                471319,
                471320,
                471892,
                471893,
                471894,
                471895,
                471896,
                471948,
                471949,
                471950,
                471951,
                471952,
                471953,
                471954,
                471955,
                471956,
                471957,
                472090,
                472091,
                472092,
                472093,
                472094,
                472142,
                472143,
                472144,
                472145,
                472146,
                472194,
                472195,
                472196,
                472197,
                472198,
            }
        ),
        "",
    ),
    "v12736_m": (
        frozenset(
            {
                470662,
                470813,
                470815,
                470817,
                471076,
                471078,
                471080,
                471218,
                471220,
                471222,
                471266,
                471272,
                471278,
                471284,
                471290,
                471291,
                471292,
                471293,
                471294,
                471295,
                471296,
                471302,
                471303,
                471304,
                471305,
                471306,
                471307,
                471308,
                471314,
                471315,
                471316,
                471317,
                471318,
                471319,
                471320,
                471892,
                471894,
                471896,
                471948,
                471949,
                471952,
                471953,
                471956,
                471957,
                472090,
                472092,
                472094,
                472142,
                472144,
                472146,
                472194,
                472196,
                472198,
            }
        ),
        "",
    ),
}

# op_code -> predicate deciding whether a Constant node found anywhere
# in that operation's ast should be flipped to Boolean True.
_CONSTANT_TRUE_FIXES: Dict[str, Callable[[Dict[str, Any]], bool]] = {
    "v7364_m": lambda node: True,
    "v8713_m": lambda node: node.get("type_") == "Integer",
    "v8787_m": lambda node: True,
    "v10726_m": lambda node: node.get("value") == 1,
    "v12456_m": lambda node: node.get("value") == 1,
    "v12457_m": lambda node: node.get("value") == 1,
}

# op_code -> datapoint: a BinOp whose left is a VarID for this
# datapoint has its right (a Constant) flipped to Boolean False.
_BINOP_SIBLING_FALSE_FIXES: Dict[str, int] = {
    "v6512_m": 418132,
    "v6513_m": 418133,
    "v12458_m": 470572,
    "v12459_m": 470572,
}

# Operations whose every VarID.interval must be forced to False.
_INTERVAL_FALSE_OPS = frozenset({"v7339_m"})

# Operations whose CondExpr chain's then_expr/else_expr Constants need
# boolean-literal fixing (see _flip_condexpr_chain).
_CONDEXPR_CHAIN_OPS = frozenset({"v6519_c"})


def fix_operation_ast(op_code: str, ast: Any) -> bool:
    """Apply every known fix for *op_code* to *ast* in place.

    Returns whether anything changed, so a caller can skip rewriting
    an operation (or a whole file) untouched.
    """
    changed = False
    if op_code in _WRONG_DEFAULTS:
        datapoints, wrong_value = _WRONG_DEFAULTS[op_code]
        changed |= _strip_wrong_defaults(ast, datapoints, wrong_value)
    if op_code in _CONSTANT_TRUE_FIXES:
        changed |= _flip_constants_true(ast, _CONSTANT_TRUE_FIXES[op_code])
    if op_code in _BINOP_SIBLING_FALSE_FIXES:
        changed |= _flip_binop_sibling_false(
            ast, _BINOP_SIBLING_FALSE_FIXES[op_code]
        )
    if op_code in _INTERVAL_FALSE_OPS:
        changed |= _force_interval_false(ast)
    if op_code in _CONDEXPR_CHAIN_OPS:
        changed |= _flip_condexpr_chain(ast)
    return changed


def fix_module_operations(operations: Dict[str, Dict[str, Any]]) -> List[str]:
    """Apply :func:`fix_operation_ast` to every operation with a known fix.

    Returns the codes actually changed.
    """
    changed_codes: List[str] = []
    for code, entry in operations.items():
        if fix_operation_ast(code, entry.get("ast")):
            changed_codes.append(code)
    return changed_codes


def _strip_wrong_defaults(
    node: Any, datapoints: FrozenSet[int], wrong_value: Any
) -> bool:
    changed = False
    if isinstance(node, dict):
        if node.get("class_name") == "VarID":
            data = node.get("data") or []
            dp = data[0].get("datapoint") if data else None
            if dp in datapoints and node.get("default") == wrong_value:
                del node["default"]
                changed = True
        else:
            for value in node.values():
                changed |= _strip_wrong_defaults(
                    value, datapoints, wrong_value
                )
    elif isinstance(node, list):
        for item in node:
            changed |= _strip_wrong_defaults(item, datapoints, wrong_value)
    return changed


def _flip_constants_true(
    node: Any, predicate: Callable[[Dict[str, Any]], bool]
) -> bool:
    changed = False
    if isinstance(node, dict):
        if node.get("class_name") == "Constant":
            # The predicates below key off ``value``, and a Boolean
            # ``True`` already satisfies e.g. ``value == 1`` (bool is
            # an int subtype) — only report a change when the node
            # wasn't already the target shape.
            if predicate(node) and (
                node.get("type_") != "Boolean" or node.get("value") is not True
            ):
                node["type_"] = "Boolean"
                node["value"] = True
                changed = True
        else:
            for value in node.values():
                changed |= _flip_constants_true(value, predicate)
    elif isinstance(node, list):
        for item in node:
            changed |= _flip_constants_true(item, predicate)
    return changed


def _flip_binop_sibling_false(node: Any, datapoint: int) -> bool:
    changed = False
    if isinstance(node, dict):
        if node.get("class_name") == "BinOp":
            left = node.get("left")
            if isinstance(left, dict) and left.get("class_name") == "VarID":
                data = left.get("data") or []
                dp = data[0].get("datapoint") if data else None
                if dp == datapoint:
                    right = node.get("right")
                    if (
                        isinstance(right, dict)
                        and right.get("class_name") == "Constant"
                        and (
                            right.get("type_") != "Boolean"
                            or right.get("value") is not False
                        )
                    ):
                        right["type_"] = "Boolean"
                        right["value"] = False
                        changed = True
        for value in node.values():
            changed |= _flip_binop_sibling_false(value, datapoint)
    elif isinstance(node, list):
        for item in node:
            changed |= _flip_binop_sibling_false(item, datapoint)
    return changed


def _force_interval_false(node: Any) -> bool:
    changed = False
    if isinstance(node, dict):
        if node.get("class_name") == "VarID":
            if node.get("interval") is not False:
                node["interval"] = False
                changed = True
        else:
            for value in node.values():
                changed |= _force_interval_false(value)
    elif isinstance(node, list):
        for item in node:
            changed |= _force_interval_false(item)
    return changed


def _flip_boolean_constant(constant: Any, target: bool) -> bool:
    """Flip a ``Constant`` node to ``Boolean``/*target*, if not already."""
    if not isinstance(constant, dict):
        return False
    if constant.get("type_") == "Boolean" and constant.get("value") is target:
        return False
    constant["type_"] = "Boolean"
    constant["value"] = target
    return True


def _flip_condexpr_else(else_expr: Any) -> bool:
    """Flip an ``else_expr``'s ``Constant``, or recurse into its chain."""
    constant = else_expr.get("expression")
    if isinstance(constant, dict) and constant.get("class_name") == "Constant":
        return _flip_boolean_constant(constant, False)
    return _flip_condexpr_chain(else_expr)


def _flip_condexpr_chain(node: Any) -> bool:
    """Fix a ``CondExpr`` chain's boolean literals (``v6519_c``).

    Every ``then_expr`` unwraps to a bare ``Constant`` — flipped to
    ``True`` unconditionally. An ``else_expr`` either unwraps to a
    bare ``Constant`` too (the chain's final branch — flipped to
    ``False``) or to another nested ``CondExpr`` (recursed into
    instead, repeating the same rule one level down).
    """
    changed = False
    if isinstance(node, dict):
        then_expr = node.get("then_expr")
        if isinstance(then_expr, dict):
            changed |= _flip_boolean_constant(
                then_expr.get("expression"), True
            )

        else_expr = node.get("else_expr")
        if isinstance(else_expr, dict):
            changed |= _flip_condexpr_else(else_expr)

        for key, value in node.items():
            if key not in ("then_expr", "else_expr"):
                changed |= _flip_condexpr_chain(value)
    elif isinstance(node, list):
        for item in node:
            changed |= _flip_condexpr_chain(item)
    return changed
