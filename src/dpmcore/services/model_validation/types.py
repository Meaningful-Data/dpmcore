"""Result types for the model-validation service.

These are the JSON-serialisable objects returned by
:class:`~dpmcore.services.model_validation.service.ModelValidationService`.
They replace the ``ModelViolations`` result table used by the original
``check_modelling_rules_tidy`` stored procedure: nothing is persisted,
callers consume the returned dataclasses (or their ``to_dict()`` form).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


@dataclass(frozen=True)
class ObjectRef:
    """Reference to a DPM model object involved in a violation.

    Attributes:
        kind: Object kind, e.g. ``"table_version"``, ``"header"``,
            ``"item"``, ``"cell"``.
        id: Primary identifier (a ``*ID``/``*VID`` integer, or a string
            key for composite identities).
        code: Business code of the object, where one exists.
        name: Human-readable name, where one exists.
    """

    kind: str
    id: Union[int, str, None] = None
    code: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "kind": self.kind,
            "id": self.id,
            "code": self.code,
            "name": self.name,
        }


@dataclass(frozen=True)
class Violation:
    """A single broken modelling rule.

    Attributes:
        rule_id: Unique rule identifier, e.g. ``"1_5"`` or ``"3_5a"``
            (letter suffixes disambiguate SQL codes that were reused
            for distinct checks).
        legacy_code: Original ``ViolationCode`` used by the SQL stored
            procedure, kept for traceability, e.g. ``"3_5"``.
        message: Human-readable description of the violation.
        severity: ``"error"`` (blocking) or ``"warning"``.
        objects: The offending object first, then any secondary
            objects (e.g. the other cell of a duplicate pair).
    """

    rule_id: str
    legacy_code: str
    message: str
    severity: str
    objects: Tuple[ObjectRef, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "rule_id": self.rule_id,
            "legacy_code": self.legacy_code,
            "message": self.message,
            "severity": self.severity,
            "objects": [o.to_dict() for o in self.objects],
        }


@dataclass(frozen=True)
class RuleInfo:
    """Catalogue entry describing a registered validation rule.

    Attributes:
        rule_id: Unique rule identifier.
        legacy_code: Original SQL ``ViolationCode``.
        family: Rule family, e.g. ``"lifecycle"`` or ``"glossary"``.
        severity: Severity of violations produced by this rule.
        description: What the rule checks.
    """

    rule_id: str
    legacy_code: str
    family: str
    severity: str
    description: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "rule_id": self.rule_id,
            "legacy_code": self.legacy_code,
            "family": self.family,
            "severity": self.severity,
            "description": self.description,
        }


@dataclass(frozen=True)
class ModelValidationResult:
    """Outcome of a full model-validation run.

    Attributes:
        is_valid: True when no error-severity violation was found.
        release_id: The release the model was validated against.
        release_code: Code of that release, when available.
        violations: All violations found, ordered by rule then object.
        error_count: Number of error-severity violations.
        warning_count: Number of warning-severity violations.
        rules_run: Number of rules that were evaluated.
        elapsed_ms: Wall-clock validation time in milliseconds.
    """

    is_valid: bool
    release_id: int
    release_code: Optional[str]
    violations: Tuple[Violation, ...]
    error_count: int
    warning_count: int
    rules_run: int
    elapsed_ms: float

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "is_valid": self.is_valid,
            "release_id": self.release_id,
            "release_code": self.release_code,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "rules_run": self.rules_run,
            "elapsed_ms": self.elapsed_ms,
            "violations": [v.to_dict() for v in self.violations],
        }

    def by_rule(self) -> Dict[str, List[Violation]]:
        """Group the violations by ``rule_id``."""
        grouped: Dict[str, List[Violation]] = {}
        for violation in self.violations:
            grouped.setdefault(violation.rule_id, []).append(violation)
        return grouped
