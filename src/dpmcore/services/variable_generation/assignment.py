"""Cell-modelling working set and the outcome-decision engine.

Port of the SQL ``#cellmodelling`` construction and the "MAIN PROCESS
OF FACT VARIABLE GENERATION": one working record per (module version,
table version, cell) across active module versions, old coordinates
taken from the predecessor table version closed by the current
release or through ``Aux_CellMapping`` continuity, and the outcome
blocks applied with exactly the SQL precedence:

1.  ``old aspect == new aspect`` -> UNCHANGED (``OLD/OLD``).
2.  The same variable already has an active version carrying the new
    aspect (SQL block 1b) -> UNCHANGED, reusing that version.
3.  Aspect changed, same key, same main-property data type ->
    NEW_VERSION: a proposed VariableVersion on the old variable, the
    superseded version recorded (SQL block 2.1, list a).
4.  Another active *fact* VariableVersion already carries the new
    aspect -> REASSIGNED to the most recent one (``OTHER ...``).
5.  Every remaining aspect -> NEW_VARIABLE, one proposal per distinct
    aspect (cells sharing an aspect share the proposal).
6.  Void/excluded cells are never assigned (NOT_REPORTABLE).

The 5_5/5_6 warnings the SQL emits between the blocks are produced at
the same positions through the helpers in
:mod:`dpmcore.services.variable_generation.checks`.

Note:
    The SQL's NEW_VERSION insert numbers rows *before* applying
    DISTINCT, so two cells sharing (old variable, new aspect) would
    create duplicate versions; the plan proposes exactly one version
    per distinct (old variable, new aspect), which is the reading the
    surrounding checks (5_2/5_3) enforce anyway.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Set, Tuple, cast

from dpmcore.services.model_validation.release_context import (
    ReleaseContext,
)
from dpmcore.services.model_validation.snapshot import (
    ModelSnapshot,
    VariableVersionRow,
)
from dpmcore.services.model_validation.types import Violation
from dpmcore.services.variable_generation.checks import (
    apply_5_5,
    apply_5_6_stale_modules,
    check_5_6_shared_aspect,
)
from dpmcore.services.variable_generation.state import (
    CellRecord,
    GenerationState,
)
from dpmcore.services.variable_generation.types import (
    Aspect,
    OptionalRef,
    ProposedVariable,
    ProposedVariableVersion,
    Ref,
)

MSG_UNCHANGED = (
    "Old Cell with the Same Aspect: Old VariableID & Old VariableVID"
)
MSG_UNCHANGED_1B = (
    "Old Cell with the Different Aspect but Existing active "
    "VariableVID for the same Old VariableID"
)
MSG_NEW_VERSION = (
    "Old Cell with Different Aspect but same Key & same data type "
    "for Main Property: Old VariableID & New VariableVID. "
)
MSG_REASSIGNED_OLD = (
    "An old cell (changing Main property or keys) has another "
    "variable (already used in other cells)"
)
MSG_REASSIGNED_NEW = (
    "A new cell has another variable (already used in other cells)"
)
MSG_NEW_VARIABLE_PREFIX = "New Variable ID & New Variable VID: "


# ------------------------------------------------------------------
# Working-set construction (SQL #cellmodelling)
# ------------------------------------------------------------------


def build_working_set(
    snapshot: ModelSnapshot, release: ReleaseContext
) -> List[CellRecord]:
    """One record per (active module version, table version, cell).

    Old coordinates come from the cell's own ``VariableVID``, then —
    for table versions starting in the current release — from the
    predecessor table version closed by the current release, then
    from ``Aux_CellMapping`` continuity. Cells of unchanged table
    versions get their new coordinates copied from the old ones.
    """
    records = _base_records(snapshot, release)
    records.sort(
        key=lambda r: (r.module_vid, r.table_vid, r.cell_id)
    )
    predecessors = _predecessor_versions(snapshot, release)
    continuity = _continuity_versions(snapshot)
    for record in records:
        if not release.is_current(record.tv_start):
            continue
        vv = predecessors.get(record.cell_id)
        if vv is not None:
            _set_old_coordinates(record, vv)
        vv = continuity.get((record.table_vid, record.cell_id))
        if vv is not None:
            _set_old_coordinates(record, vv)
    for record in records:
        if not release.is_current(record.tv_start):
            record.new_context_id = record.old_context_id
            record.new_property_id = record.old_property_id
            record.new_key_id = record.old_key_id
    _set_is_new_cell(snapshot, release, records)
    return records


def _base_records(
    snapshot: ModelSnapshot, release: ReleaseContext
) -> List[CellRecord]:
    """Initial rows from active, non-draft module versions."""
    records = []
    tvc_index = snapshot.tvc_by_table_vid()
    for mv in snapshot.module_versions:
        if mv.end_release_id is not None or release.is_draft(
            mv.start_release_id
        ):
            continue
        for mvc in snapshot.mvc_by_module_vid().get(mv.module_vid, []):
            tv = snapshot.table_versions_by_vid.get(
                mvc.table_vid or -1
            )
            if tv is None:
                continue
            for tvc in tvc_index.get(tv.table_vid, []):
                record = CellRecord(
                    module_vid=mv.module_vid,
                    module_code=mv.code,
                    table_vid=tv.table_vid,
                    table_code=tv.code,
                    cell_id=tvc.cell_id,
                    cell_code=tvc.cell_code,
                    is_void=bool(tvc.is_void) or bool(tvc.is_excluded),
                    tv_start=tv.start_release_id,
                    mv_start=mv.start_release_id,
                )
                if tvc.variable_vid is not None:
                    vv = snapshot.variable_versions_by_vid.get(
                        tvc.variable_vid
                    )
                    if vv is not None:
                        _set_old_coordinates(record, vv)
                records.append(record)
    return records


def _set_old_coordinates(
    record: CellRecord, vv: VariableVersionRow
) -> None:
    """Copy a VariableVersion's coordinates into the old fields."""
    record.vv_old_end = vv.end_release_id
    record.old_variable_id = vv.variable_id
    record.old_variable_vid = vv.variable_vid
    record.old_context_id = vv.context_id
    record.old_property_id = vv.property_id
    record.old_key_id = vv.key_id


