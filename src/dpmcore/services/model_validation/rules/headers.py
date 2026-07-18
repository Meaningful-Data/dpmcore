"""Family 3 modelling rules — header-level checks.

Port of the ``3_x`` INSERT blocks of ``check_modelling_rules_tidy``:
key-header requirements (3_1, 3_2, 3_6, 3_7, 3_8), main-property and
subcategory compatibility (3_3, 3_4, 3_9), header-tree structure
(3_5a, 3_5b, 3_15b, 3_16) and attribute-header relations via
``ConceptRelation``/``RelatedConcept`` (3_10a, 3_10b, 3_11, 3_12,
3_14, 3_15a).

The SQL reuses ViolationCodes 3_5, 3_10 and 3_15 for two distinct
checks each; rule ids carry letter suffixes while ``legacy_code``
keeps the SQL code. SQL Server string comparisons are
case-insensitive — literal comparisons (axis directions) are
normalised accordingly.
"""

from __future__ import annotations

from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from dpmcore.services.model_validation.registry import (
    Finding,
    RuleContext,
    rule,
)
from dpmcore.services.model_validation.snapshot import (
    HeaderRow,
    HeaderVersionRow,
    ItemCategoryRow,
    ModelSnapshot,
    SubCategoryRow,
    SubCategoryVersionRow,
    TableRow,
    TableVersionHeaderRow,
    TableVersionRow,
)
from dpmcore.services.model_validation.types import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    ObjectRef,
)

_FAMILY = "headers"

#: (table version, table, header, header version, tvh) join row.
_JoinRow = Tuple[
    TableVersionRow,
    TableRow,
    HeaderRow,
    HeaderVersionRow,
    TableVersionHeaderRow,
]

_ATTR_RELATION = "header_attributeHeader"


def _is_false(flag: Optional[bool]) -> bool:
    """Mirror SQL ``column = 0``: NULL rows never match."""
    return flag is not None and not flag


def _tv_ref(tv: TableVersionRow) -> ObjectRef:
    """Reference to a table version."""
    return ObjectRef(kind="table_version", id=tv.table_vid, code=tv.code)


def _header_ref(header: HeaderRow, hv: HeaderVersionRow) -> ObjectRef:
    """Reference to a header carrying its version code/direction."""
    return ObjectRef(
        kind="header",
        id=header.header_id,
        code=hv.code,
        name=header.direction,
    )


def _emit(findings: Dict[Tuple[Any, ...], Finding]) -> Iterator[Finding]:
    """Yield findings ordered by their deduplication key."""
    for key in sorted(findings, key=repr):
        yield findings[key]


def _rows_by_header_vid(ctx: RuleContext) -> List[_JoinRow]:
    """Join rows where TVH links by HeaderVID.

    Mirrors ``TableVersion JOIN Table JOIN Header JOIN HeaderVersion
    JOIN TableVersionHeader ON (tvh.HeaderVID = hv.HeaderVID AND
    tvh.TableVID = tv.TableVID)`` with ``h.TableID = t.TableID``.
    """
    snap = ctx.snapshot

    def build() -> List[_JoinRow]:
        rows: List[_JoinRow] = []
        for tvh in snap.table_version_headers:
            if tvh.header_vid is None:
                continue
            hv = snap.header_versions_by_vid.get(tvh.header_vid)
            tv = snap.table_versions_by_vid.get(tvh.table_vid)
            if hv is None or tv is None or hv.header_id is None:
                continue
            header = snap.headers_by_id.get(hv.header_id)
            if header is None:
                continue
            table = (
                snap.tables_by_id.get(tv.table_id)
                if tv.table_id is not None
                else None
            )
            if table is None or header.table_id != table.table_id:
                continue
            rows.append((tv, table, header, hv, tvh))
        return rows

    return snap.cache("headers:rows_by_header_vid", build)


def _rows_by_header_id(ctx: RuleContext) -> List[_JoinRow]:
    """Join rows where TVH links by HeaderID (rules 3_1, 3_2).

    Every HeaderVersion of the header is paired with the TVH row of
    the table version, mirroring ``tvh.HeaderID = h.HeaderID``.
    """
    snap = ctx.snapshot

    def build() -> List[_JoinRow]:
        hv_by_header = snap.header_versions_by_header()
        rows: List[_JoinRow] = []
        for tvh in snap.table_version_headers:
            tv = snap.table_versions_by_vid.get(tvh.table_vid)
            header = snap.headers_by_id.get(tvh.header_id)
            if tv is None or header is None:
                continue
            table = (
                snap.tables_by_id.get(tv.table_id)
                if tv.table_id is not None
                else None
            )
            if table is None or header.table_id != table.table_id:
                continue
            rows.extend(
                (tv, table, header, hv, tvh)
                for hv in hv_by_header.get(header.header_id, [])
            )
        return rows

    return snap.cache("headers:rows_by_header_id", build)


def _member_any_mv(ctx: RuleContext, table_vid: int) -> bool:
    """INNER JOIN mvc/mv membership: any existing module version."""
    snap = ctx.snapshot
    return any(
        mvc.module_vid in snap.module_versions_by_vid
        for mvc in snap.mvc_by_table_vid().get(table_vid, [])
    )


