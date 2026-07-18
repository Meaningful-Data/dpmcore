"""Internal working state of a variable-generation run.

Mutable, plan-internal structures shared by the generation stages:
the ``#cellmodelling`` working records, the temp-id allocator and the
accumulated proposals. Nothing here is part of the public result —
see :mod:`dpmcore.services.variable_generation.types` for that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from dpmcore.services.variable_generation.types import (
    Aspect,
    OptionalRef,
    ProposedCompoundKey,
    ProposedContext,
    ProposedFilingIndicator,
    ProposedVariable,
    ProposedVariableVersion,
    Ref,
)


class TempIdAllocator:
    """Deterministic per-prefix counters for plan-local temp ids."""

    def __init__(self) -> None:
        """Start every counter at zero."""
        self._counters: Dict[str, int] = {}

    def next(self, prefix: str) -> str:
        """Return the next id for ``prefix``, e.g. ``"var:3"``."""
        value = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = value
        return f"{prefix}:{value}"


def ref_sort_key(ref: Ref) -> Tuple[int, int, str]:
    """Sort key for mixed int/temp-id references (ints first)."""
    if isinstance(ref, int):
        return (0, ref, "")
    return (1, 0, ref)


@dataclass
class CellRecord:
    """One ``#cellmodelling`` row: a (module, table version, cell).

    Field names mirror the SQL temp-table columns. ``new_*`` fields
    may hold temp ids for objects proposed by the plan.
    """

    module_vid: int
    module_code: Optional[str]
    table_vid: int
    table_code: Optional[str]
    cell_id: int
    cell_code: Optional[str]
    is_void: bool
    tv_start: Optional[int]
    mv_start: Optional[int]
    vv_old_end: Optional[int] = None
    old_variable_id: Optional[int] = None
    old_variable_vid: Optional[int] = None
    old_context_id: Optional[int] = None
    old_property_id: Optional[int] = None
    old_key_id: Optional[int] = None
    new_context_id: OptionalRef = None
    new_property_id: Optional[int] = None
    new_key_id: OptionalRef = None
    is_new_cell: bool = False
    is_new_property_datatype: bool = False
    is_new_key: bool = False
    outcome_id: Optional[str] = None
    outcome_vid: Optional[str] = None
    new_variable_ref: OptionalRef = None
    new_vvid_ref: OptionalRef = None
    report_msg: Optional[str] = None

    @property
    def old_aspect(self) -> Aspect:
        """Aspect before generation (SQL ``OldAspect`` components)."""
        return Aspect(
            self.old_key_id, self.old_property_id, self.old_context_id
        )

    @property
    def new_aspect(self) -> Aspect:
        """Aspect after generation (SQL ``NewAspect`` components)."""
        return Aspect(
            self.new_key_id, self.new_property_id, self.new_context_id
        )

    @property
    def old_signature(self) -> str:
        """SQL ``OldAspect`` string."""
        return self.old_aspect.signature

    @property
    def new_signature(self) -> str:
        """SQL ``NewAspect`` string."""
        return self.new_aspect.signature


@dataclass
class GenerationState:
    """Proposals and mappings accumulated across generation stages.

    Attributes:
        release_dates: ``release_id -> Release.Date`` map, used by the
            reassignment step's "most recent release" ordering.
        ids: Temp-id allocator shared by all stages.
        key_variables: Proposed key variables, in property order.
        key_variable_by_property: property id -> active key
            VariableVersion (existing vid or proposed temp id).
        header_key_refs: header_vid -> resolved key variable version
            for header versions starting in the current release.
        compound_keys: Proposed compound keys, in signature order.
        key_by_table_vid: table_vid -> compound key (existing id or
            temp id) for current-release table versions.
        filing_indicators: Proposed filing-indicator bundles.
        fi_variables: Proposed filing-indicator variables.
        fi_contexts: Contexts proposed for filing indicators.
        cell_contexts: Contexts proposed for cell aspects.
        new_version_versions: NEW_VERSION variable versions proposed
            on existing variables (SQL outcome block 2.1, list a).
        fact_variables: Brand-new fact variables (SQL list b "NEW").
    """

    release_dates: Dict[int, Optional[date]] = field(
        default_factory=dict
    )
    ids: TempIdAllocator = field(default_factory=TempIdAllocator)
    key_variables: List[ProposedVariable] = field(default_factory=list)
    key_variable_by_property: Dict[int, Ref] = field(
        default_factory=dict
    )
    header_key_refs: Dict[int, Ref] = field(default_factory=dict)
    compound_keys: List[ProposedCompoundKey] = field(
        default_factory=list
    )
    key_by_table_vid: Dict[int, Ref] = field(default_factory=dict)
    filing_indicators: List[ProposedFilingIndicator] = field(
        default_factory=list
    )
    fi_variables: List[ProposedVariable] = field(default_factory=list)
    fi_contexts: List[ProposedContext] = field(default_factory=list)
    cell_contexts: List[ProposedContext] = field(default_factory=list)
    new_version_versions: List[ProposedVariableVersion] = field(
        default_factory=list
    )
    fact_variables: List[ProposedVariable] = field(default_factory=list)

    def all_variables(self) -> Tuple[ProposedVariable, ...]:
        """All proposed variables, in plan-construction order."""
        return tuple(
            self.key_variables + self.fi_variables + self.fact_variables
        )

    def all_variable_versions(
        self,
    ) -> Tuple[ProposedVariableVersion, ...]:
        """All proposed variable versions, in plan order."""
        versions: List[ProposedVariableVersion] = []
        for variable in self.key_variables + self.fi_variables:
            versions.extend(variable.versions)
        versions.extend(self.new_version_versions)
        for variable in self.fact_variables:
            versions.extend(variable.versions)
        return tuple(versions)

    def all_contexts(self) -> Tuple[ProposedContext, ...]:
        """All proposed contexts, in plan-construction order."""
        return tuple(self.fi_contexts + self.cell_contexts)
