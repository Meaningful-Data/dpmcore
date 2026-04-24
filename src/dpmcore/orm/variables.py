"""ORM models for DPM Variables domain.

This module defines Variable, VariableVersion, VariableCalculation,
CompoundKey, and KeyComposition models.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
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
    from dpmcore.orm.operations import OperandReference, OperationVersion
    from dpmcore.orm.packaging import Module, ModuleParameters, ModuleVersion
    from dpmcore.orm.rendering import (
        HeaderVersion,
        TableVersion,
        TableVersionCell,
    )


# ------------------------------------------------------------------
# Variable
# ------------------------------------------------------------------


class Variable(Base):
    """Core variable entity.

    Attributes:
        variable_id: Primary key.
        type: Variable type descriptor.
        row_guid: FK to Concept.
    """

    __tablename__ = "Variable"

    variable_id: Mapped[int] = mapped_column(
        "VariableID", Integer, primary_key=True
    )
    type: Mapped[Optional[str]] = mapped_column("Type", String(20))
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    owner_id: Mapped[Optional[int]] = mapped_column("OwnerID", Integer)

    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    variable_versions: Mapped[List["VariableVersion"]] = relationship(
        back_populates="variable",
    )
    variable_calculations: Mapped[List["VariableCalculation"]] = relationship(
        back_populates="variable",
    )
    operand_references: Mapped[List["OperandReference"]] = relationship(
        back_populates="variable",
    )


# ------------------------------------------------------------------
# VariableVersion
# ------------------------------------------------------------------


class VariableVersion(Base):
    """Versioned snapshot of a Variable.

    Attributes:
        variable_vid: Primary key.
        variable_id: FK to Variable.
        property_id: FK to Property.
        subcategory_vid: FK to SubCategoryVersion.
        context_id: FK to Context.
        key_id: FK to CompoundKey.
        is_multi_valued: Multi-value flag.
        code: Short code.
        name: Display name.
        start_release_id: FK to starting Release.
        end_release_id: FK to ending Release.
        row_guid: FK to Concept.
    """

    __tablename__ = "VariableVersion"
    __table_args__ = (UniqueConstraint("VariableID", "StartReleaseID"),)

    variable_vid: Mapped[int] = mapped_column(
        "VariableVID", Integer, primary_key=True
    )
    variable_id: Mapped[Optional[int]] = mapped_column(
        "VariableID",
        Integer,
        ForeignKey("Variable.VariableID"),
    )
    property_id: Mapped[Optional[int]] = mapped_column(
        "PropertyID",
        Integer,
        ForeignKey("Property.PropertyID"),
    )
    subcategory_vid: Mapped[Optional[int]] = mapped_column(
        "SubCategoryVID",
        Integer,
        ForeignKey("SubCategoryVersion.SubCategoryVID"),
    )
    context_id: Mapped[Optional[int]] = mapped_column(
        "ContextID",
        Integer,
        ForeignKey("Context.ContextID"),
    )
    key_id: Mapped[Optional[int]] = mapped_column(
        "KeyID",
        Integer,
        ForeignKey("CompoundKey.KeyID"),
    )
    is_multi_valued: Mapped[Optional[bool]] = mapped_column(
        "IsMultiValued", Boolean
    )
    code: Mapped[Optional[str]] = mapped_column("Code", String(20))
    name: Mapped[Optional[str]] = mapped_column("Name", String(50))
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

    variable: Mapped[Optional["Variable"]] = relationship(
        back_populates="variable_versions"
    )
    property: Mapped[Optional["Property"]] = relationship(
        foreign_keys=[property_id]
    )
    subcategory_version: Mapped[Optional["SubCategoryVersion"]] = relationship(
        foreign_keys=[subcategory_vid]
    )
    context: Mapped[Optional["Context"]] = relationship(
        foreign_keys=[context_id]
    )
    key: Mapped[Optional["CompoundKey"]] = relationship(foreign_keys=[key_id])
    start_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[start_release_id]
    )
    end_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[end_release_id]
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    key_compositions: Mapped[List["KeyComposition"]] = relationship(
        back_populates="variable_version",
    )
    module_parameters: Mapped[List["ModuleParameters"]] = relationship(
        back_populates="variable_version",
    )
    table_version_cells: Mapped[List["TableVersionCell"]] = relationship(
        back_populates="variable_version",
    )
    header_versions: Mapped[List["HeaderVersion"]] = relationship(
        back_populates="key_variable_version",
    )


# ------------------------------------------------------------------
# VariableCalculation
# ------------------------------------------------------------------


class VariableCalculation(Base):
    """Link between a Module, Variable, and OperationVersion.

    Attributes:
        module_id: FK to Module (composite PK).
        variable_id: FK to Variable (composite PK).
        operation_vid: FK to OperationVersion (composite PK).
        from_reference_date: Start of reference period.
        to_reference_date: End of reference period.
        row_guid: Row GUID.
    """

    __tablename__ = "VariableCalculation"

    module_id: Mapped[int] = mapped_column(
        "ModuleID",
        Integer,
        ForeignKey("Module.ModuleID"),
        primary_key=True,
    )
    variable_id: Mapped[int] = mapped_column(
        "VariableID",
        Integer,
        ForeignKey("Variable.VariableID"),
        primary_key=True,
    )
    operation_vid: Mapped[int] = mapped_column(
        "OperationVID",
        Integer,
        ForeignKey("OperationVersion.OperationVID"),
        primary_key=True,
    )
    from_reference_date: Mapped[Optional[date]] = mapped_column(
        "FromReferenceDate", Date
    )
    to_reference_date: Mapped[Optional[date]] = mapped_column(
        "ToReferenceDate", Date
    )
    row_guid: Mapped[Optional[str]] = mapped_column("RowGUID", String(36))

    module: Mapped["Module"] = relationship(
        back_populates="variable_calculations"
    )
    variable: Mapped["Variable"] = relationship(
        back_populates="variable_calculations"
    )
    operation_version: Mapped["OperationVersion"] = relationship(
        back_populates="variable_calculations"
    )


# ------------------------------------------------------------------
# CompoundKey
# ------------------------------------------------------------------


class CompoundKey(Base):
    """Composite key definition for Variables.

    Attributes:
        key_id: Primary key.
        signature: Unique key signature string.
        row_guid: FK to Concept.
    """

    __tablename__ = "CompoundKey"

    key_id: Mapped[int] = mapped_column("KeyID", Integer, primary_key=True)
    signature: Mapped[Optional[str]] = mapped_column(
        "Signature", String(255), unique=True
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    owner_id: Mapped[Optional[int]] = mapped_column("OwnerID", Integer)

    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    key_compositions: Mapped[List["KeyComposition"]] = relationship(
        back_populates="compound_key",
    )
    module_versions: Mapped[List["ModuleVersion"]] = relationship(
        back_populates="global_key",
    )
    table_versions: Mapped[List["TableVersion"]] = relationship(
        back_populates="key",
    )


# ------------------------------------------------------------------
# KeyComposition
# ------------------------------------------------------------------


class KeyComposition(Base):
    """Association between CompoundKey and VariableVersion.

    Attributes:
        key_id: FK to CompoundKey (composite PK).
        variable_vid: FK to VariableVersion (composite PK).
        row_guid: Row GUID.
    """

    __tablename__ = "KeyComposition"

    key_id: Mapped[int] = mapped_column(
        "KeyID",
        Integer,
        ForeignKey("CompoundKey.KeyID"),
        primary_key=True,
    )
    variable_vid: Mapped[int] = mapped_column(
        "VariableVID",
        Integer,
        ForeignKey("VariableVersion.VariableVID"),
        primary_key=True,
    )
    row_guid: Mapped[Optional[str]] = mapped_column("RowGUID", String(36))

    compound_key: Mapped["CompoundKey"] = relationship(
        back_populates="key_compositions"
    )
    variable_version: Mapped["VariableVersion"] = relationship(
        back_populates="key_compositions"
    )
