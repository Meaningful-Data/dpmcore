# dpmcore Specification — Usage Modes

## 1. Overview

dpmcore supports three usage modes that share the same ORM and service layers
but differ in how they are deployed and extended.

```
┌─────────────────────────────────────────────────────────────┐
│                        Usage Modes                           │
│                                                               │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────┐│
│  │ Mode 1:       │  │ Mode 2:       │  │ Mode 3:           ││
│  │ Standalone    │  │ Web App       │  │ Django Integration ││
│  │ Library       │  │               │  │                   ││
│  │               │  │ FastAPI +     │  │ Django project +  ││
│  │ Python API    │  │ dpmcore       │  │ dpmcore.django    ││
│  │ only          │  │ REST API      │  │ app               ││
│  └───────┬───────┘  └───────┬───────┘  └─────────┬─────────┘│
│          │                  │                     │          │
│  ┌───────┴──────────────────┴─────────────────────┴─────────┐│
│  │              Shared: ORM + Services                       ││
│  └───────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## 2. Mode 1 — Standalone Library

### 2.1 Description

dpmcore is used as a Python package. The consumer imports it, provides
database connection details, and calls the Python API directly. No web
framework is involved. No HTTP server runs.

### 2.2 Installation

```bash
pip install dpmcore
# or
poetry add dpmcore
```

Only core dependencies are installed (SQLAlchemy, ANTLR4, pandas, etc.).
FastAPI and Django are not required.

### 2.3 Usage Examples

**Basic connection and query:**

```python
from dpmcore import connect

# Connect to a database
db = connect("postgresql://user:pass@localhost/dpm_db")

# Or SQLite
db = connect("sqlite:///path/to/dpm.db")

# Or with explicit config
db = connect(
    dialect="postgresql",
    host="localhost",
    port=5432,
    database="dpm_db",
    user="user",
    password="pass",
    pool_size=10,
)
```

The `connect()` function returns a `DpmConnection` object:

```python
class DpmConnection:
    """Main entry point for standalone library usage."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._session_factory = SessionFactory(engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Create a new session for database operations."""
        with self._session_factory() as session:
            yield session

    @property
    def services(self) -> ServiceRegistry:
        """Get a service registry with a fresh session."""
        ...

    @property
    def orm(self) -> ModuleType:
        """Access ORM model classes."""
        ...
```

**Using services:**

```python
from dpmcore import connect

db = connect("sqlite:///dpm.db")

# DPM-XL validation
result = db.services.dpm_xl.validate_syntax("v1234 = v5678 + v9012")
print(result.is_valid)  # True

result = db.services.dpm_xl.validate_semantic(
    "v1234 = v5678 + v9012",
    release_code="3.4",
)
print(result.is_valid)
print(result.warning)

# Data dictionary
tables = db.services.data_dictionary.get_all_tables(release_code="3.4")
for table in tables:
    print(f"{table.code}: {table.name}")

# AST generation
ast = db.services.dpm_xl.generate_ast(
    "v1234 = v5678 + v9012",
    level=2,
    release_code="3.4",
)

# Script generation
script = db.services.dpm_xl.generate_script(
    expressions=["v1234 = v5678 + v9012", "v4567 > 0"],
    release_code="3.4",
    severity="error",
)
```

**Direct ORM access:**

```python
from dpmcore import connect
from dpmcore.orm import Table, TableVersion, ModuleVersion

db = connect("sqlite:///dpm.db")

with db.session() as session:
    # SQLAlchemy queries
    tables = session.query(Table).all()

    # Filtered queries
    from dpmcore.orm import filter_by_release
    active_versions = (
        session.query(TableVersion)
        .filter(filter_by_release(TableVersion, release_id=5))
        .all()
    )

    # Relationships
    for mv in session.query(ModuleVersion).filter_by(code="FINREP_IND"):
        for comp in mv.module_version_compositions:
            print(f"  Table: {comp.table_version.code}")
```

**Syntax-only usage (no database):**

```python
from dpmcore.services import SyntaxService

# No database connection needed for syntax validation
syntax = SyntaxService()
result = syntax.validate("v1234 = v5678 + v9012")
print(result.is_valid)  # True

