"""ORM models for DPM Rendering entities.

This module defines the reporting-table structure: Table,
TableVersion, Header, HeaderVersion, Cell, TableVersionCell,
TableVersionHeader, TableGroup, TableGroupComposition,
TableAssociation, and KeyHeaderMapping.
"""

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dpmcore.orm.base import Base
from dpmcore.orm.infrastructure import Concept, Release

if TYPE_CHECKING:
    from dpmcore.orm.glossary import (
        Context,
        Property,
        SubCategoryVersion,
    )


# ------------------------------------------------------------------
# Table
# ------------------------------------------------------------------


class Table(Base):
    """Top-level reporting table.

    Attributes:
        table_id: Primary key.
        is_abstract: Whether the table is abstract.
        has_open_columns: Whether columns are open.
        has_open_rows: Whether rows are open.
        has_open_sheets: Whether sheets are open.
        is_normalised: Whether the table is normalised.
        is_flat: Whether the table is flat.
        row_guid: FK to Concept.
    """

    __tablename__ = "Table"

    table_id: Mapped[int] = mapped_column(
        "TableID", Integer, primary_key=True
    )
    is_abstract: Mapped[Optional[bool]] = mapped_column(
        "IsAbstract", Boolean
    )
    has_open_columns: Mapped[Optional[bool]] = mapped_column(
        "HasOpenColumns", Boolean
    )
    has_open_rows: Mapped[Optional[bool]] = mapped_column(
        "HasOpenRows", Boolean
    )
    has_open_sheets: Mapped[Optional[bool]] = mapped_column(
        "HasOpenSheets", Boolean
    )
    is_normalised: Mapped[Optional[bool]] = mapped_column(
        "IsNormalised", Boolean
    )
    is_flat: Mapped[Optional[bool]] = mapped_column(
        "IsFlat", Boolean
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    owner_id: Mapped[Optional[int]] = mapped_column(
        "OwnerID", Integer
    )

    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    headers: Mapped[List["Header"]] = relationship(
        back_populates="table",
    )
    cells: Mapped[List["Cell"]] = relationship(
        back_populates="table",
    )
    table_versions: Mapped[List["TableVersion"]] = relationship(
        foreign_keys="TableVersion.table_id",
        back_populates="table",
    )
    abstract_table_versions: Mapped[
        List["TableVersion"]
    ] = relationship(
        foreign_keys="TableVersion.abstract_table_id",
        back_populates="abstract_table",
    )
    table_group_compositions: Mapped[
        List["TableGroupComposition"]
    ] = relationship(
        back_populates="table",
    )
    module_version_compositions: Mapped[
        List["ModuleVersionComposition"]
    ] = relationship(
        back_populates="table",
    )


# ------------------------------------------------------------------
# TableVersion
# ------------------------------------------------------------------


class TableVersion(Base):
    """Release-versioned snapshot of a Table.

    Attributes:
        table_vid: Primary key.
        code: Version code.
        name: Version name.
        description: Version description.
        table_id: FK to Table.
        abstract_table_id: FK to Table (abstract).
        key_id: FK to CompoundKey.
        property_id: FK to Property.
        context_id: FK to Context.
        start_release_id: FK to Release.
        end_release_id: FK to Release.
        row_guid: FK to Concept.
    """

    __tablename__ = "TableVersion"
    __table_args__ = (
        UniqueConstraint("TableID", "StartReleaseID"),
    )

    table_vid: Mapped[int] = mapped_column(
        "TableVID", Integer, primary_key=True
    )
    code: Mapped[Optional[str]] = mapped_column(
        "Code", String(30)
    )
    name: Mapped[Optional[str]] = mapped_column(
        "Name", String(255)
    )
    description: Mapped[Optional[str]] = mapped_column(
        "Description", String(500)
    )
    table_id: Mapped[Optional[int]] = mapped_column(
        "TableID", Integer, ForeignKey("Table.TableID")
    )
    abstract_table_id: Mapped[Optional[int]] = mapped_column(
        "AbstractTableID",
        Integer,
        ForeignKey("Table.TableID"),
    )
    key_id: Mapped[Optional[int]] = mapped_column(
        "KeyID",
        Integer,
        ForeignKey("CompoundKey.KeyID"),
    )
    property_id: Mapped[Optional[int]] = mapped_column(
        "PropertyID",
        Integer,
        ForeignKey("Property.PropertyID"),
    )
    context_id: Mapped[Optional[int]] = mapped_column(
        "ContextID",
        Integer,
        ForeignKey("Context.ContextID"),
    )
    start_release_id: Mapped[Optional[int]] = mapped_column(
        "StartReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
    )
    end_release_id: Mapped[Optional[int]] = mapped_column(
        "EndReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )

    table: Mapped[Optional["Table"]] = relationship(
        foreign_keys=[table_id],
        back_populates="table_versions",
    )
    abstract_table: Mapped[Optional["Table"]] = relationship(
        foreign_keys=[abstract_table_id],
        back_populates="abstract_table_versions",
    )
    key: Mapped[Optional["CompoundKey"]] = relationship(
        foreign_keys=[key_id]
    )
    property: Mapped[Optional["Property"]] = relationship(
        foreign_keys=[property_id]
    )
    context: Mapped[Optional["Context"]] = relationship(
        foreign_keys=[context_id]
    )
    start_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[start_release_id]
    )
    end_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[end_release_id]
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    table_version_cells: Mapped[
        List["TableVersionCell"]
    ] = relationship(
        back_populates="table_version",
    )
    table_version_headers: Mapped[
        List["TableVersionHeader"]
    ] = relationship(
        back_populates="table_version",
    )
    table_associations_as_child: Mapped[
        List["TableAssociation"]
    ] = relationship(
        foreign_keys="TableAssociation.child_table_vid",
        back_populates="child_table_version",
    )
    table_associations_as_parent: Mapped[
        List["TableAssociation"]
    ] = relationship(
        foreign_keys="TableAssociation.parent_table_vid",
        back_populates="parent_table_version",
    )
    module_version_compositions: Mapped[
        List["ModuleVersionComposition"]
    ] = relationship(
        back_populates="table_version",
    )


# ------------------------------------------------------------------
# Header
# ------------------------------------------------------------------


class Header(Base):
    """Header axis (column, row, or sheet) within a Table.

    Attributes:
        header_id: Primary key.
        table_id: FK to Table.
        direction: Axis direction (x/y/z).
        is_key: Whether this header is a key.
        row_guid: FK to Concept.
    """

    __tablename__ = "Header"

    header_id: Mapped[int] = mapped_column(
        "HeaderID", Integer, primary_key=True
    )
    table_id: Mapped[Optional[int]] = mapped_column(
        "TableID", Integer, ForeignKey("Table.TableID")
    )
    direction: Mapped[Optional[str]] = mapped_column(
        "Direction", String(1)
    )
    is_key: Mapped[Optional[bool]] = mapped_column(
        "IsKey", Boolean
    )
    is_attribute: Mapped[Optional[bool]] = mapped_column(
        "IsAttribute", Boolean
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    owner_id: Mapped[Optional[int]] = mapped_column(
        "OwnerID", Integer
    )

    table: Mapped[Optional["Table"]] = relationship(
        back_populates="headers"
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    header_versions: Mapped[
        List["HeaderVersion"]
    ] = relationship(
        back_populates="header",
    )
    column_cells: Mapped[List["Cell"]] = relationship(
        foreign_keys="Cell.column_id",
        back_populates="column_header",
    )
    row_cells: Mapped[List["Cell"]] = relationship(
        foreign_keys="Cell.row_id",
        back_populates="row_header",
    )
    sheet_cells: Mapped[List["Cell"]] = relationship(
        foreign_keys="Cell.sheet_id",
        back_populates="sheet_header",
    )


# ------------------------------------------------------------------
# HeaderVersion
# ------------------------------------------------------------------


class HeaderVersion(Base):
    """Release-versioned snapshot of a Header.

    Attributes:
        header_vid: Primary key.
        header_id: FK to Header.
        code: Version code.
        label: Display label.
        property_id: FK to Property.
        context_id: FK to Context.
        subcategory_vid: FK to SubCategoryVersion.
        key_variable_vid: FK to VariableVersion.
        start_release_id: FK to Release.
        end_release_id: FK to Release.
        row_guid: FK to Concept.
    """

    __tablename__ = "HeaderVersion"
    __table_args__ = (
        UniqueConstraint("HeaderID", "StartReleaseID"),
    )

    header_vid: Mapped[int] = mapped_column(
        "HeaderVID", Integer, primary_key=True
    )
    header_id: Mapped[Optional[int]] = mapped_column(
        "HeaderID",
        Integer,
        ForeignKey("Header.HeaderID"),
    )
    code: Mapped[Optional[str]] = mapped_column(
        "Code", String(10)
    )
    label: Mapped[Optional[str]] = mapped_column(
        "Label", String(500)
    )
    property_id: Mapped[Optional[int]] = mapped_column(
        "PropertyID",
        Integer,
        ForeignKey("Property.PropertyID"),
    )
    context_id: Mapped[Optional[int]] = mapped_column(
        "ContextID",
        Integer,
        ForeignKey("Context.ContextID"),
    )
    subcategory_vid: Mapped[Optional[int]] = mapped_column(
        "SubCategoryVID",
        Integer,
        ForeignKey("SubCategoryVersion.SubCategoryVID"),
    )
    key_variable_vid: Mapped[Optional[int]] = mapped_column(
        "KeyVariableVID",
        Integer,
        ForeignKey("VariableVersion.VariableVID"),
    )
    start_release_id: Mapped[Optional[int]] = mapped_column(
        "StartReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
    )
    end_release_id: Mapped[Optional[int]] = mapped_column(
        "EndReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )

    header: Mapped[Optional["Header"]] = relationship(
        back_populates="header_versions"
    )
    property: Mapped[Optional["Property"]] = relationship(
        foreign_keys=[property_id]
    )
    context: Mapped[Optional["Context"]] = relationship(
        foreign_keys=[context_id]
    )
    subcategory_version: Mapped[
        Optional["SubCategoryVersion"]
    ] = relationship(
        foreign_keys=[subcategory_vid]
    )
    key_variable_version: Mapped[
        Optional["VariableVersion"]
    ] = relationship(
        foreign_keys=[key_variable_vid]
    )
    start_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[start_release_id]
    )
    end_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[end_release_id]
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )


# ------------------------------------------------------------------
# Cell
# ------------------------------------------------------------------


class Cell(Base):
    """Intersection point in a Table (column x row x sheet).

    Attributes:
        cell_id: Primary key.
        table_id: FK to Table.
        column_id: FK to Header (column).
        row_id: FK to Header (row).
        sheet_id: FK to Header (sheet).
        row_guid: FK to Concept.
    """

    __tablename__ = "Cell"
    __table_args__ = (
        UniqueConstraint("ColumnID", "RowID", "SheetID"),
    )

    cell_id: Mapped[int] = mapped_column(
        "CellID", Integer, primary_key=True
    )
    table_id: Mapped[Optional[int]] = mapped_column(
        "TableID", Integer, ForeignKey("Table.TableID")
    )
    column_id: Mapped[Optional[int]] = mapped_column(
        "ColumnID",
        Integer,
        ForeignKey("Header.HeaderID"),
    )
    row_id: Mapped[Optional[int]] = mapped_column(
        "RowID",
        Integer,
        ForeignKey("Header.HeaderID"),
    )
    sheet_id: Mapped[Optional[int]] = mapped_column(
        "SheetID",
        Integer,
        ForeignKey("Header.HeaderID"),
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    owner_id: Mapped[Optional[int]] = mapped_column(
        "OwnerID", Integer
    )

    table: Mapped[Optional["Table"]] = relationship(
        back_populates="cells"
    )
    column_header: Mapped[Optional["Header"]] = relationship(
        foreign_keys=[column_id],
        back_populates="column_cells",
    )
    row_header: Mapped[Optional["Header"]] = relationship(
        foreign_keys=[row_id],
        back_populates="row_cells",
    )
    sheet_header: Mapped[Optional["Header"]] = relationship(
        foreign_keys=[sheet_id],
        back_populates="sheet_cells",
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    table_version_cells: Mapped[
        List["TableVersionCell"]
    ] = relationship(
        back_populates="cell",
    )
    operand_reference_locations: Mapped[
        List["OperandReferenceLocation"]
    ] = relationship(
        back_populates="cell",
    )


# ------------------------------------------------------------------
# TableVersionCell
# ------------------------------------------------------------------


class TableVersionCell(Base):
    """Release-scoped cell configuration within a TableVersion.

    Attributes:
        table_vid: FK to TableVersion (composite PK).
        cell_id: FK to Cell (composite PK).
        cell_code: Cell code string.
        is_nullable: Whether the cell is nullable.
        is_excluded: Whether the cell is excluded.
        is_void: Whether the cell is void.
        sign: Sign indicator.
        variable_vid: FK to VariableVersion.
        row_guid: Row GUID.
    """

    __tablename__ = "TableVersionCell"

    table_vid: Mapped[int] = mapped_column(
        "TableVID",
        Integer,
        ForeignKey("TableVersion.TableVID"),
        primary_key=True,
    )
    cell_id: Mapped[int] = mapped_column(
        "CellID",
        Integer,
        ForeignKey("Cell.CellID"),
        primary_key=True,
    )
    cell_code: Mapped[Optional[str]] = mapped_column(
        "CellCode", String(100)
    )
    is_nullable: Mapped[Optional[bool]] = mapped_column(
        "IsNullable", Boolean
    )
    is_excluded: Mapped[Optional[bool]] = mapped_column(
        "IsExcluded", Boolean
    )
    is_void: Mapped[Optional[bool]] = mapped_column(
        "IsVoid", Boolean
    )
    sign: Mapped[Optional[str]] = mapped_column(
        "Sign", String(8)
    )
    variable_vid: Mapped[Optional[int]] = mapped_column(
        "VariableVID",
        Integer,
        ForeignKey("VariableVersion.VariableVID"),
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID", String(36)
    )

    table_version: Mapped["TableVersion"] = relationship(
        back_populates="table_version_cells"
    )
    cell: Mapped["Cell"] = relationship(
        back_populates="table_version_cells"
    )
    variable_version: Mapped[
        Optional["VariableVersion"]
    ] = relationship(
        foreign_keys=[variable_vid]
    )


# ------------------------------------------------------------------
# TableVersionHeader
# ------------------------------------------------------------------


class TableVersionHeader(Base):
    """Ordered header assignment within a TableVersion.

    Attributes:
        table_vid: FK to TableVersion (composite PK).
        header_id: FK to Header (composite PK).
        header_vid: FK to HeaderVersion.
        parent_header_id: FK to Header (parent).
        parent_first: Whether parent renders first.
        order: Display order.
        is_abstract: Whether the header is abstract.
        is_unique: Whether the header is unique.
        row_guid: Row GUID.
    """

    __tablename__ = "TableVersionHeader"

    table_vid: Mapped[int] = mapped_column(
        "TableVID",
        Integer,
        ForeignKey("TableVersion.TableVID"),
        primary_key=True,
    )
    header_id: Mapped[int] = mapped_column(
        "HeaderID",
        Integer,
        ForeignKey("Header.HeaderID"),
        primary_key=True,
    )
    header_vid: Mapped[Optional[int]] = mapped_column(
        "HeaderVID",
        Integer,
        ForeignKey("HeaderVersion.HeaderVID"),
    )
    parent_header_id: Mapped[Optional[int]] = mapped_column(
        "ParentHeaderID",
        Integer,
        ForeignKey("Header.HeaderID"),
    )
    parent_first: Mapped[Optional[bool]] = mapped_column(
        "ParentFirst", Boolean
    )
    order: Mapped[Optional[int]] = mapped_column(
        "Order", Integer
    )
    is_abstract: Mapped[Optional[bool]] = mapped_column(
        "IsAbstract", Boolean
    )
    is_unique: Mapped[Optional[bool]] = mapped_column(
        "IsUnique", Boolean
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID", String(36)
    )

    table_version: Mapped["TableVersion"] = relationship(
        back_populates="table_version_headers"
    )
    header: Mapped["Header"] = relationship(
        foreign_keys=[header_id]
    )
    header_version: Mapped[
        Optional["HeaderVersion"]
    ] = relationship(
        foreign_keys=[header_vid]
    )
    parent_header: Mapped[Optional["Header"]] = relationship(
        foreign_keys=[parent_header_id]
    )


# ------------------------------------------------------------------
# TableGroup
# ------------------------------------------------------------------


class TableGroup(Base):
    """Logical grouping of tables for navigation.

    Attributes:
        table_group_id: Primary key.
        code: Group code.
        name: Group name.
        description: Group description.
        type: Group type.
        row_guid: FK to Concept.
        start_release_id: FK to Release.
        end_release_id: FK to Release.
        parent_table_group_id: Self-FK for hierarchy.
    """

    __tablename__ = "TableGroup"

    table_group_id: Mapped[int] = mapped_column(
        "TableGroupID", Integer, primary_key=True
    )
    code: Mapped[Optional[str]] = mapped_column(
        "Code", String(255)
    )
    name: Mapped[Optional[str]] = mapped_column(
        "Name", String(255)
    )
    description: Mapped[Optional[str]] = mapped_column(
        "Description", String(2000)
    )
    type: Mapped[Optional[str]] = mapped_column(
        "Type", String(20)
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    start_release_id: Mapped[Optional[int]] = mapped_column(
        "StartReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
    )
    end_release_id: Mapped[Optional[int]] = mapped_column(
        "EndReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
    )
    parent_table_group_id: Mapped[
        Optional[int]
    ] = mapped_column(
        "ParentTableGroupID",
        Integer,
        ForeignKey("TableGroup.TableGroupID"),
    )
    owner_id: Mapped[Optional[int]] = mapped_column(
        "OwnerID", Integer
    )

    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    start_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[start_release_id]
    )
    end_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[end_release_id]
    )
    parent_table_group: Mapped[
        Optional["TableGroup"]
    ] = relationship(
        remote_side=[table_group_id],
        back_populates="child_table_groups",
    )
    child_table_groups: Mapped[
        List["TableGroup"]
    ] = relationship(
        back_populates="parent_table_group",
    )
    table_group_compositions: Mapped[
        List["TableGroupComposition"]
    ] = relationship(
        back_populates="table_group",
    )


# ------------------------------------------------------------------
# TableGroupComposition
# ------------------------------------------------------------------


class TableGroupComposition(Base):
    """Links Tables to TableGroups with ordering.

    Attributes:
        table_group_id: FK to TableGroup (composite PK).
        table_id: FK to Table (composite PK).
        order: Display order.
        start_release_id: FK to Release.
        end_release_id: FK to Release.
        row_guid: Row GUID.
    """

    __tablename__ = "TableGroupComposition"

    table_group_id: Mapped[int] = mapped_column(
        "TableGroupID",
        Integer,
        ForeignKey("TableGroup.TableGroupID"),
        primary_key=True,
    )
    table_id: Mapped[int] = mapped_column(
        "TableID",
        Integer,
        ForeignKey("Table.TableID"),
        primary_key=True,
    )
    order: Mapped[Optional[int]] = mapped_column(
        "Order", Integer
    )
    start_release_id: Mapped[Optional[int]] = mapped_column(
        "StartReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
    )
    end_release_id: Mapped[Optional[int]] = mapped_column(
        "EndReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID", String(36)
    )

    table_group: Mapped["TableGroup"] = relationship(
        back_populates="table_group_compositions"
    )
    table: Mapped["Table"] = relationship(
        back_populates="table_group_compositions"
    )
    start_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[start_release_id]
    )
    end_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[end_release_id]
    )


# ------------------------------------------------------------------
# TableAssociation
# ------------------------------------------------------------------


class TableAssociation(Base):
    """Parent-child relationship between TableVersions.

    Attributes:
        association_id: Primary key.
        child_table_vid: FK to TableVersion (child).
        parent_table_vid: FK to TableVersion (parent).
        name: Association name.
        description: Association description.
        is_identifying: Whether the association is identifying.
        is_subtype: Whether it represents a subtype.
        subtype_discriminator: FK to Header.
        parent_cardinality: Parent cardinality/optionality.
        child_cardinality: Child cardinality/optionality.
        row_guid: FK to Concept.
    """

    __tablename__ = "TableAssociation"

    association_id: Mapped[int] = mapped_column(
        "AssociationID", Integer, primary_key=True
    )
    child_table_vid: Mapped[Optional[int]] = mapped_column(
        "ChildTableVID",
        Integer,
        ForeignKey("TableVersion.TableVID"),
    )
    parent_table_vid: Mapped[Optional[int]] = mapped_column(
        "ParentTableVID",
        Integer,
        ForeignKey("TableVersion.TableVID"),
    )
    name: Mapped[Optional[str]] = mapped_column(
        "Name", String(50)
    )
    description: Mapped[Optional[str]] = mapped_column(
        "Description", String(255)
    )
    is_identifying: Mapped[Optional[bool]] = mapped_column(
        "IsIdentifying", Boolean
    )
    is_subtype: Mapped[Optional[bool]] = mapped_column(
        "IsSubtype", Boolean
    )
    subtype_discriminator: Mapped[
        Optional[int]
    ] = mapped_column(
        "SubtypeDiscriminator",
        Integer,
        ForeignKey("Header.HeaderID"),
    )
    parent_cardinality: Mapped[
        Optional[str]
    ] = mapped_column(
        "ParentCardinalityAndOptionality", String(3)
    )
    child_cardinality: Mapped[
        Optional[str]
    ] = mapped_column(
        "ChildCardinalityAndOptionality", String(3)
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    owner_id: Mapped[Optional[int]] = mapped_column(
        "OwnerID", Integer
    )

    child_table_version: Mapped[
        Optional["TableVersion"]
    ] = relationship(
        foreign_keys=[child_table_vid],
        back_populates="table_associations_as_child",
    )
    parent_table_version: Mapped[
        Optional["TableVersion"]
    ] = relationship(
        foreign_keys=[parent_table_vid],
        back_populates="table_associations_as_parent",
    )
    subtype_discriminator_header: Mapped[
        Optional["Header"]
    ] = relationship(
        foreign_keys=[subtype_discriminator]
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    key_header_mappings: Mapped[
        List["KeyHeaderMapping"]
    ] = relationship(
        back_populates="table_association",
    )


# ------------------------------------------------------------------
# KeyHeaderMapping
# ------------------------------------------------------------------


class KeyHeaderMapping(Base):
    """Maps foreign-key headers to primary-key headers.

    Attributes:
        association_id: FK to TableAssociation (composite PK).
        foreign_key_header_id: FK to Header (composite PK).
        primary_key_header_id: FK to Header.
        row_guid: Row GUID.
    """

    __tablename__ = "KeyHeaderMapping"

    association_id: Mapped[int] = mapped_column(
        "AssociationID",
        Integer,
        ForeignKey("TableAssociation.AssociationID"),
        primary_key=True,
    )
    foreign_key_header_id: Mapped[int] = mapped_column(
        "ForeignKeyHeaderID",
        Integer,
        ForeignKey("Header.HeaderID"),
        primary_key=True,
    )
    primary_key_header_id: Mapped[
        Optional[int]
    ] = mapped_column(
        "PrimaryKeyHeaderID",
        Integer,
        ForeignKey("Header.HeaderID"),
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID", String(36)
    )

    table_association: Mapped[
        "TableAssociation"
    ] = relationship(
        back_populates="key_header_mappings"
    )
    foreign_key_header: Mapped["Header"] = relationship(
        foreign_keys=[foreign_key_header_id]
    )
    primary_key_header: Mapped[
        Optional["Header"]
    ] = relationship(
        foreign_keys=[primary_key_header_id]
    )
