"""Result types for the variable-generation service.

JSON-serialisable, frozen dataclasses describing the *generation plan*
computed by
:class:`~dpmcore.services.variable_generation.service
.VariableGenerationService`. They replace the tables the original
``variable_generation_tidy`` stored procedure wrote to
(``Variable``/``VariableVersion`` inserts, ``VarGeneration_Detail``,
``VarGeneration_Summary``, ``Aux_CellStatus``): nothing is persisted.

Identifier strategy (spec section 5.5): objects the SQL would have
inserted receive deterministic plan-local temp ids (``"var:1"``,
``"vv:3"``, ``"ctx:2"``, ``"key:1"``, ``"fi:1"``) assigned in plan
construction order. Cross references are either a real database id
(``int``) or such a temp id (``str``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple, Union

from dpmcore.services.model_validation.types import (
    ModelValidationResult,
    Violation,
)

#: A reference to a model object: real DB id or plan-local temp id.
Ref = Union[int, str]
OptionalRef = Union[int, str, None]


def _fmt(part: OptionalRef) -> str:
    """Render an aspect component the way the SQL renders NULL.

    The SQL builds ``NewAspect``/``OldAspect`` with
    ``CASE WHEN x IS NULL THEN '' ELSE CAST(x AS nvarchar) END``, so
    ``None`` becomes the empty string.
    """
    return "" if part is None else str(part)


@dataclass(frozen=True)
class Aspect:
    """The location-independent identity of a data point.

    Attributes:
        key_id: Compound key of the table (open axes). May be a temp
            id when the key is proposed by this plan.
        property_id: Main property (the metric measured).
        context_id: Dimensional coordinates. May be a temp id when the
            context is proposed by this plan.
    """

    key_id: OptionalRef
    property_id: OptionalRef
    context_id: OptionalRef

    @property
    def signature(self) -> str:
        """``key_property_context`` with None rendered as ``''``.

        Parity with the SQL ``NewAspect``/``OldAspect`` strings.
        """
        return (
            f"{_fmt(self.key_id)}_{_fmt(self.property_id)}"
            f"_{_fmt(self.context_id)}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "key_id": self.key_id,
            "property_id": self.property_id,
            "context_id": self.context_id,
            "signature": self.signature,
        }


class GenerationStatus(str, Enum):
    """Overall outcome of a generation run."""

    COMPLETED = "completed"
    BLOCKED_BY_VALIDATION = "blocked_by_validation"
    BLOCKED_BY_CONSISTENCY = "blocked_by_consistency"


class CellOutcome(str, Enum):
    """Per-cell generation outcome.

    Mapping from the SQL ``OutcomeID``/``OutcomeVID`` pairs:
    ``OLD/OLD`` is UNCHANGED, ``OLD/NEW`` is NEW_VERSION, any
    ``OTHER *`` pair is REASSIGNED, ``NEW/NEW`` is NEW_VARIABLE.
    Void/excluded cells (never assigned by the SQL, marked
    ``Not reportable`` in ``Aux_CellStatus``) are NOT_REPORTABLE.
    """

    UNCHANGED = "unchanged"
    NEW_VERSION = "new_version"
    REASSIGNED = "reassigned"
    NEW_VARIABLE = "new_variable"
    NOT_REPORTABLE = "not_reportable"


@dataclass(frozen=True)
class ProposedVariableVersion:
    """A ``VariableVersion`` row the plan proposes to create.

    Attributes:
        temp_id: Plan-local id, ``"vv:N"``.
        variable_ref: Existing ``variable_id`` or the temp id of a
            :class:`ProposedVariable` in the same plan.
        aspect: The aspect the version carries.
        code: Version code (filing indicators only).
        name: Version name, when one applies.
        supersedes_vid: Existing VariableVersion whose ``EndReleaseID``
            the SQL would have closed with the current release.
    """

    temp_id: str
    variable_ref: Ref
    aspect: Aspect
    code: Optional[str] = None
    name: Optional[str] = None
    supersedes_vid: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "temp_id": self.temp_id,
            "variable_ref": self.variable_ref,
            "aspect": self.aspect.to_dict(),
            "code": self.code,
            "name": self.name,
            "supersedes_vid": self.supersedes_vid,
        }


@dataclass(frozen=True)
class ProposedVariable:
    """A ``Variable`` row the plan proposes to create.

    Attributes:
        temp_id: Plan-local id, ``"var:N"``.
        type: ``"fact"``, ``"key"`` or ``"filingindicator"``.
        aspect: Aspect of the initial version (None for key
            variables, whose identity is just the property).
        code: Business code, when one applies.
        versions: The versions proposed together with the variable.
    """

    temp_id: str
    type: str
    aspect: Optional[Aspect]
    code: Optional[str]
    versions: Tuple[ProposedVariableVersion, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "temp_id": self.temp_id,
            "type": self.type,
            "aspect": self.aspect.to_dict() if self.aspect else None,
            "code": self.code,
            "versions": [v.to_dict() for v in self.versions],
        }


@dataclass(frozen=True)
class ProposedContext:
    """A ``Context`` row (plus compositions) the plan proposes.

    Attributes:
        temp_id: Plan-local id, ``"ctx:N"``.
        signature: Context signature (``prop_item#...`` for cell
            contexts; ``property_item#`` for filing indicators; item
            references may be temp ids for filing-indicator items
            proposed in the same plan).
        compositions: ``(property_id, item_ref)`` pairs.
    """

    temp_id: str
    signature: str
    compositions: Tuple[Tuple[int, Ref], ...]

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "temp_id": self.temp_id,
            "signature": self.signature,
            "compositions": [list(c) for c in self.compositions],
        }


@dataclass(frozen=True)
class ProposedCompoundKey:
    """A ``CompoundKey`` row (plus key composition) the plan proposes.

    Attributes:
        temp_id: Plan-local id, ``"key:N"``.
        signature: ``'#'``-joined key-header property ids (trailing
            ``#``), exactly as the SQL builds it.
        member_variable_refs: Key-variable VariableVersion ids or
            temp ids composing the key.
    """

    temp_id: str
    signature: str
    member_variable_refs: Tuple[Ref, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "temp_id": self.temp_id,
            "signature": self.signature,
            "member_variable_refs": list(self.member_variable_refs),
        }


@dataclass(frozen=True)
class ProposedFilingIndicator:
    """A filing indicator the plan proposes (bundle).

    Bundles everything the SQL creates for one filing-indicator code:
    the Templates ``Item``/``ItemCategory`` (when missing), the
    single-composition ``Context``, the ``Variable`` of type
    ``filingindicator`` with its ``VariableVersion``, and the
    ``ModuleParameters`` links.

    Attributes:
        temp_id: Plan-local id, ``"fi:N"``. Doubles as the reference
            for the bundled Item when a new Templates item is needed.
        code: Filing-indicator code (derived from table codes).
        module_vids: Module versions receiving a ModuleParameters
            link to the filing-indicator variable version.
        item_ref: Templates item carrying the code — an existing item
            id, or this bundle's ``temp_id`` when the item is new.
        item_category_signature: Signature of the proposed Templates
            ItemCategory row (None when the item pre-exists).
        context_ref: Context of the filing-indicator variable.
        variable_ref: The filing-indicator variable (existing id or
            temp id).
        variable_version_ref: Its active version (existing id or temp
            id); None when no ``isReported`` property item exists.
    """

    temp_id: str
    code: str
    module_vids: Tuple[int, ...]
    item_ref: OptionalRef = None
    item_category_signature: Optional[str] = None
    context_ref: OptionalRef = None
    variable_ref: OptionalRef = None
    variable_version_ref: OptionalRef = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "temp_id": self.temp_id,
            "code": self.code,
            "module_vids": list(self.module_vids),
            "item_ref": self.item_ref,
            "item_category_signature": self.item_category_signature,
            "context_ref": self.context_ref,
            "variable_ref": self.variable_ref,
            "variable_version_ref": self.variable_version_ref,
        }


@dataclass(frozen=True)
class HeaderDedup:
    """A header-version deduplication detected in the current release.

    The SQL repoints ``TableVersionHeader`` rows from the redundant
    new HeaderVersion to its identical predecessor, deletes the new
    one and reopens the old one. The plan records the operation and
    applies it *virtually* so later stages see the old HeaderVID.

    Attributes:
        old_header_vid: The reopened predecessor version.
        new_header_vid: The redundant version created this release.
        table_vids: Table versions whose header mapping is repointed.
    """

    old_header_vid: int
    new_header_vid: int
    table_vids: Tuple[int, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "old_header_vid": self.old_header_vid,
            "new_header_vid": self.new_header_vid,
            "table_vids": list(self.table_vids),
        }


@dataclass(frozen=True)
class CellAssignment:
    """The resolved variable mapping of one (table version, cell).

    Parity equivalent of one ``VarGeneration_Detail`` row, but the
    returned set is *complete*: unchanged and not-reportable cells are
    included (the SQL only trimmed them because its output was a UI
    report; the summary applies the SQL filter instead).

    Attributes:
        table_vid: Table version.
        table_code: Its code.
        cell_id: Cell.
        cell_code: Its code.
        outcome: Decided outcome; None when the SQL leaves the cell
            unassigned (e.g. a non-void cell without a main property).
        old_variable_id: Variable previously carrying the cell.
        old_variable_vid: Its version.
        new_variable_ref: Variable after generation (id or temp id).
        new_variable_vid_ref: Version after generation.
        old_aspect: Aspect before generation.
        new_aspect: Aspect after generation.
        notes: Report messages produced for the cell (one per distinct
            message across the module versions containing it).
    """

    table_vid: int
    table_code: Optional[str]
    cell_id: int
    cell_code: Optional[str]
    outcome: Optional[CellOutcome]
    old_variable_id: Optional[int]
    old_variable_vid: Optional[int]
    new_variable_ref: OptionalRef
    new_variable_vid_ref: OptionalRef
    old_aspect: Optional[Aspect]
    new_aspect: Optional[Aspect]
    notes: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "table_vid": self.table_vid,
            "table_code": self.table_code,
            "cell_id": self.cell_id,
            "cell_code": self.cell_code,
            "outcome": self.outcome.value if self.outcome else None,
            "old_variable_id": self.old_variable_id,
            "old_variable_vid": self.old_variable_vid,
            "new_variable_ref": self.new_variable_ref,
            "new_variable_vid_ref": self.new_variable_vid_ref,
            "old_aspect": (
                self.old_aspect.to_dict() if self.old_aspect else None
            ),
            "new_aspect": (
                self.new_aspect.to_dict() if self.new_aspect else None
            ),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class GenerationSummaryRow:
    """One ``VarGeneration_Summary`` row.

    Attributes:
        outcome: Cell outcome the row aggregates.
        message: Report message shared by the aggregated cells.
        count: Number of distinct (table version, cell) pairs.
        min_cell_code: Smallest cell code in the group.
        max_cell_code: Largest cell code in the group.
    """

    outcome: CellOutcome
    message: str
    count: int
    min_cell_code: Optional[str]
    max_cell_code: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "outcome": self.outcome.value,
            "message": self.message,
            "count": self.count,
            "min_cell_code": self.min_cell_code,
            "max_cell_code": self.max_cell_code,
        }


@dataclass(frozen=True)
class VariableGenerationResult:
    """Outcome of a variable-generation run: the complete plan.

    Attributes:
        status: COMPLETED, or a blocked status (plan fields empty).
        release_id: The release the plan was computed for.
        release_code: Code of that release, when available.
        validation: The validation-gate result, when the gate ran.
        consistency_violations: 5_x findings (errors when blocked by
            consistency; 5_5/5_6 warnings on completed runs).
        new_variables: Proposed variables (key, filing indicator and
            fact), in plan-construction order.
        new_variable_versions: Every proposed variable version,
            including those nested in ``new_variables``.
        new_contexts: Proposed contexts.
        new_compound_keys: Proposed compound keys.
        new_filing_indicators: Proposed filing-indicator bundles.
        cell_assignments: Complete (table version, cell) mapping.
        header_deduplications: Virtually applied header dedups.
        summary: Parity with ``VarGeneration_Summary``.
        elapsed_ms: Wall-clock computation time in milliseconds.
    """

    status: GenerationStatus
    release_id: int
    release_code: Optional[str]
    validation: Optional[ModelValidationResult]
    consistency_violations: Tuple[Violation, ...]
    new_variables: Tuple[ProposedVariable, ...]
    new_variable_versions: Tuple[ProposedVariableVersion, ...]
    new_contexts: Tuple[ProposedContext, ...]
    new_compound_keys: Tuple[ProposedCompoundKey, ...]
    new_filing_indicators: Tuple[ProposedFilingIndicator, ...]
    cell_assignments: Tuple[CellAssignment, ...]
    header_deduplications: Tuple[HeaderDedup, ...]
    summary: Tuple[GenerationSummaryRow, ...]
    elapsed_ms: float

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "status": self.status.value,
            "release_id": self.release_id,
            "release_code": self.release_code,
            "validation": (
                self.validation.to_dict() if self.validation else None
            ),
            "consistency_violations": [
                v.to_dict() for v in self.consistency_violations
            ],
            "new_variables": [
                v.to_dict() for v in self.new_variables
            ],
            "new_variable_versions": [
                v.to_dict() for v in self.new_variable_versions
            ],
            "new_contexts": [c.to_dict() for c in self.new_contexts],
            "new_compound_keys": [
                k.to_dict() for k in self.new_compound_keys
            ],
            "new_filing_indicators": [
                f.to_dict() for f in self.new_filing_indicators
            ],
            "cell_assignments": [
                c.to_dict() for c in self.cell_assignments
            ],
            "header_deduplications": [
                h.to_dict() for h in self.header_deduplications
            ],
            "summary": [s.to_dict() for s in self.summary],
            "elapsed_ms": self.elapsed_ms,
        }
