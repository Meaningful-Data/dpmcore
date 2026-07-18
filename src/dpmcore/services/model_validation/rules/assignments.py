"""Family 4 modelling rules — property/context/item assignments.

Port of the ``4_x`` INSERT blocks of ``check_modelling_rules_tidy``:
key/main-property overlaps (4_1a, 4_1b), duplicate coordinates (4_2,
4_4), main-property vs context collisions (4_3a, 4_3b, 4_5a, 4_5b),
category integrity of context compositions (4_6, 4_7, 4_7b, 4_7c,
4_7d), subcategory uniqueness (4_8) and default-item misuse (4_9a,
4_9b, 4_9c, 4_10).

The SQL reuses ViolationCodes 4_1, 4_3, 4_5 and 4_9 for distinct
checks; rule ids carry letter suffixes while ``legacy_code`` keeps
the SQL code. NOTE: the original analysis missed 4_1 entirely (its
blocks use lowercase ``as ViolationCode``) — both variants are
ported here.
"""

from __future__ import annotations

from datetime import date
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
)

from dpmcore.services.model_validation.registry import (
    Finding,
    RuleContext,
    rule,
)
from dpmcore.services.model_validation.rules.headers import (
    _all_ics,
    _emit,
    _header_ref,
    _is_false,
    _left_open_categories,
    _left_open_ic_codes,
    _member_any_mv,
    _member_mv_start_now,
    _open_ics,
    _open_pc_categories,
    _rows_by_header_vid,
    _same_direction,
    _tv_header_rows,
    _tv_ref,
)
from dpmcore.services.model_validation.snapshot import (
    ContextCompositionRow,
    HeaderRow,
    HeaderVersionRow,
    ItemCategoryRow,
    ModelSnapshot,
    PropertyCategoryRow,
    TableVersionRow,
)
from dpmcore.services.model_validation.types import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    ObjectRef,
)

_FAMILY = "assignments"

_RowT = TypeVar("_RowT")

#: A 4_7-family context source: (source ref, context composition).
_ContextSource = Tuple[ObjectRef, ContextCompositionRow]


def _key_header_property_ids(
    ctx: RuleContext, tv: TableVersionRow
) -> set[int]:
    """Properties of open, non-abstract key headers of a TV."""
    result: set[int] = set()
    for header2, hv2, tvh2 in _tv_header_rows(ctx, tv.table_vid):
        if not header2.is_key or not _is_false(tvh2.is_abstract):
            continue
        if hv2.end_release_id is not None:
            continue
        if hv2.property_id is not None:
            result.add(hv2.property_id)
    return result


def _pc_rows(
    snap: ModelSnapshot, property_id: Optional[int]
) -> List[PropertyCategoryRow]:
    """PropertyCategory rows of a property (any end release)."""
    if property_id is None:
        return []
    grouped = snap.cache(
        "assignments:pc_by_property", lambda: _group_pcs(snap)
    )
    return grouped.get(property_id, [])


def _group_pcs(
    snap: ModelSnapshot,
) -> Dict[int, List[PropertyCategoryRow]]:
    """PropertyCategory rows grouped by property id."""
    grouped: Dict[int, List[PropertyCategoryRow]] = {}
    for pc in snap.property_categories:
        grouped.setdefault(pc.property_id, []).append(pc)
    return grouped


def _context_ccs(
    snap: ModelSnapshot, context_id: Optional[int]
) -> List[ContextCompositionRow]:
    """ContextComposition rows of a context."""
    if context_id is None:
        return []
    return snap.context_compositions_by_context().get(context_id, [])


# ------------------------------------------------------------------
# Rules 4_1a / 4_1b
# ------------------------------------------------------------------


