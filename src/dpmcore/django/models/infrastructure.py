"""Django models for DPM infrastructure entities."""

from django.db import models


class Concept(models.Model):
    """Universal identity object."""

    concept_guid = models.CharField(
        db_column="ConceptGUID",
        max_length=36,
        primary_key=True,
    )
    class_id = models.ForeignKey(
        "DpmClass",
        on_delete=models.DO_NOTHING,
        db_column="ClassID",
        null=True,
        blank=True,
    )
    owner_id = models.ForeignKey(
        "Organisation",
        on_delete=models.DO_NOTHING,
        db_column="OwnerID",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "Concept"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.concept_guid


class ConceptRelation(models.Model):
    """Relation between two Concepts."""

    concept_relation_id = models.IntegerField(
        db_column="ConceptRelationID",
        primary_key=True,
    )
    type = models.CharField(
        db_column="Type",
        max_length=50,
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
        db_table = "ConceptRelation"
        app_label = "dpmcore_django"


class RelatedConcept(models.Model):
    """Association between a Concept and a ConceptRelation."""

    id = models.AutoField(primary_key=True)
    concept_guid = models.ForeignKey(
        "Concept",
        on_delete=models.DO_NOTHING,
        db_column="ConceptGUID",
    )
    concept_relation_id = models.ForeignKey(
        "ConceptRelation",
        on_delete=models.DO_NOTHING,
        db_column="ConceptRelationID",
    )
    is_related_concept = models.BooleanField(
        db_column="IsRelatedConcept",
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
        db_table = "RelatedConcept"
        app_label = "dpmcore_django"
        unique_together = (
            ("concept_guid", "concept_relation_id"),
        )


class Organisation(models.Model):
    """Data owner / maintainer organisation."""

    org_id = models.IntegerField(
        db_column="OrgID",
        primary_key=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=200,
        null=True,
        blank=True,
    )
    acronym = models.CharField(
        db_column="Acronym",
        max_length=20,
        null=True,
        blank=True,
    )
    id_prefix = models.IntegerField(
        db_column="IDPrefix",
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
        db_table = "Organisation"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.name or str(self.org_id)


class Language(models.Model):
    """Language code reference."""

    language_code = models.IntegerField(
        db_column="LanguageCode",
        primary_key=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=20,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "Language"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.name or str(self.language_code)


class User(models.Model):
    """User account."""

    user_id = models.IntegerField(
        db_column="UserID",
        primary_key=True,
    )
    org_id = models.ForeignKey(
        "Organisation",
        on_delete=models.DO_NOTHING,
        db_column="OrgID",
        null=True,
        blank=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=50,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "User"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.name or str(self.user_id)


class Role(models.Model):
    """Access role."""

    role_id = models.IntegerField(
        db_column="RoleID",
        primary_key=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=50,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "Role"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.name or str(self.role_id)


class UserRole(models.Model):
    """Many-to-many link between User and Role."""

    id = models.AutoField(primary_key=True)
    user_id = models.ForeignKey(
        "User",
        on_delete=models.DO_NOTHING,
        db_column="UserID",
    )
    role_id = models.ForeignKey(
        "Role",
        on_delete=models.DO_NOTHING,
        db_column="RoleID",
    )

    class Meta:
        managed = False
        db_table = "UserRole"
        app_label = "dpmcore_django"
        unique_together = (("user_id", "role_id"),)


class DataType(models.Model):
    """Data type definition."""

    data_type_id = models.IntegerField(
        db_column="DataTypeID",
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
    parent_data_type_id = models.ForeignKey(
        "self",
        on_delete=models.DO_NOTHING,
        db_column="ParentDataTypeID",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(
        db_column="IsActive",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "DataType"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.code or str(self.data_type_id)


class DpmClass(models.Model):
    """DPM metamodel class definition."""

    class_id = models.IntegerField(
        db_column="ClassID",
        primary_key=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=50,
        null=True,
        blank=True,
    )
    type = models.CharField(
        db_column="Type",
        max_length=20,
        null=True,
        blank=True,
    )
    owner_class_id = models.ForeignKey(
        "self",
        on_delete=models.DO_NOTHING,
        db_column="OwnerClassID",
        null=True,
        blank=True,
    )
    has_references = models.BooleanField(
        db_column="HasReferences",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "DPMClass"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.name or str(self.class_id)


class DpmAttribute(models.Model):
    """Attribute of a DpmClass."""

    attribute_id = models.IntegerField(
        db_column="AttributeID",
        primary_key=True,
    )
    class_id = models.ForeignKey(
        "DpmClass",
        on_delete=models.DO_NOTHING,
        db_column="ClassID",
        null=True,
        blank=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=20,
        null=True,
        blank=True,
    )
    has_translations = models.BooleanField(
        db_column="HasTranslations",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "DPMAttribute"
        app_label = "dpmcore_django"


class Translation(models.Model):
    """Multilingual text translation."""

    id = models.AutoField(primary_key=True)
    concept_guid = models.ForeignKey(
        "Concept",
        on_delete=models.DO_NOTHING,
        db_column="ConceptGUID",
    )
    attribute_id = models.ForeignKey(
        "DpmAttribute",
        on_delete=models.DO_NOTHING,
        db_column="AttributeID",
    )
    translator_id = models.ForeignKey(
        "Organisation",
        on_delete=models.DO_NOTHING,
        db_column="TranslatorID",
    )
    language_code = models.ForeignKey(
        "Language",
        on_delete=models.DO_NOTHING,
        db_column="LanguageCode",
    )
    translation = models.TextField(
        db_column="Translation",
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
        db_table = "Translation"
        app_label = "dpmcore_django"
        unique_together = (
            (
                "concept_guid",
                "attribute_id",
                "translator_id",
                "language_code",
            ),
        )


class Changelog(models.Model):
    """Change tracking entry."""

    id = models.AutoField(primary_key=True)
    row_guid = models.CharField(
        db_column="RowGUID",
        max_length=36,
    )
    class_id = models.ForeignKey(
        "DpmClass",
        on_delete=models.DO_NOTHING,
        db_column="ClassID",
    )
    timestamp = models.IntegerField(
        db_column="Timestamp",
    )
    change_type = models.CharField(
        db_column="ChangeType",
        max_length=255,
        null=True,
        blank=True,
    )
    status = models.CharField(
        db_column="Status",
        max_length=1,
        null=True,
        blank=True,
    )
    user_email = models.CharField(
        db_column="UserEmail",
        max_length=255,
        null=True,
        blank=True,
    )
    release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="ReleaseID",
        null=True,
        blank=True,
    )
    entity_id = models.IntegerField(
        db_column="EntityID",
        null=True,
        blank=True,
    )
    entity_code = models.CharField(
        db_column="EntityCode",
        max_length=255,
        null=True,
        blank=True,
    )
    action_id = models.IntegerField(
        db_column="ActionID",
    )

    class Meta:
        managed = False
        db_table = "ChangeLog"
        app_label = "dpmcore_django"
        unique_together = (
            ("row_guid", "class_id", "timestamp"),
        )


class ChangelogAttribute(models.Model):
    """Attribute-level detail for a Changelog action."""

    changelog_attribute_id = models.IntegerField(
        db_column="ChangeLogAttributeID",
        primary_key=True,
    )
    action_id = models.IntegerField(
        db_column="ActionID",
    )
    attribute_id = models.ForeignKey(
        "DpmAttribute",
        on_delete=models.DO_NOTHING,
        db_column="AttributeID",
        null=True,
        blank=True,
    )
    old_value = models.CharField(
        db_column="OldValue",
        max_length=255,
        null=True,
        blank=True,
    )
    new_value = models.CharField(
        db_column="NewValue",
        max_length=255,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "ChangeLogAttribute"
        app_label = "dpmcore_django"


class Document(models.Model):
    """Supporting documentation."""

    document_id = models.IntegerField(
        db_column="DocumentID",
        primary_key=True,
    )
    name = models.CharField(
        db_column="Name",
        max_length=50,
        null=True,
        blank=True,
    )
    code = models.CharField(
        db_column="Code",
        max_length=20,
        null=True,
        blank=True,
    )
    type = models.CharField(
        db_column="Type",
        max_length=255,
        null=True,
        blank=True,
    )
    org_id = models.ForeignKey(
        "Organisation",
        on_delete=models.DO_NOTHING,
        db_column="OrgID",
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
        db_table = "Document"
        app_label = "dpmcore_django"


class DocumentVersion(models.Model):
    """Versioned snapshot of a Document."""

    document_vid = models.IntegerField(
        db_column="DocumentVID",
        primary_key=True,
    )
    document_id = models.ForeignKey(
        "Document",
        on_delete=models.DO_NOTHING,
        db_column="DocumentID",
        null=True,
        blank=True,
    )
    code = models.CharField(
        db_column="Code",
        max_length=20,
        null=True,
        blank=True,
    )
    version = models.CharField(
        db_column="Version",
        max_length=20,
        null=True,
        blank=True,
    )
    publication_date = models.DateField(
        db_column="PublicationDate",
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
        db_table = "DocumentVersion"
        app_label = "dpmcore_django"


class Subdivision(models.Model):
    """Geographic or structural subdivision."""

    subdivision_id = models.IntegerField(
        db_column="SubdivisionID",
        primary_key=True,
    )
    document_vid = models.ForeignKey(
        "DocumentVersion",
        on_delete=models.DO_NOTHING,
        db_column="DocumentVID",
        null=True,
        blank=True,
    )
    subdivision_type_id = models.ForeignKey(
        "SubdivisionType",
        on_delete=models.DO_NOTHING,
        db_column="SubdivisionTypeID",
        null=True,
        blank=True,
    )
    number = models.CharField(
        db_column="Number",
        max_length=20,
        null=True,
        blank=True,
    )
    parent_subdivision_id = models.ForeignKey(
        "self",
        on_delete=models.DO_NOTHING,
        db_column="ParentSubdivisionID",
        null=True,
        blank=True,
    )
    structure_path = models.CharField(
        db_column="StructurePath",
        max_length=255,
        null=True,
        blank=True,
    )
    text_excerpt = models.TextField(
        db_column="TextExcerpt",
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
        db_table = "Subdivision"
        app_label = "dpmcore_django"


class SubdivisionType(models.Model):
    """Subdivision type definition."""

    subdivision_type_id = models.IntegerField(
        db_column="SubdivisionTypeID",
        primary_key=True,
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

    class Meta:
        managed = False
        db_table = "SubdivisionType"
        app_label = "dpmcore_django"


class Reference(models.Model):
    """Link between a Subdivision and a Concept."""

    id = models.AutoField(primary_key=True)
    subdivision_id = models.ForeignKey(
        "Subdivision",
        on_delete=models.DO_NOTHING,
        db_column="SubdivisionID",
    )
    concept_guid = models.ForeignKey(
        "Concept",
        on_delete=models.DO_NOTHING,
        db_column="ConceptGUID",
    )
    row_guid = models.CharField(
        db_column="RowGUID",
        max_length=36,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "Reference"
        app_label = "dpmcore_django"
        unique_together = (
            ("subdivision_id", "concept_guid"),
        )


class Release(models.Model):
    """Publication milestone."""

    release_id = models.IntegerField(
        db_column="ReleaseID",
        primary_key=True,
    )
    code = models.CharField(
        db_column="Code",
        max_length=20,
        null=True,
        blank=True,
    )
    date = models.DateField(
        db_column="Date",
        null=True,
        blank=True,
    )
    description = models.CharField(
        db_column="Description",
        max_length=255,
        null=True,
        blank=True,
    )
    status = models.CharField(
        db_column="Status",
        max_length=50,
        null=True,
        blank=True,
    )
    is_current = models.BooleanField(
        db_column="IsCurrent",
        null=True,
        blank=True,
    )
    row_guid = models.CharField(
        db_column="RowGUID",
        max_length=36,
        null=True,
        blank=True,
    )
    error_date = models.DateTimeField(
        db_column="ErrorDate",
        null=True,
        blank=True,
    )
    type = models.CharField(
        db_column="Type",
        max_length=20,
        null=True,
        blank=True,
    )
    error = models.CharField(
        db_column="Error",
        max_length=4000,
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
        db_table = "Release"
        app_label = "dpmcore_django"

    def __str__(self) -> str:
        return self.code or str(self.release_id)


class VariableGeneration(models.Model):
    """Batch variable generation job."""

    variable_generation_id = models.IntegerField(
        db_column="VariableGenerationID",
        primary_key=True,
    )
    start_date = models.DateTimeField(
        db_column="StartDate",
        null=True,
        blank=True,
    )
    end_date = models.DateTimeField(
        db_column="EndDate",
        null=True,
        blank=True,
    )
    status = models.CharField(
        db_column="Status",
        max_length=50,
        null=True,
        blank=True,
    )
    release_id = models.ForeignKey(
        "Release",
        on_delete=models.DO_NOTHING,
        db_column="ReleaseID",
        null=True,
        blank=True,
    )
    error = models.CharField(
        db_column="Error",
        max_length=4000,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "VariableGeneration"
        app_label = "dpmcore_django"
