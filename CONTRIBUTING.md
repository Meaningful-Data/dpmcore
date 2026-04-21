# Contributing to dpmcore

Thanks for your interest in contributing! This guide covers the basics to get you productive quickly.

## Getting Started
- Use Python 3.10+.
- Install dependencies with poetry:
  ```bash
  poetry install --all-extras
  ```
- Activate the virtual environment:
  ```bash
  poetry shell
  ```

## Development Workflow
1) Branch from `master` and use a descriptive branch name.
2) Make changes with tests and type hints in mind.
3) Run mandatory quality checks (must pass before any commit/PR):
   ```bash
   poetry run ruff format src/ tests/
   poetry run ruff check --fix src/ tests/
   poetry run mypy src/
   ```
4) Run the full test suite with coverage (must hit 100% before finishing an issue/PR):
   ```bash
   poetry run pytest \
       --cov=dpmcore --cov-branch --cov-report=term-missing \
       --strict-markers --strict-config tests/
   poetry run coverage report --fail-under=100 --show-missing --skip-covered
   ```
5) Keep diffs small and focused; include relevant test updates/data fixtures where needed.

## Project Conventions
- `dpmcore` follows a layered architecture: ORM (SQLAlchemy 2.0) → Services → REST API (FastAPI) / Django integration / CLI (Click). See [README.md](README.md) for the layout.
- DPM-XL grammar lives in `src/dpmcore/dpm_xl/grammar/`; regenerate via `antlr4 -Dlanguage=Python3 -visitor` against the `.g4` file. Do not hand-edit generated lexer/parser/tokens.
- Service methods return frozen dataclasses (not dicts). All public modules, classes, and functions carry Google-style docstrings (enforced by ruff `D` rules).
- Tests use the markers `unit`, `integration`, `api`, `django`. Integration tests may hit a real database.

## Submitting Changes
- Open a Pull Request against `master` with a clear description of the change and testing performed.
- Reference related issues and include screenshots/logs if relevant.
- Be responsive to review feedback; keep discussions respectful (see Code of Conduct).

## Questions?
Open a GitHub issue or discuss in the PR. Security issues: follow the [SECURITY.md](SECURITY.md) instructions.
