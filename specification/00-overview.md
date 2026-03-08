# dpmcore Specification — Overview

## 1. Purpose

**dpmcore** is a Python library that implements the core infrastructure for the
DPM (Data Point Model) 2.0 Refit standard. It provides three architectural
layers — ORM, REST API, and Services — that can be used independently or
together, in three distinct deployment modes.

## 2. Goals

| # | Goal | Description |
|---|------|-------------|
| G1 | **Complete DPM metamodel** | Map every DPM 2.0 Refit entity to a Python ORM class with full relationship support |
| G2 | **SDMX-inspired REST API** | Offer a browsable, SDMX-style REST API for querying DPM structures |
| G3 | **DPM-XL services** | Provide syntactic validation, semantic validation, AST generation, scope calculation, and script generation for DPM-XL expressions |
| G4 | **Standalone mode** | Work as a plain Python library — no web framework required |
| G5 | **Web application mode** | Provide a ready-to-run web application exposing the REST API |
| G6 | **Extensible core for Django** | Be importable as a foundation for Django-based DPM management applications |
| G7 | **Multi-database support** | Support SQLite, PostgreSQL, and SQL Server backends |

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Consumer Applications                   │
│  (Django apps, CLI tools, Jupyter notebooks, scripts, …)     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │  REST API    │  │    Services      │  │   Direct ORM   │  │
│  │  (Layer 2)   │  │    (Layer 3)     │  │   access       │  │
│  │             │  │                  │  │   (Layer 1)    │  │
│  │  SDMX-like  │  │  DPM-XL Engine   │  │                │  │
│  │  endpoints  │  │  Scope Calc.     │  │  Query, filter │  │
│  │  JSON resp. │  │  Script Gen.     │  │  create, join  │  │
│  │             │  │  Instance Gen.   │  │                │  │
│  └──────┬──────┘  └────────┬─────────┘  └───────┬────────┘  │
│         │                  │                     │            │
│  ┌──────┴──────────────────┴─────────────────────┴────────┐  │
│  │                     ORM Layer (Layer 1)                 │  │
│  │                                                         │  │
│  │  Models · Relationships · Views · Session Management    │  │
│  │  Multi-DB (SQLite / PostgreSQL / SQL Server)            │  │
│  └─────────────────────────┬───────────────────────────────┘  │
│                             │                                  │
└─────────────────────────────┼──────────────────────────────────┘
                              │
                     ┌────────┴────────┐
                     │    Database      │
                     └─────────────────┘
```

## 4. Layers

### Layer 1 — ORM

The ORM maps every DPM metamodel entity to a SQLAlchemy model class. It is the
single source of truth for the database schema and provides:

- Model classes for all DPM entities (Glossary, Rendering, Variables, Operations,
  Packaging)
- Relationships (one-to-many, many-to-many, self-referential)
- Release-aware versioning (start/end release filtering)
- View models for complex pre-joined queries
- Session and engine management with connection pooling
- Multi-database dialect support

Full specification: [01-orm-layer.md](01-orm-layer.md)

### Layer 2 — REST API

An SDMX-inspired REST API that follows familiar URL patterns and conventions:

- Hierarchical URL paths: `/{artefactType}/{owner}/{id}/{version}`
- `detail` and `references` query parameters for response control
- Content negotiation (JSON primary, XML optional)
- Pagination, filtering, and sorting
- 204 for empty results (following SDMX convention)

Full specification: [02-rest-api.md](02-rest-api.md)

### Layer 3 — Services

Business-logic services that operate on top of the ORM:

- **DPM-XL Engine**: Syntax validation, semantic validation, AST generation,
  operation scope calculation, validation script generation
- **Data Dictionary**: Table/variable/module queries
- **Explorer**: Inverse lookups and introspection
- **Instance Generation**: XBRL-CSV package creation
- **Migration**: Database import/export

Full specification: [03-services.md](03-services.md)

## 5. Usage Modes

### Mode 1 — Standalone Library

```python
from dpmcore import connect, services

