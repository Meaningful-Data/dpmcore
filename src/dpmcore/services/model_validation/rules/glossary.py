"""Glossary rules — family 6 (code hygiene and catalog integrity).

Each rule translates one ``INSERT INTO ModelViolations`` block of the
``check_modelling_rules_tidy`` stored procedure whose ``ViolationCode``
is ``6_*``. The SQL join/WHERE logic is replicated against the
in-memory :class:`~dpmcore.services.model_validation.snapshot
.ModelSnapshot`; release arithmetic goes through
:class:`~dpmcore.services.model_validation.release_context
.ReleaseContext` predicates (never literal sentinel ids).

Conventions shared by several rules:

* SQL ``isnumeric(x)`` is replicated as "digits only after trimming"
  (:func:`_sql_isnumeric`). SQL Server ``isnumeric`` also accepts
  signs, decimals and currency symbols, but the modelling intent of
  these checks is plain digit codes, so the stricter digits-only
  reading is used.
* "Essentially unique" name comparisons remove ``' '``, ``'.'``,
  ``'('``, ``')'`` and ``'_'`` exactly like the SQL ``replace`` chain
  and compare case-insensitively, mirroring the case-insensitive
  collation of the EBA DPM databases (:func:`_essential_name`).
* SQL equality never matches ``NULL`` operands; every comparison
  below excludes ``None`` the same way the original predicate does.
"""

from __future__ import annotations

from typing import (
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
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
    HeaderRow,
    HeaderVersionRow,
    ItemCategoryRow,
    ItemRow,
    ModelSnapshot,
    PropertyCategoryRow,
    PropertyRow,
    ReleaseRow,
    SubCategoryRow,
    SubCategoryVersionRow,
    TableVersionCellRow,
    TableVersionRow,
)
from dpmcore.services.model_validation.types import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    ObjectRef,
)

RowT = TypeVar("RowT")

_ASCII_LOWER = "abcdefghijklmnopqrstuvwxyz"

#: DataTypeIDs compatible with metric properties (SQL rule 6_3).
_METRIC_DATATYPE_IDS = frozenset({1, 2, 9, 10})

#: DataTypeID of the ``monetary`` data type (SQL rule 6_4).
_MONETARY_DATATYPE_ID = 9

#: DataTypeID of the ``enumeration`` data type (SQL rules 6_13/6_14).
_ENUMERATION_DATATYPE_ID = 8


# ------------------------------------------------------------------
# Generic helpers
# ------------------------------------------------------------------


def _lookup(index: Dict[int, RowT], key: Optional[int]) -> Optional[RowT]:
    """Index lookup tolerating a NULL foreign key.

    Args:
        index: Primary-key index of a snapshot store.
        key: Possibly-NULL foreign key value.

    Returns:
        The row, or None when the key is NULL or dangling (in SQL
        terms, the INNER JOIN drops the row).
    """
    if key is None:
        return None
    return index.get(key)


def _has_inner_space(code: Optional[str]) -> bool:
    """SQL ``charindex(' ', trim(code)) > 0`` (NULL never matches)."""
    return code is not None and " " in code.strip()


def _sql_isnumeric(text: str) -> bool:
    """Digits-only reading of SQL ``isnumeric()``.

    SQL Server ``isnumeric`` also accepts signs, decimal points and
    currency symbols; the code-hygiene rules intend plain digit
    sequences, so this helper returns True only for non-empty,
    all-digit strings (after trimming).
    """
    stripped = text.strip()
    return stripped != "" and stripped.isdigit()


def _essential_name(name: str) -> str:
    """Normalise a name for the "essentially unique" comparisons.

    Mirrors the SQL ``replace`` chain removing ``' '``, ``'.'``,
    ``')'``, ``'('`` and ``'_'``; the final case fold replicates the
    case-insensitive collation under which the SQL comparison runs.
    """
    for char in " .()_":
        name = name.replace(char, "")
    return name.lower()


def _active_assignment(
    rel: ReleaseContext,
    start_release_id: Optional[int],
    end_release_id: Optional[int],
) -> bool:
    """SQL ``(End IS NULL AND Start<>9999) OR End=9999`` pattern."""
    return (
        end_release_id is None and not rel.is_draft(start_release_id)
    ) or rel.is_draft(end_release_id)


def _outside_current(
    rel: ReleaseContext, start_release_id: Optional[int]
) -> bool:
    """SQL ``Start <> @CurrentRelease AND Start <> 9999`` pattern."""
    return start_release_id is not None and not rel.is_current(
        start_release_id
    )


def _short_code(code: Optional[str]) -> str:
    """SQL ``trim(left(code, 20))`` with NULL treated as empty."""
    return (code or "")[:20].strip()


def _finding_key(
    finding: Finding,
) -> Tuple[Tuple[Tuple[str, str, str], ...], str]:
    """Deterministic sort key for findings."""
    objects = tuple(
        (ref.kind, str(ref.id), ref.code or "")
        for ref in finding.objects
    )
    return (objects, finding.message or "")


def _emit(findings: Iterable[Finding]) -> Iterator[Finding]:
    """Deduplicate (SQL ``SELECT DISTINCT``) and order findings."""
    return iter(sorted(dict.fromkeys(findings), key=_finding_key))


# ------------------------------------------------------------------
# Shared derived indexes (cached on the snapshot)
# ------------------------------------------------------------------


def _ic_by_item(
    snap: ModelSnapshot,
) -> Dict[int, List[ItemCategoryRow]]:
    """``ItemCategory`` rows grouped by ``item_id``."""

    def build() -> Dict[int, List[ItemCategoryRow]]:
        grouped: Dict[int, List[ItemCategoryRow]] = {}
        for ic in snap.item_categories:
            grouped.setdefault(ic.item_id, []).append(ic)
        return grouped

    return snap.cache("glossary:ic_by_item", build)


def _pc_by_property(
    snap: ModelSnapshot,
) -> Dict[int, List[PropertyCategoryRow]]:
    """``PropertyCategory`` rows grouped by ``property_id``."""

    def build() -> Dict[int, List[PropertyCategoryRow]]:
        grouped: Dict[int, List[PropertyCategoryRow]] = {}
        for pc in snap.property_categories:
            grouped.setdefault(pc.property_id, []).append(pc)
        return grouped

    return snap.cache("glossary:pc_by_property", build)


_PropJoinRow = Tuple[
    PropertyRow, ItemCategoryRow, PropertyCategoryRow, CategoryRow
]


def _prop_assignments(snap: ModelSnapshot) -> List[_PropJoinRow]:
    """Rows of the recurring property/category join.

    Materialises ``Property p JOIN ItemCategory ic ON
    ic.ItemID = p.PropertyID JOIN PropertyCategory pc ON
    pc.PropertyID = p.PropertyID JOIN Category c ON
    c.CategoryID = pc.CategoryID`` used by many family-6 rules.
    """

    def build() -> List[_PropJoinRow]:
        rows: List[_PropJoinRow] = []
        for prop in snap.properties:
            for ic in _ic_by_item(snap).get(prop.property_id, []):
                for pc in _pc_by_property(snap).get(
                    prop.property_id, []
                ):
                    category = _lookup(
                        snap.categories_by_id, pc.category_id
                    )
                    if category is not None:
                        rows.append((prop, ic, pc, category))
        return rows

    return snap.cache("glossary:prop_assignments", build)


_HeaderUsage = Tuple[HeaderVersionRow, HeaderRow, TableVersionRow]


def _header_usages(snap: ModelSnapshot) -> List[_HeaderUsage]:
    """(HeaderVersion, Header, TableVersion) triples linked by TVH."""

    def build() -> List[_HeaderUsage]:
        rows: List[_HeaderUsage] = []
        for tvh in snap.table_version_headers:
            hv = _lookup(snap.header_versions_by_vid, tvh.header_vid)
            tv = snap.table_versions_by_vid.get(tvh.table_vid)
            if hv is None or tv is None:
                continue
            header = _lookup(snap.headers_by_id, hv.header_id)
            if header is not None:
                rows.append((hv, header, tv))
        return rows

    return snap.cache("glossary:header_usages", build)


def _scv_by_subcategory(
    snap: ModelSnapshot,
) -> Dict[int, List[SubCategoryVersionRow]]:
    """``SubCategoryVersion`` rows grouped by ``subcategory_id``."""

    def build() -> Dict[int, List[SubCategoryVersionRow]]:
        grouped: Dict[int, List[SubCategoryVersionRow]] = {}
        for scv in snap.subcategory_versions:
            if scv.subcategory_id is not None:
                grouped.setdefault(scv.subcategory_id, []).append(scv)
        return grouped

    return snap.cache("glossary:scv_by_subcategory", build)


def _sci_item_ids_by_scv(
    snap: ModelSnapshot,
) -> Dict[int, List[int]]:
    """``SubCategoryItem`` item ids grouped by ``subcategory_vid``."""

    def build() -> Dict[int, List[int]]:
        grouped: Dict[int, List[int]] = {}
        for sci in snap.subcategory_items:
            grouped.setdefault(sci.subcategory_vid, []).append(
                sci.item_id
            )
        return grouped

    return snap.cache("glossary:sci_item_ids_by_scv", build)


# ------------------------------------------------------------------
# Shared ObjectRef builders
# ------------------------------------------------------------------


def _prop_refs(
    prop: PropertyRow, ic: ItemCategoryRow, category: CategoryRow
) -> Tuple[ObjectRef, ...]:
    """(property, category) reference pair used by many rules."""
    return (
        ObjectRef(kind="property", id=prop.property_id, code=ic.code),
        ObjectRef(
            kind="category",
            id=category.category_id,
            code=category.code,
        ),
    )


