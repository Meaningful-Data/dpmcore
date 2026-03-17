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


class DpmModelAdmin(admin.ModelAdmin):
    """Base admin class for all DPM models."""

    list_per_page = 50
    show_full_result_count = False

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
class ConceptAdmin(DpmModelAdmin):
    list_display = ("concept_guid", "class_id", "owner_id")
    search_fields = ("concept_guid",)


@admin.register(ConceptRelation)
class ConceptRelationAdmin(DpmModelAdmin):
    list_display = ("concept_relation_id", "type")
    list_filter = ("type",)


@admin.register(RelatedConcept)
class RelatedConceptAdmin(DpmModelAdmin):
    list_display = (
        "concept_guid",
        "concept_relation_id",
        "is_related_concept",
    )
    list_filter = ("is_related_concept",)


@admin.register(Organisation)
class OrganisationAdmin(DpmModelAdmin):
    list_display = ("org_id", "name", "acronym")
    search_fields = ("name", "acronym")


@admin.register(Language)
class LanguageAdmin(DpmModelAdmin):
    list_display = ("language_code", "name")
    search_fields = ("name",)


@admin.register(User)
class UserAdmin(DpmModelAdmin):
    list_display = ("user_id", "name", "org_id")
    search_fields = ("name",)


@admin.register(Role)
class RoleAdmin(DpmModelAdmin):
    list_display = ("role_id", "name")
    search_fields = ("name",)


@admin.register(UserRole)
class UserRoleAdmin(DpmModelAdmin):
    list_display = ("user_id", "role_id")


@admin.register(DataType)
class DataTypeAdmin(DpmModelAdmin):
    list_display = (
        "data_type_id",
        "code",
        "name",
        "is_active",
    )
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(DpmClass)
class DpmClassAdmin(DpmModelAdmin):
    list_display = (
        "class_id",
        "name",
        "type",
        "has_references",
    )
    search_fields = ("name",)
    list_filter = ("type",)


@admin.register(DpmAttribute)
class DpmAttributeAdmin(DpmModelAdmin):
    list_display = (
        "attribute_id",
        "name",
        "class_id",
        "has_translations",
    )
    search_fields = ("name",)
    list_filter = ("has_translations",)


@admin.register(Translation)
class TranslationAdmin(DpmModelAdmin):
    list_display = (
        "concept_guid",
        "attribute_id",
        "language_code",
        "translator_id",
    )
    search_fields = ("translation",)


@admin.register(Changelog)
class ChangelogAdmin(DpmModelAdmin):
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
class ChangelogAttributeAdmin(DpmModelAdmin):
    list_display = (
        "changelog_attribute_id",
        "action_id",
        "attribute_id",
    )


@admin.register(Document)
class DocumentAdmin(DpmModelAdmin):
    list_display = ("document_id", "code", "name", "type")
    search_fields = ("code", "name")
    list_filter = ("type",)


@admin.register(DocumentVersion)
class DocumentVersionAdmin(DpmModelAdmin):
    list_display = (
        "document_vid",
        "document_id",
        "code",
        "version",
    )
    search_fields = ("code",)


@admin.register(Subdivision)
class SubdivisionAdmin(DpmModelAdmin):
    list_display = (
        "subdivision_id",
        "number",
        "subdivision_type_id",
    )
    search_fields = ("number",)


@admin.register(SubdivisionType)
class SubdivisionTypeAdmin(DpmModelAdmin):
    list_display = ("subdivision_type_id", "name")
    search_fields = ("name",)


@admin.register(Reference)
class ReferenceAdmin(DpmModelAdmin):
    list_display = ("subdivision_id", "concept_guid")


@admin.register(Release)
class ReleaseAdmin(DpmModelAdmin):
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
class VariableGenerationAdmin(DpmModelAdmin):
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
class CategoryAdmin(DpmModelAdmin):
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
class SubCategoryAdmin(DpmModelAdmin):
    list_display = (
        "subcategory_id",
        "code",
        "name",
        "category_id",
    )
    search_fields = ("code", "name")


@admin.register(SubCategoryVersion)
class SubCategoryVersionAdmin(DpmModelAdmin):
    list_display = (
        "subcategory_vid",
        "subcategory_id",
        "start_release_id",
        "end_release_id",
    )


@admin.register(SubCategoryItem)
class SubCategoryItemAdmin(DpmModelAdmin):
    list_display = (
        "item_id",
        "subcategory_vid",
        "order",
        "label",
    )
    search_fields = ("label",)