@rule(
    "4_1a",
    legacy_code="4_1",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Main Property in this Header exists also as Key Property "
        "on the same Table"
    ),
)
def rule_4_1a(ctx: RuleContext) -> Iterator[Finding]:
    """Header main properties may not double as key properties.

    Non-key, non-abstract headers of open, current-release
    TableVersions (in a module) whose property is also carried by
    an open key header of the same table version fire, once per
    open ItemCategory code and PropertyCategory category.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _matches_4_1a(ctx, tv, table, header, hv, tvh):
            continue
        for ic in _open_ics(snap, hv.property_id):
            for cat_id, cat_code in _open_pc_categories(
                ctx, hv.property_id
            ):
                key = (tv.table_vid, hv.header_vid, ic.code, cat_id)
                findings.setdefault(
                    key,
                    Finding(
                        objects=(
                            ObjectRef(
                                kind="header_version",
                                id=hv.header_vid,
                                code=hv.code,
                            ),
                            _tv_ref(tv),
                            ObjectRef(
                                kind="property",
                                id=hv.property_id,
                                code=ic.code,
                            ),
                            ObjectRef(
                                kind="category",
                                id=cat_id,
                                code=cat_code,
                            ),
                        )
                    ),
                )
    yield from _emit(findings)


def _matches_4_1a(
    ctx: RuleContext,
    tv: TableVersionRow,
    table: Any,
    header: HeaderRow,
    hv: HeaderVersionRow,
    tvh: Any,
) -> bool:
    """The 4_1a row filter: fact property doubling as key property."""
    rel = ctx.release
    if not _is_false(table.is_abstract):
        return False
    if tv.end_release_id is not None or hv.end_release_id is not None:
        return False
    if not rel.is_current(tv.start_release_id):
        return False
    if not _is_false(header.is_key) or not _is_false(tvh.is_abstract):
        return False
    if hv.property_id is None:
        return False
    if not _member_any_mv(ctx, tv.table_vid):
        return False
    return hv.property_id in _key_header_property_ids(ctx, tv)


@rule(
    "4_1b",
    legacy_code="4_1",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Main Property of the whole Table exists also as Key "
        "Property on the same Table"
    ),
)
def rule_4_1b(ctx: RuleContext) -> Iterator[Finding]:
    """Whole-table main properties may not double as keys.

    Open, current-release TableVersions carrying a PropertyID that
    an open, non-abstract key header of the same table version also
    carries fire, once per open ItemCategory / PropertyCategory.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv in snap.table_versions:
        if tv.end_release_id is not None or tv.property_id is None:
            continue
        if not rel.is_current(tv.start_release_id):
            continue
        table = (
            snap.tables_by_id.get(tv.table_id)
            if tv.table_id is not None
            else None
        )
        if table is None or not _is_false(table.is_abstract):
            continue
        if not _member_any_mv(ctx, tv.table_vid):
            continue
        if tv.property_id not in _key_header_property_ids(ctx, tv):
            continue
        for ic in _open_ics(snap, tv.property_id):
            for cat_id, cat_code in _open_pc_categories(
                ctx, tv.property_id
            ):
                key = (tv.table_vid, ic.code, cat_id)
                findings.setdefault(
                    key,
                    Finding(
                        objects=(
                            _tv_ref(tv),
                            ObjectRef(
                                kind="property",
                                id=tv.property_id,
                                code=ic.code,
                            ),
                            ObjectRef(
                                kind="category",
                                id=cat_id,
                                code=cat_code,
                            ),
                        )
                    ),
                )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rule 4_2
# ------------------------------------------------------------------


@rule(
    "4_2",
    legacy_code="4_2",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "This combination of Main PropertyID and ContextID appears "
        "in more than one Headers"
    ),
)
def rule_4_2(ctx: RuleContext) -> Iterator[Finding]:
    """(Property, Context) pairs must be unique per direction.

    Two distinct non-key, non-abstract open HeaderVersions of the
    same direction and table version with identical PropertyID and
    ContextID (NULLs compare equal, mirroring ``ISNULL(x, -1)``)
    both fire. ItemCategory / PropertyCategory are LEFT-joined.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None or hv.end_release_id is not None:
            continue
        if not rel.is_current(tv.start_release_id):
            continue
        if not _is_false(header.is_key) or not _is_false(
            tvh.is_abstract
        ):
            continue
        if not _has_4_2_twin(ctx, tv, header, hv):
            continue
        for ic_code in _left_open_ic_codes(snap, hv.property_id):
            for cat_id, cat_code in _left_open_categories(
                ctx, hv.property_id
            ):
                key = (tv.table_vid, header.header_id, ic_code, cat_id)
                findings.setdefault(
                    key,
                    Finding(
                        objects=(
                            _header_ref(header, hv),
                            _tv_ref(tv),
                            ObjectRef(
                                kind="property",
                                id=hv.property_id,
                                code=ic_code,
                            ),
                            ObjectRef(kind="context", id=hv.context_id),
                            ObjectRef(
                                kind="category",
                                id=cat_id,
                                code=cat_code,
                            ),
                        )
                    ),
                )
    yield from _emit(findings)


def _has_4_2_twin(
    ctx: RuleContext,
    tv: TableVersionRow,
    header: HeaderRow,
    hv: HeaderVersionRow,
) -> bool:
    """Another header with the same (property, context) coordinates."""
    for header2, hv2, tvh2 in _tv_header_rows(ctx, tv.table_vid):
        if hv2.header_id == hv.header_id:
            continue
        if not _is_false(tvh2.is_abstract):
            continue
        if not _is_false(header2.is_key):
            continue
        if not _same_direction(header2.direction, header.direction):
            continue
        if hv2.end_release_id is not None:
            continue
        if (
            hv2.property_id == hv.property_id
            and hv2.context_id == hv.context_id
        ):
            return True
    return False


# ------------------------------------------------------------------
# Rules 4_3a / 4_3b
# ------------------------------------------------------------------


def _4_3_base_rows(
    ctx: RuleContext,
) -> Iterator[
    Tuple[TableVersionRow, HeaderRow, HeaderVersionRow]
]:
    """Shared outer rows of the 4_3 variants."""
    rel = ctx.release
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None or hv.end_release_id is not None:
            continue
        if not rel.is_current(tv.start_release_id):
            continue
        if not _is_false(header.is_key) or not _is_false(
            tvh.is_abstract
        ):
            continue
        if hv.property_id is None:
            continue
        if not _member_any_mv(ctx, tv.table_vid):
            continue
        yield tv, header, hv


def _emit_4_3(
    ctx: RuleContext,
    tv: TableVersionRow,
    header: HeaderRow,
    hv: HeaderVersionRow,
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Emit 4_3 rows with the LEFT-joined category columns."""
    snap = ctx.snapshot
    for ic_code in _left_open_ic_codes(snap, hv.property_id):
        for cat_id, cat_code in _left_open_categories(
            ctx, hv.property_id
        ):
            key = (tv.table_vid, header.header_id, ic_code, cat_id)
            findings.setdefault(
                key,
                Finding(
                    objects=(
                        _header_ref(header, hv),
                        _tv_ref(tv),
                        ObjectRef(
                            kind="property",
                            id=hv.property_id,
                            code=ic_code,
                        ),
                        ObjectRef(
                            kind="category", id=cat_id, code=cat_code
                        ),
                    )
                ),
            )


