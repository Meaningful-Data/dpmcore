"""Generation consistency checks (SQL violation codes 5_1 .. 5_6).

Evaluated over the in-memory cell-modelling working set — not over
the snapshot alone — so they live here rather than in the model-
validation rule registry, but they produce the same
:class:`~dpmcore.services.model_validation.types.Violation` type.

``5_1``–``5_4`` are blocking (severity ``error``) and run before the
outcome decision; any finding stops the generation. ``5_5``/``5_6``
are warnings the SQL emits *during* the outcome blocks; the outcome
engine calls the corresponding helpers at the exact SQL positions.

Note:
    The SQL flags the "shared aspect with a cell of another module
    changing in this release" variant of ``5_6`` as blocking, but it
    is inserted after the blocking gate and can never stop the run;
    per the specification both ``5_6`` variants are warnings here.
    The SQL's message-append UPDATE preceding the first ``5_6``
    insert compares ``mv.EndReleaseID = Null`` and can never fire;
    it is not ported.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from dpmcore.services.model_validation.release_context import (
    ReleaseContext,
)
from dpmcore.services.model_validation.snapshot import (
    ModelSnapshot,
    VariableVersionRow,
)
from dpmcore.services.model_validation.types import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    ObjectRef,
    Violation,
)
from dpmcore.services.variable_generation.state import CellRecord

MSG_5_1 = "Expired VariableVersion in active TableVersion"
MSG_5_2 = (
    "These two cells had the same old VariableID but now they have "
    "different aspects"
)
MSG_5_3 = (
    "These two cells had different old VariableIDs but now they have "
    "the same aspect"
)
MSG_5_4 = (
    "The first cell is void and the second cell has the same new "
    "aspect but is non-void"
)
MSG_5_5 = (
    "Old VariableID & New VariableVID. WARNING: Old Cell with Same "
    "Aspect but old VariableVersion EndRelease not Null. Its "
    "VariableID may have been employed by another VariableVID in the "
    "meantime, different than the original one."
)


def _cell_ref(
    cell_id: int, cell_code: Optional[str], kind: str = "cell"
) -> ObjectRef:
    """ObjectRef for a cell."""
    return ObjectRef(kind=kind, id=cell_id, code=cell_code)


def _tv_ref(
    snapshot: ModelSnapshot, table_vid: int
) -> ObjectRef:
    """ObjectRef for a table version."""
    tv = snapshot.table_versions_by_vid.get(table_vid)
    return ObjectRef(
        kind="table_version",
        id=table_vid,
        code=tv.code if tv is not None else None,
    )


def _violation(
    rule_id: str,
    severity: str,
    message: str,
    objects: Tuple[ObjectRef, ...],
) -> Violation:
    """Build a generation-family violation."""
    return Violation(
        rule_id=rule_id,
        legacy_code=rule_id,
        message=message,
        severity=severity,
        objects=objects,
    )


def blocking_checks(
    records: Sequence[CellRecord],
    snapshot: ModelSnapshot,
    release: ReleaseContext,
) -> List[Violation]:
    """Run the blocking checks 5_1 .. 5_4 over the working set."""
    violations = _check_5_1(records, snapshot, release)
    violations += _check_5_2(records, snapshot, release)
    violations += _check_5_3(records, snapshot, release)
    violations += _check_5_4(records, snapshot, release)
    return violations


def _emit_pairs(
    rule_id: str,
    message: str,
    snapshot: ModelSnapshot,
    pairs: Iterable[Tuple[CellRecord, CellRecord]],
) -> List[Violation]:
    """Distinct, ordered violations for cell-pair findings."""
    seen: Set[Tuple[int, int, int]] = set()
    ordered = []
    for first, second in pairs:
        key = (first.table_vid, first.cell_id, second.cell_id)
        if key not in seen:
            seen.add(key)
            ordered.append((key, first, second))
    return [
        _violation(
            rule_id,
            SEVERITY_ERROR,
            message,
            (
                _cell_ref(first.cell_id, first.cell_code),
                _cell_ref(second.cell_id, second.cell_code, "cell2"),
                _tv_ref(snapshot, first.table_vid),
            ),
        )
        for _, first, second in sorted(ordered, key=lambda e: e[0])
    ]


def _check_5_1(
    records: Sequence[CellRecord],
    snapshot: ModelSnapshot,
    release: ReleaseContext,
) -> List[Violation]:
    """Expired VariableVersion referenced by an active table version."""
    found = {
        (r.table_vid, r.cell_id, r.cell_code)
        for r in records
        if release.is_current(r.mv_start)
        and r.tv_start is not None
        and not release.is_current(r.tv_start)
        and r.vv_old_end is not None
        and not r.is_void
    }
    return [
        _violation(
            "5_1",
            SEVERITY_ERROR,
            MSG_5_1,
            (
                _cell_ref(cell_id, cell_code),
                _tv_ref(snapshot, table_vid),
            ),
        )
        for table_vid, cell_id, cell_code in sorted(
            found, key=lambda f: (f[0], f[1])
        )
    ]


def _key_unchanged(record: CellRecord) -> bool:
    """SQL ``(OldKey NULL AND NewKey NULL) OR NewKey = OldKey``."""
    return record.new_key_id == record.old_key_id


def _check_5_2(
    records: Sequence[CellRecord],
    snapshot: ModelSnapshot,
    release: ReleaseContext,
) -> List[Violation]:
    """Same old variable, different new aspects, no key/type change."""
    by_variable: Dict[int, List[CellRecord]] = {}
    for r in records:
        if r.old_variable_id is not None:
            by_variable.setdefault(r.old_variable_id, []).append(r)

    def pairs() -> Iterable[Tuple[CellRecord, CellRecord]]:
        for group in by_variable.values():
            for first in group:
                if not _qualifies_5_2(first, release) or first.is_void:
                    continue
                yield from (
                    (first, second)
                    for second in group
                    if second.cell_id > first.cell_id
                    and _qualifies_5_2(second, release)
                    and first.new_signature != second.new_signature
                )

    return _emit_pairs("5_2", MSG_5_2, snapshot, pairs())


def _qualifies_5_2(
    record: CellRecord, release: ReleaseContext
) -> bool:
    """Shared 5_2 conditions applied to each side of the pair."""
    return (
        not record.is_new_cell
        and _key_unchanged(record)
        and not record.is_new_property_datatype
        and release.is_current(record.mv_start)
    )


def _check_5_3(
    records: Sequence[CellRecord],
    snapshot: ModelSnapshot,
    release: ReleaseContext,
) -> List[Violation]:
    """Different old variables now resolving to the same aspect."""
    by_aspect: Dict[str, List[CellRecord]] = {}
    for r in records:
        by_aspect.setdefault(r.new_signature, []).append(r)

    def pairs() -> Iterable[Tuple[CellRecord, CellRecord]]:
        for group in by_aspect.values():
            for first in group:
                if (
                    first.is_new_cell
                    or first.is_void
                    or not release.is_current(first.mv_start)
                    or first.old_variable_id is None
                ):
                    continue
                yield from (
                    (first, second)
                    for second in group
                    if second.cell_id > first.cell_id
                    and not second.is_new_cell
                    and release.is_current(second.mv_start)
                    and second.old_variable_id is not None
                    and second.old_variable_id != first.old_variable_id
                )

    return _emit_pairs("5_3", MSG_5_3, snapshot, pairs())


def _check_5_4(
    records: Sequence[CellRecord],
    snapshot: ModelSnapshot,
    release: ReleaseContext,
) -> List[Violation]:
    """A void cell sharing its new aspect with a non-void cell.

    Union of the SQL's two 5_4 INSERTs: the first requires the void
    cell's table version to start in the current release, the second
    requires the non-void cell's; duplicates are emitted once.
    """
    void_flags = {
        (tvc.table_vid, tvc.cell_id): tvc.is_void
        for tvc in snapshot.table_version_cells
    }
    by_aspect: Dict[str, List[CellRecord]] = {}
    for r in records:
        by_aspect.setdefault(r.new_signature, []).append(r)

    def pairs() -> Iterable[Tuple[CellRecord, CellRecord]]:
        for group in by_aspect.values():
            for first in group:
                if (
                    void_flags.get((first.table_vid, first.cell_id))
                    is not True
                ):
                    continue
                first_tv_current = release.is_current(first.tv_start)
                yield from (
                    (first, second)
                    for second in group
                    if not second.is_void
                    and second.cell_id != first.cell_id
                    and (
                        first_tv_current
                        or release.is_current(second.tv_start)
                    )
                )

    return _emit_pairs("5_4", MSG_5_4, snapshot, pairs())


# ------------------------------------------------------------------
# Warning helpers used by the outcome engine (SQL 5_5 / 5_6)
# ------------------------------------------------------------------


def apply_5_5(
    records: Sequence[CellRecord], release: ReleaseContext
) -> List[Violation]:
    """Same aspect reused after the old version had expired.

    Overwrites the report message of the matched records (mirroring
    the SQL UPDATE) and returns the corresponding warnings.
    """
    matched = [
        r
        for r in records
        if release.is_current(r.tv_start)
        and r.old_signature == r.new_signature
        and not r.is_new_cell
        and r.outcome_id == "OLD"
        and r.outcome_vid == "NEW"
        and r.new_vvid_ref is not None
        and r.vv_old_end is not None
        and not r.is_void
    ]
    seen: Set[Tuple[int, int]] = set()
    violations = []
    for r in matched:
        r.report_msg = MSG_5_5
        key = (r.table_vid, r.cell_id)
        if key not in seen:
            seen.add(key)
            violations.append(
                _violation(
                    "5_5",
                    SEVERITY_WARNING,
                    MSG_5_5,
                    (
                        _cell_ref(r.cell_id, r.cell_code),
                        ObjectRef(kind="table_version", id=r.table_vid),
                    ),
                )
            )
    return violations


def _aspect_matches(
    record: CellRecord, vv: VariableVersionRow
) -> bool:
    """SQL ``ISNULL``-style aspect match between a record and a VV.

    ``ISNULL(x, -1) = ISNULL(y, -1)`` treats two NULLs as equal for
    the key and context; the property comparison is a plain equality
    that never matches on NULL.
    """
    return (
        record.new_key_id == vv.key_id
        and record.new_context_id == vv.context_id
        and record.new_property_id is not None
        and vv.property_id == record.new_property_id
    )


def check_5_6_shared_aspect(
    records: Sequence[CellRecord],
    snapshot: ModelSnapshot,
    release: ReleaseContext,
) -> List[Violation]:
    """Aspect shared with a cell of another module, other variable.

    Union of the SQL's two 5_6 INSERTs over cells of active module
    versions (one for modules not changing in this release, one —
    flagged blocking in the SQL but reported as a warning here, see
    the module docstring — for modules changing in this release).
    """
    tvc_by_vv: Dict[int, List[Tuple[int, int, Optional[str]]]] = {}
    for tvc in snapshot.table_version_cells:
        if tvc.variable_vid is not None:
            tvc_by_vv.setdefault(tvc.variable_vid, []).append(
                (tvc.table_vid, tvc.cell_id, tvc.cell_code)
            )
    seen: Set[Tuple[int, int, int, int]] = set()
    violations = []
    for r in records:
        if (
            not release.is_current(r.mv_start)
            or r.new_vvid_ref is None
            or r.is_void
            or r.new_variable_ref is None
        ):
            continue
        for vv in snapshot.variable_versions:
            if (
                vv.end_release_id is not None
                or not _aspect_matches(r, vv)
                or vv.variable_id is None
                or vv.variable_id == r.new_variable_ref
            ):
                continue
            violations += _shared_aspect_findings(
                r, vv, tvc_by_vv, snapshot, release, seen
            )
    return violations


def _shared_aspect_findings(
    record: CellRecord,
    vv: VariableVersionRow,
    tvc_by_vv: Dict[int, List[Tuple[int, int, Optional[str]]]],
    snapshot: ModelSnapshot,
    release: ReleaseContext,
    seen: Set[Tuple[int, int, int, int]],
) -> List[Violation]:
    """5_6 findings for one (record, other variable version) pair."""
    violations = []
    for table_vid, cell_id, cell_code in tvc_by_vv.get(
        vv.variable_vid, []
    ):
        if cell_id == record.cell_id:
            continue
        for mvc in snapshot.mvc_by_table_vid().get(table_vid, []):
            mv = snapshot.module_versions_by_vid.get(mvc.module_vid)
            if mv is None or mv.end_release_id is not None:
                continue
            key = (
                record.table_vid,
                record.cell_id,
                table_vid,
                cell_id,
            )
            if key in seen:
                continue
            seen.add(key)
            message = (
                f"The cell {cell_code}, in the module {mv.code} has "
                f"the same aspects as the cell {record.cell_code} of "
                f"the current module {record.module_code} but they "
                "have different variables."
            )
            violations.append(
                _violation(
                    "5_6",
                    SEVERITY_WARNING,
                    message,
                    (
                        _cell_ref(record.cell_id, record.cell_code),
                        _cell_ref(cell_id, cell_code, "cell2"),
                        _tv_ref(snapshot, record.table_vid),
                    ),
                )
            )
    return violations


def apply_5_6_stale_modules(
    records: Sequence[CellRecord], release: ReleaseContext
) -> List[Violation]:
    """Variable also used by cells of modules not updated here.

    Overwrites the matched records' report message (SQL UPDATE) and
    returns the corresponding 5_6 warnings.
    """
    stale_codes: Dict[int, str] = {}
    for r in records:
        if (
            not release.is_current(r.mv_start)
            and r.vv_old_end is not None
            and r.old_variable_id is not None
            and r.module_code is not None
        ):
            best = stale_codes.get(r.old_variable_id)
            if best is None or r.module_code < best:
                stale_codes[r.old_variable_id] = r.module_code
    seen: Set[Tuple[int, int]] = set()
    violations = []
    for r in records:
        if not (
            release.is_current(r.tv_start)
            and not r.is_new_cell
            and r.outcome_id == "OLD"
            and r.outcome_vid == "NEW"
            and r.new_vvid_ref is not None
            and not r.is_void
            and r.old_variable_id in stale_codes
        ):
            continue
        message = (
            "Cell has new variable version, but other cells in "
            f"modules such as: {stale_codes[r.old_variable_id]}, "
            "have the same variableID with old VariableVID not "
            "being updated in this release"
        )
        r.report_msg = message
        key = (r.table_vid, r.cell_id)
        if key not in seen:
            seen.add(key)
            violations.append(
                _violation(
                    "5_6",
                    SEVERITY_WARNING,
                    message,
                    (
                        _cell_ref(r.cell_id, r.cell_code),
                        ObjectRef(kind="table_version", id=r.table_vid),
                    ),
                )
            )
    return violations
