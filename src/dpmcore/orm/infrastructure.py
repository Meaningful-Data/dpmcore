"""ORM models for DPM infrastructure entities.

This module defines foundational models that other domain modules
depend on: Concept, Organisation, Language, User, Role, DataType,
DpmClass, DpmAttribute, Translation, Changelog, Document,
DocumentVersion, Subdivision, and SubdivisionType.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dpmcore.orm.base import Base

if TYPE_CHECKING:
    from dpmcore.orm.glossary import ContextComposition


# ------------------------------------------------------------------
# Concept & ConceptRelation
# ------------------------------------------------------------------


class Concept(Base):
    """Universal identity object — every DPM entity has a Concept.

    Attributes:
        concept_guid: UUID-format primary key.
        class_id: Foreign key to DpmClass.
        owner_id: Foreign key to Organisation.
    """

    __tablename__ = "Concept"

    concept_guid: Mapped[str] = mapped_column(
        "ConceptGUID", String(36), primary_key=True
    )
    class_id: Mapped[Optional[int]] = mapped_column(
        "ClassID", Integer, ForeignKey("DPMClass.ClassID")
    )
    owner_id: Mapped[Optional[int]] = mapped_column(
        "OwnerID", Integer, ForeignKey("Organisation.OrgID")
    )

    dpm_class: Mapped[Optional["DpmClass"]] = relationship(
        foreign_keys=[class_id]
    )
    owner: Mapped[Optional["Organisation"]] = relationship(
        foreign_keys=[owner_id],
        back_populates="concepts_owned",
    )
    related_concepts: Mapped[List["RelatedConcept"]] = relationship(
        back_populates="concept",
    )
    context_compositions: Mapped[List["ContextComposition"]] = relationship(
        back_populates="concept",
    )


class ConceptRelation(Base):
    """Relation between two Concepts.

    Attributes:
        concept_relation_id: Primary key.
        type: Relation type descriptor.
        row_guid: Row GUID.
    """

    __tablename__ = "ConceptRelation"

    concept_relation_id: Mapped[int] = mapped_column(
        "ConceptRelationID", Integer, primary_key=True
    )
    type: Mapped[Optional[str]] = mapped_column("Type", String(50))
    row_guid: Mapped[Optional[str]] = mapped_column("RowGUID", String(36))

    related_concepts: Mapped[List["RelatedConcept"]] = relationship(
        back_populates="concept_relation",
    )


class RelatedConcept(Base):
    """Association between a Concept and a ConceptRelation.

    Attributes:
        concept_guid: FK to Concept (composite PK).
        concept_relation_id: FK to ConceptRelation (composite PK).
        is_related_concept: Direction flag.
        row_guid: Row GUID.
    """

    __tablename__ = "RelatedConcept"

    concept_guid: Mapped[str] = mapped_column(
        "ConceptGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
        primary_key=True,
    )
    concept_relation_id: Mapped[int] = mapped_column(
        "ConceptRelationID",
        Integer,
        ForeignKey("ConceptRelation.ConceptRelationID"),
        primary_key=True,
    )
    is_related_concept: Mapped[Optional[bool]] = mapped_column(
        "IsRelatedConcept", Boolean
    )
    row_guid: Mapped[Optional[str]] = mapped_column("RowGUID", String(36))

    concept: Mapped["Concept"] = relationship(
        back_populates="related_concepts"
    )
    concept_relation: Mapped["ConceptRelation"] = relationship(
        back_populates="related_concepts"
    )


# ------------------------------------------------------------------
# Organisation
# ------------------------------------------------------------------


class Organisation(Base):
    """Data owner / maintainer organisation.

    Attributes:
        org_id: Primary key.
        name: Organisation name (unique).
        acronym: Short form.
        id_prefix: Numeric prefix (unique).
        row_guid: FK to Concept.
    """

    __tablename__ = "Organisation"

    org_id: Mapped[int] = mapped_column("OrgID", Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(
        "Name", String(200), unique=True
    )
    acronym: Mapped[Optional[str]] = mapped_column("Acronym", String(20))
    id_prefix: Mapped[Optional[int]] = mapped_column(
        "IDPrefix", Integer, unique=True
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey(
            "Concept.ConceptGUID",
            use_alter=True,
            name="fk_org_concept",
        ),
    )

    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    concepts_owned: Mapped[List["Concept"]] = relationship(
        foreign_keys="Concept.owner_id",
        back_populates="owner",
    )
    documents: Mapped[List["Document"]] = relationship(
        back_populates="organisation",
    )
    users: Mapped[List["User"]] = relationship(
        back_populates="organisation",
    )
    translations: Mapped[List["Translation"]] = relationship(
        back_populates="translator",
    )


# ------------------------------------------------------------------
# Language
# ------------------------------------------------------------------


class Language(Base):
    """Language code reference.

    Attributes:
        language_code: Primary key (integer language code).
        name: Human-readable language name.
    """

    __tablename__ = "Language"

    language_code: Mapped[int] = mapped_column(
        "LanguageCode", Integer, primary_key=True
    )
    name: Mapped[Optional[str]] = mapped_column("Name", String(20))

    translations: Mapped[List["Translation"]] = relationship(
        back_populates="language",
    )


# ------------------------------------------------------------------
# User & Role
# ------------------------------------------------------------------


class User(Base):
    """User account.

    Attributes:
        user_id: Primary key.
        org_id: FK to Organisation.
        name: User display name.
    """

    __tablename__ = "User"

    user_id: Mapped[int] = mapped_column("UserID", Integer, primary_key=True)
    org_id: Mapped[Optional[int]] = mapped_column(
        "OrgID", Integer, ForeignKey("Organisation.OrgID")
    )
    name: Mapped[Optional[str]] = mapped_column("Name", String(50))

    organisation: Mapped[Optional["Organisation"]] = relationship(
        back_populates="users"
    )
    user_roles: Mapped[List["UserRole"]] = relationship(
        back_populates="user",
    )


class Role(Base):
    """Access role.

    Attributes:
        role_id: Primary key.
        name: Role name.
    """

    __tablename__ = "Role"

    role_id: Mapped[int] = mapped_column("RoleID", Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column("Name", String(50))

    user_roles: Mapped[List["UserRole"]] = relationship(
        back_populates="role",
    )


class UserRole(Base):
    """Many-to-many link between User and Role.

    Attributes:
        user_id: FK to User (composite PK).
        role_id: FK to Role (composite PK).
    """

    __tablename__ = "UserRole"

    user_id: Mapped[int] = mapped_column(
        "UserID",
        Integer,
        ForeignKey("User.UserID"),
        primary_key=True,
    )
    role_id: Mapped[int] = mapped_column(
        "RoleID",
        Integer,
        ForeignKey("Role.RoleID"),
        primary_key=True,
    )

    user: Mapped["User"] = relationship(back_populates="user_roles")
    role: Mapped["Role"] = relationship(back_populates="user_roles")


# ------------------------------------------------------------------
# DataType
# ------------------------------------------------------------------


class DataType(Base):
    """Data type definition.

    Attributes:
        data_type_id: Primary key.
        code: Unique code (e.g. 'String', 'Integer').
        name: Unique human-readable name.
        parent_data_type_id: Self-FK for type hierarchy.
        is_active: Whether currently in use.
    """

    __tablename__ = "DataType"

    data_type_id: Mapped[int] = mapped_column(
        "DataTypeID", Integer, primary_key=True
    )
    code: Mapped[Optional[str]] = mapped_column(
        "Code", String(20), unique=True
    )
    name: Mapped[Optional[str]] = mapped_column(
        "Name", String(50), unique=True
    )
    parent_data_type_id: Mapped[Optional[int]] = mapped_column(
        "ParentDataTypeID",
        Integer,
        ForeignKey("DataType.DataTypeID"),
    )
    is_active: Mapped[Optional[bool]] = mapped_column("IsActive", Boolean)

    parent_datatype: Mapped[Optional["DataType"]] = relationship(
        remote_side=[data_type_id],
        back_populates="child_datatypes",
    )
    child_datatypes: Mapped[List["DataType"]] = relationship(
        back_populates="parent_datatype",
    )
    properties: Mapped[List["Property"]] = relationship(  # type: ignore[name-defined]
        back_populates="datatype",
    )


# ------------------------------------------------------------------
# DpmClass & DpmAttribute
# ------------------------------------------------------------------


class DpmClass(Base):
    """DPM metamodel class definition.

    Attributes:
        class_id: Primary key.
        name: Class name.
        type: Class type.
        owner_class_id: Self-FK for class hierarchy.
        has_references: Whether this class supports references.
    """

    __tablename__ = "DPMClass"

    class_id: Mapped[int] = mapped_column("ClassID", Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column("Name", String(50))
    type: Mapped[Optional[str]] = mapped_column("Type", String(20))
    owner_class_id: Mapped[Optional[int]] = mapped_column(
        "OwnerClassID", Integer, ForeignKey("DPMClass.ClassID")
    )
    has_references: Mapped[Optional[bool]] = mapped_column(
        "HasReferences", Boolean
    )

    owner_class: Mapped[Optional["DpmClass"]] = relationship(
        remote_side=[class_id],
        back_populates="owned_classes",
    )
    owned_classes: Mapped[List["DpmClass"]] = relationship(
        back_populates="owner_class",
    )
    concepts: Mapped[List["Concept"]] = relationship(
        back_populates="dpm_class",
    )
    dpm_attributes: Mapped[List["DpmAttribute"]] = relationship(
        back_populates="dpm_class",
    )
    changelogs: Mapped[List["Changelog"]] = relationship(
        back_populates="dpm_class",
    )


class DpmAttribute(Base):
    """Attribute of a DpmClass.

    Attributes:
        attribute_id: Primary key.
        class_id: FK to DpmClass.
        name: Attribute name.
        has_translations: Whether translations exist.
    """

    __tablename__ = "DPMAttribute"

    attribute_id: Mapped[int] = mapped_column(
        "AttributeID", Integer, primary_key=True
    )
    class_id: Mapped[Optional[int]] = mapped_column(
        "ClassID", Integer, ForeignKey("DPMClass.ClassID")
    )
    name: Mapped[Optional[str]] = mapped_column("Name", String(20))
    has_translations: Mapped[Optional[bool]] = mapped_column(
        "HasTranslations", Boolean
    )

    dpm_class: Mapped[Optional["DpmClass"]] = relationship(
        back_populates="dpm_attributes"
    )
    changelog_attributes: Mapped[List["ChangelogAttribute"]] = relationship(
        back_populates="dpm_attribute",
    )
    translations: Mapped[List["Translation"]] = relationship(
        back_populates="dpm_attribute",
    )


# ------------------------------------------------------------------
# Translation
# ------------------------------------------------------------------


class Translation(Base):
    """Multilingual text translation.

    Attributes:
        concept_guid: FK to Concept (composite PK).
        attribute_id: FK to DpmAttribute (composite PK).
        translator_id: FK to Organisation (composite PK).
        language_code: FK to Language (composite PK).
        translation: The translated text.
        row_guid: Row GUID.
    """

    __tablename__ = "Translation"

    concept_guid: Mapped[str] = mapped_column(
        "ConceptGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
        primary_key=True,
    )
    attribute_id: Mapped[int] = mapped_column(
        "AttributeID",
        Integer,
        ForeignKey("DPMAttribute.AttributeID"),
        primary_key=True,
    )
    translator_id: Mapped[int] = mapped_column(
        "TranslatorID",
        Integer,
        ForeignKey("Organisation.OrgID"),
        primary_key=True,
    )
    language_code: Mapped[int] = mapped_column(
        "LanguageCode",
        Integer,
        ForeignKey("Language.LanguageCode"),
        primary_key=True,
    )
    translation: Mapped[Optional[str]] = mapped_column("Translation", Text)
    row_guid: Mapped[Optional[str]] = mapped_column("RowGUID", String(36))

    concept: Mapped["Concept"] = relationship(foreign_keys=[concept_guid])
    dpm_attribute: Mapped["DpmAttribute"] = relationship(
        back_populates="translations"
    )
    translator: Mapped["Organisation"] = relationship(
        foreign_keys=[translator_id],
        back_populates="translations",
    )
    language: Mapped["Language"] = relationship(back_populates="translations")


# ------------------------------------------------------------------
# Changelog
# ------------------------------------------------------------------


class Changelog(Base):
    """Change tracking entry.

    Attributes:
        row_guid: Concept GUID (composite PK).
        class_id: FK to DpmClass (composite PK).
        timestamp: Change timestamp (composite PK).
        change_type: Type of change.
        status: Change status.
        user_email: Email of the user who made the change.
        release_id: FK to Release.
        entity_id: Identifier of the changed entity.
        entity_code: Code of the changed entity.
        action_id: Action identifier (links to ChangelogAttribute).
    """

    __tablename__ = "ChangeLog"

    row_guid: Mapped[str] = mapped_column(
        "RowGUID", String(36), primary_key=True
    )
    class_id: Mapped[int] = mapped_column(
        "ClassID",
        Integer,
        ForeignKey("DPMClass.ClassID"),
        primary_key=True,
    )
    timestamp: Mapped[int] = mapped_column(
        "Timestamp", Integer, primary_key=True
    )
    change_type: Mapped[Optional[str]] = mapped_column(
        "ChangeType", String(255)
    )
    status: Mapped[Optional[str]] = mapped_column("Status", String(1))
    user_email: Mapped[Optional[str]] = mapped_column("UserEmail", String(255))
    release_id: Mapped[Optional[int]] = mapped_column(
        "ReleaseID", Integer, ForeignKey("Release.ReleaseID")
    )
    entity_id: Mapped[Optional[int]] = mapped_column("EntityID", Integer)
    entity_code: Mapped[Optional[str]] = mapped_column(
        "EntityCode", String(255)
    )
    action_id: Mapped[int] = mapped_column("ActionID", Integer)

    dpm_class: Mapped[Optional["DpmClass"]] = relationship(
        foreign_keys=[class_id]
    )
    release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[release_id]
    )
    changelog_attributes: Mapped[List["ChangelogAttribute"]] = relationship(
        primaryjoin="Changelog.action_id == foreign(ChangelogAttribute.action_id)",
        back_populates="changelog",
    )


# ------------------------------------------------------------------
# ChangelogAttribute
# ------------------------------------------------------------------


class ChangelogAttribute(Base):
    """Attribute-level detail for a Changelog action.

    Attributes:
        changelog_attribute_id: Primary key.
        action_id: Action identifier linking to Changelog.
        attribute_id: FK to DpmAttribute.
        old_value: Previous value.
        new_value: Updated value.
    """

    __tablename__ = "ChangeLogAttribute"

    changelog_attribute_id: Mapped[int] = mapped_column(
        "ChangeLogAttributeID", Integer, primary_key=True
    )
    action_id: Mapped[int] = mapped_column("ActionID", Integer)
    attribute_id: Mapped[Optional[int]] = mapped_column(
        "AttributeID",
        Integer,
        ForeignKey("DPMAttribute.AttributeID"),
    )
    old_value: Mapped[Optional[str]] = mapped_column("OldValue", String(255))
    new_value: Mapped[Optional[str]] = mapped_column("NewValue", String(255))

    dpm_attribute: Mapped[Optional["DpmAttribute"]] = relationship(
        foreign_keys=[attribute_id]
    )
    changelog: Mapped[Optional["Changelog"]] = relationship(
        foreign_keys=[action_id],
        primaryjoin="ChangelogAttribute.action_id == Changelog.action_id",
        back_populates="changelog_attributes",
    )


# ------------------------------------------------------------------
# Document & DocumentVersion
# ------------------------------------------------------------------


class Document(Base):
    """Supporting documentation.

    Attributes:
        document_id: Primary key.
        name: Document name.
        code: Document code.
        type: Document type.
        org_id: FK to Organisation.
        row_guid: FK to Concept.
    """

    __tablename__ = "Document"

    document_id: Mapped[int] = mapped_column(
        "DocumentID", Integer, primary_key=True
    )
    name: Mapped[Optional[str]] = mapped_column("Name", String(50))
    code: Mapped[Optional[str]] = mapped_column("Code", String(20))
    type: Mapped[Optional[str]] = mapped_column("Type", String(255))
    org_id: Mapped[Optional[int]] = mapped_column(
        "OrgID", Integer, ForeignKey("Organisation.OrgID")
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )

    organisation: Mapped[Optional["Organisation"]] = relationship(
        foreign_keys=[org_id]
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    document_versions: Mapped[List["DocumentVersion"]] = relationship(
        back_populates="document",
    )


class DocumentVersion(Base):
    """Versioned snapshot of a Document.

    Attributes:
        document_vid: Primary key.
        document_id: FK to Document.
        code: Version code.
        version: Version string.
        publication_date: Publication date.
        row_guid: FK to Concept.
    """

    __tablename__ = "DocumentVersion"
    __table_args__ = (UniqueConstraint("DocumentID", "PublicationDate"),)

    document_vid: Mapped[int] = mapped_column(
        "DocumentVID", Integer, primary_key=True
    )
    document_id: Mapped[Optional[int]] = mapped_column(
        "DocumentID", Integer, ForeignKey("Document.DocumentID")
    )
    code: Mapped[Optional[str]] = mapped_column("Code", String(20))
    version: Mapped[Optional[str]] = mapped_column("Version", String(20))
    publication_date: Mapped[Optional[date]] = mapped_column(
        "PublicationDate", Date
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )

    document: Mapped[Optional["Document"]] = relationship(
        back_populates="document_versions"
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    subdivisions: Mapped[List["Subdivision"]] = relationship(
        back_populates="document_version",
    )


# ------------------------------------------------------------------
# Subdivision & SubdivisionType
# ------------------------------------------------------------------


class Subdivision(Base):
    """Geographic or structural subdivision.

    Attributes:
        subdivision_id: Primary key.
        document_vid: FK to DocumentVersion.
        subdivision_type_id: FK to SubdivisionType.
        number: Subdivision number.
        parent_subdivision_id: Self-FK for hierarchy.
        structure_path: Hierarchical path string.
        text_excerpt: Excerpt text.
        row_guid: FK to Concept.
    """

    __tablename__ = "Subdivision"

    subdivision_id: Mapped[int] = mapped_column(
        "SubdivisionID", Integer, primary_key=True
    )
    document_vid: Mapped[Optional[int]] = mapped_column(
        "DocumentVID",
        Integer,
        ForeignKey("DocumentVersion.DocumentVID"),
    )
    subdivision_type_id: Mapped[Optional[int]] = mapped_column(
        "SubdivisionTypeID",
        Integer,
        ForeignKey("SubdivisionType.SubdivisionTypeID"),
    )
    number: Mapped[Optional[str]] = mapped_column("Number", String(20))
    parent_subdivision_id: Mapped[Optional[int]] = mapped_column(
        "ParentSubdivisionID",
        Integer,
        ForeignKey("Subdivision.SubdivisionID"),
    )
    structure_path: Mapped[Optional[str]] = mapped_column(
        "StructurePath", String(255)
    )
    text_excerpt: Mapped[Optional[str]] = mapped_column("TextExcerpt", Text)
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    owner_id: Mapped[Optional[int]] = mapped_column("OwnerID", Integer)

    document_version: Mapped[Optional["DocumentVersion"]] = relationship(
        back_populates="subdivisions"
    )
    subdivision_type: Mapped[Optional["SubdivisionType"]] = relationship(
        back_populates="subdivisions"
    )
    parent_subdivision: Mapped[Optional["Subdivision"]] = relationship(
        remote_side=[subdivision_id],
        back_populates="child_subdivisions",
    )
    child_subdivisions: Mapped[List["Subdivision"]] = relationship(
        back_populates="parent_subdivision",
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    references: Mapped[List["Reference"]] = relationship(
        back_populates="subdivision",
    )


class SubdivisionType(Base):
    """Subdivision type definition.

    Attributes:
        subdivision_type_id: Primary key.
        name: Type name.
        description: Type description.
    """

    __tablename__ = "SubdivisionType"

    subdivision_type_id: Mapped[int] = mapped_column(
        "SubdivisionTypeID", Integer, primary_key=True
    )
    name: Mapped[Optional[str]] = mapped_column("Name", String(50))
    description: Mapped[Optional[str]] = mapped_column(
        "Description", String(255)
    )

    subdivisions: Mapped[List["Subdivision"]] = relationship(
        back_populates="subdivision_type",
    )


# ------------------------------------------------------------------
# Reference
# ------------------------------------------------------------------


class Reference(Base):
    """Link between a Subdivision and a Concept.

    Attributes:
        subdivision_id: FK to Subdivision (composite PK).
        concept_guid: FK to Concept (composite PK).
        row_guid: Row GUID.
    """

    __tablename__ = "Reference"

    subdivision_id: Mapped[int] = mapped_column(
        "SubdivisionID",
        Integer,
        ForeignKey("Subdivision.SubdivisionID"),
        primary_key=True,
    )
    concept_guid: Mapped[str] = mapped_column(
        "ConceptGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
        primary_key=True,
    )
    row_guid: Mapped[Optional[str]] = mapped_column("RowGUID", String(36))

    subdivision: Mapped["Subdivision"] = relationship(
        back_populates="references"
    )
    concept: Mapped["Concept"] = relationship(foreign_keys=[concept_guid])


# ------------------------------------------------------------------
# Release (from packaging, but needed here for FK targets)
# ------------------------------------------------------------------


class Release(Base):
    """Publication milestone.

    Attributes:
        release_id: Primary key.
        code: Release code.
        date: Release date.
        description: Release description.
        status: Release status.
        is_current: Whether this is the active release.
        row_guid: FK to Concept.
        latest_variable_gen_time: Last variable generation timestamp.
    """

    __tablename__ = "Release"

    release_id: Mapped[int] = mapped_column(
        "ReleaseID", Integer, primary_key=True
    )
    code: Mapped[Optional[str]] = mapped_column("Code", String(20))
    date: Mapped[Optional[date]] = mapped_column("Date", Date)
    description: Mapped[Optional[str]] = mapped_column(
        "Description", String(255)
    )
    status: Mapped[Optional[str]] = mapped_column("Status", String(50))
    is_current: Mapped[Optional[bool]] = mapped_column("IsCurrent", Boolean)
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    error_date: Mapped[Optional[datetime]] = mapped_column(
        "ErrorDate", DateTime
    )
    type: Mapped[Optional[str]] = mapped_column("Type", String(20))
    error: Mapped[Optional[str]] = mapped_column("Error", String(4000))
    owner_id: Mapped[Optional[int]] = mapped_column("OwnerID", Integer)

    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    changelogs: Mapped[List["Changelog"]] = relationship(
        back_populates="release",
    )
    variable_generations: Mapped[List["VariableGeneration"]] = relationship(
        back_populates="release",
    )


# ------------------------------------------------------------------
# VariableGeneration (needs Release FK, kept here)
# ------------------------------------------------------------------


class VariableGeneration(Base):
    """Batch variable generation job.

    Attributes:
        variable_generation_id: Primary key.
        start_date: Job start time.
        end_date: Job end time.
        status: Job status.
        release_id: FK to Release.
        error: Error message (up to 4000 chars).
    """

    __tablename__ = "VariableGeneration"

    variable_generation_id: Mapped[int] = mapped_column(
        "VariableGenerationID", Integer, primary_key=True
    )
    start_date: Mapped[Optional[datetime]] = mapped_column(
        "StartDate", DateTime
    )
    end_date: Mapped[Optional[datetime]] = mapped_column("EndDate", DateTime)
    status: Mapped[Optional[str]] = mapped_column("Status", String(50))
    release_id: Mapped[Optional[int]] = mapped_column(
        "ReleaseID", Integer, ForeignKey("Release.ReleaseID")
    )
    error: Mapped[Optional[str]] = mapped_column("Error", String(4000))

    release: Mapped[Optional["Release"]] = relationship(
        back_populates="variable_generations"
    )