def _predecessor_versions(
    snapshot: ModelSnapshot, release: ReleaseContext
) -> Dict[int, VariableVersionRow]:
    """cell_id -> VariableVersion of the closed predecessor cell.

    Note:
        The SQL matches predecessor cells by CellID alone; if several
        table versions closed by the current release carry the cell,
        the update picks one arbitrarily — the plan deterministically
        uses the one with the highest TableVID.
    """
    best: Dict[int, Tuple[int, VariableVersionRow]] = {}
    for tvc in snapshot.table_version_cells:
        tv = snapshot.table_versions_by_vid.get(tvc.table_vid)
        if tv is None or not release.ends_in_current(
            tv.end_release_id
        ):
            continue
        if tvc.cell_id not in snapshot.cells_by_id:
            continue
        if tvc.variable_vid is None:
            continue
        vv = snapshot.variable_versions_by_vid.get(tvc.variable_vid)
        if vv is None:
            continue
        current = best.get(tvc.cell_id)
        if current is None or tvc.table_vid > current[0]:
            best[tvc.cell_id] = (tvc.table_vid, vv)
    return {cell_id: vv for cell_id, (_, vv) in best.items()}


def _continuity_versions(
    snapshot: ModelSnapshot,
) -> Dict[Tuple[int, int], VariableVersionRow]:
    """(new table_vid, new cell_id) -> mapped old VariableVersion."""
    tvc_by_pair = {
        (tvc.table_vid, tvc.cell_id): tvc
        for tvc in snapshot.table_version_cells
    }
    mapping: Dict[Tuple[int, int], VariableVersionRow] = {}
    for ac in snapshot.aux_cell_mappings:
        if ac.old_table_vid is None or ac.old_cell_id is None:
            continue
        tvc = tvc_by_pair.get((ac.old_table_vid, ac.old_cell_id))
        if (
            tvc is None
            or tvc.variable_vid is None
            or tvc.cell_id not in snapshot.cells_by_id
            or ac.old_table_vid not in snapshot.table_versions_by_vid
        ):
            continue
        vv = snapshot.variable_versions_by_vid.get(tvc.variable_vid)
        if vv is not None:
            mapping[(ac.new_table_vid, ac.new_cell_id)] = vv
    return mapping


def _set_is_new_cell(
    snapshot: ModelSnapshot,
    release: ReleaseContext,
    records: List[CellRecord],
) -> None:
    """SQL ``isNewCell`` flag."""
    predecessor_cells = {
        tvc.cell_id
        for tvc in snapshot.table_version_cells
        if tvc.variable_vid is not None
        and (tv := snapshot.table_versions_by_vid.get(tvc.table_vid))
        is not None
        and release.ends_in_current(tv.end_release_id)
    }
    tvc_index = snapshot.tvc_by_table_vid()
    mapped: Set[Tuple[int, int]] = set()
    for ac in snapshot.aux_cell_mappings:
        if ac.old_table_vid is None:
            continue
        old_cells = {
            tvc.cell_id
            for tvc in tvc_index.get(ac.old_table_vid, [])
            if tvc.variable_vid is not None
        }
        if ac.old_cell_id in old_cells:
            mapped.add((ac.new_table_vid, ac.new_cell_id))
    for record in records:
        known = (
            record.cell_id in predecessor_cells
            or (record.table_vid, record.cell_id) in mapped
        )
        if known:
            record.is_new_cell = False
        else:
            record.is_new_cell = release.is_current(record.tv_start)


