"""Django models for DPM glossary entities."""

from django.db import models


class Category(models.Model):
    """Enumerated or reference-data grouping."""

    category_id = models.IntegerField(
        db_column="CategoryID",
        primary_key=True,
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
    description = models.CharField(
        db_column="Description",
        max_length=1000,
        null=True,
        blank=True,
    )
    is_enumerated = models.BooleanField(
        db_column="IsEnumerated",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(
        db_column="IsActive",
        null=True,
        blank=True,
    )
    is_external_ref_data = models.BooleanField(
        db_column="IsExternalRefData",
        null=True,
        blank=True,
    )
    ref_data_source = models.CharField(
        db_column="RefDataSource",
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
    created_release = models.IntegerField(
        db_column="CreatedRelease",
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
        db_table = "Category"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.code or str(self.category_id)


class SubCategory(models.Model):
    """Alternative grouping within a Category."""

    subcategory_id = models.IntegerField(
        db_column="SubCategoryID",
        primary_key=True,
    )
    category_id = models.ForeignKey(
        "Category",
        on_delete=models.DO_NOTHING,
        db_column="CategoryID",
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
        max_length=500,
        null=True,
        blank=True,
    )
    description = models.CharField(
        db_column="Description",
        max_length=500,
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
        db_table = "SubCategory"
        app_label = "dpmcore_django"


class SubCategoryVersion(models.Model):
    """Release-versioned snapshot of a SubCategory."""

    subcategory_vid = models.IntegerField(
        db_column="SubCategoryVID",
        primary_key=True,
    )
    subcategory_id = models.ForeignKey(
        "SubCategory",
        on_delete=models.DO_NOTHING,
        db_column="SubCategoryID",
        null=True,
        blank=True,
    )
    start_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="StartReleaseID",
        related_name="subcategory_version_starts",
        null=True,
        blank=True,
    )
    end_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="EndReleaseID",
        related_name="subcategory_version_ends",
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
        db_table = "SubCategoryVersion"
        app_label = "dpmcore_django"


class SubCategoryItem(models.Model):
    """An Item within a SubCategoryVersion, with ordering."""

    id = models.AutoField(primary_key=True)
    item_id = models.ForeignKey(
        "Item",
        on_delete=models.DO_NOTHING,
        db_column="ItemID",
        related_name="subcategory_items",
    )
    subcategory_vid = models.ForeignKey(
        "SubCategoryVersion",
        on_delete=models.DO_NOTHING,
        db_column="SubCategoryVID",
    )
    order = models.IntegerField(
        db_column="Order",
        null=True,
        blank=True,
    )
    label = models.CharField(
        db_column="Label",
        max_length=200,
        null=True,
        blank=True,
    )
    parent_item_id = models.ForeignKey(
        "Item",
        on_delete=models.DO_NOTHING,
        db_column="ParentItemID",
        related_name="child_subcategory_items",
        null=True,
        blank=True,
    )
    comparison_operator_id = models.ForeignKey(
        "Operator",
        on_delete=models.DO_NOTHING,
        db_column="ComparisonOperatorID",
        related_name="comparison_subcategory_items",
        null=True,
        blank=True,
    )
    arithmetic_operator_id = models.ForeignKey(
        "Operator",
        on_delete=models.DO_NOTHING,
        db_column="ArithmeticOperatorID",
        related_name="arithmetic_subcategory_items",
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
        db_table = "SubCategoryItem"
        app_label = "dpmcore_django"
        unique_together = (
            ("item_id", "subcategory_vid"),
        )


class Item(models.Model):
    """Concrete category member (enumerated value)."""

    item_id = models.IntegerField(
        db_column="ItemID",
        primary_key=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=500,
        null=True,
        blank=True,
    )
    description = models.CharField(
        db_column="Description",
        max_length=2000,
        null=True,
        blank=True,
    )
    is_property = models.BooleanField(
        db_column="IsProperty",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(
        db_column="IsActive",
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
        db_table = "Item"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.name or str(self.item_id)


class ItemCategory(models.Model):
    """Release-versioned link between an Item and a Category."""

    id = models.AutoField(primary_key=True)
    item_id = models.ForeignKey(
        "Item",
        on_delete=models.DO_NOTHING,
        db_column="ItemID",
    )
    start_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="StartReleaseID",
        related_name="item_category_starts",
    )
    category_id = models.ForeignKey(
        "Category",
        on_delete=models.DO_NOTHING,
        db_column="CategoryID",
        null=True,
        blank=True,
    )
    code = models.CharField(
        db_column="Code",
        max_length=20,
        null=True,
        blank=True,
    )
    is_default_item = models.BooleanField(
        db_column="IsDefaultItem",
        null=True,
        blank=True,
    )
    signature = models.CharField(
        db_column="Signature",
        max_length=255,
        null=True,
        blank=True,
    )
    end_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="EndReleaseID",
        related_name="item_category_ends",
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
        db_table = "ItemCategory"
        app_label = "dpmcore_django"
        unique_together = (
            ("item_id", "start_release_id"),
        )


class Property(models.Model):
    """Aspect or characteristic linked to an Item."""

    property_id = models.OneToOneField(
        "Item",
        on_delete=models.DO_NOTHING,
        db_column="PropertyID",
        primary_key=True,
    )
    is_composite = models.BooleanField(
        db_column="IsComposite",
        null=True,
        blank=True,
    )
    is_metric = models.BooleanField(
        db_column="IsMetric",
        null=True,
        blank=True,
    )
    data_type_id = models.ForeignKey(
        "DataType",
        on_delete=models.DO_NOTHING,
        db_column="DataTypeID",
        null=True,
        blank=True,
    )
    value_length = models.IntegerField(
        db_column="ValueLength",
        null=True,
        blank=True,
    )
    period_type = models.CharField(
        db_column="PeriodType",
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
        db_table = "Property"
        app_label = "dpmcore_django"


class PropertyCategory(models.Model):
    """Release-versioned link between a Property and a Category."""

    id = models.AutoField(primary_key=True)
    property_id = models.ForeignKey(
        "Property",
        on_delete=models.DO_NOTHING,
        db_column="PropertyID",
    )
    start_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="StartReleaseID",
        related_name="property_category_starts",
    )
    category_id = models.ForeignKey(
        "Category",
        on_delete=models.DO_NOTHING,
        db_column="CategoryID",
        null=True,
        blank=True,
    )
    end_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="EndReleaseID",
        related_name="property_category_ends",
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
        db_table = "PropertyCategory"
        app_label = "dpmcore_django"
        unique_together = (
            ("property_id", "start_release_id"),
        )


class Context(models.Model):
    """Reusable signature grouping Properties."""

    context_id = models.IntegerField(
        db_column="ContextID",
        primary_key=True,
    )
    signature = models.CharField(
        db_column="Signature",
        max_length=2000,
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
        db_table = "Context"
        app_label = "dpmcore_django"


class ContextComposition(models.Model):
    """Maps Properties and Items within a Context."""

    id = models.AutoField(primary_key=True)
    context_id = models.ForeignKey(
        "Context",
        on_delete=models.DO_NOTHING,
        db_column="ContextID",
    )
    property_id = models.ForeignKey(
        "Property",
        on_delete=models.DO_NOTHING,
        db_column="PropertyID",
    )
    item_id = models.ForeignKey(
        "Item",
        on_delete=models.DO_NOTHING,
        db_column="ItemID",
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
        db_table = "ContextComposition"
        app_label = "dpmcore_django"
        unique_together = (
            ("context_id", "property_id"),
        )


class CompoundItemContext(models.Model):
    """Release-versioned association of a compound Item."""

    id = models.AutoField(primary_key=True)
    item_id = models.ForeignKey(
        "Item",
        on_delete=models.DO_NOTHING,
        db_column="ItemID",
    )
    start_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="StartReleaseID",
        related_name="compound_item_context_starts",
    )
    context_id = models.ForeignKey(
        "Context",
        on_delete=models.DO_NOTHING,
        db_column="ContextID",
        null=True,
        blank=True,
    )
    end_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="EndReleaseID",
        related_name="compound_item_context_ends",
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
        db_table = "CompoundItemContext"
        app_label = "dpmcore_django"
        unique_together = (
            ("item_id", "start_release_id"),
        )


class SupercategoryComposition(models.Model):
    """Composition link between a super-category and a category."""

    id = models.AutoField(primary_key=True)
    supercategory_id = models.ForeignKey(
        "Category",
        on_delete=models.DO_NOTHING,
        db_column="SuperCategoryID",
        related_name="supercategory_compositions",
    )
    category_id = models.ForeignKey(
        "Category",
        on_delete=models.DO_NOTHING,
        db_column="CategoryID",
        related_name="category_compositions",
    )
    start_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="StartReleaseID",
        related_name="supercategory_composition_starts",
        null=True,
        blank=True,
    )
    end_release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="EndReleaseID",
        related_name="supercategory_composition_ends",
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
        db_table = "SuperCategoryComposition"
        app_label = "dpmcore_django"
        unique_together = (
            ("supercategory_id", "category_id"),
        )