def _item_refs(
    ic: ItemCategoryRow, category: CategoryRow
) -> Tuple[ObjectRef, ...]:
    """(item, category) reference pair used by several rules."""
    return (
        ObjectRef(kind="item", id=ic.item_id, code=ic.code),
        ObjectRef(
            kind="category",
            id=category.category_id,
            code=category.code,
        ),
    )


def _category_ref(category: CategoryRow) -> Tuple[ObjectRef, ...]:
    """Single (category,) reference tuple."""
    return (
        ObjectRef(
            kind="category",
            id=category.category_id,
            code=category.code,
        ),
    )


def _subcategory_refs(
    sc: SubCategoryRow, category: CategoryRow
) -> Tuple[ObjectRef, ...]:
    """(subcategory, category) reference pair."""
    return (
        ObjectRef(
            kind="subcategory", id=sc.subcategory_id, code=sc.code
        ),
        ObjectRef(
            kind="category",
            id=category.category_id,
            code=category.code,
        ),
    )


def _header_refs(
    hv: HeaderVersionRow, tv: TableVersionRow
) -> Tuple[ObjectRef, ...]:
    """(header_version, table_version) reference pair."""
    return (
        ObjectRef(
            kind="header_version",
            id=hv.header_vid,
            code=hv.code,
            name=hv.label,
        ),
        ObjectRef(
            kind="table_version", id=tv.table_vid, code=tv.code
        ),
    )


def _cell_refs(
    tvc: TableVersionCellRow, tv: TableVersionRow
) -> Tuple[ObjectRef, ...]:
    """(cell, table_version) reference pair for cell-level rules."""
    return (
        ObjectRef(kind="cell", id=tvc.cell_id, code=tvc.cell_code),
        ObjectRef(
            kind="table_version", id=tv.table_vid, code=tv.code
        ),
    )


# ------------------------------------------------------------------
# Rules 6_1 / 6_2 — unique open category assignment for used objects
# ------------------------------------------------------------------


def _context_member_ids(
    snap: ModelSnapshot,
    rel: ReleaseContext,
    include_variables: bool,
    member: str,
) -> Set[int]:
    """Context-composition member ids used in the current release.

    Collects ``ContextComposition.<member>`` values reachable from
    header/table (and optionally variable) versions whose
    ``StartReleaseID`` is the current release.
    """
    versions: List[Tuple[Optional[int], Optional[int]]] = [
        (hv.start_release_id, hv.context_id)
        for hv in snap.header_versions
    ]
    versions += [
        (tv.start_release_id, tv.context_id)
        for tv in snap.table_versions
    ]
    if include_variables:
        versions += [
            (vv.start_release_id, vv.context_id)
            for vv in snap.variable_versions
        ]
    cc_by_ctx = snap.context_compositions_by_context()
    found: Set[int] = set()
    for start_release_id, context_id in versions:
        if context_id is None or not rel.is_current(start_release_id):
            continue
        for cc in cc_by_ctx.get(context_id, []):
            value: Optional[int] = getattr(cc, member)
            if value is not None:
                found.add(value)
    return found


def _employed_property_ids(
    snap: ModelSnapshot, rel: ReleaseContext
) -> Set[int]:
    """Property ids employed by objects defined in this release."""
    employed = _context_member_ids(snap, rel, False, "property_id")
    for hv in snap.header_versions:
        if (
            rel.is_current(hv.start_release_id)
            and hv.property_id is not None
        ):
            employed.add(hv.property_id)
    for tv in snap.table_versions:
        if (
            rel.is_current(tv.start_release_id)
            and tv.property_id is not None
        ):
            employed.add(tv.property_id)
    return employed


@rule(
    "6_1",
    legacy_code="6_1",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Property employed in the current release without exactly "
        "one open PropertyCategory"
    ),
)
def rule_6_1(ctx: RuleContext) -> Iterator[Finding]:
    """A used property must have one open PropertyCategory.

    For every property employed by an object defined in the current
    release (header/table version contexts or main properties), there
    has to exist one and only one PropertyCategory with a NULL
    EndReleaseID.
    """
    snap, rel = ctx.snapshot, ctx.release
    employed = _employed_property_ids(snap, rel)
    findings = []
    for prop in snap.properties:
        if prop.property_id not in employed:
            continue
        open_count = sum(
            1
            for pc in _pc_by_property(snap).get(prop.property_id, [])
            if pc.end_release_id is None
        )
        if open_count != 1:
            findings.append(
                Finding(
                    objects=(
                        ObjectRef(
                            kind="property", id=prop.property_id
                        ),
                    )
                )
            )
    return _emit(findings)


def _employed_item_ids(
    snap: ModelSnapshot, rel: ReleaseContext
) -> Set[int]:
    """Item ids employed by objects defined in this release."""
    employed = _context_member_ids(snap, rel, True, "item_id")
    employed.update(prop.property_id for prop in snap.properties)
    for cic in snap.compound_item_contexts:
        if rel.is_current(cic.start_release_id):
            employed.add(cic.item_id)
    for sci in snap.subcategory_items:
        scv = snap.subcategory_versions_by_vid.get(sci.subcategory_vid)
        if scv is not None and rel.is_current(scv.start_release_id):
            employed.add(sci.item_id)
    return employed


@rule(
    "6_2",
    legacy_code="6_2",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Item employed in the current release without exactly one "
        "open ItemCategory"
    ),
)
def rule_6_2(ctx: RuleContext) -> Iterator[Finding]:
    """A used item must have one open ItemCategory.

    For every item employed by any object defined in the current
    release (contexts of header/table/variable versions, properties,
    compound item contexts or subcategory compositions), there has to
    exist one and only one ItemCategory with a NULL EndReleaseID.
    """
    snap, rel = ctx.snapshot, ctx.release
    employed = _employed_item_ids(snap, rel)
    findings = []
    for item in snap.items:
        if item.item_id not in employed:
            continue
        open_count = sum(
            1
            for ic in _ic_by_item(snap).get(item.item_id, [])
            if ic.end_release_id is None
        )
        if open_count != 1:
            findings.append(
                Finding(
                    objects=(ObjectRef(kind="item", id=item.item_id),)
                )
            )
    return _emit(findings)


# ------------------------------------------------------------------
# Rules 6_3 / 6_4 — metric flag versus data type
# ------------------------------------------------------------------


@rule(
    "6_3",
    legacy_code="6_3",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Property is metric but belongs to an incompatible data type"
    ),
)
def rule_6_3(ctx: RuleContext) -> Iterator[Finding]:
    """A metric property must belong to a compatible data type.

    Metric properties (with an open ItemCategory) whose DataTypeID is
    not one of the metric-compatible ids (1, 2, 9, 10) are flagged.
    A NULL DataTypeID is excluded here, matching the SQL ``NOT IN``
    semantics (rule 6_16 reports missing data types).
    """
    snap = ctx.snapshot
    findings = []
    for prop, ic, _pc, category in _prop_assignments(snap):
        if (
            ic.end_release_id is None
            and prop.is_metric is True
            and prop.data_type_id is not None
            and prop.data_type_id not in _METRIC_DATATYPE_IDS
        ):
            findings.append(
                Finding(objects=_prop_refs(prop, ic, category))
            )
    return _emit(findings)


@rule(
    "6_4",
    legacy_code="6_4",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Property is not metric although it belongs to the monetary "
        "data type"
    ),
)
def rule_6_4(ctx: RuleContext) -> Iterator[Finding]:
    """A monetary property has to be a metric.

    Non-metric properties of the monetary data type (DataTypeID 9)
    with open ItemCategory and PropertyCategory assignments are
    flagged.
    """
    snap = ctx.snapshot
    findings = []
    for prop, ic, pc, category in _prop_assignments(snap):
        if (
            ic.end_release_id is None
            and prop.is_metric is False
            and prop.data_type_id == _MONETARY_DATATYPE_ID
            and pc.end_release_id is None
        ):
            findings.append(
                Finding(objects=_prop_refs(prop, ic, category))
            )
    return _emit(findings)


# ------------------------------------------------------------------
# Rule 6_5 — non-enumerated categories with members
# ------------------------------------------------------------------


@rule(
    "6_5",
    legacy_code="6_5",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Non-enumerated category (other than Not applicable) with "
        "associated items or subcategories"
    ),
)
def rule_6_5(ctx: RuleContext) -> Iterator[Finding]:
    """Only enumerated categories may have items or subcategories.

    A non-enumerated category (except the one named "Not applicable")
    cannot appear in any ItemCategory or SubCategory row. Categories
    with a NULL name or NULL IsEnumerated are excluded, matching the
    SQL NULL comparisons.
    """
    snap = ctx.snapshot
    item_cats = {ic.category_id for ic in snap.item_categories}
    sub_cats = {sc.category_id for sc in snap.subcategories}
    findings = [
        Finding(objects=_category_ref(category))
        for category in snap.categories
        if (
            category.name is not None
            and category.name.strip() != "Not applicable"
            and category.is_enumerated is False
            and (
                category.category_id in item_cats
                or category.category_id in sub_cats
            )
        )
    ]
    return _emit(findings)


# ------------------------------------------------------------------
# Rules 6_6a / 6_6b — duplicate item / property codes
# ------------------------------------------------------------------


