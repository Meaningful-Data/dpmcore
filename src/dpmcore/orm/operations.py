"""ORM models for DPM Operations domain.

This module defines Operation, OperationVersion, OperationVersionData,
OperationNode, OperationScope, OperationScopeComposition, Operator,
OperatorArgument, OperandReference, and OperandReferenceLocation
models.
"""

from datetime import date
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dpmcore.orm.base import Base
from dpmcore.orm.infrastructure import Concept, Release

if TYPE_CHECKING:
    from dpmcore.orm.glossary import (
        Item,
        Property,
        SubCategory,
    )
    from dpmcore.orm.packaging import ModuleVersion
    from dpmcore.orm.variables import Variable


# ------------------------------------------------------------------
# Operation
# ------------------------------------------------------------------


class Operation(Base):
    """Top-level operation entity.

    Attributes:
        operation_id: Primary key.
        code: Short code.
        type: Operation type.
        source: Operation source.
        group_operation_id: Self-FK for grouping.
        row_guid: FK to Concept.
    """

    __tablename__ = "Operation"

    operation_id: Mapped[int] = mapped_column(
        "OperationID", Integer, primary_key=True
    )
    code: Mapped[Optional[str]] = mapped_column("Code", String(20))
    type: Mapped[Optional[str]] = mapped_column("Type", String(20))
    source: Mapped[Optional[str]] = mapped_column("Source", String(20))
    group_operation_id: Mapped[Optional[int]] = mapped_column(
        "GroupOperID",
        Integer,
        ForeignKey("Operation.OperationID"),
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    owner_id: Mapped[Optional[int]] = mapped_column("OwnerID", Integer)

    group_operation: Mapped[Optional["Operation"]] = relationship(
        remote_side=[operation_id],
        back_populates="grouped_operations",
    )
    grouped_operations: Mapped[List["Operation"]] = relationship(
        back_populates="group_operation",
    )
    concept: Mapped[Optional["Concept"]] = relationship(
        foreign_keys=[row_guid]
    )
    operation_versions: Mapped[List["OperationVersion"]] = relationship(
        back_populates="operation",
    )


# ------------------------------------------------------------------
# OperationVersion
# ------------------------------------------------------------------


class OperationVersion(Base):
    """Versioned snapshot of an Operation.

    Attributes:
        operation_vid: Primary key.
        operation_id: FK to Operation.
        precondition_operation_vid: Self-FK for precondition.
        severity_operation_vid: Self-FK for severity.
        start_release_id: FK to starting Release.
        end_release_id: FK to ending Release.
        expression: Full expression text.
        description: Human-readable description.
        row_guid: FK to Concept.
        endorsement: Endorsement label.
        is_variant_approved: Variant approval flag.
    """

    __tablename__ = "OperationVersion"
    __table_args__ = (UniqueConstraint("OperationID", "StartReleaseID"),)

    operation_vid: Mapped[int] = mapped_column(
        "OperationVID", Integer, primary_key=True
    )
    operation_id: Mapped[Optional[int]] = mapped_column(
        "OperationID",
        Integer,
        ForeignKey("Operation.OperationID"),
    )
    precondition_operation_vid: Mapped[Optional[int]] = mapped_column(
        "PreconditionOperationVID",
        Integer,
        ForeignKey("OperationVersion.OperationVID"),
    )
    severity_operation_vid: Mapped[Optional[int]] = mapped_column(
        "SeverityOperationVID",
        Integer,
        ForeignKey("OperationVersion.OperationVID"),
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
    expression: Mapped[Optional[str]] = mapped_column("Expression", Text)
    description: Mapped[Optional[str]] = mapped_column(
        "Description", String(1000)
    )
    row_guid: Mapped[Optional[str]] = mapped_column(
        "RowGUID",
        String(36),
        ForeignKey("Concept.ConceptGUID"),
    )
    endorsement: Mapped[Optional[str]] = mapped_column(
        "Endorsement", String(25)
    )
    is_variant_approved: Mapped[Optional[bool]] = mapped_column(
        "IsVariantApproved", Boolean
    )

    operation: Mapped[Optional["Operation"]] = relationship(
        back_populates="operation_versions"
    )
    precondition_operation: Mapped[Optional["OperationVersion"]] = (
        relationship(
            foreign_keys=[precondition_operation_vid],
            remote_side=[operation_vid],
            back_populates="precondition_dependent_operations",
        )
    )
    severity_operation: Mapped[Optional["OperationVersion"]] = relationship(
        foreign_keys=[severity_operation_vid],
        remote_side=[operation_vid],
        back_populates="severity_dependent_operations",
    )
    precondition_dependent_operations: Mapped[List["OperationVersion"]] = (
        relationship(
            foreign_keys=[precondition_operation_vid],
            back_populates="precondition_operation",
        )
    )
    severity_dependent_operations: Mapped[List["OperationVersion"]] = (
        relationship(
            foreign_keys=[severity_operation_vid],
            back_populates="severity_operation",
        )
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
    operation_nodes: Mapped[List["OperationNode"]] = relationship(
        back_populates="operation_version",
    )
    operation_scopes: Mapped[List["OperationScope"]] = relationship(
        back_populates="operation_version",
    )
    operation_version_data: Mapped[Optional["OperationVersionData"]] = (
        relationship(
            back_populates="operation_version",
            uselist=False,
        )
    )
    variable_calculations: Mapped[List["VariableCalculation"]] = relationship(
        back_populates="operation_version",
    )


# ------------------------------------------------------------------
# OperationVersionData
# ------------------------------------------------------------------


class OperationVersionData(Base):
    """Extended data for an OperationVersion.

    Attributes:
        operation_vid: FK to OperationVersion (PK).
        error: Error message text.
        error_code: Error code string.
        is_applying: Whether currently applying.
        proposing_status: Proposal status label.
    """

    __tablename__ = "OperationVersionData"

    operation_vid: Mapped[int] = mapped_column(
        "OperationVID",
        Integer,
        ForeignKey("OperationVersion.OperationVID"),
        primary_key=True,
    )
    error: Mapped[Optional[str]] = mapped_column("Error", String(2000))
    error_code: Mapped[Optional[str]] = mapped_column("ErrorCode", String(50))
    is_applying: Mapped[Optional[bool]] = mapped_column("IsApplying", Boolean)
    proposing_status: Mapped[Optional[str]] = mapped_column(
        "ProposingStatus", String(50)
    )

    operation_version: Mapped["OperationVersion"] = relationship(
        back_populates="operation_version_data"
    )


# ------------------------------------------------------------------
# OperationNode
# ------------------------------------------------------------------


class OperationNode(Base):
    """Tree node within an OperationVersion expression.

    Attributes:
        node_id: Primary key.
        operation_vid: FK to OperationVersion.
        parent_node_id: Self-FK for tree hierarchy.
        operator_id: FK to Operator.
        argument_id: FK to OperatorArgument.
        absolute_tolerance: Absolute tolerance value.
        relative_tolerance: Relative tolerance value.
        fallback_value: Fallback value text.
        use_interval_arithmetics: Interval-arithmetic flag.
        operand_type: Operand type descriptor.
        is_leaf: Leaf-node flag.
        scalar: Scalar expression text.
    """

    __tablename__ = "OperationNode"

    node_id: Mapped[int] = mapped_column("NodeID", Integer, primary_key=True)
    operation_vid: Mapped[Optional[int]] = mapped_column(
        "OperationVID",
        Integer,
        ForeignKey("OperationVersion.OperationVID"),
    )
    parent_node_id: Mapped[Optional[int]] = mapped_column(
        "ParentNodeID",
        Integer,
        ForeignKey("OperationNode.NodeID"),
    )
    operator_id: Mapped[Optional[int]] = mapped_column(
        "OperatorID",
        Integer,
        ForeignKey("Operator.OperatorID"),
    )
    argument_id: Mapped[Optional[int]] = mapped_column(
        "ArgumentID",
        Integer,
        ForeignKey("OperatorArgument.ArgumentID"),
    )
    absolute_tolerance: Mapped[Optional[str]] = mapped_column(
        "AbsoluteTolerance", String
    )
    relative_tolerance: Mapped[Optional[str]] = mapped_column(
        "RelativeTolerance", String
    )
    fallback_value: Mapped[Optional[str]] = mapped_column(
        "FallbackValue", String(50)
    )
    use_interval_arithmetics: Mapped[Optional[bool]] = mapped_column(
        "UseIntervalArithmetics", Boolean
    )
    operand_type: Mapped[Optional[str]] = mapped_column(
        "OperandType", String(20)
    )
    is_leaf: Mapped[Optional[bool]] = mapped_column("IsLeaf", Boolean)
    scalar: Mapped[Optional[str]] = mapped_column("Scalar", Text)

    operation_version: Mapped[Optional["OperationVersion"]] = relationship(
        back_populates="operation_nodes"
    )
    parent: Mapped[Optional["OperationNode"]] = relationship(
        remote_side=[node_id],
        back_populates="children",
    )
    children: Mapped[List["OperationNode"]] = relationship(
        back_populates="parent",
    )
    operator: Mapped[Optional["Operator"]] = relationship(
        foreign_keys=[operator_id],
        back_populates="operation_nodes",
    )
    operator_argument: Mapped[Optional["OperatorArgument"]] = relationship(
        foreign_keys=[argument_id],
        back_populates="operation_nodes",
    )
    operand_references: Mapped[List["OperandReference"]] = relationship(
        back_populates="operation_node",
    )


# ------------------------------------------------------------------
# OperationScope
# ------------------------------------------------------------------


class OperationScope(Base):
    """Scope definition for an OperationVersion.

    Attributes:
        operation_scope_id: Primary key.
        operation_vid: FK to OperationVersion.
        is_active: Active flag (small integer).
        severity: Severity level label.
        from_submission_date: Effective start date.
        row_guid: Row GUID.
    """

    __tablename__ = "OperationScope"

    operation_scope_id: Mapped[int] = mapped_column(
        "OperationScopeID", Integer, primary_key=True
    )
    operation_vid: Mapped[Optional[int]] = mapped_column(
        "OperationVID",
        Integer,
        ForeignKey("OperationVersion.OperationVID"),
    )
    is_active: Mapped[Optional[int]] = mapped_column("IsActive", SmallInteger)
    severity: Mapped[Optional[str]] = mapped_column("Severity", String(20))
    from_submission_date: Mapped[Optional[date]] = mapped_column(
        "FromSubmissionDate", Date
    )
    row_guid: Mapped[Optional[str]] = mapped_column("RowGUID", String(36))

    operation_version: Mapped[Optional["OperationVersion"]] = relationship(
        back_populates="operation_scopes"
    )
    operation_scope_compositions: Mapped[List["OperationScopeComposition"]] = (
        relationship(
            back_populates="operation_scope",
        )
    )


# ------------------------------------------------------------------
# OperationScopeComposition
# ------------------------------------------------------------------


class OperationScopeComposition(Base):
    """Association between OperationScope and ModuleVersion.

    Attributes:
        operation_scope_id: FK to OperationScope (composite PK).
        module_vid: FK to ModuleVersion (composite PK).
        row_guid: Row GUID.
    """

    __tablename__ = "OperationScopeComposition"

    operation_scope_id: Mapped[int] = mapped_column(
        "OperationScopeID",
        Integer,
        ForeignKey("OperationScope.OperationScopeID"),
        primary_key=True,
    )
    module_vid: Mapped[int] = mapped_column(
        "ModuleVID",
        Integer,
        ForeignKey("ModuleVersion.ModuleVID"),
        primary_key=True,
    )
    row_guid: Mapped[Optional[str]] = mapped_column("RowGUID", String(36))

    operation_scope: Mapped["OperationScope"] = relationship(
        back_populates="operation_scope_compositions"
    )
    module_version: Mapped["ModuleVersion"] = relationship(
        back_populates="operation_scope_compositions"
    )


# ------------------------------------------------------------------
# Operator
# ------------------------------------------------------------------


class Operator(Base):
    """Operator definition (e.g. +, -, =, AND).

    Attributes:
        operator_id: Primary key.
        name: Display name.
        symbol: Symbol representation.
        type: Operator type.
    """

    __tablename__ = "Operator"

    operator_id: Mapped[int] = mapped_column(
        "OperatorID", Integer, primary_key=True
    )
    name: Mapped[Optional[str]] = mapped_column("Name", String(50))
    symbol: Mapped[Optional[str]] = mapped_column("Symbol", String(20))
    type: Mapped[Optional[str]] = mapped_column("Type", String(20))

    operator_arguments: Mapped[List["OperatorArgument"]] = relationship(
        back_populates="operator",
    )
    operation_nodes: Mapped[List["OperationNode"]] = relationship(
        foreign_keys="OperationNode.operator_id",
        back_populates="operator",
    )
    comparison_subcategory_items: Mapped[List["SubCategoryItem"]] = (
        relationship(
            foreign_keys="SubCategoryItem.comparison_operator_id",
            back_populates="comparison_operator",
        )
    )
    arithmetic_subcategory_items: Mapped[List["SubCategoryItem"]] = (
        relationship(
            foreign_keys="SubCategoryItem.arithmetic_operator_id",
            back_populates="arithmetic_operator",
        )
    )


# ------------------------------------------------------------------
# OperatorArgument
# ------------------------------------------------------------------


class OperatorArgument(Base):
    """Argument definition for an Operator.

    Attributes:
        argument_id: Primary key.
        operator_id: FK to Operator.
        order: Argument position.
        is_mandatory: Whether the argument is required.
        name: Argument name.
    """

    __tablename__ = "OperatorArgument"

    argument_id: Mapped[int] = mapped_column(
        "ArgumentID", Integer, primary_key=True
    )
    operator_id: Mapped[Optional[int]] = mapped_column(
        "OperatorID",
        Integer,
        ForeignKey("Operator.OperatorID"),
    )
    order: Mapped[Optional[int]] = mapped_column("Order", SmallInteger)
    is_mandatory: Mapped[Optional[bool]] = mapped_column(
        "IsMandatory", Boolean
    )
    name: Mapped[Optional[str]] = mapped_column("Name", String(50))

    operator: Mapped[Optional["Operator"]] = relationship(
        back_populates="operator_arguments"
    )
    operation_nodes: Mapped[List["OperationNode"]] = relationship(
        foreign_keys="OperationNode.argument_id",
        back_populates="operator_argument",
    )


# ------------------------------------------------------------------
# OperandReference
# ------------------------------------------------------------------


class OperandReference(Base):
    """Reference from an OperationNode to data entities.

    Attributes:
        operand_reference_id: Primary key.
        node_id: FK to OperationNode.
        x: X coordinate.
        y: Y coordinate.
        z: Z coordinate.
        operand_reference: Reference expression string.
        item_id: FK to Item.
        property_id: FK to Property.
        variable_id: FK to Variable.
        subcategory_id: FK to SubCategory.
    """

    __tablename__ = "OperandReference"

    operand_reference_id: Mapped[int] = mapped_column(
        "OperandReferenceID", Integer, primary_key=True
    )
    node_id: Mapped[Optional[int]] = mapped_column(
        "NodeID",
        Integer,
        ForeignKey("OperationNode.NodeID"),
    )
    x: Mapped[Optional[int]] = mapped_column("x", Integer)
    y: Mapped[Optional[int]] = mapped_column("y", Integer)
    z: Mapped[Optional[int]] = mapped_column("z", Integer)
    operand_reference: Mapped[Optional[str]] = mapped_column(
        "OperandReference", String(255)
    )
    item_id: Mapped[Optional[int]] = mapped_column(
        "ItemID",
        Integer,
        ForeignKey("Item.ItemID"),
    )
    property_id: Mapped[Optional[int]] = mapped_column(
        "PropertyID",
        Integer,
        ForeignKey("Property.PropertyID"),
    )
    variable_id: Mapped[Optional[int]] = mapped_column(
        "VariableID",
        Integer,
        ForeignKey("Variable.VariableID"),
    )
    subcategory_id: Mapped[Optional[int]] = mapped_column(
        "SubCategoryID",
        Integer,
        ForeignKey("SubCategory.SubCategoryID"),
    )

    operation_node: Mapped[Optional["OperationNode"]] = relationship(
        back_populates="operand_references"
    )
    item: Mapped[Optional["Item"]] = relationship(foreign_keys=[item_id])
    property: Mapped[Optional["Property"]] = relationship(
        foreign_keys=[property_id]
    )
    variable: Mapped[Optional["Variable"]] = relationship(
        foreign_keys=[variable_id],
        back_populates="operand_references",
    )
    subcategory: Mapped[Optional["SubCategory"]] = relationship(
        foreign_keys=[subcategory_id]
    )
    operand_reference_locations: Mapped[List["OperandReferenceLocation"]] = (
        relationship(
            back_populates="operand_reference",
        )
    )


# ------------------------------------------------------------------
# OperandReferenceLocation
# ------------------------------------------------------------------


class OperandReferenceLocation(Base):
    """Physical location of an OperandReference in a table.

    Attributes:
        operand_reference_id: FK to OperandReference (PK).
        cell_id: FK to Cell.
        table: Table name.
        row: Row identifier.
        column: Column identifier.
        sheet: Sheet identifier.
    """

    __tablename__ = "OperandReferenceLocation"

    operand_reference_id: Mapped[int] = mapped_column(
        "OperandReferenceID",
        Integer,
        ForeignKey("OperandReference.OperandReferenceID"),
        primary_key=True,
    )
    cell_id: Mapped[Optional[int]] = mapped_column(
        "CellID",
        Integer,
        ForeignKey("Cell.CellID"),
    )
    table: Mapped[Optional[str]] = mapped_column("Table", String(255))
    row: Mapped[Optional[str]] = mapped_column("Row", String(255))
    column: Mapped[Optional[str]] = mapped_column("Column", String(255))
    sheet: Mapped[Optional[str]] = mapped_column("Sheet", String(255))

    operand_reference: Mapped["OperandReference"] = relationship(
        back_populates="operand_reference_locations"
    )
    cell: Mapped[Optional["Cell"]] = relationship(foreign_keys=[cell_id])
