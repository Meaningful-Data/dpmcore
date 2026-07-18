"""Family 1 modelling rules — lifecycle and versioning.

Port of the ``1_x`` INSERT blocks of ``check_modelling_rules_tidy``:
module/table/tablegroup versioning consistency, composition integrity
and table-association hygiene. Release arithmetic goes through
:class:`~dpmcore.services.model_validation.release_context
.ReleaseContext`; a plain SQL ``EndReleaseID IS NULL`` is translated
literally (``is None``) while the ``9999`` sentinel patterns use the
context predicates.

Blocks 1_10, 1_13, 1_22, 1_23 and 1_24 are commented out in the
reference SQL but remain part of the specification catalogue
(§4.4 of ``specification/08-modelling-services.md``); they are
implemented from the commented SQL text.
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
)

from dpmcore.services.model_validation.registry import (
    Finding,
    RuleContext,
    rule,
)
from dpmcore.services.model_validation.release_context import (
    ReleaseContext,
)
from dpmcore.services.model_validation.snapshot import (
    CategoryRow,
    HeaderVersionRow,
    ItemCategoryRow,
    KeyHeaderMappingRow,
    ModelSnapshot,
    ModuleVersionCompositionRow,
    ModuleVersionRow,
    PropertyCategoryRow,
    SubCategoryItemRow,
    TableAssociationRow,
    TableGroupCompositionRow,
    TableGroupRow,
    TableRow,
    TableVersionHeaderRow,
    TableVersionRow,
)
from dpmcore.services.model_validation.types import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    ObjectRef,
)

_FAMILY = "lifecycle"

_RowT = TypeVar("_RowT")
_KeyT = TypeVar("_KeyT")

#: Characters rule 1_18 forbids in templateGroup TableGroup codes.
_ILLEGAL_TG_CODE_CHARS = ("-", "–", "(", ")", ".", " ")

#: A usage of a glossary object by a table version (rule 1_15):
#: ``(source, header_code, direction, kind, object_id)`` where kind
#: is ``"property"`` or ``"item"``.
_Usage = Tuple[str, str, str, str, int]


# ------------------------------------------------------------------
# SQL-semantics helpers
# ------------------------------------------------------------------


def _is_false(flag: Optional[bool]) -> bool:
    """Mirror SQL ``column = 0``: NULL rows never match."""
    return flag is not None and not flag


def _bit_ne(a: Optional[bool], b: Optional[bool]) -> bool:
    """Mirror SQL ``a <> b`` on bit columns: NULL never differs."""
    return a is not None and b is not None and bool(a) != bool(b)


def _active_non_draft(
    rel: ReleaseContext,
    start_release_id: Optional[int],
    end_release_id: Optional[int],
) -> bool:
    """Mirror ``(End IS NULL AND Start <> 9999) OR End = 9999``.

    The recurring SQL pattern selecting versions that are open but
    not introduced only in the draft/playground release, or that were
    closed by the draft release.
    """
    if rel.is_draft(end_release_id):
        return True
    return end_release_id is None and not rel.is_draft(
        start_release_id
    )


def _group_by(
    rows: Sequence[_RowT],
    key: Callable[[_RowT], Optional[_KeyT]],
) -> Dict[_KeyT, List[_RowT]]:
    """Group rows by a key, skipping rows whose key is NULL."""
    grouped: Dict[_KeyT, List[_RowT]] = {}
    for row in rows:
        value = key(row)
        if value is not None:
            grouped.setdefault(value, []).append(row)
    return grouped


def _emit(
    findings: Dict[Tuple[Any, ...], Finding],
) -> Iterator[Finding]:
    """Yield findings ordered by their deduplication key."""
    for key in sorted(findings):
        yield findings[key]


# ------------------------------------------------------------------
# Object references
# ------------------------------------------------------------------


def _tv_ref(tv: TableVersionRow) -> ObjectRef:
    """Reference to a table version."""
    return ObjectRef(
        kind="table_version", id=tv.table_vid, code=tv.code
    )


def _mv_ref(mv: ModuleVersionRow) -> ObjectRef:
    """Reference to a module version."""
    return ObjectRef(
        kind="module_version", id=mv.module_vid, code=mv.code
    )


def _tg_ref(tg: TableGroupRow) -> ObjectRef:
    """Reference to a table group."""
    return ObjectRef(
        kind="table_group", id=tg.table_group_id, code=tg.code
    )


def _hv_ref(hv: HeaderVersionRow) -> ObjectRef:
    """Reference to a header version."""
    return ObjectRef(
        kind="header_version", id=hv.header_vid, code=hv.code
    )


def _assoc_ref(ta: TableAssociationRow) -> ObjectRef:
    """Reference to a table association."""
    return ObjectRef(
        kind="table_association", id=ta.association_id, name=ta.name
    )


# ------------------------------------------------------------------
# Shared derived indexes (cached on the snapshot)
# ------------------------------------------------------------------


def _mv_by_module(
    snap: ModelSnapshot,
) -> Dict[int, List[ModuleVersionRow]]:
    """``ModuleVersion`` rows grouped by ``module_id``."""
    return snap.cache(
        "lifecycle:mv_by_module",
        lambda: _group_by(
            snap.module_versions, lambda m: m.module_id
        ),
    )


def _mvc_by_table_id(
    snap: ModelSnapshot,
) -> Dict[int, List[ModuleVersionCompositionRow]]:
    """``ModuleVersionComposition`` rows grouped by ``table_id``."""
    return snap.cache(
        "lifecycle:mvc_by_table_id",
        lambda: _group_by(
            snap.module_version_compositions, lambda c: c.table_id
        ),
    )


def _tgc_by_table(
    snap: ModelSnapshot,
) -> Dict[int, List[TableGroupCompositionRow]]:
    """``TableGroupComposition`` rows grouped by ``table_id``."""
    return snap.cache(
        "lifecycle:tgc_by_table",
        lambda: _group_by(
            snap.table_group_compositions, lambda c: c.table_id
        ),
    )


def _tgc_by_group(
    snap: ModelSnapshot,
) -> Dict[int, List[TableGroupCompositionRow]]:
    """``TableGroupComposition`` rows grouped by group id."""
    return snap.cache(
        "lifecycle:tgc_by_group",
        lambda: _group_by(
            snap.table_group_compositions,
            lambda c: c.table_group_id,
        ),
    )


def _khm_by_assoc(
    snap: ModelSnapshot,
) -> Dict[int, List[KeyHeaderMappingRow]]:
    """``KeyHeaderMapping`` rows grouped by ``association_id``."""
    return snap.cache(
        "lifecycle:khm_by_assoc",
        lambda: _group_by(
            snap.key_header_mappings, lambda k: k.association_id
        ),
    )


def _ic_by_item(
    snap: ModelSnapshot,
) -> Dict[int, List[ItemCategoryRow]]:
    """``ItemCategory`` rows grouped by ``item_id``."""
    return snap.cache(
        "lifecycle:ic_by_item",
        lambda: _group_by(snap.item_categories, lambda i: i.item_id),
    )


def _pc_by_property(
    snap: ModelSnapshot,
) -> Dict[int, List[PropertyCategoryRow]]:
    """``PropertyCategory`` rows grouped by ``property_id``."""
    return snap.cache(
        "lifecycle:pc_by_property",
        lambda: _group_by(
            snap.property_categories, lambda p: p.property_id
        ),
    )


def _sci_by_scv(
    snap: ModelSnapshot,
) -> Dict[int, List[SubCategoryItemRow]]:
    """``SubCategoryItem`` rows grouped by ``subcategory_vid``."""
    return snap.cache(
        "lifecycle:sci_by_scv",
        lambda: _group_by(
            snap.subcategory_items, lambda s: s.subcategory_vid
        ),
    )


def _tv_by_abstract(
    snap: ModelSnapshot,
) -> Dict[int, List[TableVersionRow]]:
    """``TableVersion`` rows grouped by ``abstract_table_id``."""
    return snap.cache(
        "lifecycle:tv_by_abstract",
        lambda: _group_by(
            snap.table_versions, lambda t: t.abstract_table_id
        ),
    )


def _tv_by_trimmed_name(
    snap: ModelSnapshot,
) -> Dict[str, List[TableVersionRow]]:
    """``TableVersion`` rows grouped by trimmed name."""
    return snap.cache(
        "lifecycle:tv_by_trimmed_name",
        lambda: _group_by(
            snap.table_versions,
            lambda t: t.name.strip() if t.name is not None else None,
        ),
    )


def _current_open_tvs(
    ctx: RuleContext,
) -> List[Tuple[TableVersionRow, TableRow]]:
    """Open TableVersions starting in the current release, in a module.

    Mirrors ``TableVersion JOIN Table JOIN ModuleVersionComposition
    JOIN ModuleVersion WHERE tv.EndReleaseID IS NULL AND
    tv.StartReleaseID = @CurrentRelease`` (no filter on the module
    version itself).
    """
    snap, rel = ctx.snapshot, ctx.release

    def build() -> List[Tuple[TableVersionRow, TableRow]]:
        in_module = snap.mvc_by_table_vid()
        rows: List[Tuple[TableVersionRow, TableRow]] = []
        for tv in snap.table_versions:
            if tv.end_release_id is not None:
                continue
            if not rel.starts_in_current(tv.start_release_id):
                continue
            if not any(
                mvc.module_vid in snap.module_versions_by_vid
                for mvc in in_module.get(tv.table_vid, [])
            ):
                continue
            table = (
                snap.tables_by_id.get(tv.table_id)
                if tv.table_id is not None
                else None
            )
            if table is None:
                continue
            rows.append((tv, table))
        rows.sort(key=lambda pair: pair[0].table_vid)
        return rows

    return snap.cache("lifecycle:current_open_tvs", build)


def _tvs_in_new_modules(
    ctx: RuleContext,
) -> List[Tuple[TableVersionRow, TableRow]]:
    """TableVersions composed into a ModuleVersion starting now.

    Mirrors ``TableVersion JOIN Table JOIN ModuleVersionComposition
    JOIN ModuleVersion WHERE mv.StartReleaseID = @CurrentRelease``.
    """
    snap, rel = ctx.snapshot, ctx.release

    def build() -> List[Tuple[TableVersionRow, TableRow]]:
        rows: List[Tuple[TableVersionRow, TableRow]] = []
        for tv in snap.table_versions:
            memberships = snap.mvc_by_table_vid().get(
                tv.table_vid, []
            )
            if not any(
                _starts_now(snap, rel, mvc.module_vid)
                for mvc in memberships
            ):
                continue
            table = (
                snap.tables_by_id.get(tv.table_id)
                if tv.table_id is not None
                else None
            )
            if table is None:
                continue
            rows.append((tv, table))
        rows.sort(key=lambda pair: pair[0].table_vid)
        return rows

    return snap.cache("lifecycle:tvs_in_new_modules", build)


def _starts_now(
    snap: ModelSnapshot, rel: ReleaseContext, module_vid: int
) -> bool:
    """True when the module version exists and starts now."""
    mv = snap.module_versions_by_vid.get(module_vid)
    return mv is not None and rel.starts_in_current(
        mv.start_release_id
    )


def _tvs_in_active_modules(ctx: RuleContext) -> Set[int]:
    """TableVIDs composed into an active, non-draft ModuleVersion."""
    snap, rel = ctx.snapshot, ctx.release

    def build() -> Set[int]:
        vids: Set[int] = set()
        for mvc in snap.module_version_compositions:
            if mvc.table_vid is None:
                continue
            mv = snap.module_versions_by_vid.get(mvc.module_vid)
            if mv is not None and _active_non_draft(
                rel, mv.start_release_id, mv.end_release_id
            ):
                vids.add(mvc.table_vid)
        return vids

    return snap.cache("lifecycle:tvs_in_active_modules", build)


# ------------------------------------------------------------------
# Rule 1_1
# ------------------------------------------------------------------


_HvFields = Tuple[
    Optional[str],
    Optional[str],
    Optional[int],
    Optional[int],
    Optional[int],
]

#: Field tuple of an absent HeaderVersion (all columns NULL).
_NULL_HV_FIELDS: _HvFields = (None, None, None, None, None)


def _hv_fields(hv: HeaderVersionRow) -> _HvFields:
    """Compared HeaderVersion fields, with ISNULL-sentinel semantics.

    The SQL compares each field through ``ISNULL(x, sentinel)``,
    which makes NULL equal to NULL — exactly Python ``None == None``.
    """
    return (
        hv.code,
        hv.label,
        hv.context_id,
        hv.property_id,
        hv.subcategory_vid,
    )


@rule(
    "1_1",
    legacy_code="1_1",
    family=_FAMILY,
    severity=SEVERITY_WARNING,
    description=(
        "Header has current version identical to previous version"
    ),
)
def rule_1_1(ctx: RuleContext) -> Iterator[Finding]:
    """A new HeaderVersion must differ from its predecessor.

    For every open, current-release TableVersion of a non-abstract
    table, each non-key header attached through a non-abstract
    TableVersionHeader row is checked: an open HeaderVersion whose
    compared fields (code, label, context, property, subcategory)
    equal those of the version it superseded
    (``hv2.EndReleaseID = hv.StartReleaseID``) is a violation.
    """
    snap = ctx.snapshot
    for tv, table in _current_open_tvs(ctx):
        if not _is_false(table.is_abstract):
            continue
        for tvh in snap.tvh_by_table_vid().get(tv.table_vid, []):
            if not _is_false(tvh.is_abstract):
                continue
            header = snap.headers_by_id.get(tvh.header_id)
            if (
                header is None
                or header.table_id != table.table_id
                or not _is_false(header.is_key)
            ):
                continue
            yield from _header_version_repeats(
                snap, tv, header.header_id
            )


def _header_version_repeats(
    snap: ModelSnapshot, tv: TableVersionRow, header_id: int
) -> Iterator[Finding]:
    """Findings for open header versions equal to their predecessor."""
    versions = snap.header_versions_by_header().get(header_id, [])
    for hv in versions:
        if hv.end_release_id is not None:
            continue
        for hv2 in versions:
            if (
                hv2.end_release_id is None
                or hv2.end_release_id != hv.start_release_id
            ):
                continue
            if _hv_fields(hv) != _hv_fields(hv2):
                continue
            yield Finding(
                objects=(_hv_ref(hv), _hv_ref(hv2), _tv_ref(tv))
            )


# ------------------------------------------------------------------
# Rule 1_2
# ------------------------------------------------------------------


@rule(
    "1_2",
    legacy_code="1_2",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "TableVersion fields identical to previous TableVersion"
    ),
)
def rule_1_2(ctx: RuleContext) -> Iterator[Finding]:
    """A new TableVersion must differ from its predecessor.

    Compares the open, current-release TableVersion of a
    non-abstract table with the version it superseded
    (``tv2.EndReleaseID = tv.StartReleaseID``): scalar fields,
    TableVersionHeader rows (matched by HeaderID, including the
    referenced HeaderVersion fields) and TableVersionCell rows
    (matched by CellID) must all be identical for the rule to fire.
    """
    snap = ctx.snapshot
    for tv, table in _current_open_tvs(ctx):
        if not _is_false(table.is_abstract):
            continue
        candidates = snap.table_versions_by_table().get(
            table.table_id, []
        )
        for tv2 in candidates:
            if (
                tv2.end_release_id is None
                or tv2.end_release_id != tv.start_release_id
            ):
                continue
            if not _tv_fields_equal(tv, tv2):
                continue
            if not _tvh_sets_identical(
                snap, tv.table_vid, tv2.table_vid
            ):
                continue
            if not _tvc_sets_identical(
                snap, tv.table_vid, tv2.table_vid
            ):
                continue
            yield Finding(objects=(_tv_ref(tv), _tv_ref(tv2)))


def _tv_fields_equal(a: TableVersionRow, b: TableVersionRow) -> bool:
    """ISNULL-sentinel equality of the compared TableVersion fields."""
    return (
        a.code,
        a.name,
        a.context_id,
        a.property_id,
        a.key_id,
    ) == (b.code, b.name, b.context_id, b.property_id, b.key_id)


def _tvh_sets_identical(
    snap: ModelSnapshot, new_vid: int, old_vid: int
) -> bool:
    """True when the TableVersionHeader rows of both versions match.

    Mirrors the SQL: equal row counts and, for every row of the new
    version that joins a HeaderVersion, a row of the old version
    with the same HeaderID whose compared fields do not differ.
    """
    rows_new = snap.tvh_by_table_vid().get(new_vid, [])
    rows_old = snap.tvh_by_table_vid().get(old_vid, [])
    if len(rows_new) != len(rows_old):
        return False
    old_by_header = {row.header_id: row for row in rows_old}
    for tvh in rows_new:
        hv = (
            snap.header_versions_by_vid.get(tvh.header_vid)
            if tvh.header_vid is not None
            else None
        )
        if hv is None:
            continue
        tvh2 = old_by_header.get(tvh.header_id)
        if tvh2 is None:
            return False
        hv2 = (
            snap.header_versions_by_vid.get(tvh2.header_vid)
            if tvh2.header_vid is not None
            else None
        )
        if _tvh_pair_differs(tvh, hv, tvh2, hv2):
            return False
    return True


def _tvh_pair_differs(
    tvh: TableVersionHeaderRow,
    hv: HeaderVersionRow,
    tvh2: TableVersionHeaderRow,
    hv2: Optional[HeaderVersionRow],
) -> bool:
    """Field-level comparison of one TableVersionHeader pair.

    ``ISNULL``-sentinel fields treat NULL as equal to NULL; the
    plain ``isAbstract``/``isUnique`` bit comparisons never differ
    on NULL.
    """
    if (
        tvh.header_id,
        tvh.header_vid,
        tvh.parent_header_id,
        tvh.order,
    ) != (
        tvh2.header_id,
        tvh2.header_vid,
        tvh2.parent_header_id,
        tvh2.order,
    ):
        return True
    if _bit_ne(tvh.is_abstract, tvh2.is_abstract) or _bit_ne(
        tvh.is_unique, tvh2.is_unique
    ):
        return True
    fields2 = (
        _hv_fields(hv2) if hv2 is not None else _NULL_HV_FIELDS
    )
    return _hv_fields(hv) != fields2


def _tvc_sets_identical(
    snap: ModelSnapshot, new_vid: int, old_vid: int
) -> bool:
    """True when the TableVersionCell rows of both versions match.

    Mirrors the SQL: equal row counts and no cell present in both
    versions (the WHERE clause turns the outer join into an inner
    one) whose compared fields differ. Cells missing from the Cell
    table are skipped, as the SQL inner-joins ``Cell``.
    """
    rows_new = snap.tvc_by_table_vid().get(new_vid, [])
    rows_old = snap.tvc_by_table_vid().get(old_vid, [])
    if len(rows_new) != len(rows_old):
        return False
    old_by_cell = {row.cell_id: row for row in rows_old}
    for tvc in rows_new:
        if tvc.cell_id not in snap.cells_by_id:
            continue
        tvc2 = old_by_cell.get(tvc.cell_id)
        if tvc2 is None:
            continue
        if tvc.cell_code != tvc2.cell_code or tvc.sign != tvc2.sign:
            return False
        if (
            _bit_ne(tvc.is_nullable, tvc2.is_nullable)
            or _bit_ne(tvc.is_excluded, tvc2.is_excluded)
            or _bit_ne(tvc.is_void, tvc2.is_void)
        ):
            return False
    return True


# ------------------------------------------------------------------
# Rules 1_3 / 1_4
# ------------------------------------------------------------------


@rule(
    "1_3",
    legacy_code="1_3",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "TableVersion with non-null AbstractTableID in a "
        "ModuleVersionComposition whose abstract table is absent "
        "from the same ModuleVersion"
    ),
)
def rule_1_3(ctx: RuleContext) -> Iterator[Finding]:
    """Technical tables must ship with their abstract table.

    For every composition row of a ModuleVersion starting in the
    current release whose non-abstract TableVersion references an
    AbstractTableID, that table id must also appear (as ``TableID``)
    in the same ModuleVersion's composition.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for mvc in snap.module_version_compositions:
        mv = snap.module_versions_by_vid.get(mvc.module_vid)
        if mv is None or not rel.starts_in_current(
            mv.start_release_id
        ):
            continue
        tv = (
            snap.table_versions_by_vid.get(mvc.table_vid)
            if mvc.table_vid is not None
            else None
        )
        if tv is None or tv.abstract_table_id is None:
            continue
        table = (
            snap.tables_by_id.get(tv.table_id)
            if tv.table_id is not None
            else None
        )
        if table is None or not _is_false(table.is_abstract):
            continue
        module_tables = {
            row.table_id
            for row in snap.mvc_by_module_vid().get(
                mvc.module_vid, []
            )
        }
        if tv.abstract_table_id in module_tables:
            continue
        key = (tv.table_vid, mv.module_vid)
        findings.setdefault(
            key, Finding(objects=(_tv_ref(tv), _mv_ref(mv)))
        )
    yield from _emit(findings)