@rule(
    "6_6a",
    legacy_code="6_6",
    family="glossary",
    severity=SEVERITY_ERROR,
    description="Duplicate ItemCode within a specific category",
)
def rule_6_6a(ctx: RuleContext) -> Iterator[Finding]:
    """An item code has to be unique within its category.

    For non-property items, the number of distinct items carrying the
    same ItemCategory code within the same category must be exactly
    one. Mirroring the SQL NULL semantics, an assignment with a NULL
    code matches no other assignment (count 0) and is reported.
    """
    snap = ctx.snapshot
    owners: Dict[Tuple[str, int], Set[int]] = {}
    for ic in snap.item_categories:
        if ic.code is not None and ic.category_id is not None:
            owners.setdefault((ic.code, ic.category_id), set()).add(
                ic.item_id
            )
    findings = []
    for ic in snap.item_categories:
        item = snap.items_by_id.get(ic.item_id)
        category = _lookup(snap.categories_by_id, ic.category_id)
        if item is None or category is None:
            continue
        if item.is_property is not False:
            continue
        count = (
            len(owners[(ic.code, category.category_id)])
            if ic.code is not None
            else 0
        )
        if count != 1:
            findings.append(Finding(objects=_item_refs(ic, category)))
    return _emit(findings)


def _has_active_pc(
    snap: ModelSnapshot, rel: ReleaseContext, property_id: int
) -> bool:
    """True when the property has an active PropertyCategory row."""
    return any(
        _active_assignment(rel, pc.start_release_id, pc.end_release_id)
        for pc in _pc_by_property(snap).get(property_id, [])
    )


@rule(
    "6_6b",
    legacy_code="6_6",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Duplicate PropertyCode within a specific category amongst "
        "active items"
    ),
)
def rule_6_6b(ctx: RuleContext) -> Iterator[Finding]:
    """A property code has to be unique amongst active assignments.

    For property items with active ItemCategory and PropertyCategory
    rows, the number of distinct properties carrying the same
    ItemCategory code (across all categories, as in the SQL subquery)
    must be exactly one.
    """
    snap, rel = ctx.snapshot, ctx.release
    owners: Dict[str, Set[int]] = {}
    for ic in snap.item_categories:
        if (
            ic.code is not None
            and _active_assignment(
                rel, ic.start_release_id, ic.end_release_id
            )
            and _has_active_pc(snap, rel, ic.item_id)
        ):
            owners.setdefault(ic.code, set()).add(ic.item_id)
    findings = []
    for ic in snap.item_categories:
        item = snap.items_by_id.get(ic.item_id)
        if item is None or item.is_property is not True:
            continue
        if not _active_assignment(
            rel, ic.start_release_id, ic.end_release_id
        ):
            continue
        findings.extend(_r66b_findings(snap, rel, ic, owners))
    return _emit(findings)


def _r66b_findings(
    snap: ModelSnapshot,
    rel: ReleaseContext,
    ic: ItemCategoryRow,
    owners: Dict[str, Set[int]],
) -> List[Finding]:
    """Findings of rule 6_6b for one active ItemCategory row."""
    findings = []
    count = (
        len(owners.get(ic.code, ())) if ic.code is not None else 0
    )
    for pc in _pc_by_property(snap).get(ic.item_id, []):
        category = _lookup(snap.categories_by_id, pc.category_id)
        if category is None or not _active_assignment(
            rel, pc.start_release_id, pc.end_release_id
        ):
            continue
        if count != 1:
            findings.append(Finding(objects=_item_refs(ic, category)))
    return findings


# ------------------------------------------------------------------
# Rule 6_7 — metrics in enumerated property categories
# ------------------------------------------------------------------


@rule(
    "6_7",
    legacy_code="6_7",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Property that is metric belongs to an enumerated (property) "
        "category"
    ),
)
def rule_6_7(ctx: RuleContext) -> Iterator[Finding]:
    """A metric can never belong to an enumerated property category.

    Metric properties whose open PropertyCategory points to an
    enumerated category (and whose ItemCategory is open) are flagged.
    """
    snap = ctx.snapshot
    findings = []
    for prop, ic, pc, category in _prop_assignments(snap):
        if (
            prop.is_metric is True
            and category.is_enumerated is True
            and pc.end_release_id is None
            and ic.end_release_id is None
        ):
            findings.append(
                Finding(objects=_prop_refs(prop, ic, category))
            )
    return _emit(findings)


# ------------------------------------------------------------------
# Rule 6_8 — signs on cells with non-metric main properties
# ------------------------------------------------------------------


def _main_props_by_header(
    snap: ModelSnapshot, table_vid: int
) -> Dict[int, Set[int]]:
    """Header id -> main property ids on one table version."""
    props: Dict[int, Set[int]] = {}
    for tvh in snap.tvh_by_table_vid().get(table_vid, []):
        hv = _lookup(snap.header_versions_by_vid, tvh.header_vid)
        if hv is None or hv.property_id is None:
            continue
        header = _lookup(snap.headers_by_id, hv.header_id)
        if header is not None:
            props.setdefault(header.header_id, set()).add(
                hv.property_id
            )
    return props


def _cell_has_nonmetric_property(
    snap: ModelSnapshot,
    cell_id: int,
    header_props: Dict[int, Set[int]],
) -> bool:
    """True when a header of the cell carries a non-metric property."""
    cell = snap.cells_by_id.get(cell_id)
    if cell is None:
        return False
    property_ids: Set[int] = set()
    for header_id in (cell.column_id, cell.row_id, cell.sheet_id):
        if header_id is not None:
            property_ids.update(header_props.get(header_id, ()))
    for property_id in property_ids:
        prop = snap.properties_by_id.get(property_id)
        if prop is not None and prop.is_metric is False:
            return True
    return False