# ------------------------------------------------------------------
# Outcome decision (SQL outcome blocks, in order)
# ------------------------------------------------------------------


@dataclass(frozen=True)
class _NewAspect:
    """One distinct unassigned aspect (SQL ``#new_Aspects`` row)."""

    signature: str
    key_id: OptionalRef
    property_id: int
    context_id: OptionalRef

    def aspect(self) -> Aspect:
        """The aspect value."""
        return Aspect(self.key_id, self.property_id, self.context_id)


def decide_outcomes(
    records: List[CellRecord],
    snapshot: ModelSnapshot,
    release: ReleaseContext,
    state: GenerationState,
) -> List[Violation]:
    """Run the outcome blocks and return the 5_5/5_6 warnings."""
    _block_unchanged(records, release)
    _block_existing_version_of_same_variable(
        records, snapshot, release
    )
    new_aspects = _collect_new_aspects(records, release)
    _propose_new_versions(records, new_aspects, snapshot, release, state)
    _assign_new_versions(records, release, state)
    warnings = apply_5_5(records, release)
    warnings += check_5_6_shared_aspect(records, snapshot, release)
    warnings += apply_5_6_stale_modules(records, release)
    _assign_reassigned(records, snapshot, release, state)
    _assign_new_variables(records, new_aspects, release, state)
    return warnings


def _case_message(
    record: CellRecord, release: ReleaseContext, else_message: str
) -> str:
    """The SQL CASE over module/table-version age (NULL -> ELSE)."""
    if record.mv_start is not None and not release.is_current(
        record.mv_start
    ):
        return "OLD ModuleVersion: "
    if record.tv_start is not None and not release.is_current(
        record.tv_start
    ):
        return "NEW ModuleVersion & OLD TableVersion "
    return else_message


def _block_unchanged(
    records: List[CellRecord], release: ReleaseContext
) -> None:
    """SQL block 1: old aspect equals new aspect."""
    for record in records:
        if record.is_void:
            continue
        if record.old_signature != record.new_signature:
            continue
        if record.vv_old_end is not None and not (
            record.tv_start is not None
            and not release.is_current(record.tv_start)
        ):
            continue
        record.new_variable_ref = record.old_variable_id
        record.new_vvid_ref = record.old_variable_vid
        record.outcome_id = "OLD"
        record.outcome_vid = "OLD"
        record.report_msg = _case_message(
            record, release, MSG_UNCHANGED
        )


def _block_existing_version_of_same_variable(
    records: List[CellRecord],
    snapshot: ModelSnapshot,
    release: ReleaseContext,
) -> None:
    """Reuse an active same-variable version (SQL block 1b).

    Another cell resolved the same variable to an active version
    carrying this cell's new aspect.
    """
    frozen = [
        (
            r.cell_id,
            r.new_variable_ref,
            r.new_signature,
            r.new_vvid_ref,
            r.is_void,
        )
        for r in records
    ]
    for record in records:
        if (
            record.is_void
            or record.new_vvid_ref is not None
            or record.old_signature == record.new_signature
            or not release.is_current(record.tv_start)
            or record.old_variable_id is None
        ):
            continue
        best = _best_active_match(record, frozen, snapshot)
        if best is None:
            continue
        record.new_variable_ref = record.old_variable_id
        record.new_vvid_ref = best
        record.outcome_id = "OLD"
        record.outcome_vid = "OLD"
        record.report_msg = _case_message(
            record, release, MSG_UNCHANGED_1B
        )


def _best_active_match(
    record: CellRecord,
    frozen: List[Tuple[int, OptionalRef, str, OptionalRef, bool]],
    snapshot: ModelSnapshot,
) -> Optional[int]:
    """Highest active existing VVID assigned by another cell."""
    best: Optional[int] = None
    for cell_id, var_ref, signature, vvid_ref, is_void in frozen:
        if (
            cell_id == record.cell_id
            or is_void
            or not isinstance(vvid_ref, int)
            or var_ref != record.old_variable_id
            or signature != record.new_signature
        ):
            continue
        vv = snapshot.variable_versions_by_vid.get(vvid_ref)
        if vv is None or vv.end_release_id is not None:
            continue
        if best is None or vvid_ref > best:
            best = vvid_ref
    return best


