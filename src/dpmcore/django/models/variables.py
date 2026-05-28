"""Django models for DPM variables domain."""

from django.db import models


class Variable(models.Model):
    """Core variable entity."""

    variable_id = models.IntegerField(
        db_column="VariableID",
        primary_key=True,
    )
    type = models.CharField(
        db_column="Type",
        max_length=20,
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
        db_table = "Variable"
        app_label = "dpmcore_django"


class VariableVersion(models.Model):
    """Versioned snapshot of a Variable."""

    variable_vid = models.IntegerField(
        db_column="VariableVID",
        primary_key=True,
    )
    variable = models.ForeignKey(
        "Variable",
        on_delete=models.DO_NOTHING,
        db_column="VariableID",
        null=True,
        blank=True,
    )
    property = models.ForeignKey(
        "Property",
        on_delete=models.DO_NOTHING,
        db_column="PropertyID",
        null=True,
        blank=True,
    )
    subcategory_version = models.ForeignKey(
        "SubCategoryVersion",
        on_delete=models.DO_NOTHING,
        db_column="SubCategoryVID",
        null=True,
        blank=True,
    )
    context = models.ForeignKey(
        "Context",
        on_delete=models.DO_NOTHING,
        db_column="ContextID",
        null=True,
        blank=True,
    )
    key = models.ForeignKey(
        "CompoundKey",
        on_delete=models.DO_NOTHING,
        db_column="KeyID",
        null=True,
        blank=True,
    )
    is_multi_valued = models.BooleanField(
        db_column="IsMultiValued",
        null=True,
        blank=True,
    )
    code = models.CharField(
        db_column="Code",
        max_length=20,
        null=True,
        blank=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=50,
        null=True,
        blank=True,
    )
    start_release = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="StartReleaseID",
        related_name="variable_version_starts",
        null=True,
        blank=True,
    )
    end_release = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="EndReleaseID",
        related_name="variable_version_ends",
        null=True,
        blank=True,
    )
    row_guid = models.CharField(
        db_column="RowGUID",
        max_length=36,
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return self.code or str(self.variable_vid)

    class Meta:
        managed = False
        db_table = "VariableVersion"
        app_label = "dpmcore_django"


class VariableCalculation(models.Model):
    """Link between a Module, Variable, and OperationVersion."""

    module = models.ForeignKey(
        "Module",
        on_delete=models.DO_NOTHING,
        db_column="ModuleID",
        primary_key=True,
    )
    variable = models.ForeignKey(
        "Variable",
        on_delete=models.DO_NOTHING,
        db_column="VariableID",
    )
    operation_version = models.ForeignKey(
        "OperationVersion",
        on_delete=models.DO_NOTHING,
        db_column="OperationVID",
    )
    from_reference_date = models.DateField(
        db_column="FromReferenceDate",
        null=True,
        blank=True,
    )
    to_reference_date = models.DateField(
        db_column="ToReferenceDate",
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
        db_table = "VariableCalculation"
        app_label = "dpmcore_django"
        unique_together = (("module", "variable", "operation_version"),)


class CompoundKey(models.Model):
    """Composite key definition for Variables."""

    key_id = models.IntegerField(
        db_column="KeyID",
        primary_key=True,
    )
    signature = models.CharField(
        db_column="Signature",
        max_length=255,
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

    def __str__(self) -> str:
        return self.signature or str(self.key_id)

    class Meta:
        managed = False
        db_table = "CompoundKey"
        app_label = "dpmcore_django"


class KeyComposition(models.Model):
    """Association between CompoundKey and VariableVersion."""

    key = models.ForeignKey(
        "CompoundKey",
        on_delete=models.DO_NOTHING,
        db_column="KeyID",
        primary_key=True,
    )
    variable_version = models.ForeignKey(
        "VariableVersion",
        on_delete=models.DO_NOTHING,
        db_column="VariableVID",
    )
    row_guid = models.CharField(
        db_column="RowGUID",
        max_length=36,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "KeyComposition"
        app_label = "dpmcore_django"
        unique_together = (("key", "variable_version"),)
