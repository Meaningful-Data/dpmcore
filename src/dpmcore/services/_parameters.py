"""Shared helper: merging parameter declarations across expressions.

Kept as a module-level function rather than a service method so both
:meth:`~dpmcore.services.semantic.SemanticService.validate` (applying the rule
across an expression and its precondition gate) and
``ASTGeneratorService._accumulate_parameters`` (applying it across a whole
generated script) share one implementation of the rule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable

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