def _member_mv_start_now(ctx: RuleContext, table_vid: int) -> bool:
    """Membership in a module version starting in this release."""
    snap, rel = ctx.snapshot, ctx.release
    for mvc in snap.mvc_by_table_vid().get(table_vid, []):
        mv = snap.module_versions_by_vid.get(mvc.module_vid)
        if mv is not None and rel.is_current(mv.start_release_id):
            return True
    return False


def _member_open_mv_start_now(ctx: RuleContext, table_vid: int) -> bool:
    """Membership in an open module version starting now."""
    snap, rel = ctx.snapshot, ctx.release
    for mvc in snap.mvc_by_table_vid().get(table_vid, []):
        mv = snap.module_versions_by_vid.get(mvc.module_vid)
        if (
            mv is not None
            and mv.end_release_id is None
            and rel.is_current(mv.start_release_id)
        ):
            return True
    return False


def _group_ics(
    snap: ModelSnapshot,
) -> Dict[int, List[ItemCategoryRow]]:
    """ItemCategory rows grouped by item id."""
    grouped: Dict[int, List[ItemCategoryRow]] = {}
    for ic in snap.item_categories:
        grouped.setdefault(ic.item_id, []).append(ic)
    return grouped


def _all_ics(
    snap: ModelSnapshot, item_id: Optional[int]
) -> List[ItemCategoryRow]:
    """All ItemCategory rows of an item, any end release."""
    if item_id is None:
        return []
    grouped = snap.cache("headers:ic_by_item", lambda: _group_ics(snap))
    return grouped.get(item_id, [])


def _open_ics(
    snap: ModelSnapshot, item_id: Optional[int]
) -> List[ItemCategoryRow]:
    """Open ItemCategory rows of an item (INNER-join style)."""
    return [
        ic
        for ic in _all_ics(snap, item_id)
        if ic.end_release_id is None
    ]


def _open_pc_categories(
    ctx: RuleContext, property_id: Optional[int]
) -> List[Tuple[int, Optional[str]]]:
    """(CategoryID, Code) of the open PropertyCategory rows."""
    snap = ctx.snapshot
    if property_id is None:
        return []
    result: List[Tuple[int, Optional[str]]] = []
    for pc in snap.property_categories:
        if pc.property_id != property_id:
            continue
        if pc.end_release_id is not None or pc.category_id is None:
            continue
        category = snap.categories_by_id.get(pc.category_id)
        if category is not None:
            result.append((category.category_id, category.code))
    return result


def _attr_relations(
    ctx: RuleContext,
) -> Dict[int, Tuple[Set[str], Set[str]]]:
    """``header_attributeHeader`` relations by relation id.

    Returns relation id -> (guids with IsRelatedConcept = 1, guids
    with IsRelatedConcept = 0).
    """
    snap = ctx.snapshot

    def build() -> Dict[int, Tuple[Set[str], Set[str]]]:
        wanted = {
            cr.concept_relation_id
            for cr in snap.concept_relations
            if cr.type == _ATTR_RELATION
        }
        result: Dict[int, Tuple[Set[str], Set[str]]] = {}
        for rc in snap.related_concepts:
            if rc.concept_relation_id not in wanted:
                continue
            sides = result.setdefault(
                rc.concept_relation_id, (set(), set())
            )
            if rc.is_related_concept:
                sides[0].add(rc.concept_guid)
            elif _is_false(rc.is_related_concept):
                sides[1].add(rc.concept_guid)
        return result

    return snap.cache("headers:attr_relations", build)


def _relations_between(
    ctx: RuleContext,
    related_guid: Optional[str],
    base_guid: Optional[str],
) -> Set[int]:
    """Relation ids linking (IsRelated=1 guid, IsRelated=0 guid)."""
    if related_guid is None or base_guid is None:
        return set()
    return {
        relation_id
        for relation_id, (related, base) in _attr_relations(ctx).items()
        if related_guid in related and base_guid in base
    }


def _tv_header_rows(
    ctx: RuleContext, table_vid: int
) -> List[Tuple[HeaderRow, HeaderVersionRow, TableVersionHeaderRow]]:
    """(header, header version, tvh) rows of one table version."""
    snap = ctx.snapshot
    rows: List[
        Tuple[HeaderRow, HeaderVersionRow, TableVersionHeaderRow]
    ] = []
    for tvh in snap.tvh_by_table_vid().get(table_vid, []):
        if tvh.header_vid is None:
            continue
        hv = snap.header_versions_by_vid.get(tvh.header_vid)
        if hv is None or hv.header_id is None:
            continue
        header = snap.headers_by_id.get(hv.header_id)
        if header is not None:
            rows.append((header, hv, tvh))
    return rows


def _same_direction(a: Optional[str], b: Optional[str]) -> bool:
    """Case-insensitive direction equality (SQL CI collation)."""
    if a is None or b is None:
        return a == b
    return a.upper() == b.upper()


def _context_property_ids(
    snap: ModelSnapshot, context_id: Optional[int]
) -> Set[int]:
    """Property ids composed into a context."""
    if context_id is None:
        return set()
    return {
        cc.property_id
        for cc in snap.context_compositions_by_context().get(
            context_id, []
        )
    }


