# dpmcore Specification — Layer 8: Modelling Services (Model Validation & Variable Generation)

**Status:** Draft for review
**Source material:** stored procedures extracted from `input/DPM_REFIT_EBA_DEV_260715.bacpac`
(SQL bodies preserved under `specification/reference/stored-procedures/`).

## 1. Purpose and scope

The EBA DPM Refit development database implements its modelling workflow as
T-SQL stored procedures. This specification defines how their **business
logic** is reimplemented as native dpmcore services. This is a **port of
behaviour, not of implementation**: the SQL architecture (result tables,
cursors, sentinel releases, dynamic DDL) is replaced by idiomatic Python, but
the *outputs* — the set of violations found, the set of variables generated —
must be equivalent.

### 1.1 Source procedures and their disposition

| # | Stored procedure | Disposition in dpmcore |
|---|------------------|------------------------|
| 1 | `check_modelling_rules_tidy` | **Port** → `ModelValidationService` (§4) |
| 2 | `check_modelling_rules_playground` | **Subsumed** — strict subset of `tidy`; covered by the `release` parameter of `ModelValidationService` (§3.3) |
| 3 | `variable_generation_tidy` | **Port** → `VariableGenerationService` (§5) |
| 4 | `Cleaning_Service_01` | **Reinterpreted** → read-only `OrphanAnalysisService` (§6, optional phase) |
| 5 | `insert_GUIDs` | **Out of scope** — GUID/Concept bookkeeping is a persistence concern (§7) |
| 6–11 | `DeleteDPMRefitTables`, `DropDPMRefitTables`, `DisableForeignKeys`, `EnableForeignKeys`, `DropForeignKeys`, `SetColumnToNullable` | **Out of scope** — SQL Server DDL administration with no domain logic (§7) |

### 1.2 Core requirements (from product owner)

1. **All validations run** — the full rule set of `check_modelling_rules_tidy`.
2. **No result persistence** — nothing is written to `ModelViolations`,
   `VarGeneration_Detail`, `VarGeneration_Summary`, `Aux_CellStatus` or any
   other table. Results are returned as Python objects that serialise to
   dict/JSON, consistent with the rest of the library (frozen dataclasses +
   `to_dict()`, per `03-services.md`).
3. **Variable generation computes but does not store** — the service produces
   the complete *generation plan* (variables to create, versions to create,
   cell assignments, keys, filing indicators, contexts) without mutating the
   database.
4. **Python-first architecture** — do not transliterate the 119 SQL queries.
   Restructure around an in-memory model snapshot and pure rule functions.
5. **Result equivalence** — for the same input database, the set of violations
   and the set of generated variables must match what the SQL procedures
   produce (verified by the parity harness, §9).

## 2. Design principles

1. **Read-only services.** Both services honour the existing services-layer
   contract (`services/__init__.py`): they receive a `Session`, only read,
   never mutate. This is a natural fit — the SQL procedures' writes were
   only (a) result storage, which we replace with return values, and
   (b) model mutation in variable generation, which we replace with a plan.
