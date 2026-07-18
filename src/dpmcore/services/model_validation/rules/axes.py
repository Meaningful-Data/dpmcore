"""Family 2 modelling rules — table axis structure.

Port of the ``2_x`` INSERT blocks of ``check_modelling_rules_tidy``:
open/closed axis key-header requirements (2_1 .. 2_9) and main-property
axis assignment rules (2_10 .. 2_13). Every block evaluates the open
``TableVersion`` rows that start in the release under validation and
appear in at least one ``ModuleVersionComposition`` — that shared
join/filter is factored into :func:`_current_open_tvs`.
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
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
    ItemCategoryRow,
    ModelSnapshot,
    PropertyCategoryRow,
    TableRow,
    TableVersionRow,
)
from dpmcore.services.model_validation.types import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    ObjectRef,
)

_FAMILY = "axes"

_FlagGetter = Callable[[TableRow], Optional[bool]]


def _is_false(flag: Optional[bool]) -> bool:
    """Mirror SQL ``column = 0``: NULL rows never match."""
    return flag is not None and not flag


def _tv_ref(tv: TableVersionRow) -> ObjectRef:
    """Reference to a table version."""
    return ObjectRef(kind="table_version", id=tv.table_vid, code=tv.code)


def _emit(findings: Dict[Tuple[Any, ...], Finding]) -> Iterator[Finding]:
    """Yield findings ordered by their deduplication key."""
    for key in sorted(findings):
        yield findings[key]


def _current_open_tvs(
    ctx: RuleContext,
) -> List[Tuple[TableVersionRow, TableRow]]:
    """Open TableVersions starting in the current release, in a module.

    Mirrors the join/filter shared by every ``2_x`` block:
    ``TableVersion JOIN Table JOIN ModuleVersionComposition JOIN
    ModuleVersion WHERE tv.EndReleaseID IS NULL AND
    tv.StartReleaseID = @CurrentRelease``.
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
            memberships = in_module.get(tv.table_vid, [])
            if not any(
                mvc.module_vid in snap.module_versions_by_vid
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

    return snap.cache("axes:current_open_tvs", build)


def _headers_of(
    snap: ModelSnapshot, tv: TableVersionRow, table: TableRow
) -> Iterator[HeaderRow]:
    """Headers reachable from a TableVersion via TableVersionHeader.

    Mirrors ``Header h JOIN TableVersionHeader tvh ON
    tvh.HeaderID = h.HeaderID WHERE tvh.TableVID = tv.TableVID AND
    h.TableID = t.TableID``.
    """
    for tvh in snap.tvh_by_table_vid().get(tv.table_vid, []):
        header = snap.headers_by_id.get(tvh.header_id)
        if header is not None and header.table_id == table.table_id:
            yield header


def _has_axis_header(
    snap: ModelSnapshot,
    tv: TableVersionRow,
    table: TableRow,
    direction: str,
    key: bool,
) -> bool:
    """True when the table version has a header on ``direction``.

    ``key`` selects between ``h.isKey = 1`` and ``h.isKey = 0``
    (NULL ``isKey`` matches neither, as in SQL).
    """
    for header in _headers_of(snap, tv, table):
        key_ok = (
            bool(header.is_key) if key else _is_false(header.is_key)
        )
        if key_ok and header.direction == direction:
            return True
    return False


def _axis_findings(
    ctx: RuleContext,
    flag: _FlagGetter,
    flag_true: bool,
    direction: str,
    key: bool,
    fire_on_exists: bool,
) -> Iterator[Finding]:
    """Shared body of rules 2_1 .. 2_5 and 2_7 .. 2_9.

    Args:
        ctx: Evaluation context.
        flag: Getter for the open-axis flag of the ``Table`` row.
        flag_true: Whether the flag must be 1 (else it must be 0).
        direction: Header direction the subquery looks for.
        key: Whether the subquery looks for key headers.
        fire_on_exists: True translates the SQL ``EXISTS`` variants,
            False the ``NOT EXISTS`` ones.
    """
    snap = ctx.snapshot
    for tv, table in _current_open_tvs(ctx):
        if not _is_false(table.is_abstract):
            continue
        value = flag(table)
        flag_ok = bool(value) if flag_true else _is_false(value)
        if not flag_ok:
            continue
        exists = _has_axis_header(snap, tv, table, direction, key)
        if exists == fire_on_exists:
            yield Finding(objects=(_tv_ref(tv),))


def _axis_property_split(
    ctx: RuleContext, tv: TableVersionRow, table: TableRow
) -> Tuple[Set[str], Set[str]]:
    """Split header directions by main-property presence.

    Considers non-key headers whose TableVersionHeader row is not
    abstract, joined to their open HeaderVersion via ``HeaderVID``
    (the join used by 2_10 .. 2_12). Returns the directions carrying
    at least one header with a main property and the directions
    carrying at least one header without. NULL directions are ignored
    (SQL ``COUNT(DISTINCT h.Direction)`` skips NULL and
    ``h2.Direction = h.Direction`` never matches NULL).
    """
    snap = ctx.snapshot
    with_prop: Set[str] = set()
    without_prop: Set[str] = set()
    for tvh in snap.tvh_by_table_vid().get(tv.table_vid, []):
        if not _is_false(tvh.is_abstract):
            continue
        if tvh.header_vid is None:
            continue
        hv = snap.header_versions_by_vid.get(tvh.header_vid)
        if hv is None or hv.end_release_id is not None:
            continue
        header = (
            snap.headers_by_id.get(hv.header_id)
            if hv.header_id is not None
            else None
        )
        if header is None or header.table_id != table.table_id:
            continue
        if not _is_false(header.is_key):
            continue
        if header.direction is None:
            continue
        if hv.property_id is not None:
            with_prop.add(header.direction)
        else:
            without_prop.add(header.direction)
    return with_prop, without_prop


def _ic_by_item(
    snap: ModelSnapshot,
) -> Dict[int, List[ItemCategoryRow]]:
    """``ItemCategory`` rows grouped by ``item_id``."""

    def build() -> Dict[int, List[ItemCategoryRow]]:
        grouped: Dict[int, List[ItemCategoryRow]] = {}
        for ic in snap.item_categories:
            grouped.setdefault(ic.item_id, []).append(ic)
        return grouped

    return snap.cache("axes:ic_by_item", build)


def _pc_by_property(
    snap: ModelSnapshot,
) -> Dict[int, List[PropertyCategoryRow]]:
    """``PropertyCategory`` rows grouped by ``property_id``."""

    def build() -> Dict[int, List[PropertyCategoryRow]]:
        grouped: Dict[int, List[PropertyCategoryRow]] = {}
        for pc in snap.property_categories:
            grouped.setdefault(pc.property_id, []).append(pc)
        return grouped

    return snap.cache("axes:pc_by_property", build)


@rule(
    "2_1",
    legacy_code="2_1",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Open Row Table without Key Columns",
)
def rule_2_1(ctx: RuleContext) -> Iterator[Finding]:
    """Open-row tables must have at least one key header in X."""
    return _axis_findings(
        ctx, lambda t: t.has_open_rows, True, "X", True, False
    )


@rule(
    "2_2",
    legacy_code="2_2",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Open Column Table without Key Rows",
)
def rule_2_2(ctx: RuleContext) -> Iterator[Finding]:
    """Open-column tables must have at least one key header in Y."""
    return _axis_findings(
        ctx, lambda t: t.has_open_columns, True, "Y", True, False
    )


@rule(
    "2_3",
    legacy_code="2_3",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Open Sheet Table without Key Sheets",
)
def rule_2_3(ctx: RuleContext) -> Iterator[Finding]:
    """Open-sheet tables must have at least one key header in Z."""
    return _axis_findings(
        ctx, lambda t: t.has_open_sheets, True, "Z", True, False
    )


@rule(
    "2_4",
    legacy_code="2_4",
    family=_FAMILY,
    severity=SEVERITY_WARNING,
    description="Open Row Table without non-Key Columns",
)
def rule_2_4(ctx: RuleContext) -> Iterator[Finding]:
    """Open-row tables should have at least one non-key X header."""
    return _axis_findings(
        ctx, lambda t: t.has_open_rows, True, "X", False, False
    )


@rule(
    "2_5",
    legacy_code="2_5",
    family=_FAMILY,
    severity=SEVERITY_WARNING,
    description="Open Column Table without non-Key Rows",
)
def rule_2_5(ctx: RuleContext) -> Iterator[Finding]:
    """Open-column tables should have at least one non-key Y header."""
    return _axis_findings(
        ctx, lambda t: t.has_open_columns, True, "Y", False, False
    )


@rule(
    "2_6",
    legacy_code="2_6",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Closed Row & Column Table is missing Rows or Columns",
)
def rule_2_6(ctx: RuleContext) -> Iterator[Finding]:
    """Closed row & column tables need non-key X and Y headers."""
    snap = ctx.snapshot
    for tv, table in _current_open_tvs(ctx):
        if not _is_false(table.is_abstract):
            continue
        if not _is_false(table.has_open_columns):
            continue
        if not _is_false(table.has_open_rows):
            continue
        has_y = _has_axis_header(snap, tv, table, "Y", False)
        has_x = _has_axis_header(snap, tv, table, "X", False)
        if not (has_y and has_x):
            yield Finding(objects=(_tv_ref(tv),))


@rule(
    "2_7",
    legacy_code="2_7",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Closed Row Table with Key Columns",
)
def rule_2_7(ctx: RuleContext) -> Iterator[Finding]:
    """Closed-row tables must not have key headers in X."""
    return _axis_findings(
        ctx, lambda t: t.has_open_rows, False, "X", True, True
    )


@rule(
    "2_8",
    legacy_code="2_8",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Closed Column Table with Key Rows",
)
def rule_2_8(ctx: RuleContext) -> Iterator[Finding]:
    """Closed-column tables must not have key headers in Y."""
    return _axis_findings(
        ctx, lambda t: t.has_open_columns, False, "Y", True, True
    )


@rule(
    "2_9",
    legacy_code="2_9",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Closed Sheet Table with Key Sheets",
)
def rule_2_9(ctx: RuleContext) -> Iterator[Finding]:
    """Closed-sheet tables must not have key headers in Z."""
    return _axis_findings(
        ctx, lambda t: t.has_open_sheets, False, "Z", True, True
    )


@rule(
    "2_10",
    legacy_code="2_10",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="Main properties assigned to more than one axis",
)
def rule_2_10(ctx: RuleContext) -> Iterator[Finding]:
    """Main properties must be accommodated in a single axis.

    Counts the distinct directions of non-abstract, non-key headers
    with an open HeaderVersion carrying a main property, plus one when
    the TableVersion itself carries a whole-table main property.
    """
    for tv, table in _current_open_tvs(ctx):
        if not _is_false(table.is_abstract):
            continue
        with_prop, _ = _axis_property_split(ctx, tv, table)
        axes_count = len(with_prop)
        if tv.property_id is not None:
            axes_count += 1
        if axes_count > 1:
            yield Finding(objects=(_tv_ref(tv),))


@rule(
    "2_11",
    legacy_code="2_11",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description="No main property assigned to any axis",
)
def rule_2_11(ctx: RuleContext) -> Iterator[Finding]:
    """There must be at least one axis with main properties assigned.

    Same count as rule 2_10 but firing when it is zero.
    """
    for tv, table in _current_open_tvs(ctx):
        if not _is_false(table.is_abstract):
            continue
        with_prop, _ = _axis_property_split(ctx, tv, table)
        axes_count = len(with_prop)
        if tv.property_id is not None:
            axes_count += 1
        if axes_count == 0:
            yield Finding(objects=(_tv_ref(tv),))


@rule(
    "2_12",
    legacy_code="2_12",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Not all non-abstract and non-key headers of the axis to "
        "which main properties are assigned have a main property"
    ),
)
def rule_2_12(ctx: RuleContext) -> Iterator[Finding]:
    """The main-property axis must be fully covered.

    Fires once per direction where a non-key, non-abstract header
    carries a main property while another such header on the same
    direction carries none.
    """
    for tv, table in _current_open_tvs(ctx):
        if not _is_false(table.is_abstract):
            continue
        with_prop, without_prop = _axis_property_split(ctx, tv, table)
        for direction in sorted(with_prop & without_prop):
            yield Finding(
                objects=(
                    _tv_ref(tv),
                    ObjectRef(kind="axis", id=direction),
                )
            )