# ------------------------------------------------------------------
# Rule 3_1
# ------------------------------------------------------------------


@rule(
    "3_1",
    legacy_code="3_1",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Key Header without any attached Property in it",
)
def rule_3_1(ctx: RuleContext) -> Iterator[Finding]:
    """Every key header must carry a PropertyID.

    Open, current-release TableVersions of non-abstract tables in a
    module: any open HeaderVersion of a key header with a NULL
    PropertyID fires.
    """
    rel = ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, _tvh in _rows_by_header_id(ctx):
        if not _is_false(table.is_abstract):
            continue
        if not header.is_key or hv.property_id is not None:
            continue
        if tv.end_release_id is not None or hv.end_release_id is not None:
            continue
        if not rel.is_current(tv.start_release_id):
            continue
        if not _member_any_mv(ctx, tv.table_vid):
            continue
        key = (tv.table_vid, header.header_id, hv.code)
        findings.setdefault(
            key,
            Finding(objects=(_header_ref(header, hv), _tv_ref(tv))),
        )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rule 3_2
# ------------------------------------------------------------------


@rule(
    "3_2",
    legacy_code="3_2",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Key Header declared as Abstract is not allowed",
)
def rule_3_2(ctx: RuleContext) -> Iterator[Finding]:
    """Key headers may not be abstract.

    Open, current-release TableVersions of non-abstract tables: a
    key header attached through an abstract TableVersionHeader row
    fires (each open HeaderVersion is reported).
    """
    rel = ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_id(ctx):
        if not _is_false(table.is_abstract):
            continue
        if not tvh.is_abstract or not header.is_key:
            continue
        if tv.end_release_id is not None or hv.end_release_id is not None:
            continue
        if not rel.is_current(tv.start_release_id):
            continue
        key = (tv.table_vid, header.header_id, hv.code)
        findings.setdefault(
            key,
            Finding(objects=(_header_ref(header, hv), _tv_ref(tv))),
        )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rule 3_3
# ------------------------------------------------------------------


@rule(
    "3_3",
    legacy_code="3_3",
    family=_FAMILY,
    severity=SEVERITY_WARNING,
    description="Main Property on Sheet Header that is Not a Metric",
)
def rule_3_3(ctx: RuleContext) -> Iterator[Finding]:
    """Sheet-axis main properties must be metrics.

    Non-key, non-abstract Z-direction headers of open,
    current-release TableVersions (in a module) whose property is
    not a metric fire once per open PropertyCategory category.
    Severity mirrors the SQL ``isBlocking = 0``.
    """
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _matches_3_3(ctx, tv, table, header, hv, tvh):
            continue
        for cat_id, cat_code in _open_pc_categories(
            ctx, hv.property_id
        ):
            key = (tv.table_vid, header.header_id, cat_id)
            findings.setdefault(
                key,
                Finding(
                    objects=(
                        _header_ref(header, hv),
                        _tv_ref(tv),
                        ObjectRef(
                            kind="category", id=cat_id, code=cat_code
                        ),
                    )
                ),
            )
    yield from _emit(findings)


def _matches_3_3(
    ctx: RuleContext,
    tv: TableVersionRow,
    table: TableRow,
    header: HeaderRow,
    hv: HeaderVersionRow,
    tvh: TableVersionHeaderRow,
) -> bool:
    """The 3_3 row filter: non-metric property on a Z fact header."""
    snap, rel = ctx.snapshot, ctx.release
    if not _is_false(table.is_abstract):
        return False
    if tv.end_release_id is not None or hv.end_release_id is not None:
        return False
    if not rel.is_current(tv.start_release_id):
        return False
    if not _is_false(header.is_key) or not _is_false(tvh.is_abstract):
        return False
    if not _same_direction(header.direction, "Z"):
        return False
    if hv.property_id is None:
        return False
    prop = snap.properties_by_id.get(hv.property_id)
    if prop is None or not _is_false(prop.is_metric):
        return False
    return _member_any_mv(ctx, tv.table_vid)


# ------------------------------------------------------------------
# Rule 3_4
# ------------------------------------------------------------------


