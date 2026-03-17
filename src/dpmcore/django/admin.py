"""Read-only Django admin registrations for all 68 DPM entities."""

from __future__ import annotations

from typing import Any, Sequence

from django.contrib import admin
from django.contrib.admin.utils import quote as admin_quote
from django.contrib.admin.views.main import ChangeList
from django.db import models
from django.http import HttpRequest
from django.urls import reverse

from dpmcore.django.models.auxiliary import (
    AuxCellMapping,
    AuxCellStatus,
    ModelViolations,
)
from dpmcore.django.models.glossary import (
    Category,
    CompoundItemContext,
    Context,
    ContextComposition,
    Item,
    ItemCategory,
    Property,
    PropertyCategory,
    SubCategory,
    SubCategoryItem,
    SubCategoryVersion,
    SupercategoryComposition,
)
from dpmcore.django.models.infrastructure import (
    Changelog,
    ChangelogAttribute,
    Concept,
    ConceptRelation,
    DataType,
    Document,
    DocumentVersion,
    DpmAttribute,
    DpmClass,
    Language,
    Organisation,
    Reference,
    RelatedConcept,
    Release,
    Role,
    Subdivision,
    SubdivisionType,
    Translation,
    User,
    UserRole,
    VariableGeneration,
)
from dpmcore.django.models.operations import (
    OperandReference,
    OperandReferenceLocation,
    Operation,
    OperationNode,
    OperationScope,
    OperationScopeComposition,
    OperationVersion,
    OperationVersionData,
    Operator,
    OperatorArgument,
)
from dpmcore.django.models.packaging import (
    Framework,
    Module,
    ModuleParameters,
    ModuleVersion,
    ModuleVersionComposition,
    OperationCodePrefix,
)
from dpmcore.django.models.rendering import (
    Cell,
    Header,
    HeaderVersion,
    KeyHeaderMapping,
    Table,
    TableAssociation,
    TableGroup,
    TableGroupComposition,
    TableVersion,
    TableVersionCell,
    TableVersionHeader,
)
from dpmcore.django.models.variables import (
    CompoundKey,
    KeyComposition,
    Variable,
    VariableCalculation,
    VariableVersion,
)

admin.site.site_header = "DPM REFIT Administration"
admin.site.site_title = "DPM Admin"
admin.site.index_title = "DPM Data Browser"

COMPOSITE_SEP = ","


# ── Composite-key helpers ──────────────────────────────────────


def _unique_fields(
    model: type[models.Model],
) -> tuple[str, ...]:
    """Return the first unique_together tuple, or empty."""
    ut = model._meta.unique_together
    if ut:
        return ut[0]
    return ()


def _composite_pk(
    instance: models.Model,
    fields: Sequence[str],
) -> str:
    """Build a comma-separated composite key string."""
    values: list[str] = []
    for name in fields:
        field = instance._meta.get_field(name)
        if field.is_relation:
            values.append(str(getattr(instance, field.attname)))
        else:
            values.append(str(getattr(instance, name)))
    return COMPOSITE_SEP.join(values)


class CompositeChangeList(ChangeList):
    """ChangeList that encodes composite keys in result URLs."""

    def url_for_result(self, result: models.Model) -> str:
        """Build a change-form URL using composite key if present."""
        fields = _unique_fields(result.__class__)
        if fields:
            pk = _composite_pk(result, fields)
            return reverse(
                "admin:%s_%s_change"
                % (
                    result._meta.app_label,
                    result._meta.model_name,
                ),
                args=(admin_quote(pk),),
            )
        return super().url_for_result(result)


# ── Read-only base class ────────────────────────────────────────