@rule(
    "6_8",
    legacy_code="6_8",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Sign set on a cell whose corresponding main property is "
        "non-metric"
    ),
)
def rule_6_8(ctx: RuleContext) -> Iterator[Finding]:
    """No sign is allowed on cells of non-metric main properties.

    For table versions starting in the current release, a non-void
    cell with a non-empty sign is flagged when any header version of
    that table version attached to one of the cell's axes carries a
    non-metric main property.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for tv in snap.table_versions:
        if not rel.is_current(tv.start_release_id):
            continue
        header_props: Optional[Dict[int, Set[int]]] = None
        for tvc in snap.tvc_by_table_vid().get(tv.table_vid, []):
            if (
                tvc.is_void is not False
                or tvc.sign is None
                or tvc.sign == ""
            ):
                continue
            if header_props is None:
                header_props = _main_props_by_header(
                    snap, tv.table_vid
                )
            if _cell_has_nonmetric_property(
                snap, tvc.cell_id, header_props
            ):
                findings.append(Finding(objects=_cell_refs(tvc, tv)))
    return _emit(findings)


# ------------------------------------------------------------------
# Rules 6_9 / 6_10 — default items of enumerated categories
# ------------------------------------------------------------------


@rule(
    "6_9",
    legacy_code="6_9",
    family="glossary",
    severity=SEVERITY_ERROR,
    description="Enumerated category without exactly one default item",
)
def rule_6_9(ctx: RuleContext) -> Iterator[Finding]:
    """An enumerated category must have one default item.

    Enumerated categories (except codes ``_PR``, ``_TE`` and ``AS``)
    must have exactly one distinct item with an open, default-flagged
    ItemCategory assignment.
    """
    snap = ctx.snapshot
    defaults: Dict[int, Set[int]] = {}
    for ic in snap.item_categories:
        if (
            ic.end_release_id is None
            and ic.is_default_item is True
            and ic.category_id is not None
        ):
            defaults.setdefault(ic.category_id, set()).add(ic.item_id)
    findings = [
        Finding(objects=_category_ref(category))
        for category in snap.categories
        if (
            category.is_enumerated is True
            and category.code is not None
            and category.code not in ("_PR", "_TE", "AS")
            and len(defaults.get(category.category_id, ())) != 1
        )
    ]
    return _emit(findings)


@rule(
    "6_10",
    legacy_code="6_10",
    family="glossary",
    severity=SEVERITY_ERROR,
    description="Enumerated category with more than one default item",
)
def rule_6_10(ctx: RuleContext) -> Iterator[Finding]:
    """An enumerated category must have only one default item.

    Enumerated categories (except codes ``_PR`` and ``_TE``) with
    more than one distinct default item across all ItemCategory rows
    are flagged.

    Note:
        The SQL block for 6_10 is commented out in the stored
        procedure ("DEACTIVATE AS IS INCLUDED WITHIN 6_9"); the rule
        is retained in the catalogue and implemented from that
        deactivated block, which — unlike 6_9 — applies no
        EndReleaseID filter to the default-item count.
    """
    snap = ctx.snapshot
    defaults: Dict[int, Set[int]] = {}
    for ic in snap.item_categories:
        if ic.is_default_item is True and ic.category_id is not None:
            defaults.setdefault(ic.category_id, set()).add(ic.item_id)
    findings = [
        Finding(objects=_category_ref(category))
        for category in snap.categories
        if (
            category.is_enumerated is True
            and category.code is not None
            and category.code not in ("_PR", "_TE")
            and len(defaults.get(category.category_id, ())) > 1
        )
    ]
    return _emit(findings)


# ------------------------------------------------------------------
# Rule family 6_11a..6_11k — codes with embedded spaces
# ------------------------------------------------------------------

_SpaceCandidates = Iterator[
    Tuple[Optional[str], Tuple[ObjectRef, ...]]
]
_SpaceCollector = Callable[
    [ModelSnapshot, ReleaseContext], _SpaceCandidates
]


def _space_frameworks(
    snap: ModelSnapshot, rel: ReleaseContext
) -> _SpaceCandidates:
    """6_11a candidates: codes of new frameworks having modules."""
    used = {
        module.framework_id
        for module in snap.modules
        if module.framework_id is not None
    }
    seasoned: Set[int] = set()
    for mv in snap.module_versions:
        module = _lookup(snap.modules_by_id, mv.module_id)
        if (
            module is not None
            and module.framework_id is not None
            and _outside_current(rel, mv.start_release_id)
        ):
            seasoned.add(module.framework_id)
    for framework in snap.frameworks:
        if (
            framework.framework_id in used
            and framework.framework_id not in seasoned
        ):
            yield (
                framework.code,
                (
                    ObjectRef(
                        kind="framework",
                        id=framework.framework_id,
                        code=framework.code,
                    ),
                ),
            )


def _space_modules(
    snap: ModelSnapshot, rel: ReleaseContext
) -> _SpaceCandidates:
    """6_11b candidates: module versions starting in this release."""
    for mv in snap.module_versions:
        if rel.is_current(mv.start_release_id):
            yield (
                mv.code,
                (
                    ObjectRef(
                        kind="module_version",
                        id=mv.module_vid,
                        code=mv.code,
                    ),
                ),
            )


def _space_tables(
    snap: ModelSnapshot, rel: ReleaseContext
) -> _SpaceCandidates:
    """6_11c candidates: table versions starting in this release."""
    for tv in snap.table_versions:
        if rel.is_current(tv.start_release_id):
            yield (
                tv.code,
                (
                    ObjectRef(
                        kind="table_version",
                        id=tv.table_vid,
                        code=tv.code,
                    ),
                ),
            )


def _space_tablegroups(
    snap: ModelSnapshot, rel: ReleaseContext
) -> _SpaceCandidates:
    """6_11d candidates: table groups starting in this release."""
    for tg in snap.table_groups:
        if rel.is_current(tg.start_release_id):
            yield (
                tg.code,
                (
                    ObjectRef(
                        kind="table_group",
                        id=tg.table_group_id,
                        code=tg.code,
                    ),
                ),
            )


def _space_headers(
    snap: ModelSnapshot, rel: ReleaseContext
) -> _SpaceCandidates:
    """6_11e candidates: header versions starting in this release."""
    for hv in snap.header_versions:
        if hv.code is not None and rel.is_current(
            hv.start_release_id
        ):
            yield (
                hv.code,
                (
                    ObjectRef(
                        kind="header_version",
                        id=hv.header_vid,
                        code=hv.code,
                    ),
                ),
            )


def _space_variables(
    snap: ModelSnapshot, rel: ReleaseContext
) -> _SpaceCandidates:
    """6_11f candidates: variable versions starting in this release."""
    for vv in snap.variable_versions:
        if vv.code is not None and rel.is_current(
            vv.start_release_id
        ):
            yield (
                vv.code,
                (
                    ObjectRef(
                        kind="variable_version",
                        id=vv.variable_vid,
                        code=vv.code,
                    ),
                ),
            )


def _space_items(
    snap: ModelSnapshot, rel: ReleaseContext
) -> _SpaceCandidates:
    """6_11g candidates: open item assignments of this release."""
    for ic in snap.item_categories:
        item = snap.items_by_id.get(ic.item_id)
        category = _lookup(snap.categories_by_id, ic.category_id)
        if (
            item is not None
            and category is not None
            and item.is_property is False
            and ic.code is not None
            and rel.is_current(ic.start_release_id)
            and ic.end_release_id is None
        ):
            yield (ic.code, _item_refs(ic, category))


def _space_properties(
    snap: ModelSnapshot, rel: ReleaseContext
) -> _SpaceCandidates:
    """6_11h candidates: open property assignments of this release."""
    for ic in snap.item_categories:
        item = snap.items_by_id.get(ic.item_id)
        category = _lookup(snap.categories_by_id, ic.category_id)
        if (
            item is not None
            and category is not None
            and item.is_property is True
            and ic.code is not None
            and rel.is_current(ic.start_release_id)
            and ic.end_release_id is None
            and any(
                pc.end_release_id is None
                for pc in _pc_by_property(snap).get(ic.item_id, [])
            )
        ):
            yield (
                ic.code,
                (
                    ObjectRef(
                        kind="property", id=ic.item_id, code=ic.code
                    ),
                    ObjectRef(
                        kind="category",
                        id=category.category_id,
                        code=category.code,
                    ),
                ),
            )


def _space_subcategories(
    snap: ModelSnapshot, rel: ReleaseContext
) -> _SpaceCandidates:
    """6_11i candidates: subcategories that are new in this release."""
    for sc in snap.subcategories:
        category = _lookup(snap.categories_by_id, sc.category_id)
        if category is None:
            continue
        if any(
            _outside_current(rel, scv.start_release_id)
            for scv in _scv_by_subcategory(snap).get(
                sc.subcategory_id, []
            )
        ):
            continue
        yield (sc.code, _subcategory_refs(sc, category))


def _seasoned_category_ids(
    snap: ModelSnapshot, rel: ReleaseContext
) -> Set[int]:
    """Categories referenced by rows created before this release."""
    seasoned: Set[int] = set()
    for scv in snap.subcategory_versions:
        sc = _lookup(snap.subcategories_by_id, scv.subcategory_id)
        if (
            sc is not None
            and sc.category_id is not None
            and _outside_current(rel, scv.start_release_id)
        ):
            seasoned.add(sc.category_id)
    for scc in snap.supercategory_compositions:
        if _outside_current(rel, scc.start_release_id):
            seasoned.update((scc.category_id, scc.supercategory_id))
    assignments: List[Tuple[Optional[int], Optional[int]]] = [
        (ic.category_id, ic.start_release_id)
        for ic in snap.item_categories
    ]
    assignments += [
        (pc.category_id, pc.start_release_id)
        for pc in snap.property_categories
    ]
    for category_id, start_release_id in assignments:
        if category_id is not None and _outside_current(
            rel, start_release_id
        ):
            seasoned.add(category_id)
    return seasoned


def _space_categories(
    snap: ModelSnapshot, rel: ReleaseContext
) -> _SpaceCandidates:
    """6_11j candidates: categories that are new in this release."""
    seasoned = _seasoned_category_ids(snap, rel)
    for category in snap.categories:
        if category.category_id not in seasoned:
            yield (category.code, _category_ref(category))


def _space_operations(
    snap: ModelSnapshot, rel: ReleaseContext
) -> _SpaceCandidates:
    """6_11k candidates: operations that are new in this release."""
    seasoned = {
        opv.operation_id
        for opv in snap.operation_versions
        if opv.operation_id is not None
        and _outside_current(rel, opv.start_release_id)
    }
    for op in snap.operation_list:
        if op.operation_id not in seasoned:
            yield (
                op.code,
                (
                    ObjectRef(
                        kind="operation",
                        id=op.operation_id,
                        code=op.code,
                    ),
                ),
            )


def _register_code_space_rule(
    suffix: str, label: str, collect: _SpaceCollector
) -> None:
    """Register one member of the 6_11 "code with spaces" family."""

    @rule(
        f"6_11{suffix}",
        legacy_code="6_11",
        family="glossary",
        severity=SEVERITY_ERROR,
        description=f"{label} code with spaces in between",
    )
    def check(ctx: RuleContext) -> Iterator[Finding]:
        """Flag object codes containing embedded spaces (6_11)."""
        findings = [
            Finding(objects=objects)
            for code, objects in collect(ctx.snapshot, ctx.release)
            if _has_inner_space(code)
        ]
        return _emit(findings)


#: 6_11 sub-rules in the order the blocks appear in the SQL file.
_SPACE_RULE_SPECS: Tuple[Tuple[str, str, _SpaceCollector], ...] = (
    ("a", "FRAMEWORK", _space_frameworks),
    ("b", "MODULE", _space_modules),
    ("c", "TABLE", _space_tables),
    ("d", "TABLEGROUP", _space_tablegroups),
    ("e", "HEADER", _space_headers),
    ("f", "VARIABLE", _space_variables),
    ("g", "ITEM", _space_items),
    ("h", "PROPERTY", _space_properties),
    ("i", "SUBCATEGORY", _space_subcategories),
    ("j", "CATEGORY", _space_categories),
    ("k", "OPERATION", _space_operations),
)

for _suffix, _label, _collector in _SPACE_RULE_SPECS:
    _register_code_space_rule(_suffix, _label, _collector)


# ------------------------------------------------------------------
# Rules 6_12 / 6_19 — header code hygiene
# ------------------------------------------------------------------


@rule(
    "6_12",
    legacy_code="6_12",
    family="glossary",
    severity=SEVERITY_ERROR,
    description="Header code that is not numeric",
)
def rule_6_12(ctx: RuleContext) -> Iterator[Finding]:
    """A header version code is required to be numeric.

    Header versions starting in the current release, used by an open
    table version, whose code is not a plain digit sequence are
    flagged (see :func:`_sql_isnumeric` for the ``isnumeric``
    reading).
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for hv, _header, tv in _header_usages(snap):
        if (
            hv.code is not None
            and not _sql_isnumeric(hv.code)
            and rel.is_current(hv.start_release_id)
            and tv.end_release_id is None
        ):
            findings.append(Finding(objects=_header_refs(hv, tv)))
    return _emit(findings)