@admin.register(Item)
class ItemAdmin(DpmModelAdmin):
    list_display = (
        "item_id",
        "name",
        "is_property",
        "is_active",
    )
    search_fields = ("name",)
    list_filter = ("is_active", "is_property")


@admin.register(ItemCategory)
class ItemCategoryAdmin(DpmModelAdmin):
    list_display = (
        "item_id",
        "start_release_id",
        "category_id",
        "code",
    )
    search_fields = ("code",)


@admin.register(Property)
class PropertyAdmin(DpmModelAdmin):
    list_display = (
        "property_id",
        "is_composite",
        "is_metric",
        "data_type_id",
        "period_type",
    )
    list_filter = ("is_composite", "is_metric")


@admin.register(PropertyCategory)
class PropertyCategoryAdmin(DpmModelAdmin):
    list_display = (
        "property_id",
        "start_release_id",
        "category_id",
    )


@admin.register(Context)
class ContextAdmin(DpmModelAdmin):
    list_display = ("context_id", "signature")
    search_fields = ("signature",)


@admin.register(ContextComposition)
class ContextCompositionAdmin(DpmModelAdmin):
    list_display = ("context_id", "property_id", "item_id")


@admin.register(CompoundItemContext)
class CompoundItemContextAdmin(DpmModelAdmin):
    list_display = (
        "item_id",
        "start_release_id",
        "context_id",
    )


@admin.register(SupercategoryComposition)
class SupercategoryCompositionAdmin(DpmModelAdmin):
    list_display = ("supercategory_id", "category_id")


# ── Rendering (11 models) ───────────────────────────────────────


@admin.register(Table)
class TableAdmin(DpmModelAdmin):
    list_display = (
        "table_id",
        "is_abstract",
        "is_flat",
        "is_normalised",
    )
    list_filter = ("is_abstract", "is_flat")


@admin.register(TableVersion)
class TableVersionAdmin(DpmModelAdmin):
    list_display = (
        "table_vid",
        "code",
        "name",
        "table_id",
        "start_release_id",
    )
    search_fields = ("code", "name")


@admin.register(Header)
class HeaderAdmin(DpmModelAdmin):
    list_display = (
        "header_id",
        "table_id",
        "direction",
        "is_key",
    )
    list_filter = ("direction", "is_key")


@admin.register(HeaderVersion)
class HeaderVersionAdmin(DpmModelAdmin):
    list_display = (
        "header_vid",
        "header_id",
        "code",
        "label",
    )
    search_fields = ("code", "label")


@admin.register(Cell)
class CellAdmin(DpmModelAdmin):
    list_display = (
        "cell_id",
        "table_id",
        "column_id",
        "row_id",
        "sheet_id",
    )


@admin.register(TableVersionCell)
class TableVersionCellAdmin(DpmModelAdmin):
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
class TableVersionHeaderAdmin(DpmModelAdmin):
    list_display = (
        "table_vid",
        "header_id",
        "header_vid",
        "order",
        "is_abstract",
    )
    list_filter = ("is_abstract",)


@admin.register(TableGroup)
class TableGroupAdmin(DpmModelAdmin):
    list_display = (
        "table_group_id",
        "code",
        "name",
        "type",
    )
    search_fields = ("code", "name")
    list_filter = ("type",)


@admin.register(TableGroupComposition)
class TableGroupCompositionAdmin(DpmModelAdmin):
    list_display = ("table_group_id", "table_id", "order")


@admin.register(TableAssociation)
class TableAssociationAdmin(DpmModelAdmin):
    list_display = (
        "association_id",
        "name",
        "child_table_vid",
        "parent_table_vid",
    )
    search_fields = ("name",)
    list_filter = ("is_identifying", "is_subtype")


@admin.register(KeyHeaderMapping)
class KeyHeaderMappingAdmin(DpmModelAdmin):
    list_display = (
        "association_id",
        "foreign_key_header_id",
        "primary_key_header_id",
    )


# ── Variables (5 models) ────────────────────────────────────────


@admin.register(Variable)
class VariableAdmin(DpmModelAdmin):
    list_display = ("variable_id", "type")
    list_filter = ("type",)


@admin.register(VariableVersion)
class VariableVersionAdmin(DpmModelAdmin):
    list_display = (
        "variable_vid",
        "variable_id",
        "code",
        "name",
    )
    search_fields = ("code", "name")


