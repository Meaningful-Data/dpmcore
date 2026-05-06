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
        release_code="4.2.1",       # or release_id=<int>
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
        severity="warning",                # global default (default: "warning")
        severities={"v0002": "error"},     # per-validation override
        release="4.2",                     # optional; latest available if omitted
    )
    # script["enriched_ast"] is keyed by the resolved module URI:
    #   {namespace_uri: {module_code, module_version, framework_code,
    #                    dpm_release, dates, operations, variables, tables,
    #                    preconditions, precondition_variables,
    #                    dependency_information, dependency_modules}}
    namespace, ns_block = next(iter(script["enriched_ast"].items()))
    print(ns_block["dpm_release"])      # {"release": "...", "publication_date": "..."}
    print(ns_block["operations"])       # {validation_code: {ast, severity, ...}}
    print(ns_block["dependency_modules"])
```

`preconditions`, `severities` and `release` are all optional. Severity
resolution per validation is `severities.get(code, severity)`; values
must be one of `error`, `warning`, `info` (case-insensitive). Codes in
`severities` that are not present in `expressions` raise `ValueError`.
When `release` is omitted, dpmcore resolves the latest release whose
window contains the requested ``(module_code, module_version)`` and
embeds it in the resulting `dpm_release` block.

The same script generation is exposed via the CLI and the REST API.
The CLI input file mirrors the Python shape:

```json
{
    "expressions": [
        ["{tC_01.00, r0100, c0010} = {tC_01.00, r0200, c0010}", "v0001"]
    ],
    "preconditions": [
        ["{is_reporting_entity}", ["v0001"]]
    ],
    "severities": {"v0001": "error"}
}
```

```bash
dpmcore generate-script \
    --expressions ./rules.json \
    --module-code COREP_Con --module-version 2.0.1 \
    --severity warning --release 4.2 \
    --database sqlite:///dpm.db --output ./script.json
```

```bash
curl -X POST http://localhost:8000/api/v1/scripts \
    -H 'content-type: application/json' \
    -d '{
          "expressions":[["{tC_01.00, r0100, c0010} = {tC_01.00, r0200, c0010}","v0001"]],
          "preconditions":[{"expression":"{is_reporting_entity}","validation_codes":["v0001"]}],
          "severities":{"v0001":"error"},
          "release":"4.2",
          "module_code":"COREP_Con",
          "module_version":"2.0.1"
        }'
```

**Data dictionary queries:**

Release-aware methods accept `release_id` (integer ID) or
`release_code` (semver string like `"4.2.1"`). At most one may be
supplied; passing both raises `ValueError`.

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    dd = db.services.data_dictionary

    releases = dd.get_releases()
    tables   = dd.get_tables(release_code="4.2.1")
    items    = dd.get_all_item_signatures(release_code="4.2.1")
    table    = dd.get_table_version("C_01.00", release_code="4.2.1")
    cats     = dd.get_item_categories(release_code="4.2.1")
```

**Operation scope calculation:**

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    result = db.services.scope_calculator.calculate_from_expression(
        expression="{tC_01.00, r0100, c0010} = {tC_01.00, r0200, c0010}",
        release_code="4.2.1",       # or release_id=<int>
    )
    print(result.total_scopes)
    print(result.module_versions)
```

**Explorer — reverse lookups:**

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    explorer = db.services.explorer

    var = explorer.get_variable_by_code("mi123", release_code="4.2.1")
    usage = explorer.get_variable_usage(variable_vid=99,
                                        release_code="4.2.1")
    tables = explorer.search_table("C_01", release_code="4.2.1")
```

