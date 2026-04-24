"""Django models for DPM operations domain."""

from django.db import models


class Operation(models.Model):
    """Top-level operation entity."""

    operation_id = models.IntegerField(
        db_column="OperationID",
        primary_key=True,
    )
    code = models.CharField(
        db_column="Code",
        max_length=20,
        null=True,
        blank=True,
    )
    type = models.CharField(
        db_column="Type",
        max_length=20,
        null=True,
        blank=True,
    )
    source = models.CharField(
        db_column="Source",
        max_length=20,
        null=True,
        blank=True,
    )
    group_operation_id = models.ForeignKey(
        "self",
        on_delete=models.DO_NOTHING,
        db_column="GroupOperID",
        null=True,
        blank=True,
    )
    row_guid = models.CharField(
        db_column="RowGUID",
        max_length=36,
        null=True,
        blank=True,
    )
    owner_id = models.IntegerField(
        db_column="OwnerID",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "Operation"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.code or str(self.operation_id)


class OperationVersion(models.Model):
    """Versioned snapshot of an Operation."""

    operation_vid = models.IntegerField(
        db_column="OperationVID",
        primary_key=True,
    )
    operation_id = models.ForeignKey(
        "Operation",
        on_delete=models.DO_NOTHING,
        db_column="OperationID",
        null=True,
        blank=True,
    )
    precondition_operation_vid = models.ForeignKey(
        "self",
        on_delete=models.DO_NOTHING,
        db_column="PreconditionOperationVID",
        related_name="precondition_dependents",
        null=True,
        blank=True,
    )
    severity_operation_vid = models.ForeignKey(
        "self",
        on_delete=models.DO_NOTHING,
        db_column="SeverityOperationVID",
        related_name="severity_dependents",
        null=True,
        blank=True,
    )
    start_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="StartReleaseID",
        related_name="operation_version_starts",
        null=True,
        blank=True,
    )
    end_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="EndReleaseID",
        related_name="operation_version_ends",
        null=True,
        blank=True,
    )
    expression = models.TextField(
        db_column="Expression",
        null=True,
        blank=True,
    )
    description = models.CharField(
        db_column="Description",
        max_length=1000,
        null=True,
        blank=True,
    )
    row_guid = models.CharField(
        db_column="RowGUID",
        max_length=36,
        null=True,
        blank=True,
    )
    endorsement = models.CharField(
        db_column="Endorsement",
        max_length=25,
        null=True,
        blank=True,
    )
    is_variant_approved = models.BooleanField(
        db_column="IsVariantApproved",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "OperationVersion"
        app_label = "dpmcore_django"


class OperationVersionData(models.Model):
    """Extended data for an OperationVersion."""

    operation_vid = models.OneToOneField(
        "OperationVersion",
        on_delete=models.DO_NOTHING,
        db_column="OperationVID",
        primary_key=True,
    )
    error = models.CharField(
        db_column="Error",
        max_length=2000,
        null=True,
        blank=True,
    )
    error_code = models.CharField(
        db_column="ErrorCode",
        max_length=50,
        null=True,
        blank=True,
    )
    is_applying = models.BooleanField(
        db_column="IsApplying",
        null=True,
        blank=True,
    )
    proposing_status = models.CharField(
        db_column="ProposingStatus",
        max_length=50,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "OperationVersionData"
        app_label = "dpmcore_django"


class OperationNode(models.Model):
    """Tree node within an OperationVersion expression."""

    node_id = models.IntegerField(
        db_column="NodeID",
        primary_key=True,
    )
    operation_vid = models.ForeignKey(
        "OperationVersion",
        on_delete=models.DO_NOTHING,
        db_column="OperationVID",
        null=True,
        blank=True,
    )
    parent_node_id = models.ForeignKey(
        "self",
        on_delete=models.DO_NOTHING,
        db_column="ParentNodeID",
        null=True,
        blank=True,
    )
    operator_id = models.ForeignKey(
        "Operator",
        on_delete=models.DO_NOTHING,
        db_column="OperatorID",
        null=True,
        blank=True,
    )
    argument_id = models.ForeignKey(
        "OperatorArgument",
        on_delete=models.DO_NOTHING,
        db_column="ArgumentID",
        null=True,
        blank=True,
    )
    absolute_tolerance = models.TextField(
        db_column="AbsoluteTolerance",
        null=True,
        blank=True,
    )
    relative_tolerance = models.TextField(
        db_column="RelativeTolerance",
        null=True,
        blank=True,
    )
    fallback_value = models.CharField(
        db_column="FallbackValue",
        max_length=50,
        null=True,
        blank=True,
    )
    use_interval_arithmetics = models.BooleanField(
        db_column="UseIntervalArithmetics",
        null=True,
        blank=True,
    )
    operand_type = models.CharField(
        db_column="OperandType",
        max_length=20,
        null=True,
        blank=True,
    )
    is_leaf = models.BooleanField(
        db_column="IsLeaf",
        null=True,
        blank=True,
    )
    scalar = models.TextField(
        db_column="Scalar",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "OperationNode"
        app_label = "dpmcore_django"


class OperationScope(models.Model):
    """Scope definition for an OperationVersion."""

    operation_scope_id = models.IntegerField(
        db_column="OperationScopeID",
        primary_key=True,
    )
    operation_vid = models.ForeignKey(
        "OperationVersion",
        on_delete=models.DO_NOTHING,
        db_column="OperationVID",
        null=True,
        blank=True,
    )
    is_active = models.SmallIntegerField(
        db_column="IsActive",
        null=True,
        blank=True,
    )
    severity = models.CharField(
        db_column="Severity",
        max_length=20,
        null=True,
        blank=True,
    )
    from_submission_date = models.DateField(
        db_column="FromSubmissionDate",
        null=True,
        blank=True,
    )
    row_guid = models.CharField(
        db_column="RowGUID",
        max_length=36,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "OperationScope"
        app_label = "dpmcore_django"


class OperationScopeComposition(models.Model):
    """Association between OperationScope and ModuleVersion."""

    operation_scope_id = models.ForeignKey(
        "OperationScope",
        on_delete=models.DO_NOTHING,
        db_column="OperationScopeID",
        primary_key=True,
    )
    module_vid = models.ForeignKey(
        "ModuleVersion",
        on_delete=models.DO_NOTHING,
        db_column="ModuleVID",
    )
    row_guid = models.CharField(
        db_column="RowGUID",
        max_length=36,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "OperationScopeComposition"
        app_label = "dpmcore_django"
        unique_together = (("operation_scope_id", "module_vid"),)


class Operator(models.Model):
    """Operator definition (e.g. +, -, =, AND)."""

    operator_id = models.IntegerField(
        db_column="OperatorID",
        primary_key=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=50,
        null=True,
        blank=True,
    )
    symbol = models.CharField(
        db_column="Symbol",
        max_length=20,
        null=True,
        blank=True,
    )
    type = models.CharField(
        db_column="Type",
        max_length=20,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "Operator"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.name or str(self.operator_id)


class OperatorArgument(models.Model):
    """Argument definition for an Operator."""

    argument_id = models.IntegerField(
        db_column="ArgumentID",
        primary_key=True,
    )
    operator_id = models.ForeignKey(
        "Operator",
        on_delete=models.DO_NOTHING,
        db_column="OperatorID",
        null=True,
        blank=True,
    )
    order = models.SmallIntegerField(
        db_column="Order",
        null=True,
        blank=True,
    )
    is_mandatory = models.BooleanField(
        db_column="IsMandatory",
        null=True,
        blank=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=50,
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return self.name or str(self.argument_id)

    class Meta:
        managed = False
        db_table = "OperatorArgument"
        app_label = "dpmcore_django"


class OperandReference(models.Model):
    """Reference from an OperationNode to data entities."""

    operand_reference_id = models.IntegerField(
        db_column="OperandReferenceID",
        primary_key=True,
    )
    node_id = models.ForeignKey(
        "OperationNode",
        on_delete=models.DO_NOTHING,
        db_column="NodeID",
        null=True,
        blank=True,
    )
    x = models.IntegerField(
        db_column="x",
        null=True,
        blank=True,
    )
    y = models.IntegerField(
        db_column="y",
        null=True,
        blank=True,
    )
    z = models.IntegerField(
        db_column="z",
        null=True,
        blank=True,
    )
    operand_reference = models.CharField(
        db_column="OperandReference",
        max_length=255,
        null=True,
        blank=True,
    )
    item_id = models.ForeignKey(
        "Item",
        on_delete=models.DO_NOTHING,
        db_column="ItemID",
        null=True,
        blank=True,
    )
    property_id = models.ForeignKey(
        "Property",
        on_delete=models.DO_NOTHING,
        db_column="PropertyID",
        null=True,
        blank=True,
    )
    variable_id = models.ForeignKey(
        "Variable",
        on_delete=models.DO_NOTHING,
        db_column="VariableID",
        null=True,
        blank=True,
    )
    subcategory_id = models.ForeignKey(
        "SubCategory",
        on_delete=models.DO_NOTHING,
        db_column="SubCategoryID",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "OperandReference"
        app_label = "dpmcore_django"


class OperandReferenceLocation(models.Model):
    """Physical location of an OperandReference in a table."""

    operand_reference_id = models.OneToOneField(
        "OperandReference",
        on_delete=models.DO_NOTHING,
        db_column="OperandReferenceID",
        primary_key=True,
    )
    cell_id = models.ForeignKey(
        "Cell",
        on_delete=models.DO_NOTHING,
        db_column="CellID",
        null=True,
        blank=True,
    )
    table = models.CharField(
        db_column="Table",
        max_length=255,
        null=True,
        blank=True,
    )
    row = models.CharField(
        db_column="Row",
        max_length=255,
        null=True,
        blank=True,
    )
    column = models.CharField(
        db_column="Column",
        max_length=255,
        null=True,
        blank=True,
    )
    sheet = models.CharField(
        db_column="Sheet",
        max_length=255,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "OperandReferenceLocation"
        app_label = "dpmcore_django"