@rule(
    "3_4",
    legacy_code="3_4",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="SubCategoryVID on this Header has already expired",
)
def rule_3_4(ctx: RuleContext) -> Iterator[Finding]:
    """Headers may not reference expired SubCategoryVersions.

    Open HeaderVersions of open TableVersions (non-abstract table)
    in a module version starting in the current release fire when
    their SubCategoryVersion has a non-NULL EndReleaseID.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, _tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None or hv.end_release_id is not None:
            continue
        if hv.subcategory_vid is None:
            continue
        if not _member_mv_start_now(ctx, tv.table_vid):
            continue
        scv = snap.subcategory_versions_by_vid.get(hv.subcategory_vid)
        if scv is None or scv.end_release_id is None:
            continue
        resolved = _sc_and_category(snap, scv)
        if resolved is None:
            continue
        sc, category = resolved
        key = (tv.table_vid, header.header_id, scv.subcategory_id)
        findings.setdefault(
            key,
            Finding(
                objects=(
                    _header_ref(header, hv),
                    _tv_ref(tv),
                    ObjectRef(
                        kind="subcategory",
                        id=scv.subcategory_id,
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
    yield from _emit(findings)


def _sc_and_category(
    snap: ModelSnapshot, scv: SubCategoryVersionRow
) -> Optional[Tuple[SubCategoryRow, Any]]:
    """Resolve a SubCategoryVersion to (SubCategory, Category)."""
    sc = (
        snap.subcategories_by_id.get(scv.subcategory_id)
        if scv.subcategory_id is not None
        else None
    )
    if sc is None or sc.category_id is None:
        return None
    category = snap.categories_by_id.get(sc.category_id)
    if category is None:
        return None
    return sc, category


# ------------------------------------------------------------------
# Rules 3_5a / 3_5b
# ------------------------------------------------------------------


@rule(
    "3_5a",
    legacy_code="3_5",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Abstract Header has no non-Abstract Descendant headers"
    ),
)
def rule_3_5a(ctx: RuleContext) -> Iterator[Finding]:
    """Abstract headers need descendants.

    Open HeaderVersions attached abstractly to a table of an open
    module version starting in the current release fire when no
    TableVersionHeader of the same table version has them as
    parent.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if hv.end_release_id is not None or not tvh.is_abstract:
            continue
        if not _member_open_mv_start_now(ctx, tv.table_vid):
            continue
        has_child = any(
            tvh2.parent_header_id == tvh.header_id
            for tvh2 in snap.tvh_by_table_vid().get(tv.table_vid, [])
        )
        if has_child:
            continue
        key = (tv.table_vid, header.header_id)
        findings.setdefault(
            key,
            Finding(objects=(_header_ref(header, hv), _tv_ref(tv))),
        )
    yield from _emit(findings)


@rule(
    "3_5b",
    legacy_code="3_5",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Header whose Parent header does not belong to a "
        "TableVersionHeader of the same TableVID"
    ),
)
def rule_3_5b(ctx: RuleContext) -> Iterator[Finding]:
    """Parent headers must exist within the same table version.

    Open TableVersions in a module version starting in the current
    release fire for TVH rows whose ParentHeaderID is not among the
    HeaderIDs of the same table version.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, _table, header, hv, tvh in _rows_by_header_vid(ctx):
        if tv.end_release_id is not None:
            continue
        if tvh.parent_header_id is None:
            continue
        if not _member_mv_start_now(ctx, tv.table_vid):
            continue
        siblings = {
            tvh2.header_id
            for tvh2 in snap.tvh_by_table_vid().get(tv.table_vid, [])
        }
        if tvh.parent_header_id in siblings:
            continue
        key = (tv.table_vid, header.header_id)
        findings.setdefault(
            key,
            Finding(objects=(_header_ref(header, hv), _tv_ref(tv))),
        )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rule 3_6
# ------------------------------------------------------------------


@rule(
    "3_6",
    legacy_code="3_6",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Key Header with Metric Property attached",
)
def rule_3_6(ctx: RuleContext) -> Iterator[Finding]:
    """Key headers may only carry non-metric properties.

    Open, current-release TableVersions (in a module): key headers
    attached non-abstractly whose property is a metric fire, once
    per open ItemCategory code and PropertyCategory category.
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
        if not header.is_key or not _is_false(tvh.is_abstract):
            continue
        if hv.property_id is None:
            continue
        prop = snap.properties_by_id.get(hv.property_id)
        if prop is None or not prop.is_metric:
            continue
        if not _member_any_mv(ctx, tv.table_vid):
            continue
        _collect_property_category_rows(ctx, tv, header, hv, findings)
    yield from _emit(findings)