@rule(
    "2_13",
    legacy_code="2_13",
    family=_FAMILY,
    severity=SEVERITY_ERROR,
    description=(
        "Main Property assigned to a whole Table that is not a Metric"
    ),
)
def rule_2_13(ctx: RuleContext) -> Iterator[Finding]:
    """A whole-table main property must be a metric.

    Mirrors the SQL joins: the property needs at least one
    ``ItemCategory`` row (no lifecycle filter) and an open
    ``PropertyCategory`` row whose category exists; ``IsMetric = 0``
    excludes NULL flags.
    """
    snap = ctx.snapshot
    findings: Dict[Tuple[Any, ...], Finding] = {}
    for tv, _table in _current_open_tvs(ctx):
        if tv.property_id is None:
            continue
        prop = snap.properties_by_id.get(tv.property_id)
        if prop is None or not _is_false(prop.is_metric):
            continue
        _collect_2_13(snap, tv, tv.property_id, findings)
    yield from _emit(findings)


def _collect_2_13(
    snap: ModelSnapshot,
    tv: TableVersionRow,
    property_id: int,
    findings: Dict[Tuple[Any, ...], Finding],
) -> None:
    """Emit the 2_13 rows for one TableVersion into ``findings``."""
    for ic in _ic_by_item(snap).get(property_id, []):
        for pc in _pc_by_property(snap).get(property_id, []):
            if pc.end_release_id is not None:
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
                ic.code or "",
                category.category_id,
            )
            if key in findings:
                continue
            findings[key] = Finding(
                objects=(
                    _tv_ref(tv),
                    ObjectRef(
                        kind="property",
                        id=tv.property_id,
                        code=ic.code,
                    ),
                    ObjectRef(
                        kind="category",
                        id=category.category_id,
                        code=category.code,
                    ),
                )
            )