db = connect("postgresql://user:pass@host/dpm_db")
tables = services.data_dictionary(db).get_all_tables(release_code="3.4")
result = services.dpm_xl(db).validate("v1234 = v5678 + v9012")
```

No web framework. No HTTP server. The consumer provides database connection
details and calls the library's Python API directly.

### Mode 2 — Web Application

```bash
dpmcore serve --database postgresql://user:pass@host/dpm_db --port 8000
```

A ready-to-run web application that exposes the REST API. Can be started from
the CLI or deployed as a WSGI/ASGI application. Includes:

- All REST API endpoints
- Interactive API documentation (OpenAPI/Swagger)
- Health checks and monitoring endpoints

### Mode 3 — Django Integration

```python
# settings.py
INSTALLED_APPS = [
    "dpmcore.django",          # Registers models, admin, management commands
    "myapp",                   # Custom application extending dpmcore
]
```

dpmcore can be installed as a Django app. Its ORM models become Django models
(or are bridged to them), services are available as Django utilities, and the
REST API endpoints are mountable as Django URL patterns. Custom applications can:

- Add custom models with foreign keys to dpmcore models
- Extend or override services
- Add custom REST API endpoints alongside dpmcore endpoints
- Use Django admin for DPM data management

Full specification: [04-usage-modes.md](04-usage-modes.md)

### Schema Management & Migrations

dpmcore uses a hybrid schema management approach:

- It **can create and migrate** its own schema (Alembic for standalone,
  Django migrations for Django mode)
- It **can connect** to pre-existing databases without modifying them
- Consumers **can extend** dpmcore tables with additional columns via
  swappable models, and add entirely new tables via foreign keys
- A model registry resolves concrete model classes at runtime, supporting
  the swappable pattern

Full specification: [05-schema-migrations.md](05-schema-migrations.md)

### API Messages & Containment Model

Defines which entities are independently addressable (maintainable) vs.
contained within a parent, the JSON message format for each artefact type,
and the `references` parameter behaviour for traversing the dependency graph.

Full specification: [06-api-messages.md](06-api-messages.md)

### Project Setup & Conventions

Defines the project layout, tooling, code quality standards, testing
infrastructure, documentation, and CI/CD pipeline. All choices are aligned
with [pysdmx](https://github.com/bis-med-it/pysdmx) for ecosystem consistency.

Full specification: [07-project-setup.md](07-project-setup.md)

## 6. Technology Stack

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Language | Python ≥ 3.10 | Current baseline, type hints, pattern matching |
| ORM | SQLAlchemy ≥ 2.0 | Industry standard, multi-DB, Django bridge exists |
| REST framework (standalone) | FastAPI | Async, OpenAPI auto-docs, lightweight |
| REST framework (Django) | Django REST Framework | Native Django integration |
| Migrations | Alembic (standalone), Django migrations (Django mode) | Native tools for each context |
| Parsing | ANTLR4 | Existing DPM-XL grammar |
| Data frames | Pandas | Existing usage, batch queries |
| CLI | Click + Rich | Existing usage, rich terminal output |
| Testing | pytest | Existing usage, markers, fixtures |
| Package management | Poetry | Existing usage |

## 7. Package Structure (Target)

```
dpmcore/
├── pyproject.toml
├── src/
│   └── dpmcore/
│       ├── __init__.py              # Public API: connect(), version
│       ├── orm/                     # Layer 1 — ORM
│       │   ├── __init__.py
│       │   ├── base.py              # Base, engine, session management
│       │   ├── glossary.py          # Category, Item, SubCategory, Property, Context, …
│       │   ├── rendering.py         # Table, TableVersion, Header, Cell, …
│       │   ├── variables.py         # Variable, VariableVersion, Dimension, …
│       │   ├── operations.py        # Operation, OperationVersion, OperationScope, …
│       │   ├── packaging.py         # Framework, Module, ModuleVersion, Release, …
│       │   ├── infrastructure.py    # Organisation, Language, User, DataType, …
│       │   └── views.py             # View models for complex queries
│       ├── api/                     # Layer 2 — REST API
│       │   ├── __init__.py
│       │   ├── app.py               # FastAPI application factory
│       │   ├── routes/
│       │   │   ├── glossary.py
│       │   │   ├── rendering.py
│       │   │   ├── variables.py
│       │   │   ├── operations.py
│       │   │   ├── packaging.py
│       │   │   └── dpm_xl.py
│       │   ├── schemas.py           # Pydantic response/request models
│       │   ├── filters.py           # Query parameter handling
│       │   └── serialization.py     # JSON serialization
│       ├── services/                # Layer 3 — Services
│       │   ├── __init__.py
│       │   ├── dpm_xl/
│       │   │   ├── __init__.py
│       │   │   ├── syntax.py        # Syntax validation
│       │   │   ├── semantic.py       # Semantic validation
│       │   │   ├── ast_generator.py  # AST generation (3 levels)
│       │   │   ├── scope_calculator.py
│       │   │   └── script_generator.py
│       │   ├── data_dictionary.py
│       │   ├── explorer.py
│       │   ├── instance.py
│       │   └── migration.py
│       ├── dpm_xl/                  # DPM-XL engine internals
│       │   ├── grammar/
│       │   ├── ast/
│       │   ├── operators/
│       │   ├── types/
│       │   └── utils/
│       ├── django/                  # Django integration app
│       │   ├── __init__.py
│       │   ├── apps.py
│       │   ├── models.py            # Django model proxies / bridges
│       │   ├── admin.py
│       │   ├── urls.py
│       │   ├── views.py
│       │   └── management/
│       │       └── commands/
│       ├── cli/                     # Command-line interface
│       │   ├── __init__.py
│       │   └── main.py
│       └── exceptions/
│           ├── __init__.py
│           └── messages.py
├── tests/
│   ├── unit/
│   └── integration/
└── specification/                   # This specification
```

## 8. Design Principles

1. **Layer independence**: Each layer can be used without the others. The ORM
   works without the REST API. Services work without the REST API. The REST
   API is just an HTTP facade over services.

2. **Session-as-dependency**: All services and API endpoints receive a database
   session as an explicit dependency — never rely on global state.

3. **Django compatibility**: Use SQLAlchemy 2.0 with the declarative style that
   maps cleanly to Django models. Provide a Django app that bridges or proxies
   the SQLAlchemy models.

4. **Extensibility over configuration**: Prefer class inheritance and
   composition over settings dictionaries. Let consumers subclass models and
   services.

5. **DPM fidelity**: Model names, attribute names, and relationships should
   mirror the DPM 2.0 Refit metamodel specification as closely as possible.

6. **Release-aware by default**: All queries that return versioned entities
   should accept an optional release filter. When provided, only the versions
   active in that release are returned.

7. **Schema extensibility**: Key models use an abstract-base + swappable-concrete
   pattern. Consumers can replace the concrete model with their own subclass
   that adds custom columns to the same physical table. A `ModelRegistry`
   resolves the active concrete class at runtime.

8. **Hybrid schema management**: dpmcore can create and migrate its own schema
   (new deployments) or connect to pre-existing databases (legacy). Schema
   validation detects drift without requiring migrations.