class ReadOnlyAdmin(admin.ModelAdmin):
    """Base admin class that makes all fields read-only."""

    list_per_page = 50
    show_full_result_count = False

    def has_add_permission(
        self,
        request: HttpRequest,
        obj: Any = None,
    ) -> bool:
        """Deny creation."""
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: Any = None,
    ) -> bool:
        """Deny edits."""
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: Any = None,
    ) -> bool:
        """Deny deletion."""
        return False

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: Any = None,
    ) -> list[str]:
        """Mark all fields as read-only."""
        return [
            f.name
            for f in self.model._meta.get_fields()
            if hasattr(f, "column")
        ]

    def get_changelist(
        self,
        request: HttpRequest,
        **kwargs: Any,
    ) -> type[ChangeList]:
        """Use composite-key aware change list."""
        return CompositeChangeList

    def get_object(
        self,
        request: HttpRequest,
        object_id: str,
        from_field: str | None = None,
    ) -> models.Model | None:
        """Decode composite keys for detail views."""
        fields = _unique_fields(self.model)
        if fields and COMPOSITE_SEP in str(object_id):
            parts = str(object_id).split(COMPOSITE_SEP)
            if len(parts) == len(fields):
                lookup: dict[str, str] = {}
                for name, value in zip(
                    fields, parts, strict=True
                ):
                    field = self.model._meta.get_field(name)
                    if field.is_relation:
                        lookup[field.attname] = value
                    else:
                        lookup[name] = value
                queryset = self.get_queryset(request)
                try:
                    return queryset.get(**lookup)
                except (
                    self.model.DoesNotExist,
                    self.model.MultipleObjectsReturned,
                    ValueError,
                ):
                    return None
        return super().get_object(
            request, object_id, from_field
        )


# ── Infrastructure (21 models) ──────────────────────────────────


@admin.register(Concept)
class ConceptAdmin(ReadOnlyAdmin):
    list_display = ("concept_guid", "class_id", "owner_id")
    search_fields = ("concept_guid",)


@admin.register(ConceptRelation)
class ConceptRelationAdmin(ReadOnlyAdmin):
    list_display = ("concept_relation_id", "type")
    list_filter = ("type",)


@admin.register(RelatedConcept)
class RelatedConceptAdmin(ReadOnlyAdmin):
    list_display = (
        "concept_guid",
        "concept_relation_id",
        "is_related_concept",
    )
    list_filter = ("is_related_concept",)


@admin.register(Organisation)
class OrganisationAdmin(ReadOnlyAdmin):
    list_display = ("org_id", "name", "acronym")
    search_fields = ("name", "acronym")


@admin.register(Language)
class LanguageAdmin(ReadOnlyAdmin):
    list_display = ("language_code", "name")
    search_fields = ("name",)


@admin.register(User)
class UserAdmin(ReadOnlyAdmin):
    list_display = ("user_id", "name", "org_id")
    search_fields = ("name",)


@admin.register(Role)
class RoleAdmin(ReadOnlyAdmin):
    list_display = ("role_id", "name")
    search_fields = ("name",)


@admin.register(UserRole)
class UserRoleAdmin(ReadOnlyAdmin):
    list_display = ("user_id", "role_id")


@admin.register(DataType)
class DataTypeAdmin(ReadOnlyAdmin):
    list_display = (
        "data_type_id",
        "code",
        "name",
        "is_active",
    )
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(DpmClass)
class DpmClassAdmin(ReadOnlyAdmin):
    list_display = (
        "class_id",
        "name",
        "type",
        "has_references",
    )
    search_fields = ("name",)
    list_filter = ("type",)


@admin.register(DpmAttribute)
class DpmAttributeAdmin(ReadOnlyAdmin):
    list_display = (
        "attribute_id",
        "name",
        "class_id",
        "has_translations",
    )
    search_fields = ("name",)
    list_filter = ("has_translations",)


@admin.register(Translation)
class TranslationAdmin(ReadOnlyAdmin):
    list_display = (
        "concept_guid",
        "attribute_id",
        "language_code",
        "translator_id",
    )
    search_fields = ("translation",)


@admin.register(Changelog)
class ChangelogAdmin(ReadOnlyAdmin):
    list_display = (
        "row_guid",
        "class_id",
        "timestamp",
        "change_type",
        "status",
    )
    search_fields = ("entity_code",)
    list_filter = ("status", "change_type")


@admin.register(ChangelogAttribute)
class ChangelogAttributeAdmin(ReadOnlyAdmin):
    list_display = (
        "changelog_attribute_id",
        "action_id",
        "attribute_id",
    )


@admin.register(Document)
class DocumentAdmin(ReadOnlyAdmin):
    list_display = ("document_id", "code", "name", "type")
    search_fields = ("code", "name")
    list_filter = ("type",)