@rule(
    "1_4",
    legacy_code="1_4",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Abstract table in ModuleVersionComposition without any "
        "non-abstract table for the same ModuleVersion"
    ),
)
def rule_1_4(ctx: RuleContext) -> Iterator[Finding]:
    """Abstract tables must ship with a technical table.

    For every composition row of a ModuleVersion starting in the
    current release whose table is abstract, the same ModuleVersion
    must contain a non-abstract TableVersion whose AbstractTableID
    is that table. SQL ``NOT IN`` semantics: a NULL AbstractTableID
    in the compared set suppresses the violation.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for mvc in snap.module_version_compositions:
        mv = snap.module_versions_by_vid.get(mvc.module_vid)
        if mv is None or not rel.starts_in_current(
            mv.start_release_id
        ):
            continue
        tv = (
            snap.table_versions_by_vid.get(mvc.table_vid)
            if mvc.table_vid is not None
            else None
        )
        if tv is None or tv.table_id is None:
            continue
        table = snap.tables_by_id.get(tv.table_id)
        if table is None or not bool(table.is_abstract):
            continue
        abstract_ids = _module_abstract_ids(snap, mvc.module_vid)
        if table.table_id in abstract_ids or None in abstract_ids:
            continue
        key = (tv.table_vid, mv.module_vid)
        findings.setdefault(
            key, Finding(objects=(_tv_ref(tv), _mv_ref(mv)))
        )
    yield from _emit(findings)


def _module_abstract_ids(
    snap: ModelSnapshot, module_vid: int
) -> Set[Optional[int]]:
    """AbstractTableIDs of the non-abstract tables of a module."""
    ids: Set[Optional[int]] = set()
    for row in snap.mvc_by_module_vid().get(module_vid, []):
        tv2 = (
            snap.table_versions_by_vid.get(row.table_vid)
            if row.table_vid is not None
            else None
        )
        if tv2 is None or tv2.table_id is None:
            continue
        t2 = snap.tables_by_id.get(tv2.table_id)
        if t2 is None or not _is_false(t2.is_abstract):
            continue
        ids.add(tv2.abstract_table_id)
    return ids


# ------------------------------------------------------------------
# Rule 1_5
# ------------------------------------------------------------------


@rule(
    "1_5",
    legacy_code="1_5",
    family=_FAMILY,
    severity=SEVERITY_WARNING,
    description="Duplicate table code",
)
def rule_1_5(ctx: RuleContext) -> Iterator[Finding]:
    """A TableVersion code must always belong to one table.

    Open TableVersions starting in the current release and composed
    into a module version with ``EndReleaseID IS NULL`` fire when
    the trimmed code also belongs to a different TableID employed by
    an active (non-draft) module version.
    """
    snap, rel = ctx.snapshot, ctx.release
    open_member = {
        mvc.table_vid
        for mvc in snap.module_version_compositions
        if mvc.table_vid is not None
        and _open_module(snap, mvc.module_vid)
    }
    code_owners = _active_module_table_codes(ctx)
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv in snap.table_versions:
        if tv.end_release_id is not None:
            continue
        if not rel.starts_in_current(tv.start_release_id):
            continue
        if tv.table_vid not in open_member or tv.code is None:
            continue
        owners = code_owners.get(tv.code.strip(), set())
        if any(table_id != tv.table_id for table_id in owners):
            findings.setdefault(
                (tv.table_vid,), Finding(objects=(_tv_ref(tv),))
            )
    yield from _emit(findings)


def _open_module(snap: ModelSnapshot, module_vid: int) -> bool:
    """True when the module version exists and has a NULL end."""
    mv = snap.module_versions_by_vid.get(module_vid)
    return mv is not None and mv.end_release_id is None


def _active_module_table_codes(
    ctx: RuleContext,
) -> Dict[str, Set[int]]:
    """Trimmed TableVersion code -> TableIDs in active modules."""
    snap, rel = ctx.snapshot, ctx.release

    def build() -> Dict[str, Set[int]]:
        owners: Dict[str, Set[int]] = {}
        for mvc in snap.module_version_compositions:
            mv = snap.module_versions_by_vid.get(mvc.module_vid)
            if mv is None or not _active_non_draft(
                rel, mv.start_release_id, mv.end_release_id
            ):
                continue
            tv = (
                snap.table_versions_by_vid.get(mvc.table_vid)
                if mvc.table_vid is not None
                else None
            )
            if tv is None or tv.code is None or tv.table_id is None:
                continue
            owners.setdefault(tv.code.strip(), set()).add(
                tv.table_id
            )
        return owners

    return snap.cache("lifecycle:active_module_table_codes", build)


# ------------------------------------------------------------------
# Rule 1_6
# ------------------------------------------------------------------


@rule(
    "1_6",
    legacy_code="1_6",
    family=_FAMILY,
    severity=SEVERITY_WARNING,
    description="Abstract table found in composition of a TableGroup",
)
def rule_1_6(ctx: RuleContext) -> Iterator[Finding]:
    """TableGroups should not contain abstract tables.

    For every open TableGroupComposition row starting in the current
    release whose table is abstract, each open TableVersion of that
    table that is employed by any module version is reported
    together with the table group.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tgc in snap.table_group_compositions:
        if not rel.starts_in_current(tgc.start_release_id):
            continue
        if tgc.end_release_id is not None:
            continue
        tg = snap.table_groups_by_id.get(tgc.table_group_id)
        table = snap.tables_by_id.get(tgc.table_id)
        if (
            tg is None
            or table is None
            or not bool(table.is_abstract)
        ):
            continue
        for tv in snap.table_versions_by_table().get(
            tgc.table_id, []
        ):
            if tv.end_release_id is not None:
                continue
            if not any(
                mvc.module_vid in snap.module_versions_by_vid
                for mvc in snap.mvc_by_table_vid().get(
                    tv.table_vid, []
                )
            ):
                continue
            key = (tv.table_vid, tg.table_group_id)
            findings.setdefault(
                key, Finding(objects=(_tv_ref(tv), _tg_ref(tg)))
            )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rules 1_7 / 1_8 / 1_9
