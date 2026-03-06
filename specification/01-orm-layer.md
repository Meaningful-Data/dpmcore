# dpmcore Specification — Layer 1: ORM

## 1. Overview

The ORM layer maps the DPM 2.0 Refit metamodel to SQLAlchemy 2.0 model classes.
It is the foundational layer that all other layers depend on.

## 2. Technology

- **SQLAlchemy ≥ 2.0** with the `DeclarativeBase` pattern (not legacy
  `declarative_base()`)
- **Mapped columns** using `Mapped[T]` and `mapped_column()` for full type-hint
  integration
- **Multi-database**: SQLite (development/testing), PostgreSQL (production),
  SQL Server (legacy compatibility)

## 3. Base Infrastructure

### 3.1 Base Class

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    """Base for all dpmcore ORM models."""

    def to_dict(self) -> dict:
        """Serialize model instance to dictionary."""
        ...
```

All models inherit from `Base`. The `to_dict()` method provides basic
serialization. Consumers extending dpmcore can inherit from this same `Base`
to add custom models.

### 3.2 Session Management

```python
from dpmcore.orm import create_engine, create_session, SessionFactory

# Explicit session creation (preferred)
engine = create_engine("postgresql://user:pass@host/db")
session = create_session(engine)

# Session factory for dependency injection
factory = SessionFactory(engine)
with factory() as session:
    ...