@rule(
    "6_19",
    legacy_code="6_19",
    family="glossary",
    severity=SEVERITY_ERROR,
    description="Header code that is NULL or blank",
)
def rule_6_19(ctx: RuleContext) -> Iterator[Finding]:
    """Each header must have a non-null and non-blank code.

    Header versions starting in the current release, used by an open
    table version, whose code is NULL or blank after trimming are
    flagged.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for hv, _header, tv in _header_usages(snap):
        if (
            (hv.code is None or hv.code.strip() == "")
            and rel.is_current(hv.start_release_id)
            and tv.end_release_id is None
        ):
            findings.append(Finding(objects=_header_refs(hv, tv)))
    return _emit(findings)


# ------------------------------------------------------------------
# Rules 6_13 / 6_14 / 6_16 — data types of properties
# ------------------------------------------------------------------


@rule(
    "6_13",
    legacy_code="6_13",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Property belonging to an enumerated category whose data "
        "type is not enumeration"
    ),
)
def rule_6_13(ctx: RuleContext) -> Iterator[Finding]:
    """Properties of enumerated categories need the enumeration type.

    A property assigned (via PropertyCategory) to an enumerated
    category must have DataTypeID 8 (enumeration). A NULL DataTypeID
    is excluded, matching the SQL ``<>`` comparison (rule 6_16
    reports missing data types).
    """
    snap = ctx.snapshot
    findings = []
    for prop, ic, _pc, category in _prop_assignments(snap):
        if (
            category.is_enumerated is True
            and prop.data_type_id is not None
            and prop.data_type_id != _ENUMERATION_DATATYPE_ID
        ):
            findings.append(
                Finding(objects=_prop_refs(prop, ic, category))
            )
    return _emit(findings)


@rule(
    "6_14",
    legacy_code="6_14",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Property belonging to a non-enumerated category (except "
        "_NA) whose data type is enumeration"
    ),
)
def rule_6_14(ctx: RuleContext) -> Iterator[Finding]:
    """Enumeration type is reserved for enumerated categories.

    A property assigned to a non-enumerated category (except the one
    coded ``_NA``) must never have DataTypeID 8 (enumeration).
    """
    snap = ctx.snapshot
    findings = []
    for prop, ic, _pc, category in _prop_assignments(snap):
        if (
            category.is_enumerated is False
            and prop.data_type_id == _ENUMERATION_DATATYPE_ID
            and category.code is not None
            and category.code != "_NA"
        ):
            findings.append(
                Finding(objects=_prop_refs(prop, ic, category))
            )
    return _emit(findings)


@rule(
    "6_16",
    legacy_code="6_16",
    family="glossary",
    severity=SEVERITY_ERROR,
    description="Property is not associated with any data type",
)
def rule_6_16(ctx: RuleContext) -> Iterator[Finding]:
    """A property must always be associated with a data type.

    Properties (joined to their item/property/category assignments)
    with a NULL DataTypeID are flagged.
    """
    snap = ctx.snapshot
    findings = []
    for prop, ic, _pc, category in _prop_assignments(snap):
        if prop.data_type_id is None:
            findings.append(
                Finding(objects=_prop_refs(prop, ic, category))
            )
    return _emit(findings)


# ------------------------------------------------------------------
# Rules 6_15 / 6_20 / 6_21 — property code prefix conventions
# ------------------------------------------------------------------


def _numeric_suffix(code: Optional[str]) -> Optional[str]:
    """Numeric part of a property code after its 2-char prefix.

    Returns ``code[2:]`` when the code is longer than two characters
    and the remainder is a digit sequence, mirroring the SQL
    ``len(Code)>2 AND isnumeric(right(Code, len(Code)-2))=1``
    predicate (see :func:`_sql_isnumeric`); otherwise None.
    """
    if code is None or len(code) <= 2 or not _sql_isnumeric(code[2:]):
        return None
    return code[2:]


def _numeric_suffix_owners(
    snap: ModelSnapshot,
) -> Dict[str, Set[int]]:
    """Numeric code suffix -> property ids carrying that suffix."""
    owners: Dict[str, Set[int]] = {}
    for prop in snap.properties:
        for ic in _ic_by_item(snap).get(prop.property_id, []):
            suffix = _numeric_suffix(ic.code)
            if suffix is not None:
                owners.setdefault(suffix, set()).add(
                    prop.property_id
                )
    return owners


@rule(
    "6_15",
    legacy_code="6_15",
    family="glossary",
    severity=SEVERITY_WARNING,
    description=(
        "Property code numeric part (after the 2-character prefix) "
        "is not unique amongst properties"
    ),
)
def rule_6_15(ctx: RuleContext) -> Iterator[Finding]:
    """The numeric part of a property code should be unique.

    If a property code is numeric after its first two characters,
    that numeric part has to be unique amongst all properties whose
    codes share the same feature.
    """
    snap = ctx.snapshot
    owners = _numeric_suffix_owners(snap)
    findings = []
    for prop, ic, _pc, category in _prop_assignments(snap):
        suffix = _numeric_suffix(ic.code)
        if suffix is None:
            continue
        if owners[suffix] - {prop.property_id}:
            findings.append(
                Finding(
                    message=(
                        "A Property code is numeric after its first "
                        "2 characters but the numeric part "
                        f"({suffix}) is not unique and is shared by "
                        "other Properties also"
                    ),
                    objects=_prop_refs(prop, ic, category),
                )
            )
    return _emit(findings)


def _dpm1_prefix(
    code: Optional[str], valid_first: Set[str]
) -> Optional[Tuple[str, str, str]]:
    """Parse a candidate datatype/flowtype code prefix (rule 6_20).

    Returns ``(first, second, remainder)`` of the trimmed code when
    the raw code is longer than two characters, the first two trimmed
    characters are ASCII lowercase letters, the first is a known
    DPM1-mapped datatype code and the second is ``i`` or ``d``;
    otherwise None.
    """
    if code is None or len(code) <= 2:
        return None
    trimmed = code.strip()
    if len(trimmed) < 2:
        return None
    first, second = trimmed[0], trimmed[1]
    if first not in _ASCII_LOWER or second not in _ASCII_LOWER:
        return None
    if first not in valid_first or second not in ("i", "d"):
        return None
    return (first, second, trimmed[2:])


def _r620_mismatch(
    prefix: Tuple[str, str, str],
    datatype_code: Optional[str],
    prop: PropertyRow,
) -> bool:
    """Mismatch predicate of rule 6_20 for a parsed prefix.

    A NULL datatype code makes the first-letter comparison unknown
    in SQL (never true), so it is skipped here the same way.
    """
    first, second, remainder = prefix
    expected_flow = "d" if prop.period_type == "flow" else "i"
    return (
        not _sql_isnumeric(remainder)
        or (datatype_code is not None and first != datatype_code)
        or second != expected_flow
    )


@rule(
    "6_20",
    legacy_code="6_20",
    family="glossary",
    severity=SEVERITY_WARNING,
    description=(
        "A Property code has been defined with a datatype and "
        "flowtype prefix, but either the rest of the code is not "
        "numeric or the prefix does not match the property data "
        "type and flow type"
    ),
)
def rule_6_20(ctx: RuleContext) -> Iterator[Finding]:
    """A datatype/flowtype code prefix has to match the property.

    For assignments touched in the current release whose code starts
    with a DPM1-compatible datatype letter (per the ``dt -> d``,
    ``u/es/o -> s`` remap of
    :meth:`~dpmcore.services.model_validation.snapshot.ModelSnapshot
    .dpm1_datatype_codes`) followed by ``i``/``d``, the remainder
    must be numeric, the first letter must equal the property's
    remapped datatype code and the second letter must match its
    period type (``d`` for flow, ``i`` otherwise).
    """
    snap, rel = ctx.snapshot, ctx.release
    dpm1 = snap.dpm1_datatype_codes()
    valid_first = {
        code for code in dpm1.values() if code is not None
    }
    findings = []
    for prop, ic, pc, category in _prop_assignments(snap):
        prefix = _dpm1_prefix(ic.code, valid_first)
        if prefix is None:
            continue
        if not (
            rel.is_current(pc.start_release_id)
            or rel.is_current(ic.start_release_id)
        ):
            continue
        data_type_id = prop.data_type_id
        if data_type_id is None or data_type_id not in dpm1:
            continue
        if _r620_mismatch(prefix, dpm1[data_type_id], prop):
            findings.append(
                Finding(objects=_prop_refs(prop, ic, category))
            )
    return _emit(findings)


@rule(
    "6_21",
    legacy_code="6_21",
    family="glossary",
    severity=SEVERITY_ERROR,
    description="Property code cannot be a plain numeric code",
)
def rule_6_21(ctx: RuleContext) -> Iterator[Finding]:
    """A property code cannot be a plain numeric code.

    Property code assignments starting in the current release whose
    code is a plain digit sequence are flagged.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for prop, ic, _pc, category in _prop_assignments(snap):
        if (
            rel.is_current(ic.start_release_id)
            and ic.code is not None
            and _sql_isnumeric(ic.code)
        ):
            findings.append(
                Finding(objects=_prop_refs(prop, ic, category))
            )
    return _emit(findings)


# ------------------------------------------------------------------
# Rules 6_22 / 6_23 / 6_32 / 6_33 — subcategory versions
# ------------------------------------------------------------------