def _collect_property_category_rows(
    ctx: RuleContext,
    tv: TableVersionRow,
    header: HeaderRow,
    hv: HeaderVersionRow,
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Emit one row per (open IC code, open PC category) pair."""
    snap = ctx.snapshot
    for ic in _open_ics(snap, hv.property_id):
        for cat_id, cat_code in _open_pc_categories(
            ctx, hv.property_id
        ):
            key = (
                tv.table_vid,
                header.header_id,
                hv.property_id,
                ic.code,
                cat_id,
            )
            findings.setdefault(
                key,
                Finding(
                    objects=(
                        ObjectRef(
                            kind="property",
                            id=hv.property_id,
                            code=ic.code,
                        ),
                        _tv_ref(tv),
                        ObjectRef(
                            kind="category", id=cat_id, code=cat_code
                        ),
                    )
                ),
            )


# ------------------------------------------------------------------
# Rule 3_7
# ------------------------------------------------------------------


@rule(
    "3_7",
    legacy_code="3_7",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Property in Key Header is also assigned to Other Key Header"
    ),
)
def rule_3_7(ctx: RuleContext) -> Iterator[Finding]:
    """A property may sit on only one key header of a table.

    Pairs of open key HeaderVersions sharing a property within the
    same open, current-release TableVersion fire (lowest HeaderVID
    reported, mirroring ``hv.HeaderVID < hv2.HeaderVID``).
    """
    rel = ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None or hv.end_release_id is not None:
            continue
        if not rel.is_current(tv.start_release_id):
            continue
        if not header.is_key or not _is_false(tvh.is_abstract):
            continue
        if hv.property_id is None:
            continue
        for header2, hv2, _tvh2 in _tv_header_rows(ctx, tv.table_vid):
            if (
                not header2.is_key
                or hv2.end_release_id is not None
                or hv2.property_id is None
                or hv2.property_id != hv.property_id
                or hv.header_vid >= hv2.header_vid
            ):
                continue
            _collect_3_7(ctx, tv, hv, hv2, findings)
    yield from _emit(findings)


def _collect_3_7(
    ctx: RuleContext,
    tv: TableVersionRow,
    hv: HeaderVersionRow,
    hv2: HeaderVersionRow,
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Emit 3_7 rows per (IC code, PC category) combination."""
    snap = ctx.snapshot
    for ic in _open_ics(snap, hv.property_id):
        for cat_id, cat_code in _open_pc_categories(
            ctx, hv.property_id
        ):
            key = (
                tv.table_vid,
                hv.header_vid,
                hv2.header_vid,
                ic.code,
                cat_id,
            )
            findings.setdefault(
                key,
                Finding(
                    objects=(
                        ObjectRef(
                            kind="header_version",
                            id=hv.header_vid,
                            code=hv.code,
                        ),
                        ObjectRef(
                            kind="header_version",
                            id=hv2.header_vid,
                            code=hv2.code,
                        ),
                        _tv_ref(tv),
                        ObjectRef(
                            kind="property",
                            id=hv.property_id,
                            code=ic.code,
                        ),
                        ObjectRef(
                            kind="category", id=cat_id, code=cat_code
                        ),
                    )
                ),
            )


# ------------------------------------------------------------------
# Rule 3_8
# ------------------------------------------------------------------


def _property_in_tv_contexts(
    ctx: RuleContext, tv: TableVersionRow, property_id: int
) -> bool:
    """True when the property appears in a context of the table.

    Mirrors the 3_8 EXISTS: contexts of open, non-key, non-abstract
    HeaderVersions of the same table version, or the table
    version's own context.
    """
    snap = ctx.snapshot
    for header2, hv2, tvh2 in _tv_header_rows(ctx, tv.table_vid):
        if not _is_false(tvh2.is_abstract):
            continue
        if not _is_false(header2.is_key):
            continue
        if hv2.end_release_id is not None:
            continue
        if property_id in _context_property_ids(snap, hv2.context_id):
            return True
    return property_id in _context_property_ids(snap, tv.context_id)


def _left_open_ic_codes(
    snap: ModelSnapshot, item_id: Optional[int]
) -> Sequence[Optional[str]]:
    """LEFT JOIN ItemCategory + ``EndReleaseID IS NULL`` semantics.

    Items without any assignment pass once with a NULL code; items
    with assignments contribute only the open ones (an item with
    only expired assignments is filtered out entirely).
    """
    rows = _all_ics(snap, item_id)
    if not rows:
        return [None]
    return [ic.code for ic in rows if ic.end_release_id is None]


def _left_open_categories(
    ctx: RuleContext, property_id: Optional[int]
) -> Sequence[Tuple[Optional[int], Optional[str]]]:
    """LEFT JOIN PropertyCategory/Category open-rows semantics."""
    snap = ctx.snapshot
    rows = [
        pc
        for pc in snap.property_categories
        if pc.property_id == property_id
    ]
    if not rows:
        return [(None, None)]
    result: List[Tuple[Optional[int], Optional[str]]] = []
    for pc in rows:
        if pc.end_release_id is not None:
            continue
        category = (
            snap.categories_by_id.get(pc.category_id)
            if pc.category_id is not None
            else None
        )
        if category is None:
            result.append((None, None))
        else:
            result.append((category.category_id, category.code))
    return result


@rule(
    "3_8",
    legacy_code="3_8",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Property exists in Key Header and Context of the Same Table"
    ),
)
def rule_3_8(ctx: RuleContext) -> Iterator[Finding]:
    """Key-header properties must not appear in table contexts.

    Key headers (non-abstract TVH) of open, current-release
    TableVersions whose property also appears in a header or table
    context of the same table version fire. ItemCategory /
    PropertyCategory are LEFT-joined in the SQL: a property with
    only expired assignments is excluded, one with none passes with
    NULL codes.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _matches_3_8(ctx, tv, table, header, hv, tvh):
            continue
        for ic_code in _left_open_ic_codes(snap, hv.property_id):
            for cat_id, cat_code in _left_open_categories(
                ctx, hv.property_id
            ):
                key = (
                    tv.table_vid,
                    header.header_id,
                    ic_code,
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
                                code=ic_code,
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


def _matches_3_8(
    ctx: RuleContext,
    tv: TableVersionRow,
    table: TableRow,
    header: HeaderRow,
    hv: HeaderVersionRow,
    tvh: TableVersionHeaderRow,
) -> bool:
    """The 3_8 row filter: key-header property found in a context."""
    rel = ctx.release
    if not _is_false(table.is_abstract):
        return False
    if tv.end_release_id is not None:
        return False
    if not rel.is_current(tv.start_release_id):
        return False
    if not header.is_key or not _is_false(tvh.is_abstract):
        return False
    if hv.property_id is None:
        return False
    if not _member_any_mv(ctx, tv.table_vid):
        return False
    return _property_in_tv_contexts(ctx, tv, hv.property_id)


# ------------------------------------------------------------------
# Rule 3_9
# ------------------------------------------------------------------


def _compatible_3_9(c1: Any, c2: Any) -> bool:
    """The 3_9 compatibility predicate between two categories."""
    if (
        c1.category_id == c2.category_id
        and bool(c1.is_enumerated)
        and bool(c2.is_enumerated)
    ):
        return True
    return c1.code == "_NA" and c2.code in ("_NA", "_PR")


@rule(
    "3_9",
    legacy_code="3_9",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "The Category of SubCategory is Not Compatible with the "
        "Category of Property"
    ),
)
def rule_3_9(ctx: RuleContext) -> Iterator[Finding]:
    """Subcategory and property categories must be compatible.

    Headers with both a property and an open SubCategoryVersion, on
    open TableVersions of module versions starting now: every
    PropertyCategory row (any end release, as in the SQL) whose
    category is neither identical-and-enumerated nor covered by the
    ``_NA`` / ``_PR`` exception fires.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, _tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None:
            continue
        if hv.property_id is None or hv.subcategory_vid is None:
            continue
        if not _member_mv_start_now(ctx, tv.table_vid):
            continue
        scv = snap.subcategory_versions_by_vid.get(hv.subcategory_vid)
        if scv is None or scv.end_release_id is not None:
            continue
        resolved = _sc_and_category(snap, scv)
        if resolved is None:
            continue
        sc, c2 = resolved
        _collect_3_9(ctx, tv, header, hv, scv, sc, c2, findings)
    yield from _emit(findings)


