"""Rule registry and evaluation context for model validation.

Each validation rule is a pure function decorated with :func:`rule`.
It receives a :class:`RuleContext` (snapshot + release semantics) and
yields :class:`Finding` objects; the registry stamps rule metadata onto
each finding to produce :class:`~dpmcore.services.model_validation
.types.Violation` values. Rules must not depend on each other's
output and must not mutate the snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
)

from dpmcore.services.model_validation.release_context import (
    ReleaseContext,
)
from dpmcore.services.model_validation.snapshot import ModelSnapshot
from dpmcore.services.model_validation.types import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    ObjectRef,
    RuleInfo,
    Violation,
)


@dataclass(frozen=True)
class Finding:
    """A single occurrence reported by a rule.

    Attributes:
        objects: The offending object first, then secondary objects.
        message: Violation message; when None the rule description is
            used (static-message rules never need to repeat it).
    """

    objects: Tuple[ObjectRef, ...]
    message: Optional[str] = None


@dataclass(frozen=True)
class RuleContext:
    """Everything a rule needs to evaluate.

    Attributes:
        snapshot: In-memory model snapshot.
        release: Resolved release semantics.
    """

    snapshot: ModelSnapshot
    release: ReleaseContext


RuleFn = Callable[[RuleContext], Iterable[Finding]]


@dataclass(frozen=True)
class Rule:
    """A registered validation rule.

    Attributes:
        rule_id: Unique identifier, e.g. ``"1_5"`` or ``"3_5a"``.
        legacy_code: Original SQL ``ViolationCode``.
        family: Rule family name (module the rule lives in).
        severity: Severity of violations this rule produces.
        description: One-line description of the check.
        fn: The rule function.
    """

    rule_id: str
    legacy_code: str
    family: str
    severity: str
    description: str
    fn: RuleFn

    def info(self) -> RuleInfo:
        """Return the catalogue entry for this rule."""
        return RuleInfo(
            rule_id=self.rule_id,
            legacy_code=self.legacy_code,
            family=self.family,
            severity=self.severity,
            description=self.description,
        )


#: Global registry, populated at import time by the ``rules`` modules.
REGISTRY: Dict[str, Rule] = {}

_VALID_SEVERITIES = (SEVERITY_ERROR, SEVERITY_WARNING)


def rule(
    rule_id: str,
    legacy_code: str,
    family: str,
    severity: str,
    description: str,
) -> Callable[[RuleFn], RuleFn]:
    """Register a validation rule.

    Args:
        rule_id: Unique rule identifier.
        legacy_code: Original SQL ``ViolationCode``.
        family: Rule family, e.g. ``"lifecycle"``.
        severity: ``"error"`` or ``"warning"``.
        description: One-line description of the check.

    Returns:
        A decorator that registers the function and returns it
        unchanged.

    Raises:
        ValueError: If ``rule_id`` is already registered or the
            severity is unknown.
    """
    if severity not in _VALID_SEVERITIES:
        raise ValueError(f"Unknown severity: {severity!r}")

    def decorator(fn: RuleFn) -> RuleFn:
        if rule_id in REGISTRY:
            raise ValueError(f"Duplicate rule id: {rule_id!r}")
        REGISTRY[rule_id] = Rule(
            rule_id=rule_id,
            legacy_code=legacy_code,
            family=family,
            severity=severity,
            description=description,
            fn=fn,
        )
        return fn

    return decorator


def rule_sort_key(rule_id: str) -> Tuple[int, int, str]:
    """Natural sort key for rule ids: family, number, suffix.

    ``"1_10"`` sorts after ``"1_2"``; ``"3_5a"`` before ``"3_5b"``.
    """
    family_part, _, rest = rule_id.partition("_")
    digits = "".join(ch for ch in rest if ch.isdigit())
    suffix = rest[len(digits) :]
    return (int(family_part), int(digits), suffix)


def evaluate(
    ctx: RuleContext,
    rule_ids: Optional[Sequence[str]] = None,
    include_warnings: bool = True,
) -> Tuple[List[Violation], int]:
    """Evaluate registered rules and collect violations.

    Args:
        ctx: Evaluation context.
        rule_ids: Restrict evaluation to these rule ids; None runs
            all registered rules.
        include_warnings: When False, warning-severity rules are
            skipped entirely.

    Returns:
        A pair ``(violations, rules_run)``. Violations are ordered by
        rule id (natural order) and then by the order the rule
        reported them.

    Raises:
        dpmcore.errors.NotFound: If a requested rule id is unknown.
    """
    from dpmcore.errors import NotFound

    if rule_ids is None:
        selected = list(REGISTRY.values())
    else:
        missing = [rid for rid in rule_ids if rid not in REGISTRY]
        if missing:
            raise NotFound(f"Unknown rule ids: {', '.join(missing)}")
        selected = [REGISTRY[rid] for rid in rule_ids]

    if not include_warnings:
        selected = [
            r for r in selected if r.severity != SEVERITY_WARNING
        ]

    selected.sort(key=lambda r: rule_sort_key(r.rule_id))

    violations: List[Violation] = []
    for registered in selected:
        violations.extend(
            Violation(
                rule_id=registered.rule_id,
                legacy_code=registered.legacy_code,
                message=finding.message or registered.description,
                severity=registered.severity,
                objects=finding.objects,
            )
            for finding in registered.fn(ctx)
        )
    return violations, len(selected)


def all_rule_infos() -> List[RuleInfo]:
    """Return catalogue entries for every registered rule, sorted."""
    ordered = sorted(
        REGISTRY.values(), key=lambda r: rule_sort_key(r.rule_id)
    )
    return [r.info() for r in ordered]