ast = syntax.parse("v1234 = v5678 + v9012")
print(ast)  # Dict representation of AST
```

### 2.4 Optional Dependencies

In standalone mode, certain features require additional packages:

| Feature | Package | Install Extra |
|---------|---------|---------------|
| PostgreSQL | psycopg2-binary | `pip install dpmcore[postgres]` |
| SQL Server | pyodbc | `pip install dpmcore[sqlserver]` |
| Instance generation | (included) | Core |
| DPM-XL parsing | antlr4-python3-runtime | Core |

## 3. Mode 2 — Web Application

### 3.1 Description

dpmcore ships a ready-to-run web application that exposes the REST API
described in [02-rest-api.md](02-rest-api.md). It can be started from the CLI
or deployed as a WSGI/ASGI application.

### 3.2 Installation

```bash
pip install dpmcore[server]
# Installs FastAPI, Uvicorn, and related dependencies
```

### 3.3 CLI Usage

```bash
# Start the server
dpmcore serve \
    --database postgresql://user:pass@localhost/dpm_db \
    --host 0.0.0.0 \
    --port 8000

# With SQLite
dpmcore serve --database sqlite:///path/to/dpm.db

# With environment file
dpmcore serve --env .env

# With custom workers
dpmcore serve --database postgresql://... --workers 4
```

### 3.4 ASGI Application

For production deployment with Gunicorn, Uvicorn, or similar:

```python
# asgi.py
from dpmcore.api import create_app