```

**Rules:**

- No global session state. Sessions are always created explicitly.
- `SessionFactory` is a callable that creates scoped sessions — suitable for
  use as a FastAPI dependency or Django middleware.
- Connection pooling is configurable per engine.

### 3.3 Engine Configuration

```python
engine = create_engine(
    url="postgresql://user:pass@host/db",
    pool_size=20,
    max_overflow=40,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
)
```

For SQLite, pooling options are ignored and `StaticPool` is used for in-memory
databases.

## 4. Model Organisation

Models are organised into modules that mirror the DPM metamodel's four
functional components plus infrastructure and packaging:

| Module | DPM Component | Models |
|--------|---------------|--------|
| `orm/glossary.py` | Glossary | Category, Item, SubCategory, SubCategoryVersion, SubCategoryItem, Property, PropertyCategory, Context, ContextComposition, CompoundItemContext, SuperCategory |
| `orm/rendering.py` | Rendering | Table, TableVersion, Header, HeaderVersion, Cell, TableVersionCell, TableVersionHeader, TableGroup, TableGroupComposition, TableAssociation |
| `orm/variables.py` | Variables | Variable, VariableVersion, VariableCalculation, VariableGeneration, Dimension (logical concept via Property+SubCategory) |
| `orm/operations.py` | Operations | Operation, OperationVersion, OperationVersionData, OperationNode, OperationScope, OperationScopeComposition, Operator, OperatorArgument, OperandReference, OperandReferenceLocation |
| `orm/packaging.py` | Packaging | Framework, Module, ModuleVersion, ModuleVersionComposition, ModuleParameters, Release |
| `orm/infrastructure.py` | Infrastructure | Organisation, Language, User, Role, UserRole, DataType, DpmClass, DpmAttribute, Concept, ConceptRelation, Document, DocumentVersion, Subdivision, SubdivisionType, Translation, Changelog |
| `orm/views.py` | Query views | ViewDatapoints, ViewKeyComponents, ViewOpenKeys, ViewDataTypes, ViewOperations, ViewModules, ViewTableInfo, ViewOperationInfo, … |

## 5. Glossary Models

### 5.1 Category

The abstract base for all glossary entities.

```
Category
├── category_id: int (PK)
├── code: str (unique within scope)
├── name: str
├── description: str (optional)
├── is_enumerated: bool
├── is_super_category: bool
├── is_active: bool
├── ref_data_source: str (optional)
├── concept_guid: str (FK → Concept)
│
├── subcategories → SubCategory[] (1:N)
├── property_categories → PropertyCategory[] (1:N)
├── supercategory_compositions → [] (N:M)
└── concept → Concept
```

### 5.2 Item

Concrete category member representing an enumerated value (e.g., a country
code, a currency, a metric).

```
Item
├── item_id: int (PK)
├── name: str
├── description: str (optional)
├── is_compound: bool
├── is_property: bool
├── is_active: bool
├── concept_guid: str (FK → Concept)
│
├── item_categories → ItemCategory[] (1:N, release-versioned)
├── property → Property (1:1, when is_property=True)
├── operand_references → OperandReference[] (1:N)
├── context_compositions → ContextComposition[] (1:N)
├── compound_item_contexts → CompoundItemContext[] (1:N)
└── concept → Concept
```

### 5.3 ItemCategory

Links an Item to a Category with release versioning.

```
ItemCategory
├── (item_id, start_release_id): composite PK
├── category_id: int (FK → Category)
├── code: str
├── is_default_item: bool
├── signature: str (optional)
├── end_release_id: int (FK → Release, optional)
├── concept_guid: str
│
├── item → Item
├── category → Category
├── start_release → Release
└── end_release → Release (optional)
```

### 5.4 SubCategory

Alternative grouping within a Category.

```
SubCategory
├── subcategory_id: int (PK)
├── category_id: int (FK → Category)
├── code: str
├── name: str
├── description: str (optional)
├── concept_guid: str (FK → Concept)
│
├── category → Category
├── subcategory_versions → SubCategoryVersion[] (1:N)
├── operand_references → OperandReference[] (1:N)
└── concept → Concept
```

### 5.5 SubCategoryVersion

Release-versioned snapshot of a SubCategory.

```
SubCategoryVersion
├── subcategory_vid: int (PK)
├── subcategory_id: int (FK → SubCategory)
├── start_release_id: int (FK → Release)
├── end_release_id: int (FK → Release, optional)
├── concept_guid: str (FK → Concept)
│
├── subcategory → SubCategory
├── subcategory_items → SubCategoryItem[] (1:N)
├── header_versions → HeaderVersion[] (1:N)
├── variable_versions → VariableVersion[] (1:N)
├── start_release → Release
└── end_release → Release (optional)
```

### 5.6 SubCategoryItem

An Item within a SubCategoryVersion, with ordering and optional operators.

```
SubCategoryItem
├── (item_id, subcategory_vid): composite PK
├── order: int
├── label: str (optional)
├── parent_item_id: int (self-FK, optional)
├── comparison_operator_id: int (FK → Operator, optional)
├── arithmetic_operator_id: int (FK → Operator, optional)
├── concept_guid: str (FK → Concept)
│
├── item → Item
├── subcategory_version → SubCategoryVersion
├── parent_item → SubCategoryItem (self-referential)
├── comparison_operator → Operator (optional)
└── arithmetic_operator → Operator (optional)
```

### 5.7 Property

An aspect/characteristic — links to an Item (since every Property is also an
Item in the DPM model).

```
Property
├── property_id: int (PK, FK → Item.item_id)
├── is_composite: bool
├── is_metric: bool
├── data_type_id: int (FK → DataType, optional)
├── value_length: int (optional)
├── period_type: str (optional)
├── concept_guid: str (FK → Concept)
│
├── item → Item (1:1)
├── datatype → DataType (optional)
├── property_categories → PropertyCategory[] (1:N)
├── context_compositions → ContextComposition[] (1:N)
├── variable_versions → VariableVersion[] (1:N)
├── header_versions → HeaderVersion[] (1:N)
├── table_versions → TableVersion[] (1:N)
└── concept → Concept
```

### 5.8 PropertyCategory

Release-versioned link between a Property and the Category it belongs to.

```
PropertyCategory
├── (property_id, start_release_id): composite PK
├── category_id: int (FK → Category)
├── end_release_id: int (FK → Release, optional)
├── concept_guid: str
│
├── property → Property
├── category → Category
├── start_release → Release
└── end_release → Release (optional)
```

### 5.9 Context

A reusable signature grouping Properties for CompoundItems.

```
Context
├── context_id: int (PK)
├── signature: str (unique)
├── concept_guid: str (FK → Concept)
│
├── context_compositions → ContextComposition[] (1:N)
├── variable_versions → VariableVersion[] (1:N)
├── header_versions → HeaderVersion[] (1:N)
├── table_versions → TableVersion[] (1:N)
├── compound_item_contexts → CompoundItemContext[] (1:N)
└── concept → Concept
```

### 5.10 ContextComposition

Maps Properties (and optionally specific Items) within a Context.

```
ContextComposition
├── (context_id, property_id): composite PK
├── item_id: int (FK → Item, optional)
├── concept_guid: str (FK → Concept)
│
├── context → Context
├── property → Property
├── item → Item (optional)
└── concept → Concept
```

### 5.11 CompoundItemContext

Release-versioned association of a compound Item with a Context.

```
CompoundItemContext
├── (item_id, start_release_id): composite PK
├── context_id: int (FK → Context)
├── end_release_id: int (FK → Release, optional)
├── concept_guid: str
│
├── item → Item
├── context → Context
├── start_release → Release
└── end_release → Release (optional)
```

## 6. Rendering Models

### 6.1 Table

Top-level reporting table.

```
Table
├── table_id: int (PK)
├── is_abstract: bool
├── has_open_columns: bool
├── has_open_rows: bool
├── has_open_sheets: bool
├── is_normalised: bool
├── is_flat: bool
├── concept_guid: str (FK → Concept)
│
├── headers → Header[] (1:N)
├── cells → Cell[] (1:N)
├── table_versions → TableVersion[] (1:N)
├── abstract_table_versions → TableVersion[] (1:N, as abstract table)
├── table_group_compositions → TableGroupComposition[] (1:N)
├── module_version_compositions → ModuleVersionComposition[] (1:N)
└── concept → Concept
```

### 6.2 TableVersion

A release-versioned snapshot of a Table with dimensional assignments.

```
TableVersion
├── table_vid: int (PK)
├── code: str
├── name: str
├── description: str (optional)
├── table_id: int (FK → Table)
├── abstract_table_id: int (FK → Table, optional)
├── key_id: int (FK → CompoundKey, optional)
├── property_id: int (FK → Property, optional)
├── context_id: int (FK → Context, optional)
├── start_release_id: int (FK → Release)
├── end_release_id: int (FK → Release, optional)
├── concept_guid: str (FK → Concept)
│
├── table → Table
├── abstract_table → Table (optional)
├── key → CompoundKey (optional)
├── property → Property (optional)
├── context → Context (optional)
├── table_version_cells → TableVersionCell[] (1:N)
├── table_version_headers → TableVersionHeader[] (1:N)
├── module_version_compositions → ModuleVersionComposition[] (1:N)
├── start_release → Release
└── end_release → Release (optional)
```

### 6.3 Header

A header axis (column, row, or sheet) within a Table.

```
Header
├── header_id: int (PK)
├── table_id: int (FK → Table)
├── direction: str(1) ('x' = column, 'y' = row, 'z' = sheet)
├── is_key: bool
├── concept_guid: str (FK → Concept)
│
├── table → Table
├── header_versions → HeaderVersion[] (1:N)
├── column_cells → Cell[] (1:N, as column header)
├── row_cells → Cell[] (1:N, as row header)
├── sheet_cells → Cell[] (1:N, as sheet header)
└── concept → Concept
```

### 6.4 HeaderVersion

Release-versioned snapshot of a Header with semantic bindings.

```
HeaderVersion
├── header_vid: int (PK)
├── header_id: int (FK → Header)
├── code: str
├── label: str (optional)
├── property_id: int (FK → Property, optional)
├── context_id: int (FK → Context, optional)
├── subcategory_vid: int (FK → SubCategoryVersion, optional)
├── key_variable_vid: int (FK → VariableVersion, optional)
├── start_release_id: int (FK → Release)
├── end_release_id: int (FK → Release, optional)
├── concept_guid: str (FK → Concept)
│
├── header → Header
├── property → Property (optional)
├── context → Context (optional)
├── subcategory_version → SubCategoryVersion (optional)
├── key_variable_version → VariableVersion (optional)
├── start_release → Release
└── end_release → Release (optional)
```

### 6.5 Cell

An intersection point in a Table (column × row × sheet).

```
Cell
├── cell_id: int (PK)
├── table_id: int (FK → Table)
├── column_id: int (FK → Header)
├── row_id: int (FK → Header)
├── sheet_id: int (FK → Header, optional)
├── concept_guid: str (FK → Concept)
│
├── table → Table
├── column_header → Header
├── row_header → Header
├── sheet_header → Header (optional)
├── table_version_cells → TableVersionCell[] (1:N)
├── operand_reference_locations → OperandReferenceLocation[] (1:N)
└── concept → Concept
```

### 6.6 TableVersionCell

Release-scoped cell configuration within a TableVersion.

```
TableVersionCell
├── (table_vid, cell_id): composite PK
├── cell_code: str
├── is_nullable: bool
├── is_excluded: bool
├── is_void: bool
├── sign: str (optional)
├── variable_vid: int (FK → VariableVersion, optional)
├── concept_guid: str
│
├── table_version → TableVersion
├── cell → Cell
└── variable_version → VariableVersion (optional)
```

### 6.7 TableVersionHeader

Ordered header assignment within a TableVersion.

```
TableVersionHeader
├── (table_vid, header_id): composite PK
├── header_vid: int (FK → HeaderVersion)
├── parent_header_id: int (FK → Header, optional)
├── parent_first: bool
├── order: int
├── is_abstract: bool
├── is_unique: bool
├── concept_guid: str
│
├── table_version → TableVersion
├── header → Header
├── header_version → HeaderVersion
└── parent_header → Header (optional)
```

### 6.8 TableGroup

Logical grouping of tables for navigation.

```
TableGroup
├── table_group_id: int (PK)
├── code: str
├── name: str
├── description: str (optional)
├── type: str (optional)
├── parent_table_group_id: int (self-FK, optional)
├── start_release_id: int (FK → Release)
├── end_release_id: int (FK → Release, optional)
├── concept_guid: str (FK → Concept)
│
├── parent_table_group → TableGroup (optional, self-referential)
├── child_table_groups → TableGroup[] (1:N)
├── table_group_compositions → TableGroupComposition[] (1:N)
├── start_release → Release
└── end_release → Release (optional)
```

### 6.9 TableGroupComposition

Links Tables to TableGroups with ordering.

```
TableGroupComposition
├── (table_group_id, table_id): composite PK
├── order: int
├── start_release_id: int (FK → Release)
├── end_release_id: int (FK → Release, optional)
├── concept_guid: str
│
├── table_group → TableGroup
├── table → Table
├── start_release → Release
└── end_release → Release (optional)
```

### 6.10 TableAssociation

Parent-child relationships between TableVersions.

```
TableAssociation
├── association_id: int (PK)
├── child_table_vid: int (FK → TableVersion)
├── parent_table_vid: int (FK → TableVersion)
├── name: str (optional)
├── description: str (optional)
├── is_identifying: bool
├── is_subtype: bool
├── subtype_discriminator: int (FK → Header, optional)
├── cardinality: str(3)
├── concept_guid: str (FK → Concept)
│
├── child_table_version → TableVersion
├── parent_table_version → TableVersion
├── subtype_discriminator_header → Header (optional)
└── concept → Concept
```

## 7. Variable Models

### 7.1 Variable

Abstract variable definition (fact, key, or attribute).

```
Variable
├── variable_id: int (PK)
├── type: str ('F' = Fact, 'K' = Key, 'A' = Attribute)
├── concept_guid: str (FK → Concept)
│
├── variable_versions → VariableVersion[] (1:N)
├── variable_calculations → VariableCalculation[] (1:N)
├── operand_references → OperandReference[] (1:N)
└── concept → Concept
```

### 7.2 VariableVersion

Release-versioned snapshot of a Variable with semantic bindings.

```
VariableVersion
├── variable_vid: int (PK)
├── variable_id: int (FK → Variable)
├── property_id: int (FK → Property, optional)
├── subcategory_vid: int (FK → SubCategoryVersion, optional)
├── context_id: int (FK → Context, optional)
├── key_id: int (FK → CompoundKey, optional)
├── is_multi_valued: bool
├── code: str
├── name: str
├── start_release_id: int (FK → Release)
├── end_release_id: int (FK → Release, optional)
├── concept_guid: str (FK → Concept)
│
├── variable → Variable
├── property → Property (optional)
├── subcategory_version → SubCategoryVersion (optional)
├── context → Context (optional)
├── key → CompoundKey (optional)
├── key_compositions → KeyComposition[] (1:N)
├── module_parameters → ModuleParameters[] (1:N)
├── table_version_cells → TableVersionCell[] (1:N)
├── header_versions → HeaderVersion[] (1:N)
├── start_release → Release
└── end_release → Release (optional)
```

### 7.3 VariableCalculation

Links a Variable to an Operation within a Module.

```
VariableCalculation
├── (module_id, variable_id, operation_vid): composite PK
├── from_reference_date: date (optional)
├── to_reference_date: date (optional)
├── concept_guid: str
│
├── module → Module
├── variable → Variable
└── operation_version → OperationVersion
```

### 7.4 VariableGeneration

Tracks batch variable generation jobs.

```
VariableGeneration
├── variable_generation_id: int (PK)
├── start_date: datetime
├── end_date: datetime (optional)
├── status: str
├── release_id: int (FK → Release)
├── error: str(4000) (optional)
│
└── release → Release
```

### 7.5 CompoundKey & KeyComposition

Multi-variable key definitions.

```
CompoundKey
├── key_id: int (PK)
├── signature: str (unique)
├── concept_guid: str (FK → Concept)
│
├── key_compositions → KeyComposition[] (1:N)
├── module_versions → ModuleVersion[] (1:N)
└── table_versions → TableVersion[] (1:N)

