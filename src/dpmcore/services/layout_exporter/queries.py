"""Batch query functions for the table layout exporter.

All functions take a SQLAlchemy session as first argument and return
raw ORM objects or lightweight tuples. Processing logic lives in
processing.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from dpmcore.orm.query_utils import chunked_in
from dpmcore.services.layout_exporter.models import DimensionMember

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
# Code lookups
# ------------------------------------------------------------------ #


def _load_dimension_codes(
    session: Session,
    property_ids: set[int],
) -> dict[int, str]:
    """Load DimensionCode for properties.

    DimensionCode = ItemCategory.Code where Item IS the Property
    and Category.Code = '_PR'.

    Returns {property_id: dimension_code}.
    """
    if not property_ids:
        return {}

    from dpmcore.orm.glossary import Category, ItemCategory

    base = (
        session.query(ItemCategory.item_id, ItemCategory.code)
        .join(Category, Category.category_id == ItemCategory.category_id)
        .filter(
            Category.code == "_PR",
            ItemCategory.end_release_id.is_(None),
        )
    )
    rows = chunked_in(base, ItemCategory.item_id, property_ids)
    return {r[0]: r[1] for r in rows if r[1]}


def _load_member_codes(
    session: Session,
    item_ids: set[int],
    domain_category_ids: set[int],
) -> dict[tuple[int, int], str]:
    """Load MemberCode for member items, per domain.

    MemberCode = ItemCategory.Code where CategoryID matches the domain
    the dimension is typed on — or, when that domain is a
    *super-category*, one of the categories composing it, which is
    where ``ItemCategory`` actually files the member (#359).

    Keyed by ``(item_id, domain_category_id)`` rather than by item
    alone: the export spans many domains at once, and the same item can
    be filed in two of them, so a per-item key silently hands one
    domain's code to another domain's member.

    Returns {(item_id, domain_category_id): member_code}.
    """
    if not item_ids or not domain_category_ids:
        return {}

    from dpmcore.orm.glossary import ItemCategory
    from dpmcore.orm.supercategories import (
        domain_search_order,
        load_supercategory_members,
    )

    members_by_domain = load_supercategory_members(
        session, domain_category_ids, release_id=None
    )
    # Which domains a filing category can answer for: itself, plus every
    # super-category that composes it.
    domains_by_filing: dict[int, set[int]] = {
        domain: {domain} for domain in domain_category_ids
    }
    for domain, members in members_by_domain.items():
        for member in members:
            domains_by_filing.setdefault(member, set()).add(domain)

    # Match the filing category in Python rather than via a second
    # ``IN (...)`` so the chunked statement binds only the item-id batch
    # (plus the release filter) and never approaches SQL Server's
    # 2,100-parameter cap, however many domains the export spans.
    # ``category_id`` is already selected, so this is the same predicate
    # moved off SQL.
    base = (
        session.query(
            ItemCategory.item_id,
            ItemCategory.code,
            ItemCategory.category_id,
        )
        .filter(ItemCategory.end_release_id.is_(None))
        # Two open rows for one item in the same category (successive
        # start releases) resolve to the lowest code, deterministically.
        # This holds under chunking because each item_id is queried in
        # exactly one batch (the chunk column is item_id), so all of an
        # item's rows land in that one ordered result.
        .order_by(ItemCategory.category_id, ItemCategory.code)
    )
    filed_by_item: dict[int, dict[int, str]] = {}
    for item_id, code, category_id in chunked_in(
        base, ItemCategory.item_id, item_ids
    ):
        if code:
            filed_by_item.setdefault(item_id, {}).setdefault(category_id, code)

    codes: dict[tuple[int, int], str] = {}
    for item_id, filed in filed_by_item.items():
        candidates = {
            domain
            for category_id in filed
            for domain in domains_by_filing.get(category_id, ())
        }
        for domain in candidates:
            for category_id in domain_search_order(domain, members_by_domain):
                code = filed.get(category_id)
                if code is not None:
                    codes[(item_id, domain)] = code
                    break
    return codes


# ------------------------------------------------------------------ #
# Categorisation loading
# ------------------------------------------------------------------ #


def load_categorisations(
    session: Session,
    context_ids: set[int],
) -> dict[int, list[DimensionMember]]:
    """Batch-load dimensional categorisations for a set of context IDs.

    Returns {context_id: [DimensionMember, ...]}.
    """
    if not context_ids:
        return {}

    from sqlalchemy.orm import aliased

    from dpmcore.orm.glossary import (
        Category,
        ContextComposition,
        Item,
        Property,
        PropertyCategory,
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
            Category.code,  # domain code
            DataType.code,  # data type code
            PropertyCategory.category_id,  # domain category id
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
        .outerjoin(
            PropertyCategory,
            and_(
                PropertyCategory.property_id == ContextComposition.property_id,
                PropertyCategory.end_release_id.is_(None),
            ),
        )
        .outerjoin(
            Category,
            Category.category_id == PropertyCategory.category_id,
        )
        .outerjoin(DataType, DataType.data_type_id == Property.data_type_id)
    )
    rows = chunked_in(base, ContextComposition.context_id, context_ids)

    # Collect IDs for code lookups
    prop_ids: set[int] = set()
    member_item_ids: set[int] = set()
    domain_cat_ids: set[int] = set()
    for row in rows:
        prop_ids.add(row[1])
        if row[3]:
            member_item_ids.add(row[3])
        if row[7]:
            domain_cat_ids.add(row[7])

    dim_codes = _load_dimension_codes(session, prop_ids)
    member_codes = _load_member_codes(session, member_item_ids, domain_cat_ids)

    result: dict[int, list[DimensionMember]] = {}
    for row in rows:
        ctx_id = row[0]
        dm = DimensionMember(
            property_id=row[1],
            dimension_label=row[2] or "",
            dimension_code=dim_codes.get(row[1], ""),
            domain_code=row[5] or "",
            member_label=row[4] or "",
            member_code=(
                member_codes.get((row[3], row[7]), "")
                if row[3] and row[7]
                else ""
            ),
            data_type_code=row[6] or "",
        )
        result.setdefault(ctx_id, []).append(dm)

    return result


def load_property_as_categorisation(
    session: Session,
    property_ids: set[int],
) -> dict[int, DimensionMember]:
    """Load categorisation info for headers that use property_id directly.

    Some headers (typically columns) reference a property_id instead of
    a context_id. The property IS the member (e.g., 'Carrying amount').
    """
    if not property_ids:
        return {}

    from dpmcore.orm.glossary import Category, Item, Property, PropertyCategory
    from dpmcore.orm.infrastructure import DataType

    base = (
        session.query(
            Item.item_id,
            Item.name,  # member label (e.g., "Carrying amount")
            Category.code,  # domain code
            DataType.code,  # data type code
        )
        .join(Property, Property.property_id == Item.item_id)
        .outerjoin(
            PropertyCategory,
            and_(
                PropertyCategory.property_id == Property.property_id,
                PropertyCategory.end_release_id.is_(None),
            ),
        )
        .outerjoin(
            Category,
            Category.category_id == PropertyCategory.category_id,
        )
        .outerjoin(DataType, DataType.data_type_id == Property.data_type_id)
    )
    rows = chunked_in(base, Item.item_id, property_ids)

    # Load member codes: for "Main Property", the property itself
    # IS the member, so its code in category '_PR' is the
    # member_code (e.g., qCCB)
    dim_codes = _load_dimension_codes(session, property_ids)

    result: dict[int, DimensionMember] = {}
    for row in rows:
        result[row[0]] = DimensionMember(
            property_id=row[0],
            dimension_label="Main Property",
            dimension_code="ATY",
            domain_code=row[2] or "",
            member_label=row[1] or "",
            member_code=dim_codes.get(row[0], ""),
            data_type_code=row[3] or "",
        )

    return result


def load_dp_categorisations(
    session: Session,
    variable_vids: set[int],
) -> dict[int, list[DimensionMember]]:
    """Load dimensional categorisations for data point variables.

    Returns {variable_vid: [DimensionMember, ...]}.
    """
    if not variable_vids:
        return {}

    from sqlalchemy.orm import aliased

    from dpmcore.orm.glossary import (
        Category,
        ContextComposition,
        Item,
        Property,
        PropertyCategory,
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
            Category.code,  # domain code
            DataType.code,  # data type code
            PropertyCategory.category_id,  # domain category id
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
        .outerjoin(
            PropertyCategory,
            and_(
                PropertyCategory.property_id == ContextComposition.property_id,
                PropertyCategory.end_release_id.is_(None),
            ),
        )
        .outerjoin(
            Category,
            Category.category_id == PropertyCategory.category_id,
        )
        .outerjoin(DataType, DataType.data_type_id == Property.data_type_id)
    )
    rows = chunked_in(base, VariableVersion.variable_vid, variable_vids)

    # Collect IDs for code lookups
    prop_ids: set[int] = set()
    member_item_ids: set[int] = set()
    domain_cat_ids: set[int] = set()
    for row in rows:
        prop_ids.add(row[1])
        if row[3]:
            member_item_ids.add(row[3])
        if row[7]:
            domain_cat_ids.add(row[7])

    dim_codes = _load_dimension_codes(session, prop_ids)
    member_codes = _load_member_codes(session, member_item_ids, domain_cat_ids)

    result: dict[int, list[DimensionMember]] = {}
    for row in rows:
        vvid = row[0]
        dm = DimensionMember(
            property_id=row[1],
            dimension_label=row[2] or "",
            dimension_code=dim_codes.get(row[1], ""),
            domain_code=row[5] or "",
            member_label=row[3] or "" if not row[4] else row[4],
            member_code=(
                member_codes.get((row[3], row[7]), "")
                if row[3] and row[7]
                else ""
            ),
            data_type_code=row[6] or "",
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
