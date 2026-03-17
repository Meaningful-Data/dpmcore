"""Django models for DPM packaging domain."""

from django.db import models


class Framework(models.Model):
    """Regulatory or reporting framework."""

    framework_id = models.IntegerField(
        db_column="FrameworkID",
        primary_key=True,
    )
    code = models.CharField(
        db_column="Code",
        max_length=255,
        null=True,
        blank=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=255,
        null=True,
        blank=True,
    )
    description = models.CharField(
        db_column="Description",
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

    class Meta:
        managed = False
        db_table = "Framework"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.code or str(self.framework_id)


class Module(models.Model):
    """Logical grouping within a Framework."""

    module_id = models.IntegerField(
        db_column="ModuleID",
        primary_key=True,
    )
    framework_id = models.ForeignKey(
        "Framework",
        on_delete=models.DO_NOTHING,
        db_column="FrameworkID",
        null=True,
        blank=True,
    )
    row_guid = models.CharField(
        db_column="RowGUID",
        max_length=36,
        null=True,
        blank=True,
    )
    is_document_module = models.BooleanField(
        db_column="isDocumentModule",
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
        db_table = "Module"
        app_label = "dpmcore_django"


class ModuleVersion(models.Model):
    """Release-versioned snapshot of a Module."""

    module_vid = models.IntegerField(
        db_column="ModuleVID",
        primary_key=True,
    )
    module_id = models.ForeignKey(
        "Module",
        on_delete=models.DO_NOTHING,
        db_column="ModuleID",
        null=True,
        blank=True,
    )
    global_key_id = models.ForeignKey(
        "CompoundKey",
        on_delete=models.DO_NOTHING,
        db_column="GlobalKeyID",
        null=True,
        blank=True,
    )
    start_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="StartReleaseID",
        related_name="module_version_starts",
        null=True,
        blank=True,
    )
    end_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="EndReleaseID",
        related_name="module_version_ends",
        null=True,
        blank=True,
    )
    code = models.CharField(
        db_column="Code",
        max_length=30,
        null=True,
        blank=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=100,
        null=True,
        blank=True,
    )
    description = models.CharField(
        db_column="Description",
        max_length=255,
        null=True,
        blank=True,
    )
    version_number = models.CharField(
        db_column="VersionNumber",
        max_length=20,
        null=True,
        blank=True,
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
    is_reported = models.BooleanField(
        db_column="IsReported",
        null=True,
        blank=True,
    )
    is_calculated = models.BooleanField(
        db_column="IsCalculated",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "ModuleVersion"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.code or str(self.module_vid)


class ModuleVersionComposition(models.Model):
    """Links a ModuleVersion to its constituent Tables."""

    module_vid = models.ForeignKey(
        "ModuleVersion",
        on_delete=models.DO_NOTHING,
        db_column="ModuleVID",
        primary_key=True,
    )
    table_id = models.ForeignKey(
        "Table",
        on_delete=models.DO_NOTHING,
        db_column="TableID",
    )
    table_vid = models.ForeignKey(
        "TableVersion",
        on_delete=models.DO_NOTHING,
        db_column="TableVID",
        null=True,
        blank=True,
    )
    order = models.IntegerField(
        db_column="Order",
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
        db_table = "ModuleVersionComposition"
        app_label = "dpmcore_django"
        unique_together = (
            ("module_vid", "table_id"),
        )


class ModuleParameters(models.Model):
    """Parameter variable bound to a ModuleVersion."""

    module_vid = models.ForeignKey(
        "ModuleVersion",
        on_delete=models.DO_NOTHING,
        db_column="ModuleVID",
        primary_key=True,
    )
    variable_vid = models.ForeignKey(
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
        db_table = "ModuleParameters"
        app_label = "dpmcore_django"
        verbose_name = "module parameter"
        verbose_name_plural = "module parameters"
        unique_together = (
            ("module_vid", "variable_vid"),
        )


class OperationCodePrefix(models.Model):
    """Operation code prefix scoped to a Framework."""

    operation_code_prefix_id = models.IntegerField(
        db_column="OperationCodePrefixID",
        primary_key=True,
    )
    code = models.CharField(
        db_column="Code",
        max_length=20,
        null=True,
        blank=True,
    )
    list_name = models.CharField(
        db_column="ListName",
        max_length=20,
        null=True,
        blank=True,
    )
    framework_id = models.ForeignKey(
        "Framework",
        on_delete=models.DO_NOTHING,
        db_column="FrameworkID",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "OperationCodePrefix"
        app_label = "dpmcore_django"
