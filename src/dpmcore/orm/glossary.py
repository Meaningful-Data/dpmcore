"""ORM models for the DPM Glossary domain.

This module defines the core glossary entities that form the
backbone of the DPM metamodel: categories, items, subcategories,
properties, contexts, and their versioned and compositional
relationships.
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
from dpmcore.orm.infrastructure import Concept, DataType, Release

if TYPE_CHECKING:
    from dpmcore.orm.operations import (
        OperandReference,
        Operator,
    )
    from dpmcore.orm.rendering import HeaderVersion
    from dpmcore.orm.variables import (
        TableVersion,
        VariableVersion,
    )


# ------------------------------------------------------------------
# Category
# ------------------------------------------------------------------


class Category(Base):
    """Enumerated or reference-data grouping.

    Attributes:
        category_id: Primary key.
        code: Short category code.
        name: Human-readable name.
        description: Long description.
        is_enumerated: Whether the category is enumerated.
        is_super_category: Whether this is a super-category.
        is_active: Whether the category is currently active.
        is_external_ref_data: External reference-data flag.
        ref_data_source: Source URI for external ref data.
        row_guid: FK to Concept.
    """

    __tablename__ = "Category"

    category_id: Mapped[int] = mapped_column(
        "CategoryID", Integer, primary_key=True
    )
    code: Mapped[Optional[str]] = mapped_column(
        "Code", String(20)
    )
    name: Mapped[Optional[str]] = mapped_column(
        "Name", String(50)
    )
    description: Mapped[Optional[str]] = mapped_column(
        "Description", String(1000)
    )
    is_enumerated: Mapped[Optional[bool]] = mapped_column(
        "IsEnumerated", Boolean
    )
    is_super_category: Mapped[Optional[bool]] = mapped_column(
        "IsSuperCategory", Boolean
    )
    is_active: Mapped[Optional[bool]] = mapped_column(
        "IsActive", Boolean
    )
    is_external_ref_data: Mapped[Optional[bool]] = mapped_column(
        "IsExternalRefData", Boolean
    )
    ref_data_source: Mapped[Optional[str]] = mapped_column(
        "RefDataSource", String(255)
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )

    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    subcategories: Mapped[List["SubCategory"]] = relationship(
        back_populates="category",
    )
    property_categories: Mapped[List["PropertyCategory"]] = (
        relationship(
            back_populates="category",
        )
    )
    supercategory_compositions: Mapped[
        List["SupercategoryComposition"]
    ] = relationship(
        foreign_keys=(
            "SupercategoryComposition.supercategory_id"
        ),
        back_populates="supercategory",
    )
    category_compositions: Mapped[
        List["SupercategoryComposition"]
    ] = relationship(
        foreign_keys=(
            "SupercategoryComposition.category_id"
        ),
        back_populates="category",
    )


# ------------------------------------------------------------------
# SubCategory
# ------------------------------------------------------------------


class SubCategory(Base):
    """Alternative grouping within a Category.

    Attributes:
        subcategory_id: Primary key.
        category_id: FK to Category.
        code: Short subcategory code.
        name: Human-readable name.
        description: Long description.
        row_guid: FK to Concept.
    """

    __tablename__ = "SubCategory"

    subcategory_id: Mapped[int] = mapped_column(
        "SubCategoryID", Integer, primary_key=True
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        "CategoryID",
        Integer,
        ForeignKey("Category.CategoryID"),
    )
    code: Mapped[Optional[str]] = mapped_column(
        "Code", String(30)
    )
    name: Mapped[Optional[str]] = mapped_column(
        "Name", String(500)
    )
    description: Mapped[Optional[str]] = mapped_column(
        "Description", String(500)
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )

    category: Mapped[Optional["Category"]] = relationship(
        back_populates="subcategories"
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    subcategory_versions: Mapped[
        List["SubCategoryVersion"]
    ] = relationship(
        back_populates="subcategory",
    )
    operand_references: Mapped[
        List["OperandReference"]
    ] = relationship(
        back_populates="subcategory",
    )


# ------------------------------------------------------------------
# SubCategoryVersion
# ------------------------------------------------------------------


class SubCategoryVersion(Base):
    """Release-versioned snapshot of a SubCategory.

    Attributes:
        subcategory_vid: Primary key.
        subcategory_id: FK to SubCategory.
        start_release_id: FK to Release (version start).
        end_release_id: FK to Release (version end).
        row_guid: FK to Concept.
    """

    __tablename__ = "SubCategoryVersion"
    __table_args__ = (
        UniqueConstraint("SubCategoryID", "StartReleaseID"),
    )

    subcategory_vid: Mapped[int] = mapped_column(
        "SubCategoryVID", Integer, primary_key=True
    )
    subcategory_id: Mapped[Optional[int]] = mapped_column(
        "SubCategoryID",
        Integer,
        ForeignKey("SubCategory.SubCategoryID"),
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

    subcategory: Mapped[Optional["SubCategory"]] = relationship(
        back_populates="subcategory_versions"
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
    subcategory_items: Mapped[
        List["SubCategoryItem"]
    ] = relationship(
        back_populates="subcategory_version",
    )
    header_versions: Mapped[
        List["HeaderVersion"]
    ] = relationship(
        back_populates="subcategory_version",
    )
    variable_versions: Mapped[
        List["VariableVersion"]
    ] = relationship(
        back_populates="subcategory_version",
    )


# ------------------------------------------------------------------
# SubCategoryItem
# ------------------------------------------------------------------


class SubCategoryItem(Base):
    """An Item within a SubCategoryVersion, with ordering.

    Attributes:
        item_id: FK to Item (composite PK).
        subcategory_vid: FK to SubCategoryVersion (composite PK).
        order: Display order.
        label: Optional display label.
        parent_item_id: FK to parent Item.
        comparison_operator_id: FK to Operator.
        arithmetic_operator_id: FK to Operator.
        row_guid: FK to Concept.
    """

    __tablename__ = "SubCategoryItem"

    item_id: Mapped[int] = mapped_column(
        "ItemID",
        Integer,
        ForeignKey("Item.ItemID"),
        primary_key=True,
    )
    subcategory_vid: Mapped[int] = mapped_column(
        "SubCategoryVID",
        Integer,
        ForeignKey("SubCategoryVersion.SubCategoryVID"),
        primary_key=True,
    )
    order: Mapped[Optional[int]] = mapped_column(
        "Order", Integer
    )
    label: Mapped[Optional[str]] = mapped_column(
        "Label", String(200)
    )
    parent_item_id: Mapped[Optional[int]] = mapped_column(
        "ParentItemID",
        Integer,
        ForeignKey("Item.ItemID"),
    )
    comparison_operator_id: Mapped[Optional[int]] = (
        mapped_column(
            "ComparisonOperatorID",
            Integer,
            ForeignKey("Operator.OperatorID"),
        )
    )
    arithmetic_operator_id: Mapped[Optional[int]] = (
        mapped_column(
            "ArithmeticOperatorID",
            Integer,
            ForeignKey("Operator.OperatorID"),
        )
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )

    item: Mapped["Item"] = relationship(
        foreign_keys=[item_id],
        back_populates="subcategory_items",
    )
    subcategory_version: Mapped[
        Optional["SubCategoryVersion"]
    ] = relationship(
        back_populates="subcategory_items"
    )
    parent_item: Mapped[Optional["Item"]] = relationship(
        foreign_keys=[parent_item_id]
    )
    comparison_operator: Mapped[
        Optional["Operator"]
    ] = relationship(
        foreign_keys=[comparison_operator_id],
        back_populates="comparison_subcategory_items",
    )
    arithmetic_operator: Mapped[
        Optional["Operator"]
    ] = relationship(
        foreign_keys=[arithmetic_operator_id],
        back_populates="arithmetic_subcategory_items",
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )


# ------------------------------------------------------------------
# Item
# ------------------------------------------------------------------


class Item(Base):
    """Concrete category member (enumerated value).

    Attributes:
        item_id: Primary key.
        name: Human-readable name.
        description: Long description.
        is_compound: Whether this is a compound item.
        is_property: Whether this item doubles as a property.
        is_active: Whether the item is currently active.
        row_guid: FK to Concept.
    """

    __tablename__ = "Item"

    item_id: Mapped[int] = mapped_column(
        "ItemID", Integer, primary_key=True
    )
    name: Mapped[Optional[str]] = mapped_column(
        "Name", String(500)
    )
    description: Mapped[Optional[str]] = mapped_column(
        "Description", String(2000)
    )
    is_compound: Mapped[Optional[bool]] = mapped_column(
        "IsCompound", Boolean
    )
    is_property: Mapped[Optional[bool]] = mapped_column(
        "IsProperty", Boolean
    )
    is_active: Mapped[Optional[bool]] = mapped_column(
        "IsActive", Boolean
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )

    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    item_categories: Mapped[List["ItemCategory"]] = relationship(
        back_populates="item",
    )
    property: Mapped[Optional["Property"]] = relationship(
        back_populates="item",
        uselist=False,
    )
    operand_references: Mapped[
        List["OperandReference"]
    ] = relationship(
        back_populates="item",
    )
    context_compositions: Mapped[
        List["ContextComposition"]
    ] = relationship(
        back_populates="item",
    )
    subcategory_items: Mapped[
        List["SubCategoryItem"]
    ] = relationship(
        foreign_keys="SubCategoryItem.item_id",
        back_populates="item",
    )
    compound_item_contexts: Mapped[
        List["CompoundItemContext"]
    ] = relationship(
        back_populates="item",
    )


# ------------------------------------------------------------------
# ItemCategory
# ------------------------------------------------------------------


class ItemCategory(Base):
    """Release-versioned link between an Item and a Category.

    Attributes:
        item_id: FK to Item (composite PK).
        start_release_id: FK to Release (composite PK).
        category_id: FK to Category.
        code: Item code within this category.
        is_default_item: Whether this is the default item.
        signature: Optional signature string.
        end_release_id: FK to Release (version end).
        row_guid: Row GUID.
    """

    __tablename__ = "ItemCategory"

    item_id: Mapped[int] = mapped_column(
        "ItemID",
        Integer,
        ForeignKey("Item.ItemID"),
        primary_key=True,
    )
    start_release_id: Mapped[int] = mapped_column(
        "StartReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
        primary_key=True,
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        "CategoryID",
        Integer,
        ForeignKey("Category.CategoryID"),
    )
    code: Mapped[Optional[str]] = mapped_column(
        "Code", String(20)
    )
    is_default_item: Mapped[Optional[bool]] = mapped_column(
        "IsDefaultItem", Boolean
    )
    signature: Mapped[Optional[str]] = mapped_column(
        "Signature", String(255)
    )
    end_release_id: Mapped[Optional[int]] = mapped_column(
        "EndReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID", String(36)
    )

    item: Mapped["Item"] = relationship(
        back_populates="item_categories"
    )
    start_release: Mapped["Release"] = relationship(
        foreign_keys=[start_release_id]
    )
    end_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[end_release_id]
    )
    category: Mapped[Optional["Category"]] = relationship()


# ------------------------------------------------------------------
# Property
# ------------------------------------------------------------------


class Property(Base):
    """Aspect or characteristic linked to an Item.

    Attributes:
        property_id: FK to Item (PK).
        is_composite: Whether this is a composite property.
        is_metric: Whether this property is a metric.
        data_type_id: FK to DataType.
        value_length: Maximum value length.
        period_type: Period type descriptor.
        row_guid: FK to Concept.
    """

    __tablename__ = "Property"

    property_id: Mapped[int] = mapped_column(
        "PropertyID",
        Integer,
        ForeignKey("Item.ItemID"),
        primary_key=True,
    )
    is_composite: Mapped[Optional[bool]] = mapped_column(
        "IsComposite", Boolean
    )
    is_metric: Mapped[Optional[bool]] = mapped_column(
        "IsMetric", Boolean
    )
    data_type_id: Mapped[Optional[int]] = mapped_column(
        "DataTypeID",
        Integer,
        ForeignKey("DataType.DataTypeID"),
    )
    value_length: Mapped[Optional[int]] = mapped_column(
        "ValueLength", Integer
    )
    period_type: Mapped[Optional[str]] = mapped_column(
        "PeriodType", String(20)
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )

    item: Mapped["Item"] = relationship(
        back_populates="property"
    )
    datatype: Mapped[Optional["DataType"]] = relationship(
        back_populates="properties"
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    property_categories: Mapped[
        List["PropertyCategory"]
    ] = relationship(
        back_populates="property",
    )
    context_compositions: Mapped[
        List["ContextComposition"]
    ] = relationship(
        back_populates="property",
    )
    variable_versions: Mapped[
        List["VariableVersion"]
    ] = relationship(
        back_populates="property",
    )
    header_versions: Mapped[
        List["HeaderVersion"]
    ] = relationship(
        back_populates="property",
    )
    table_versions: Mapped[
        List["TableVersion"]
    ] = relationship(
        back_populates="property",
    )


# ------------------------------------------------------------------
# PropertyCategory
# ------------------------------------------------------------------


class PropertyCategory(Base):
    """Release-versioned link between a Property and a Category.

    Attributes:
        property_id: FK to Property (composite PK).
        start_release_id: FK to Release (composite PK).
        category_id: FK to Category.
        end_release_id: FK to Release (version end).
        row_guid: Row GUID.
    """

    __tablename__ = "PropertyCategory"

    property_id: Mapped[int] = mapped_column(
        "PropertyID",
        Integer,
        ForeignKey("Property.PropertyID"),
        primary_key=True,
    )
    start_release_id: Mapped[int] = mapped_column(
        "StartReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
        primary_key=True,
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        "CategoryID",
        Integer,
        ForeignKey("Category.CategoryID"),
    )
    end_release_id: Mapped[Optional[int]] = mapped_column(
        "EndReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID", String(36)
    )

    property: Mapped["Property"] = relationship(
        back_populates="property_categories"
    )
    start_release: Mapped["Release"] = relationship(
        foreign_keys=[start_release_id]
    )
    end_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[end_release_id]
    )
    category: Mapped[Optional["Category"]] = relationship(
        back_populates="property_categories"
    )


# ------------------------------------------------------------------
# Context
# ------------------------------------------------------------------


class Context(Base):
    """Reusable signature grouping Properties for CompoundItems.

    Attributes:
        context_id: Primary key.
        signature: Unique context signature.
        row_guid: FK to Concept.
    """

    __tablename__ = "Context"

    context_id: Mapped[int] = mapped_column(
        "ContextID", Integer, primary_key=True
    )
    signature: Mapped[Optional[str]] = mapped_column(
        "Signature", String(2000), unique=True
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )

    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    context_compositions: Mapped[
        List["ContextComposition"]
    ] = relationship(
        back_populates="context",
    )
    variable_versions: Mapped[
        List["VariableVersion"]
    ] = relationship(
        back_populates="context",
    )
    header_versions: Mapped[
        List["HeaderVersion"]
    ] = relationship(
        back_populates="context",
    )
    table_versions: Mapped[
        List["TableVersion"]
    ] = relationship(
        back_populates="context",
    )
    compound_item_contexts: Mapped[
        List["CompoundItemContext"]
    ] = relationship(
        back_populates="context",
    )


# ------------------------------------------------------------------
# ContextComposition
# ------------------------------------------------------------------


class ContextComposition(Base):
    """Maps Properties and Items within a Context.

    Attributes:
        context_id: FK to Context (composite PK).
        property_id: FK to Property (composite PK).
        item_id: FK to Item.
        row_guid: FK to Concept.
    """

    __tablename__ = "ContextComposition"

    context_id: Mapped[int] = mapped_column(
        "ContextID",
        Integer,
        ForeignKey("Context.ContextID"),
        primary_key=True,
    )
    property_id: Mapped[int] = mapped_column(
        "PropertyID",
        Integer,
        ForeignKey("Property.PropertyID"),
        primary_key=True,
    )
    item_id: Mapped[Optional[int]] = mapped_column(
        "ItemID",
        Integer,
        ForeignKey("Item.ItemID"),
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )

    context: Mapped["Context"] = relationship(
        back_populates="context_compositions"
    )
    property: Mapped["Property"] = relationship(
        back_populates="context_compositions"
    )
    item: Mapped[Optional["Item"]] = relationship(
        back_populates="context_compositions"
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        back_populates="context_compositions"
    )


# ------------------------------------------------------------------
# CompoundItemContext
# ------------------------------------------------------------------


class CompoundItemContext(Base):
    """Release-versioned association of a compound Item with a Context.

    Attributes:
        item_id: FK to Item (composite PK).
        start_release_id: FK to Release (composite PK).
        context_id: FK to Context.
        end_release_id: FK to Release (version end).
        row_guid: Row GUID.
    """

    __tablename__ = "CompoundItemContext"

    item_id: Mapped[int] = mapped_column(
        "ItemID",
        Integer,
        ForeignKey("Item.ItemID"),
        primary_key=True,
    )
    start_release_id: Mapped[int] = mapped_column(
        "StartReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
        primary_key=True,
    )
    context_id: Mapped[Optional[int]] = mapped_column(
        "ContextID",
        Integer,
        ForeignKey("Context.ContextID"),
    )
    end_release_id: Mapped[Optional[int]] = mapped_column(
        "EndReleaseID",
        Integer,
        ForeignKey("Release.ReleaseID"),
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID", String(36)
    )

    item: Mapped["Item"] = relationship(
        back_populates="compound_item_contexts"
    )
    start_release: Mapped["Release"] = relationship(
        foreign_keys=[start_release_id]
    )
    end_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[end_release_id]
    )
    context: Mapped[Optional["Context"]] = relationship(
        back_populates="compound_item_contexts"
    )


# ------------------------------------------------------------------
# SupercategoryComposition
# ------------------------------------------------------------------


class SupercategoryComposition(Base):
    """Composition link between a super-category and a category.

    Attributes:
        supercategory_id: FK to Category (composite PK).
        category_id: FK to Category (composite PK).
        start_release_id: FK to Release.
        end_release_id: FK to Release (version end).
        row_guid: Row GUID.
    """

    __tablename__ = "SuperCategoryComposition"

    supercategory_id: Mapped[int] = mapped_column(
        "SuperCategoryID",
        Integer,
        ForeignKey("Category.CategoryID"),
        primary_key=True,
    )
    category_id: Mapped[int] = mapped_column(
        "CategoryID",
        Integer,
        ForeignKey("Category.CategoryID"),
        primary_key=True,
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

    supercategory: Mapped["Category"] = relationship(
        foreign_keys=[supercategory_id],
        back_populates="supercategory_compositions",
    )
    category: Mapped["Category"] = relationship(
        foreign_keys=[category_id],
        back_populates="category_compositions",
    )
    start_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[start_release_id]
    )
    end_release: Mapped[Optional["Release"]] = relationship(
        foreign_keys=[end_release_id]
    )