def _collect_new_aspects(
    records: List[CellRecord], release: ReleaseContext
) -> List[_NewAspect]:
    """SQL ``#new_Aspects``: distinct unassigned non-void aspects."""
    seen: Dict[str, _NewAspect] = {}
    for r in records:
        if (
            r.new_vvid_ref is None
            and r.new_property_id is not None
            and not r.is_void
            and release.is_current(r.tv_start)
            and r.new_signature not in seen
        ):
            seen[r.new_signature] = _NewAspect(
                r.new_signature,
                r.new_key_id,
                r.new_property_id,
                r.new_context_id,
            )
    return [seen[sig] for sig in sorted(seen)]


def _propose_new_versions(
    records: List[CellRecord],
    new_aspects: List[_NewAspect],
    snapshot: ModelSnapshot,
    release: ReleaseContext,
    state: GenerationState,
) -> None:
    """SQL block 2.1 (list a): new version on the old variable."""
    aspect_index = {na.signature: na for na in new_aspects}
    blocked_variables = {
        vv.variable_id
        for vv in snapshot.variable_versions
        if release.is_current(vv.start_release_id)
    }
    wanted: Set[Tuple[str, int]] = set()
    for r in records:
        if (
            r.new_signature in aspect_index
            and not r.is_new_cell
            and r.new_key_id == r.old_key_id
            and not r.is_new_property_datatype
            and r.new_vvid_ref is None
            and not r.is_void
            and r.old_variable_id is not None
            and r.old_variable_id not in blocked_variables
        ):
            wanted.add((r.new_signature, r.old_variable_id))
    for signature, variable_id in sorted(wanted):
        supersedes = [
            vv.variable_vid
            for vv in snapshot.variable_versions
            if vv.variable_id == variable_id
            and vv.end_release_id is None
            and vv.start_release_id is not None
            and not release.is_current(vv.start_release_id)
        ]
        state.new_version_versions.append(
            ProposedVariableVersion(
                temp_id=state.ids.next("vv"),
                variable_ref=variable_id,
                aspect=aspect_index[signature].aspect(),
                supersedes_vid=max(supersedes) if supersedes else None,
            )
        )


def _assign_new_versions(
    records: List[CellRecord],
    release: ReleaseContext,
    state: GenerationState,
) -> None:
    """SQL block 2.1 assignment: OLD variable, NEW version."""
    by_key: Dict[
        Tuple[Ref, OptionalRef, OptionalRef, OptionalRef], str
    ] = {}
    for version in state.new_version_versions:
        aspect = version.aspect
        by_key[
            (
                version.variable_ref,
                aspect.key_id,
                aspect.property_id,
                aspect.context_id,
            )
        ] = version.temp_id
    for r in records:
        if (
            not release.is_current(r.tv_start)
            or r.is_new_cell
            or r.new_vvid_ref is not None
            or r.is_void
            or r.old_variable_id is None
            or r.new_property_id is None
        ):
            continue
        temp_id = by_key.get(
            (
                r.old_variable_id,
                r.new_key_id,
                r.new_property_id,
                r.new_context_id,
            )
        )
        if temp_id is None:
            continue
        r.new_variable_ref = r.old_variable_id
        r.new_vvid_ref = temp_id
        r.outcome_id = "OLD"
        r.outcome_vid = "NEW"
        r.report_msg = MSG_NEW_VERSION


@dataclass(frozen=True)
class _Candidate:
    """An active VariableVersion eligible for reassignment."""

    variable_ref: Ref
    vvid_ref: Ref
    key_id: OptionalRef
    property_id: Optional[int]
    context_id: OptionalRef
    start_release_id: Optional[int]
    is_fact: bool
    order: Tuple[int, int]