# ------------------------------------------------------------------


@rule(
    "1_7",
    legacy_code="1_7",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Expired TableVersion referenced by an active ModuleVersion"
    ),
)
def rule_1_7(ctx: RuleContext) -> Iterator[Finding]:
    """ModuleVersions starting now must reference live TableVersions.

    Fires for every composition row of a ModuleVersion starting in
    the current release whose TableVersion is expired
    (``EndReleaseID IS NOT NULL``) or starts in the draft release.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for mvc in snap.module_version_compositions:
        mv = snap.module_versions_by_vid.get(mvc.module_vid)
        if mv is None or not rel.starts_in_current(
            mv.start_release_id
        ):
            continue
        tv = (
            snap.table_versions_by_vid.get(mvc.table_vid)
            if mvc.table_vid is not None
            else None
        )
        if tv is None:
            continue
        if tv.end_release_id is None and not rel.is_draft(
            tv.start_release_id
        ):
            continue
        release = (
            snap.releases_by_id.get(mv.start_release_id)
            if mv.start_release_id is not None
            else None
        )
        if release is None:
            continue
        message = (
            "Expired TableVersion in an Active ModuleVersion with "
            f"StartRelease={release.code}: One way to update is to "
            "create New ModuleVersion in this Release and update to "
            "latest active TableVersion"
        )
        key = (tv.table_vid, mv.module_vid)
        findings.setdefault(
            key,
            Finding(
                objects=(_tv_ref(tv), _mv_ref(mv)), message=message
            ),
        )
    yield from _emit(findings)


@rule(
    "1_8",
    legacy_code="1_8",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "New ModuleVersion with empty ModuleVersionComposition"
    ),
)
def rule_1_8(ctx: RuleContext) -> Iterator[Finding]:
    """New ModuleVersions must contain at least one table.

    Fires for every ModuleVersion starting in the current release
    whose module is not a document module and whose ModuleVID has no
    ModuleVersionComposition row.
    """
    snap, rel = ctx.snapshot, ctx.release
    composed = {
        mvc.module_vid for mvc in snap.module_version_compositions
    }
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for mv in snap.module_versions:
        if not rel.starts_in_current(mv.start_release_id):
            continue
        module = (
            snap.modules_by_id.get(mv.module_id)
            if mv.module_id is not None
            else None
        )
        if module is None or not _is_false(
            module.is_document_module
        ):
            continue
        if mv.module_vid in composed:
            continue
        findings.setdefault(
            (mv.module_vid,), Finding(objects=(_mv_ref(mv),))
        )
    yield from _emit(findings)


@rule(
    "1_9",
    legacy_code="1_9",
    family=_FAMILY,
    severity=SEVERITY_WARNING,
    description=(
        "New ModuleVersion with composition identical to the "
        "previous ModuleVersion"
    ),
)
def rule_1_9(ctx: RuleContext) -> Iterator[Finding]:
    """New ModuleVersions must change their composition.

    Fires when the TableVIDs composed into a ModuleVersion starting
    in the current release exactly match the union of the TableVIDs
    of the module's versions closed by the current release, provided
    another non-draft version of the module exists. SQL ``NOT IN``
    semantics are preserved for NULL TableVIDs.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for mv in snap.module_versions:
        if not rel.starts_in_current(mv.start_release_id):
            continue
        module = (
            snap.modules_by_id.get(mv.module_id)
            if mv.module_id is not None
            else None
        )
        if module is None or not _is_false(
            module.is_document_module
        ):
            continue
        siblings = (
            _mv_by_module(snap).get(mv.module_id, [])
            if mv.module_id is not None
            else []
        )
        if not any(
            s.module_vid != mv.module_vid
            and not rel.is_draft(s.start_release_id)
            for s in siblings
        ):
            continue
        if _composition_repeated(ctx, mv, siblings):
            findings.setdefault(
                (mv.module_vid,), Finding(objects=(_mv_ref(mv),))
            )
    yield from _emit(findings)


