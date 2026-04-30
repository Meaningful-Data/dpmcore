# dpmcore

A Python library that implements the DPM (Data Point Model) 2.0 Refit standard
for regulatory reporting. It provides an ORM, services layer, and REST API that
can be used independently or together in three deployment modes.

## Installation

```bash
pip install dpmcore
```

Optional extras:

```bash
pip install dpmcore[migration]   # Access database migration (pandas)
pip install dpmcore[data]        # Pandas support (semantic validation, scope calculation)
pip install dpmcore[server]      # FastAPI REST server
pip install dpmcore[django]      # Django integration
pip install dpmcore[postgres]    # PostgreSQL backend
pip install dpmcore[sqlserver]   # SQL Server backend
pip install dpmcore[cli]         # Command-line interface
pip install dpmcore[all]         # Everything
```

## Quick Start

### Mode 1 — Standalone Library

Use dpmcore as a plain Python library. No web framework or HTTP server
required.

**Connect to a database:**

```python
from dpmcore import connect

# SQLite
db = connect("sqlite:///path/to/dpm.db")

# PostgreSQL
db = connect("postgresql://user:pass@host:5432/dpm_db")

# With connection pool options
db = connect(
    "postgresql://user:pass@host:5432/dpm_db",
    pool_config={"pool_size": 20, "max_overflow": 10},
)
```

**Syntax validation** (no database needed):

```python
from dpmcore.services import SyntaxService

syntax = SyntaxService()

result = syntax.validate("{tC_01.00, r0100, c0010} + {tC_01.00, r0200, c0010}")
print(result.is_valid)       # True
print(result.error_message)  # None

result = syntax.validate("invalid {{{{")
print(result.is_valid)       # False
print(result.error_message)  # "offendingSymbol: ..."
```

**Semantic validation** (requires database):

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    result = db.services.semantic.validate(
        "{tC_01.00, r0100, c0010} + {tC_01.00, r0200, c0010}",
        release_id=5,
    )
    print(result.is_valid)
    print(result.warning)
```

**Engine-ready validations script:**

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    ast_svc = db.services.ast_generator

    script = ast_svc.script(
        expressions=[
            ("{tC_01.00, r0100, c0010} = {tC_01.00, r0200, c0010}", "v0001"),
            ("{tC_01.00, r0200, c0010} > 0",                        "v0002"),
        ],
        preconditions=[
            ("{is_reporting_entity}", ["v0001", "v0002"]),
        ],
        module_code="COREP_Con",
        module_version="2.0.1",
    )
    print(script["enriched_ast"])
    print(script["dependency_information"])
    print(script["dependency_modules"])
```

`preconditions` is optional — pass it when one or more validations
share a guarding precondition expression.

The same script generation is exposed via the CLI and the REST API.
The CLI input file mirrors the Python shape:

```json
{
    "expressions": [
        ["{tC_01.00, r0100, c0010} = {tC_01.00, r0200, c0010}", "v0001"]
    ],
    "preconditions": [
        ["{is_reporting_entity}", ["v0001"]]
    ]
}
```

```bash
dpmcore generate-script \
    --expressions ./rules.json \
    --module-code COREP_Con --module-version 2.0.1 \
    --database sqlite:///dpm.db --output ./script.json
```

```bash
curl -X POST http://localhost:8000/api/v1/scripts \
    -H 'content-type: application/json' \
    -d '{
          "expressions":[["{tC_01.00, r0100, c0010} = {tC_01.00, r0200, c0010}","v0001"]],
          "preconditions":[{"expression":"{is_reporting_entity}","validation_codes":["v0001"]}],
          "module_code":"COREP_Con",
          "module_version":"2.0.1"
        }'
```

**Data dictionary queries:**

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    dd = db.services.data_dictionary

    releases = dd.get_releases()
    tables   = dd.get_tables(release_id=5)
    items    = dd.get_all_item_signatures(release_id=5)
```

**Operation scope calculation:**

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    result = db.services.scope_calculator.calculate_from_expression(
        expression="{tC_01.00, r0100, c0010} = {tC_01.00, r0200, c0010}",
        release_id=5,
    )
    print(result.total_scopes)
    print(result.module_versions)
```

