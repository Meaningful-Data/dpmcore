"""Django models for DPM rendering entities."""

from django.db import models


class Table(models.Model):
    """Top-level reporting table."""

    table_id = models.IntegerField(
        db_column="TableID",
        primary_key=True,
    )
    is_abstract = models.BooleanField(
        db_column="IsAbstract",
        null=True,
        blank=True,
    )
    has_open_columns = models.BooleanField(
        db_column="HasOpenColumns",
        null=True,
        blank=True,
    )
    has_open_rows = models.BooleanField(
        db_column="HasOpenRows",
        null=True,
        blank=True,
    )
    has_open_sheets = models.BooleanField(
        db_column="HasOpenSheets",
        null=True,
        blank=True,
    )
    is_normalised = models.BooleanField(
        db_column="IsNormalised",
        null=True,
        blank=True,
    )
    is_flat = models.BooleanField(
        db_column="IsFlat",
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
        db_table = "Table"
        app_label = "dpmcore_django"


class TableVersion(models.Model):
    """Release-versioned snapshot of a Table."""

    table_vid = models.IntegerField(
        db_column="TableVID",
        primary_key=True,
    )
    code = models.CharField(
        db_column="Code",
        max_length=30,
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
        max_length=500,
        null=True,
        blank=True,
    )
    table_id = models.ForeignKey(
        "Table",
        on_delete=models.DO_NOTHING,
        db_column="TableID",
        related_name="table_versions",
        null=True,
        blank=True,
    )
    abstract_table_id = models.ForeignKey(
        "Table",
        on_delete=models.DO_NOTHING,
        db_column="AbstractTableID",
        related_name="abstract_table_versions",
        null=True,
        blank=True,
    )
    key_id = models.ForeignKey(
        "CompoundKey",
        on_delete=models.DO_NOTHING,
        db_column="KeyID",
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
    context_id = models.ForeignKey(
        "Context",
        on_delete=models.DO_NOTHING,
        db_column="ContextID",
        null=True,
        blank=True,
    )
    start_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="StartReleaseID",
        related_name="table_version_starts",
        null=True,
        blank=True,
    )
    end_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="EndReleaseID",
        related_name="table_version_ends",
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
        db_table = "TableVersion"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.code or str(self.table_vid)


class Header(models.Model):
    """Header axis (column, row, or sheet) within a Table."""

    header_id = models.IntegerField(
        db_column="HeaderID",
        primary_key=True,
    )
    table_id = models.ForeignKey(
        "Table",
        on_delete=models.DO_NOTHING,
        db_column="TableID",
        null=True,
        blank=True,
    )
    direction = models.CharField(
        db_column="Direction",
        max_length=1,
        null=True,
        blank=True,
    )
    is_key = models.BooleanField(
        db_column="IsKey",
        null=True,
        blank=True,
    )
    is_attribute = models.BooleanField(
        db_column="IsAttribute",
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
        db_table = "Header"
        app_label = "dpmcore_django"


class HeaderVersion(models.Model):
    """Release-versioned snapshot of a Header."""

    header_vid = models.IntegerField(
        db_column="HeaderVID",
        primary_key=True,
    )
    header_id = models.ForeignKey(
        "Header",
        on_delete=models.DO_NOTHING,
        db_column="HeaderID",
        null=True,
        blank=True,
    )
    code = models.CharField(
        db_column="Code",
        max_length=10,
        null=True,
        blank=True,
    )
    label = models.CharField(
        db_column="Label",
        max_length=500,
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
    context_id = models.ForeignKey(
        "Context",
        on_delete=models.DO_NOTHING,
        db_column="ContextID",
        null=True,
        blank=True,
    )
    subcategory_vid = models.ForeignKey(
        "SubCategoryVersion",
        on_delete=models.DO_NOTHING,
        db_column="SubCategoryVID",
        null=True,
        blank=True,
    )
    key_variable_vid = models.ForeignKey(
        "VariableVersion",
        on_delete=models.DO_NOTHING,
        db_column="KeyVariableVID",
        null=True,
        blank=True,
    )
    start_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="StartReleaseID",
        related_name="header_version_starts",
        null=True,
        blank=True,
    )
    end_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="EndReleaseID",
        related_name="header_version_ends",
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
        return self.code or str(self.header_vid)

    class Meta:
        managed = False
        db_table = "HeaderVersion"
        app_label = "dpmcore_django"


class Cell(models.Model):
    """Intersection point in a Table."""

    cell_id = models.IntegerField(
        db_column="CellID",
        primary_key=True,
    )
    table_id = models.ForeignKey(
        "Table",
        on_delete=models.DO_NOTHING,
        db_column="TableID",
        null=True,
        blank=True,
    )
    column_id = models.ForeignKey(
        "Header",
        on_delete=models.DO_NOTHING,
        db_column="ColumnID",
        related_name="column_cells",
        null=True,
        blank=True,
    )
    row_id = models.ForeignKey(
        "Header",
        on_delete=models.DO_NOTHING,
        db_column="RowID",
        related_name="row_cells",
        null=True,
        blank=True,
    )
    sheet_id = models.ForeignKey(
        "Header",
        on_delete=models.DO_NOTHING,
        db_column="SheetID",
        related_name="sheet_cells",
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
        db_table = "Cell"
        app_label = "dpmcore_django"


class TableVersionCell(models.Model):
    """Release-scoped cell configuration within a TableVersion."""

    table_vid = models.ForeignKey(
        "TableVersion",
        on_delete=models.DO_NOTHING,
        db_column="TableVID",
        primary_key=True,
    )
    cell_id = models.ForeignKey(
        "Cell",
        on_delete=models.DO_NOTHING,
        db_column="CellID",
    )
    cell_code = models.CharField(
        db_column="CellCode",
        max_length=100,
        null=True,
        blank=True,
    )
    is_nullable = models.BooleanField(
        db_column="IsNullable",
        null=True,
        blank=True,
    )
    is_excluded = models.BooleanField(
        db_column="IsExcluded",
        null=True,
        blank=True,
    )
    is_void = models.BooleanField(
        db_column="IsVoid",
        null=True,
        blank=True,
    )
    sign = models.CharField(
        db_column="Sign",
        max_length=8,
        null=True,
        blank=True,
    )
    variable_vid = models.ForeignKey(
        "VariableVersion",
        on_delete=models.DO_NOTHING,
        db_column="VariableVID",
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
        db_table = "TableVersionCell"
        app_label = "dpmcore_django"
        unique_together = (("table_vid", "cell_id"),)


class TableVersionHeader(models.Model):
    """Ordered header assignment within a TableVersion."""

    table_vid = models.ForeignKey(
        "TableVersion",
        on_delete=models.DO_NOTHING,
        db_column="TableVID",
        primary_key=True,
    )
    header_id = models.ForeignKey(
        "Header",
        on_delete=models.DO_NOTHING,
        db_column="HeaderID",
        related_name="table_version_headers",
    )
    header_vid = models.ForeignKey(
        "HeaderVersion",
        on_delete=models.DO_NOTHING,
        db_column="HeaderVID",
        null=True,
        blank=True,
    )
    parent_header_id = models.ForeignKey(
        "Header",
        on_delete=models.DO_NOTHING,
        db_column="ParentHeaderID",
        related_name="child_table_version_headers",
        null=True,
        blank=True,
    )
    parent_first = models.BooleanField(
        db_column="ParentFirst",
        null=True,
        blank=True,
    )
    order = models.IntegerField(
        db_column="Order",
        null=True,
        blank=True,
    )
    is_abstract = models.BooleanField(
        db_column="IsAbstract",
        null=True,
        blank=True,
    )
    is_unique = models.BooleanField(
        db_column="IsUnique",
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
        db_table = "TableVersionHeader"
        app_label = "dpmcore_django"
        unique_together = (
            ("table_vid", "header_id"),
        )


class TableGroup(models.Model):
    """Logical grouping of tables for navigation."""

    table_group_id = models.IntegerField(
        db_column="TableGroupID",
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
        max_length=2000,
        null=True,
        blank=True,
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
    start_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="StartReleaseID",
        related_name="table_group_starts",
        null=True,
        blank=True,
    )
    end_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="EndReleaseID",
        related_name="table_group_ends",
        null=True,
        blank=True,
    )
    parent_table_group_id = models.ForeignKey(
        "self",
        on_delete=models.DO_NOTHING,
        db_column="ParentTableGroupID",
        null=True,
        blank=True,
    )
    owner_id = models.IntegerField(
        db_column="OwnerID",
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return self.code or str(self.table_group_id)

    class Meta:
        managed = False
        db_table = "TableGroup"
        app_label = "dpmcore_django"


class TableGroupComposition(models.Model):
    """Links Tables to TableGroups with ordering."""

    table_group_id = models.ForeignKey(
        "TableGroup",
        on_delete=models.DO_NOTHING,
        db_column="TableGroupID",
        primary_key=True,
    )
    table_id = models.ForeignKey(
        "Table",
        on_delete=models.DO_NOTHING,
        db_column="TableID",
    )
    order = models.IntegerField(
        db_column="Order",
        null=True,
        blank=True,
    )
    start_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="StartReleaseID",
        related_name="table_group_composition_starts",
        null=True,
        blank=True,
    )
    end_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="EndReleaseID",
        related_name="table_group_composition_ends",
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
        db_table = "TableGroupComposition"
        app_label = "dpmcore_django"
        unique_together = (
            ("table_group_id", "table_id"),
        )


class TableAssociation(models.Model):
    """Parent-child relationship between TableVersions."""

    association_id = models.IntegerField(
        db_column="AssociationID",
        primary_key=True,
    )
    child_table_vid = models.ForeignKey(
        "TableVersion",
        on_delete=models.DO_NOTHING,
        db_column="ChildTableVID",
        related_name="table_associations_as_child",
        null=True,
        blank=True,
    )
    parent_table_vid = models.ForeignKey(
        "TableVersion",
        on_delete=models.DO_NOTHING,
        db_column="ParentTableVID",
        related_name="table_associations_as_parent",
        null=True,
        blank=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=50,
        null=True,
        blank=True,
    )
    description = models.CharField(
        db_column="Description",
        max_length=255,
        null=True,
        blank=True,
    )
    is_identifying = models.BooleanField(
        db_column="IsIdentifying",
        null=True,
        blank=True,
    )
    is_subtype = models.BooleanField(
        db_column="IsSubtype",
        null=True,
        blank=True,
    )
    subtype_discriminator = models.ForeignKey(
        "Header",
        on_delete=models.DO_NOTHING,
        db_column="SubtypeDiscriminator",
        related_name="subtype_discriminator_associations",
        null=True,
        blank=True,
    )
    parent_cardinality = models.CharField(
        db_column="ParentCardinalityAndOptionality",
        max_length=3,
        null=True,
        blank=True,
    )
    child_cardinality = models.CharField(
        db_column="ChildCardinalityAndOptionality",
        max_length=3,
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
        return self.name or str(self.association_id)

    class Meta:
        managed = False
        db_table = "TableAssociation"
        app_label = "dpmcore_django"


class KeyHeaderMapping(models.Model):
    """Maps foreign-key headers to primary-key headers."""

    association_id = models.ForeignKey(
        "TableAssociation",
        on_delete=models.DO_NOTHING,
        db_column="AssociationID",
        primary_key=True,
    )
    foreign_key_header_id = models.ForeignKey(
        "Header",
        on_delete=models.DO_NOTHING,
        db_column="ForeignKeyHeaderID",
        related_name="fk_header_mappings",
    )
    primary_key_header_id = models.ForeignKey(
        "Header",
        on_delete=models.DO_NOTHING,
        db_column="PrimaryKeyHeaderID",
        related_name="pk_header_mappings",
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
        db_table = "KeyHeaderMapping"
        app_label = "dpmcore_django"
        unique_together = (
            ("association_id", "foreign_key_header_id"),
        )
