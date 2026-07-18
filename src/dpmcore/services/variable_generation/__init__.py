"""DPM variable-generation service package.

Compute-only Python port of the EBA ``variable_generation_tidy``
stored procedure: the complete variable-generation plan (variables,
versions, contexts, compound keys, filing indicators and per-cell
assignments) is returned as data — nothing is written to the
database. See ``specification/08-modelling-services.md`` section 5.
"""

from dpmcore.services.variable_generation.service import (
    VariableGenerationService,
)
from dpmcore.services.variable_generation.types import (
    Aspect,
    CellAssignment,
    CellOutcome,
    GenerationStatus,
    GenerationSummaryRow,
    HeaderDedup,
    ProposedCompoundKey,
    ProposedContext,
    ProposedFilingIndicator,
    ProposedVariable,
    ProposedVariableVersion,
    VariableGenerationResult,
)

__all__ = [
    "Aspect",
    "CellAssignment",
    "CellOutcome",
    "GenerationStatus",
    "GenerationSummaryRow",
    "HeaderDedup",
    "ProposedCompoundKey",
    "ProposedContext",
    "ProposedFilingIndicator",
    "ProposedVariable",
    "ProposedVariableVersion",
    "VariableGenerationResult",
    "VariableGenerationService",
]
