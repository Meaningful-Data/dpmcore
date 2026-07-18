"""Report assembly (SQL ``VarGeneration_Detail`` / ``_Summary``).

``cell_assignments`` is the *complete* mapping — one entry per
(table version, cell), including UNCHANGED and NOT_REPORTABLE cells
(spec decision 6). The ``summary`` reproduces the SQL report filter
instead: the detail report excludes void cells and rows with
``OutcomeVID = 'OLD'`` (which also drops rows the SQL never assigned,
as ``NULL <> 'OLD'`` is UNKNOWN), and the summary aggregates that
filtered view grouped by outcome and message with the distinct
(table version, cell) count and the min/max cell code.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple, cast

from dpmcore.services.variable_generation.state import CellRecord
from dpmcore.services.variable_generation.types import (
    CellAssignment,
    CellOutcome,
    GenerationSummaryRow,
)


def outcome_of(record: CellRecord) -> Optional[CellOutcome]:
    """Map the SQL OutcomeID/OutcomeVID pair to a cell outcome.

    Void/excluded cells are NOT_REPORTABLE (the SQL clears their
    assignment and marks them ``Not reportable`` in
    ``Aux_CellStatus``); unassigned non-void cells stay None, exactly
    as the SQL leaves their OutcomeID NULL.
    """
    if record.is_void:
        return CellOutcome.NOT_REPORTABLE
    if record.outcome_id is None or record.outcome_vid is None:
        return None
    if record.outcome_id == "NEW":
        return CellOutcome.NEW_VARIABLE
    if record.outcome_id.startswith("OTHER"):
        return CellOutcome.REASSIGNED
    if record.outcome_vid == "NEW":
        return CellOutcome.NEW_VERSION
    return CellOutcome.UNCHANGED


def build_cell_assignments(
    records: Sequence[CellRecord],
) -> Tuple[CellAssignment, ...]:
    """One assignment per distinct (table version, cell).

    The working set carries one record per module version; the
    decided outcome only depends on table/cell-level state, so the
    records collapse cleanly — only the report messages differ per
    module and are gathered into ``notes``.
    """
    grouped: Dict[Tuple[int, int], List[CellRecord]] = {}
    for record in records:
        key = (record.table_vid, record.cell_id)
        grouped.setdefault(key, []).append(record)
    assignments = []
    for key in sorted(grouped):
        group = grouped[key]
        primary = group[0]
        notes = sorted(
            {r.report_msg for r in group if r.report_msg is not None}
        )
        assignments.append(
            CellAssignment(
                table_vid=primary.table_vid,
                table_code=primary.table_code,
                cell_id=primary.cell_id,
                cell_code=primary.cell_code,
                outcome=outcome_of(primary),
                old_variable_id=primary.old_variable_id,
                old_variable_vid=primary.old_variable_vid,
                new_variable_ref=primary.new_variable_ref,
                new_variable_vid_ref=primary.new_vvid_ref,
                old_aspect=primary.old_aspect,
                new_aspect=primary.new_aspect,
                notes=tuple(notes),
            )
        )
    return tuple(assignments)


def build_summary(
    records: Sequence[CellRecord],
) -> Tuple[GenerationSummaryRow, ...]:
    """Aggregate the SQL's filtered report view.

    Mirrors the ``VarGeneration_Detail`` filter (non-void and
    ``OutcomeVID <> 'OLD'``, which excludes both unchanged and
    never-assigned rows) and the ``VarGeneration_Summary`` grouping.
    """
    groups: Dict[
        Tuple[str, str],
        Tuple[CellOutcome, Set[Tuple[int, int]], List[str]],
    ] = {}
    for record in records:
        if record.is_void or record.outcome_vid in (None, "OLD"):
            continue
        # After the filter the record was assigned by some block, so
        # outcome_of never returns None here.
        outcome = cast(CellOutcome, outcome_of(record))
        message = record.report_msg or ""
        key = (outcome.value, message)
        entry = groups.setdefault(key, (outcome, set(), []))
        entry[1].add((record.table_vid, record.cell_id))
        if record.cell_code is not None:
            entry[2].append(record.cell_code)
    rows = []
    for (_, message), (outcome, cells, codes) in sorted(
        groups.items()
    ):
        rows.append(
            GenerationSummaryRow(
                outcome=outcome,
                message=message,
                count=len(cells),
                min_cell_code=min(codes) if codes else None,
                max_cell_code=max(codes) if codes else None,
            )
        )
    return tuple(rows)