@rule(
    "4_3a",
    legacy_code="4_3",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Main Property in this Header exists also as Context "
        "Property on the same Table"
    ),
)
def rule_4_3a(ctx: RuleContext) -> Iterator[Finding]:
    """Main properties may not appear in other headers' contexts.

    Fires when the property of a fact header is composed into the
    context of another open, non-key, non-abstract header of the
    same table version on a *different* direction (or the same
    header itself).
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, header, hv in _4_3_base_rows(ctx):
        hit = False
        for header2, hv2, tvh2 in _tv_header_rows(ctx, tv.table_vid):
            if not _is_false(tvh2.is_abstract):
                continue
            if not _is_false(header2.is_key):
                continue
            if hv2.end_release_id is not None:
                continue
            if (
                _same_direction(header2.direction, header.direction)
                and header2.header_id != header.header_id
            ):
                continue
            in_context = any(
                cc.property_id == hv.property_id
                for cc in _context_ccs(snap, hv2.context_id)
            )
            if in_context:
                hit = True
                break
        if hit:
            _emit_4_3(ctx, tv, header, hv, findings)
    yield from _emit(findings)


@rule(
    "4_3b",
    legacy_code="4_3",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Main Property in this Header exists also as Context "
        "Property of the whole Table"
    ),
)
def rule_4_3b(ctx: RuleContext) -> Iterator[Finding]:
    """Main properties may not appear in the table context."""
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, header, hv in _4_3_base_rows(ctx):
        in_context = any(
            cc.property_id == hv.property_id
            for cc in _context_ccs(snap, tv.context_id)
        )
        if in_context:
            _emit_4_3(ctx, tv, header, hv, findings)
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rule 4_4
# ------------------------------------------------------------------


@rule(
    "4_4",
    legacy_code="4_4",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="This Header Code is duplicate",
)
def rule_4_4(ctx: RuleContext) -> Iterator[Finding]:
    """Header codes must be unique per direction of a table version.

    Open HeaderVersions of open, current-release TableVersions (in
    a module) sharing a code and direction with another open
    HeaderVersion of the same table version fire.
    """
    rel = ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, _tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None or hv.end_release_id is not None:
            continue
        if not rel.is_current(tv.start_release_id):
            continue
        if not _member_any_mv(ctx, tv.table_vid):
            continue
        duplicate = any(
            hv2.header_vid != hv.header_vid
            and hv2.end_release_id is None
            and hv2.code == hv.code
            and _same_direction(header2.direction, header.direction)
            for header2, hv2, _tvh2 in _tv_header_rows(
                ctx, tv.table_vid
            )
        )
        if not duplicate:
            continue
        key = (tv.table_vid, header.header_id, hv.code)
        findings.setdefault(
            key,
            Finding(objects=(_header_ref(header, hv), _tv_ref(tv))),
        )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rules 4_5a / 4_5b
# ------------------------------------------------------------------


def _4_5_rows(
    ctx: RuleContext,
) -> Iterator[
    Tuple[
        TableVersionRow,
        HeaderRow,
        HeaderVersionRow,
        ContextCompositionRow,
    ]
]:
    """Outer rows of the 4_5 variants: header-context compositions."""
    snap, rel = ctx.snapshot, ctx.release
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None:
            continue
        if not rel.is_current(tv.start_release_id):
            continue
        if not _is_false(header.is_key) or not _is_false(
            tvh.is_abstract
        ):
            continue
        if not _member_any_mv(ctx, tv.table_vid):
            continue
        for cc in _context_ccs(snap, hv.context_id):
            yield tv, header, hv, cc


def _emit_4_5(
    ctx: RuleContext,
    tv: TableVersionRow,
    cc: ContextCompositionRow,
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Emit 4_5 rows per open (IC code, PC category) of cc property."""
    snap = ctx.snapshot
    for ic in _open_ics(snap, cc.property_id):
        for cat_id, cat_code in _open_pc_categories(
            ctx, cc.property_id
        ):
            key = (tv.table_vid, cc.property_id, ic.code, cat_id)
            findings.setdefault(
                key,
                Finding(
                    objects=(
                        _tv_ref(tv),
                        ObjectRef(
                            kind="property",
                            id=cc.property_id,
                            code=ic.code,
                        ),
                        ObjectRef(
                            kind="category", id=cat_id, code=cat_code
                        ),
                    )
                ),
            )