def _composition_repeated(
    ctx: RuleContext,
    mv: ModuleVersionRow,
    siblings: Sequence[ModuleVersionRow],
) -> bool:
    """True when ``mv`` repeats the just-closed composition."""
    snap, rel = ctx.snapshot, ctx.release
    new_vids = [
        row.table_vid
        for row in snap.mvc_by_module_vid().get(mv.module_vid, [])
    ]
    old_vids = [
        row.table_vid
        for sibling in siblings
        if rel.ends_in_current(sibling.end_release_id)
        for row in snap.mvc_by_module_vid().get(
            sibling.module_vid, []
        )
    ]
    new_set = {vid for vid in new_vids if vid is not None}
    old_set = {vid for vid in old_vids if vid is not None}
    new_has_null = any(vid is None for vid in new_vids)
    old_has_null = any(vid is None for vid in old_vids)
    if (new_set - old_set) and not old_has_null:
        return False
    return not ((old_set - new_set) and not new_has_null)


# ------------------------------------------------------------------
# Rule 1_10 (commented out in the reference SQL)
# ------------------------------------------------------------------


@rule(
    "1_10",
    legacy_code="1_10",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Table not assigned to any module but present in a "
        "TableGroup composition"
    ),
)
def rule_1_10(ctx: RuleContext) -> Iterator[Finding]:
    """TableGroups should only contain module-assigned tables.

    For every open TableGroupComposition row starting in the current
    release, the table must appear (by TableID) in the composition
    of a module version that is open or ends in the draft release.

    Note:
        This block is commented out in the reference SQL; it is
        implemented from the commented text per the specification
        catalogue.
    """
    snap, rel = ctx.snapshot, ctx.release
    assigned = {
        mvc.table_id
        for mvc in snap.module_version_compositions
        if _module_is_open(snap, rel, mvc.module_vid)
    }
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tgc in snap.table_group_compositions:
        if not rel.starts_in_current(tgc.start_release_id):
            continue
        if tgc.end_release_id is not None:
            continue
        tg = snap.table_groups_by_id.get(tgc.table_group_id)
        table = snap.tables_by_id.get(tgc.table_id)
        if tg is None or table is None:
            continue
        if tgc.table_id in assigned:
            continue
        for tv in snap.table_versions_by_table().get(
            tgc.table_id, []
        ):
            if tv.end_release_id is not None:
                continue
            key = (tv.table_vid, tg.table_group_id)
            findings.setdefault(
                key, Finding(objects=(_tv_ref(tv), _tg_ref(tg)))
            )
    yield from _emit(findings)