def _collect_3_9(
    ctx: RuleContext,
    tv: TableVersionRow,
    header: HeaderRow,
    hv: HeaderVersionRow,
    scv: SubCategoryVersionRow,
    sc: SubCategoryRow,
    c2: Any,
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Emit 3_9 rows for one header against each PropertyCategory."""
    snap = ctx.snapshot
    ic_codes = [ic.code for ic in _open_ics(snap, hv.property_id)]
    for pc in snap.property_categories:
        if pc.property_id != hv.property_id or pc.category_id is None:
            continue
        c1 = snap.categories_by_id.get(pc.category_id)
        if c1 is None or _compatible_3_9(c1, c2):
            continue
        for ic_code in ic_codes:
            key = (
                tv.table_vid,
                header.header_id,
                pc.category_id,
                ic_code,
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
                            code=ic_code,
                        ),
                        ObjectRef(
                            kind="subcategory",
                            id=scv.subcategory_id,
                            name=(sc.name or "")[:60],
                        ),
                    )
                ),
            )


# ------------------------------------------------------------------
# Rules 3_10a / 3_10b
# ------------------------------------------------------------------


@rule(
    "3_10a",
    legacy_code="3_10",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Attribute Header not associated with a Unique other active "
        "Header of the Same Direction of the Table"
    ),
)
def rule_3_10a(ctx: RuleContext) -> Iterator[Finding]:
    """Attribute headers relate to exactly one same-direction header.

    For each attribute header on an open, current-release
    TableVersion, the number of distinct ``header_attributeHeader``
    relations to headers of the same direction within the table
    version must be exactly one.
    """
    rel = ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None or hv.end_release_id is not None:
            continue
        if not rel.is_current(tv.start_release_id):
            continue
        if not header.is_attribute or not _is_false(tvh.is_abstract):
            continue
        relations: Set[int] = set()
        for header2, _hv2, _tvh2 in _tv_header_rows(ctx, tv.table_vid):
            if not _same_direction(
                header2.direction, header.direction
            ):
                continue
            relations |= _relations_between(
                ctx, header.row_guid, header2.row_guid
            )
        if len(relations) == 1:
            continue
        key = (tv.table_vid, hv.header_vid)
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
                )
            ),
        )
    yield from _emit(findings)


@rule(
    "3_10b",
    legacy_code="3_10",
    family=_FAMILY,
    severity=SEVERITY_WARNING,
    description=(
        "Main Property assigned to Header belongs to empty-string "
        "allowed data type es"
    ),
)
def rule_3_10b(ctx: RuleContext) -> Iterator[Finding]:
    """Warn on header properties with the ``es`` data type.

    Every header version of a table in a module version starting in
    the current release whose property's data type code is ``es``
    fires, once per ItemCategory / PropertyCategory row (the SQL
    applies no other filter — not even open-version checks).
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, _table, header, hv, _tvh in _rows_by_header_vid(ctx):
        if hv.property_id is None:
            continue
        if not _member_mv_start_now(ctx, tv.table_vid):
            continue
        prop = snap.properties_by_id.get(hv.property_id)
        if prop is None or prop.data_type_id is None:
            continue
        datatype = snap.datatypes_by_id.get(prop.data_type_id)
        if datatype is None or datatype.code != "es":
            continue
        _collect_3_10b(ctx, tv, header, hv, findings)
    yield from _emit(findings)


def _collect_3_10b(
    ctx: RuleContext,
    tv: TableVersionRow,
    header: HeaderRow,
    hv: HeaderVersionRow,
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Emit 3_10b rows per (ItemCategory, PropertyCategory) pair."""
    snap = ctx.snapshot
    for ic in _all_ics(snap, hv.property_id):
        for pc in snap.property_categories:
            if pc.property_id != hv.property_id:
                continue
            category = (
                snap.categories_by_id.get(pc.category_id)
                if pc.category_id is not None
                else None
            )
            if category is None:
                continue
            key = (
                tv.table_vid,
                hv.header_vid,
                ic.code,
                category.category_id,
            )
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
                            code=ic.code,
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
# Rules 3_11 / 3_12 — attribute placement
# ------------------------------------------------------------------


def _attribute_rows(
    ctx: RuleContext,
) -> Iterator[Tuple[_JoinRow, HeaderRow, HeaderVersionRow]]:
    """Attribute headers paired with their related base headers.

    Yields (attribute join row, base header, base header version)
    for each ``header_attributeHeader`` relation where the
    attribute header (IsRelatedConcept = 1) and the base header
    (IsRelatedConcept = 0) sit in the same open, current-release
    TableVersion of a non-abstract table.
    """
    rel = ctx.release
    for row in _rows_by_header_vid(ctx):
        tv, table, header, hv, tvh = row
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None or hv.end_release_id is not None:
            continue
        if not rel.is_current(tv.start_release_id):
            continue
        if not header.is_attribute or not _is_false(tvh.is_abstract):
            continue
        for header2, hv2, _tvh2 in _tv_header_rows(ctx, tv.table_vid):
            if _relations_between(
                ctx, header.row_guid, header2.row_guid
            ):
                yield row, header2, hv2


def _attr_header_finding(
    tv: TableVersionRow, header: HeaderRow, hv: HeaderVersionRow
) -> Finding:
    """Standard finding shape for the attribute-header rules."""
    return Finding(
        objects=(
            ObjectRef(
                kind="header_version",
                id=hv.header_vid,
                code=hv.code,
                name=header.direction,
            ),
            _tv_ref(tv),
        )
    )


@rule(
    "3_11",
    legacy_code="3_11",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Definition of Attributes for Fact Headers on a direction "
        "on which Main Property is not defined"
    ),
)
def rule_3_11(ctx: RuleContext) -> Iterator[Finding]:
    """Attributes require their fact header to carry a property.

    Fires when an attribute header relates to a non-key header
    whose HeaderVersion has no property.
    """
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for (tv, _t, header, hv, _tvh), header2, hv2 in _attribute_rows(
        ctx
    ):
        if not _is_false(header2.is_key) or hv2.property_id is not None:
            continue
        findings.setdefault(
            (tv.table_vid, hv.header_vid),
            _attr_header_finding(tv, header, hv),
        )
    yield from _emit(findings)


@rule(
    "3_12",
    legacy_code="3_12",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Definition of Attributes for Key Headers on a direction "
        "different than that of the Key Header"
    ),
)
def rule_3_12(ctx: RuleContext) -> Iterator[Finding]:
    """Key-header attributes must share the key header's direction."""
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for (tv, _t, header, hv, _tvh), header2, _hv2 in _attribute_rows(
        ctx
    ):
        if not header2.is_key:
            continue
        if _same_direction(header2.direction, header.direction):
            continue
        findings.setdefault(
            (tv.table_vid, hv.header_vid),
            _attr_header_finding(tv, header, hv),
        )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rules 3_14 / 3_15a — data-type changes on attribute relations
# ------------------------------------------------------------------


def _datatype_change(
    ctx: RuleContext, hv: HeaderVersionRow
) -> Optional[Tuple[str, str]]:
    """Data-type codes (new, old) when the property type changed.

    Compares the header version's property data type against the
    predecessor version closed by the current release
    (``hv3.EndReleaseID = @CurrentRelease``). Returns None when
    unchanged or not resolvable.
    """
    snap, rel = ctx.snapshot, ctx.release
    if hv.header_id is None or hv.property_id is None:
        return None
    prop = snap.properties_by_id.get(hv.property_id)
    if prop is None or prop.data_type_id is None:
        return None
    for hv3 in snap.header_versions_by_header().get(hv.header_id, []):
        if not rel.ends_in_current(hv3.end_release_id):
            continue
        if hv3.property_id is None:
            continue
        prop3 = snap.properties_by_id.get(hv3.property_id)
        if prop3 is None or prop3.data_type_id is None:
            continue
        if prop3.data_type_id == prop.data_type_id:
            continue
        datatype = snap.datatypes_by_id.get(prop.data_type_id)
        datatype3 = snap.datatypes_by_id.get(prop3.data_type_id)
        if datatype is None or datatype3 is None:
            continue
        return (datatype.code or "", datatype3.code or "")
    return None


@rule(
    "3_14",
    legacy_code="3_14",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Attribute Header Main Property data type differs from the "
        "previous version"
    ),
)
def rule_3_14(ctx: RuleContext) -> Iterator[Finding]:
    """Attribute headers may not change their property data type."""
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for (tv, _t, header, hv, _tvh), _h2, _hv2 in _attribute_rows(ctx):
        change = _datatype_change(ctx, hv)
        if change is None:
            continue
        new_code, old_code = change
        message = (
            f"Attribute Header Main Property data Type: {new_code} "
            f"is different than that of Previous Version: {old_code}"
        )
        key = (tv.table_vid, hv.header_vid)
        if key not in findings:
            finding = _attr_header_finding(tv, header, hv)
            findings[key] = Finding(
                objects=finding.objects, message=message
            )
    yield from _emit(findings)


@rule(
    "3_15a",
    legacy_code="3_15",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Header with an associated Attribute changed Property data "
        "type vs the previous version"
    ),
)
def rule_3_15a(ctx: RuleContext) -> Iterator[Finding]:
    """Headers with attributes may not change property data types.

    Here the reported header is the base one (IsRelatedConcept = 0)
    and the related header must be an attribute.
    """
    rel = ctx.release
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if tv.end_release_id is not None or hv.end_release_id is not None:
            continue
        if not rel.is_current(tv.start_release_id):
            continue
        if not _is_false(tvh.is_abstract):
            continue
        if not _has_attribute_partner(ctx, tv, header):
            continue
        change = _datatype_change(ctx, hv)
        if change is None:
            continue
        new_code, old_code = change
        message = (
            "Header with an associated Attribute changed Property "
            f"with current data type: {new_code} which is different "
            f"than the previous data type: {old_code}"
        )
        key = (tv.table_vid, hv.header_vid)
        if key not in findings:
            finding = _attr_header_finding(tv, header, hv)
            findings[key] = Finding(
                objects=finding.objects, message=message
            )
    yield from _emit(findings)