KeyComposition
├── (key_id, variable_vid): composite PK
├── concept_guid: str
│
├── compound_key → CompoundKey
└── variable_version → VariableVersion
```

## 8. Operation Models

### 8.1 Operation

Container for business rule versions.

```
Operation
├── operation_id: int (PK)
├── code: str
├── type: str ('V' = validation, 'C' = calculation, 'P' = precondition)
├── source: str
├── group_operation_id: int (self-FK, optional)
├── concept_guid: str (FK → Concept)
│
├── group_operation → Operation (optional, self-referential)
├── grouped_operations → Operation[] (1:N)
├── operation_versions → OperationVersion[] (1:N)
└── concept → Concept
```

### 8.2 OperationVersion

Release-versioned snapshot with the DPM-XL expression.

```
OperationVersion
├── operation_vid: int (PK)
├── operation_id: int (FK → Operation)
├── precondition_operation_vid: int (self-FK, optional)
├── severity_operation_vid: int (self-FK, optional)
├── start_release_id: int (FK → Release)
├── end_release_id: int (FK → Release, optional)
├── expression: text
├── description: str (optional)
├── endorsement: str (optional)
├── is_variant_approved: bool
├── concept_guid: str (FK → Concept)
│
├── operation → Operation
├── precondition_operation → OperationVersion (optional)
├── severity_operation → OperationVersion (optional)
├── operation_nodes → OperationNode[] (1:N)
├── operation_scopes → OperationScope[] (1:N)
├── operation_version_data → OperationVersionData (1:1)
├── variable_calculations → VariableCalculation[] (1:N)
├── start_release → Release
└── end_release → Release (optional)
```

### 8.3 OperationVersionData

Additional metadata for an OperationVersion.

```
OperationVersionData
├── operation_vid: int (PK, FK → OperationVersion)
├── error: str(2000) (optional)
├── error_code: str (optional)
├── is_applying: bool
├── proposing_status: str (optional)
│
└── operation_version → OperationVersion
```

### 8.4 OperationNode

AST node within an operation's expression tree.

```
OperationNode
├── node_id: int (PK)
├── operation_vid: int (FK → OperationVersion)
├── parent_node_id: int (self-FK, optional)
├── operator_id: int (FK → Operator, optional)
├── argument_id: int (FK → OperatorArgument, optional)
├── absolute_tolerance: float (optional)
├── relative_tolerance: float (optional)
├── fallback_value: str (optional)
├── use_interval_arithmetics: bool
├── operand_type: str (optional)
├── is_leaf: bool
├── scalar: text (optional)
│
├── operation_version → OperationVersion
├── parent → OperationNode (optional, self-referential)
├── children → OperationNode[] (1:N)
├── operator → Operator (optional)
├── operator_argument → OperatorArgument (optional)
└── operand_references → OperandReference[] (1:N)
```

### 8.5 OperationScope & OperationScopeComposition

Defines which module versions an operation targets.

```
OperationScope
├── operation_scope_id: int (PK)
├── operation_vid: int (FK → OperationVersion)
├── is_active: int (smallint)
├── severity: str (optional, "error"|"warning"|"info")
├── from_submission_date: date (optional)
├── concept_guid: str
│
├── operation_version → OperationVersion
└── operation_scope_compositions → OperationScopeComposition[] (1:N)

