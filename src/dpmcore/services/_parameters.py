"""Shared helpers: merging parameter declarations across expressions.

Kept as module-level functions rather than service methods so both
:meth:`~dpmcore.services.semantic.SemanticService.validate` (applying the rule
across an expression and its precondition gate),
``ASTGeneratorService._accumulate_parameters`` (applying it across a whole
generated script) and the calculations export (applying it across a module's
calculations) share one implementation of the rule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterable

from dpmcore.errors import SemanticError

if TYPE_CHECKING:
    from dpmcore.services.semantic import ParameterInfo


def merge_parameters(
    accumulated: Dict[str, "ParameterInfo"],
    parameters: Iterable["ParameterInfo"],
) -> None:
    """Merge one expression's parameters into ``accumulated``, by code.

    A parameter is an execution-time input bound to a single value across
    everything it co-executes with, so its declared type is intrinsic and must
    stay consistent across every co-executing expression.

    Args:
        accumulated: Registry of ``{code: ParameterInfo}`` seen so far, mutated
            in place.
        parameters: The next expression's already-deduped parameters.

    Raises:
        SemanticError: ``3-8`` when a code is redeclared with another type,
            rather than silently letting one reference win.
    """
    for prm in parameters:
        prior = accumulated.get(prm.code)
        if prior is None:
            accumulated[prm.code] = prm
        elif prior.declared_type != prm.declared_type:
            raise SemanticError(
                "3-8",
                parameter=prm.code,
                type_1=prior.declared_type,
                type_2=prm.declared_type,
            )


def accumulate_ast_parameters(
    accumulated: Dict[str, "ParameterInfo"],
    node: Any,
) -> None:
    """Add every ``ParameterRef`` in a serialised AST to ``accumulated``.

    Reads the type off the serialised node so the registry holds the same
    canonical name the engine binds against. Used for a validation script's
    precondition gates and DB-built operations, and for the calculations
    export. A parameter redeclared with another type raises ``SemanticError``
    ``3-8`` through :func:`merge_parameters`. ``default`` is a per-reference
    fallback and stays on the node only: the registry is type-only.

    Args:
        accumulated: Registry of ``{code: ParameterInfo}`` seen so far,
            mutated in place.
        node: A serialised AST node, or a list of them.

    Raises:
        SemanticError: ``3-8`` when a code is read with two types.
    """
    # Imported here: semantic imports this module.
    from dpmcore.services.semantic import ParameterInfo

    if isinstance(node, dict):
        if node.get("class_name") == "ParameterRef":
            code = node.get("code")
            declared_type = node.get("param_type")
            if isinstance(code, str) and isinstance(declared_type, str):
                merge_parameters(
                    accumulated,
                    (
                        ParameterInfo(
                            code=code,
                            declared_type=declared_type,
                            default=None,
                        ),
                    ),
                )
        children: Iterable[Any] = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return
    for child in children:
        if isinstance(child, (dict, list)):
            accumulate_ast_parameters(accumulated, child)