@admin.register(DocumentVersion)
class DocumentVersionAdmin(ReadOnlyAdmin):
    list_display = (
        "document_vid",
        "document_id",
        "code",
        "version",
    )
    search_fields = ("code",)


@admin.register(Subdivision)
class SubdivisionAdmin(ReadOnlyAdmin):
    list_display = (
        "subdivision_id",
        "number",
        "subdivision_type_id",
    )
    search_fields = ("number",)


@admin.register(SubdivisionType)
class SubdivisionTypeAdmin(ReadOnlyAdmin):
    list_display = ("subdivision_type_id", "name")
    search_fields = ("name",)


@admin.register(Reference)
class ReferenceAdmin(ReadOnlyAdmin):
    list_display = ("subdivision_id", "concept_guid")


@admin.register(Release)
class ReleaseAdmin(ReadOnlyAdmin):
    list_display = (
        "release_id",
        "code",
        "status",
        "date",
        "is_current",
        "type",
    )
    search_fields = ("code", "description")
    list_filter = ("status", "type", "is_current")


@admin.register(VariableGeneration)
class VariableGenerationAdmin(ReadOnlyAdmin):
    list_display = (
        "variable_generation_id",
        "status",
        "release_id",
        "start_date",
        "end_date",
    )
    list_filter = ("status",)


# ── Glossary (12 models) ────────────────────────────────────────


@admin.register(Category)
class CategoryAdmin(ReadOnlyAdmin):
    list_display = (
        "category_id",
        "code",
        "name",
        "is_enumerated",
        "is_active",
    )
    search_fields = ("code", "name")
    list_filter = ("is_active", "is_enumerated")


@admin.register(SubCategory)
class SubCategoryAdmin(ReadOnlyAdmin):
    list_display = (
        "subcategory_id",
        "code",
        "name",
        "category_id",
    )
    search_fields = ("code", "name")


@admin.register(SubCategoryVersion)
class SubCategoryVersionAdmin(ReadOnlyAdmin):
    list_display = (
        "subcategory_vid",
        "subcategory_id",
        "start_release_id",
        "end_release_id",
    )


@admin.register(SubCategoryItem)
class SubCategoryItemAdmin(ReadOnlyAdmin):
    list_display = (
        "item_id",
        "subcategory_vid",
        "order",
        "label",
    )
    search_fields = ("label",)


@admin.register(Item)
class ItemAdmin(ReadOnlyAdmin):
    list_display = (
        "item_id",
        "name",
        "is_property",
        "is_active",
    )
    search_fields = ("name",)
    list_filter = ("is_active", "is_property")


@admin.register(ItemCategory)
class ItemCategoryAdmin(ReadOnlyAdmin):
    list_display = (
        "item_id",
        "start_release_id",
        "category_id",
        "code",
    )
    search_fields = ("code",)


@admin.register(Property)
class PropertyAdmin(ReadOnlyAdmin):
    list_display = (
        "property_id",
        "is_composite",
        "is_metric",
        "data_type_id",
        "period_type",
    )
    list_filter = ("is_composite", "is_metric")


@admin.register(PropertyCategory)
class PropertyCategoryAdmin(ReadOnlyAdmin):
    list_display = (
        "property_id",
        "start_release_id",
        "category_id",
    )


@admin.register(Context)
class ContextAdmin(ReadOnlyAdmin):
    list_display = ("context_id", "signature")
    search_fields = ("signature",)


@admin.register(ContextComposition)
class ContextCompositionAdmin(ReadOnlyAdmin):
    list_display = ("context_id", "property_id", "item_id")


@admin.register(CompoundItemContext)
class CompoundItemContextAdmin(ReadOnlyAdmin):
    list_display = (
        "item_id",
        "start_release_id",
        "context_id",
    )


@admin.register(SupercategoryComposition)
class SupercategoryCompositionAdmin(ReadOnlyAdmin):
    list_display = ("supercategory_id", "category_id")


# ── Rendering (11 models) ───────────────────────────────────────


@admin.register(Table)
class TableAdmin(ReadOnlyAdmin):
    list_display = (
        "table_id",
        "is_abstract",
        "is_flat",
        "is_normalised",
    )
    list_filter = ("is_abstract", "is_flat")