def _module_is_open(
    snap: ModelSnapshot, rel: ReleaseContext, module_vid: int
) -> bool:
    """True when the module version exists and is open (or draft)."""
    mv = snap.module_versions_by_vid.get(module_vid)
    return mv is not None and rel.is_open(mv.end_release_id)


# ------------------------------------------------------------------
# Rules 1_11 / 1_12 / 1_13
# ------------------------------------------------------------------


@rule(
    "1_11",
    legacy_code="1_11",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Table does not belong to exactly one templateGroup "
        "TableGroup"
    ),
)
def rule_1_11(ctx: RuleContext) -> Iterator[Finding]:
    """Tables must belong to exactly one templateGroup.

    Non-abstract TableVersions composed into a ModuleVersion
    starting in the current release fire when the number of distinct
    active (non-draft) templateGroup TableGroups containing the
    table (via active composition rows) differs from one.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table in _tvs_in_new_modules(ctx):
        if not _is_false(table.is_abstract):
            continue
        groups: Set[int] = set()
        for tgc in _tgc_by_table(snap).get(table.table_id, []):
            if not _active_non_draft(
                rel, tgc.start_release_id, tgc.end_release_id
            ):
                continue
            tg = snap.table_groups_by_id.get(tgc.table_group_id)
            if tg is None or tg.type != "templateGroup":
                continue
            if not _active_non_draft(
                rel, tg.start_release_id, tg.end_release_id
            ):
                continue
            groups.add(tgc.table_group_id)
        if len(groups) != 1:
            findings.setdefault(
                (tv.table_vid,), Finding(objects=(_tv_ref(tv),))
            )
    yield from _emit(findings)


@rule(
    "1_12",
    legacy_code="1_12",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "TableGroup whose active tables do not all share at least "
        "one common active ModuleVersion"
    ),
)
def rule_1_12(ctx: RuleContext) -> Iterator[Finding]:
    """All active tables of a templateGroup must move together.

    For every active (non-draft) templateGroup, fires when a
    ModuleVersion starting in the current release covers some — but
    not all — of the group's tables that sit in an open composition
    row and still have an open TableVersion. Coverage is by TableID.
    """
    snap, rel = ctx.snapshot, ctx.release
    new_mvs = [
        mv
        for mv in snap.module_versions
        if rel.starts_in_current(mv.start_release_id)
    ]
    open_tables = {
        tv.table_id
        for tv in snap.table_versions
        if tv.end_release_id is None and tv.table_id is not None
    }
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tg in snap.table_groups:
        if tg.type != "templateGroup" or not _active_non_draft(
            rel, tg.start_release_id, tg.end_release_id
        ):
            continue
        total = {
            tgc.table_id
            for tgc in _tgc_by_group(snap).get(
                tg.table_group_id, []
            )
            if tgc.end_release_id is None
            and tgc.table_id in open_tables
        }
        if _group_split_by_module(snap, new_mvs, total):
            findings.setdefault(
                (tg.table_group_id,),
                Finding(objects=(_tg_ref(tg),)),
            )
    yield from _emit(findings)


def _group_split_by_module(
    snap: ModelSnapshot,
    new_mvs: Sequence[ModuleVersionRow],
    group_tables: Set[int],
) -> bool:
    """True when a new module covers part of the group's tables."""
    for mv in new_mvs:
        module_tables = {
            row.table_id
            for row in snap.mvc_by_module_vid().get(
                mv.module_vid, []
            )
        }
        covered = group_tables & module_tables
        if covered and covered != group_tables:
            return True
    return False


@rule(
    "1_13",
    legacy_code="1_13",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Table belongs to no templateGroup TableGroup",
)
def rule_1_13(ctx: RuleContext) -> Iterator[Finding]:
    """Every active table must belong to a templateGroup.

    Open, non-abstract TableVersions composed into a ModuleVersion
    starting in the current release fire when the table sits in no
    open templateGroup composition while still being employed (by
    TableID) by an open module version.

    Note:
        This block is commented out in the reference SQL; it is
        implemented from the commented text per the specification
        catalogue.
    """
    snap = ctx.snapshot
    template_tables = {
        tgc.table_id
        for tgc in snap.table_group_compositions
        if tgc.end_release_id is None
        and _open_template_group(snap, tgc.table_group_id)
    }
    employed = {
        mvc.table_id
        for mvc in snap.module_version_compositions
        if _open_module(snap, mvc.module_vid)
    }
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table in _tvs_in_new_modules(ctx):
        if tv.end_release_id is not None:
            continue
        if not _is_false(table.is_abstract):
            continue
        if table.table_id in template_tables:
            continue
        if table.table_id not in employed:
            continue
        findings.setdefault(
            (tv.table_vid,), Finding(objects=(_tv_ref(tv),))
        )
    yield from _emit(findings)


def _open_template_group(
    snap: ModelSnapshot, table_group_id: int
) -> bool:
    """True for an existing open templateGroup TableGroup."""
    tg = snap.table_groups_by_id.get(table_group_id)
    return (
        tg is not None
        and tg.type == "templateGroup"
        and tg.end_release_id is None
    )


# ------------------------------------------------------------------
# Rule 1_14
# ------------------------------------------------------------------


@rule(
    "1_14",
    legacy_code="1_14",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "ModuleVersion number not greater than the previous "
        "version's number"
    ),
)
def rule_1_14(ctx: RuleContext) -> Iterator[Finding]:
    """Module version numbers must strictly increase.

    A ModuleVersion starting in the current release fires when its
    version number is NULL, or when another version of the same
    module has a non-NULL version number greater than or equal to it
    (string comparison, as ``VersionNumber`` is a varchar).
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for mv in snap.module_versions:
        if not rel.starts_in_current(mv.start_release_id):
            continue
        siblings = (
            _mv_by_module(snap).get(mv.module_id, [])
            if mv.module_id is not None
            else []
        )
        if _version_number_not_greater(mv, siblings):
            findings.setdefault(
                (mv.module_vid,), Finding(objects=(_mv_ref(mv),))
            )
    yield from _emit(findings)


def _version_number_not_greater(
    mv: ModuleVersionRow, siblings: Sequence[ModuleVersionRow]
) -> bool:
    """True when the version number is NULL or not the greatest."""
    if mv.version_number is None:
        return True
    return any(
        other.module_vid != mv.module_vid
        and other.version_number is not None
        and other.version_number >= mv.version_number
        for other in siblings
    )


# ------------------------------------------------------------------
# Rule 1_15
# ------------------------------------------------------------------


def _changed_properties(ctx: RuleContext) -> Set[int]:
    """Properties whose ItemCategory/PropertyCategory changed now.

    A property qualifies when it has an open ItemCategory row and an
    open PropertyCategory row and at least one of them starts in the
    current release.
    """
    snap, rel = ctx.snapshot, ctx.release

    def build() -> Set[int]:
        open_items: Set[int] = set()
        current_items: Set[int] = set()
        for ic in snap.item_categories:
            if ic.end_release_id is not None:
                continue
            open_items.add(ic.item_id)
            if rel.is_current(ic.start_release_id):
                current_items.add(ic.item_id)
        open_props: Set[int] = set()
        current_props: Set[int] = set()
        for pc in snap.property_categories:
            if pc.end_release_id is not None:
                continue
            open_props.add(pc.property_id)
            if rel.is_current(pc.start_release_id):
                current_props.add(pc.property_id)
        return {
            pid
            for pid in open_items & open_props
            if pid in current_items or pid in current_props
        }

    return snap.cache("lifecycle:changed_properties", build)


def _changed_items(ctx: RuleContext) -> Set[int]:
    """Items with an open ItemCategory row starting now."""
    snap, rel = ctx.snapshot, ctx.release

    def build() -> Set[int]:
        return {
            ic.item_id
            for ic in snap.item_categories
            if ic.end_release_id is None
            and rel.is_current(ic.start_release_id)
        }

    return snap.cache("lifecycle:changed_items", build)


def _tv_level_usages(
    snap: ModelSnapshot, tv: TableVersionRow
) -> Iterator[_Usage]:
    """Rule 1_15 usages attached directly to the TableVersion."""
    if tv.context_id is not None:
        for cc in snap.context_compositions_by_context().get(
            tv.context_id, []
        ):
            yield (
                "table_context", "", "", "property", cc.property_id,
            )
            if cc.item_id is not None:
                yield (
                    "table_context_item", "", "", "item", cc.item_id,
                )
    if tv.property_id is not None:
        yield ("table+property", "", "", "property", tv.property_id)


def _header_usages(
    snap: ModelSnapshot, tv: TableVersionRow
) -> Iterator[_Usage]:
    """Rule 1_15 usages attached through the table's headers."""
    for tvh in snap.tvh_by_table_vid().get(tv.table_vid, []):
        hv = (
            snap.header_versions_by_vid.get(tvh.header_vid)
            if tvh.header_vid is not None
            else None
        )
        if hv is None:
            continue
        header = (
            snap.headers_by_id.get(hv.header_id)
            if hv.header_id is not None
            else None
        )
        if header is None:
            continue
        code = hv.code or ""
        direction = header.direction or ""
        if hv.context_id is not None:
            for cc in snap.context_compositions_by_context().get(
                hv.context_id, []
            ):
                yield (
                    "header_context", code, direction, "property",
                    cc.property_id,
                )
                if cc.item_id is not None:
                    yield (
                        "header_context_item", code, direction,
                        "item", cc.item_id,
                    )
        if hv.property_id is not None:
            yield (
                "header_property", code, direction, "property",
                hv.property_id,
            )
        if hv.subcategory_vid is not None:
            for sci in _sci_by_scv(snap).get(hv.subcategory_vid, []):
                yield (
                    "header_subcategory_item", code, direction,
                    "item", sci.item_id,
                )


