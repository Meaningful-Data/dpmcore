"""Batch query functions for the table layout exporter.

All functions take a SQLAlchemy session as first argument and return
raw ORM objects or lightweight tuples. Processing logic lives in
processing.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from dpmcore.services.layout_exporter.models import DimensionMember

if TYPE_CHECKING:
    from dpmcore.orm.rendering import TableVersion


def load_module_table_versions(
    session: Session,
    module_code: str,
    release_code: Optional[str] = None,
) -> list[Any]:
    """Load all TableVersions for a given module version code.

    Returns TableVersion ORM objects ordered by module composition order.
    """
    from dpmcore.orm.packaging import ModuleVersion, ModuleVersionComposition
    from dpmcore.orm.rendering import TableVersion

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

    if release_code:
        from dpmcore.orm.infrastructure import Release

        q = q.join(
            Release,
            Release.release_id == ModuleVersion.start_release_id,
        ).filter(Release.code == release_code)
    else:
        q = q.filter(ModuleVersion.end_release_id.is_(None))

    q = q.order_by(ModuleVersionComposition.order)
    return q.all()


def load_table_version(
    session: Session,
    table_code: str,
    release_code: Optional[str] = None,
) -> Optional[Any]:
    """Load a single TableVersion by code."""
    from dpmcore.orm.rendering import TableVersion

    q = session.query(TableVersion).filter(TableVersion.code == table_code)

    if release_code:
        from dpmcore.orm.infrastructure import Release

        q = (
            q.join(
                Release,
                Release.release_id == TableVersion.start_release_id,
            )
            .filter(Release.code == release_code)
        )
    else:
        q = q.filter(TableVersion.end_release_id.is_(None))

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
    return rows


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
    return rows


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

    rows = (
        session.query(ItemCategory.item_id, ItemCategory.code)
        .join(Category, Category.category_id == ItemCategory.category_id)
        .filter(
            ItemCategory.item_id.in_(property_ids),
            Category.code == "_PR",
            ItemCategory.end_release_id.is_(None),
        )
        .all()
    )
    return {r[0]: r[1] for r in rows if r[1]}


def _load_member_codes(
    session: Session,
    item_ids: set[int],
    domain_category_ids: set[int],
) -> dict[int, str]:
    """Load MemberCode for member items.

    MemberCode = ItemCategory.Code where CategoryID matches the domain.

    Returns {item_id: member_code}.
    """
    if not item_ids or not domain_category_ids:
        return {}

    from dpmcore.orm.glossary import ItemCategory

    rows = (
        session.query(
            ItemCategory.item_id, ItemCategory.code, ItemCategory.category_id,
        )
        .filter(
            ItemCategory.item_id.in_(item_ids),
            ItemCategory.category_id.in_(domain_category_ids),
            ItemCategory.end_release_id.is_(None),
        )
        .all()
    )
    return {r[0]: r[1] for r in rows if r[1]}


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

    rows = (
        session.query(
            ContextComposition.context_id,
            ContextComposition.property_id,
            DimItem.name,                   # dimension label
            ContextComposition.item_id,     # member item id
            MemberItem.name,                # member label
            Category.code,                  # domain code
            DataType.code,                  # data type code
            PropertyCategory.category_id,   # domain category id
        )
        .join(DimItem, DimItem.item_id == ContextComposition.property_id)
        .outerjoin(
            MemberItem, MemberItem.item_id == ContextComposition.item_id,
        )
        .outerjoin(
            Property, Property.property_id == ContextComposition.property_id,
        )
        .outerjoin(
            PropertyCategory,
            and_(
                PropertyCategory.property_id == ContextComposition.property_id,
                PropertyCategory.end_release_id.is_(None),
            ),
        )
        .outerjoin(
            Category, Category.category_id == PropertyCategory.category_id,
        )
        .outerjoin(DataType, DataType.data_type_id == Property.data_type_id)
        .filter(ContextComposition.context_id.in_(context_ids))
        .all()
    )

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
            member_code=member_codes.get(row[3], "") if row[3] else "",
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

    rows = (
        session.query(
            Item.item_id,
            Item.name,          # member label (e.g., "Carrying amount")
            Category.code,      # domain code
            DataType.code,      # data type code
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
            Category, Category.category_id == PropertyCategory.category_id,
        )
        .outerjoin(DataType, DataType.data_type_id == Property.data_type_id)
        .filter(Item.item_id.in_(property_ids))
        .all()
    )

    # Load member codes: for "Main Property", the property itself IS the member,
    # so its code in category '_PR' is the member_code (e.g., qCCB)
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

    rows = (
        session.query(
            VariableVersion.variable_vid,
            ContextComposition.property_id,
            DimItem.name,                   # dimension label
            ContextComposition.item_id,     # member item id
            MemberItem.name,                # member label
            Category.code,                  # domain code
            DataType.code,                  # data type code
            PropertyCategory.category_id,   # domain category id
        )
        .join(
            ContextComposition,
            ContextComposition.context_id == VariableVersion.context_id,
        )
        .join(DimItem, DimItem.item_id == ContextComposition.property_id)
        .outerjoin(
            MemberItem, MemberItem.item_id == ContextComposition.item_id,
        )
        .outerjoin(
            Property, Property.property_id == ContextComposition.property_id,
        )
        .outerjoin(
            PropertyCategory,
            and_(
                PropertyCategory.property_id == ContextComposition.property_id,
                PropertyCategory.end_release_id.is_(None),
            ),
        )
        .outerjoin(
            Category, Category.category_id == PropertyCategory.category_id,
        )
        .outerjoin(DataType, DataType.data_type_id == Property.data_type_id)
        .filter(VariableVersion.variable_vid.in_(variable_vids))
        .all()
    )

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
            member_code=member_codes.get(row[3], "") if row[3] else "",
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

    rows = (
        session.query(
            SubCategoryVersion.subcategory_vid,
            SubCategory.code,
            SubCategory.description,
            Category.code,
            SubCategory.name,
        )
        .join(SubCategory, SubCategory.subcategory_id == SubCategoryVersion.subcategory_id)
        .join(Category, Category.category_id == SubCategory.category_id)
        .filter(SubCategoryVersion.subcategory_vid.in_(subcategory_vids))
        .all()
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

    rows = (
        session.query(VariableVersion.variable_vid, VariableVersion.property_id)
        .filter(VariableVersion.variable_vid.in_(variable_vids))
        .all()
    )
    return {r[0]: r[1] for r in rows if r[1]}


def load_variable_info(
    session: Session,
    variable_vids: set[int],
) -> dict[int, tuple[int, str, str]]:
    """Load VariableID, data type code, and property name for data cell display.

    Returns {variable_vid: (variable_id, data_type_code, property_name)}.
    property_name is used for enumeration ('e') type cells to show [domain].
    """
    if not variable_vids:
        return {}

    from dpmcore.orm.glossary import Item, Property
    from dpmcore.orm.infrastructure import DataType
    from dpmcore.orm.variables import VariableVersion

    rows = (
        session.query(
            VariableVersion.variable_vid,
            VariableVersion.variable_id,
            DataType.code,
            Item.name,
        )
        .outerjoin(
            Property, Property.property_id == VariableVersion.property_id,
        )
        .outerjoin(DataType, DataType.data_type_id == Property.data_type_id)
        .outerjoin(Item, Item.item_id == VariableVersion.property_id)
        .filter(VariableVersion.variable_vid.in_(variable_vids))
        .all()
    )
    return {r[0]: (r[1], r[2] or "", r[3] or "") for r in rows}
