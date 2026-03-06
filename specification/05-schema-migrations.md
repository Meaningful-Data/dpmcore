# dpmcore Specification — Schema Management & Migrations

## 1. Overview

dpmcore uses a **hybrid schema management** approach:

- It **can create and migrate** its own schema for new deployments.
- It **can connect** to pre-existing databases (legacy Access imports, DBA-managed schemas).
- Consumers **can extend** dpmcore tables with additional columns, and add entirely new tables.

This document specifies how schema ownership, migrations, and model
extensibility work across all three usage modes.

## 2. Design Principles

| Principle | Description |
|-----------|-------------|
| **dpmcore owns its core schema** | dpmcore defines the canonical schema and ships migrations for it |
| **Consumers can extend, not fork** | Custom columns and tables are added through extension mechanisms, not by modifying dpmcore source |
| **Migrations are composable** | dpmcore's migrations and consumer migrations coexist and run in sequence |
| **Legacy DBs are supported** | dpmcore can validate an existing schema and work against it without applying migrations |
| **ORM and DB are always in sync** | A schema validation check detects drift between ORM models and the actual DB |

## 3. Schema Modes

```
┌─────────────────────────────────────────────────────────────────┐
│                     Schema Modes                                 │
│                                                                   │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ Mode A:         │  │ Mode B:          │  │ Mode C:        │  │
│  │ Full Managed    │  │ Read-Only Schema │  │ Extended       │  │
│  │                 │  │                  │  │                │  │
│  │ dpmcore creates │  │ DB pre-exists,   │  │ dpmcore schema │  │
│  │ & migrates the  │  │ dpmcore maps     │  │ + consumer     │  │
│  │ schema          │  │ to it as-is      │  │ extensions     │  │
│  └─────────────────┘  └──────────────────┘  └────────────────┘  │
│                                                                   │
│  New deployments      Legacy databases      Django apps,         │
│  CI/CD pipelines      Access imports        custom platforms     │
└─────────────────────────────────────────────────────────────────┘
```

### Mode A — Full Managed

dpmcore creates all tables and manages all migrations. Used for:

- Fresh deployments
- CI/CD test databases
- Docker-based setups

### Mode B — Read-Only Schema

The database already exists (e.g., imported from Access). dpmcore connects
to it and validates that the schema matches expectations. No migrations are
applied. Used for:

- Legacy database connections
- Read-only analysis environments
- Databases managed by external tools

### Mode C — Extended

dpmcore manages its core tables. The consumer adds custom columns to
dpmcore tables and/or creates entirely new tables. Both dpmcore and consumer
migrations coexist. Used for:

- Django management applications
- Custom platforms built on dpmcore

## 4. Migration Tools

| Usage Mode | Migration Tool | Reason |
|------------|----------------|--------|
| Standalone (Mode 1) | **Alembic** | Native SQLAlchemy migration tool |
| Web App (Mode 2) | **Alembic** | Same as standalone |
| Django (Mode 3) | **Django Migrations** | Native Django migration framework |

### 4.1 Alembic (Standalone & Web App)

dpmcore ships an Alembic migration environment with its package:

```
src/dpmcore/
├── migrations/                      # Alembic migrations
│   ├── alembic.ini                 # Alembic configuration
│   ├── env.py                      # Migration environment
│   ├── script.py.mako              # Template for new migrations
│   └── versions/                   # Migration scripts
│       ├── 001_initial_schema.py
│       ├── 002_add_severity.py
│       └── ...
```

**CLI commands:**

```bash
# Apply all pending migrations
dpmcore db upgrade

# Downgrade one revision
dpmcore db downgrade -1

# Show current revision
dpmcore db current

# Generate a new migration from model changes
dpmcore db revision --autogenerate -m "description"

# Validate schema matches ORM (no migration needed)
dpmcore db check
```

**Programmatic usage:**

```python
from dpmcore.migrations import upgrade, check_schema, get_current_revision

# Apply migrations
upgrade(engine, revision="head")

# Validate schema
is_valid, differences = check_schema(engine)
if not is_valid:
    print(f"Schema drift detected: {differences}")
```

#### Consumer Extensions with Alembic

Consumers who extend dpmcore in standalone mode use **Alembic branches**:

```python
# consumer's alembic/env.py
from dpmcore.orm import Base as DpmBase
from myapp.models import Base as MyBase

# Include both model bases for autogenerate
target_metadata = [DpmBase.metadata, MyBase.metadata]
```

Or consumers can chain migration directories:

```ini
# consumer's alembic.ini
[alembic]
script_location = myapp/migrations
# Also include dpmcore's migrations
version_locations = %(here)s/migrations dpmcore:migrations/versions
```

