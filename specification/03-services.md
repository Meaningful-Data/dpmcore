# dpmcore Specification — Layer 3: Services

## 1. Overview

The services layer contains all business logic. Services operate on top of the
ORM layer and are consumed by both the REST API layer and direct Python callers.

**Key principle:** Services are plain Python classes. They receive a database
session as a constructor parameter and expose methods that return typed results.
They have no knowledge of HTTP, serialization formats, or web frameworks.

## 2. Service Architecture

```python
from dpmcore.orm import SessionFactory
from dpmcore.services import DpmXlService, DataDictionaryService

# All services follow this pattern:
factory = SessionFactory(engine)

with factory() as session:
    dpm_xl = DpmXlService(session)
    result = dpm_xl.validate_syntax("v1234 = v5678 + v9012")
```

### 2.1 Base Service

```python
class BaseService:
    """Base class for all dpmcore services."""

    def __init__(self, session: Session) -> None:
        self._session = session
```

All services inherit from `BaseService` and receive an explicit session.

### 2.2 Service Registry

For convenience, a `ServiceRegistry` groups all services with a shared session:

```python
class ServiceRegistry:
    def __init__(self, session: Session) -> None:
        self.dpm_xl = DpmXlService(session)
        self.data_dictionary = DataDictionaryService(session)
        self.explorer = ExplorerService(session)
        self.hierarchy = HierarchyService(session)
        self.instance = InstanceService(session)
        self.migration = MigrationService(session)
```

## 3. DPM-XL Services

The DPM-XL services handle validation, parsing, and code generation for the
DPM-XL expression language.

### 3.1 Syntax Validation Service

Validates DPM-XL expressions against the grammar. **No database required.**

```python
class SyntaxService:
    """Syntax validation for DPM-XL expressions (no DB required)."""

    def validate(self, expression: str) -> SyntaxValidationResult:
        """Validate expression syntax.

        Returns SyntaxValidationResult with is_valid, error info.
        """
        ...

    def parse(self, expression: str) -> dict:
        """Parse expression and return raw AST as dict."""
        ...

    def is_valid(self, expression: str) -> bool:
        """Quick check — returns True if syntax is valid."""
        ...
```

**Result type:**

```python
@dataclass
class SyntaxValidationResult:
    is_valid: bool
    expression: str
    validation_type: str = "syntax"
    error_message: str | None = None
    error_code: str | None = None
```

### 3.2 Semantic Validation Service

Validates operand references, types, and structure against the database.

```python
class SemanticService(BaseService):
    """Semantic validation for DPM-XL expressions (requires DB)."""

    def validate(
        self,
        expression: str,
        release_id: int | None = None,
        release_code: str | None = None,
    ) -> SemanticValidationResult:
        """Full semantic validation."""
        ...

    def analyze(
        self,
        expression: str,
        release_id: int | None = None,
        release_code: str | None = None,
    ) -> dict:
        """Detailed analysis with operand resolution and type info."""
        ...
```

**Result type:**

```python
@dataclass
class SemanticValidationResult:
    is_valid: bool
    expression: str
    validation_type: str = "semantic"
    error_message: str | None = None
    error_code: str | None = None
    warning: str | None = None
    results: Any = None
```

**Warning collection:** Semantic validation uses a warning collector to
capture non-fatal issues separately from errors:

```python
@dataclass
class WarningCollector:
    warnings: list[str]

    @contextmanager
    def collect(self) -> Iterator[WarningCollector]:
        """Context manager for collecting warnings during validation."""
        ...

    def add_warning(self, message: str) -> None:
        """Add a semantic warning."""
        ...
```

### 3.3 AST Generator Service

Generates Abstract Syntax Trees at three levels of enrichment.

```python
class ASTGeneratorService(BaseService):
    """AST generation for DPM-XL expressions."""

    def generate_basic_ast(self, expression: str) -> dict:
        """Level 1: Syntax-only AST. No DB required."""
        ...

    def generate_complete_ast(
        self,
        expression: str,
        release_id: int | None = None,
        release_code: str | None = None,
    ) -> dict:
        """Level 2: Semantically validated AST with metadata."""
        ...

    def generate_validations_script(
        self,
        expressions: list[str | tuple[str, str, str, str]],
        release_id: int | None = None,
        release_code: str | None = None,
        severity: str = "error",
    ) -> list[dict]:
        """Level 3: Engine-ready AST with scope and severity info.

        Expressions can be:
        - Simple strings: "v1234 = v5678"
        - 4-tuples: ("v1234 = v5678", "op_code", "op_vid", "warning")

        Severity values: "error", "warning", "info" (case-insensitive).
        """
        ...
```

### 3.4 Scope Calculator Service

Calculates which modules and tables an operation applies to.