def _variable_usages(
    snap: ModelSnapshot, tv: TableVersionRow
) -> Iterator[_Usage]:
    """Rule 1_15 usages attached through the table's cell variables."""
    for tvc in snap.tvc_by_table_vid().get(tv.table_vid, []):
        vv = (
            snap.variable_versions_by_vid.get(tvc.variable_vid)
            if tvc.variable_vid is not None
            else None
        )
        if vv is None:
            continue
        if vv.context_id is not None:
            for cc in snap.context_compositions_by_context().get(
                vv.context_id, []
            ):
                yield (
                    "variable_context", "", "", "property",
                    cc.property_id,
                )
                if cc.item_id is not None:
                    yield (
                        "variable_context_item", "", "", "item",
                        cc.item_id,
                    )
        if vv.property_id is not None:
            yield (
                "variable_property", "", "", "property",
                vv.property_id,
            )


def _open_item_category(
    snap: ModelSnapshot, item_id: int
) -> Optional[ItemCategoryRow]:
    """The open ItemCategory row of an item (earliest start wins)."""
    best: Optional[ItemCategoryRow] = None
    for ic in _ic_by_item(snap).get(item_id, []):
        if ic.end_release_id is not None:
            continue
        if (
            best is None
            or ic.start_release_id < best.start_release_id
        ):
            best = ic
    return best


def _finding_1_15(
    snap: ModelSnapshot,
    mv_code: str,
    tv_code: Optional[str],
    usage: _Usage,
    property_id: Optional[int],
    item_id: int,
) -> Finding:
    """Assemble one 1_15 finding (dynamic message + objects)."""
    source, header_code, direction, _kind, _object_id = usage
    message = (
        "ItemCategory or PropertyCategory have changed with impact "
        f'in: "{source}". But no New ModuleVersion for '
        f"Module:{mv_code} has been created"
    )
    objects: List[ObjectRef] = [
        ObjectRef(kind="table_version", code=tv_code),
        ObjectRef(kind="module_version", code=mv_code),
    ]
    if header_code:
        objects.append(
            ObjectRef(
                kind="header",
                code=header_code,
                name=direction or None,
            )
        )
    if property_id is not None:
        prop_ic = _open_item_category(snap, property_id)
        objects.append(
            ObjectRef(
                kind="property",
                id=property_id,
                code=prop_ic.code if prop_ic is not None else None,
            )
        )
    item_ic = _open_item_category(snap, item_id)
    objects.append(
        ObjectRef(
            kind="item",
            id=item_id,
            code=item_ic.signature if item_ic is not None else None,
        )
    )
    return Finding(objects=tuple(objects), message=message)


@rule(
    "1_15",
    legacy_code="1_15",
    family=_FAMILY,
    severity=SEVERITY_WARNING,
    description=(
        "ItemCategory/PropertyCategory changed with impact on a "
        "module but no new ModuleVersion created"
    ),
)
def rule_1_15(ctx: RuleContext) -> Iterator[Finding]:
    """Glossary changes must trigger new ModuleVersions.

    For every active (non-draft) ModuleVersion that does not start
    in the current release (and whose module has at least one
    non-draft version), every use of a property or item whose
    ItemCategory/PropertyCategory changed in the current release is
    reported: contexts and properties of table versions, header
    versions and variable versions, context items, and subcategory
    items of header versions.
    """
    snap, rel = ctx.snapshot, ctx.release
    changed_props = _changed_properties(ctx)
    changed_items = _changed_items(ctx)
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for mv in snap.module_versions:
        if not _active_non_draft(
            rel, mv.start_release_id, mv.end_release_id
        ):
            continue
        if mv.start_release_id == rel.current_release_id:
            continue
        siblings = (
            _mv_by_module(snap).get(mv.module_id, [])
            if mv.module_id is not None
            else []
        )
        if not any(
            not rel.is_draft(s.start_release_id) for s in siblings
        ):
            continue
        for mvc in snap.mvc_by_module_vid().get(mv.module_vid, []):
            tv = (
                snap.table_versions_by_vid.get(mvc.table_vid)
                if mvc.table_vid is not None
                else None
            )
            if tv is None:
                continue
            _collect_1_15(
                snap, mv, tv, changed_props, changed_items, findings
            )
    yield from _emit(findings)


