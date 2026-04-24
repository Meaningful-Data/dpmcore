# dpmcore - AI Coding Assistant Instructions

## Project Overview

dpmcore is a Python library implementing the DPM (Data Point Model) 2.0 Refit standard for regulatory reporting. It provides an ORM, services layer, REST API, Django integration, and CLI that can be used independently or together.

- **DPM 2.0 Refit specification**: <https://www.eba.europa.eu/risk-and-data-analysis/reporting-frameworks/dpm-data-dictionary>
- **Documentation**: <https://docs.dpmcore.meaningfuldata.eu>

## Core Architecture

### Layered Design

```
Consumer applications (Django, CLI, scripts, notebooks)
    │
    ├── REST API (FastAPI, optional)       — src/dpmcore/api/
    ├── Services layer                      — src/dpmcore/services/
    └── Direct ORM access                   — src/dpmcore/orm/
            │
            └── DPM-XL engine internals     — src/dpmcore/dpm_xl/
```

### Packages

- `src/dpmcore/orm/` — SQLAlchemy 2.0 declarative models (Concept, Release, Framework, Module, Table, Variable, Operation, ...). Multi-backend: SQLite, PostgreSQL, SQL Server.
- `src/dpmcore/services/` — Stateless services returning frozen dataclasses: `SyntaxService`, `SemanticService`, `ASTGeneratorService` (three levels), `ScopeCalculatorService`, `DataDictionaryService`, `ExplorerService`, `HierarchyService`, `DpmXlService` (facade), `MigrationService` (Access → DPM DB).
- `src/dpmcore/dpm_xl/` — DPM-XL parser/engine: ANTLR4 grammar, AST nodes and visitor, operators (arithmetic, comparison, boolean, …), type system.
- `src/dpmcore/cli/` — Click-based CLI (`dpmcore migrate`, `dpmcore serve`, …).
- `src/dpmcore/django/` — Django integration app (models, admin, management commands, URL-mountable views).

### Parser Pipeline (ANTLR → AST → Interpreter)

1. **Lexing / parsing** (`src/dpmcore/dpm_xl/grammar/`): ANTLR4-generated lexer/parser. **DO NOT hand-edit** generated files — change the `.g4` and regenerate with `antlr4 -Dlanguage=Python3 -visitor`.
2. **AST construction** (`src/dpmcore/dpm_xl/ast/`): Visitor pattern transforms parse tree to typed AST nodes.
3. **Services** consume the AST (syntax validation, semantic enrichment against the ORM, scope calculation, script generation).

## Public API

The `connect()` factory is the main entry point:

```python
from dpmcore import connect

with connect("sqlite:///dpm.db") as db:
    db.services.syntax.validate("{tC_01.00, r0100, c0010}")
    db.services.semantic.validate(..., release_id=5)
    db.services.ast_generator.script(..., release_id=5, module_code="F_01.01")
```

## Code Quality (mandatory before every commit)

```bash
poetry run ruff format src/ tests/
poetry run ruff check --fix src/ tests/
poetry run mypy src/
```

All errors from `ruff format` and `ruff check` MUST be fixed before committing.

### Ruff Rules

- Max line length: **79** (conservative, matches strict PEP 8)
- Max complexity: **10**
- Docstring convention: **google**
- Broad rule set: `ASYNC, B, C4, C90, D, DTZ, E, ERA, F, FURB, I, LOG, PERF, PT, S, SIM, W`

### Mypy

- Strict mode for `src/`
- All functions MUST have type annotations
- No implicit optionals

## Testing

Tests use pytest markers declared in `pyproject.toml`:

- `unit` — no DB, fast
- `integration` — requires a real DB
- `api` — REST API tests
- `django` — Django integration tests

Run with coverage enforcement (100% branch coverage is mandatory):

```bash
poetry run pytest \
    --cov=dpmcore --cov-branch --cov-report=term-missing \
    --strict-markers --strict-config tests/
poetry run coverage report --fail-under=100 --show-missing --skip-covered
```

## Error Handling

Exception hierarchy lives in `src/dpmcore/errors.py`:

- `DpmCoreError` — base, carries `title`, `description`, optional `csi`
- `Invalid` — bad input / validation failure
- `NotFound` — missing resource
- `InternalError` — unexpected internal failure
- `ConfigurationError` — invalid or missing configuration
- `SyntaxValidationError`, `SemanticValidationError` — DPM-XL validation failures
- `MigrationError` — migration pipeline failure

Never raise bare `Exception`. Always raise a specific `DpmCoreError` subclass.

## Documentation

Sphinx-based documentation published at <https://docs.dpmcore.meaningfuldata.eu>.

- `docs/index.rst` — Main entry point and toctree
- `docs/guide/` — User guide (installation, quickstart, migration)
- `docs/api/` — API reference (autodoc)
- `docs/cli.rst` — CLI reference
- `docs/conf.py` — Sphinx config (theme: `sphinx_rtd_theme`, versioning: `sphinx-multiversion`)

Build docs locally:

```bash
poetry install --with docs
poetry run sphinx-build -b html docs docs/_build/html
```

## Git Workflow

### Branch Naming

- Issue branches: `cr-{issue_number}` (e.g., `cr-42` for issue #42)
- Version bump branches: `bump-version-{version}` (e.g., `bump-version-0.2.0`)

### Workflow

1. Create branch: `git checkout -b cr-{issue_number}`
2. Make changes with descriptive commits
3. Run all quality checks (ruff format, ruff check, mypy, pytest)
4. Push and create draft PR: `gh pr create --draft --title "Fix #{issue_number}: Description"`
5. Never add the PR to a milestone

### Issue Conventions

- Always follow the issue templates in `.github/ISSUE_TEMPLATE/` — do not create issues with free-form bodies
- Always set the issue type: `Bug`, `Feature`, or `Task`
- Only apply labels for cross-cutting concerns: `documentation`, `workflows`, `dependencies`, `optimization`, `question`, `help wanted`
- Never create new labels — only use the existing set listed above
- Include a self-contained reproduction script where possible (using `connect()` and an in-memory SQLite DB if practical)
- Use GitHub callout syntax for notes/warnings in issue descriptions:
  - `> [!NOTE]` for informational notes
  - `> [!IMPORTANT]` for critical information
  - `> [!WARNING]` for potential pitfalls or breaking changes

### Pull Request Descriptions

- Always follow the template in `.github/PULL_REQUEST_TEMPLATE.md`
- Focus on what changed, why, impact/risk, and notes
- Always include a closing keyword linking to the related issue (e.g., `Fixes #123`, `Closes #456`, `Resolves #789`)

## Version Management

Version is maintained in `pyproject.toml` (`[project].version`). When bumping, create a branch named `bump-version-{version}` from `origin/master` and open a PR with no body.

## External Dependencies

- **sqlalchemy** (2.x): ORM layer
- **antlr4-python3-runtime** (4.9.2): DPM-XL parser runtime
- Optional: `fastapi`, `django`, `pandas`, `click`, `rich`, `psycopg2-binary`, `pyodbc` — see `[project.optional-dependencies]` in `pyproject.toml`

## Common Pitfalls

1. **Never edit ANTLR-generated files** — change the `.g4` grammar and regenerate.
2. **Identifiers cannot be nullable** in DPM models; measures can.
3. **ANTLR version** — Must use 4.9.2 to match the `antlr4-python3-runtime` pin.
4. **SQL Server driver** — `pyodbc` requires the Microsoft ODBC Driver 17+ installed on the host.
5. **Version updates** — update the version in `pyproject.toml`. Create a new branch `bump-version-{version}` from `origin/master`.
