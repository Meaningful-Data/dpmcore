# dpmcore Specification — Project Setup & Conventions

This document specifies the project setup, tooling, code quality standards,
testing infrastructure, documentation, and CI/CD pipeline for dpmcore. All
choices are aligned with [pysdmx](https://github.com/bis-med-it/pysdmx) to
maintain consistency across the MeaningfulData open-source ecosystem.

## 1. Project Layout

### 1.1 src-Layout

dpmcore adopts the **src-layout** (PEP 517/518 best practice), matching pysdmx:

```
dpmcore/
├── src/
│   └── dpmcore/
│       ├── __init__.py          # Public API: connect(), __version__
│       ├── py.typed             # PEP 561 type hint marker
│       ├── errors.py            # Exception hierarchy
│       ├── orm/                 # Layer 1 — ORM
│       ├── api/                 # Layer 2 — REST API
│       ├── services/            # Layer 3 — Services
│       ├── dpm_xl/              # DPM-XL engine internals
│       ├── django/              # Django integration app
│       ├── cli/                 # Command-line interface
│       └── exceptions/          # (legacy, migrate to errors.py)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── docs/
│   ├── conf.py
│   ├── index.rst
│   ├── start.rst
│   ├── api/
│   └── howto/
├── specification/               # This specification
├── pyproject.toml
├── poetry.toml
├── README.rst
├── CHANGELOG.rst
├── SECURITY.md
├── LICENSE
└── .gitignore
```

### 1.2 Rationale for src-Layout

The src-layout prevents accidental imports of the development version over the
installed version. It is the layout used by pysdmx, and it is the recommended
layout for modern Python packages (PEP 517).

### 1.3 Migration from Current Layout

The current codebase uses a flat layout (`py_dpm/` at root). Migration steps:

1. Create `src/dpmcore/` directory.
2. Move all source modules from `py_dpm/` into `src/dpmcore/`.
3. Rename the package from `py_dpm` to `dpmcore`.
4. Update all internal imports from `py_dpm.*` to `dpmcore.*`.
5. Add `py.typed` marker file to `src/dpmcore/`.
6. Update `pyproject.toml` to reflect the new layout.

## 2. Package Management — Poetry

### 2.1 pyproject.toml

The `pyproject.toml` is the single source of configuration for the project.
Following pysdmx, it uses PEP 621 `[project]` metadata combined with Poetry
tooling sections.

```toml
[project]
name = "dpmcore"
version = "1.0.0"
description = "Your opinionated Python DPM library"
license = { text = "Apache-2.0" }
readme = "README.rst"
requires-python = ">=3.10"
authors = [
    { name = "MeaningfulData S.L.", email = "info@meaningfuldata.eu" },
]
keywords = ["dpm", "dpm-xl", "data-point-model", "xbrl", "regulatory-reporting"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: Apache Software License",
    "Typing :: Typed",
]
dependencies = [
    "sqlalchemy>=2.0,<3.0",
    "antlr4-python3-runtime>=4.9.2,<4.9.3",
]

[project.urls]
homepage = "https://dpmcore.meaningfuldata.eu"
repository = "https://github.com/Meaningful-Data/dpmcore"
documentation = "https://meaningful-data.github.io/dpmcore"
"Bug Tracker" = "https://github.com/Meaningful-Data/dpmcore/issues"

[project.optional-dependencies]
server = ["fastapi>=0.100", "uvicorn[standard]>=0.20"]
django = ["django>=4.2"]
postgres = ["psycopg2-binary>=2.9,<3.0"]
sqlserver = ["pyodbc>=5.1,<5.2"]
data = ["pandas>=2.1.4"]
cli = ["click>=8.1", "rich>=13.7"]
all = [
    "fastapi>=0.100", "uvicorn[standard]>=0.20",
    "django>=4.2",
    "psycopg2-binary>=2.9,<3.0",
    "pyodbc>=5.1,<5.2",
    "pandas>=2.1.4",
    "click>=8.1", "rich>=13.7",
]

[project.scripts]
dpmcore = "dpmcore.cli.main:main"

[tool.poetry]
requires-poetry = ">=2.0"

[tool.poetry.dependencies]
python = ">=3.10,<4.0"

[tool.poetry.group.dev.dependencies]
coverage = ">=7.0,<8.0"
ruff = ">=0.13.2"
mypy = "^1.18.2"
pytest = "^8.3.2"
pytest-asyncio = "^0.21.1"
pytest-cov = "^4.0.0"
pyroma = "^4.2"

[tool.poetry.group.docs.dependencies]
sphinx = "^7.2.6"
sphinx-rtd-theme = "^1.3.0"
sphinx-autodoc-typehints = "^1.24.0"

[build-system]
requires = ["poetry-core>=1.0.0"]
build-backend = "poetry.core.masonry.api"
```

### 2.2 Key Decisions (Aligned with pysdmx)

| Decision | Choice | pysdmx Reference |
|----------|--------|-------------------|
| Build backend | `poetry-core` | Same |
| Metadata format | PEP 621 `[project]` table | Same |
| Python version | `>=3.10` | pysdmx uses `>=3.9`; dpmcore uses 3.10 for pattern matching |
| Version location | `pyproject.toml` + `src/dpmcore/__init__.py` | Same dual-location pattern |
| Optional deps | Grouped by feature (`server`, `django`, `data`, etc.) | Same extras pattern |
| Dev deps | Poetry dev group (not in `[project]`) | Same |
| Docs deps | Separate Poetry group `docs` | Same |

### 2.3 Core vs Optional Dependencies

Following pysdmx's minimal-core philosophy, dpmcore keeps its core dependency
set small. Only dependencies required for the base ORM and DPM-XL engine are
mandatory; everything else is optional.

**Core dependencies** (always installed):

| Package | Purpose | Rationale |
|---------|---------|-----------|
| `sqlalchemy>=2.0` | ORM layer | Fundamental to dpmcore |
| `antlr4-python3-runtime` | DPM-XL parsing | Fundamental to DPM-XL engine |

**Optional dependency groups**:

| Extra | Packages | When Needed |
|-------|----------|-------------|
| `server` | FastAPI, Uvicorn | Web application mode |
| `django` | Django | Django integration mode |
| `postgres` | psycopg2-binary | PostgreSQL backend |
| `sqlserver` | pyodbc | SQL Server backend |
| `data` | Pandas | DataFrame-based queries |
| `cli` | Click, Rich | Command-line interface |
| `all` | Everything above | Full installation |

### 2.4 poetry.toml

```toml
[virtualenvs]
in-project = true
```

This creates the `.venv` directory inside the project root, matching pysdmx.

## 3. Code Quality — Ruff

### 3.1 Ruff Configuration

dpmcore uses the same ruff rules as pysdmx:

```toml
[tool.ruff]
line-length = 79
lint.select = [
    "ASYNC", # flake8-async: async/await best practices
    "B",     # flake8-bugbear: detect bugs and design problems
    "C4",    # flake8-comprehensions: better comprehensions
    "C90",   # mccabe: code complexity checker
    "D",     # pydocstyle: enforce docstring conventions
    "DTZ",   # flake8-datetimez: datetime best practices
    "E",     # pycodestyle errors
    "ERA",   # eradicate: find commented-out code
    "F",     # pyflakes: detect various errors
    "FURB",  # refurb: functional improvements
    "I",     # isort: import sorting
    "LOG",   # flake8-logging: logging best practices
    "PERF",  # perflint: performance optimizations
    "PT",    # flake8-pytest-style: pytest best practices
    "S",     # flake8-bandit: security issues
    "SIM",   # flake8-simplify: code simplification
    "W",     # pycodestyle warnings
]
lint.ignore = ["D411", "E203", "F901"]
lint.mccabe.max-complexity = 10
lint.pydocstyle.convention = "google"

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["C901", "DTZ", "D100", "D103", "D104", "PERF", "S101", "S311"]
```

### 3.2 Key Rules Explained

| Rule Set | Purpose | Notes |
|----------|---------|-------|
| `D` (pydocstyle) | Google-style docstrings on all public modules, classes, and functions | Convention: `"google"` |
| `I` (isort) | Consistent import ordering | 3 groups: stdlib, third-party, local |
| `C90` (mccabe) | Complexity ceiling of 10 | Keeps functions readable |
| `S` (bandit) | Security scanning | Relaxed in tests (`S101` for `assert`) |
| `PT` (pytest) | Pytest idioms | Relaxed in tests for docstrings |
| `ERA` (eradicate) | Remove commented-out code | Keeps codebase clean |

### 3.3 Line Length

**79 characters**, matching pysdmx and strict PEP 8. This is intentionally
conservative to ensure readability in split-pane editors and code review tools.

### 3.4 Running Ruff

```bash
# Check formatting compliance
poetry run ruff format --no-cache --check

# Auto-format
poetry run ruff format

# Lint check
poetry run ruff check --output-format=github

# Lint with auto-fix
poetry run ruff check --fix
```

## 4. Code Quality — mypy

### 4.1 mypy Configuration

dpmcore uses **strict mode**, matching pysdmx:

```toml
[tool.mypy]
files = "src"
disallow_untyped_defs = true
disallow_untyped_calls = true
ignore_errors = false
no_implicit_optional = true
show_column_numbers = true
strict_equality = true
strict_optional = true
strict = true
enable_error_code = [
    "redundant-expr",
    "truthy-bool",
]
warn_return_any = false
```

### 4.2 PEP 561 Compliance

The `src/dpmcore/py.typed` marker file declares that dpmcore ships inline type
stubs. Downstream consumers using mypy will type-check their dpmcore usage.

### 4.3 Type Hint Conventions

Following pysdmx patterns:

```python
# Use typing module types for Python 3.10 compatibility
from typing import Optional, Sequence, Union

# Optional for nullable fields
valid_from: Optional[datetime] = None

# Sequence for immutable collections (not List)
items: Sequence[Item] = ()

# Union for polymorphic types
agency: Union[str, Agency] = ""

# Never use X | Y syntax (requires 3.10+ in annotations only with
# `from __future__ import annotations`, but pysdmx avoids it)
```

### 4.4 Running mypy

```bash
poetry run mypy --show-error-codes --pretty
```

## 5. Docstring Conventions

### 5.1 Google Style (Enforced by Ruff)

All public modules, classes, and functions must have Google-style docstrings.
This is enforced by the `D` rule set with `lint.pydocstyle.convention = "google"`.

### 5.2 Module-Level Docstrings

Every `.py` file starts with a module-level docstring:

```python
"""ORM models for the DPM Glossary domain.

This module defines the SQLAlchemy models for Categories, Items,
SubCategories, Properties, and Contexts.
"""
```

### 5.3 Class Docstrings

Classes have a summary line, optional elaboration, and an `Attributes:` section:

```python
class Category(Base):
    """A classification scheme grouping related items.

    Categories are the fundamental organizational unit in the DPM
    glossary, analogous to SDMX Codelists.

    Attributes:
        id: The unique identifier for the category.
        code: The category code (e.g. "MC" for Main Category).
        label: Human-readable name.
        description: Optional longer description.
        items: The items belonging to this category.
    """
```

### 5.4 Method Docstrings

Methods use `Args:`, `Returns:`, and `Raises:` sections:

```python
def get_table_by_code(
    self,
    code: str,
    release_code: Optional[str] = None,
) -> TableInfo:
    """Retrieve a table by its code.

    Args:
        code: The table code (e.g. "T_01.00").
        release_code: Optional release filter. When provided,
            only the version active in that release is returned.

    Returns:
        The table information including headers and cells.

    Raises:
        NotFound: If no table matches the given code.
    """
```

### 5.5 Inline Field Docstrings

For dataclasses and Structs with complex fields, inline docstrings (string
literal after each field) are acceptable as an alternative to `Attributes:`:

```python
@dataclass(frozen=True)
class SyntaxValidationResult:
    """Result of a DPM-XL syntax validation."""

    is_valid: bool
    """Whether the expression is syntactically valid."""

    errors: Sequence[SyntaxError] = ()
    """List of syntax errors found, empty if valid."""
```

## 6. Error Handling

### 6.1 Exception Hierarchy

Following pysdmx's structured error hierarchy:

```python
"""Exception classes for dpmcore."""

from typing import Any, Dict, Optional


class DpmCoreError(Exception):
    """Base exception for all dpmcore errors.

    Attributes:
        title: Short error summary.
        description: Detailed explanation.
        csi: Contextual supplementary information.
    """

    def __init__(
        self,
        title: str,
        description: Optional[str] = None,
        csi: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.title = title
        self.description = description
        self.csi = csi
        msg = f"{title}: {description}" if description else title
        super().__init__(msg)


class Invalid(DpmCoreError):
    """Bad request or invalid input."""


class NotFound(DpmCoreError):
    """Requested resource does not exist."""


class InternalError(DpmCoreError):
    """Internal processing error."""


class ConfigurationError(DpmCoreError):
    """Invalid or missing configuration."""


class SyntaxValidationError(DpmCoreError):
    """DPM-XL syntax validation failure."""


class SemanticValidationError(DpmCoreError):
    """DPM-XL semantic validation failure."""


class MigrationError(DpmCoreError):
    """Database migration failure."""
```

### 6.2 Error Conventions

| Convention | Description |
|------------|-------------|
| Structured errors | All errors carry `title`, `description`, and optional `csi` |
| Single module | All errors defined in `src/dpmcore/errors.py` |
| No bare `Exception` | Always raise a specific `DpmCoreError` subclass |
| Validation errors | Raised in `__post_init__` hooks for data integrity |

## 7. Import Conventions

### 7.1 Import Order (Enforced by Ruff `I`)

```python
# 1. Standard library
from datetime import datetime
from typing import Optional, Sequence

# 2. Third-party packages
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

# 3. Local package
from dpmcore.errors import Invalid, NotFound
from dpmcore.orm.base import Base
```

Each group separated by a blank line. Within each group, imports are sorted
alphabetically.

### 7.2 Public API Exposure

Following pysdmx's pattern:

- **Top-level `__init__.py`** is minimal:

```python
"""Your opinionated Python DPM library."""

__version__ = "1.0.0"
```

- **Subpackage `__init__.py`** files are minimal (just a docstring).

- **Public API surface** is exposed via re-exports in key `__init__.py` files
  with explicit `__all__` lists.

## 8. Testing — pytest

### 8.1 Configuration

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "unit: unit tests (no DB, fast)",
    "integration: integration tests (require DB)",
    "api: REST API tests",
    "django: Django integration tests",
]
addopts = "-v --tb=short --strict-markers --strict-config"
```

### 8.2 Test Organisation

Tests mirror the source structure:

```
tests/
├── conftest.py              # Shared fixtures, marker auto-assignment
├── unit/
│   ├── orm/
│   │   ├── test_glossary.py
│   │   ├── test_rendering.py
│   │   ├── test_variables.py
│   │   └── test_operations.py
│   ├── services/
│   │   ├── test_syntax.py
│   │   ├── test_semantic.py
│   │   └── test_ast_generator.py
│   └── api/
│       └── test_routes.py
├── integration/
│   ├── test_queries.py
│   ├── test_migration.py
│   └── test_scopes.py
└── __init__.py
```

### 8.3 Test Style (Matching pysdmx)

Tests are **purely functional** — no test classes. Fixtures define reusable
data. Assertions use plain `assert` statements.

```python
"""Tests for Category ORM model."""