def _collect_1_15(
    snap: ModelSnapshot,
    mv: ModuleVersionRow,
    tv: TableVersionRow,
    changed_props: Set[int],
    changed_items: Set[int],
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Emit the 1_15 rows for one (ModuleVersion, TableVersion)."""
    usages: List[_Usage] = [
        *_tv_level_usages(snap, tv),
        *_header_usages(snap, tv),
        *_variable_usages(snap, tv),
    ]
    mv_code = mv.code or ""
    for usage in usages:
        source, header_code, direction, kind, object_id = usage
        if kind == "property":
            if object_id not in changed_props:
                continue
            property_id: Optional[int] = object_id
        else:
            if object_id not in changed_items:
                continue
            property_id = None
        key = (
            source,
            mv_code,
            tv.code or "",
            header_code,
            direction,
            -1 if property_id is None else property_id,
            object_id,
        )
        if key in findings:
            continue
        findings[key] = _finding_1_15(
            snap, mv_code, tv.code, usage, property_id, object_id
        )


# ------------------------------------------------------------------
# Rule 1_16
# ------------------------------------------------------------------


@rule(
    "1_16",
    legacy_code="1_16",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Technical tables from the same abstract table in different "
        "template groups"
    ),
)
def rule_1_16(ctx: RuleContext) -> Iterator[Finding]:
    """Tables of one abstract table share one template group.

    Open, non-abstract TableVersions in a ModuleVersion starting in
    the current release, sitting in a templateGroup composition
    starting in the current release, fire when another open
    TableVersion of a different table with the same AbstractTableID
    sits in an open composition of a different open templateGroup.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table in _tvs_in_new_modules(ctx):
        if tv.end_release_id is not None:
            continue
        if not _is_false(table.is_abstract):
            continue
        if tv.abstract_table_id is None:
            continue
        for tgc in _tgc_by_table(snap).get(table.table_id, []):
            if not rel.starts_in_current(tgc.start_release_id):
                continue
            tg = snap.table_groups_by_id.get(tgc.table_group_id)
            if tg is None or tg.type != "templateGroup":
                continue
            _collect_1_16(
                ctx,
                tv,
                tv.abstract_table_id,
                tgc.table_group_id,
                findings,
            )
    yield from _emit(findings)


def _collect_1_16(
    ctx: RuleContext,
    tv: TableVersionRow,
    abstract_table_id: int,
    own_group_id: int,
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Find sibling technical tables in other template groups."""
    snap = ctx.snapshot
    for tv2 in _tv_by_abstract(snap).get(abstract_table_id, []):
        if tv2.end_release_id is not None:
            continue
        if tv2.table_id is None or tv2.table_id == tv.table_id:
            continue
        for tgc2 in _tgc_by_table(snap).get(tv2.table_id, []):
            if tgc2.table_group_id == own_group_id:
                continue
            if tgc2.end_release_id is not None:
                continue
            if not _open_template_group(snap, tgc2.table_group_id):
                continue
            key = (tv.table_vid, tv2.table_vid)
            if key in findings:
                continue
            message = (
                "Technical Table belongs to a different Template "
                "Group than another technical Table that emanates "
                "from the same Abstract Table as the current one: "
                f"{tv2.code}"
            )
            findings[key] = Finding(
                objects=(_tv_ref(tv), _tv_ref(tv2)), message=message
            )


# ------------------------------------------------------------------
# Rule 1_17
# ------------------------------------------------------------------


@rule(
    "1_17",
    legacy_code="1_17",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Duplicate TableVersion name within modules changing in the "
        "current release"
    ),
)
def rule_1_17(ctx: RuleContext) -> Iterator[Finding]:
    """Active TableVersions must have unique names.

    TableVersions composed into a ModuleVersion starting in the
    current release fire when another TableVersion of a lower
    TableID with the same trimmed name and the same abstractness
    sits in an active (non-draft) module version.
    """
    snap = ctx.snapshot
    active_vids = _tvs_in_active_modules(ctx)
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table in _tvs_in_new_modules(ctx):
        if tv.name is None:
            continue
        for tv2 in _tv_by_trimmed_name(snap).get(
            tv.name.strip(), []
        ):
            if (
                tv2.table_id is None
                or tv2.table_id >= table.table_id
            ):
                continue
            table2 = snap.tables_by_id.get(tv2.table_id)
            if table2 is None:
                continue
            if (
                table.is_abstract is None
                or table2.is_abstract is None
                or bool(table.is_abstract)
                != bool(table2.is_abstract)
            ):
                continue
            if tv2.table_vid not in active_vids:
                continue
            key = (tv.table_vid, tv2.table_vid)
            label = f"{tv.code}: {tv.name}"[:100]
            message = (
                f'Duplicate Name: "{label}"... of TableVersion that '
                "belongs to a Module changing in Current Release "
                f"with: {tv2.code}"
            )
            findings[key] = Finding(
                objects=(_tv_ref(tv), _tv_ref(tv2)), message=message
            )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rule 1_18
# ------------------------------------------------------------------


@rule(
    "1_18",
    legacy_code="1_18",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "TableGroup Code contains one of these illegal characters: "
        '"-", "–", "(", ")", ".", " "'
    ),
)
def rule_1_18(ctx: RuleContext) -> Iterator[Finding]:
    """Template group codes must avoid illegal characters.

    TableGroups of type templateGroup starting in the current
    release fire when their code contains a dash, en-dash,
    parenthesis, dot or space.
    """
    rel = ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tg in ctx.snapshot.table_groups:
        if not rel.starts_in_current(tg.start_release_id):
            continue
        if tg.type != "templateGroup" or tg.code is None:
            continue
        if any(char in tg.code for char in _ILLEGAL_TG_CODE_CHARS):
            findings.setdefault(
                (tg.table_group_id,),
                Finding(objects=(_tg_ref(tg),)),
            )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rule 1_19
# ------------------------------------------------------------------


@rule(
    "1_19",
    legacy_code="1_19",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Destination table of an association has different open "
        "row/column/sheet settings than the source table"
    ),
)
def rule_1_19(ctx: RuleContext) -> Iterator[Finding]:
    """Copy-pasted tables must keep the source open-axis settings.

    For every ``Aux_CellMapping`` row whose new TableVersion is
    composed into a ModuleVersion starting in the current release,
    the new and old tables must agree on their open row/column/sheet
    flags (SQL ``<>``: NULL flags never differ).
    """
    snap = ctx.snapshot
    new_vids = {tv.table_vid for tv, _ in _tvs_in_new_modules(ctx)}
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for cm in snap.aux_cell_mappings:
        tv = snap.table_versions_by_vid.get(cm.new_table_vid)
        if tv is None or tv.table_vid not in new_vids:
            continue
        table = (
            snap.tables_by_id.get(tv.table_id)
            if tv.table_id is not None
            else None
        )
        tv2 = (
            snap.table_versions_by_vid.get(cm.old_table_vid)
            if cm.old_table_vid is not None
            else None
        )
        table2 = (
            snap.tables_by_id.get(tv2.table_id)
            if tv2 is not None and tv2.table_id is not None
            else None
        )
        if table is None or table2 is None:
            continue
        if (
            _bit_ne(table.has_open_columns, table2.has_open_columns)
            or _bit_ne(table.has_open_rows, table2.has_open_rows)
            or _bit_ne(
                table.has_open_sheets, table2.has_open_sheets
            )
        ):
            findings.setdefault(
                (tv.table_vid,), Finding(objects=(_tv_ref(tv),))
            )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rules 1_20 / 1_21
# ------------------------------------------------------------------


@rule(
    "1_20",
    legacy_code="1_20",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Table with a new TableVersion still employed by an old "
        "active ModuleVersion"
    ),
)
def rule_1_20(ctx: RuleContext) -> Iterator[Finding]:
    """New TableVersions require new ModuleVersions.

    For every TableVersion starting in the current release, every
    active (non-draft) ModuleVersion employing the same TableID
    whose start release differs from the current one is reported.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv in snap.table_versions:
        if not rel.starts_in_current(tv.start_release_id):
            continue
        table = (
            snap.tables_by_id.get(tv.table_id)
            if tv.table_id is not None
            else None
        )
        if table is None:
            continue
        for mvc in _mvc_by_table_id(snap).get(table.table_id, []):
            mv = snap.module_versions_by_vid.get(mvc.module_vid)
            if mv is None or not _active_non_draft(
                rel, mv.start_release_id, mv.end_release_id
            ):
                continue
            if mv.start_release_id == rel.current_release_id:
                continue
            key = (tv.table_vid, mv.module_vid)
            findings.setdefault(
                key, Finding(objects=(_tv_ref(tv), _mv_ref(mv)))
            )
    yield from _emit(findings)


@rule(
    "1_21",
    legacy_code="1_21",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Table in a TableGroup starting in the draft release with "
        "draft TableGroupComposition start"
    ),
)
def rule_1_21(ctx: RuleContext) -> Iterator[Finding]:
    """Draft-started compositions are not allowed in new groups.

    For every TableGroupComposition row starting in the draft
    (playground) release whose TableGroup starts in the current
    release, each open TableVersion of the table is reported. Never
    fires when no draft release exists in the database.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tgc in snap.table_group_compositions:
        if not rel.is_draft(tgc.start_release_id):
            continue
        tg = snap.table_groups_by_id.get(tgc.table_group_id)
        if tg is None or not rel.starts_in_current(
            tg.start_release_id
        ):
            continue
        for tv in snap.table_versions_by_table().get(
            tgc.table_id, []
        ):
            if tv.end_release_id is not None:
                continue
            key = (tv.table_vid, tg.table_group_id)
            findings.setdefault(
                key, Finding(objects=(_tv_ref(tv), _tg_ref(tg)))
            )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rules 1_22 / 1_23 / 1_24 (commented out in the reference SQL)
# ------------------------------------------------------------------


@rule(
    "1_22",
    legacy_code="1_22",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Replicated (duplicate) TableAssociation",
)
def rule_1_22(ctx: RuleContext) -> Iterator[Finding]:
    """No duplicate TableAssociations between the same tables.

    Two associations between the same parent and child TableVersions
    are duplicates when no pair of their KeyHeaderMapping rows maps
    different foreign-key headers (which includes the case where
    either association has no mapping at all).

    Note:
        This block is commented out in the reference SQL; it is
        implemented from the commented text per the specification
        catalogue. dpmcore's ``TableAssociation`` table carries no
        release lifecycle columns, so the SQL filters on
        ``TableAssociation.StartReleaseID``/``EndReleaseID`` cannot
        be replicated and the check applies to all associations.
    """
    snap = ctx.snapshot
    pairs = _group_by(
        snap.table_associations,
        lambda ta: (
            (ta.parent_table_vid, ta.child_table_vid)
            if ta.parent_table_vid is not None
            and ta.child_table_vid is not None
            else None
        ),
    )
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for (parent_vid, _child_vid), group in pairs.items():
        tv1 = snap.table_versions_by_vid.get(parent_vid)
        if tv1 is None:
            continue
        ordered = sorted(group, key=lambda ta: ta.association_id)
        for index, ta1 in enumerate(ordered):
            for ta2 in ordered[:index]:
                if _mappings_differ(snap, ta1, ta2):
                    continue
                _add_1_22(findings, tv1, ta1, ta2)
    yield from _emit(findings)


def _add_1_22(
    findings: Dict[Tuple[Any, ...], Finding],
    tv1: TableVersionRow,
    ta1: TableAssociationRow,
    ta2: TableAssociationRow,
) -> None:
    """Record one replicated-association finding."""
    message = (
        f"Replicated TableAssociation {ta1.name} with existing: "
        f"{ta2.name}. Please remove current Table Association. "
        "(Only if EndRelease=CurrentRelease: Please re-open an "
        "identical association already existing between same "
        "Tables and Columns that you just closed)"
    )
    key = (ta1.association_id, ta2.association_id)
    findings.setdefault(
        key,
        Finding(
            objects=(_tv_ref(tv1), _assoc_ref(ta1), _assoc_ref(ta2)),
            message=message,
        ),
    )


def _mappings_differ(
    snap: ModelSnapshot,
    ta1: TableAssociationRow,
    ta2: TableAssociationRow,
) -> bool:
    """True when some mapping pair maps different FK headers."""
    rows1 = _khm_by_assoc(snap).get(ta1.association_id, [])
    rows2 = _khm_by_assoc(snap).get(ta2.association_id, [])
    return any(
        khm1.foreign_key_header_id != khm2.foreign_key_header_id
        for khm1 in rows1
        for khm2 in rows2
    )


@rule(
    "1_23",
    legacy_code="1_23",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Inconsistent property categories between linked properties "
        "in a TableAssociation"
    ),
)
def rule_1_23(ctx: RuleContext) -> Iterator[Finding]:
    """Linked key-header properties must share their category.

    For each KeyHeaderMapping of an association, the property of the
    parent's primary-key header (through its open ItemCategory and
    PropertyCategory rows) must be in the same category as the
    property of the child's foreign-key header (through its open
    PropertyCategory rows).

    Note:
        This block is commented out in the reference SQL; it is
        implemented from the commented text per the specification
        catalogue. dpmcore's ``TableAssociation`` carries no release
        lifecycle columns, so the SQL filter on
        ``TableAssociation.StartReleaseID`` cannot be replicated and
        the check applies to all associations.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for ta in snap.table_associations:
        parent_tv = (
            snap.table_versions_by_vid.get(ta.parent_table_vid)
            if ta.parent_table_vid is not None
            else None
        )
        child_tv = (
            snap.table_versions_by_vid.get(ta.child_table_vid)
            if ta.child_table_vid is not None
            else None
        )
        if parent_tv is None or child_tv is None:
            continue
        for khm in _khm_by_assoc(snap).get(ta.association_id, []):
            pair = _mapped_header_versions(
                snap, parent_tv, child_tv, khm
            )
            if pair is None:
                continue
            _collect_1_23(snap, ta, parent_tv, pair, findings)
    yield from _emit(findings)