@rule(
    "4_5a",
    legacy_code="4_5",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Property in table Context has already been assigned to the "
        "Context of another Direction of this Table"
    ),
)
def rule_4_5a(ctx: RuleContext) -> Iterator[Finding]:
    """Context properties may not repeat across directions.

    Fires when a property composed into a header context also
    appears in the context of an open, non-key, non-abstract header
    of a different direction of the same table version.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, header, _hv, cc in _4_5_rows(ctx):
        hit = False
        for header2, hv2, tvh2 in _tv_header_rows(ctx, tv.table_vid):
            if not _is_false(tvh2.is_abstract):
                continue
            if not _is_false(header2.is_key):
                continue
            if hv2.end_release_id is not None:
                continue
            if _same_direction(header2.direction, header.direction):
                continue
            if any(
                cc2.property_id == cc.property_id
                for cc2 in _context_ccs(snap, hv2.context_id)
            ):
                hit = True
                break
        if hit:
            _emit_4_5(ctx, tv, cc, findings)
    yield from _emit(findings)


@rule(
    "4_5b",
    legacy_code="4_5",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Property in a header Context has already been assigned to "
        "the Context of the whole Table"
    ),
)
def rule_4_5b(ctx: RuleContext) -> Iterator[Finding]:
    """Header-context properties may not repeat in the table context."""
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, _header, _hv, cc in _4_5_rows(ctx):
        if tv.context_id is None:
            continue
        if any(
            cc2.property_id == cc.property_id
            for cc2 in _context_ccs(snap, tv.context_id)
        ):
            _emit_4_5(ctx, tv, cc, findings)
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rule 4_6
# ------------------------------------------------------------------


@rule(
    "4_6",
    legacy_code="4_6",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Non-enumerated Property Assigned to Context Composition"
    ),
)
def rule_4_6(ctx: RuleContext) -> Iterator[Finding]:
    """Context compositions may only carry enumerated properties.

    Header contexts of non-key, non-abstract headers on open
    TableVersions of module versions starting now: a composed
    property with an open PropertyCategory whose category is not
    enumerated fires (open ItemCategory required, as in the SQL).
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None:
            continue
        if not _is_false(header.is_key) or not _is_false(
            tvh.is_abstract
        ):
            continue
        if not _member_mv_start_now(ctx, tv.table_vid):
            continue
        for cc in _context_ccs(snap, hv.context_id):
            _collect_4_6(ctx, tv, cc, findings)
    yield from _emit(findings)