OperationScopeComposition
├── (operation_scope_id, module_vid): composite PK
├── concept_guid: str
│
├── operation_scope → OperationScope
└── module_version → ModuleVersion
```

### 8.6 Operator & OperatorArgument

Operator definitions used in expression trees.

```
Operator
├── operator_id: int (PK)
├── name: str
├── symbol: str (optional)
├── type: str (optional)
│
├── operator_arguments → OperatorArgument[] (1:N)
└── operation_nodes → OperationNode[] (1:N)

OperatorArgument
├── argument_id: int (PK)
├── operator_id: int (FK → Operator)
├── order: int
├── is_mandatory: bool
├── name: str (optional)
│
├── operator → Operator
└── operation_nodes → OperationNode[] (1:N)
```

### 8.7 OperandReference & OperandReferenceLocation

Cell references within operation expressions.

```
OperandReference
├── operand_reference_id: int (PK)
├── node_id: int (FK → OperationNode)
├── x: str (optional, column coordinate)
├── y: str (optional, row coordinate)
├── z: str (optional, sheet coordinate)
├── operand_reference: str (optional, textual reference)
├── item_id: int (FK → Item, optional)
├── property_id: int (FK → Property, optional)
├── variable_id: int (FK → Variable, optional)
├── subcategory_id: int (FK → SubCategory, optional)
│
├── operation_node → OperationNode
├── item → Item (optional)
├── property → Property (optional)
├── variable → Variable (optional)
├── subcategory → SubCategory (optional)
└── operand_reference_locations → OperandReferenceLocation[] (1:N)