### 4.2 Django Migrations (Django Mode)

In Django mode, dpmcore provides a Django app with models that Django's
migration framework manages.

**Key decision: `managed = True`** — dpmcore's Django models ARE managed by
Django migrations. This allows:

- `python manage.py migrate dpmcore_core` to create/update dpmcore tables
- Consumers to add columns via model inheritance
- Django's migration framework to handle the full schema lifecycle

```python
# dpmcore/django/models.py
class Table(models.Model):
    table_id = models.AutoField(primary_key=True, db_column="TableID")
    is_abstract = models.BooleanField(db_column="IsAbstract")
    # ...

    class Meta:
        managed = True           # Django manages this table
        db_table = "Table"       # Explicit table name
        app_label = "dpmcore_core"
```

**Migration commands:**

```bash
# Create dpmcore tables
python manage.py migrate dpmcore_core

# Check for pending migrations
python manage.py showmigrations dpmcore_core

# Create migrations after model changes
python manage.py makemigrations dpmcore_core
```

## 5. Model Extensibility

Consumers need to add custom columns to dpmcore tables and create new tables.
This section specifies how.

### 5.1 Extension Strategies

```
┌─────────────────────────────────────────────────────────────┐
│                  Extension Strategies                         │
│                                                               │
│  Strategy 1: Extension Tables (1:1 FK)                       │
│  ─────────────────────────────────────                       │
│  Safest. New table with OneToOne to dpmcore table.           │
│  No modifications to dpmcore models.                         │
│                                                               │
│  Strategy 2: Swappable Models                                │
│  ────────────────────────────                                │
│  Like Django's AUTH_USER_MODEL. Consumer provides a          │
│  replacement model that extends the base.                    │
│                                                               │
│  Strategy 3: Abstract Base + Concrete Model                  │
│  ──────────────────────────────────────────                  │
│  dpmcore ships abstract bases. Consumer creates concrete     │
│  models adding their own fields. Configuration tells         │
│  dpmcore which concrete class to use.                        │
│                                                               │
│  Strategy 4: Entirely New Tables                             │
│  ──────────────────────────────                              │
│  Consumer creates new models with ForeignKeys to dpmcore     │
│  models. Standard Django/SQLAlchemy practice.                │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Strategy 1 — Extension Tables (Always Available)

The simplest and safest approach. Works in all modes.

**SQLAlchemy (standalone):**

```python
from dpmcore.orm import Base, Table

class TableExtension(Base):
    __tablename__ = "custom_table_extension"

    id = mapped_column(Integer, primary_key=True)
    table_id = mapped_column(
        Integer,
        ForeignKey("Table.TableID"),
        unique=True,
    )
    notes = mapped_column(Text, nullable=True)
    status = mapped_column(String(20), default="draft")
    created_at = mapped_column(DateTime, default=func.now())

    # Relationship back to dpmcore model
    table = relationship("Table", backref="extension")
```

**Django:**

```python
from django.db import models
from dpmcore.django.models import Table

class TableExtension(models.Model):
    table = models.OneToOneField(
        Table,
        on_delete=models.CASCADE,
        related_name="extension",
    )
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, default="draft")
    created_at = models.DateTimeField(auto_now_add=True)
```

**Pros:** No dpmcore schema changes, clean migration, easy to understand.
**Cons:** Extra JOIN for every query that needs custom fields.

### 5.3 Strategy 2 — Swappable Models (Recommended for Column Extension)

For key entities that consumers commonly need to extend, dpmcore supports
a **swappable model** pattern inspired by Django's `AUTH_USER_MODEL`.

#### How It Works

1. dpmcore defines an **abstract base model** with all core fields.
2. dpmcore also ships a **default concrete model** that inherits from the base.
3. Consumers can provide their own concrete model that inherits from the same
   base and adds custom fields.
4. A configuration setting tells dpmcore which concrete model to use.

#### SQLAlchemy Implementation

```python
# dpmcore/orm/glossary.py

class AbstractTable(Base):
    """Abstract base — defines all dpmcore columns."""
    __abstract__ = True

    table_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, name="TableID"
    )
    is_abstract: Mapped[bool] = mapped_column(
        Boolean, name="IsAbstract"
    )
    has_open_columns: Mapped[bool] = mapped_column(
        Boolean, name="HasOpenColumns"
    )
    has_open_rows: Mapped[bool] = mapped_column(
        Boolean, name="HasOpenRows"
    )
    has_open_sheets: Mapped[bool] = mapped_column(
        Boolean, name="HasOpenSheets"
    )
    # ... all core columns