```python
class ScopeCalculatorService(BaseService):
    """Operation scope calculation."""

    def calculate_from_expression(
        self,
        expression: str,
        operation_version_id: int,
        release_id: int | None = None,
        release_code: str | None = None,
    ) -> ScopeResult:
        """Calculate scopes from a DPM-XL expression."""
        ...

    def calculate(
        self,
        operation_version_id: int,
        table_vids: list[int],
        precondition_items: list | None = None,
    ) -> ScopeResult:
        """Calculate scopes from explicit table VIDs."""
        ...

    def get_scopes_with_metadata(
        self,
        operation_version_id: int,
    ) -> list[ScopeMetadata]:
        """Get scopes with full metadata for an operation."""
        ...

    def get_tables_with_metadata(
        self,
        operation_version_id: int,
    ) -> list[TableMetadata]:
        """Get tables with metadata for an operation."""
        ...

    def get_headers_with_metadata(
        self,
        operation_version_id: int,
        table_vid: int,
    ) -> list[HeaderMetadata]:
        """Get headers with metadata for a specific table in an operation."""
        ...
```

**Result types:**

```python
@dataclass
class ScopeResult:
    scopes: list[ScopeMetadata]
    tables: list[TableMetadata]
    metadata: dict

@dataclass
class ScopeMetadata:
    scope_id: int
    module_version: ModuleVersionInfo
    tables: list[TableMetadataInfo]
    severity: str

@dataclass
class TableMetadata:
    table_vid: int
    code: str
    name: str
    module_code: str
```

### 3.5 Unified DPM-XL Service

A facade that combines all DPM-XL sub-services:

```python
class DpmXlService(BaseService):
    """Unified facade for all DPM-XL operations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.syntax = SyntaxService()           # No session needed
        self.semantic = SemanticService(session)
        self.ast = ASTGeneratorService(session)
        self.scopes = ScopeCalculatorService(session)

    def validate_syntax(self, expression: str) -> SyntaxValidationResult:
        return self.syntax.validate(expression)

    def validate_semantic(
        self, expression: str, **kwargs
    ) -> SemanticValidationResult:
        return self.semantic.validate(expression, **kwargs)

    def generate_ast(
        self, expression: str, level: int = 1, **kwargs
    ) -> dict:
        if level == 1:
            return self.ast.generate_basic_ast(expression)
        elif level == 2:
            return self.ast.generate_complete_ast(expression, **kwargs)
        elif level == 3:
            return self.ast.generate_validations_script(
                [expression], **kwargs
            )
        raise ValueError(f"Invalid AST level: {level}")

    def generate_script(
        self, expressions: list, **kwargs
    ) -> list[dict]:
        return self.ast.generate_validations_script(expressions, **kwargs)

    def calculate_scopes(self, **kwargs) -> ScopeResult:
        return self.scopes.calculate_from_expression(**kwargs)
```

## 4. Data Dictionary Service

Provides structured queries for DPM data dictionary objects.

```python
class DataDictionaryService(BaseService):
    """Data dictionary queries."""

    def get_all_tables(
        self,
        release_id: int | None = None,
        release_code: str | None = None,
        module_code: str | None = None,
    ) -> list[TableInfo]:
        """Get all tables, optionally filtered by release and module."""
        ...

    def get_table_by_code(
        self,
        code: str,
        release_id: int | None = None,
        release_code: str | None = None,
    ) -> TableInfo | None:
        """Get a specific table by its code."""
        ...

    def get_tables_for_module(
        self,
        module_code: str,
        release_id: int | None = None,
        release_code: str | None = None,
    ) -> list[TableInfo]:
        """Get all tables belonging to a module."""
        ...

    def get_table_details(
        self,
        table_vid: int,
    ) -> TableDetails:
        """Get full table structure: headers, cells, variables."""
        ...

    def get_all_modules(
        self,
        release_id: int | None = None,
        release_code: str | None = None,
    ) -> list[ModuleInfo]:
        """Get all modules."""
        ...

    def get_all_frameworks(self) -> list[FrameworkInfo]:
        """Get all frameworks."""
        ...

    def get_all_releases(self) -> list[ReleaseInfo]:
        """Get all releases."""
        ...

    def get_variables_for_table(
        self,
        table_code: str,
        release_id: int | None = None,
    ) -> list[VariableInfo]:
        """Get all variables used in a table."""
        ...

    def get_operations_for_module(
        self,
        module_code: str,
        release_id: int | None = None,
    ) -> list[OperationInfo]:
        """Get all operations scoped to a module."""
        ...
```

**Result types:**