@admin.register(TableVersion)
class TableVersionAdmin(ReadOnlyAdmin):
    list_display = (
        "table_vid",
        "code",
        "name",
        "table_id",
        "start_release_id",
    )
    search_fields = ("code", "name")


@admin.register(Header)
class HeaderAdmin(ReadOnlyAdmin):
    list_display = (
        "header_id",
        "table_id",
        "direction",
        "is_key",
    )
    list_filter = ("direction", "is_key")


@admin.register(HeaderVersion)
class HeaderVersionAdmin(ReadOnlyAdmin):
    list_display = (
        "header_vid",
        "header_id",
        "code",
        "label",
    )
    search_fields = ("code", "label")


@admin.register(Cell)
class CellAdmin(ReadOnlyAdmin):
    list_display = (
        "cell_id",
        "table_id",
        "column_id",
        "row_id",
        "sheet_id",
    )


@admin.register(TableVersionCell)
class TableVersionCellAdmin(ReadOnlyAdmin):
    list_display = (
        "table_vid",
        "cell_id",
        "cell_code",
        "is_nullable",
        "is_excluded",
        "is_void",
    )
    search_fields = ("cell_code",)
    list_filter = ("is_nullable", "is_excluded", "is_void")


@admin.register(TableVersionHeader)
class TableVersionHeaderAdmin(ReadOnlyAdmin):
    list_display = (
        "table_vid",
        "header_id",
        "header_vid",
        "order",
        "is_abstract",
    )
    list_filter = ("is_abstract",)


@admin.register(TableGroup)
class TableGroupAdmin(ReadOnlyAdmin):
    list_display = (
        "table_group_id",
        "code",
        "name",
        "type",
    )
    search_fields = ("code", "name")
    list_filter = ("type",)


@admin.register(TableGroupComposition)
class TableGroupCompositionAdmin(ReadOnlyAdmin):
    list_display = ("table_group_id", "table_id", "order")


@admin.register(TableAssociation)
class TableAssociationAdmin(ReadOnlyAdmin):
    list_display = (
        "association_id",
        "name",
        "child_table_vid",
        "parent_table_vid",
    )
    search_fields = ("name",)
    list_filter = ("is_identifying", "is_subtype")


@admin.register(KeyHeaderMapping)
class KeyHeaderMappingAdmin(ReadOnlyAdmin):
    list_display = (
        "association_id",
        "foreign_key_header_id",
        "primary_key_header_id",
    )


# ── Variables (5 models) ────────────────────────────────────────


@admin.register(Variable)
class VariableAdmin(ReadOnlyAdmin):
    list_display = ("variable_id", "type")
    list_filter = ("type",)


@admin.register(VariableVersion)
class VariableVersionAdmin(ReadOnlyAdmin):
    list_display = (
        "variable_vid",
        "variable_id",
        "code",
        "name",
    )
    search_fields = ("code", "name")


@admin.register(VariableCalculation)
class VariableCalculationAdmin(ReadOnlyAdmin):
    list_display = (
        "module_id",
        "variable_id",
        "operation_vid",
        "from_reference_date",
        "to_reference_date",
    )


@admin.register(CompoundKey)
class CompoundKeyAdmin(ReadOnlyAdmin):
    list_display = ("key_id", "signature")
    search_fields = ("signature",)


@admin.register(KeyComposition)
class KeyCompositionAdmin(ReadOnlyAdmin):
    list_display = ("key_id", "variable_vid")


# ── Operations (10 models) ──────────────────────────────────────


@admin.register(Operation)
class OperationAdmin(ReadOnlyAdmin):
    list_display = (
        "operation_id",
        "code",
        "type",
        "source",
    )
    search_fields = ("code",)
    list_filter = ("type", "source")


@admin.register(OperationVersion)
class OperationVersionAdmin(ReadOnlyAdmin):
    list_display = (
        "operation_vid",
        "operation_id",
        "endorsement",
        "start_release_id",
        "end_release_id",
    )
    search_fields = ("description", "expression")
    list_filter = ("endorsement", "is_variant_approved")