# Default concrete model (used when no custom model is configured)
class Table(AbstractTable):
    __tablename__ = "Table"
```

```python
# consumer/models.py

from dpmcore.orm.rendering import AbstractTable

class Table(AbstractTable):
    """Extended Table with custom columns."""
    __tablename__ = "Table"

    # Custom columns added to the same table
    workflow_status: Mapped[str | None] = mapped_column(
        String(20), name="WorkflowStatus", nullable=True
    )
    internal_notes: Mapped[str | None] = mapped_column(
        Text, name="InternalNotes", nullable=True
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime, name="LastReviewedAt", nullable=True
    )
```

```python
# consumer/config.py or settings.py

DPMCORE_MODELS = {
    "Table": "consumer.models.Table",       # Use custom Table
    # All other models use dpmcore defaults
}
```

#### Django Implementation

```python
# dpmcore/django/models/rendering.py

class AbstractTable(models.Model):
    """Abstract base — defines all dpmcore columns."""
    table_id = models.AutoField(primary_key=True, db_column="TableID")
    is_abstract = models.BooleanField(db_column="IsAbstract")
    has_open_columns = models.BooleanField(db_column="HasOpenColumns")
    # ... all core columns

    class Meta:
        abstract = True


class Table(AbstractTable):
    """Default concrete Table model."""

    class Meta:
        db_table = "Table"
        app_label = "dpmcore_core"
        swappable = "DPMCORE_TABLE_MODEL"  # Swappable!
```

```python
# consumer's Django settings.py

DPMCORE_TABLE_MODEL = "myapp.CustomTable"
```

```python
# myapp/models.py

from dpmcore.django.models.rendering import AbstractTable

class CustomTable(AbstractTable):
    """Extended Table with custom fields."""
    workflow_status = models.CharField(
        max_length=20, db_column="WorkflowStatus",
        null=True, blank=True,
    )
    internal_notes = models.TextField(
        db_column="InternalNotes", blank=True,
    )
    last_reviewed_at = models.DateTimeField(
        db_column="LastReviewedAt", null=True, blank=True,
    )

    class Meta:
        db_table = "Table"        # Same physical table
        app_label = "myapp"
```

#### Swappable Entities

Not every model needs to be swappable. Only key entities that consumers
commonly extend:

| Entity | Swappable Setting | Rationale |
|--------|-------------------|-----------|
| `Table` | `DPMCORE_TABLE_MODEL` | Most commonly extended for workflow metadata |
| `TableVersion` | `DPMCORE_TABLEVERSION_MODEL` | Version-level custom metadata |
| `Module` | `DPMCORE_MODULE_MODEL` | Module-level workflow fields |
| `ModuleVersion` | `DPMCORE_MODULEVERSION_MODEL` | Version-level custom fields |
| `Operation` | `DPMCORE_OPERATION_MODEL` | Custom operation metadata |
| `OperationVersion` | `DPMCORE_OPERATIONVERSION_MODEL` | Custom validation fields |
| `Variable` | `DPMCORE_VARIABLE_MODEL` | Custom variable metadata |
| `Release` | `DPMCORE_RELEASE_MODEL` | Custom release tracking fields |
| `Framework` | `DPMCORE_FRAMEWORK_MODEL` | Custom framework metadata |

All other entities use their default concrete models and can be extended
via extension tables (Strategy 1) if needed.

### 5.4 Strategy 3 — Model Registry (Internal Mechanism)

Internally, dpmcore uses a **model registry** that resolves which concrete
class to use for each entity. This powers the swappable model mechanism.

```python
# dpmcore/orm/registry.py

from importlib import import_module

class ModelRegistry:
    """Resolves concrete model classes, supporting swappable models."""

    _defaults: dict[str, type] = {}
    _overrides: dict[str, str] = {}  # entity_name → dotted.path.ClassName
    _resolved: dict[str, type] = {}

    @classmethod
    def register_default(cls, name: str, model_class: type) -> None:
        """Register a default model class (called by dpmcore at import)."""
        cls._defaults[name] = model_class

    @classmethod
    def configure(cls, overrides: dict[str, str]) -> None:
        """Configure model overrides from settings.

        Args:
            overrides: Mapping of entity name to dotted class path.
                       e.g., {"Table": "myapp.models.CustomTable"}
        """
        cls._overrides = overrides
        cls._resolved.clear()

    @classmethod
    def get_model(cls, name: str) -> type:
        """Get the concrete model class for an entity name."""
        if name not in cls._resolved:
            if name in cls._overrides:
                module_path, class_name = cls._overrides[name].rsplit(".", 1)
                module = import_module(module_path)
                cls._resolved[name] = getattr(module, class_name)
            elif name in cls._defaults:
                cls._resolved[name] = cls._defaults[name]
            else:
                raise ValueError(f"Unknown model: {name}")
        return cls._resolved[name]