app = create_app(
    database_url="postgresql://user:pass@localhost/dpm_db",
    title="DPM API",
    version="1.0.0",
)
```

```bash
uvicorn asgi:app --host 0.0.0.0 --port 8000 --workers 4
```

### 3.5 Application Factory

```python
def create_app(
    database_url: str | None = None,
    engine: Engine | None = None,
    title: str = "dpmcore API",
    version: str = "1.0.0",
    cors_origins: list[str] | None = None,
    auth_enabled: bool = False,
    api_key: str | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Either database_url or engine must be provided.
    """
    ...
```

### 3.6 Features

- All REST API endpoints from [02-rest-api.md](02-rest-api.md)
- Interactive OpenAPI documentation at `/api/v1/docs`
- Health check at `/api/v1/system/health`
- CORS support (configurable origins)
- Optional API key authentication
- Structured JSON logging
- Request/response timing middleware

### 3.7 Configuration

Configuration via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DPMCORE_DATABASE_URL` | Database connection URL | *(required)* |
| `DPMCORE_HOST` | Bind host | `0.0.0.0` |
| `DPMCORE_PORT` | Bind port | `8000` |
| `DPMCORE_WORKERS` | Number of worker processes | `1` |
| `DPMCORE_LOG_LEVEL` | Logging level | `info` |
| `DPMCORE_CORS_ORIGINS` | Comma-separated CORS origins | `*` |
| `DPMCORE_AUTH_ENABLED` | Enable authentication | `false` |
| `DPMCORE_API_KEY` | API key (when auth is enabled) | *(none)* |
| `DPMCORE_POOL_SIZE` | Connection pool size | `20` |
| `DPMCORE_MAX_OVERFLOW` | Max pool overflow | `40` |

### 3.8 Docker

```dockerfile
FROM python:3.12-slim
RUN pip install dpmcore[server]
EXPOSE 8000
CMD ["dpmcore", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
services:
  dpmcore:
    image: dpmcore:latest
    ports:
      - "8000:8000"
    environment:
      DPMCORE_DATABASE_URL: postgresql://user:pass@db/dpm
    depends_on:
      - db

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: dpm
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
```

## 4. Mode 3 — Django Integration

### 4.1 Description

dpmcore can be installed as a Django app within a Django project. This is the
mode for building DPM management applications. It provides:

- dpmcore ORM models accessible from Django
- Services available to Django views
- REST API endpoints mountable as Django URL patterns
- Django admin integration for DPM entities
- Ability to add custom models that reference dpmcore models

### 4.2 Installation

```bash
pip install dpmcore[django]
# Installs Django, Django REST Framework
```

### 4.3 Django Project Setup

```python
# settings.py

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",

    # dpmcore Django app
    "dpmcore.django",

    # Your custom apps
    "myapp",
]

# Database configuration
# Option A: Single database — dpmcore uses Django's default DB
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "dpm_management",
        "USER": "user",
        "PASSWORD": "pass",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

# Option B: Separate databases — dpmcore uses its own DB
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "management_app",
        ...
    },
    "dpm": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "dpm_data",
        ...
    },
}

DATABASE_ROUTERS = ["dpmcore.django.routers.DpmRouter"]

# dpmcore configuration
DPMCORE = {
    "DATABASE": "dpm",  # Which Django database to use (default: "default")
}
```

### 4.4 Model Integration Strategy

The core challenge is making SQLAlchemy models usable in Django. We support
two approaches:

#### Approach A: Django-native models (recommended)

dpmcore provides Django model classes that mirror the SQLAlchemy models. The
`dpmcore.django` app includes Django models that map to the same database
tables:

```python
# dpmcore/django/models.py (auto-generated or hand-written)
from django.db import models

class Table(models.Model):
    table_id = models.AutoField(primary_key=True, db_column="TableID")
    is_abstract = models.BooleanField(db_column="IsAbstract")
    has_open_columns = models.BooleanField(db_column="HasOpenColumns")
    # ... all columns mapped to Django fields

    class Meta:
        managed = False  # dpmcore owns the schema
        db_table = "Table"
```

**Advantages:**

- Full Django ORM compatibility (QuerySets, admin, forms, serializers)
- Custom apps can create ForeignKeys to dpmcore models
- Django migrations manage custom tables; dpmcore tables are `managed = False`

**Disadvantages:**

- Model definitions are duplicated (SQLAlchemy + Django)
- Must keep both in sync

#### Approach B: SQLAlchemy bridge

dpmcore services use SQLAlchemy internally, and a thin bridge provides Django
integration:

```python
# dpmcore/django/bridge.py
from dpmcore.orm import SessionFactory, Base

class DpmBridge:
    """Bridge between Django and dpmcore SQLAlchemy models."""

    def __init__(self):
        from django.conf import settings
        db_config = settings.DATABASES[settings.DPMCORE.get("DATABASE", "default")]
        url = self._django_db_to_url(db_config)
        self._engine = create_engine(url)
        self._session_factory = SessionFactory(self._engine)

    def get_session(self):
        return self._session_factory()

    def get_services(self):
        from dpmcore.services import ServiceRegistry
        session = self.get_session()
        return ServiceRegistry(session)
```

**Recommended approach:** **A** (Django-native models) because it enables the
full Django ecosystem: admin, forms, serializers, QuerySets, ForeignKeys from
custom apps, and migrations.

### 4.5 URL Configuration

```python
# urls.py (project)
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("dpmcore.django.urls")),  # dpmcore REST API
    path("", include("myapp.urls")),                   # Custom app
]
```

The `dpmcore.django.urls` module provides the same REST API endpoints as the
FastAPI version, implemented using Django REST Framework views.

### 4.6 Custom Models Extending dpmcore

```python
# myapp/models.py
from django.db import models
from dpmcore.django.models import Table, ModuleVersion

class CustomTableAnnotation(models.Model):
    """Custom metadata added to DPM tables by the management app."""

    table = models.ForeignKey(
        Table,
        on_delete=models.CASCADE,
        related_name="annotations",
    )
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("draft", "Draft"),
            ("review", "Under Review"),
            ("approved", "Approved"),
        ],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "custom_table_annotation"  # Custom table in the DB


class WorkflowStep(models.Model):
    """Custom workflow management on top of dpmcore modules."""

    module_version = models.ForeignKey(
        ModuleVersion,
        on_delete=models.CASCADE,
        related_name="workflow_steps",
    )
    step_name = models.CharField(max_length=100)
    completed = models.BooleanField(default=False)
    completed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
    )
```

### 4.7 Custom Services

```python
# myapp/services.py
from dpmcore.services import DataDictionaryService, ServiceRegistry

class ExtendedDataDictionary(DataDictionaryService):
    """Extended data dictionary with custom queries."""

    def get_tables_with_annotations(self, release_code=None):
        tables = self.get_all_tables(release_code=release_code)
        # Add custom annotation data
        ...
        return tables

class CustomServiceRegistry(ServiceRegistry):
    """Extended service registry with custom services."""

    def __init__(self, session):
        super().__init__(session)
        self.extended_data_dictionary = ExtendedDataDictionary(session)
```

### 4.8 Django Admin Integration

```python
# dpmcore/django/admin.py
from django.contrib import admin
from dpmcore.django.models import (
    Table, TableVersion, Module, ModuleVersion,
    Framework, Release, Operation, Variable,
)

@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ["table_id", "concept_guid"]
    search_fields = ["table_versions__code", "table_versions__name"]
    readonly_fields = ["table_id"]  # managed = False tables are read-only

@admin.register(Release)
class ReleaseAdmin(admin.ModelAdmin):
    list_display = ["code", "date", "is_current", "status"]
    list_filter = ["is_current", "status"]

# ... more admin classes for key entities
```

### 4.9 Management Commands

```bash
# Import DPM data from an Access database
python manage.py dpmcore_migrate --source access --path /path/to/dpm.accdb

# Export DPM data to SQLite
python manage.py dpmcore_export --format sqlite --output dpm_export.db

# Validate all operations in a release
python manage.py dpmcore_validate --release 3.4

# Generate validation scripts
python manage.py dpmcore_generate_script --release 3.4 --output scripts/
```

### 4.10 Using Services in Django Views

```python
# myapp/views.py
from django.http import JsonResponse
from dpmcore.django.utils import get_dpm_services

def table_list(request):
    """List all tables with optional release filter."""
    release = request.GET.get("release")
    services = get_dpm_services()
    tables = services.data_dictionary.get_all_tables(release_code=release)
    return JsonResponse({
        "tables": [t.__dict__ for t in tables]
    })

# With DRF
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(["POST"])
def validate_expression(request):
    """Validate a DPM-XL expression."""
    expression = request.data.get("expression")
    release = request.data.get("release")
    services = get_dpm_services()
    result = services.dpm_xl.validate_semantic(
        expression, release_code=release
    )
    return Response({
        "isValid": result.is_valid,
        "errorMessage": result.error_message,
        "warning": result.warning,
    })
```

## 5. Dependency Matrix

| Dependency | Mode 1 (Standalone) | Mode 2 (Web App) | Mode 3 (Django) |
|------------|:-------------------:|:-----------------:|:---------------:|
| sqlalchemy | Required | Required | Required |
| antlr4-python3-runtime | Required | Required | Required |
| pandas | Required | Required | Required |
| click | Optional (CLI) | Required | Optional |
| rich | Optional (CLI) | Required | Optional |
| fastapi | Not needed | Required | Not needed |
| uvicorn | Not needed | Required | Not needed |
| django | Not needed | Not needed | Required |
| djangorestframework | Not needed | Not needed | Required |
| psycopg2-binary | Optional | Optional | Optional |
| pyodbc | Optional | Optional | Optional |

### pip install extras:

```toml
[project.optional-dependencies]
server = ["fastapi>=0.110", "uvicorn[standard]>=0.29"]
django = ["django>=4.2", "djangorestframework>=3.15"]
postgres = ["psycopg2-binary>=2.9"]
sqlserver = ["pyodbc>=5.1"]
all = ["dpmcore[server,django,postgres,sqlserver]"]
```

## 6. Configuration Comparison

| Setting | Mode 1 | Mode 2 | Mode 3 |
|---------|--------|--------|--------|
| Database URL | `connect()` arg | `DPMCORE_DATABASE_URL` env var | `DATABASES` in settings.py |
| Pool size | `connect()` arg | `DPMCORE_POOL_SIZE` env var | Django DB config |
| Auth | N/A | `DPMCORE_AUTH_ENABLED` | Django auth system |
| CORS | N/A | `DPMCORE_CORS_ORIGINS` | Django CORS middleware |
| Logging | Python logging | `DPMCORE_LOG_LEVEL` | Django `LOGGING` |

## 7. Testing Strategy

### 7.1 Shared Tests

Core ORM and service tests run in all modes:

```python
# tests/unit/services/test_syntax.py
def test_syntax_validation():
    syntax = SyntaxService()
    result = syntax.validate("v1234 = v5678")
    assert result.is_valid

# tests/integration/services/test_semantic.py
def test_semantic_validation(memory_session):
    semantic = SemanticService(memory_session)
    result = semantic.validate("v1234 = v5678", release_id=1)
    assert result.is_valid
```

### 7.2 Mode-Specific Tests

```python
# tests/integration/api/test_rest_api.py  (Mode 2)
from fastapi.testclient import TestClient

def test_get_tables(app):
    client = TestClient(app)
    response = client.get("/api/v1/structure/table")
    assert response.status_code in (200, 204)

# tests/integration/django/test_django_models.py  (Mode 3)
from django.test import TestCase

class TableModelTest(TestCase):
    databases = {"dpm"}

    def test_table_queryset(self):
        from dpmcore.django.models import Table
        tables = Table.objects.all()
        self.assertIsNotNone(tables)
```

### 7.3 Test Markers

```
pytest -m unit           # Unit tests (no DB)
pytest -m integration    # Integration tests (with DB)
pytest -m api            # REST API tests
pytest -m django         # Django integration tests
```