2. **Snapshot + pure rules.** Rather than 119 independent multi-join queries,
   load the relevant slice of the model once into an indexed, in-memory
   **`ModelSnapshot`**, then evaluate each rule as a pure function
   `rule(ctx: RuleContext) -> list[Violation]`. Benefits: each rule is
   independently unit-testable without a DB, the full run does bounded I/O,
   and rules share derived indexes (e.g. "active table versions of modules
   changing in this release") instead of recomputing them.
3. **Never raise on validation failure.** Following `SemanticService` /
   `SyntaxService`: a model full of violations is a *successful* validation
   run. Exceptions are reserved for operational failures (bad release code,
   broken DB).
4. **Stable, unique rule identifiers.** The SQL reuses some `ViolationCode`s
   for distinct checks (`3_5`, `3_10`, `3_15`, `4_3`, `4_5`, `4_9`, `6_6`,
   `6_11`). Each Python rule gets a **unique** `rule_id` (reused codes get a
   letter suffix: `3_5a`, `3_5b`, …); the original SQL code is preserved as
   `legacy_code` for traceability.
5. **Severity, not `isBlocking`.** The SQL `isBlocking` bit maps onto the
   library-wide severity system (`SEVERITY_ERROR` / `SEVERITY_WARNING` /
   `SEVERITY_INFO`): `isBlocking=1` → `error`, `isBlocking=0` → `warning`.
6. **JSON-serialisable end to end.** Every result object has `to_dict()`
   producing plain dict/list/str/int/bool/None, directly consumable by the
   REST `envelope()` and by `json.dumps`.

## 3. Shared infrastructure

### 3.1 Module layout

```
src/dpmcore/services/model_validation/
    __init__.py          # exports ModelValidationService, result types
    service.py           # ModelValidationService (orchestrator)
    snapshot.py          # ModelSnapshot loader + indexes
    types.py             # Violation, ModelValidationResult, ObjectRef, enums
    registry.py          # rule registration/discovery, RuleContext
    rules/
        lifecycle.py     # family 1_x  (module/table/tablegroup versioning)
        axes.py          # family 2_x  (table axis structure)
        headers.py       # family 3_x  (header-level rules)
        assignments.py   # family 4_x  (property/context/item assignment)
        glossary.py      # family 6_x  (code hygiene & catalog integrity)

src/dpmcore/services/variable_generation/
    __init__.py          # exports VariableGenerationService, result types
    service.py           # VariableGenerationService (orchestrator)
    snapshot.py          # generation-specific snapshot (cells, aspects)
    types.py             # Aspect, CellAssignment, Proposed*, results, enums
    aspects.py           # aspect computation (key / property / context)
    keys.py              # key variables + compound (table) keys
    filing_indicators.py # filing-indicator derivation
    assignment.py        # the outcome-decision algorithm (§5.6)
    checks.py            # 5_x consistency checks
    reporting.py         # detail/summary report assembly
```

### 3.2 `ObjectRef` — locating the offending/affected object

The SQL `ModelViolations` table has ~25 nullable identifier columns
(TableVID, HeaderVID, ItemCode, CellID, …). In Python this collapses to a
compact reference type used by both services:

```python
@dataclass(frozen=True)
class ObjectRef:
    """Reference to a DPM model object."""
    kind: str                      # "table_version", "header", "item", "cell", ...
    id: int | str | None = None    # primary identifier (VID or ID)
    code: str | None = None        # business code where available
    name: str | None = None

    def to_dict(self) -> dict: ...
```

A `Violation` carries `objects: tuple[ObjectRef, ...]` — the primary object
first, then any secondary objects (e.g. the *other* cell in a duplicate-aspect
violation, the previous version in a lifecycle violation). This preserves all
the information the SQL columns carried while staying self-describing in JSON.

### 3.3 Release semantics (`ReleaseContext`)

The SQL procedures resolve `@CurrentRelease` from `Release.IsCurrent = 1`
(tidy) or hard-pin it to the sandbox release `9999` (playground), and use
`9999` throughout as an "open/draft" sentinel. dpmcore's ORM has no such
sentinel — currency is `end_release_id IS NULL` — but migrated EBA databases
*may contain* a release row with ID 9999. To reproduce SQL behaviour exactly
while keeping a clean API:

```python
@dataclass(frozen=True)
class ReleaseContext:
    current_release_id: int          # resolved release under validation
    draft_release_id: int | None     # 9999 if such a release exists in data
    # --- predicates used by rules (mirror the SQL WHERE patterns) ---
    def is_open(self, end_release_id: int | None) -> bool:
        """SQL: (EndReleaseID IS NULL) OR EndReleaseID = 9999"""
    def starts_in_current(self, start_release_id: int | None) -> bool:
        """SQL: StartReleaseID = @CurrentRelease OR StartReleaseID = 9999"""
    def is_active(self, start: int | None, end: int | None) -> bool:
        """Version is live in the release under validation."""
```

**Resolution rules** (in `service.py`, shared by both services):

- `release_id=None, release_code=None` → the release with `is_current=True`
  (exactly the `tidy` behaviour). Error if none exists.
- `release_id=9999` (or the code of the draft release) → exactly the
  `playground` behaviour, with the *full* tidy rule set. This is deliberate:
  playground's smaller rule set is historical drift, not a requirement.
- Any other explicit `release_id` / `release_code` → validate as of that
  release (useful for re-validating historical releases).

All rule predicates go through `ReleaseContext` — no literal `9999` anywhere
in rule code.

### 3.4 `ModelSnapshot`

One loader queries each needed table **once** (using `query_utils.chunked_in`
where key sets are large) and builds plain-Python indexed structures:

```python
class ModelSnapshot:
    # keyed primary stores (dict[id, row-dataclass])
    releases, frameworks, modules, module_versions, tables, table_versions,
    headers, header_versions, cells, table_version_cells, table_version_headers,
    table_groups, table_group_compositions, table_associations,
    key_header_mappings, module_version_compositions, module_parameters,
    variables, variable_versions, compound_keys, key_compositions,
    categories, subcategories, subcategory_versions, subcategory_items,
    items, item_categories, properties, property_categories,
    contexts, context_compositions, compound_item_contexts, datatypes,
    operations, operation_versions, supercategory_compositions

    # derived indexes built lazily (cached) — examples:
    def tvh_by_table_vid(self) -> dict[int, list[TVHRow]]: ...
    def active_module_versions(self) -> list[MVRow]: ...
    def context_signature(self, context_id: int) -> str: ...
    def datatype_mapping(self) -> dict[int, str]:
        """DPM1-compatible remap used by 6_20/6_24: dt→d, u→s, es→s, o→s."""
```

Rows are lightweight frozen dataclasses (or named tuples), **not** live ORM
objects — the snapshot is detached from the session after loading, so rule
evaluation cannot trigger lazy loads.

Both services use the same snapshot loader; variable generation extends it
with cell-level data (`snapshot.py` in its package adds `Aux_CellMapping`
continuity data and per-cell context composition).

## 4. `ModelValidationService`

### 4.1 Public API

```python
class ModelValidationService(BaseService):
    """DPM model integrity validation (port of check_modelling_rules_tidy)."""

    def validate(
        self,
        release_id: int | None = None,
        release_code: str | None = None,
        rule_ids: Sequence[str] | None = None,   # run a subset (default: all)
        include_warnings: bool = True,
    ) -> ModelValidationResult: ...

    def list_rules(self) -> list[RuleInfo]:
        """Catalogue of all registered rules (id, legacy_code, family,
        severity, description) — introspection for docs/UI/CLI."""
```

### 4.2 Result types

```python
@dataclass(frozen=True)
class Violation:
    rule_id: str                  # unique, e.g. "1_5", "3_5a"
    legacy_code: str              # original SQL ViolationCode, e.g. "3_5"
    message: str                  # human-readable, may embed object codes
    severity: str                 # "error" (blocking) | "warning"
    objects: tuple[ObjectRef, ...]

@dataclass(frozen=True)
class ModelValidationResult:
    is_valid: bool                       # True iff no error-severity violations
    release_id: int
    release_code: str | None
    violations: tuple[Violation, ...]    # deterministic order: rule_id, then object id
    error_count: int
    warning_count: int
    rules_run: int
    elapsed_ms: float

    def to_dict(self) -> dict: ...
    def by_rule(self) -> dict[str, list[Violation]]: ...
```

JSON shape (via `to_dict()`; the REST layer wraps it in `envelope()`):

```json
{
  "is_valid": false,
  "release_id": 1010000003,
  "release_code": "4.2.1",
  "error_count": 2,
  "warning_count": 1,
  "rules_run": 119,
  "elapsed_ms": 842.1,
  "violations": [
    {
      "rule_id": "1_5",
      "legacy_code": "1_5",
      "severity": "error",
      "message": "Duplicate Table Code",
      "objects": [
        {"kind": "table_version", "id": 12345, "code": "C 01.00"},
        {"kind": "table_version", "id": 67890, "code": "C 01.00"}
      ]
    }
  ]
}
```

### 4.3 Rule engine

```python
@dataclass(frozen=True)
class RuleInfo:
    rule_id: str
    legacy_code: str
    family: str          # "lifecycle" | "axes" | "headers" | "assignments" | "glossary"
    severity: str
    description: str

RuleFn = Callable[[RuleContext], Iterable[Violation]]

def rule(rule_id: str, legacy_code: str, severity: str, description: str):
    """Decorator: registers the function in the rule registry."""
```

`RuleContext` bundles the `ModelSnapshot`, the `ReleaseContext`, and a
`make_violation(...)` helper that stamps rule metadata so rule bodies stay
minimal. The orchestrator imports the `rules/` modules (triggering
registration), evaluates each registered rule in `rule_id` order, and
aggregates. Rules must not depend on each other's output.

### 4.4 Rule catalogue

Every INSERT block of `check_modelling_rules_tidy` becomes exactly one
registered rule. The authoritative reference for each rule's exact predicate
is the SQL body (`specification/reference/stored-procedures/check_modelling_rules_tidy.sql`);
the implementer must translate the JOIN/WHERE logic faithfully, replacing
release arithmetic with `ReleaseContext` predicates. Known message typos in
the SQL ("Composiiton", "ModuleVesions", …) are **corrected** in the Python
messages; `legacy_code` keeps traceability.

Severity below reflects the SQL `isBlocking` flag; where the SQL text itself
says "Warning", severity is `warning`.

#### Family 1 — lifecycle (`rules/lifecycle.py`)

| rule_id | Description (normalised) |
|---------|--------------------------|
| 1_1 | Header has current version identical to previous version |
| 1_2 | TableVersion fields identical to previous TableVersion |
| 1_3 | TableVersion with non-null AbstractTableID in a ModuleVersionComposition whose abstract table is absent from the same ModuleVersion |
| 1_4 | Abstract table in ModuleVersionComposition without any non-abstract table for the same ModuleVersion |
| 1_5 | Duplicate table code |
| 1_6 | *(warning)* Abstract table found in composition of a TableGroup |
| 1_7 | Expired TableVersion referenced by an active ModuleVersion |
| 1_8 | New ModuleVersion with empty ModuleVersionComposition |
| 1_9 | New ModuleVersion with composition identical to the previous ModuleVersion |
| 1_10 | Table not assigned to any module but present in a TableGroup composition |
| 1_11 | Table does not belong to exactly one templateGroup TableGroup |
| 1_12 | TableGroup whose active tables do not all share at least one common active ModuleVersion |
| 1_13 | Table belongs to no templateGroup TableGroup |
| 1_14 | ModuleVersion number not greater than the previous version's number |
| 1_15 | ItemCategory/PropertyCategory changed with impact on a module but no new ModuleVersion created |
| 1_16 | Technical tables from the same abstract table in different template groups |
| 1_17 | Duplicate TableVersion name within modules changing in the current release |
| 1_18 | TableGroup code contains illegal characters (`-`, `–`, `(`, `)`, `.`, space) |
| 1_19 | Destination table of an association has different open row/column/sheet settings than the source table |
| 1_20 | Table with a new TableVersion still employed by an old active ModuleVersion |
| 1_21 | Table in a TableGroup starting in the draft release with draft TableGroupComposition start |
| 1_22 | Replicated (duplicate) TableAssociation |
| 1_23 | Inconsistent property categories between linked properties in a TableAssociation |
| 1_24 | TableAssociation header mapping does not cover exactly the primary-key headers |

#### Family 2 — axis structure (`rules/axes.py`)

| rule_id | Description |
|---------|-------------|
| 2_1 | Open-row table without key columns |
| 2_2 | Open-column table without key rows |
| 2_3 | Open-sheet table without key sheets |
| 2_4 | *(warning)* Open-row table without non-key columns |
| 2_5 | *(warning)* Open-column table without non-key rows |
| 2_6 | Closed row & column table missing rows or columns |
| 2_7 | Closed-row table with key columns |
| 2_8 | Closed-column table with key rows |
| 2_9 | Closed-sheet table with key sheets |
| 2_10 | Main properties assigned to more than one axis |
| 2_11 | No main property assigned to any axis |
| 2_12 | Not all non-abstract, non-key headers of the main-property axis carry a main property |
| 2_13 | Main property assigned to whole table that is not a metric |

#### Family 3 — headers (`rules/headers.py`)

| rule_id | Description |
|---------|-------------|
| 3_1 | Key header without any attached property |
| 3_2 | Key header declared abstract |
| 3_3 | Main property on sheet header that is not a metric |
| 3_4 | Header references an expired SubCategoryVersion |
| 3_5a | Abstract header with no non-abstract descendants |
| 3_5b | Header whose parent header is not a TableVersionHeader of the same TableVersion |
| 3_6 | Key header with a metric property attached |
| 3_7 | Property of a key header also assigned to another key header |
| 3_8 | Property present both in a key header and in a context of the same table |
| 3_9 | SubCategory's category incompatible with the property's category |
| 3_10a | Attribute header not associated with a unique other active header of the same direction |
| 3_10b | *(warning)* Main property on header belongs to an empty-string-allowed data type |
| 3_11 | Attributes defined for fact headers on a direction without a main property |
| 3_12 | Attributes defined for key headers on a direction other than the key header's |
| 3_14 | Attribute header main-property data type differs from previous version |
| 3_15a | Header with an associated attribute changed property data type vs previous version |
| 3_15b | Header order violates the parent-first specification |
| 3_16 | Abstract header with a property or context assigned |

#### Family 4 — assignments (`rules/assignments.py`)

| rule_id | Description |
|---------|-------------|
| 4_1a / 4_1b | Main property of a header (4_1a) or of the whole table (4_1b) also carried by a key header of the same table. *Implementation note: the original SQL analysis missed 4_1 entirely — its blocks use lowercase `as ViolationCode`.* |
| 4_2 | Same (main PropertyID, ContextID) combination on more than one header |
| 4_3a / 4_3b | Main property of a header also present as context property on the same table (two SQL variants) |
| 4_4 | Duplicate header code |
| 4_5a / 4_5b | Property in a table context already assigned to the context of another direction of the same table (two SQL variants) |
| 4_6 | Non-enumerated property assigned to a context composition |
| 4_7 | Property category and item category assignments differ |
| 4_7b | Property category has expired |
| 4_7c | Property code has expired |
| 4_7d | Item category has expired |
| 4_8 | Main property assigned to more than one distinct subcategory across this release's ModuleVersions |
| 4_9a | Default item appears in the context of a header of a table from a module updated in the current release |
| 4_9b | *(warning)* Default item appears in the whole-table context (SQL `isBlocking = 0`) |
| 4_9c | *(warning)* Default item appears in the context of a CompoundItem updated in the current release |
| 4_10 | Default item appears in the composition of a subcategory associated with a header |

*Severity corrections discovered during the port (SQL `isBlocking`
wins over this catalogue's first draft): 1_1, 1_5, 1_9, 1_15 and 3_3
are warnings (`isBlocking = 0`); 4_9b and 4_9c are warnings; 4_9 has
THREE SQL blocks, not two. The implementation was audited 1:1
against all 119 SQL INSERT blocks.*

#### Family 6 — glossary & code hygiene (`rules/glossary.py`)

| rule_id | Description |
|---------|-------------|
| 6_1 | Property in use without a unique open PropertyCategory |
| 6_2 | Item in use without a unique open ItemCategory |
| 6_3 | Metric property with incompatible data type |
| 6_4 | Non-metric property with monetary data type |
| 6_5 | Non-enumerated category (other than Not applicable) with items or subcategories |
| 6_6a | Duplicate item code within a category (active items) |
| 6_6b | Duplicate property code within a category (active items) |
| 6_7 | Metric property in an enumerated property category |
| 6_8 | Sign set on a cell whose main property is non-metric |
| 6_9 | Enumerated category without a default item |
| 6_10 | Enumerated category with more than one default item |
| 6_11a–k | Code contains spaces — one rule per object type: framework, module, table, tablegroup, header, variable, item, property, subcategory, category, operation |
| 6_12 | Header code not numeric |
| 6_13 | Property of an enumerated category whose data type is not enumeration |
| 6_14 | Property of a non-enumerated category (except `_NA`) whose data type is enumeration |
| 6_15 | Property code numeric part (after 2-char prefix) not unique |
| 6_16 | Property without a data type |
| 6_18 | Property of an enumerated category without a subcategory lookup |
| 6_19 | Header code NULL or blank |
| 6_20 | Property code prefix does not match its data-type/flow-type or remainder not numeric (uses the DPM1 datatype remap, §3.4) |
| 6_21 | Property code is a plain numeric code |
| 6_22 | SubCategoryVersion created this release but unused by any HeaderVersion or VariableVersion |
| 6_23 | Items of a subcategory not in a category compatible with the subcategory's category |
| 6_24 | Properties of a non-enumerated category (except `_PR`, `_NA`) span multiple data types |
| 6_25 | Property name not essentially unique within its category |
| 6_26 | Item name not essentially unique within its category |
| 6_27 | Metric property with NULL period type |
| 6_28 | Sign set on a void or excluded cell |
| 6_29 | Duplicate subcategory code within a category |
| 6_30 | Duplicate category code |
| 6_31 | Item code does not start with a letter, or contains spaces |
| 6_32 | SubCategory name duplicated within the same category |
| 6_33 | SubCategoryVersion created this release with no SubCategoryItems |
| 6_34 | SubCategory contains exactly the same items as an existing active subcategory |
| 6_35 | Property name not essentially unique across all categories |
| 6_36 | SubCategoryVersion identical to the previous SubCategoryVersion |

*(“essentially unique”: the SQL compares names case-/whitespace-normalised;
replicate its exact normalisation.)*

### 4.5 Determinism

Violations are returned sorted by `(rule_id, primary object id)`. Two runs on
the same database must produce identical output (required by the parity
harness and by consumers diffing runs).

## 5. `VariableGenerationService`

### 5.1 Concept

In DPM, a **Variable** is the location-independent meaning of a data point,
identified by its **Aspect**:

```python
@dataclass(frozen=True)
class Aspect:
    key_id: int | None        # compound key of the table (open axes)
    property_id: int | None   # "main property" — the metric measured
    context_id: int | None    # dimensional coordinates (property→item pairs)

    @property
    def signature(self) -> str:   # "key_property_context", parity with SQL NewAspect
```

Variable generation answers, for every cell of every table version affected by
the release under generation: *which variable does this cell represent* —
reusing existing variables where the aspect is unchanged, proposing a new
`VariableVersion` where the aspect changed but the variable identity is
preserved, and proposing brand-new `Variable`s for genuinely new data points.
It also derives the supporting objects: key variables, compound (table) keys,
filing-indicator variables, and contexts.

**The service never writes.** Its output is a *plan* — a complete, ordered
description of what the SQL procedure would have persisted.

### 5.2 Public API

```python
class VariableGenerationService(BaseService):
    """Variable generation (port of variable_generation_tidy) — compute-only."""

    def generate(
        self,
        release_id: int | None = None,
        release_code: str | None = None,
        validate_first: bool = True,     # run ModelValidationService as a gate
    ) -> VariableGenerationResult: ...
```

### 5.3 Result types

```python
class GenerationStatus(str, Enum):
    COMPLETED = "completed"
    BLOCKED_BY_VALIDATION = "blocked_by_validation"   # model-rule errors
    BLOCKED_BY_CONSISTENCY = "blocked_by_consistency" # 5_x errors

class CellOutcome(str, Enum):
    UNCHANGED = "unchanged"            # SQL OutcomeID=OLD,  OutcomeVID=OLD
    NEW_VERSION = "new_version"        # SQL OutcomeID=OLD,  OutcomeVID=NEW
    REASSIGNED = "reassigned"          # SQL OutcomeID=OTHER OLD, OutcomeVID=OTHER NEW
    NEW_VARIABLE = "new_variable"      # SQL OutcomeID=NEW,  OutcomeVID=NEW
    NOT_REPORTABLE = "not_reportable"  # void/excluded → no variable

@dataclass(frozen=True)
class ProposedVariable:
    temp_id: str                # "var:1", "var:2", ... (plan-local, §5.5)
    type: str                   # "fact" | "key" | "filingindicator"
    aspect: Aspect | None       # None for key variables
    code: str | None
    versions: tuple[ProposedVariableVersion, ...]

@dataclass(frozen=True)
class ProposedVariableVersion:
    temp_id: str                        # "vv:1", ...
    variable_ref: int | str             # existing variable_id OR ProposedVariable.temp_id
    aspect: Aspect
    code: str | None
    name: str | None
    supersedes_vid: int | None          # existing VV whose end_release closes

@dataclass(frozen=True)
class ProposedContext:
    temp_id: str
    signature: str
    compositions: tuple[tuple[int, int], ...]   # (property_id, item_id)

@dataclass(frozen=True)
class ProposedCompoundKey:
    temp_id: str
    signature: str                                  # '#'-joined property ids
    member_variable_refs: tuple[int | str, ...]      # key-variable VVIDs or temp ids

@dataclass(frozen=True)
class ProposedFilingIndicator:
    temp_id: str
    code: str                        # derived from table code (§5.6 step 4)
    module_vids: tuple[int, ...]     # modules it parameterises
    # bundles its proposed Item/ItemCategory/Context if new

@dataclass(frozen=True)
class CellAssignment:
    table_vid: int
    table_code: str
    cell_id: int
    cell_code: str | None
    outcome: CellOutcome
    old_variable_id: int | None
    old_variable_vid: int | None
    new_variable_ref: int | str | None      # id or temp_id
    new_variable_vid_ref: int | str | None
    old_aspect: Aspect | None
    new_aspect: Aspect | None
    notes: tuple[str, ...]                  # e.g. "aspect shared across modules"

@dataclass(frozen=True)
class VariableGenerationResult:
    status: GenerationStatus
    release_id: int
    release_code: str | None
    validation: ModelValidationResult | None          # gate result (if run)
    consistency_violations: tuple[Violation, ...]     # 5_x (rule engine reused)
    # --- the plan (empty when blocked) ---
    new_variables: tuple[ProposedVariable, ...]
    new_variable_versions: tuple[ProposedVariableVersion, ...]
    new_contexts: tuple[ProposedContext, ...]
    new_compound_keys: tuple[ProposedCompoundKey, ...]
    new_filing_indicators: tuple[ProposedFilingIndicator, ...]
    cell_assignments: tuple[CellAssignment, ...]
    header_deduplications: tuple[HeaderDedup, ...]     # §5.6 step 2
    # --- reporting (parity with VarGeneration_Detail / _Summary) ---
    summary: tuple[GenerationSummaryRow, ...]  # grouped by (outcome, message): count, min/max cell code
    elapsed_ms: float

    def to_dict(self) -> dict: ...
```

`cell_assignments` is the parity equivalent of `VarGeneration_Detail`
(excluding, as the SQL does, void cells and unchanged assignments from the
detail report — but **`cell_assignments` includes everything**; the filtered
view is what `summary` aggregates. Rationale: a library consumer wants the
complete mapping; the SQL only trimmed it because it was a UI report).

### 5.4 Consistency checks (5_x)

Reuses the `Violation` type and rule registry from `model_validation` (family
"generation"). Evaluated on the in-memory cell-modelling state:

| rule_id | Severity | Description |
|---------|----------|-------------|
| 5_1 | error | Expired VariableVersion referenced by an active table version |
| 5_2 | error | Two cells shared a variable but now have different aspects without a key/datatype change |
| 5_3 | error | Two cells had different variables but now resolve to the same aspect |
| 5_4 | error | A void cell shares an aspect with a non-void cell |
| 5_5 | warning | Aspect reused across modules (informational, SQL emits as warning) |
| 5_6 | warning | Variable shared across modules after aspect change |

Any 5_x error → `status=BLOCKED_BY_CONSISTENCY`, plan fields empty,
`consistency_violations` populated. (Mirrors the SQL, which stops before the
assignment block.)

### 5.5 Identifier strategy

The SQL allocates real IDs (`MAX(id ≥ 1010000000) + ROW_NUMBER()`) and then
realigns sequences — pure persistence mechanics. The plan instead uses
**plan-local temp ids** (`"var:1"`, `"vv:3"`, `"ctx:2"`, …), deterministic for
a given input (assigned in the same deterministic order the plan is built).
Cross-references inside the plan use either a real DB id (`int`) or a temp id
(`str`); the discriminating union is explicit in the types. Whoever applies
the plan later (out of scope) maps temp ids to real ids.

**Parity comparisons therefore never compare ids** — they compare business
keys: aspect signatures, codes, (table_vid, cell_id) pairs (§9).

### 5.6 Algorithm (adapted from the SQL, in plan order)

Each SQL step that *mutated* the model either (a) becomes part of the returned
plan, or (b) is applied **virtually to the in-memory snapshot** so later
stages see its effect — never to the DB.

1. **Snapshot load.** All active module versions (`end_release IS NULL`) and
   their table versions, headers, cells, plus glossary/variable/key/context
   stores and `Aux_CellMapping` continuity rows.
2. **Header-version dedup (virtual).** Detect header versions created in the
   current release that are byte-identical to their immediate predecessor
   (code, label, context, property, subcategory). Record as
   `header_deduplications` in the result; apply virtually (later stages see
   the old HeaderVID, exactly as the SQL repoints and deletes).
   *Note:* the SQL's `ItemCategory.Signature` refresh disappears — signatures
   are **computed** in the snapshot (`acronym_category:code` /
   plain `code` for properties), never stored.
3. **Validation gate.** If `validate_first`, run `ModelValidationService`
   with the same snapshot (shared loader, no double I/O). Any error-severity
   violation → `status=BLOCKED_BY_VALIDATION`, return with the validation
   result attached.
4. **Supporting objects** (all proposals, all virtual):
   a. **Key variables** — key-header properties (`Header.is_key`) lacking a
      `Variable(type="key")` → `ProposedVariable`; header versions get their
      `key_variable` resolved (virtually).
   b. **Compound keys** — per current-release table version, the `#`-joined
      signature of its key-header property ids; unseen signatures →
      `ProposedCompoundKey`.
   c. **Filing indicators** — codes derived from table-version codes
      (resolving abstract tables exactly as the SQL does); missing ones →
      `ProposedFilingIndicator` bundling proposed Item ("Templates"
      category), Context (Template property → item), Variable
      (type="filingindicator", property `isReported`), and the module-version
      links (the SQL's `ModuleParameters` inserts).
5. **Cell modelling.** Build the working set: one record per (table version,
   cell) across active module versions, with *old* coordinates (from the
   predecessor version or via `Aux_CellMapping` continuity) and *new*
   coordinates:
   - `new_property_id`: max property id across the cell's column/row/sheet
     header versions and the table version (SQL semantics — preserve exactly);
   - `new_context_id`: per-cell context signature assembled from the header/
     table context compositions; unseen signatures → `ProposedContext`;
   - `new_key_id`: the table's compound key (existing or proposed);
   - `new_aspect = Aspect(key, property, context)`.
6. **Consistency checks** (§5.4). Stop if any error.
7. **Outcome decision** per cell (precedence exactly as the SQL's blocks):
   1. `old_aspect == new_aspect` → `UNCHANGED`.
   2. Same variable already has an active version with the new aspect →
      `UNCHANGED` (SQL 1b — reuse that version).
   3. Aspect changed, same key, same property data type → `NEW_VERSION`:
      `ProposedVariableVersion` on the old variable, `supersedes_vid` set
      (the SQL closed the predecessor's `EndReleaseID`; the plan records it).
   4. Another active fact VariableVersion elsewhere already carries the new
      aspect → `REASSIGNED` to the most recent such version.
   5. Otherwise → `NEW_VARIABLE`: one `ProposedVariable` **per distinct
      remaining aspect** (cells sharing an aspect share the proposal), with
      one `ProposedVariableVersion`.
   6. Void/excluded cells → `NOT_REPORTABLE` (assignment cleared).
8. **Reporting.** Assemble `summary` grouped by (outcome, message) with cell
   counts and min/max cell codes — parity with `VarGeneration_Summary`.

**Dropped SQL steps** (persistence-only, no Python counterpart): the initial
cleanup of a previous generation run (our run is stateless), `Aux_CellStatus`
writes (subsumed by `CellAssignment.outcome`), the `Cleaning_Service_01` call
(see §6), sequence realignment, and the buggy `RAISERROR` error path.

## 6. `OrphanAnalysisService` (optional, phase 3)

`Cleaning_Service_01` deletes orphaned objects. The read-only reinterpretation
reports what *would* be deleted:

```python
class OrphanAnalysisService(BaseService):
    def analyze(self, release_id: int | None = None) -> OrphanAnalysisResult: ...

@dataclass(frozen=True)
class OrphanAnalysisResult:
    release_id: int
    orphans: tuple[OrphanGroup, ...]     # one group per SQL step, in dependency order
    total_count: int

@dataclass(frozen=True)
class OrphanGroup:
    step: str            # e.g. "module_versions_without_composition"
    description: str
    objects: tuple[ObjectRef, ...]
    reopened_versions: tuple[ObjectRef, ...]   # predecessors whose EndRelease would reopen
```

The 17 active steps of the SQL (module versions → table versions → cells →
headers → variables → contexts → compound keys → items → aux tables →
duplicate concept relations) each become one detection function; the six
commented-out "publication stage" steps are **not** implemented. Because
deletes cascade in the SQL (step N's deletions can orphan step N+1's
candidates), detection must be evaluated against a **virtually-pruned
snapshot**, applying each step's removals in memory before evaluating the
next — otherwise the report undercounts.

This service is optional: it is not required by the two core requirements but
completes the workflow (the SQL calls it at the end of variable generation).
When implemented, `VariableGenerationResult` gains an optional
`orphan_analysis` field, populated only on request.

## 7. Explicitly out of scope

- **`check_modelling_rules_playground`** — historical subset of `tidy`
  pinned to release 9999; fully covered by `validate(release_id=9999)` with
  the complete rule set. No separate implementation, no compatibility mode
  for its *missing* rules.
- **`insert_GUIDs`, `SetColumnToNullable`** — RowGUID/Concept bookkeeping is
  a persistence/migration concern; dpmcore's loaders already own that
  lifecycle. If Concept-sync is ever needed it belongs in
  `dpmcore.loaders.migration`, not here.
- **`Delete/DropDPMRefitTables`, `Disable/Enable/DropForeignKeys`** — SQL
  Server administration with no domain logic; SQLAlchemy metadata operations
  already cover the equivalent needs.
- **Applying the generation plan** (persisting proposed variables). Deliberate
  future work; the plan types are designed so an `apply(plan)` writer can be
  added without changing this spec's services.

## 8. Integration

### 8.1 Service registry & connection accessor

Add to `ServiceRegistry` and `_ServiceAccessor` (`connection.py`):
`model_validation`, `variable_generation` (and later `orphan_analysis`).

### 8.2 REST (Layer 2 conventions)

- `POST /model/validation` → body `{release_code?, release_id?, rule_ids?}` →
  `ModelValidationResult.to_dict()` in `envelope()`.
- `GET /model/validation/rules` → rule catalogue (`list_rules`).
- `POST /model/variable-generation` → `VariableGenerationResult.to_dict()`
  in `envelope()`.

Long-run note: both endpoints are synchronous in phase 1; if wall-clock on
production-size databases demands it, an async job pattern is a later,
separate spec.

### 8.3 CLI

Following the existing `validate` command pattern (rich table or `--as-json`,
exit code):

- `dpmcore validate-model [--release CODE] [--rules 1_5,6_11a] [--as-json]`
  — exit 0 if `is_valid`, 1 otherwise; rich table grouped by family.
- `dpmcore generate-variables [--release CODE] [--as-json] [--summary-only]`
  — exit 0 on `COMPLETED`, 1 when blocked; prints the summary table,
  `--as-json` dumps the full plan.

## 9. Testing & parity strategy

### 9.1 Unit tests (per rule / per stage)

- Every validation rule gets at least one *violating* and one *clean* fixture,
  built programmatically on `memory_session` (in-memory SQLite,
  `Base.metadata.create_all`) — the snapshot loader works unchanged on it.
- Variable-generation stages (aspects, keys, filing indicators, outcome
  decision) are pure functions over snapshot rows → direct unit tests without
  a DB.

### 9.2 Parity harness (the equivalence guarantee)

One-time golden-file generation (documented script, run against SQL Server
with the bacpac restored):

1. Restore `DPM_REFIT_EBA_DEV_260715.bacpac`; run
   `check_modelling_rules_tidy`; export `ModelViolations` to CSV.
   Run `variable_generation_tidy`; export `VarGeneration_Detail`,
   `VarGeneration_Summary`, the created `Variable`/`VariableVersion` rows,
   and the final `TableVersionCell.VariableVID` map to CSV.
2. Migrate the same database to SQLite via the existing migration service →
   `tests/fixtures/parity_dpm.db` (kept out of the repo like `test_data.db`;
   tests auto-skip when absent, per existing convention).
3. Integration tests run the Python services against the SQLite fixture and
   compare against the golden CSVs:
   - **Validation parity:** multiset of `(legacy_code, primary-object
     business key)` must match. Message text is *not* compared (typos fixed);
     blocking flag must match severity mapping.
   - **Generation parity:** per (table_vid, cell_id): outcome class and
     resolved aspect signature must match; the set of new variables is
     compared by `(type, aspect signature, code)`, never by id (§5.5).
4. Known-acceptable diffs (e.g. SQL bugs faithfully *not* ported) must be
   listed in `tests/fixtures/parity_allowlist.yaml` with a justification —
   an empty allowlist is the goal.

### 9.3 Performance target

Full validation + generation on the EBA dev database (≈ the bacpac content)
in **< 60 s** on a laptop against SQLite. The snapshot design makes this
mostly a data-loading problem; if a table proves hot, tune the loader, not
the rules.

## 10. Implementation phases

| Phase | Deliverable | Contents |
|-------|-------------|----------|
| 1 | Shared infra + `ModelValidationService` families 1, 2 | snapshot, `ReleaseContext`, types, registry, rules 1_x + 2_x, unit tests, CLI `validate-model` |
| 2 | Remaining rule families | 3_x, 4_x, 6_x; validation parity harness green |
| 3 | `VariableGenerationService` | aspects, keys, filing indicators, 5_x checks, outcome engine, reports; generation parity green; CLI `generate-variables` |
| 4 | REST endpoints + docs | routers, envelope wiring, `docs/` guide pages |
| 5 (opt.) | `OrphanAnalysisService` | §6 |

Each phase is a separate PR; phase 2 may be split per family if review size
demands it.

## 11. Decisions taken (for reviewer sign-off)

1. **Playground is not ported** — subsumed by the release parameter (§7).
2. **Unique rule ids with letter suffixes** for SQL's reused codes;
   `legacy_code` preserved (§2.4).
3. **`isBlocking` → severity** (`error`/`warning`), aligning with the
   library-wide severity system (§2.5).
4. **SQL message typos corrected** in Python messages; parity compares codes
   and objects, not text (§4.4, §9.2).
5. **Generation is compute-only**; applying the plan is future work (§7).
   Plan uses deterministic temp ids (§5.5).
6. **`cell_assignments` is complete** (not filtered like
   `VarGeneration_Detail`); the summary reproduces the SQL report (§5.3).
7. **`Cleaning_Service_01` becomes an optional read-only orphan report**, not
   part of the generation flow (§6). If this is wrong — i.e. cleanup analysis
   must run inside generation — flag it in review.
8. **Six commented-out cleaning steps and the SQL `RAISERROR` bug are not
   ported.**

## 12. Implementation status & next steps

*Updated 2026-07-18 — initial implementation complete on branch
`feature/implement-variables-generation`.*

### 12.1 Delivered

| Phase | Status |
|-------|--------|
| 1–2 `ModelValidationService`, all 5 rule families | ✅ 119 rules, audited 1:1 against the SQL blocks (codes, occurrence order, `isBlocking` severities) |
| 3 `VariableGenerationService` | ✅ full plan computation incl. 5_x checks, validation gate, temp ids |
| 4 REST + CLI + docs | ✅ `POST /api/v1/model/validation`, `GET …/rules`, `POST …/variable-generation`; `dpmcore validate-model`, `dpmcore generate-variables`; `docs/guide/modelling.rst` |
| 5 `OrphanAnalysisService` (§6, optional) | ⬜ not started |

Quality gates at time of writing: 2 706 tests green, 100 % branch
coverage on both new packages, ruff + mypy strict clean.

### 12.2 Next steps

1. **Run the parity harness (§9.2) — the empirical equivalence
   proof.** Requires a SQL Server instance:

   1. Restore `input/DPM_REFIT_EBA_DEV_260715.bacpac`.
   2. Follow `scripts/parity/README.md`: run
      `scripts/parity/export_goldens.sql` to produce the golden CSVs
      (validation goldens BEFORE running `variable_generation_tidy`;
      snapshot/migrate the DB to
      `tests/fixtures/parity_dpm.db` at the pre-generation state).
   3. Drop the goldens under `tests/fixtures/parity/` and run
      `pytest tests/integration/validation/test_model_validation_parity.py -v`.
   4. Triage divergences: rule-by-rule, the SQL block is the
      authority; genuine SQL bugs go to
      `tests/fixtures/parity/allowlist.yaml` with a justification.
   5. Extend the harness with the generation goldens
      (`VarGeneration_Detail`/`Summary`, generated variables, cell
      map) — compare by aspect signature and outcome class, never by
      id (§5.5).

2. **Decide on the draft-release normalisation.** The port funnels
   the SQL's two patterns (`= @CurrentRelease` and
   `= @CurrentRelease OR = 9999`) through
   `ReleaseContext.is_current`, which treats an existing draft
   release (9999) as current in BOTH cases. On databases containing
   draft rows this makes Python findings a superset of a strict
   tidy run. If exact-strict behaviour is needed, split
   `ReleaseContext.is_current` into strict/draft-inclusive variants
   and re-audit which rules use which (the SQL reference under
   `specification/reference/stored-procedures/` is the authority).

3. **Performance validation on a production-size database** (§9.3
   target: < 60 s validation + generation). The snapshot loader is
   the only I/O; tune there if needed.

4. **Phase 5 (optional): `OrphanAnalysisService`** per §6 —
   read-only reinterpretation of `Cleaning_Service_01` with a
   virtually-pruned snapshot for cascade fidelity.

5. **Future: `apply(plan)` writer** (§7) — persisting a
   `VariableGenerationResult` (temp-id → real-id mapping, sequence
   handling) as a separate, explicitly-mutating service outside the
   read-only services contract.