**Hierarchy — framework / module / table tree:**

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    hierarchy = db.services.hierarchy

    # Flat framework rows (default) — active releases only
    frameworks = hierarchy.get_all_frameworks()

    # Deep tree: framework -> module_versions -> table_versions
    tree       = hierarchy.get_all_frameworks(deep=True)

    # Filter by release code — preferred over numeric release_id since
    # IDs became opaque from DPM 4.2.1 onwards (e.g. release "4.2.1"
    # has ReleaseID=1010000003, not 6).
    by_code    = hierarchy.get_all_frameworks(
        deep=True, release_code="4.2.1"
    )

    # Filter by business date — resolves via ModuleVersion validity range
    today_tree = hierarchy.get_all_frameworks(deep=True, date="2025-06-30")

    module     = hierarchy.get_module_version("F_01.01", release_code="4.2")
    tables     = hierarchy.get_tables_for_module(
        "F_01.01", release_code="4.2"
    )
    details    = hierarchy.get_table_details(
        "tC_01.00", release_code="4.2"
    )

    # Per-header modelling metadata (main property + context property/item)
    modelling  = hierarchy.get_table_modelling(
        "tC_01.00", release_code="4.2"
    )
```

`get_all_frameworks`, `get_table_details`, and `get_table_modelling`
accept up to one of `release_id` / `release_code` / `date`;
`get_module_version` and `get_tables_for_module` accept `release_id`
or `release_code` only (no `date`). Passing more than one raises
`ValueError`, and an unknown `release_code` also raises. When no
filter is supplied, `get_module_version` and `get_all_frameworks`
fall back to the currently-active (`end_release_id IS NULL`) module
versions, so results stay deterministic when a module has been
republished across releases.

> **How range comparisons work.** From DPM **4.2.1** onwards EBA
> assigns opaque `ReleaseID` values (`4.2.1` is `1010000003`, while
> older releases are still 1..5). dpmcore therefore compares ranges
> against `Release.sort_order` — a synthetic integer derived from the
> parsed semver `code` and auto-populated by an ORM listener
> (backfilled by `MigrationService` after bulk loads). This means
> both forms work correctly: `release_id=1010000003` and
> `release_code="4.2.1"` resolve identically, and a hypothetical
> backport like `4.0.1` shipped after `4.2.1` is correctly placed
> inside the `4.0` lineage. Prefer `release_code` for human input
> because the codes are readable; `release_id` is for cases where
> you already have the resolved integer in hand.

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

**Export table layouts** (Excel):

Export annotated table layouts to ``.xlsx`` for review or distribution.
You can export all tables in a module, or a specific list of tables.

```python
from dpmcore import connect
from dpmcore.services.layout_exporter.models import ExportConfig

config = ExportConfig(
    annotate=True,
    add_cell_comments=True,
    add_header_comments=True,
)

with connect("sqlite:///dpm.db") as db:
    svc = db.services.layout_exporter

    # Whole module
    svc.export_module("FINREP9", release_code="4.2", output_path="finrep9.xlsx",
                      config=config)

    # Specific tables
    svc.export_tables(["F_01.01", "F_01.02"], release_code="4.2",
                      output_path="finrep_subset.xlsx", config=config)
```

Or from the command line:

```bash
# Whole module
dpmcore export-layout --database sqlite:///dpm.db \
    --module FINREP9 --release 4.2 --output finrep9.xlsx

# Specific tables
dpmcore export-layout --database sqlite:///dpm.db \
    --tables F_01.01,F_01.02 --release 4.2 --output finrep_subset.xlsx
```

Use ``--no-annotate`` or ``--no-comments`` to disable annotations/comments.

**Unified facade:**

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    dpm_xl = db.services.dpm_xl

    dpm_xl.validate_syntax("{tC_01.00, r0100, c0010}")
    dpm_xl.validate_semantic(
        "{tC_01.00, r0100, c0010}", release_code="4.2.1",
    )
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
│   ├── meili_json.py      MeiliJsonService (JSON generation)
│   └── layout_exporter/   LayoutExporterService (tables → .xlsx)
├── loaders/               data-loading (mutates the DB)
│   └── migration.py       MigrationService (Access import)
├── cli/
│   └── main.py            Click CLI (migrate, export-csv, build-meili-json, serve, generate-script, export-layout)
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