def _mapped_header_versions(
    snap: ModelSnapshot,
    parent_tv: TableVersionRow,
    child_tv: TableVersionRow,
    khm: KeyHeaderMappingRow,
) -> Optional[Tuple[HeaderVersionRow, HeaderVersionRow]]:
    """HeaderVersions linked by one KeyHeaderMapping row.

    Returns the (parent, child) HeaderVersion pair reached through
    the TableVersionHeader rows of the association's parent and
    child TableVersions, or None when any join fails.
    """
    if khm.primary_key_header_id is None:
        return None
    parent_hv = _tvh_header_version(
        snap, parent_tv.table_vid, khm.primary_key_header_id
    )
    child_hv = _tvh_header_version(
        snap, child_tv.table_vid, khm.foreign_key_header_id
    )
    if parent_hv is None or child_hv is None:
        return None
    return parent_hv, child_hv


def _tvh_header_version(
    snap: ModelSnapshot,
    table_vid: int,
    header_id: int,
) -> Optional[HeaderVersionRow]:
    """HeaderVersion of a header within a TableVersion, if any."""
    for tvh in snap.tvh_by_table_vid().get(table_vid, []):
        if tvh.header_id != header_id or tvh.header_vid is None:
            continue
        return snap.header_versions_by_vid.get(tvh.header_vid)
    return None


def _collect_1_23(
    snap: ModelSnapshot,
    ta: TableAssociationRow,
    parent_tv: TableVersionRow,
    pair: Tuple[HeaderVersionRow, HeaderVersionRow],
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Emit 1_23 rows for one mapped header pair."""
    parent_hv, child_hv = pair
    if (
        parent_hv.property_id is None
        or child_hv.property_id is None
    ):
        return
    child_categories = {
        pc2.category_id
        for pc2 in _pc_by_property(snap).get(
            child_hv.property_id, []
        )
        if pc2.end_release_id is None
    }
    for ic in _ic_by_item(snap).get(parent_hv.property_id, []):
        if ic.end_release_id is not None:
            continue
        for pc in _pc_by_property(snap).get(
            parent_hv.property_id, []
        ):
            if pc.end_release_id is not None:
                continue
            category = (
                snap.categories_by_id.get(pc.category_id)
                if pc.category_id is not None
                else None
            )
            if category is None:
                continue
            if not any(
                cat_id is not None and cat_id != pc.category_id
                for cat_id in child_categories
            ):
                continue
            _add_1_23(
                findings, snap, ta, parent_tv, parent_hv, ic,
                category,
            )


def _add_1_23(
    findings: Dict[Tuple[Any, ...], Finding],
    snap: ModelSnapshot,
    ta: TableAssociationRow,
    parent_tv: TableVersionRow,
    parent_hv: HeaderVersionRow,
    ic: ItemCategoryRow,
    category: CategoryRow,
) -> None:
    """Record one inconsistent-category finding."""
    message = (
        "Inconsistent Categories of Properties in TableAssociation "
        f"{ta.name} between linked Properties"
    )
    key = (
        parent_tv.table_vid,
        ta.name or "",
        parent_hv.property_id,
        ic.code or "",
        category.category_id,
    )
    findings.setdefault(
        key,
        Finding(
            objects=(
                _tv_ref(parent_tv),
                ObjectRef(
                    kind="property",
                    id=parent_hv.property_id,
                    code=ic.code,
                ),
                ObjectRef(
                    kind="category",
                    id=category.category_id,
                    code=category.code,
                ),
            ),
            message=message,
        ),
    )


@rule(
    "1_24",
    legacy_code="1_24",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "TableAssociation header mapping does not cover exactly the "
        "primary-key headers"
    ),
)
def rule_1_24(ctx: RuleContext) -> Iterator[Finding]:
    """Header mappings must cover exactly the parent key headers.

    An association fires when a key header of the parent
    TableVersion is missing from the mapped primary-key headers, or
    a non-key header of the parent appears among them. SQL
    ``NOT IN`` semantics: a NULL PrimaryKeyHeaderID in the mapping
    suppresses the missing-key branch.

    Note:
        This block is commented out in the reference SQL; it is
        implemented from the commented text per the specification
        catalogue. dpmcore's ``TableAssociation`` carries no release
        lifecycle columns, so the SQL filter on
        ``TableAssociation.StartReleaseID`` cannot be replicated and
        the check applies to all associations.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for ta in snap.table_associations:
        tv = (
            snap.table_versions_by_vid.get(ta.parent_table_vid)
            if ta.parent_table_vid is not None
            else None
        )
        if tv is None:
            continue
        mapped: Set[Optional[int]] = {
            khm.primary_key_header_id
            for khm in _khm_by_assoc(snap).get(
                ta.association_id, []
            )
        }
        has_null = None in mapped
        mapped.discard(None)
        if _mapping_incomplete(snap, tv, mapped, has_null):
            message = (
                "The Header mapping in this table association "
                f"{ta.name} does not include all the Primary Key "
                "Headers and only them"
            )
            findings.setdefault(
                (ta.association_id,),
                Finding(
                    objects=(_tv_ref(tv), _assoc_ref(ta)),
                    message=message,
                ),
            )
    yield from _emit(findings)


def _mapping_incomplete(
    snap: ModelSnapshot,
    tv: TableVersionRow,
    mapped: Set[Optional[int]],
    has_null: bool,
) -> bool:
    """True when the mapping misses a key or includes a non-key."""
    for tvh in snap.tvh_by_table_vid().get(tv.table_vid, []):
        header = snap.headers_by_id.get(tvh.header_id)
        if header is None:
            continue
        if bool(header.is_key):
            if tvh.header_id not in mapped and not has_null:
                return True
        elif _is_false(header.is_key) and tvh.header_id in mapped:
            return True
    return False