def _new_open_scvs(
    snap: ModelSnapshot, rel: ReleaseContext
) -> Iterator[
    Tuple[SubCategoryRow, CategoryRow, SubCategoryVersionRow]
]:
    """Open SubCategoryVersions starting in the current release.

    Yields ``(subcategory, category, version)`` triples where the
    version has a NULL EndReleaseID and starts in the current
    release; the category join is INNER, as in the SQL.
    """
    for sc in snap.subcategories:
        category = _lookup(snap.categories_by_id, sc.category_id)
        if category is None:
            continue
        for scv in _scv_by_subcategory(snap).get(
            sc.subcategory_id, []
        ):
            if scv.end_release_id is None and rel.is_current(
                scv.start_release_id
            ):
                yield sc, category, scv


@rule(
    "6_22",
    legacy_code="6_22",
    family="glossary",
    severity=SEVERITY_WARNING,
    description=(
        "SubCategoryVersion created in this release is not used by "
        "any HeaderVersion or VariableVersion"
    ),
)
def rule_6_22(ctx: RuleContext) -> Iterator[Finding]:
    """A new SubCategoryVersion should be used somewhere.

    Open subcategory versions created in the current release that
    are referenced by no HeaderVersion and no VariableVersion should
    be examined for retention.
    """
    snap, rel = ctx.snapshot, ctx.release
    used = {
        hv.subcategory_vid
        for hv in snap.header_versions
        if hv.subcategory_vid is not None
    }
    used.update(
        vv.subcategory_vid
        for vv in snap.variable_versions
        if vv.subcategory_vid is not None
    )
    findings = []
    for sc, category, scv in _new_open_scvs(snap, rel):
        if scv.subcategory_vid not in used:
            findings.append(
                Finding(objects=_subcategory_refs(sc, category))
            )
    return _emit(findings)


def _supercategory_members(
    snap: ModelSnapshot,
) -> Dict[int, Set[int]]:
    """SuperCategory id -> constituent category ids."""
    members: Dict[int, Set[int]] = {}
    for scc in snap.supercategory_compositions:
        members.setdefault(scc.supercategory_id, set()).add(
            scc.category_id
        )
    return members


def _compatible_item_category(
    sc_category_id: Optional[int],
    item_category_id: Optional[int],
    members: Dict[int, Set[int]],
) -> bool:
    """Compatibility clause of rule 6_23.

    The item's category is compatible when it equals the
    subcategory's category, or — if the latter is a supercategory —
    when it is one of the supercategory's constituent categories.
    """
    if sc_category_id in members:
        return item_category_id == sc_category_id or (
            item_category_id in members[sc_category_id]
        )
    return item_category_id == sc_category_id


def _open_subcat_item_categories(
    snap: ModelSnapshot, subcategory_vid: int
) -> Iterator[Tuple[ItemCategoryRow, CategoryRow]]:
    """Open ItemCategory rows of a subcategory version's items."""
    for item_id in _sci_item_ids_by_scv(snap).get(
        subcategory_vid, []
    ):
        for ic in _ic_by_item(snap).get(item_id, []):
            if ic.end_release_id is not None:
                continue
            item_category = _lookup(
                snap.categories_by_id, ic.category_id
            )
            if item_category is not None:
                yield ic, item_category


@rule(
    "6_23",
    legacy_code="6_23",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Items of a subcategory do not currently belong to a "
        "category compatible with the subcategory's category"
    ),
)
def rule_6_23(ctx: RuleContext) -> Iterator[Finding]:
    """Subcategory items must belong to compatible categories.

    All items of a subcategory (open version starting in the current
    release) should currently belong either to the same category as
    the subcategory itself or, if that category is a supercategory,
    to one of its constituent categories.
    """
    snap, rel = ctx.snapshot, ctx.release
    members = _supercategory_members(snap)
    findings = []
    for sc, category, scv in _new_open_scvs(snap, rel):
        for ic, item_category in _open_subcat_item_categories(
            snap, scv.subcategory_vid
        ):
            if not _compatible_item_category(
                sc.category_id, ic.category_id, members
            ):
                findings.append(
                    Finding(
                        objects=(
                            *_subcategory_refs(sc, category),
                            ObjectRef(
                                kind="item",
                                id=ic.item_id,
                                code=ic.code,
                            ),
                            ObjectRef(
                                kind="category",
                                id=item_category.category_id,
                                code=item_category.code,
                            ),
                        )
                    )
                )
    return _emit(findings)


