"""Django models for auxiliary and mapping entities."""

from django.db import models


class AuxCellMapping(models.Model):
    """Maps new cell/table identifiers to their old equivalents."""

    new_cell_id = models.IntegerField(
        db_column="NewCellID",
        primary_key=True,
    )
    new_table_vid = models.IntegerField(
        db_column="NewTableVID",
    )
    old_cell_id = models.IntegerField(
        db_column="OldCellID",
        null=True,
        blank=True,
    )
    old_table_vid = models.IntegerField(
        db_column="OldTableVID",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "Aux_CellMapping"
        app_label = "dpmcore_django"
        unique_together = (
            ("new_cell_id", "new_table_vid"),
        )


class AuxCellStatus(models.Model):
    """Tracks the status and novelty of a cell."""

    table_vid = models.IntegerField(
        db_column="TableVID",
        primary_key=True,
    )
    cell_id = models.IntegerField(
        db_column="CellID",
    )
    status = models.CharField(
        db_column="Status",
        max_length=100,
        null=True,
        blank=True,
    )
    is_new_cell = models.BooleanField(
        db_column="IsNewCell",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "Aux_CellStatus"
        app_label = "dpmcore_django"
        unique_together = (("table_vid", "cell_id"),)
        verbose_name = "aux cell status"
        verbose_name_plural = "aux cell statuses"


class ModelViolations(models.Model):
    """Records structural or semantic violations."""

    violation_code = models.CharField(
        db_column="ViolationCode",
        max_length=10,
        primary_key=True,
    )
    violation = models.CharField(
        db_column="Violation",
        max_length=255,
        null=True,
        blank=True,
    )
    is_blocking = models.BooleanField(
        db_column="isBlocking",
        null=True,
        blank=True,
    )
    table_vid = models.IntegerField(
        db_column="TableVID",
        null=True,
        blank=True,
    )
    old_table_vid = models.IntegerField(
        db_column="OldTableVID",
        null=True,
        blank=True,
    )
    table_code = models.CharField(
        db_column="TableCode",
        max_length=40,
        null=True,
        blank=True,
    )
    header_id = models.IntegerField(
        db_column="HeaderID",
        null=True,
        blank=True,
    )
    header_code = models.CharField(
        db_column="HeaderCode",
        max_length=20,
        null=True,
        blank=True,
    )
    header_vid = models.IntegerField(
        db_column="HeaderVID",
        null=True,
        blank=True,
    )
    old_header_vid = models.IntegerField(
        db_column="OldHeaderVID",
        null=True,
        blank=True,
    )
    key_header = models.BooleanField(
        db_column="KeyHeader",
        null=True,
        blank=True,
    )
    header_direction = models.CharField(
        db_column="HeaderDirection",
        max_length=1,
        null=True,
        blank=True,
    )
    header_property_id = models.IntegerField(
        db_column="HeaderPropertyID",
        null=True,
        blank=True,
    )
    header_property_code = models.CharField(
        db_column="HeaderPropertyCode",
        max_length=20,
        null=True,
        blank=True,
    )
    header_subcategory_id = models.IntegerField(
        db_column="HeaderSubcategoryID",
        null=True,
        blank=True,
    )
    header_subcategory_name = models.CharField(
        db_column="HeaderSubcategoryName",
        max_length=60,
        null=True,
        blank=True,
    )
    header_context_id = models.IntegerField(
        db_column="HeaderContextID",
        null=True,
        blank=True,
    )
    category_id = models.IntegerField(
        db_column="CategoryID",
        null=True,
        blank=True,
    )
    category_code = models.CharField(
        db_column="CategoryCode",
        max_length=30,
        null=True,
        blank=True,
    )
    item_id = models.IntegerField(
        db_column="ItemID",
        null=True,
        blank=True,
    )
    item_code = models.CharField(
        db_column="ItemCode",
        max_length=30,
        null=True,
        blank=True,
    )
    cell_id = models.IntegerField(
        db_column="CellID",
        null=True,
        blank=True,
    )
    cell_code = models.CharField(
        db_column="CellCode",
        max_length=50,
        null=True,
        blank=True,
    )
    cell2_id = models.IntegerField(
        db_column="Cell2ID",
        null=True,
        blank=True,
    )
    cell2_code = models.CharField(
        db_column="Cell2Code",
        max_length=50,
        null=True,
        blank=True,
    )
    vv_end_release_id = models.IntegerField(
        db_column="VVEndReleaseID",
        null=True,
        blank=True,
    )
    new_aspect = models.CharField(
        db_column="NewAspect",
        max_length=80,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "ModelViolations"
        app_label = "dpmcore_django"
        verbose_name = "model violation"
        verbose_name_plural = "model violations"