def _collect_4_6(
    ctx: RuleContext,
    tv: TableVersionRow,
    cc: ContextCompositionRow,
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Emit 4_6 rows for non-enumerated categories of cc property."""
    snap = ctx.snapshot
    ic_codes = [ic.code for ic in _open_ics(snap, cc.property_id)]
    if not ic_codes:
        return
    for pc in _pc_rows(snap, cc.property_id):
        if pc.end_release_id is not None or pc.category_id is None:
            continue
        category = snap.categories_by_id.get(pc.category_id)
        if category is None:
            continue
        if category.is_enumerated is None or category.is_enumerated:
            continue
        for ic_code in ic_codes:
            key = (
                tv.table_vid,
                cc.property_id,
                ic_code,
                category.category_id,
            )
            findings.setdefault(
                key,
                Finding(
                    objects=(
                        _tv_ref(tv),
                        ObjectRef(
                            kind="property",
                            id=cc.property_id,
                            code=ic_code,
                        ),
                        ObjectRef(
                            kind="category",
                            id=category.category_id,
                            code=category.code,
                        ),
                    )
                ),
            )
    return


# ------------------------------------------------------------------
# Rules 4_7 / 4_7b / 4_7c / 4_7d — category assignment integrity
# ------------------------------------------------------------------


def _context_sources(ctx: RuleContext) -> List[_ContextSource]:
    """The three 4_7-family context branches, flattened.

    Header contexts of non-key non-abstract headers, contexts of
    open compound items starting now, and whole-table contexts —
    each restricted to open TableVersions in module versions
    starting in the current release (per the SQL branches).
    """
    snap = ctx.snapshot

    def build() -> List[_ContextSource]:
        sources: List[_ContextSource] = []
        sources.extend(_header_context_sources(ctx))
        sources.extend(_compound_item_sources(ctx))
        sources.extend(_table_context_sources(ctx))
        return sources

    return snap.cache("assignments:context_sources", build)


def _header_context_sources(ctx: RuleContext) -> List[_ContextSource]:
    """Branch 1: contexts of fact headers."""
    snap = ctx.snapshot
    sources: List[_ContextSource] = []
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None:
            continue
        if not _is_false(header.is_key) or not _is_false(
            tvh.is_abstract
        ):
            continue
        if not _member_mv_start_now(ctx, tv.table_vid):
            continue
        label = f"{header.direction}_{hv.code}"
        ref = ObjectRef(
            kind="table_version",
            id=tv.table_vid,
            code=(tv.code or "").strip()[:40],
            name=label.strip()[:30],
        )
        sources.extend(
            (ref, cc) for cc in _context_ccs(snap, hv.context_id)
        )
    return sources


def _compound_item_sources(ctx: RuleContext) -> List[_ContextSource]:
    """Branch 2: contexts of compound items starting now."""
    snap, rel = ctx.snapshot, ctx.release
    sources: List[_ContextSource] = []
    for cic in snap.compound_item_contexts:
        if cic.end_release_id is not None:
            continue
        if not rel.is_current(cic.start_release_id):
            continue
        for ic0 in _open_ics(snap, cic.item_id):
            label = (
                f"CompoundItemID: {cic.item_id}  "
                f"CompoundItemCode: {(ic0.code or '')[:13]}"
            )
            ref = ObjectRef(
                kind="compound_item",
                id=cic.item_id,
                code=label.strip()[:40],
            )
            sources.extend(
                (ref, cc)
                for cc in _context_ccs(snap, cic.context_id)
            )
    return sources


def _table_context_sources(ctx: RuleContext) -> List[_ContextSource]:
    """Branch 3: whole-table contexts."""
    snap = ctx.snapshot
    sources: List[_ContextSource] = []
    for tv in snap.table_versions:
        if tv.end_release_id is not None or tv.context_id is None:
            continue
        table = (
            snap.tables_by_id.get(tv.table_id)
            if tv.table_id is not None
            else None
        )
        if table is None or not _is_false(table.is_abstract):
            continue
        if not _member_mv_start_now(ctx, tv.table_vid):
            continue
        ref = ObjectRef(
            kind="table_version",
            id=tv.table_vid,
            code=(tv.code or "").strip()[:40],
            name="Table_Context",
        )
        sources.extend(
            (ref, cc) for cc in _context_ccs(snap, tv.context_id)
        )
    return sources


def _latest_by_release_date(
    ctx: RuleContext,
    rows: Sequence[_RowT],
    start_of: Callable[[_RowT], Optional[int]],
) -> List[_RowT]:
    """Rows whose start release has the latest (max) release date.

    Mirrors ``r.Date IN (SELECT max(r.Date) ...)``: rows whose start
    release is missing or undated never match, and when no row has
    a dated release the result is empty.
    """
    snap = ctx.snapshot
    dated: List[Tuple[date, _RowT]] = []
    for row in rows:
        start = start_of(row)
        release = (
            snap.releases_by_id.get(start) if start is not None else None
        )
        if release is not None and release.date is not None:
            dated.append((release.date, row))
    if not dated:
        return []
    top = max(d for d, _ in dated)
    return [row for d, row in dated if d == top]


def _category_code(
    snap: ModelSnapshot, category_id: Optional[int]
) -> Optional[str]:
    """Category code by id, None when unresolvable."""
    if category_id is None:
        return None
    category = snap.categories_by_id.get(category_id)
    return category.code if category is not None else None


def _47_family(
    ctx: RuleContext,
    variant: str,
) -> Iterator[Finding]:
    """Shared driver of the 4_7 / 4_7b / 4_7c / 4_7d checks."""
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for source_ref, cc in _context_sources(ctx):
        if cc.item_id is None:
            continue
        itcs = _all_ics(snap, cc.property_id)
        itc2s = _latest_by_release_date(
            ctx,
            _all_ics(snap, cc.item_id),
            lambda r: r.start_release_id,
        )
        pcs = _latest_by_release_date(
            ctx,
            _pc_rows(snap, cc.property_id),
            lambda r: r.start_release_id,
        )
        for combo in _47_combos(ctx, variant, itcs, pcs, itc2s):
            itc, pc, itc2, message = combo
            key = (
                variant,
                source_ref.kind,
                source_ref.id,
                source_ref.name,
                cc.property_id,
                itc.code if itc is not None else None,
                itc2.item_id,
                itc2.code,
                message,
            )
            findings.setdefault(
                key,
                Finding(
                    objects=(
                        source_ref,
                        ObjectRef(
                            kind="property",
                            id=cc.property_id,
                            code=(
                                itc.code if itc is not None else None
                            ),
                        ),
                        ObjectRef(
                            kind="item",
                            id=itc2.item_id,
                            code=itc2.code,
                        ),
                    ),
                    message=message,
                ),
            )
    yield from _emit(findings)


def _47_combos(
    ctx: RuleContext,
    variant: str,
    itcs: Sequence[ItemCategoryRow],
    pcs: Sequence[PropertyCategoryRow],
    itc2s: Sequence[ItemCategoryRow],
) -> Iterator[
    Tuple[
        Optional[ItemCategoryRow],
        PropertyCategoryRow,
        ItemCategoryRow,
        str,
    ]
]:
    """(itc, pc, itc2, message) combinations firing for a variant."""
    snap = ctx.snapshot
    itc_pool = (
        _latest_by_release_date(
            ctx, itcs, lambda r: r.start_release_id
        )
        if variant == "4_7c"
        else list(itcs)
    )
    for pc in pcs:
        for itc2 in itc2s:
            for itc in itc_pool:
                message = _47_message(
                    variant,
                    snap,
                    pc,
                    itc,
                    itc2,
                )
                if message is not None:
                    yield itc, pc, itc2, message


def _47_message(
    variant: str,
    snap: ModelSnapshot,
    pc: PropertyCategoryRow,
    itc: ItemCategoryRow,
    itc2: ItemCategoryRow,
) -> Optional[str]:
    """Message for a firing 4_7-family combination, else None."""
    pc_code = _category_code(snap, pc.category_id)
    itc2_code = _category_code(snap, itc2.category_id)
    if variant == "4_7":
        if (
            itc2.end_release_id is None
            and pc.end_release_id is None
            and itc.end_release_id is None
            and pc.category_id is not None
            and itc2.category_id is not None
            and pc.category_id != itc2.category_id
        ):
            return (
                f"Property Category ({pc_code}) and Item Category "
                f"({itc2_code}) assignments are not the same"
            )
        return None
    if variant == "4_7b":
        if pc.end_release_id is not None:
            return f"Property Category ({pc_code}) has Expired"
        return None
    if variant == "4_7c":
        if itc.end_release_id is not None:
            return f"Property Code ({pc_code}) has Expired"
        return None
    if itc2.end_release_id is not None:
        return f"Item Category ({itc2_code}) has Expired"
    return None


@rule(
    "4_7",
    legacy_code="4_7",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Property Category and Item Category assignments are not "
        "the same"
    ),
)
def rule_4_7(ctx: RuleContext) -> Iterator[Finding]:
    """Context compositions must pair categories consistently.

    For every context composition reachable from header, compound
    item or table contexts: the latest (by release date) open
    PropertyCategory of the property must name the same category as
    the latest open ItemCategory of the item.
    """
    return _47_family(ctx, "4_7")


@rule(
    "4_7b",
    legacy_code="4_7b",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Property Category has Expired",
)
def rule_4_7b(ctx: RuleContext) -> Iterator[Finding]:
    """The property's latest PropertyCategory must not be expired."""
    return _47_family(ctx, "4_7b")


@rule(
    "4_7c",
    legacy_code="4_7c",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Property Code has Expired",
)
def rule_4_7c(ctx: RuleContext) -> Iterator[Finding]:
    """The property's latest ItemCategory must not be expired."""
    return _47_family(ctx, "4_7c")


@rule(
    "4_7d",
    legacy_code="4_7d",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Item Category has Expired",
)
def rule_4_7d(ctx: RuleContext) -> Iterator[Finding]:
    """The item's latest ItemCategory must not be expired."""
    return _47_family(ctx, "4_7d")


# ------------------------------------------------------------------
# Rule 4_8
# ------------------------------------------------------------------


@rule(
    "4_8",
    legacy_code="4_8",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Main Property on ModuleVersions of this Release has been "
        "assigned to more than one distinct SubCategories"
    ),
)
def rule_4_8(ctx: RuleContext) -> Iterator[Finding]:
    """A property maps to one subcategory per release cohort.

    Fact headers with a property and an open SubCategoryVersion on
    tables of module versions starting now fire when, across all
    such module versions, the property is paired with more than one
    distinct SubCategoryVID.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    property_scvs = _property_scvs_in_new_modules(ctx)
    for tv, _table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(header.is_key) or not _is_false(
            tvh.is_abstract
        ):
            continue
        if hv.property_id is None or hv.subcategory_vid is None:
            continue
        if not _member_mv_start_now(ctx, tv.table_vid):
            continue
        scv = snap.subcategory_versions_by_vid.get(hv.subcategory_vid)
        if scv is None or scv.end_release_id is not None:
            continue
        if len(property_scvs.get(hv.property_id, set())) <= 1:
            continue
        _collect_4_8(ctx, tv, header, hv, scv, findings)
    yield from _emit(findings)


def _property_scvs_in_new_modules(
    ctx: RuleContext,
) -> Dict[int, set[int]]:
    """PropertyID -> SubCategoryVIDs used in module versions starting now."""
    snap = ctx.snapshot

    def build() -> Dict[int, set[int]]:
        result: Dict[int, set[int]] = {}
        for tv2, _t2, header2, hv2, tvh2 in _rows_by_header_vid(ctx):
            if not _is_false(header2.is_key) or not _is_false(
                tvh2.is_abstract
            ):
                continue
            if hv2.property_id is None or hv2.subcategory_vid is None:
                continue
            if not _member_mv_start_now(ctx, tv2.table_vid):
                continue
            result.setdefault(hv2.property_id, set()).add(
                hv2.subcategory_vid
            )
        return result

    return snap.cache("assignments:property_scvs", build)


def _collect_4_8(
    ctx: RuleContext,
    tv: TableVersionRow,
    header: HeaderRow,
    hv: HeaderVersionRow,
    scv: Any,
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Emit 4_8 rows per ItemCategory row of the property."""
    snap = ctx.snapshot
    sc = (
        snap.subcategories_by_id.get(scv.subcategory_id)
        if scv.subcategory_id is not None
        else None
    )
    if sc is None or sc.category_id is None:
        return
    category = snap.categories_by_id.get(sc.category_id)
    if category is None:
        return
    for itc in _all_ics(snap, hv.property_id):
        key = (tv.table_vid, hv.header_vid, itc.code)
        findings.setdefault(
            key,
            Finding(
                objects=(
                    ObjectRef(
                        kind="header_version",
                        id=hv.header_vid,
                        code=hv.code,
                        name=header.direction,
                    ),
                    _tv_ref(tv),
                    ObjectRef(
                        kind="property",
                        id=hv.property_id,
                        code=itc.code,
                    ),
                    ObjectRef(
                        kind="subcategory",
                        id=sc.subcategory_id,
                        name=(sc.name or "")[:60],
                    ),
                    ObjectRef(
                        kind="category",
                        id=category.category_id,
                        code=category.code,
                    ),
                )
            ),
        )