@rule(
    "6_32",
    legacy_code="6_32",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "SubCategory has the same name as another subcategory of "
        "the same category"
    ),
)
def rule_6_32(ctx: RuleContext) -> Iterator[Finding]:
    """A new subcategory's name must be unique in its category.

    Brand-new subcategories (whose only versions start in the
    current release) sharing their name with another subcategory of
    the same category are flagged.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for sc, category, _scv in _new_open_scvs(snap, rel):
        if any(
            other.start_release_id != rel.current_release_id
            for other in _scv_by_subcategory(snap).get(
                sc.subcategory_id, []
            )
        ):
            continue
        if sc.name is not None and _duplicate_subcategory_name(
            snap, sc
        ):
            findings.append(
                Finding(objects=_subcategory_refs(sc, category))
            )
    return _emit(findings)


def _duplicate_subcategory_name(
    snap: ModelSnapshot, sc: SubCategoryRow
) -> bool:
    """True when another subcategory of the category shares the name."""
    return any(
        other.subcategory_id != sc.subcategory_id
        and other.name == sc.name
        and other.category_id == sc.category_id
        for other in snap.subcategories
    )


@rule(
    "6_33",
    legacy_code="6_33",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "SubCategoryVersion created in this release does not contain "
        "any SubCategoryItem"
    ),
)
def rule_6_33(ctx: RuleContext) -> Iterator[Finding]:
    """A new SubCategoryVersion needs at least one item.

    Open subcategory versions starting in the current release
    without any corresponding SubCategoryItem row are flagged.
    """
    snap, rel = ctx.snapshot, ctx.release
    item_index = _sci_item_ids_by_scv(snap)
    findings = []
    for sc, category, scv in _new_open_scvs(snap, rel):
        if not item_index.get(scv.subcategory_vid):
            findings.append(
                Finding(objects=_subcategory_refs(sc, category))
            )
    return _emit(findings)


# ------------------------------------------------------------------
# Rule 6_24 — majority data type within a category
# ------------------------------------------------------------------


def _open_pc_stats(
    snap: ModelSnapshot,
) -> Dict[int, Tuple[int, Dict[int, int]]]:
    """Per category: (open assignment count, count per data type).

    The total counts every open PropertyCategory row (the SQL
    ``pc4`` subquery has no Property join); the per-datatype counts
    require the property row to exist (INNER JOIN ``p3``).
    """

    def build() -> Dict[int, Tuple[int, Dict[int, int]]]:
        totals: Dict[int, int] = {}
        counts: Dict[int, Dict[int, int]] = {}
        for pc in snap.property_categories:
            if (
                pc.end_release_id is not None
                or pc.category_id is None
            ):
                continue
            totals[pc.category_id] = totals.get(pc.category_id, 0) + 1
            prop = snap.properties_by_id.get(pc.property_id)
            if prop is not None and prop.data_type_id is not None:
                per_dt = counts.setdefault(pc.category_id, {})
                per_dt[prop.data_type_id] = (
                    per_dt.get(prop.data_type_id, 0) + 1
                )
        return {
            category_id: (total, counts.get(category_id, {}))
            for category_id, total in totals.items()
        }

    return snap.cache("glossary:open_pc_stats", build)


def _majority_other_datatypes(
    snap: ModelSnapshot,
    prop: PropertyRow,
    pc: PropertyCategoryRow,
    category: CategoryRow,
) -> List[int]:
    """Majority datatype candidates of rule 6_24 for one property.

    Data types (other than the property's own) used by another
    property assigned to the same category, whose share amongst the
    category's open assignments is at least 50%.
    """
    total, per_dt = _open_pc_stats(snap).get(
        category.category_id, (0, {})
    )
    result: Set[int] = set()
    for pc2 in snap.property_categories:
        if (
            pc2.category_id != category.category_id
            or pc2.property_id == pc.property_id
        ):
            continue
        other = snap.properties_by_id.get(pc2.property_id)
        if (
            other is None
            or other.data_type_id is None
            or other.data_type_id == prop.data_type_id
            or other.data_type_id not in snap.datatypes_by_id
        ):
            continue
        if per_dt.get(other.data_type_id, 0) >= 0.5 * total:
            result.add(other.data_type_id)
    return sorted(result)


@rule(
    "6_24",
    legacy_code="6_24",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Properties of a non-enumerated category (except _PR and "
        "_NA) belong to more than one data type"
    ),
)
def rule_6_24(ctx: RuleContext) -> Iterator[Finding]:
    """Properties of a plain category must share one data type.

    All properties in any non-enumerated category (except ``_PR``
    and ``_NA``) must belong to one common data type; properties
    deviating from a majority data type (>= 50% of the category's
    open assignments) are flagged, naming that majority data type.
    """
    snap = ctx.snapshot
    findings = []
    for prop, ic, pc, category in _prop_assignments(snap):
        if (
            category.is_enumerated is not False
            or category.code is None
            or category.code in ("_NA", "_PR")
            or pc.end_release_id is not None
            or prop.data_type_id not in snap.datatypes_by_id
        ):
            continue
        for datatype_id in _majority_other_datatypes(
            snap, prop, pc, category
        ):
            majority = snap.datatypes_by_id[datatype_id]
            findings.append(
                Finding(
                    message=(
                        "Properties from non-enumerated Category "
                        "(except _PR and _NA) belong to more than "
                        "one data type; majority data type is: "
                        f"{majority.name}"
                    ),
                    objects=(
                        *_prop_refs(prop, ic, category),
                        ObjectRef(
                            kind="datatype",
                            id=majority.data_type_id,
                            code=majority.code,
                            name=majority.name,
                        ),
                    ),
                )
            )
    return _emit(findings)


# ------------------------------------------------------------------
# Rules 6_25 / 6_26 / 6_35 — essentially unique names
# ------------------------------------------------------------------


def _new_item_assignments(
    snap: ModelSnapshot, rel: ReleaseContext, is_property: bool
) -> Iterator[Tuple[ItemRow, ItemCategoryRow]]:
    """Open current-release ItemCategory rows of brand-new items.

    Yields ``(item, assignment)`` pairs where the assignment starts
    in the current release with a NULL EndReleaseID and the item has
    no other assignment from a different release (SQL ``NOT EXISTS
    ... StartReleaseID <> @CurrentRelease``, replicated literally
    against the current release id).
    """
    for ic in snap.item_categories:
        item = snap.items_by_id.get(ic.item_id)
        if item is None or item.is_property is not is_property:
            continue
        if not (
            rel.is_current(ic.start_release_id)
            and ic.end_release_id is None
        ):
            continue
        if any(
            other.start_release_id != rel.current_release_id
            for other in _ic_by_item(snap).get(ic.item_id, [])
        ):
            continue
        yield item, ic


def _property_name_clash(
    snap: ModelSnapshot,
    source_item_id: int,
    normalised: str,
    category_id: Optional[int],
    open_pred: Callable[[Optional[int]], bool],
) -> bool:
    """EXISTS predicate shared by rules 6_25 and 6_35.

    True when another property item, assigned through a
    PropertyCategory row accepted by ``open_pred`` (and matching
    ``category_id`` when given), has the same essential name.
    """
    for pc2 in snap.property_categories:
        if not open_pred(pc2.end_release_id):
            continue
        if (
            category_id is not None
            and pc2.category_id != category_id
        ):
            continue
        other = snap.items_by_id.get(pc2.property_id)
        if (
            other is None
            or other.is_property is not True
            or other.item_id == source_item_id
        ):
            continue
        if (
            other.name is not None
            and _essential_name(other.name) == normalised
        ):
            return True
    return False


@rule(
    "6_25",
    legacy_code="6_25",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Property name is not essentially unique within its category"
    ),
)
def rule_6_25(ctx: RuleContext) -> Iterator[Finding]:
    """A property name has to be unique within its own category.

    For brand-new property items, the name — compared after removing
    ``' '``, ``'.'``, ``'('``, ``')'`` and ``'_'`` — must not match
    the name of another property with an open assignment to the same
    category.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for item, ic in _new_item_assignments(snap, rel, True):
        prop = snap.properties_by_id.get(item.item_id)
        if prop is None or item.name is None:
            continue
        normalised = _essential_name(item.name)
        for pc in _pc_by_property(snap).get(item.item_id, []):
            category = _lookup(snap.categories_by_id, pc.category_id)
            if category is None:
                continue
            if _property_name_clash(
                snap,
                item.item_id,
                normalised,
                pc.category_id,
                lambda end: end is None,
            ):
                findings.append(
                    Finding(
                        message=(
                            "Property Name is not essentially "
                            "Unique within its Category: "
                            f'"{item.name.strip()}"'
                        ),
                        objects=_prop_refs(prop, ic, category),
                    )
                )
    return _emit(findings)


@rule(
    "6_26",
    legacy_code="6_26",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Item name is not essentially unique within its category"
    ),
)
def rule_6_26(ctx: RuleContext) -> Iterator[Finding]:
    """An item name has to be unique within its category.

    For brand-new non-property items, the essential name must not
    match the name of any other item with an open assignment to the
    same category.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for item, ic in _new_item_assignments(snap, rel, False):
        category = _lookup(snap.categories_by_id, ic.category_id)
        if category is None or item.name is None:
            continue
        normalised = _essential_name(item.name)
        if _item_name_clash(
            snap, item.item_id, normalised, ic.category_id
        ):
            findings.append(
                Finding(
                    message=(
                        "Item Name is not essentially Unique within "
                        f'its Category itself: "{item.name.strip()}"'
                    ),
                    objects=_item_refs(ic, category),
                )
            )
    return _emit(findings)


def _item_name_clash(
    snap: ModelSnapshot,
    source_item_id: int,
    normalised: str,
    category_id: Optional[int],
) -> bool:
    """EXISTS predicate of rule 6_26.

    True when another item with an open assignment to the same
    category has the same essential name.
    """
    for ic2 in snap.item_categories:
        if (
            ic2.end_release_id is not None
            or ic2.category_id != category_id
        ):
            continue
        other = snap.items_by_id.get(ic2.item_id)
        if other is None or other.item_id == source_item_id:
            continue
        if (
            other.name is not None
            and _essential_name(other.name) == normalised
        ):
            return True
    return False


@rule(
    "6_35",
    legacy_code="6_35",
    family="glossary",
    severity=SEVERITY_WARNING,
    description=(
        "Property name is not essentially unique across all "
        "categories"
    ),
)
def rule_6_35(ctx: RuleContext) -> Iterator[Finding]:
    """A property name has to be unique across all categories.

    Like rule 6_25 but the clashing property may belong to any
    category and its assignment may also be draft-closed (SQL
    ``EndReleaseID IS NULL OR EndReleaseID = 9999``).
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for item, ic in _new_item_assignments(snap, rel, True):
        prop = snap.properties_by_id.get(item.item_id)
        if prop is None or item.name is None:
            continue
        normalised = _essential_name(item.name)
        for pc in _pc_by_property(snap).get(item.item_id, []):
            category = _lookup(snap.categories_by_id, pc.category_id)
            if category is None:
                continue
            if _property_name_clash(
                snap, item.item_id, normalised, None, rel.is_open
            ):
                findings.append(
                    Finding(
                        message=(
                            "Property Name is not essentially "
                            "Unique across all Categories: "
                            f'"{item.name.strip()}"'
                        ),
                        objects=_prop_refs(prop, ic, category),
                    )
                )
    return _emit(findings)


# ------------------------------------------------------------------
# Rule 6_27 — metric properties need a period type
# ------------------------------------------------------------------


@rule(
    "6_27",
    legacy_code="6_27",
    family="glossary",
    severity=SEVERITY_ERROR,
    description="Property is metric but has no stock/flow period type",
)
def rule_6_27(ctx: RuleContext) -> Iterator[Finding]:
    """A metric property must have a stock or flow period type.

    Metric properties with a PropertyCategory starting in the
    current release (open, with an open ItemCategory and an existing
    data type) whose period type is NULL or neither ``stock`` nor
    ``flow`` are flagged.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for prop, ic, pc, category in _prop_assignments(snap):
        if (
            rel.is_current(pc.start_release_id)
            and pc.end_release_id is None
            and ic.end_release_id is None
            and prop.is_metric is True
            and prop.data_type_id in snap.datatypes_by_id
            and (
                prop.period_type is None
                or prop.period_type not in ("stock", "flow")
            )
        ):
            findings.append(
                Finding(objects=_prop_refs(prop, ic, category))
            )
    return _emit(findings)


# ------------------------------------------------------------------
# Rule 6_28 — signs on void or excluded cells
# ------------------------------------------------------------------


def _in_current_module(
    snap: ModelSnapshot, rel: ReleaseContext, table_vid: int
) -> bool:
    """True when the table version is in a current ModuleVersion."""
    for mvc in snap.mvc_by_table_vid().get(table_vid, []):
        mv = snap.module_versions_by_vid.get(mvc.module_vid)
        if mv is not None and rel.is_current(mv.start_release_id):
            return True
    return False


@rule(
    "6_28",
    legacy_code="6_28",
    family="glossary",
    severity=SEVERITY_ERROR,
    description="Sign set on a cell that is void or excluded",
)
def rule_6_28(ctx: RuleContext) -> Iterator[Finding]:
    """No sign is allowed on a void or excluded cell.

    Cells with a non-NULL sign that are void or excluded are flagged
    when their table version belongs to a module version starting in
    the current release.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for tvc in snap.table_version_cells:
        if tvc.sign is None:
            continue
        if not (tvc.is_void is True or tvc.is_excluded is True):
            continue
        tv = snap.table_versions_by_vid.get(tvc.table_vid)
        if tv is None or not _in_current_module(
            snap, rel, tvc.table_vid
        ):
            continue
        findings.append(Finding(objects=_cell_refs(tvc, tv)))
    return _emit(findings)


# ------------------------------------------------------------------
# Rules 6_29 / 6_30 — duplicate subcategory / category codes
# ------------------------------------------------------------------


@rule(
    "6_29",
    legacy_code="6_29",
    family="glossary",
    severity=SEVERITY_ERROR,
    description="Duplicate SubCategory code within the same category",
)
def rule_6_29(ctx: RuleContext) -> Iterator[Finding]:
    """A subcategory code has to be unique within its category.

    Subcategories sharing their code with another subcategory of the
    same category are flagged when they have a version starting in
    the current release.
    """
    snap, rel = ctx.snapshot, ctx.release
    owners: Dict[Tuple[str, int], Set[int]] = {}
    for sc in snap.subcategories:
        if sc.code is not None and sc.category_id is not None:
            owners.setdefault((sc.code, sc.category_id), set()).add(
                sc.subcategory_id
            )
    findings = []
    for sc in snap.subcategories:
        category = _lookup(snap.categories_by_id, sc.category_id)
        if category is None or sc.code is None:
            continue
        if len(owners[(sc.code, category.category_id)]) < 2:
            continue
        if any(
            rel.is_current(scv.start_release_id)
            for scv in _scv_by_subcategory(snap).get(
                sc.subcategory_id, []
            )
        ):
            findings.append(
                Finding(objects=_subcategory_refs(sc, category))
            )
    return _emit(findings)


