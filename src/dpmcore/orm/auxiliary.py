"""ORM models for auxiliary and mapping entities.

This module defines helper models that do not belong to a specific
DPM domain: cell mappings, cell status tracking, and model-level
violation records.
"""

from typing import Optional

from sqlalchemy import (
    Boolean,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from dpmcore.orm.base import Base


# ------------------------------------------------------------------
# AuxCellMapping
# ------------------------------------------------------------------


class AuxCellMapping(Base):
    """Maps new cell/table identifiers to their old equivalents.

    Attributes:
        new_cell_id: New cell identifier (composite PK).
        new_table_vid: New table version identifier (composite PK).
        old_cell_id: Previous cell identifier.
        old_table_vid: Previous table version identifier.
    """

    __tablename__ = "Aux_CellMapping"
    __table_args__ = (UniqueConstraint("NewCellID", "NewTableVID"),)

    new_cell_id: Mapped[int] = mapped_column(
        "NewCellID", Integer, primary_key=True
    )
    new_table_vid: Mapped[int] = mapped_column(
        "NewTableVID", Integer, primary_key=True
    )
    old_cell_id: Mapped[Optional[int]] = mapped_column("OldCellID", Integer)
    old_table_vid: Mapped[Optional[int]] = mapped_column(
        "OldTableVID", Integer
    )


# ------------------------------------------------------------------
# AuxCellStatus
# ------------------------------------------------------------------


class AuxCellStatus(Base):
    """Tracks the status and novelty of a cell within a table version.

    Attributes:
        table_vid: Table version identifier (composite PK).
        cell_id: Cell identifier (composite PK).
        status: Status descriptor.
        is_new_cell: Whether the cell is newly introduced.
    """

    __tablename__ = "Aux_CellStatus"
    __table_args__ = (UniqueConstraint("TableVID", "CellID"),)

    table_vid: Mapped[int] = mapped_column(
        "TableVID", Integer, primary_key=True
    )
    cell_id: Mapped[int] = mapped_column("CellID", Integer, primary_key=True)
    status: Mapped[Optional[str]] = mapped_column("Status", String(100))
    is_new_cell: Mapped[Optional[bool]] = mapped_column("IsNewCell", Boolean)


# ------------------------------------------------------------------
# ModelViolations
# ------------------------------------------------------------------


class ModelViolations(Base):
    """Records structural or semantic violations found in a model.

    Attributes:
        id: Auto-increment primary key.
        violation_code: Short violation code.
        violation: Violation description.
        is_blocking: Whether the violation blocks processing.
        table_vid: Affected table version identifier.
        old_table_vid: Previous table version identifier.
        table_code: Table code.
        header_id: Header identifier.
        header_code: Header code.
        header_vid: Header version identifier.
        old_header_vid: Previous header version identifier.
        key_header: Whether the header is a key header.
        header_direction: Header direction flag.
        header_property_id: Header property identifier.
        header_property_code: Header property code.
        header_subcategory_id: Header subcategory identifier.
        header_subcategory_name: Header subcategory name.
        header_context_id: Header context identifier.
        category_id: Category identifier.
        category_code: Category code.
        item_id: Item identifier.
        item_code: Item code.
        cell_id: Cell identifier.
        cell_code: Cell code.
        cell2_id: Second cell identifier.
        cell2_code: Second cell code.
        vv_end_release_id: Variable-version end release id.
        new_aspect: Description of the new aspect.
    """

    __tablename__ = "ModelViolations"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    violation_code: Mapped[Optional[str]] = mapped_column(
        "ViolationCode", String(10)
    )
    violation: Mapped[Optional[str]] = mapped_column("Violation", String(255))
    is_blocking: Mapped[Optional[bool]] = mapped_column("isBlocking", Boolean)
    table_vid: Mapped[Optional[int]] = mapped_column("TableVID", Integer)
    old_table_vid: Mapped[Optional[int]] = mapped_column(
        "OldTableVID", Integer
    )
    table_code: Mapped[Optional[str]] = mapped_column("TableCode", String(40))
    header_id: Mapped[Optional[int]] = mapped_column("HeaderID", Integer)
    header_code: Mapped[Optional[str]] = mapped_column(
        "HeaderCode", String(20)
    )
    header_vid: Mapped[Optional[int]] = mapped_column("HeaderVID", Integer)
    old_header_vid: Mapped[Optional[int]] = mapped_column(
        "OldHeaderVID", Integer
    )
    key_header: Mapped[Optional[bool]] = mapped_column("KeyHeader", Boolean)
    header_direction: Mapped[Optional[str]] = mapped_column(
        "HeaderDirection", String(1)
    )
    header_property_id: Mapped[Optional[int]] = mapped_column(
        "HeaderPropertyID", Integer
    )
    header_property_code: Mapped[Optional[str]] = mapped_column(
        "HeaderPropertyCode", String(20)
    )
    header_subcategory_id: Mapped[Optional[int]] = mapped_column(
        "HeaderSubcategoryID", Integer
    )
    header_subcategory_name: Mapped[Optional[str]] = mapped_column(
        "HeaderSubcategoryName", String(60)
    )
    header_context_id: Mapped[Optional[int]] = mapped_column(
        "HeaderContextID", Integer
    )
    category_id: Mapped[Optional[int]] = mapped_column("CategoryID", Integer)
    category_code: Mapped[Optional[str]] = mapped_column(
        "CategoryCode", String(30)
    )
    item_id: Mapped[Optional[int]] = mapped_column("ItemID", Integer)
    item_code: Mapped[Optional[str]] = mapped_column("ItemCode", String(30))
    cell_id: Mapped[Optional[int]] = mapped_column("CellID", Integer)
    cell_code: Mapped[Optional[str]] = mapped_column("CellCode", String(50))
    cell2_id: Mapped[Optional[int]] = mapped_column("Cell2ID", Integer)
    cell2_code: Mapped[Optional[str]] = mapped_column("Cell2Code", String(50))
    vv_end_release_id: Mapped[Optional[int]] = mapped_column(
        "VVEndReleaseID", Integer
    )
    new_aspect: Mapped[Optional[str]] = mapped_column("NewAspect", String(80))