```

**Usage in services:**

```python
from dpmcore.orm.registry import ModelRegistry

class DataDictionaryService(BaseService):
    def get_all_tables(self, ...):
        Table = ModelRegistry.get_model("Table")
        return self._session.query(Table).all()
```

This ensures that services always use the correct (possibly extended) model
class, including any custom columns the consumer added.

### 5.5 Strategy 4 — New Tables (Always Available)

Consumers can always create entirely new tables with foreign keys to dpmcore
models. This is standard practice and requires no special dpmcore support.

**SQLAlchemy:**

```python
class AuditLog(Base):
    __tablename__ = "custom_audit_log"

    id = mapped_column(Integer, primary_key=True)
    table_vid = mapped_column(Integer, ForeignKey("TableVersion.TableVID"))
    user = mapped_column(String(100))
    action = mapped_column(String(20))
    timestamp = mapped_column(DateTime, default=func.now())

    table_version = relationship("TableVersion")
```

**Django:**

```python
class AuditLog(models.Model):
    table_version = models.ForeignKey(
        "dpmcore_core.TableVersion",
        on_delete=models.CASCADE,
    )
    user = models.CharField(max_length=100)
    action = models.CharField(max_length=20)
    timestamp = models.DateTimeField(auto_now_add=True)
```

## 6. Schema Validation

dpmcore provides a schema validation tool that checks whether the actual
database schema matches the ORM expectations. This is essential for:

- **Mode B** (read-only schema): Validate that a legacy DB is compatible
- **Mode C** (extended): Detect drift after manual DB changes
- **CI/CD**: Verify schema consistency before deployment

### 6.1 Validation Checks

| Check | Description |
|-------|-------------|
| **Table existence** | All expected tables exist in the database |
| **Column existence** | All expected columns exist in each table |
| **Column types** | Column data types match ORM expectations |
| **Nullable** | Nullable constraints match |
| **Primary keys** | PK constraints match |
| **Foreign keys** | FK constraints exist (warning-level, not blocking) |
| **Extra columns** | Columns in DB not in ORM (info-level — expected for extensions) |
| **Extra tables** | Tables in DB not in ORM (info-level — expected for extensions) |

### 6.2 API

```python
from dpmcore.schema import validate_schema, SchemaValidationResult

result: SchemaValidationResult = validate_schema(engine)

print(result.is_compatible)     # True if core schema matches
print(result.errors)            # Blocking issues (missing tables/columns)
print(result.warnings)          # Non-blocking (missing FKs, type differences)
print(result.info)              # Informational (extra columns/tables)
```

### 6.3 CLI

```bash
dpmcore db check --database postgresql://...
# Output:
# Schema validation: COMPATIBLE
# ✓ 58 tables found
# ✓ All required columns present
# ℹ 3 extra columns found (consumer extensions)
# ℹ 2 extra tables found (consumer tables)
```

## 7. Legacy Database Support

### 7.1 Connecting to a Pre-Existing DB

```python
from dpmcore import connect

db = connect(
    "postgresql://user:pass@host/legacy_dpm_db",
    schema_mode="readonly",  # Do not attempt migrations
)

# Optional: validate compatibility
validation = db.validate_schema()
if not validation.is_compatible:
    print(f"Schema issues: {validation.errors}")
```

### 7.2 Schema Mode Configuration

| Mode | Behaviour |
|------|-----------|
| `"managed"` (default) | Apply migrations on connect. Error if DB is behind. |
| `"readonly"` | Never apply migrations. Validate schema on first use. |
| `"validate"` | Validate schema on connect, error if incompatible. Do not migrate. |
| `"none"` | No validation, no migration. Trust the schema blindly. |

```python
db = connect(url, schema_mode="managed")     # Apply migrations
db = connect(url, schema_mode="readonly")    # Legacy DB, no changes
db = connect(url, schema_mode="validate")    # Check but don't change
db = connect(url, schema_mode="none")        # Skip all checks
```

### 7.3 Migration from Access

The migration service handles importing from Access databases:

```python
db = connect("postgresql://user:pass@host/new_dpm_db", schema_mode="managed")

# This creates the schema first, then imports data
db.services.migration.migrate_from_access("/path/to/dpm.accdb")
```

## 8. Migration Workflow Examples

### 8.1 New Standalone Deployment

```bash
# 1. Create database
createdb dpm_production

