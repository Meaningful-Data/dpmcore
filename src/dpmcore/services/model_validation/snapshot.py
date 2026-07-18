"""In-memory snapshot of the DPM model for rule evaluation.

Instead of translating each SQL validation query into a multi-join
SQLAlchemy query, the modelling services load the relevant slice of
the model **once** into plain, frozen dataclass rows and evaluate all
rules against these in-memory structures. Rows carry only column
values (never live ORM objects), so rule evaluation can never trigger
lazy loads, and every rule is unit-testable by constructing a snapshot
by hand.

Derived indexes are built lazily through :meth:`ModelSnapshot.cache`
so that rules can share them without recomputation.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date as _date
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from dpmcore.orm import (
    auxiliary,
    glossary,
    infrastructure,
    operations,
    packaging,
    rendering,
    variables,
)

RowT = TypeVar("RowT")
CachedT = TypeVar("CachedT")

#: DPM1-compatible datatype code remapping used by the taxonomy
#: generation checks (rule 6_20). Mirrors the SQL ``#datatype_mapping``
#: temp table: ``dt -> d``; ``u``, ``es`` and ``o`` -> ``s``.
DPM1_DATATYPE_REMAP: Dict[str, str] = {
    "dt": "d",
    "u": "s",
    "es": "s",
    "o": "s",
}


# ------------------------------------------------------------------
# Row dataclasses (field names match ORM mapped attribute names)
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ReleaseRow:
    """Row of the ``Release`` table."""

    release_id: int
    code: Optional[str]
    status: Optional[str]
    is_current: Optional[bool]
    type: Optional[str]
    date: Optional[_date] = None


@dataclass(frozen=True)
class ConceptRelationRow:
    """Row of the ``ConceptRelation`` table."""

    concept_relation_id: int
    type: Optional[str]


@dataclass(frozen=True)
class RelatedConceptRow:
    """Row of the ``RelatedConcept`` table."""

    concept_guid: str
    concept_relation_id: int
    is_related_concept: Optional[bool]


@dataclass(frozen=True)
class OrganisationRow:
    """Row of the ``Organisation`` table."""

    org_id: int
    name: Optional[str]
    acronym: Optional[str]


@dataclass(frozen=True)
class DataTypeRow:
    """Row of the ``DataType`` table."""

    data_type_id: int
    code: Optional[str]
    name: Optional[str]
    parent_data_type_id: Optional[int]
    is_active: Optional[bool]


@dataclass(frozen=True)
class FrameworkRow:
    """Row of the ``Framework`` table."""

    framework_id: int
    code: Optional[str]
    name: Optional[str]


@dataclass(frozen=True)
class ModuleRow:
    """Row of the ``Module`` table."""

    module_id: int
    framework_id: Optional[int]
    is_document_module: Optional[bool]


@dataclass(frozen=True)
class ModuleVersionRow:
    """Row of the ``ModuleVersion`` table."""

    module_vid: int
    module_id: Optional[int]
    global_key_id: Optional[int]
    start_release_id: Optional[int]
    end_release_id: Optional[int]
    code: Optional[str]
    name: Optional[str]
    version_number: Optional[str]
    is_reported: Optional[bool]
    is_calculated: Optional[bool]


@dataclass(frozen=True)
class ModuleVersionCompositionRow:
    """Row of the ``ModuleVersionComposition`` table."""

    module_vid: int
    table_id: int
    table_vid: Optional[int]
    order: Optional[int]


@dataclass(frozen=True)
class ModuleParametersRow:
    """Row of the ``ModuleParameters`` table."""

    module_vid: int
    variable_vid: int


@dataclass(frozen=True)
class TableRow:
    """Row of the ``Table`` table."""

    table_id: int
    is_abstract: Optional[bool]
    has_open_columns: Optional[bool]
    has_open_rows: Optional[bool]
    has_open_sheets: Optional[bool]


@dataclass(frozen=True)
class TableVersionRow:
    """Row of the ``TableVersion`` table."""

    table_vid: int
    code: Optional[str]
    name: Optional[str]
    table_id: Optional[int]
    abstract_table_id: Optional[int]
    key_id: Optional[int]
    property_id: Optional[int]
    context_id: Optional[int]
    start_release_id: Optional[int]
    end_release_id: Optional[int]


@dataclass(frozen=True)
class HeaderRow:
    """Row of the ``Header`` table."""

    header_id: int
    table_id: Optional[int]
    direction: Optional[str]
    is_key: Optional[bool]
    is_attribute: Optional[bool]
    row_guid: Optional[str] = None


@dataclass(frozen=True)
class HeaderVersionRow:
    """Row of the ``HeaderVersion`` table."""

    header_vid: int
    header_id: Optional[int]
    code: Optional[str]
    label: Optional[str]
    property_id: Optional[int]
    context_id: Optional[int]
    subcategory_vid: Optional[int]
    key_variable_vid: Optional[int]
    start_release_id: Optional[int]
    end_release_id: Optional[int]


@dataclass(frozen=True)
class CellRow:
    """Row of the ``Cell`` table."""

    cell_id: int
    table_id: Optional[int]
    column_id: Optional[int]
    row_id: Optional[int]
    sheet_id: Optional[int]


@dataclass(frozen=True)
class TableVersionCellRow:
    """Row of the ``TableVersionCell`` table."""

    table_vid: int
    cell_id: int
    cell_code: Optional[str]
    is_nullable: Optional[bool]
    is_excluded: Optional[bool]
    is_void: Optional[bool]
    sign: Optional[str]
    variable_vid: Optional[int]


@dataclass(frozen=True)
class TableVersionHeaderRow:
    """Row of the ``TableVersionHeader`` table."""

    table_vid: int
    header_id: int
    header_vid: Optional[int]
    parent_header_id: Optional[int]
    parent_first: Optional[bool]
    order: Optional[int]
    is_abstract: Optional[bool]
    is_unique: Optional[bool]


@dataclass(frozen=True)
class TableGroupRow:
    """Row of the ``TableGroup`` table."""

    table_group_id: int
    code: Optional[str]
    name: Optional[str]
    type: Optional[str]
    start_release_id: Optional[int]
    end_release_id: Optional[int]
    parent_table_group_id: Optional[int]


@dataclass(frozen=True)
class TableGroupCompositionRow:
    """Row of the ``TableGroupComposition`` table."""

    table_group_id: int
    table_id: int
    order: Optional[int]
    start_release_id: Optional[int]
    end_release_id: Optional[int]


@dataclass(frozen=True)
class TableAssociationRow:
    """Row of the ``TableAssociation`` table."""

    association_id: int
    child_table_vid: Optional[int]
    parent_table_vid: Optional[int]
    name: Optional[str]
    is_identifying: Optional[bool]
    is_subtype: Optional[bool]
    subtype_discriminator: Optional[int]


@dataclass(frozen=True)
class KeyHeaderMappingRow:
    """Row of the ``KeyHeaderMapping`` table."""

    association_id: int
    foreign_key_header_id: int
    primary_key_header_id: Optional[int]


@dataclass(frozen=True)
class VariableRow:
    """Row of the ``Variable`` table."""

    variable_id: int
    type: Optional[str]


@dataclass(frozen=True)
class VariableVersionRow:
    """Row of the ``VariableVersion`` table."""

    variable_vid: int
    variable_id: Optional[int]
    property_id: Optional[int]
    subcategory_vid: Optional[int]
    context_id: Optional[int]
    key_id: Optional[int]
    is_multi_valued: Optional[bool]
    code: Optional[str]
    name: Optional[str]
    start_release_id: Optional[int]
    end_release_id: Optional[int]


@dataclass(frozen=True)
class CompoundKeyRow:
    """Row of the ``CompoundKey`` table."""

    key_id: int
    signature: Optional[str]


@dataclass(frozen=True)
class KeyCompositionRow:
    """Row of the ``KeyComposition`` table."""

    key_id: int
    variable_vid: int


@dataclass(frozen=True)
class CategoryRow:
    """Row of the ``Category`` table."""

    category_id: int
    code: Optional[str]
    name: Optional[str]
    is_enumerated: Optional[bool]
    is_active: Optional[bool]
    created_release_id: Optional[int]


@dataclass(frozen=True)
class SubCategoryRow:
    """Row of the ``SubCategory`` table."""

    subcategory_id: int
    category_id: Optional[int]
    code: Optional[str]
    name: Optional[str]


@dataclass(frozen=True)
class SubCategoryVersionRow:
    """Row of the ``SubCategoryVersion`` table."""

    subcategory_vid: int
    subcategory_id: Optional[int]
    start_release_id: Optional[int]
    end_release_id: Optional[int]


@dataclass(frozen=True)
class SubCategoryItemRow:
    """Row of the ``SubCategoryItem`` table."""

    item_id: int
    subcategory_vid: int
    order: Optional[int]
    label: Optional[str]
    parent_item_id: Optional[int]


@dataclass(frozen=True)
class ItemRow:
    """Row of the ``Item`` table."""

    item_id: int
    name: Optional[str]
    is_property: Optional[bool]
    is_active: Optional[bool]
    owner_id: Optional[int]


@dataclass(frozen=True)
class ItemCategoryRow:
    """Row of the ``ItemCategory`` table."""

    item_id: int
    start_release_id: int
    category_id: Optional[int]
    code: Optional[str]
    is_default_item: Optional[bool]
    signature: Optional[str]
    end_release_id: Optional[int]


@dataclass(frozen=True)
class PropertyRow:
    """Row of the ``Property`` table."""

    property_id: int
    is_composite: Optional[bool]
    is_metric: Optional[bool]
    data_type_id: Optional[int]
    period_type: Optional[str]


@dataclass(frozen=True)
class PropertyCategoryRow:
    """Row of the ``PropertyCategory`` table."""

    property_id: int
    start_release_id: int
    category_id: Optional[int]
    end_release_id: Optional[int]


@dataclass(frozen=True)
class ContextRow:
    """Row of the ``Context`` table."""

    context_id: int
    signature: Optional[str]


@dataclass(frozen=True)
class ContextCompositionRow:
    """Row of the ``ContextComposition`` table."""

    context_id: int
    property_id: int
    item_id: Optional[int]


@dataclass(frozen=True)
class CompoundItemContextRow:
    """Row of the ``CompoundItemContext`` table."""

    item_id: int
    start_release_id: int
    context_id: Optional[int]
    end_release_id: Optional[int]


@dataclass(frozen=True)
class SupercategoryCompositionRow:
    """Row of the ``SuperCategoryComposition`` table."""

    supercategory_id: int
    category_id: int
    start_release_id: Optional[int]
    end_release_id: Optional[int]


@dataclass(frozen=True)
class OperationRow:
    """Row of the ``Operation`` table."""

    operation_id: int
    code: Optional[str]


@dataclass(frozen=True)
class OperationVersionRow:
    """Row of the ``OperationVersion`` table."""

    operation_vid: int
    operation_id: Optional[int]
    start_release_id: Optional[int]
    end_release_id: Optional[int]


@dataclass(frozen=True)
class AuxCellMappingRow:
    """Row of the ``Aux_CellMapping`` table."""

    new_cell_id: int
    new_table_vid: int
    old_cell_id: Optional[int]
    old_table_vid: Optional[int]


#: Store name -> (ORM model, row dataclass). Drives both the DB
#: loader and the test-oriented :meth:`ModelSnapshot.from_rows`.
_STORES: Dict[str, Tuple[type, type]] = {
    "releases": (infrastructure.Release, ReleaseRow),
    "concept_relations": (
        infrastructure.ConceptRelation,
        ConceptRelationRow,
    ),
    "related_concepts": (
        infrastructure.RelatedConcept,
        RelatedConceptRow,
    ),
    "organisations": (infrastructure.Organisation, OrganisationRow),
    "datatypes": (infrastructure.DataType, DataTypeRow),
    "frameworks": (packaging.Framework, FrameworkRow),
    "modules": (packaging.Module, ModuleRow),
    "module_versions": (packaging.ModuleVersion, ModuleVersionRow),
    "module_version_compositions": (
        packaging.ModuleVersionComposition,
        ModuleVersionCompositionRow,
    ),
    "module_parameters": (
        packaging.ModuleParameters,
        ModuleParametersRow,
    ),
    "tables": (rendering.Table, TableRow),
    "table_versions": (rendering.TableVersion, TableVersionRow),
    "headers": (rendering.Header, HeaderRow),
    "header_versions": (rendering.HeaderVersion, HeaderVersionRow),
    "cells": (rendering.Cell, CellRow),
    "table_version_cells": (
        rendering.TableVersionCell,
        TableVersionCellRow,
    ),
    "table_version_headers": (
        rendering.TableVersionHeader,
        TableVersionHeaderRow,
    ),
    "table_groups": (rendering.TableGroup, TableGroupRow),
    "table_group_compositions": (
        rendering.TableGroupComposition,
        TableGroupCompositionRow,
    ),
    "table_associations": (
        rendering.TableAssociation,
        TableAssociationRow,
    ),
    "key_header_mappings": (
        rendering.KeyHeaderMapping,
        KeyHeaderMappingRow,
    ),
    "variables": (variables.Variable, VariableRow),
    "variable_versions": (
        variables.VariableVersion,
        VariableVersionRow,
    ),
    "compound_keys": (variables.CompoundKey, CompoundKeyRow),
    "key_compositions": (variables.KeyComposition, KeyCompositionRow),
    "categories": (glossary.Category, CategoryRow),
    "subcategories": (glossary.SubCategory, SubCategoryRow),
    "subcategory_versions": (
        glossary.SubCategoryVersion,
        SubCategoryVersionRow,
    ),
    "subcategory_items": (
        glossary.SubCategoryItem,
        SubCategoryItemRow,
    ),
    "items": (glossary.Item, ItemRow),
    "item_categories": (glossary.ItemCategory, ItemCategoryRow),
    "properties": (glossary.Property, PropertyRow),
    "property_categories": (
        glossary.PropertyCategory,
        PropertyCategoryRow,
    ),
    "contexts": (glossary.Context, ContextRow),
    "context_compositions": (
        glossary.ContextComposition,
        ContextCompositionRow,
    ),
    "compound_item_contexts": (
        glossary.CompoundItemContext,
        CompoundItemContextRow,
    ),
    "supercategory_compositions": (
        glossary.SupercategoryComposition,
        SupercategoryCompositionRow,
    ),
    "operation_list": (operations.Operation, OperationRow),
    "operation_versions": (
        operations.OperationVersion,
        OperationVersionRow,
    ),
    "aux_cell_mappings": (auxiliary.AuxCellMapping, AuxCellMappingRow),
}


def _load_rows(
    session: Session,
    model: type,
    row_cls: Callable[..., RowT],
) -> List[RowT]:
    """Load all rows of ``model`` into ``row_cls`` dataclasses.

    Selects only the columns named by the dataclass fields, so the
    resulting rows are plain values fully detached from the session.
    """
    names = [f.name for f in fields(row_cls)]  # type: ignore[arg-type]
    stmt = select(*(getattr(model, name) for name in names))
    return [row_cls(*row) for row in session.execute(stmt)]


class ModelSnapshot:
    """Indexed, in-memory copy of the DPM model.

    Primary stores are lists of frozen row dataclasses plus ``*_by_*``
    dictionaries keyed by primary key. Derived indexes shared between
    rules are built on demand through :meth:`cache`.
    """

    releases: List[ReleaseRow]
    concept_relations: List[ConceptRelationRow]
    related_concepts: List[RelatedConceptRow]
    organisations: List[OrganisationRow]
    datatypes: List[DataTypeRow]
    frameworks: List[FrameworkRow]
    modules: List[ModuleRow]
    module_versions: List[ModuleVersionRow]
    module_version_compositions: List[ModuleVersionCompositionRow]
    module_parameters: List[ModuleParametersRow]
    tables: List[TableRow]
    table_versions: List[TableVersionRow]
    headers: List[HeaderRow]
    header_versions: List[HeaderVersionRow]
    cells: List[CellRow]
    table_version_cells: List[TableVersionCellRow]
    table_version_headers: List[TableVersionHeaderRow]
    table_groups: List[TableGroupRow]
    table_group_compositions: List[TableGroupCompositionRow]
    table_associations: List[TableAssociationRow]
    key_header_mappings: List[KeyHeaderMappingRow]
    variables: List[VariableRow]
    variable_versions: List[VariableVersionRow]
    compound_keys: List[CompoundKeyRow]
    key_compositions: List[KeyCompositionRow]
    categories: List[CategoryRow]
    subcategories: List[SubCategoryRow]
    subcategory_versions: List[SubCategoryVersionRow]
    subcategory_items: List[SubCategoryItemRow]
    items: List[ItemRow]
    item_categories: List[ItemCategoryRow]
    properties: List[PropertyRow]
    property_categories: List[PropertyCategoryRow]
    contexts: List[ContextRow]
    context_compositions: List[ContextCompositionRow]
    compound_item_contexts: List[CompoundItemContextRow]
    supercategory_compositions: List[SupercategoryCompositionRow]
    operation_list: List[OperationRow]
    operation_versions: List[OperationVersionRow]
    aux_cell_mappings: List[AuxCellMappingRow]

    def __init__(self, session: Session) -> None:
        """Load every table needed by the modelling rules.

        Args:
            session: Session bound to the DPM database. Only read.
        """
        for store_name, (model, row_cls) in _STORES.items():
            setattr(
                self, store_name, _load_rows(session, model, row_cls)
            )
        self._build_indexes()

    @classmethod
    def from_rows(cls, **stores: List[Any]) -> "ModelSnapshot":
        """Build a snapshot directly from row lists (for tests).

        Args:
            **stores: Store name (e.g. ``table_versions``) to list of
                row dataclasses. Omitted stores default to empty.

        Returns:
            A fully indexed snapshot, no database involved.

        Raises:
            TypeError: On an unknown store name.
        """
        unknown = set(stores) - set(_STORES)
        if unknown:
            raise TypeError(
                f"Unknown snapshot stores: {', '.join(sorted(unknown))}"
            )
        snapshot = cls.__new__(cls)
        for store_name in _STORES:
            setattr(snapshot, store_name, stores.get(store_name, []))
        snapshot._build_indexes()
        return snapshot

    def _build_indexes(self) -> None:
        """Build the primary-key dictionaries and the cache."""
        self.releases_by_id = {r.release_id: r for r in self.releases}
        self.organisations_by_id = {
            o.org_id: o for o in self.organisations
        }
        self.datatypes_by_id = {
            d.data_type_id: d for d in self.datatypes
        }
        self.frameworks_by_id = {
            f.framework_id: f for f in self.frameworks
        }
        self.modules_by_id = {m.module_id: m for m in self.modules}
        self.module_versions_by_vid = {
            mv.module_vid: mv for mv in self.module_versions
        }
        self.tables_by_id = {t.table_id: t for t in self.tables}
        self.table_versions_by_vid = {
            tv.table_vid: tv for tv in self.table_versions
        }
        self.headers_by_id = {h.header_id: h for h in self.headers}
        self.header_versions_by_vid = {
            hv.header_vid: hv for hv in self.header_versions
        }
        self.cells_by_id = {c.cell_id: c for c in self.cells}
        self.table_groups_by_id = {
            tg.table_group_id: tg for tg in self.table_groups
        }
        self.table_associations_by_id = {
            ta.association_id: ta for ta in self.table_associations
        }
        self.variables_by_id = {
            v.variable_id: v for v in self.variables
        }
        self.variable_versions_by_vid = {
            vv.variable_vid: vv for vv in self.variable_versions
        }
        self.compound_keys_by_id = {
            ck.key_id: ck for ck in self.compound_keys
        }
        self.categories_by_id = {
            c.category_id: c for c in self.categories
        }
        self.subcategories_by_id = {
            sc.subcategory_id: sc for sc in self.subcategories
        }
        self.subcategory_versions_by_vid = {
            sv.subcategory_vid: sv for sv in self.subcategory_versions
        }
        self.items_by_id = {i.item_id: i for i in self.items}
        self.properties_by_id = {
            p.property_id: p for p in self.properties
        }
        self.contexts_by_id = {c.context_id: c for c in self.contexts}
        self.operations_by_id = {
            o.operation_id: o for o in self.operation_list
        }

        self._cache: Dict[str, Any] = {}

    def cache(self, key: str, build: Callable[[], CachedT]) -> CachedT:
        """Return a derived index, building it once on first use.

        Args:
            key: Unique cache key. Prefix with the rule family (e.g.
                ``"axes:key_headers_by_tv"``) unless the index is a
                documented shared one.
            build: Zero-argument callable that builds the value.
        """
        if key not in self._cache:
            self._cache[key] = build()
        value: CachedT = self._cache[key]
        return value

    # --------------------------------------------------------------
    # Documented shared indexes
    # --------------------------------------------------------------

    def tvh_by_table_vid(
        self,
    ) -> Dict[int, List[TableVersionHeaderRow]]:
        """``TableVersionHeader`` rows grouped by ``table_vid``."""

        def build() -> Dict[int, List[TableVersionHeaderRow]]:
            grouped: Dict[int, List[TableVersionHeaderRow]] = {}
            for tvh in self.table_version_headers:
                grouped.setdefault(tvh.table_vid, []).append(tvh)
            return grouped

        return self.cache("shared:tvh_by_table_vid", build)

    def tvc_by_table_vid(self) -> Dict[int, List[TableVersionCellRow]]:
        """``TableVersionCell`` rows grouped by ``table_vid``."""

        def build() -> Dict[int, List[TableVersionCellRow]]:
            grouped: Dict[int, List[TableVersionCellRow]] = {}
            for tvc in self.table_version_cells:
                grouped.setdefault(tvc.table_vid, []).append(tvc)
            return grouped

        return self.cache("shared:tvc_by_table_vid", build)

    def mvc_by_module_vid(
        self,
    ) -> Dict[int, List[ModuleVersionCompositionRow]]:
        """``ModuleVersionComposition`` rows grouped by ``module_vid``."""

        def build() -> Dict[int, List[ModuleVersionCompositionRow]]:
            grouped: Dict[int, List[ModuleVersionCompositionRow]] = {}
            for mvc in self.module_version_compositions:
                grouped.setdefault(mvc.module_vid, []).append(mvc)
            return grouped

        return self.cache("shared:mvc_by_module_vid", build)

    def mvc_by_table_vid(
        self,
    ) -> Dict[int, List[ModuleVersionCompositionRow]]:
        """``ModuleVersionComposition`` rows grouped by ``table_vid``."""

        def build() -> Dict[int, List[ModuleVersionCompositionRow]]:
            grouped: Dict[int, List[ModuleVersionCompositionRow]] = {}
            for mvc in self.module_version_compositions:
                if mvc.table_vid is not None:
                    grouped.setdefault(mvc.table_vid, []).append(mvc)
            return grouped

        return self.cache("shared:mvc_by_table_vid", build)

    def context_compositions_by_context(
        self,
    ) -> Dict[int, List[ContextCompositionRow]]:
        """``ContextComposition`` rows grouped by ``context_id``."""

        def build() -> Dict[int, List[ContextCompositionRow]]:
            grouped: Dict[int, List[ContextCompositionRow]] = {}
            for cc in self.context_compositions:
                grouped.setdefault(cc.context_id, []).append(cc)
            return grouped

        return self.cache("shared:cc_by_context", build)

    def table_versions_by_table(
        self,
    ) -> Dict[int, List[TableVersionRow]]:
        """``TableVersion`` rows grouped by ``table_id``."""

        def build() -> Dict[int, List[TableVersionRow]]:
            grouped: Dict[int, List[TableVersionRow]] = {}
            for tv in self.table_versions:
                if tv.table_id is not None:
                    grouped.setdefault(tv.table_id, []).append(tv)
            return grouped

        return self.cache("shared:tv_by_table", build)

    def header_versions_by_header(
        self,
    ) -> Dict[int, List[HeaderVersionRow]]:
        """``HeaderVersion`` rows grouped by ``header_id``."""

        def build() -> Dict[int, List[HeaderVersionRow]]:
            grouped: Dict[int, List[HeaderVersionRow]] = {}
            for hv in self.header_versions:
                if hv.header_id is not None:
                    grouped.setdefault(hv.header_id, []).append(hv)
            return grouped

        return self.cache("shared:hv_by_header", build)

    def dpm1_datatype_codes(self) -> Dict[int, Optional[str]]:
        """DataTypeID -> DPM1-compatible datatype code.

        Applies :data:`DPM1_DATATYPE_REMAP` to each datatype code,
        mirroring the SQL ``#datatype_mapping`` temp table.
        """

        def build() -> Dict[int, Optional[str]]:
            remapped: Dict[int, Optional[str]] = {}
            for dt in self.datatypes:
                code = dt.code
                if code is not None:
                    code = DPM1_DATATYPE_REMAP.get(code, code)
                remapped[dt.data_type_id] = code
            return remapped

        return self.cache("shared:dpm1_datatype_codes", build)


__all__: Tuple[str, ...] = (
    "DPM1_DATATYPE_REMAP",
    "ModelSnapshot",
    "ReleaseRow",
    "ConceptRelationRow",
    "RelatedConceptRow",
    "OrganisationRow",
    "DataTypeRow",
    "FrameworkRow",
    "ModuleRow",
    "ModuleVersionRow",
    "ModuleVersionCompositionRow",
    "ModuleParametersRow",
    "TableRow",
    "TableVersionRow",
    "HeaderRow",
    "HeaderVersionRow",
    "CellRow",
    "TableVersionCellRow",
    "TableVersionHeaderRow",
    "TableGroupRow",
    "TableGroupCompositionRow",
    "TableAssociationRow",
    "KeyHeaderMappingRow",
    "VariableRow",
    "VariableVersionRow",
    "CompoundKeyRow",
    "KeyCompositionRow",
    "CategoryRow",
    "SubCategoryRow",
    "SubCategoryVersionRow",
    "SubCategoryItemRow",
    "ItemRow",
    "ItemCategoryRow",
    "PropertyRow",
    "PropertyCategoryRow",
    "ContextRow",
    "ContextCompositionRow",
    "CompoundItemContextRow",
    "SupercategoryCompositionRow",
    "OperationRow",
    "OperationVersionRow",
    "AuxCellMappingRow",
)
