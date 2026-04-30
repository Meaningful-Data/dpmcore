"""ORM models for the DPM Packaging domain.

This module defines the packaging entities that organise DPM
content into frameworks, modules, and their versioned compositions:
Framework, Module, ModuleVersion, ModuleVersionComposition,
ModuleParameters, and OperationCodePrefix.
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
    from dpmcore.orm.operations import OperationScopeComposition
    from dpmcore.orm.rendering import Table, TableVersion
    from dpmcore.orm.variables import (
        CompoundKey,
        VariableCalculation,
        VariableVersion,
    )


# ------------------------------------------------------------------
# Framework
# ------------------------------------------------------------------


class Framework(Base):
    """Regulatory or reporting framework.

    Attributes:
        framework_id: Primary key.
        code: Short framework code.
        name: Human-readable name.
        description: Long description.
        row_guid: FK to Concept.
    """

    __tablename__ = "Framework"

    framework_id: Mapped[int] = mapped_column(
        "FrameworkID", Integer, primary_key=True
    )
    code: Mapped[Optional[str]] = mapped_column("Code", String(255))
    name: Mapped[Optional[str]] = mapped_column("Name", String(255))
    description: Mapped[Optional[str]] = mapped_column(
        "Description", String(255)
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
    modules: Mapped[List["Module"]] = relationship(
        back_populates="framework",
    )
    operation_code_prefixes: Mapped[List["OperationCodePrefix"]] = (
        relationship(
            back_populates="framework",
        )
    )


# ------------------------------------------------------------------
# Module
# ------------------------------------------------------------------


class Module(Base):
    """Logical grouping within a Framework.

    Attributes:
        module_id: Primary key.
        framework_id: FK to Framework.
        row_guid: FK to Concept.
    """

    __tablename__ = "Module"

    module_id: Mapped[int] = mapped_column(
        "ModuleID", Integer, primary_key=True
    )
    framework_id: Mapped[Optional[int]] = mapped_column(
        "FrameworkID",
        Integer,
        ForeignKey("Framework.FrameworkID"),
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    is_document_module: Mapped[Optional[bool]] = mapped_column(
        "isDocumentModule", Boolean
    )
    owner_id: Mapped[Optional[int]] = mapped_column("OwnerID", Integer)

    framework: Mapped[Optional["Framework"]] = relationship(
        back_populates="modules"
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    module_versions: Mapped[List["ModuleVersion"]] = relationship(
        back_populates="module",
    )
    variable_calculations: Mapped[List["VariableCalculation"]] = relationship(
        back_populates="module",
    )


# ------------------------------------------------------------------
# ModuleVersion
# ------------------------------------------------------------------


class ModuleVersion(Base):
    """Release-versioned snapshot of a Module.

    Attributes:
        module_vid: Primary key.
        module_id: FK to Module.
        global_key_id: FK to CompoundKey.
        start_release_id: FK to Release (version start).
        end_release_id: FK to Release (version end).
        code: Short version code.
        name: Human-readable name.
        description: Long description.
        version_number: Semantic version string.
        from_reference_date: Validity start date.
        to_reference_date: Validity end date.
        row_guid: FK to Concept.
    """

    __tablename__ = "ModuleVersion"
    __table_args__ = (UniqueConstraint("ModuleID", "StartReleaseID"),)

    module_vid: Mapped[int] = mapped_column(
        "ModuleVID", Integer, primary_key=True
    )
    module_id: Mapped[Optional[int]] = mapped_column(
        "ModuleID",
        Integer,
        ForeignKey("Module.ModuleID"),
    )
    global_key_id: Mapped[Optional[int]] = mapped_column(
        "GlobalKeyID",
        Integer,
        ForeignKey("CompoundKey.KeyID"),
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
    code: Mapped[Optional[str]] = mapped_column("Code", String(30))
    name: Mapped[Optional[str]] = mapped_column("Name", String(100))
    description: Mapped[Optional[str]] = mapped_column(
        "Description", String(255)
    )
    version_number: Mapped[Optional[str]] = mapped_column(
        "VersionNumber", String(20)
    )
    from_reference_date: Mapped[Optional[date]] = mapped_column(
        "FromReferenceDate", Date
    )
    to_reference_date: Mapped[Optional[date]] = mapped_column(
        "ToReferenceDate", Date
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    is_reported: Mapped[Optional[bool]] = mapped_column("IsReported", Boolean)
    is_calculated: Mapped[Optional[bool]] = mapped_column(
        "IsCalculated", Boolean
    )

    module: Mapped[Optional["Module"]] = relationship(
        back_populates="module_versions"
    )
    global_key: Mapped[Optional["CompoundKey"]] = relationship(
        foreign_keys=[global_key_id]
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
    module_version_compositions: Mapped[List["ModuleVersionComposition"]] = (
        relationship(
            back_populates="module_version",
        )
    )
    operation_scope_compositions: Mapped[List["OperationScopeComposition"]] = (
        relationship(
            back_populates="module_version",
        )
    )
    module_parameters: Mapped[List["ModuleParameters"]] = relationship(
        back_populates="module_version",
    )


# ------------------------------------------------------------------
# ModuleVersionComposition
# ------------------------------------------------------------------


class ModuleVersionComposition(Base):
    """Links a ModuleVersion to its constituent Tables.

    Attributes:
        module_vid: FK to ModuleVersion (composite PK).
        table_id: FK to Table (composite PK).
        table_vid: FK to TableVersion.
        order: Display/processing order.
        row_guid: Row GUID.
    """

    __tablename__ = "ModuleVersionComposition"

    module_vid: Mapped[int] = mapped_column(
        "ModuleVID",
        Integer,
        ForeignKey("ModuleVersion.ModuleVID"),
        primary_key=True,
    )
    table_id: Mapped[int] = mapped_column(
        "TableID",
        Integer,
        ForeignKey("Table.TableID"),
        primary_key=True,
    )
    table_vid: Mapped[Optional[int]] = mapped_column(
        "TableVID",
        Integer,
        ForeignKey("TableVersion.TableVID"),
    )
    order: Mapped[Optional[int]] = mapped_column("Order", Integer)
    row_guid: Mapped[Optional[str]] = mapped_column("RowGUID", String(36))

    module_version: Mapped["ModuleVersion"] = relationship(
        back_populates="module_version_compositions"
    )
    table: Mapped["Table"] = relationship(foreign_keys=[table_id])
    table_version: Mapped[Optional["TableVersion"]] = relationship(
        foreign_keys=[table_vid]
    )


# ------------------------------------------------------------------
# ModuleParameters
# ------------------------------------------------------------------


class ModuleParameters(Base):
    """Parameter variable bound to a ModuleVersion.

    Attributes:
        module_vid: FK to ModuleVersion (composite PK).
        variable_vid: FK to VariableVersion (composite PK).
        row_guid: Row GUID.
    """

    __tablename__ = "ModuleParameters"

    module_vid: Mapped[int] = mapped_column(
        "ModuleVID",
        Integer,
        ForeignKey("ModuleVersion.ModuleVID"),
        primary_key=True,
    )
    variable_vid: Mapped[int] = mapped_column(
        "VariableVID",
        Integer,
        ForeignKey("VariableVersion.VariableVID"),
        primary_key=True,
    )
    row_guid: Mapped[Optional[str]] = mapped_column("RowGUID", String(36))

    module_version: Mapped["ModuleVersion"] = relationship(
        back_populates="module_parameters"
    )
    variable_version: Mapped["VariableVersion"] = relationship(
        foreign_keys=[variable_vid]
    )


# ------------------------------------------------------------------
# OperationCodePrefix
# ------------------------------------------------------------------


class OperationCodePrefix(Base):
    """Operation code prefix scoped to a Framework.

    Attributes:
        operation_code_prefix_id: Primary key.
        code: Unique prefix code.
        list_name: List name descriptor.
        framework_id: FK to Framework.
    """

    __tablename__ = "OperationCodePrefix"

    operation_code_prefix_id: Mapped[int] = mapped_column(
        "OperationCodePrefixID", Integer, primary_key=True
    )
    code: Mapped[Optional[str]] = mapped_column(
        "Code", String(20), unique=True
    )
    list_name: Mapped[Optional[str]] = mapped_column("ListName", String(20))
    framework_id: Mapped[Optional[int]] = mapped_column(
        "FrameworkID",
        Integer,
        ForeignKey("Framework.FrameworkID"),
    )

    framework: Mapped[Optional["Framework"]] = relationship(
        back_populates="operation_code_prefixes"
    )