```python
@dataclass
class TableInfo:
    code: str
    name: str
    table_id: int
    table_vid: int
    module_code: str | None
    release_code: str | None

@dataclass
class TableDetails:
    info: TableInfo
    columns: list[HeaderInfo]
    rows: list[HeaderInfo]
    sheets: list[HeaderInfo]
    cells: list[CellInfo]
    variables: list[VariableInfo]

@dataclass
class ModuleInfo:
    code: str
    name: str
    module_id: int
    module_vid: int
    framework_code: str
    table_count: int

@dataclass
class FrameworkInfo:
    code: str
    name: str
    description: str | None
    module_count: int

@dataclass
class ReleaseInfo:
    code: str
    date: date
    description: str | None
    is_current: bool
```

## 5. Explorer Service

Inverse/introspection queries — "where is X used?"

```python
class ExplorerService(BaseService):
    """Inverse lookups and introspection queries."""

    def get_properties_using_item(
        self,
        item_code: str,
        release_id: int | None = None,
    ) -> list[PropertyUsageInfo]:
        """Find all properties that use a given item."""
        ...

    def get_tables_using_variable(
        self,
        variable_code: str,
        release_id: int | None = None,
    ) -> list[TableInfo]:
        """Find all tables that use a given variable."""
        ...

    def get_variable_from_cell_address(
        self,
        table_code: str,
        column_code: str,
        row_code: str,
        sheet_code: str | None = None,
        release_id: int | None = None,
    ) -> VariableInfo | None:
        """Resolve a cell address to its variable."""
        ...

    def get_module_url(
        self,
        module_code: str,
    ) -> str | None:
        """Get documentation URL for a module."""
        ...

    def get_operations_using_variable(
        self,
        variable_code: str,
        release_id: int | None = None,
    ) -> list[OperationInfo]:
        """Find all operations that reference a variable."""
        ...
```

## 6. Hierarchy Service

Navigate hierarchical relationships within categories.

```python
class HierarchyService(BaseService):
    """Hierarchical relationship navigation."""

    def get_hierarchy(
        self,
        domain_code: str,
        release_id: int | None = None,
    ) -> HierarchyNode:
        """Get the full hierarchy tree for a domain."""
        ...

    def get_children(
        self,
        item_code: str,
        release_id: int | None = None,
    ) -> list[HierarchyNode]:
        """Get direct children of an item."""
        ...

    def get_ancestors(
        self,
        item_code: str,
        release_id: int | None = None,
    ) -> list[HierarchyNode]:
        """Get all ancestors of an item (path to root)."""
        ...

    def get_descendants(
        self,
        item_code: str,
        release_id: int | None = None,
        max_depth: int | None = None,
    ) -> list[HierarchyNode]:
        """Get all descendants of an item."""
        ...
```

**Result type:**

```python
@dataclass
class HierarchyNode:
    code: str
    name: str
    item_id: int
    level: int
    parent_code: str | None
    children: list[HierarchyNode]
```

## 7. Instance Service

XBRL-CSV instance package generation.

```python
class InstanceService(BaseService):
    """XBRL-CSV instance generation."""

    def build_package_from_dict(
        self,
        data: dict,
        output_path: str | Path,
    ) -> Path:
        """Build an XBRL-CSV package from a dictionary."""
        ...

    def build_package_from_json(
        self,
        json_file: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Build an XBRL-CSV package from a JSON file."""
        ...

    def build_package_from_dataframe(
        self,
        df: pd.DataFrame,
        metadata: dict,
        output_path: str | Path,
    ) -> Path:
        """Build an XBRL-CSV package from a Pandas DataFrame."""
        ...
```

## 8. Migration Service

Database import/export and migration.

```python
class MigrationService(BaseService):
    """Database migration and import/export."""

    def migrate_from_access(
        self,
        access_db_path: str | Path,
    ) -> MigrationResult:
        """Migrate from an Access database to the current DB."""
        ...

    def export_to_sqlite(
        self,
        output_path: str | Path,
    ) -> Path:
        """Export the current database to SQLite."""
        ...

    def import_from_sqlite(
        self,
        sqlite_path: str | Path,
    ) -> MigrationResult:
        """Import data from a SQLite database."""
        ...
```

## 9. DPM-XL Engine Internals

The DPM-XL engine is the internal implementation that the services delegate to.
It is not part of the public API but is documented here for completeness.

### 9.1 Grammar & Parser

- **ANTLR4 grammar**: `dpm_xl.g4` defines the DPM-XL language syntax
- **Generated parser**: Auto-generated lexer, parser, and listener from the grammar
- **ANTLR version**: 4.9.2 (specific version required)

### 9.2 AST Nodes

```
ExpressionNode (abstract)
├── BinaryExpression (operator, left, right)
├── UnaryExpression (operator, operand)
├── FunctionCall (functionName, arguments[])
├── VariableReference (variable → Variable)
├── Literal (value, dataType)
├── ConditionalExpression (condition, thenBranch, elseBranch)
└── AggregationExpression (function, expression, groupBy)
```