**Explorer — reverse lookups:**

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    explorer = db.services.explorer

    var = explorer.get_variable_by_code("mi123", release_id=5)
    usage = explorer.get_variable_usage(variable_vid=99)
    tables = explorer.search_table("C_01")
```

**Hierarchy — framework / module / table tree:**

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    hierarchy = db.services.hierarchy

    frameworks = hierarchy.get_all_frameworks(release_id=5)
    module     = hierarchy.get_module_version("F_01.01", release_id=5)
    tables     = hierarchy.get_tables_for_module("F_01.01", release_id=5)
    details    = hierarchy.get_table_details("tC_01.00", release_id=5)
```

**Migration — import from Access:**

```python
from dpmcore import connect

# Via DpmConnection (uses the connection's engine)
with connect("sqlite:///dpm.db") as db:
    result = db.services.migration.migrate_from_access("/path/to/dpm.accdb")
    print(f"Migrated {result.tables_migrated} tables, {result.total_rows} rows")
```

```python
# Standalone usage with any SQLAlchemy engine
from sqlalchemy import create_engine
from dpmcore.loaders.migration import MigrationService

engine = create_engine("postgresql://user:pass@host/dpm_db")
service = MigrationService(engine)
result = service.migrate_from_access("/path/to/dpm.accdb")
```

Or from the command line:

```bash
pip install dpmcore[cli,migration]
dpmcore migrate --source /path/to/dpm.accdb --database sqlite:///dpm.db
```