@admin.register(OperationVersionData)
class OperationVersionDataAdmin(ReadOnlyAdmin):
    list_display = (
        "operation_vid",
        "error_code",
        "is_applying",
        "proposing_status",
    )
    search_fields = ("error_code",)
    list_filter = ("is_applying", "proposing_status")


@admin.register(OperationNode)
class OperationNodeAdmin(ReadOnlyAdmin):
    list_display = (
        "node_id",
        "operation_vid",
        "operator_id",
        "operand_type",
        "is_leaf",
    )
    list_filter = ("operand_type", "is_leaf")


@admin.register(OperationScope)
class OperationScopeAdmin(ReadOnlyAdmin):
    list_display = (
        "operation_scope_id",
        "operation_vid",
        "severity",
    )
    list_filter = ("severity",)


@admin.register(OperationScopeComposition)
class OperationScopeCompositionAdmin(ReadOnlyAdmin):
    list_display = ("operation_scope_id", "module_vid")


@admin.register(Operator)
class OperatorAdmin(ReadOnlyAdmin):
    list_display = (
        "operator_id",
        "name",
        "symbol",
        "type",
    )
    search_fields = ("name", "symbol")
    list_filter = ("type",)


@admin.register(OperatorArgument)
class OperatorArgumentAdmin(ReadOnlyAdmin):
    list_display = (
        "argument_id",
        "operator_id",
        "name",
        "order",
        "is_mandatory",
    )
    search_fields = ("name",)
    list_filter = ("is_mandatory",)


@admin.register(OperandReference)
class OperandReferenceAdmin(ReadOnlyAdmin):
    list_display = (
        "operand_reference_id",
        "node_id",
        "operand_reference",
    )
    search_fields = ("operand_reference",)


@admin.register(OperandReferenceLocation)
class OperandReferenceLocationAdmin(ReadOnlyAdmin):
    list_display = (
        "operand_reference_id",
        "table",
        "row",
        "column",
        "sheet",
    )
    search_fields = ("table",)


# ── Packaging (6 models) ────────────────────────────────────────


@admin.register(Framework)
class FrameworkAdmin(ReadOnlyAdmin):
    list_display = ("framework_id", "code", "name")
    search_fields = ("code", "name")


@admin.register(Module)
class ModuleAdmin(ReadOnlyAdmin):
    list_display = (
        "module_id",
        "framework_id",
        "is_document_module",
    )
    list_filter = ("is_document_module",)


@admin.register(ModuleVersion)
class ModuleVersionAdmin(ReadOnlyAdmin):
    list_display = (
        "module_vid",
        "module_id",
        "code",
        "name",
        "version_number",
    )
    search_fields = ("code", "name")
    list_filter = ("is_reported", "is_calculated")


@admin.register(ModuleVersionComposition)
class ModuleVersionCompositionAdmin(ReadOnlyAdmin):
    list_display = (
        "module_vid",
        "table_id",
        "table_vid",
        "order",
    )


@admin.register(ModuleParameters)
class ModuleParametersAdmin(ReadOnlyAdmin):
    list_display = ("module_vid", "variable_vid")


@admin.register(OperationCodePrefix)
class OperationCodePrefixAdmin(ReadOnlyAdmin):
    list_display = (
        "operation_code_prefix_id",
        "code",
        "list_name",
        "framework_id",
    )
    search_fields = ("code",)


# ── Auxiliary (3 models) ────────────────────────────────────────


@admin.register(AuxCellMapping)
class AuxCellMappingAdmin(ReadOnlyAdmin):
    list_display = (
        "new_cell_id",
        "new_table_vid",
        "old_cell_id",
        "old_table_vid",
    )


@admin.register(AuxCellStatus)
class AuxCellStatusAdmin(ReadOnlyAdmin):
    list_display = (
        "table_vid",
        "cell_id",
        "status",
        "is_new_cell",
    )
    list_filter = ("status", "is_new_cell")


@admin.register(ModelViolations)
class ModelViolationsAdmin(ReadOnlyAdmin):
    list_display = (
        "violation_code",
        "violation",
        "is_blocking",
        "table_code",
    )
    search_fields = ("violation_code", "table_code")
    list_filter = ("is_blocking",)
