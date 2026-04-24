# tests/fixtures/

This directory is intentionally near-empty. It is the expected location for
`test_data.db` — a SQLite snapshot of the EBA DPM data dictionary used by
integration tests in [`tests/integration/validation/test_semantic_release.py`](../integration/validation/test_semantic_release.py).

## Why the file is not committed

`test_data.db` contains a multi-release snapshot of the EBA DPM (20+ framework
tables × 3 release versions × property/enumeration/cell content). A populated
dump is typically 20–100 MB — too large for regular git without LFS, and LFS
bandwidth under the CI matrix (12 jobs × 4 Python versions) would exhaust the
free quota quickly.

It is also not hosted in any public MeaningfulData repo at the time of writing,
so contributors must provide it out-of-band.

## How to provide it

Drop a `test_data.db` file into this directory (`tests/fixtures/test_data.db`).

Any of the following works:

- Copy from an internal MeaningfulData share.
- Build one from a real EBA DPM access database via `dpmcore migrate`
  (see [`src/dpmcore/cli/main.py`](../../src/dpmcore/cli/main.py) `migrate`
  subcommand). The destination SQLite DB can be pointed at this path.
- Any SQLite file whose schema matches
  [`dpmcore.orm.Base.metadata`](../../src/dpmcore/orm/base.py) and whose rows
  cover the framework tables / enumerations / releases the tests reference
  (see the expressions in `test_semantic_release.py`).

## Skip behaviour

`tests/integration/conftest.py` `fixture_db_url` fixture detects when the file
is missing and **skips** dependent tests (rather than erroring). CI and local
runs therefore succeed without the file; providing it activates the additional
25 tests in `test_semantic_release.py`.

Run `pytest tests/integration/validation/test_semantic_release.py -v` after
dropping the file in — you should see every test pass.