import pytest

from dpmcore.orm.glossary import Category


@pytest.fixture
def code() -> str:
    return "MC"


@pytest.fixture
def label() -> str:
    return "Main Category"


def test_default(code: str) -> None:
    c = Category(code=code)
    assert c.code == code
    assert c.label is None


def test_full(code: str, label: str) -> None:
    c = Category(code=code, label=label)
    assert c.code == code
    assert c.label == label
```

### 8.4 Coverage

Following pysdmx, dpmcore targets **100% branch coverage** for all new code:

```toml
[tool.coverage.run]
branch = true
source = ["src/dpmcore"]

[tool.coverage.report]
fail_under = 100
show_missing = true
skip_covered = true
```

Coverage is enforced in CI:

```bash
poetry run pytest \
    --cov=dpmcore \
    --cov-branch \
    --cov-report=term-missing \
    --verbose --tb=short \
    --strict-markers --strict-config \
    --durations=10 \
    tests/

poetry run coverage report \
    --fail-under=100 \
    --show-missing \
    --skip-covered
```

### 8.5 Auto-Marking via conftest.py

Following pysdmx's pattern, `conftest.py` auto-assigns markers based on test
file paths:

```python
"""Shared fixtures and marker auto-assignment."""

import pytest

PATH_RULES = [
    ("tests/unit/", "unit"),
    ("tests/integration/", "integration"),
    ("tests/unit/api/", "api"),
]


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Auto-assign markers based on test file paths."""
    for item in items:
        path = str(item.fspath)
        for prefix, marker_name in PATH_RULES:
            if prefix in path:
                item.add_marker(getattr(pytest.mark, marker_name))
```

## 9. Documentation — Sphinx

### 9.1 Setup

Sphinx with the Read the Docs theme, matching pysdmx exactly:

```
docs/
├── conf.py
├── index.rst
├── start.rst
├── api/
│   ├── orm.rst
│   ├── services.rst
│   ├── rest_api.rst
│   └── cli.rst
├── howto/
│   ├── standalone.rst
│   ├── web_app.rst
│   ├── django.rst
│   └── migration.rst
├── Makefile
└── make.bat
```

### 9.2 Sphinx Configuration

```python
"""Sphinx configuration."""

import os
import sys

package_path = os.path.abspath("../src")
sys.path.insert(0, package_path)
os.environ["PYTHONPATH"] = ";".join(
    (package_path, os.environ.get("PYTHONPATH", ""))
)

project = "dpmcore"
copyright = "2025, MeaningfulData"
author = "MeaningfulData"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_rtd_theme",
    "sphinx_autodoc_typehints",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
```

### 9.3 Extensions

| Extension | Purpose | pysdmx |
|-----------|---------|--------|
| `sphinx.ext.autodoc` | Auto-generate API docs from docstrings | Yes |
| `sphinx.ext.napoleon` | Parse Google-style docstrings | Yes |
| `sphinx_rtd_theme` | Read the Docs HTML theme | Yes |
| `sphinx_autodoc_typehints` | Render type hints in docs | Yes |

### 9.4 Documentation Format

Following pysdmx, use **reStructuredText** (`.rst`) for README, CHANGELOG,
and all Sphinx documentation. This ensures native Sphinx compatibility without
extra parsers.

### 9.5 Building Documentation

```bash
# Install docs dependencies
poetry install --with docs

# Build HTML
cd docs && make html

# Or directly
poetry run sphinx-build -b html docs docs/_build/html
```

## 10. CI/CD — GitHub Actions

### 10.1 CI Workflow (`.github/workflows/ci.yml`)

Matches pysdmx's pipeline: format check, lint, type check, test, coverage.

```yaml
name: Build

on:
  push:
    branches: ["develop", "main"]
  pull_request:
    branches: ["develop", "main"]

permissions:
  contents: read

jobs:
  build:
    runs-on: ${{ matrix.os }}

    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ["3.10", "3.11", "3.12", "3.13"]
      fail-fast: false

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install poetry
        run: pipx install --python ${{ matrix.python-version }} poetry
      - name: Install dependencies
        run: poetry install --all-extras
      - name: Check compliance with code formatting guidelines
        run: poetry run ruff format --no-cache --check
      - name: Run lint checks
        run: poetry run ruff check --output-format=github
      - name: Run type checks
        run: poetry run mypy --show-error-codes --pretty
      - name: Run tests
        run: >-
          poetry run pytest
          --cov=dpmcore --cov-branch --cov-report=term-missing
          --verbose --tb=short
          --strict-markers --strict-config
          --durations=10 tests/
      - name: Check coverage
        run: >-
          poetry run coverage report
          --fail-under=100 --show-missing --skip-covered
```

### 10.2 CD Workflow (`.github/workflows/cd.yml`)

```yaml
name: Publish package

on:
  release:
    types: [published]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  release:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Install poetry
        run: pipx install poetry
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - name: Build package
        run: poetry build
      - name: Publish to PyPI
        run: >-
          poetry publish
          --username=__token__
          --password=${{ secrets.PYPI_TOKEN }}
```

### 10.3 Documentation Workflow (`.github/workflows/sphinx.yml`)

```yaml
name: Documentation

on:
  push:
    branches: ["main"]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install poetry
        run: pipx install poetry
      - name: Install dependencies
        run: poetry install --all-extras --with docs
      - name: Build documentation
        run: poetry run sphinx-build -b html docs docs/_build/html
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: docs/_build/html

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}

    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

### 10.4 CI Pipeline Order

The CI pipeline runs checks in a strict order, matching pysdmx:

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `ruff format --check` | Formatting compliance |
| 2 | `ruff check` | Linting (style, bugs, security, complexity) |
| 3 | `mypy` | Type checking (strict mode) |
| 4 | `pytest --cov` | Tests with branch coverage |
| 5 | `coverage report --fail-under=100` | 100% coverage enforcement |

This order ensures fast failures: formatting issues fail in seconds before
running the full test suite.

## 11. Version Management

### 11.1 Dual-Location Version

Version is maintained in two locations that must stay synchronized:

1. `pyproject.toml`: `version = "1.0.0"`
2. `src/dpmcore/__init__.py`: `__version__ = "1.0.0"`

### 11.2 Changelog

Use `CHANGELOG.rst` in reStructuredText format. For each release, document
changes in categories: Added, Changed, Fixed, Removed. Alternatively, delegate
to GitHub Releases page (as pysdmx does).

### 11.3 Versioning Scheme

Follow [Semantic Versioning 2.0](https://semver.org/):

- **MAJOR**: Breaking API changes
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, backward compatible

## 12. Model Conventions

### 12.1 ORM Models (SQLAlchemy 2.0)

All ORM models use SQLAlchemy 2.0 declarative style with full type annotations:

```python
"""ORM models for the DPM Glossary domain."""

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dpmcore.orm.base import Base


class Category(Base):
    """A classification scheme grouping related items.

    Attributes:
        id: The unique database identifier.
        code: The category code.
        label: Human-readable name.
        items: The items belonging to this category.
    """

    __tablename__ = "tCategory"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50))
    label: Mapped[Optional[str]] = mapped_column(String(255), default=None)

    items: Mapped[Sequence["Item"]] = relationship(
        back_populates="category",
        default_factory=list,
    )
```

### 12.2 Service Result Types

Service methods return **frozen dataclasses** (not dicts), matching pysdmx's
preference for typed return values:

```python
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class SyntaxValidationResult:
    """Result of a DPM-XL syntax validation.

    Attributes:
        is_valid: Whether the expression is syntactically valid.
        errors: List of syntax errors, empty if valid.
        expression: The original expression.
    """

    is_valid: bool
    errors: Sequence["SyntaxError"] = ()
    expression: str = ""
```

### 12.3 Enums

Enums use `(str, Enum)` dual inheritance for serialization compatibility:

```python
from enum import Enum


class Severity(str, Enum):
    """Validation severity level."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    def __str__(self) -> str:
        """Return the enum value as string."""
        return self.value