def _has_attribute_partner(
    ctx: RuleContext, tv: TableVersionRow, header: HeaderRow
) -> bool:
    """True when an attribute header of the same TV relates to it."""
    for header2, _hv2, _tvh2 in _tv_header_rows(ctx, tv.table_vid):
        if not header2.is_attribute:
            continue
        if _relations_between(ctx, header2.row_guid, header.row_guid):
            return True
    return False


# ------------------------------------------------------------------
# Rule 3_15b — parent-first ordering
# ------------------------------------------------------------------


@rule(
    "3_15b",
    legacy_code="3_15",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "The Order of a Header violates the ParentFirst specification"
    ),
)
def rule_3_15b(ctx: RuleContext) -> Iterator[Finding]:
    """Header order must respect the parent's ParentFirst flag.

    For TVH rows of tables in open module versions starting in the
    current release: a child ordered before a parent-first parent,
    or after a parent-last parent, fires.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if hv.end_release_id is not None:
            continue
        if tvh.parent_header_id is None or tvh.order is None:
            continue
        if not _member_open_mv_start_now(ctx, tv.table_vid):
            continue
        for tvh2 in snap.tvh_by_table_vid().get(tv.table_vid, []):
            if tvh2.header_id != tvh.parent_header_id:
                continue
            if tvh2.order is None:
                continue
            diff = tvh.order - tvh2.order
            violates = (tvh2.parent_first and diff < 0) or (
                _is_false(tvh2.parent_first) and diff > 0
            )
            if not violates:
                continue
            message = (
                "The Order of a Header violates ParentFirst "
                f"specification. Child_Order={tvh.order}  "
                f"Parent_Order={tvh2.order}  "
                f"ParentFirst={int(bool(tvh2.parent_first))}"
            )
            key = (tv.table_vid, header.header_id, tvh2.header_id)
            findings.setdefault(
                key,
                Finding(
                    objects=(_header_ref(header, hv), _tv_ref(tv)),
                    message=message,
                ),
            )
    yield from _emit(findings)


# ------------------------------------------------------------------
# Rule 3_16
# ------------------------------------------------------------------


@rule(
    "3_16",
    legacy_code="3_16",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "An Abstract Header cannot have any Property or Context "
        "assigned to it"
    ),
)
def rule_3_16(ctx: RuleContext) -> Iterator[Finding]:
    """Abstract headers must be bare.

    Open HeaderVersions attached abstractly to tables of module
    versions starting in the current release fire when they carry a
    property or a context. The property code passes through a LEFT
    join on ItemCategory (all rows, as in the SQL).
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, table, header, hv, tvh in _rows_by_header_vid(ctx):
        if not _is_false(table.is_abstract):
            continue
        if not tvh.is_abstract or hv.end_release_id is not None:
            continue
        if hv.context_id is None and hv.property_id is None:
            continue
        if not _member_mv_start_now(ctx, tv.table_vid):
            continue
        ics = _all_ics(snap, hv.property_id)
        ic_codes: Sequence[Optional[str]] = (
            [ic.code for ic in ics] if ics else [None]
        )
        for ic_code in ic_codes:
            key = (tv.table_vid, header.header_id, ic_code)
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
                    )
                ),
            )
    yield from _emit(findings)