# 2. Apply all migrations
dpmcore db upgrade --database postgresql://user:pass@localhost/dpm_production

# 3. Optionally import data from Access
dpmcore migrate --source access --path /path/to/dpm.accdb \
    --database postgresql://user:pass@localhost/dpm_production

# 4. Start the API server
dpmcore serve --database postgresql://user:pass@localhost/dpm_production
```

### 8.2 New Django Deployment

```bash
# 1. Apply all migrations (dpmcore + custom app)
python manage.py migrate

# 2. Optionally import data
python manage.py dpmcore_migrate --source access --path /path/to/dpm.accdb

# 3. Start Django
python manage.py runserver
```

### 8.3 Upgrading dpmcore

```bash
# Standalone
pip install --upgrade dpmcore
dpmcore db upgrade  # Apply new migrations

# Django
pip install --upgrade dpmcore
python manage.py migrate dpmcore_core  # Apply new dpmcore migrations
python manage.py migrate myapp         # Apply custom app migrations if any
```

### 8.4 Adding Custom Columns (Django)

```python
# 1. Configure swappable model in settings.py
DPMCORE_TABLE_MODEL = "myapp.CustomTable"

# 2. Define custom model
class CustomTable(AbstractTable):
    workflow_status = models.CharField(max_length=20, null=True)
    class Meta:
        db_table = "Table"
        app_label = "myapp"

# 3. Generate and apply migration
# $ python manage.py makemigrations myapp
# $ python manage.py migrate myapp
```

### 8.5 Adding Custom Columns (Standalone)

```python
# 1. Define custom model
from dpmcore.orm.rendering import AbstractTable

class CustomTable(AbstractTable):
    __tablename__ = "Table"
    workflow_status = mapped_column(String(20), nullable=True)

# 2. Configure
from dpmcore.orm.registry import ModelRegistry
ModelRegistry.configure({"Table": "mypackage.models.CustomTable"})

# 3. Generate Alembic migration
# $ alembic revision --autogenerate -m "Add workflow_status to Table"
# $ alembic upgrade head
```

## 9. Dual Model Sync (SQLAlchemy ↔ Django)

Since dpmcore maintains both SQLAlchemy models (for standalone/FastAPI) and
Django models (for Django mode), keeping them in sync is critical.

### 9.1 Single Source of Truth

The **SQLAlchemy models** are the single source of truth for the schema.
Django models are derived from them, either:

**Option A — Code generation (recommended):**

A build-time script generates Django models from the SQLAlchemy model
definitions:

```bash
dpmcore generate-django-models \
    --output src/dpmcore/django/models/generated.py
```

This reads SQLAlchemy model classes and generates equivalent Django model
classes with matching `db_table`, `db_column`, and field types.

**Option B — Manual sync:**

Both are hand-written and kept in sync via tests:

```python
# tests/test_model_sync.py

def test_sqlalchemy_django_sync():
    """Verify that SQLAlchemy and Django models define the same schema."""
    from dpmcore.orm import Base as SABase
    from dpmcore.django.models import all_models as django_models

    for sa_model in SABase.__subclasses__():
        table_name = sa_model.__tablename__
        django_model = django_models.get(table_name)
        assert django_model is not None, f"Missing Django model for {table_name}"

        sa_columns = {c.name for c in sa_model.__table__.columns}
        dj_columns = {f.db_column or f.name for f in django_model._meta.get_fields()
                      if hasattr(f, 'db_column')}

        assert sa_columns == dj_columns, (
            f"Column mismatch for {table_name}: "
            f"SA has {sa_columns - dj_columns}, "
            f"Django has {dj_columns - sa_columns}"
        )
```

### 9.2 Recommendation

**Option A (code generation)** is preferred because:

- Eliminates manual sync errors
- Can be part of CI/CD (generate → compare → fail if different)
- Reduces maintenance burden

## 10. Summary

| Concern | Solution |
|---------|----------|
| Schema creation | Alembic (standalone) or Django migrations (Django mode) |
| Legacy DB support | `schema_mode="readonly"` skips migrations, validates schema |
| Schema validation | `dpmcore db check` / `validate_schema(engine)` |
| Adding columns | Swappable model pattern with abstract bases |
| Adding tables | ForeignKey to dpmcore models (standard practice) |
| Model registry | `ModelRegistry` resolves swappable models at runtime |
| SQLAlchemy ↔ Django sync | Code generation from SA models (recommended) |
| Upgrading dpmcore | `dpmcore db upgrade` / `python manage.py migrate` |
| Which entities are swappable | Table, TableVersion, Module, ModuleVersion, Operation, OperationVersion, Variable, Release, Framework |