OperandReferenceLocation
├── (operand_reference_id, cell_id): composite PK
├── table: str (optional)
├── row: str (optional)
├── column: str (optional)
├── sheet: str (optional)
│
├── operand_reference → OperandReference
└── cell → Cell
```

## 9. Packaging Models

### 9.1 Framework

Top-level container for a reporting domain.

```
Framework
├── framework_id: int (PK)
├── code: str
├── name: str
├── description: str (optional)
├── concept_guid: str (FK → Concept)
│
├── modules → Module[] (1:N)
├── operation_code_prefixes → OperationCodePrefix[] (1:N)
└── concept → Concept
```

### 9.2 Module & ModuleVersion

```
Module
├── module_id: int (PK)
├── framework_id: int (FK → Framework)
├── concept_guid: str (FK → Concept)
│
├── framework → Framework
├── module_versions → ModuleVersion[] (1:N)
├── variable_calculations → VariableCalculation[] (1:N)
└── concept → Concept

ModuleVersion
├── module_vid: int (PK)
├── module_id: int (FK → Module)
├── global_key_id: int (FK → CompoundKey, optional)
├── start_release_id: int (FK → Release)
├── end_release_id: int (FK → Release, optional)
├── code: str
├── name: str
├── description: str (optional)
├── version_number: str (optional)
├── from_reference_date: date (optional)
├── to_reference_date: date (optional)
├── concept_guid: str (FK → Concept)
│
├── module → Module
├── global_key → CompoundKey (optional)
├── module_version_compositions → ModuleVersionComposition[] (1:N)
├── operation_scope_compositions → OperationScopeComposition[] (1:N)
├── module_parameters → ModuleParameters[] (1:N)
├── start_release → Release
└── end_release → Release (optional)
```

### 9.3 ModuleVersionComposition

Links tables (and their versions) to module versions.

```
ModuleVersionComposition
├── (module_vid, table_id): composite PK
├── table_vid: int (FK → TableVersion, optional)
├── order: int
├── concept_guid: str
│
├── module_version → ModuleVersion
├── table → Table
└── table_version → TableVersion (optional)
```

### 9.4 ModuleParameters

Variables exposed as module parameters.

```
ModuleParameters
├── (module_vid, variable_vid): composite PK
├── concept_guid: str
│
├── module_version → ModuleVersion
└── variable_version → VariableVersion
```

### 9.5 Release

Publication milestone.

```
Release
├── release_id: int (PK)
├── code: str
├── date: date
├── description: str (optional)
├── status: str (optional)
├── is_current: bool
├── concept_guid: str (FK → Concept)
│
└── concept → Concept
```

### 9.6 OperationCodePrefix

Code prefix conventions per framework.

```
OperationCodePrefix
├── operation_code_prefix_id: int (PK)
├── code: str (unique)
├── list_name: str (optional)
├── framework_id: int (FK → Framework)
│
└── framework → Framework
```

## 10. Infrastructure Models

### 10.1 Organisation

```
Organisation
├── org_id: int (PK)
├── name: str (unique)
├── acronym: str (optional)
├── id_prefix: str (unique, optional)
├── concept_guid: str (FK → Concept)
│
├── concept → Concept
├── users → User[] (1:N)
├── documents → Document[] (1:N)
└── translations → Translation[] (via translator)
```

### 10.2 Concept & ConceptRelation

The universal identity object — every DPM entity has a Concept.

```
Concept
├── concept_guid: str (PK, UUID-format)
├── class_id: int (FK → DpmClass)
├── owner_id: int (FK → Organisation)
│
├── dpm_class → DpmClass
├── owner → Organisation
├── related_concepts → RelatedConcept[] (1:N)
└── context_compositions → ContextComposition[] (1:N)