### 9.3 Type System

| Category | Types |
|----------|-------|
| Numeric | Integer, Decimal, Monetary, Percentage, Pure |
| String | String |
| Temporal | Date, DateTime |
| Logical | Boolean |
| Special | Mixed, Null |

Type promotion rules are defined in `types/promotion.py` and handle implicit
conversions (e.g., Integer + Decimal → Decimal).

### 9.4 Operators

| Category | Operators |
|----------|-----------|
| Arithmetic | `+`, `-`, `*`, `/` |
| Comparison | `=`, `!=`, `<`, `>`, `<=`, `>=` |
| Boolean | `AND`, `OR`, `NOT` |
| Conditional | `IF-THEN-ELSE` |
| Aggregate | `SUM`, `AVG`, `MIN`, `MAX`, `COUNT` |
| Clause | `WHERE`, `FILTER`, `RENAME`, `SUB` |
| String | String manipulation operators |
| Time | `TIMESHIFT` and temporal operators |

### 9.5 Symbols

```
Operand (abstract)
├── Scalar (single value)
└── RecordSet (multi-dimensional)

Component (abstract)
├── KeyComponent (dimension: DPM | STANDARD)
├── FactComponent (data value)
└── AttributeComponent (auxiliary)

Structure (component set with unique keys + single fact)
```

### 9.6 Semantic Analyzer

The `InputAnalyzer` walks the AST and:

1. Resolves variable references against the database
2. Validates types and applies promotion rules
3. Checks operand compatibility
4. Resolves cell references to variables
5. Collects warnings for non-fatal issues

### 9.7 Severity System

Three severity levels for validation operations:

| Level | Constant | Description |
|-------|----------|-------------|
| Error | `SEVERITY_ERROR` = `"error"` | Blocking validation failure |
| Warning | `SEVERITY_WARNING` = `"warning"` | Non-blocking issue |
| Info | `SEVERITY_INFO` = `"info"` | Informational message |

Severity can be set:
- **Globally**: Default for all operations in a script
- **Per-operation**: Via 4-tuple expression entries
- All severity values are case-insensitive

## 10. Extension Points

Services are designed for extensibility:

### 10.1 Subclassing

```python
from dpmcore.services import DataDictionaryService

class CustomDataDictionaryService(DataDictionaryService):
    """Extended data dictionary with custom queries."""

    def get_tables_with_custom_metadata(self, ...) -> list:
        # Custom query using self._session
        ...
```

### 10.2 Service Registry Extension

```python
from dpmcore.services import ServiceRegistry

class CustomServiceRegistry(ServiceRegistry):
    def __init__(self, session):
        super().__init__(session)
        self.custom = CustomService(session)
```

### 10.3 Django Integration

In Django mode, services are available as:

```python
# In a Django view
from dpmcore.services import ServiceRegistry
from dpmcore.django.utils import get_session

def my_view(request):
    with get_session() as session:
        services = ServiceRegistry(session)
        tables = services.data_dictionary.get_all_tables()
        return JsonResponse({"tables": [t.to_dict() for t in tables]})
```

## 11. Error Handling

### 11.1 Exception Hierarchy

```
DpmCoreError (base)
├── SyntaxValidationError
│   └── (ANTLR parse errors)
├── SemanticValidationError
│   ├── UnknownVariableError
│   ├── TypeMismatchError
│   └── InvalidOperandError
├── ScopeCalculationError
├── DatabaseError
│   ├── ConnectionError
│   └── QueryError
├── ConfigurationError
└── MigrationError
```

### 11.2 Error Messages

Error messages are defined in a central messages module for consistency and
potential internationalisation:

```python
# exceptions/messages.py
UNKNOWN_VARIABLE = "Variable '{code}' not found in release '{release}'"
TYPE_MISMATCH = "Cannot apply {operator} to {left_type} and {right_type}"
INVALID_RELEASE = "Release '{code}' does not exist"
```

## 12. Migration from Current Codebase

| Current (py_dpm) | Target (dpmcore) | Changes |
|-------------------|-------------------|---------|
| API classes (`SyntaxAPI`, etc.) | Service classes | Rename, remove HTTP awareness |
| Global session in constructors | Explicit session parameter | Dependency injection |
| `database_path` / `connection_url` in API constructors | Session from `SessionFactory` | Separate connection from logic |
| Mixed pandas/SQLAlchemy in queries | SQLAlchemy-first, pandas optional | Reduce pandas coupling |
| Dataclasses scattered in API files | Centralised result types | Single `types.py` or per-service |
| `WarningCollector` as module global | `WarningCollector` as instance | Thread safety |