**Export Access to CSV** (requires `migration` extra and [mdb-tools](https://github.com/mdbtools/mdbtools)):

Export every user table from an `.accdb` / `.mdb` file to individual CSV
files. Tables are exported in parallel (up to 8 workers).

```python
from pathlib import Path
from dpmcore.services.export_csv import ExportCsvService

result = ExportCsvService().export("/path/to/dpm.accdb", Path("data/DPM"))
print(f"Exported {result.tables_exported} tables to {result.output_dir}")
```

Or from the command line:

```bash
dpmcore export-csv /path/to/dpm.accdb --output-dir data/DPM
```

The `--output-dir` option defaults to `data/DPM`.

**Build Meilisearch JSON** (requires `migration` extra):

Generate a Meilisearch-ready JSON document that contains all DPM operation
versions with their scopes, module assignments, operand references, and
version history. The pipeline is:
*Access → CSV → in-memory SQLite → JSON* (the CSV and SQLite steps are handled
transparently when `access_file` is supplied).

```python
from dpmcore.services.meili_build import MeiliBuildService

# From a directory of pre-exported CSV tables
result = MeiliBuildService().build(
    output_file="operations.json",
    source_dir="data/DPM",
)
print(f"Wrote {result.operations_written} operations to {result.output_file}")

# Directly from an Access file — CSV export is handled transparently
result = MeiliBuildService().build(
    output_file="operations.json",
    access_file="/path/to/dpm.accdb",
    ecb_validations_file="validation_versions.csv",  # optional
)
```

Or from the command line:

```bash
# From a pre-exported CSV directory
dpmcore build-meili-json --source-dir data/DPM --output operations.json

# Directly from an Access file
dpmcore build-meili-json --access-file /path/to/dpm.accdb --output operations.json

# With optional ECB validations CSV
dpmcore build-meili-json --access-file /path/to/dpm.accdb \
    --ecb-validations-file validation_versions.csv \
    --output operations.json
```

The `--output` option defaults to `operations.json`. `--source-dir` and
`--access-file` are mutually exclusive.

**Unified facade:**

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    dpm_xl = db.services.dpm_xl

    dpm_xl.validate_syntax("{tC_01.00, r0100, c0010}")
    dpm_xl.validate_semantic("{tC_01.00, r0100, c0010}", release_id=5)
```

**Direct ORM access:**

```python
from dpmcore import connect
from dpmcore.orm.infrastructure import Release

with connect("sqlite:///dpm.db") as db:
    session = db.orm
    releases = session.query(Release).all()
```

### Mode 2 — Web Application (REST API)

> Requires the `server` extra: `pip install dpmcore[server]`

Start a ready-to-run FastAPI server exposing SDMX-inspired endpoints:

```bash
dpmcore serve --database sqlite:///dpm.db --port 8000
```

Then browse the interactive API docs at `http://localhost:8000/api/v1/docs`.

### Mode 3 — Django Integration

> Requires the `django` extra: `pip install dpmcore[django]`

Add dpmcore to your Django project:

```python
# settings.py
INSTALLED_APPS = [
    "dpmcore.django",
    # ... your apps ...
]
```

This registers DPM models in Django admin, adds management commands, and
exposes REST endpoints mountable in your URL configuration.

## Architecture

```
+---------------------------------------------------------------+
|                   Consumer Applications                        |
|  (Django apps, CLI tools, Jupyter notebooks, scripts, ...)     |
+---------------------------------------------------------------+
|                                                                |
|  +-----------+  +----------------+  +-----------------------+  |
|  | REST API  |  |    Services    |  |     Direct ORM        |  |
|  | (FastAPI) |  |                |  |      access           |  |
|  |           |  |  SyntaxService |  |                       |  |
|  | SDMX-like |  |  SemanticSvc   |  |  session.query(...)   |  |
|  | endpoints |  |  ASTGenerator  |  |  select(Model).where  |  |
|  |           |  |  ScopeCalc     |  |                       |  |
|  +-----------+  +----------------+  +-----------------------+  |
|        |                |                     |                |
|  +-----+----------------+---------------------+----------+     |
|  |                     ORM Layer                          |    |
|  |                                                        |    |
|  |  Models . Relationships . Views . Session Management   |    |
|  |  Multi-DB: SQLite / PostgreSQL / SQL Server            |    |
|  +------------------------------+------------------------+    |
|                                  |                             |
+----------------------------------+-----------------------------+
                                   |
                           +-------+--------+
                           |    Database    |
                           +----------------+
```

## Package Layout

```
src/dpmcore/
├── __init__.py            connect(), __version__
├── connection.py          DpmConnection
├── errors.py              Exception hierarchy
├── orm/
│   ├── base.py            DeclarativeBase, engine, session
│   ├── infrastructure.py  Concept, Organisation, Release, ...
│   ├── glossary.py        Category, Item, Property, Context, ...
│   ├── rendering.py       Table, TableVersion, Header, Cell, ...
│   ├── variables.py       Variable, VariableVersion, CompoundKey, ...
│   ├── operations.py      Operation, OperationVersion, Scope, ...
│   └── packaging.py       Framework, Module, ModuleVersion, ...
├── services/              read-only DPM dictionary services
│   ├── syntax.py          SyntaxService     (no DB)
│   ├── semantic.py        SemanticService
│   ├── ast_generator.py   ASTGeneratorService (engine-ready)
│   ├── scope_calculator.py ScopeCalculatorService
│   ├── data_dictionary.py DataDictionaryService
│   ├── explorer.py        ExplorerService
│   ├── hierarchy.py       HierarchyService
│   ├── dpm_xl.py          DpmXlService (facade)
│   ├── export_csv.py      ExportCsvService (Access → CSV)
│   ├── meili_build.py     MeiliBuildService (end-to-end pipeline)
│   └── meili_json.py      MeiliJsonService (JSON generation)
├── loaders/               data-loading (mutates the DB)
│   └── migration.py       MigrationService (Access import)
├── cli/
│   └── main.py            Click CLI (migrate, export-csv, build-meili-json, serve, generate-script)
└── dpm_xl/                DPM-XL engine internals
    ├── grammar/           ANTLR4 grammar + generated parser
    ├── ast/               AST nodes, visitor, operands
    ├── operators/         Arithmetic, comparison, boolean, ...
    ├── types/             Scalar, time, promotion
    ├── utils/             Serialization, scope calculator, ...
    └── model_queries.py   Query compatibility layer
```

## Development

```bash
# Install all dependencies (including dev tools)
poetry install --all-extras

# Run tests
poetry run pytest

# Linting and formatting
poetry run ruff check src/ tests/
poetry run ruff format src/ tests/

# Type checking
poetry run mypy src/
```

## License

Apache-2.0 — see [LICENSE](LICENSE) for details.
