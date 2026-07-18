"""DPM model-validation service package.

Python port of the EBA ``check_modelling_rules_tidy`` stored
procedure: the full modelling-rule set evaluated against an in-memory
snapshot, with violations returned as data instead of being persisted
to a ``ModelViolations`` table. See
``specification/08-modelling-services.md``.
"""

from dpmcore.services.model_validation.registry import (
    Finding,
    Rule,
    RuleContext,
    rule,
)
from dpmcore.services.model_validation.release_context import (
    DRAFT_RELEASE_ID,
    ReleaseContext,
)
from dpmcore.services.model_validation.service import (
    ModelValidationService,
)
from dpmcore.services.model_validation.snapshot import ModelSnapshot
from dpmcore.services.model_validation.types import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    ModelValidationResult,
    ObjectRef,
    RuleInfo,
    Violation,
)

__all__ = [
    "DRAFT_RELEASE_ID",
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "Finding",
    "ModelSnapshot",
    "ModelValidationResult",
    "ModelValidationService",
    "ObjectRef",
    "ReleaseContext",
    "Rule",
    "RuleContext",
    "RuleInfo",
    "Violation",
    "rule",
]
