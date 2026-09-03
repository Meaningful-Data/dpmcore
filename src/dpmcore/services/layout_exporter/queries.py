"""Batch query functions for the table layout exporter.

All functions take a SQLAlchemy session as first argument and return
raw ORM objects or lightweight tuples. Processing logic lives in
processing.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.orm import Session

from dpmcore.orm.query_utils import chunked_in
from dpmcore.orm.release_sort_order import (
    compute_sort_order,
    load_release_sort_orders,
)
from dpmcore.services.layout_exporter.models import (
    DimensionMember,
    Enumeration,
    EnumValue,
    ReleaseWindow,
)

# Sort-order bounds for an open-ended release window. ``_LATEST`` is the
# sentinel an undated (working) release carries, so a window ending at
# one is as open as a window with no end at all.
_EARLIEST = -1
_LATEST = compute_sort_order(None, None)

if TYPE_CHECKING:
    pass


def load_module_table_versions(
    session: Session,
    module_code: str,
    release_code: Optional[str] = None,
) -> list[Any]:
    """Load all TableVersions for a given module version code.

    The ``release_code`` filter is a *range* query (any module version
    whose validity window covers the resolved release), consistent
    with the rest of the codebase. When ``release_code`` is omitted,
    only currently-active module versions (``end_release_id IS NULL``)
    are considered.

    Args:
        session: SQLAlchemy session.
        module_code: Module version code (e.g. ``"FINREP9"``).
        release_code: Optional release code (e.g. ``"4.2"``). Resolved
            via :class:`Release.code`; raises ``ValueError`` if the
            code does not match any release.

    Returns:
        TableVersion ORM objects ordered by module composition order.
    """
    from dpmcore.dpm_xl.utils.filters import (
        filter_by_release,
        resolve_release_id,
    )
    from dpmcore.orm.packaging import ModuleVersion, ModuleVersionComposition
    from dpmcore.orm.rendering import TableVersion

    release_id = resolve_release_id(session, release_code=release_code)

    q = (
        session.query(TableVersion)
        .join(
            ModuleVersionComposition,
            ModuleVersionComposition.table_vid == TableVersion.table_vid,
        )
        .join(
            ModuleVersion,
            ModuleVersion.module_vid == ModuleVersionComposition.module_vid,
        )
        .filter(ModuleVersion.code == module_code)
    )
    q = filter_by_release(
        q,
        start_col=ModuleVersion.start_release_id,
        end_col=ModuleVersion.end_release_id,
        release_id=release_id,
        active_only_fallback=True,
    )

    q = q.order_by(ModuleVersionComposition.order)
    return q.all()


def load_module_version(
    session: Session,
    module_code: str,
    release_code: Optional[str] = None,
) -> Optional[Any]:
    """Load the ModuleVersion whose release window the export uses.

    Selected with the same range query as
    :func:`load_module_table_versions`. Should more than one module
    version match, the latest-starting one wins, so the window is the
    most recent context the tables were reported in.

    Args:
        session: SQLAlchemy session.
        module_code: Module version code (e.g. ``"FINREP9"``).
        release_code: Optional release code.
    """
    from dpmcore.dpm_xl.utils.filters import (
        filter_by_release,
        resolve_release_id,
    )
    from dpmcore.orm.packaging import ModuleVersion

    release_id = resolve_release_id(session, release_code=release_code)

    q = session.query(ModuleVersion).filter(ModuleVersion.code == module_code)
    q = filter_by_release(
        q,
        start_col=ModuleVersion.start_release_id,
        end_col=ModuleVersion.end_release_id,
        release_id=release_id,
        active_only_fallback=True,
    )

    versions = q.all()
    if not versions:
        return None
    sort_orders = load_release_sort_orders(session)
    return max(
        versions,
        key=lambda mv: (
            sort_orders.get(mv.start_release_id, _EARLIEST),
            mv.module_vid,
        ),
    )


def load_table_version(
    session: Session,
    table_code: str,
    release_code: Optional[str] = None,
) -> Optional[Any]:
    """Load a single TableVersion by code.

    The ``release_code`` filter is a *range* query: any TableVersion
    whose validity window covers the resolved release matches. When
    omitted, only currently-active table versions are considered.

    Args:
        session: SQLAlchemy session.
        table_code: Table code (e.g. ``"F_01.01"``).
        release_code: Optional release code; raises ``ValueError`` if
            the code does not match any release.
    """
    from dpmcore.dpm_xl.utils.filters import (
        filter_by_release,
        resolve_release_id,
    )
    from dpmcore.orm.rendering import TableVersion

    release_id = resolve_release_id(session, release_code=release_code)

    q = session.query(TableVersion).filter(TableVersion.code == table_code)
    q = filter_by_release(
        q,
        start_col=TableVersion.start_release_id,
        end_col=TableVersion.end_release_id,
        release_id=release_id,
        active_only_fallback=True,
    )

    return q.first()


def load_headers(
    session: Session,
    table_vid: int,
) -> list[tuple[Any, ...]]:
    """Load all headers for a table version.

    Returns list of (TableVersionHeader, Header, HeaderVersion) tuples
    in a single query with JOINs.
    """
    from dpmcore.orm.rendering import (
        Header,
        HeaderVersion,
        TableVersionHeader,
    )

    rows = (
        session.query(TableVersionHeader, Header, HeaderVersion)
        .join(Header, Header.header_id == TableVersionHeader.header_id)
        .join(
            HeaderVersion,
            HeaderVersion.header_vid == TableVersionHeader.header_vid,
        )
        .filter(TableVersionHeader.table_vid == table_vid)
        .all()
    )
    return [tuple(r) for r in rows]


def load_cells(
    session: Session,
    table_vid: int,
) -> list[tuple[Any, ...]]:
    """Load all cells for a table version.

    Returns list of (TableVersionCell, Cell) tuples.
    """
    from dpmcore.orm.rendering import Cell, TableVersionCell

    rows = (
        session.query(TableVersionCell, Cell)
        .join(Cell, Cell.cell_id == TableVersionCell.cell_id)
        .filter(TableVersionCell.table_vid == table_vid)
        .all()
    )
    return [tuple(r) for r in rows]


# ------------------------------------------------------------------ #
# Release-windowed code lookups
# ------------------------------------------------------------------ #


def _pick_in_window(
    rows: list[tuple[Any, int, Optional[int], Any]],
    sort_orders: dict[int, int],
    window: ReleaseWindow,
) -> dict[Any, Any]:
    """Choose one version of each versioned row for a release window.

    ``rows`` are ``(key, start_release_id, end_release_id, payload)``
    tuples — ItemCategory and PropertyCategory rows, which carry a code
    that can change from one release to the next.

    Of the versions whose start release falls inside the window, the
    latest one wins: a member recoded halfway through a module
    version's life is reported under its new code. When no version
    starts inside the window, the one in force when the window opened
    is used. Versions that had already ended by then, and versions that
    only start after the window closes, are ignored.

    Releases are ordered by date, not by ID (see
    :mod:`dpmcore.orm.release_sort_order`); ties on the "latest"
    sentinel break by release ID so the choice stays deterministic.

    Returns {key: payload}.
    """
    window_start = (
        sort_orders.get(window.start_release_id, _EARLIEST)
        if window.start_release_id is not None
        else _EARLIEST
    )
    # Release windows are half-open: a version ending at release R is
    # already gone at R. ``None`` is an open end — no upper bound at all,
    # so a version starting at an undated working release still counts.
    window_end = (
        sort_orders.get(window.end_release_id)
        if window.end_release_id is not None
        else None
    )

    best: dict[Any, tuple[int, int]] = {}
    chosen: dict[Any, Any] = {}
    for key, start_id, end_id, payload in rows:
        start = sort_orders.get(start_id)
        if start is None:
            continue
        if window_end is not None and start >= window_end:
            continue
        if (
            end_id is not None
            and sort_orders.get(end_id, _LATEST) <= window_start
        ):
            continue
        rank = (start, start_id)
        if key in best and best[key] >= rank:
            continue
        best[key] = rank
        chosen[key] = payload
    return chosen


def _load_dimension_codes(
    session: Session,
    property_ids: set[int],
    window: ReleaseWindow,
) -> dict[int, str]:
    """Load DimensionCode for properties.

    DimensionCode = ItemCategory.Code where Item IS the Property
    and Category.Code = '_PR', read at *window*.

    Returns {property_id: dimension_code}.
    """
    if not property_ids:
        return {}

    from dpmcore.orm.glossary import Category, ItemCategory

    base = (
        session.query(
            ItemCategory.item_id,
            ItemCategory.start_release_id,
            ItemCategory.end_release_id,
            ItemCategory.code,
        )
        .join(Category, Category.category_id == ItemCategory.category_id)
        .filter(Category.code == "_PR")
    )
    rows = chunked_in(base, ItemCategory.item_id, property_ids)
    picked = _pick_in_window(
        [(r[0], r[1], r[2], r[3]) for r in rows],
        load_release_sort_orders(session),
        window,
    )
    return {item_id: code for item_id, code in picked.items() if code}


def _load_member_codes(
    session: Session,
    item_ids: set[int],
    domain_category_ids: set[int],
    window: ReleaseWindow,
) -> dict[int, str]:
    """Load MemberCode for member items, read at *window*.

    MemberCode = ItemCategory.Code where CategoryID matches the domain.

    Returns {item_id: member_code}.
    """
    if not item_ids or not domain_category_ids:
        return {}

    from dpmcore.orm.glossary import ItemCategory

    # Match the domain in Python rather than via a second ``IN (...)`` so
    # the chunked statement binds only the item-id batch and never
    # approaches SQL Server's 2,100-parameter cap, however many domains
    # the export spans. ``category_id`` is already selected, so this is
    # the same predicate moved off SQL.
    domain = set(domain_category_ids)
    base = session.query(
        ItemCategory.item_id,
        ItemCategory.category_id,
        ItemCategory.start_release_id,
        ItemCategory.end_release_id,
        ItemCategory.code,
    )
    rows = [
        r
        for r in chunked_in(base, ItemCategory.item_id, item_ids)
        if r[1] in domain
    ]
    picked = _pick_in_window(
        [((r[0], r[1]), r[2], r[3], r[4]) for r in rows],
        load_release_sort_orders(session),
        window,
    )
    # An item can be a member of more than one of the domains in play.
    # Now that each domain contributes one version, keep the same
    # deterministic winner as before: the highest (category_id, code).
    result: dict[int, str] = {}
    for (item_id, _category_id), code in sorted(picked.items()):
        if code:
            result[item_id] = code
    return result


def _load_property_categories(
    session: Session,
    property_ids: set[int],
    window: ReleaseWindow,
) -> dict[int, tuple[int, str]]:
    """Load the domain each property belongs to, read at *window*.

    Returns {property_id: (category_id, category_code)}.
    """
    if not property_ids:
        return {}

    from dpmcore.orm.glossary import Category, PropertyCategory

    base = session.query(
        PropertyCategory.property_id,
        PropertyCategory.start_release_id,
        PropertyCategory.end_release_id,
        PropertyCategory.category_id,
        Category.code,
    ).outerjoin(
        Category,
        Category.category_id == PropertyCategory.category_id,
    )
    rows = chunked_in(base, PropertyCategory.property_id, property_ids)
    return _pick_in_window(
        [(r[0], r[1], r[2], (r[3], r[4] or "")) for r in rows],
        load_release_sort_orders(session),
        window,
    )


# ------------------------------------------------------------------ #
# Categorisation loading
# ------------------------------------------------------------------ #


def load_categorisations(
    session: Session,
    context_ids: set[int],
    window: ReleaseWindow,
) -> dict[int, list[DimensionMember]]:
    """Batch-load dimensional categorisations for a set of context IDs.

    Codes are read at *window* — the release window of the version
    being exported.

    Returns {context_id: [DimensionMember, ...]}.
    """
    if not context_ids:
        return {}

    from sqlalchemy.orm import aliased

    from dpmcore.orm.glossary import (
        ContextComposition,
        Item,
        Property,
    )
    from dpmcore.orm.infrastructure import DataType

    DimItem = aliased(Item, name="dim_item")
    MemberItem = aliased(Item, name="member_item")

    base = (
        session.query(
            ContextComposition.context_id,
            ContextComposition.property_id,
            DimItem.name,  # dimension label
            ContextComposition.item_id,  # member item id
            MemberItem.name,  # member label
            DataType.code,  # data type code
        )
        .join(DimItem, DimItem.item_id == ContextComposition.property_id)
        .outerjoin(
            MemberItem,
            MemberItem.item_id == ContextComposition.item_id,
        )
        .outerjoin(
            Property,
            Property.property_id == ContextComposition.property_id,
        )
        .outerjoin(DataType, DataType.data_type_id == Property.data_type_id)
    )
    rows = chunked_in(base, ContextComposition.context_id, context_ids)

    # Collect IDs for code lookups
    prop_ids: set[int] = set()
    member_item_ids: set[int] = set()
    for row in rows:
        prop_ids.add(row[1])
        if row[3]:
            member_item_ids.add(row[3])

    domains = _load_property_categories(session, prop_ids, window)
    domain_cat_ids = {cat_id for cat_id, _code in domains.values()}
    dim_codes = _load_dimension_codes(session, prop_ids, window)
    member_codes = _load_member_codes(
        session,
        member_item_ids,
        domain_cat_ids,
        window,
    )

    result: dict[int, list[DimensionMember]] = {}
    for row in rows:
        ctx_id = row[0]
        _cat_id, domain_code = domains.get(row[1], (0, ""))
        dm = DimensionMember(
            property_id=row[1],
            dimension_label=row[2] or "",
            dimension_code=dim_codes.get(row[1], ""),
            domain_code=domain_code,
            member_label=row[4] or "",
            member_code=member_codes.get(row[3], "") if row[3] else "",
            data_type_code=row[5] or "",
        )
        result.setdefault(ctx_id, []).append(dm)

    return result


def load_property_as_categorisation(
    session: Session,
    property_ids: set[int],
    window: ReleaseWindow,
) -> dict[int, DimensionMember]:
    """Load categorisation info for headers that use property_id directly.

    Some headers (typically columns) reference a property_id instead of
    a context_id. The property IS the member (e.g., 'Carrying amount').
    Codes are read at *window*.
    """
    if not property_ids:
        return {}

    from dpmcore.orm.glossary import Item, Property
    from dpmcore.orm.infrastructure import DataType

    base = (
        session.query(
            Item.item_id,
            Item.name,  # member label (e.g., "Carrying amount")
            DataType.code,  # data type code
        )
        .join(Property, Property.property_id == Item.item_id)
        .outerjoin(DataType, DataType.data_type_id == Property.data_type_id)
    )
    rows = chunked_in(base, Item.item_id, property_ids)

    domains = _load_property_categories(session, property_ids, window)
    # Load member codes: for "Main Property", the property itself
    # IS the member, so its code in category '_PR' is the
    # member_code (e.g., qCCB)
    dim_codes = _load_dimension_codes(session, property_ids, window)

    result: dict[int, DimensionMember] = {}
    for row in rows:
        _cat_id, domain_code = domains.get(row[0], (0, ""))
        result[row[0]] = DimensionMember(
            property_id=row[0],
            dimension_label="Main Property",
            dimension_code="ATY",
            domain_code=domain_code,
            member_label=row[1] or "",
            member_code=dim_codes.get(row[0], ""),
            data_type_code=row[2] or "",
        )

    return result


def load_dp_categorisations(
    session: Session,
    variable_vids: set[int],
    window: ReleaseWindow,
) -> dict[int, list[DimensionMember]]:
    """Load dimensional categorisations for data point variables.

    Codes are read at *window*.

    Returns {variable_vid: [DimensionMember, ...]}.
    """
    if not variable_vids:
        return {}

    from sqlalchemy.orm import aliased

    from dpmcore.orm.glossary import (
        ContextComposition,
        Item,
        Property,
    )
    from dpmcore.orm.infrastructure import DataType
    from dpmcore.orm.variables import VariableVersion

    DimItem = aliased(Item, name="dim_item")
    MemberItem = aliased(Item, name="member_item")

    base = (
        session.query(
            VariableVersion.variable_vid,
            ContextComposition.property_id,
            DimItem.name,  # dimension label
            ContextComposition.item_id,  # member item id
            MemberItem.name,  # member label
            DataType.code,  # data type code
        )
        .join(
            ContextComposition,
            ContextComposition.context_id == VariableVersion.context_id,
        )
        .join(DimItem, DimItem.item_id == ContextComposition.property_id)
        .outerjoin(
            MemberItem,
            MemberItem.item_id == ContextComposition.item_id,
        )
        .outerjoin(
            Property,
            Property.property_id == ContextComposition.property_id,
        )
        .outerjoin(DataType, DataType.data_type_id == Property.data_type_id)
    )
    rows = chunked_in(base, VariableVersion.variable_vid, variable_vids)

    # Collect IDs for code lookups
    prop_ids: set[int] = set()
    member_item_ids: set[int] = set()
    for row in rows:
        prop_ids.add(row[1])
        if row[3]:
            member_item_ids.add(row[3])

    domains = _load_property_categories(session, prop_ids, window)
    domain_cat_ids = {cat_id for cat_id, _code in domains.values()}
    dim_codes = _load_dimension_codes(session, prop_ids, window)
    member_codes = _load_member_codes(
        session,
        member_item_ids,
        domain_cat_ids,
        window,
    )

    result: dict[int, list[DimensionMember]] = {}
    for row in rows:
        vvid = row[0]
        _cat_id, domain_code = domains.get(row[1], (0, ""))
        dm = DimensionMember(
            property_id=row[1],
            dimension_label=row[2] or "",
            dimension_code=dim_codes.get(row[1], ""),
            domain_code=domain_code,
            member_label=row[3] or "" if not row[4] else row[4],
            member_code=member_codes.get(row[3], "") if row[3] else "",
            data_type_code=row[5] or "",
        )
        result.setdefault(vvid, []).append(dm)

    return result


def load_subcategory_info(
    session: Session,
    subcategory_vids: set[int],
) -> dict[int, tuple[str, str, str]]:
    """Load SubCategory info for headers with a SubCategoryVID.

    Returns {subcategory_vid: (subcat_code, subcat_description, cat_code)}.
    """
    if not subcategory_vids:
        return {}

    from dpmcore.orm.glossary import Category, SubCategory, SubCategoryVersion

    base = (
        session.query(
            SubCategoryVersion.subcategory_vid,
            SubCategory.code,
            SubCategory.description,
            Category.code,
            SubCategory.name,
        )
        .join(
            SubCategory,
            SubCategory.subcategory_id == SubCategoryVersion.subcategory_id,
        )
        .join(Category, Category.category_id == SubCategory.category_id)
    )
    rows = chunked_in(
        base, SubCategoryVersion.subcategory_vid, subcategory_vids
    )
    # Prefer description over name (some subcategories only have one populated)
    return {r[0]: (r[1] or "", r[2] or r[4] or "", r[3] or "") for r in rows}


def load_key_variable_property_ids(
    session: Session,
    variable_vids: set[int],
) -> dict[int, int]:
    """Load property_id for each key variable VID.

    Returns {variable_vid: property_id}.
    """
    if not variable_vids:
        return {}

    from dpmcore.orm.variables import VariableVersion

    base = session.query(
        VariableVersion.variable_vid, VariableVersion.property_id
    )
    rows = chunked_in(base, VariableVersion.variable_vid, variable_vids)
    return {r[0]: r[1] for r in rows if r[1]}


def load_variable_info(
    session: Session,
    variable_vids: set[int],
) -> dict[int, tuple[int, str, str]]:
    """Load VariableID, data type code, and property name.

    Returns {variable_vid: (variable_id, data_type_code, property_name)}.
    property_name is used for enumeration ('e') type cells to show [domain].
    """
    if not variable_vids:
        return {}

    from dpmcore.orm.glossary import Item, Property
    from dpmcore.orm.infrastructure import DataType
    from dpmcore.orm.variables import VariableVersion

    base = (
        session.query(
            VariableVersion.variable_vid,
            VariableVersion.variable_id,
            DataType.code,
            Item.name,
        )
        .outerjoin(
            Property,
            Property.property_id == VariableVersion.property_id,
        )
        .outerjoin(DataType, DataType.data_type_id == Property.data_type_id)
        .outerjoin(Item, Item.item_id == VariableVersion.property_id)
    )
    rows = chunked_in(base, VariableVersion.variable_vid, variable_vids)
    return {r[0]: (r[1], r[2] or "", r[3] or "") for r in rows}


def load_enumerations(
    session: Session,
    subcategory_vids: set[int],
    window: ReleaseWindow,
) -> dict[int, Enumeration]:
    """Load the allowed values of a set of SubCategoryVersions.

    A SubCategoryVersion is the hierarchy that restricts which members
    of a domain may be reported: for an enumerated variable it *is* the
    list of possible values. Items are returned in hierarchy order,
    each with the depth of its position in the parent/child tree.

    A member's code and signature are versioned: the same item is
    ``eba_CU:x7`` up to release 4.2 and ``eba_CU:qx2015`` from 4.2 on.
    They are therefore read at *window* and not from the
    currently-active row. Items with no ``ItemCategory`` row in the
    parent category there are dropped: they carry no code in it.

    Args:
        session: SQLAlchemy session.
        subcategory_vids: Hierarchies to load.
        window: Release window of the version being exported.

    Returns {subcategory_vid: Enumeration}.
    """
    if not subcategory_vids:
        return {}

    from dpmcore.orm.glossary import (
        Category,
        Item,
        ItemCategory,
        SubCategory,
        SubCategoryItem,
        SubCategoryVersion,
    )

    info_base = (
        session.query(
            SubCategoryVersion.subcategory_vid,
            SubCategory.code,
            SubCategory.name,
            Category.category_id,
            Category.code,
        )
        .join(
            SubCategory,
            SubCategory.subcategory_id == SubCategoryVersion.subcategory_id,
        )
        .join(Category, Category.category_id == SubCategory.category_id)
    )
    info_rows = chunked_in(
        info_base,
        SubCategoryVersion.subcategory_vid,
        subcategory_vids,
    )
    if not info_rows:
        return {}

    # SubCategoryItem rows in hierarchy order. The ORDER BY survives
    # chunking because each subcategory_vid falls entirely within one
    # chunk (the chunk column is subcategory_vid).
    item_base = (
        session.query(
            SubCategoryItem.subcategory_vid,
            SubCategoryItem.item_id,
            SubCategoryItem.parent_item_id,
            Item.name,
        )
        .join(Item, Item.item_id == SubCategoryItem.item_id)
        .order_by(SubCategoryItem.subcategory_vid, SubCategoryItem.order)
    )
    item_rows = chunked_in(
        item_base,
        SubCategoryItem.subcategory_vid,
        subcategory_vids,
    )

    # Item codes are per (item, parent category): load the categories
    # of the requested hierarchies and match in Python, so the chunked
    # statement binds only one id list.
    category_ids = {row[3] for row in info_rows if row[3]}
    item_ids = {row[1] for row in item_rows}
    code_base = session.query(
        ItemCategory.item_id,
        ItemCategory.category_id,
        ItemCategory.start_release_id,
        ItemCategory.end_release_id,
        ItemCategory.code,
        ItemCategory.signature,
    )
    code_rows = [
        r
        for r in chunked_in(code_base, ItemCategory.item_id, item_ids)
        if r[1] in category_ids
    ]
    codes: dict[tuple[int, int], tuple[str, str]] = _pick_in_window(
        [
            ((r[0], r[1]), r[2], r[3], (r[4] or "", r[5] or ""))
            for r in code_rows
        ],
        load_release_sort_orders(session),
        window,
    )

    result: dict[int, Enumeration] = {
        row[0]: Enumeration(
            subcategory_vid=row[0],
            code=row[1] or "",
            name=row[2] or "",
            category_code=row[4] or "",
        )
        for row in info_rows
    }
    cat_by_svid: dict[int, int] = {row[0]: row[3] for row in info_rows}

    # Depth comes from the parent chain; parents always precede their
    # children in hierarchy order, so a single pass suffices.
    depths: dict[tuple[int, int], int] = {}
    for svid, item_id, parent_item_id, name in item_rows:
        depth = (
            depths.get((svid, parent_item_id), -1) + 1 if parent_item_id else 0
        )
        depths[(svid, item_id)] = depth
        enum = result.get(svid)
        entry = codes.get((item_id, cat_by_svid.get(svid, 0)))
        if enum is None or entry is None:
            continue
        code, signature = entry
        enum.values.append(
            EnumValue(
                code=code,
                label=name or "",
                depth=depth,
                signature=signature,
            ),
        )

    return result
