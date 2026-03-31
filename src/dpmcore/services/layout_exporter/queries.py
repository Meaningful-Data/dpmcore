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


def load_categorisations(
    session: Session,
    context_ids: set[int],
) -> dict[int, list[DimensionMember]]:
    """Batch-load dimensional categorisations for a set of context IDs.

    Returns {context_id: [DimensionMember, ...]}.
    Each ContextComposition row maps a property (dimension) to an item (member).
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
            DimItem.name,           # dimension label
            MemberItem.item_id,
            MemberItem.name,        # member label
            Category.code,          # domain code
            DataType.code,          # data type code
            Property.is_metric,
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

    result: dict[int, list[DimensionMember]] = {}
    for row in rows:
        ctx_id = row[0]
        dm = DimensionMember(
            property_id=row[1],
            dimension_label=row[2] or "",
            dimension_code="",  # derived later if needed
            domain_code=row[5] or "",
            member_label=row[4] or "",
            member_code="",
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
            Property.is_metric,
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

    result: dict[int, DimensionMember] = {}
    for row in rows:
        result[row[0]] = DimensionMember(
            property_id=row[0],
            dimension_label="Main Property",
            dimension_code="",
            domain_code=row[2] or "",
            member_label=row[1] or "",
            member_code="",
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
            DimItem.name,           # dimension label
            MemberItem.name,        # member label
            Category.code,          # domain code
            DataType.code,          # data type code
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

    result: dict[int, list[DimensionMember]] = {}
    for row in rows:
        vvid = row[0]
        dm = DimensionMember(
            property_id=row[1],
            dimension_label=row[2] or "",
            dimension_code="",
            domain_code=row[4] or "",
            member_label=row[3] or "",
            member_code="",
            data_type_code=row[5] or "",
        )
        result.setdefault(vvid, []).append(dm)

    return result