@rule(
    "6_30",
    legacy_code="6_30",
    family="glossary",
    severity=SEVERITY_ERROR,
    description="Duplicate category code",
)
def rule_6_30(ctx: RuleContext) -> Iterator[Finding]:
    """A category code has to be unique.

    Categories sharing their code with any other category are
    flagged; categories with a NULL code are excluded (SQL equality
    never matches NULL).
    """
    snap = ctx.snapshot
    owners: Dict[str, Set[int]] = {}
    for category in snap.categories:
        if category.code is not None:
            owners.setdefault(category.code, set()).add(
                category.category_id
            )
    findings = [
        Finding(objects=_category_ref(category))
        for category in snap.categories
        if category.code is not None
        and len(owners[category.code]) > 1
    ]
    return _emit(findings)


# ------------------------------------------------------------------
# Rule 6_31 — item code shape
# ------------------------------------------------------------------


def _bad_item_code(code: str) -> bool:
    """Predicate of rule 6_31 on a non-NULL item code.

    True when the code does not start with a letter (or ``_``) or
    contains a space anywhere (the SQL checks the raw, untrimmed
    code here). An empty code counts as not starting with a letter,
    as in SQL where ``left('', 1)`` is ``''``.
    """
    first = code[:1]
    starts_badly = not ("A" <= first.upper() <= "Z") and first != "_"
    return starts_badly or " " in code


@rule(
    "6_31",
    legacy_code="6_31",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Item code does not start with a letter or contains spaces"
    ),
)
def rule_6_31(ctx: RuleContext) -> Iterator[Finding]:
    """Item codes must start with a letter and contain no spaces.

    Open item assignments of enumerated categories starting in the
    current release are checked.

    Note:
        The SQL leaves the ItemID result column NULL; the item id is
        nevertheless carried on the ObjectRef here to identify the
        offending assignment.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for ic in snap.item_categories:
        category = _lookup(snap.categories_by_id, ic.category_id)
        if category is None or category.is_enumerated is not True:
            continue
        if ic.end_release_id is not None or not rel.is_current(
            ic.start_release_id
        ):
            continue
        if ic.code is not None and _bad_item_code(ic.code):
            findings.append(Finding(objects=_item_refs(ic, category)))
    return _emit(findings)


# ------------------------------------------------------------------
# Rules 6_34 / 6_36 — identical subcategory item sets
# ------------------------------------------------------------------


def _same_subcategory_items(
    snap: ModelSnapshot, vid_a: int, vid_b: int
) -> bool:
    """Item-set equality as computed by the SQL count comparison.

    The SQL compares ``count(items of a)`` with the number of
    matching (a, b) item pairs and with ``count(items of b)``; this
    is replicated literally, counting join pairs.
    """
    items_a = _sci_item_ids_by_scv(snap).get(vid_a, [])
    items_b = _sci_item_ids_by_scv(snap).get(vid_b, [])
    pairs = sum(items_b.count(item_id) for item_id in items_a)
    return len(items_a) == pairs and len(items_a) == len(items_b)


@rule(
    "6_34",
    legacy_code="6_34",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "SubCategory updated in the current release contains exactly "
        "the same items as another existing active subcategory"
    ),
)
def rule_6_34(ctx: RuleContext) -> Iterator[Finding]:
    """No two active subcategories may hold identical item sets.

    A subcategory version updated in the current release (active per
    the SQL start/end sentinel pattern) must not contain exactly the
    same items as an earlier active subcategory version of another
    subcategory in the same category. The SQL joins the Release
    table for both versions, so both start releases must exist.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for sc in snap.subcategories:
        category = _lookup(snap.categories_by_id, sc.category_id)
        if category is None:
            continue
        for scv in _scv_by_subcategory(snap).get(
            sc.subcategory_id, []
        ):
            if not (
                _active_assignment(
                    rel, scv.start_release_id, scv.end_release_id
                )
                and rel.is_current(scv.start_release_id)
            ):
                continue
            release = _lookup(
                snap.releases_by_id, scv.start_release_id
            )
            if release is None:
                continue
            findings.extend(
                _r634_partners(snap, rel, sc, category, scv, release)
            )
    return _emit(findings)


def _r634_partners(
    snap: ModelSnapshot,
    rel: ReleaseContext,
    sc: SubCategoryRow,
    category: CategoryRow,
    scv: SubCategoryVersionRow,
    release: ReleaseRow,
) -> List[Finding]:
    """Rule 6_34 findings for one updated subcategory version."""
    findings = []
    for other_sc in snap.subcategories:
        if (
            other_sc.category_id != sc.category_id
            or other_sc.subcategory_id == sc.subcategory_id
        ):
            continue
        for other in _scv_by_subcategory(snap).get(
            other_sc.subcategory_id, []
        ):
            if (
                other.subcategory_vid >= scv.subcategory_vid
                or not _active_assignment(
                    rel, other.start_release_id, other.end_release_id
                )
            ):
                continue
            other_release = _lookup(
                snap.releases_by_id, other.start_release_id
            )
            if other_release is None or not _same_subcategory_items(
                snap, scv.subcategory_vid, other.subcategory_vid
            ):
                continue
            findings.append(
                Finding(
                    message=(
                        f"SubCategory: {_short_code(sc.code)} "
                        f"updated in release: {release.code} "
                        "contains exactly the same Items as the "
                        "existing active SubCategory: "
                        f"{_short_code(other_sc.code)} updated in "
                        f"release: {other_release.code}"
                    ),
                    objects=(
                        ObjectRef(
                            kind="subcategory",
                            id=sc.subcategory_id,
                            code=sc.code,
                        ),
                        ObjectRef(
                            kind="subcategory",
                            id=other_sc.subcategory_id,
                            code=other_sc.code,
                        ),
                        ObjectRef(
                            kind="category",
                            id=category.category_id,
                            code=category.code,
                        ),
                    ),
                )
            )
    return findings


@rule(
    "6_36",
    legacy_code="6_36",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "SubCategory updated in the current release contains exactly "
        "the same items as its previous version"
    ),
)
def rule_6_36(ctx: RuleContext) -> Iterator[Finding]:
    """An updated subcategory version must actually change.

    A subcategory version created in the current release must not
    contain exactly the same items as the previous version of the
    same subcategory that was closed in the current release. Both
    versions' start releases must exist (INNER JOIN Release).
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for sc, category, scv in _new_open_scvs(snap, rel):
        release = _lookup(snap.releases_by_id, scv.start_release_id)
        if release is None:
            continue
        for other in _scv_by_subcategory(snap).get(
            sc.subcategory_id, []
        ):
            if (
                other.subcategory_vid >= scv.subcategory_vid
                or not rel.ends_in_current(other.end_release_id)
                or other.start_release_id not in snap.releases_by_id
                or not _same_subcategory_items(
                    snap, scv.subcategory_vid, other.subcategory_vid
                )
            ):
                continue
            findings.append(
                Finding(
                    message=(
                        f"SubCategory: {_short_code(sc.code)} "
                        f"updated in release: {release.code} "
                        "contains exactly the same SubCategoryItems "
                        "as the previous SubCategoryVersion"
                    ),
                    objects=_subcategory_refs(sc, category),
                )
            )
    return _emit(findings)


# ------------------------------------------------------------------
# Rule 6_18 — enumerated properties need subcategory lookups
# ------------------------------------------------------------------


def _enumerated_prop_categories(
    snap: ModelSnapshot, property_id: int
) -> Iterator[Tuple[ItemCategoryRow, CategoryRow]]:
    """Open enumerated-category assignments of one property.

    Yields (item assignment, category) pairs where the property has
    an open PropertyCategory to an enumerated category and an open
    ItemCategory row.
    """
    for pc in _pc_by_property(snap).get(property_id, []):
        if pc.end_release_id is not None:
            continue
        category = _lookup(snap.categories_by_id, pc.category_id)
        if category is None or category.is_enumerated is not True:
            continue
        for ic in _ic_by_item(snap).get(property_id, []):
            if ic.end_release_id is None:
                yield ic, category


@rule(
    "6_18",
    legacy_code="6_18",
    family="glossary",
    severity=SEVERITY_ERROR,
    description=(
        "Property belonging to an enumerated category but not "
        "associated with any subcategory lookup"
    ),
)
def rule_6_18(ctx: RuleContext) -> Iterator[Finding]:
    """Enumerated header properties need a subcategory lookup.

    On non-abstract, open table versions starting in the current
    release, header versions carrying a main property of an
    enumerated category (open assignments) without a SubCategoryVID
    are flagged.
    """
    snap, rel = ctx.snapshot, ctx.release
    findings = []
    for hv, _header, tv in _header_usages(snap):
        table = _lookup(snap.tables_by_id, tv.table_id)
        if table is None or table.is_abstract is not False:
            continue
        if tv.end_release_id is not None or not rel.is_current(
            tv.start_release_id
        ):
            continue
        if hv.subcategory_vid is not None or hv.property_id is None:
            continue
        if hv.property_id not in snap.properties_by_id:
            continue
        for ic, category in _enumerated_prop_categories(
            snap, hv.property_id
        ):
            findings.append(
                Finding(
                    objects=(
                        *_header_refs(hv, tv),
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
                )
            )
    return _emit(findings)