# ------------------------------------------------------------------
# Rules 4_9a / 4_9b / 4_9c — default items in contexts
# ------------------------------------------------------------------


def _default_item_ics(
    ctx: RuleContext, item_id: Optional[int]
) -> Iterator[Tuple[ItemCategoryRow, Any]]:
    """Open default-item assignments to enumerated categories."""
    snap = ctx.snapshot
    for itc in _open_ics(snap, item_id):
        if not itc.is_default_item or itc.category_id is None:
            continue
        category = snap.categories_by_id.get(itc.category_id)
        if category is None or not category.is_enumerated:
            continue
        yield itc, category


@rule(
    "4_9a",
    legacy_code="4_9",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Default Item appears in Context of a Table from a module "
        "updated in Current Release"
    ),
)
def rule_4_9a(ctx: RuleContext) -> Iterator[Finding]:
    """Header contexts may not pin default items.

    Contexts of non-key, non-abstract headers on open TableVersions
    of module versions starting now: a composed item that is the
    open default item of an enumerated category fires.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None:
            continue
        if not _is_false(header.is_key) or not _is_false(
            tvh.is_abstract
        ):
            continue
        if not _member_mv_start_now(ctx, tv.table_vid):
            continue
        for cc in _context_ccs(snap, hv.context_id):
            for itc, category in _default_item_ics(ctx, cc.item_id):
                key = (
                    tv.table_vid,
                    hv.header_vid,
                    itc.item_id,
                    itc.code,
                )
                findings.setdefault(
                    key,
                    Finding(
                        objects=(
                            _header_ref(header, hv),
                            _tv_ref(tv),
                            ObjectRef(
                                kind="item",
                                id=itc.item_id,
                                code=itc.code,
                            ),
                            ObjectRef(
                                kind="category",
                                id=category.category_id,
                                code=category.code,
                            ),
                        )
                    ),
                )
    yield from _emit(findings)


@rule(
    "4_9b",
    legacy_code="4_9",
    family=_FAMILY,
    severity=SEVERITY_WARNING,
    description=(
        "Default Item appears in the whole-table Context of a "
        "module updated in Current Release"
    ),
)
def rule_4_9b(ctx: RuleContext) -> Iterator[Finding]:
    """Table contexts should not pin default items (warning)."""
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv in snap.table_versions:
        if tv.end_release_id is not None or tv.context_id is None:
            continue
        table = (
            snap.tables_by_id.get(tv.table_id)
            if tv.table_id is not None
            else None
        )
        if table is None or not _is_false(table.is_abstract):
            continue
        if not _member_mv_start_now(ctx, tv.table_vid):
            continue
        for cc in _context_ccs(snap, tv.context_id):
            for itc, category in _default_item_ics(ctx, cc.item_id):
                key = (tv.table_vid, itc.item_id, itc.code)
                findings.setdefault(
                    key,
                    Finding(
                        objects=(
                            _tv_ref(tv),
                            ObjectRef(
                                kind="item",
                                id=itc.item_id,
                                code=itc.code,
                            ),
                            ObjectRef(
                                kind="category",
                                id=category.category_id,
                                code=category.code,
                            ),
                        )
                    ),
                )
    yield from _emit(findings)


@rule(
    "4_9c",
    legacy_code="4_9",
    family=_FAMILY,
    severity=SEVERITY_WARNING,
    description=(
        "Default Item appears in Context of a CompoundItem updated "
        "in Current Release"
    ),
)
def rule_4_9c(ctx: RuleContext) -> Iterator[Finding]:
    """Compound-item contexts should not pin default items (warning).

    CompoundItemContexts starting in the current release (any end
    release, as in the SQL) fire once per ItemCategory row of the
    compound item and per default item found in the context.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for cic in snap.compound_item_contexts:
        if not rel.is_current(cic.start_release_id):
            continue
        for ic0 in _all_ics(snap, cic.item_id):
            c0_code = _category_code(snap, ic0.category_id)
            for cc in _context_ccs(snap, cic.context_id):
                for itc, category in _default_item_ics(
                    ctx, cc.item_id
                ):
                    key = (
                        cic.item_id,
                        ic0.code,
                        c0_code,
                        itc.item_id,
                        itc.code,
                    )
                    findings.setdefault(
                        key,
                        Finding(
                            objects=(
                                ObjectRef(
                                    kind="compound_item",
                                    id=cic.item_id,
                                    code=ic0.code,
                                    name=c0_code,
                                ),
                                ObjectRef(
                                    kind="item",
                                    id=itc.item_id,
                                    code=itc.code,
                                ),
                                ObjectRef(
                                    kind="category",
                                    id=category.category_id,
                                    code=category.code,
                                ),
                            )
                        ),
                    )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rule 4_10