ConceptRelation
├── concept_relation_id: int (PK)
├── type: str
├── concept_guid: str
│
└── related_concepts → RelatedConcept[] (1:N)
```

### 10.3 DpmClass & DpmAttribute

Metamodel class and attribute definitions.

```
DpmClass
├── class_id: int (PK)
├── name: str
├── type: str (optional)
├── owner_class_id: int (self-FK, optional)
│
├── owner_class → DpmClass (optional, self-referential)
├── owned_classes → DpmClass[] (1:N)
├── concepts → Concept[] (1:N)
├── dpm_attributes → DpmAttribute[] (1:N)
└── changelogs → Changelog[] (1:N)

DpmAttribute
├── attribute_id: int (PK)
├── class_id: int (FK → DpmClass)
├── name: str
├── has_translations: bool
│
├── dpm_class → DpmClass
├── changelogs → Changelog[] (1:N)
└── translations → Translation[] (1:N)
```

### 10.4 Other Infrastructure

```
Language         : language_code (PK), name
User             : user_id (PK), org_id (FK), name
Role             : role_id (PK), name
UserRole         : (user_id, role_id) composite PK
DataType         : data_type_id (PK), code (unique), name (unique),
                   parent_data_type_id (self-FK), is_active
Translation      : (concept_guid, attribute_id, translator_id, language_code) PK,
                   translation (text)