def _reassignment_candidates(
    snapshot: ModelSnapshot,
    release: ReleaseContext,
    state: GenerationState,
) -> List[_Candidate]:
    """Active versions (existing plus block-2.1 proposals)."""
    candidates = []
    for vv in snapshot.variable_versions:
        if vv.end_release_id is not None or vv.variable_id is None:
            continue
        variable = snapshot.variables_by_id.get(vv.variable_id)
        candidates.append(
            _Candidate(
                variable_ref=vv.variable_id,
                vvid_ref=vv.variable_vid,
                key_id=vv.key_id,
                property_id=vv.property_id,
                context_id=vv.context_id,
                start_release_id=vv.start_release_id,
                is_fact=(
                    variable is not None and variable.type == "fact"
                ),
                order=(0, vv.variable_vid),
            )
        )
    for index, version in enumerate(state.new_version_versions):
        # Block-2.1 proposals always reference an existing variable
        # (int) and a real property id; see _propose_new_versions.
        variable_id = cast(int, version.variable_ref)
        variable = snapshot.variables_by_id.get(variable_id)
        aspect = version.aspect
        candidates.append(
            _Candidate(
                variable_ref=variable_id,
                vvid_ref=version.temp_id,
                key_id=aspect.key_id,
                property_id=cast(int, aspect.property_id),
                context_id=aspect.context_id,
                start_release_id=release.current_release_id,
                is_fact=(
                    variable is not None and variable.type == "fact"
                ),
                order=(1, index),
            )
        )
    return candidates


def _assign_reassigned(
    records: List[CellRecord],
    snapshot: ModelSnapshot,
    release: ReleaseContext,
    state: GenerationState,
) -> None:
    """SQL list b: reuse the most recent active matching fact VV.

    Note:
        Among versions tied on the release date the SQL picks one
        arbitrarily; the plan prefers versions proposed in this run
        (they carry the largest ids in the SQL) and otherwise the
        highest VariableVID.
    """
    candidates = _reassignment_candidates(snapshot, release, state)
    old_variables = {
        vv.variable_id
        for vv in snapshot.variable_versions
        if vv.variable_id is not None
        and vv.start_release_id is not None
        and not release.is_current(vv.start_release_id)
    }
    for r in records:
        if (
            not release.is_current(r.tv_start)
            or r.new_vvid_ref is not None
            or r.is_void
            or r.new_property_id is None
        ):
            continue
        chosen = _choose_candidate(r, candidates, state)
        if chosen is None:
            continue
        r.new_variable_ref = chosen.variable_ref
        r.new_vvid_ref = chosen.vvid_ref
        r.outcome_id = "OTHER " + (
            "OLD" if chosen.variable_ref in old_variables else "NEW"
        )
        r.outcome_vid = "OTHER " + (
            "NEW"
            if release.is_current(chosen.start_release_id)
            else "OLD"
        )
        r.report_msg = (
            MSG_REASSIGNED_NEW if r.is_new_cell else MSG_REASSIGNED_OLD
        )


def _choose_candidate(
    record: CellRecord,
    candidates: List[_Candidate],
    state: GenerationState,
) -> Optional[_Candidate]:
    """Most recent matching fact candidate, None when none applies."""
    matching = [
        c
        for c in candidates
        if c.property_id == record.new_property_id
        and c.key_id == record.new_key_id
        and c.context_id == record.new_context_id
    ]
    dates = [
        d
        for c in matching
        if c.start_release_id is not None
        and (d := state.release_dates.get(c.start_release_id))
        is not None
    ]
    if not dates:
        return None
    max_date: date = max(dates)
    eligible = [
        c
        for c in matching
        if c.is_fact
        and c.start_release_id is not None
        and state.release_dates.get(c.start_release_id) == max_date
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda c: c.order)


def _assign_new_variables(
    records: List[CellRecord],
    new_aspects: List[_NewAspect],
    release: ReleaseContext,
    state: GenerationState,
) -> None:
    """SQL final block: brand-new variable per remaining aspect."""
    remaining = [
        na
        for na in new_aspects
        if any(
            r.new_signature == na.signature
            and r.new_vvid_ref is None
            and not r.is_void
            and release.is_current(r.tv_start)
            for r in records
        )
    ]
    remaining.sort(key=lambda na: (na.property_id, na.signature))
    for na in remaining:
        var_id = state.ids.next("var")
        version = ProposedVariableVersion(
            temp_id=state.ids.next("vv"),
            variable_ref=var_id,
            aspect=na.aspect(),
        )
        state.fact_variables.append(
            ProposedVariable(
                temp_id=var_id,
                type="fact",
                aspect=na.aspect(),
                code=None,
                versions=(version,),
            )
        )
        for r in records:
            if (
                release.is_current(r.tv_start)
                and r.new_vvid_ref is None
                and not r.is_void
                and r.new_signature == na.signature
            ):
                r.new_variable_ref = var_id
                r.new_vvid_ref = version.temp_id
                r.outcome_id = "NEW"
                r.outcome_vid = "NEW"
                r.report_msg = MSG_NEW_VARIABLE_PREFIX + (
                    "New Cell"
                    if r.is_new_cell
                    else "Old cell (changing Main property of keys) "
                    "has a new created variable"
                )