# ------------------------------------------------------------------


@rule(
    "4_10",
    legacy_code="4_10",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Default Item appears in the Composition of a SubCategory "
        "associated with a Header"
    ),
)
def rule_4_10(ctx: RuleContext) -> Iterator[Finding]:
    """Header subcategories may not contain default items.

    Headers with a property and a SubCategoryVersion on open
    TableVersions of module versions starting now fire for each
    open default-item assignment among the subcategory's items,
    combined with each open ItemCategory / PropertyCategory of the
    property (as the SQL's joins do).
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None:
            continue
        if not _is_false(tvh.is_abstract):
            continue
        if hv.property_id is None or hv.subcategory_vid is None:
            continue
        if not _member_mv_start_now(ctx, tv.table_vid):
            continue
        if hv.property_id not in snap.properties_by_id:
            continue
        _collect_4_10(ctx, tv, header, hv, findings)
    yield from _emit(findings)


def _collect_4_10(
    ctx: RuleContext,
    tv: TableVersionRow,
    header: HeaderRow,
    hv: HeaderVersionRow,
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Emit 4_10 rows for one header's subcategory items."""
    snap = ctx.snapshot
    scv = (
        snap.subcategory_versions_by_vid.get(hv.subcategory_vid)
        if hv.subcategory_vid is not None
        else None
    )
    sc = (
        snap.subcategories_by_id.get(scv.subcategory_id)
        if scv is not None and scv.subcategory_id is not None
        else None
    )
    if scv is None or sc is None:
        return
    default_items = [
        (sci, itc)
        for sci in snap.subcategory_items
        if sci.subcategory_vid == scv.subcategory_vid
        for itc in _open_ics(snap, sci.item_id)
        if itc.is_default_item
    ]
    if not default_items:
        return
    prop_codes = [
        itp.code for itp in _open_ics(snap, hv.property_id)
    ]
    categories = _open_pc_categories(ctx, hv.property_id)
    for _sci, itc in default_items:
        for prop_code in prop_codes:
            for cat_id, cat_code in categories:
                key = (
                    tv.table_vid,
                    hv.header_vid,
                    itc.item_id,
                    prop_code,
                    cat_id,
                )
                findings.setdefault(
                    key,
                    Finding(
                        objects=(
                            _header_ref(header, hv),
                            _tv_ref(tv),
                            ObjectRef(
                                kind="property",
                                id=hv.property_id,
                                code=prop_code,
                            ),
                            ObjectRef(
                                kind="subcategory",
                                id=sc.subcategory_id,
                                name=sc.code,
                            ),
                            ObjectRef(
                                kind="item",
                                id=itc.item_id,
                                code=f"Default_ItemCode:{itc.code}"[
                                    :30
                                ],
                            ),
                            ObjectRef(
                                kind="category",
                                id=cat_id,
                                code=(
                                    f"PropertyCategoryCode: {cat_code}"
                                )[:50],
                            ),
                        )
                    ),
                )