Changelog        : (concept_guid, class_id, attribute_id, timestamp) PK,
                   old_value, new_value, change_type, status,
                   user_id (FK), release_id (FK)
Document         : document_id (PK), name, code, type, org_id (FK)
DocumentVersion  : document_vid (PK), document_id (FK), code, version, publication_date
Subdivision      : subdivision_id (PK), document_vid (FK), subdivision_type_id (FK),
                   number, parent_subdivision_id (self-FK), structure_path, text_excerpt
SubdivisionType  : subdivision_type_id (PK), name, description
Reference        : (subdivision_id, concept_guid) composite PK
```

## 11. View Models

View models encapsulate complex joins as queryable objects. They do NOT map to
database views — they build queries programmatically using SQLAlchemy and
execute them into Pandas DataFrames.

| View | Purpose | Key Methods |
|------|---------|-------------|
| `ViewDatapoints` | Datapoint cell data with context | `get_table_data()`, `get_from_table_vid()` |
| `ViewKeyComponents` | Key components per table | `get_by_table()`, `get_by_table_version_id()` |
| `ViewOpenKeys` | Open (unconstrained) keys | `get_keys()`, `get_all_keys()` |
| `ViewDataTypes` | Data type mappings | `get_data_types()` |
| `ViewOperations` | Operation definitions | `get_operations()`, `get_expression_from_operation_code()` |
| `ViewOperationFromModule` | Module-scoped operations | `get_operations_from_moduleversion_id()` |
| `ViewOperationInfo` | Operation node details | `get_operation_info()` |
| `ViewTableInfo` | Table metadata | `get_tables_from_module_code()` |
| `ViewModules` | Module-table mapping | `get_all_modules()` |

## 12. Release Filtering

Most versioned entities use start/end release pairs. The ORM provides a
utility for filtering:

```python
def filter_by_release(
    query: Query,
    start_col: Column,
    end_col: Column,
    release_id: int,
) -> Query:
    """Return only versions active in the given release."""
    return query.filter(
        start_col <= release_id,
        or_(end_col.is_(None), end_col > release_id),
    )
```

This pattern applies to: ItemCategory, PropertyCategory, SubCategoryVersion,
HeaderVersion, TableVersion, VariableVersion, OperationVersion, ModuleVersion,
TableGroup, TableGroupComposition, CompoundItemContext, and Release itself.

## 13. Migration from Current Codebase

| Current (py_dpm) | Target (dpmcore) | Changes |
|-------------------|-------------------|---------|
| SQLAlchemy 1.4 `declarative_base()` | SQLAlchemy 2.0 `DeclarativeBase` | Migrate to Mapped[] annotations |
| Global `get_session()` | `SessionFactory` + explicit sessions | Remove global state |
| Single `models.py` (3659 lines) | Split into 7 modules | Better maintainability |
| View models with pandas coupling | View models with optional pandas | Allow pure SQLAlchemy usage |
| CamelCase table/column names | Keep CamelCase (DB compat) | Python attrs use snake_case |