@admin.register(VariableCalculation)
class VariableCalculationAdmin(DpmModelAdmin):
    list_display = (
        "module_id",
        "variable_id",
        "operation_vid",
        "from_reference_date",
        "to_reference_date",
    )


@admin.register(CompoundKey)
class CompoundKeyAdmin(DpmModelAdmin):
    list_display = ("key_id", "signature")
    search_fields = ("signature",)


@admin.register(KeyComposition)
class KeyCompositionAdmin(DpmModelAdmin):
    list_display = ("key_id", "variable_vid")


# ── Operations (10 models) ──────────────────────────────────────


@admin.register(Operation)
class OperationAdmin(DpmModelAdmin):
    list_display = (
        "operation_id",
        "code",
        "type",
        "source",
    )
    search_fields = ("code",)
    list_filter = ("type", "source")


@admin.register(OperationVersion)
class OperationVersionAdmin(DpmModelAdmin):
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
class OperationVersionDataAdmin(DpmModelAdmin):
    list_display = (
        "operation_vid",
        "error_code",
        "is_applying",
        "proposing_status",
    )
    search_fields = ("error_code",)
    list_filter = ("is_applying", "proposing_status")


@admin.register(OperationNode)
class OperationNodeAdmin(DpmModelAdmin):
    list_display = (
        "node_id",
        "operation_vid",
        "operator_id",
        "operand_type",
        "is_leaf",
    )
    list_filter = ("operand_type", "is_leaf")


@admin.register(OperationScope)
class OperationScopeAdmin(DpmModelAdmin):
    list_display = (
        "operation_scope_id",
        "operation_vid",
        "severity",
    )
    list_filter = ("severity",)


@admin.register(OperationScopeComposition)
class OperationScopeCompositionAdmin(DpmModelAdmin):
    list_display = ("operation_scope_id", "module_vid")


@admin.register(Operator)
class OperatorAdmin(DpmModelAdmin):
    list_display = (
        "operator_id",
        "name",
        "symbol",
        "type",
    )
    search_fields = ("name", "symbol")
    list_filter = ("type",)


@admin.register(OperatorArgument)
class OperatorArgumentAdmin(DpmModelAdmin):
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
class OperandReferenceAdmin(DpmModelAdmin):
    list_display = (
        "operand_reference_id",
        "node_id",
        "operand_reference",
    )
    search_fields = ("operand_reference",)


@admin.register(OperandReferenceLocation)
class OperandReferenceLocationAdmin(DpmModelAdmin):
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
class FrameworkAdmin(DpmModelAdmin):
    list_display = ("framework_id", "code", "name")
    search_fields = ("code", "name")


@admin.register(Module)
class ModuleAdmin(DpmModelAdmin):
    list_display = (
        "module_id",
        "framework_id",
        "is_document_module",
    )
    list_filter = ("is_document_module",)


@admin.register(ModuleVersion)
class ModuleVersionAdmin(DpmModelAdmin):
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
class ModuleVersionCompositionAdmin(DpmModelAdmin):
    list_display = (
        "module_vid",
        "table_id",
        "table_vid",
        "order",
    )


@admin.register(ModuleParameters)
class ModuleParametersAdmin(DpmModelAdmin):
    list_display = ("module_vid", "variable_vid")


@admin.register(OperationCodePrefix)
class OperationCodePrefixAdmin(DpmModelAdmin):
    list_display = (
        "operation_code_prefix_id",
        "code",
        "list_name",
        "framework_id",
    )
    search_fields = ("code",)


# ── Auxiliary (3 models) ────────────────────────────────────────


@admin.register(AuxCellMapping)
class AuxCellMappingAdmin(DpmModelAdmin):
    list_display = (
        "new_cell_id",
        "new_table_vid",
        "old_cell_id",
        "old_table_vid",
    )


@admin.register(AuxCellStatus)
class AuxCellStatusAdmin(DpmModelAdmin):
    list_display = (
        "table_vid",
        "cell_id",
        "status",
        "is_new_cell",
    )
    list_filter = ("status", "is_new_cell")


@admin.register(ModelViolations)
class ModelViolationsAdmin(DpmModelAdmin):
    list_display = (
        "violation_code",
        "violation",
        "is_blocking",
        "table_code",
    )
    search_fields = ("violation_code", "table_code")
    list_filter = ("is_blocking",)