```

## 13. Project Files

### 13.1 README.rst

Use reStructuredText format (matching pysdmx), not Markdown. The README should
include:

1. Project name and tagline
2. Badges (CI status, coverage, PyPI version, Python versions, license)
3. Installation instructions
4. Quick start example
5. Links to documentation
6. Contributing guidelines reference
7. License

### 13.2 SECURITY.md

Document the security policy, matching pysdmx's practice.

### 13.3 LICENSE

Apache-2.0 license file.

### 13.4 .gitignore

Standard Python `.gitignore` plus:

```
# Poetry
.venv/
poetry.lock  # (or track it — see decision below)

# IDE
.idea/
.vscode/
*.swp

# Build
dist/
*.egg-info/

# Coverage
.coverage
htmlcov/

# Documentation
docs/_build/

# Environment
.env
*.db
```

**Decision**: Track `poetry.lock` in version control (recommended for
applications; pysdmx does not track it as a library).

## 14. Development Workflow

### 14.1 Setup

```bash
# Clone the repository
git clone https://github.com/Meaningful-Data/dpmcore.git
cd dpmcore

# Install all dependencies (including dev and docs)
poetry install --all-extras --with docs

# Verify setup
poetry run ruff format --check
poetry run ruff check
poetry run mypy --show-error-codes --pretty
poetry run pytest
```

### 14.2 Pre-Commit Checks

Before committing, run the full quality pipeline:

```bash
poetry run ruff format --no-cache --check
poetry run ruff check --output-format=github
poetry run mypy --show-error-codes --pretty
poetry run pytest --cov=dpmcore --cov-branch tests/
```

### 14.3 Branch Strategy

- `main` — stable releases
- `develop` — integration branch
- Feature branches from `develop`
- PRs require CI to pass before merge

## 15. Migration Checklist

Summary of changes needed to align the current `py_dpm` codebase with this
specification:

### 15.1 Project Structure

- [ ] Adopt src-layout: `py_dpm/` → `src/dpmcore/`
- [ ] Rename package: `py_dpm` → `dpmcore`
- [ ] Add `src/dpmcore/py.typed` marker file
- [ ] Move README from `.md` to `.rst` format
- [ ] Add `CHANGELOG.rst`
- [ ] Add `SECURITY.md`

### 15.2 pyproject.toml

- [ ] Switch build backend from `setuptools` to `poetry-core`
- [ ] Use PEP 621 `[project]` metadata format
- [ ] Restructure dependencies: core minimal, rest as optional extras
- [ ] Add ruff configuration (full rule set from section 3.1)
- [ ] Add mypy strict configuration (section 4.1)
- [ ] Add pytest configuration with markers (section 8.1)
- [ ] Add coverage configuration (section 8.4)
- [ ] Add dev dependencies: ruff, mypy, coverage, pyroma
- [ ] Add docs dependencies: sphinx, sphinx-rtd-theme, sphinx-autodoc-typehints

### 15.3 Code Quality

- [ ] Run `ruff format` across entire codebase
- [ ] Fix all `ruff check` violations
- [ ] Add Google-style docstrings to all public modules, classes, functions
- [ ] Add type hints to all function signatures
- [ ] Achieve mypy strict compliance
- [ ] Consolidate exceptions into `src/dpmcore/errors.py`

### 15.4 Testing

- [ ] Upgrade pytest to 8.x
- [ ] Add pytest markers (unit, integration, api, django)
- [ ] Add auto-marker assignment in `conftest.py`
- [ ] Add coverage configuration targeting 100%
- [ ] Add strict pytest config (`--strict-markers --strict-config`)

### 15.5 CI/CD

- [ ] Replace `main.yml` and `release.yml` with `ci.yml` and `cd.yml`
- [ ] Add multi-OS, multi-Python matrix to CI
- [ ] Add format, lint, type check, test, coverage steps
- [ ] Add documentation build and deployment workflow
- [ ] Enforce 100% coverage in CI

### 15.6 Documentation

- [ ] Set up Sphinx with Read the Docs theme
- [ ] Create `docs/conf.py` with autodoc, napoleon, typehints extensions
- [ ] Create `docs/index.rst` with toctree
- [ ] Create API reference pages (one per module)
- [ ] Create how-to guides for each usage mode
- [ ] Add documentation CI workflow for GitHub Pages

### 15.7 SQLAlchemy Upgrade

- [ ] Upgrade from SQLAlchemy 1.4 to 2.0+
- [ ] Replace `Column()` with `mapped_column()`
- [ ] Replace `relationship()` types with `Mapped[...]`
- [ ] Replace `DeclarativeBase` with modern declarative
- [ ] Replace global session with explicit `SessionFactory`

## 16. Differences from pysdmx

While dpmcore follows pysdmx conventions closely, the following intentional
differences exist:

| Aspect | pysdmx | dpmcore | Rationale |
|--------|--------|---------|-----------|
| Python version | `>=3.9` | `>=3.10` | Pattern matching, modern unions |
| Model library | `msgspec.Struct` | `sqlalchemy` + `dataclass` | ORM requirement |
| HTTP client | `httpx` | Not needed (server-side) | dpmcore is a server/library, not a client |
| HTTP server | None | `fastapi` (optional) | REST API mode |
| Serialization | `msgspec` | `dataclass` + custom | Different data layer |
| README format | `.rst` | `.rst` (to be migrated from `.md`) | Alignment with pysdmx |
| License | Apache-2.0 | Apache-2.0 (to be changed from GPL-3.0) | Alignment with pysdmx |
