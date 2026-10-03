# tests/fixtures/

This directory is intentionally near-empty. It is the expected location for `test_data.db` — a SQLite snapshot of the EBA DPM data dictionary used by the integration tests under [`tests/integration/`](../integration/).

## Why the file is not committed

`test_data.db` is a full migration of an EBA DPM Access database (the current one is DPM 4.2.1, about 400 MB) — too large for regular git without LFS, and LFS bandwidth under the CI matrix would exhaust the free quota quickly.

It is also not hosted in any public MeaningfulData repo at the time of writing, so contributors must provide it out-of-band.

## How to provide it

Build it from the EBA DPM 4.2.1 Access database with `dpmcore migrate` (needs `mdb-tools`):

```bash
dpmcore migrate --source "DPM2 Database_v 4_2_1.accdb" \
    --database sqlite:///dpm_4.2.1.db --output dpm_4.2.1.db
ln -s "$PWD/dpm_4.2.1.db" tests/fixtures/test_data.db
```

Rebuild it whenever the ORM schema changes: `services/test_schema_validation_integration.py::TestFixtureDatabase::test_fixture_db_is_valid` fails when the file lacks a table or column the ORM declares.

## Known semantic failures

`tests/integration/validation/test_semantic_all.py` validates every expression in the DB. The ones that do not validate (engine limitations and dictionary data errors) are listed with their error code in [`semantic_all_known_failures.csv`](../integration/validation/semantic_all_known_failures.csv), which is tied to this DB. After rebuilding the DB, rebuild the list and review its diff:

```bash
python scripts/check_semantic.py \
    --known-failures tests/integration/validation/semantic_all_known_failures.csv
```

## Skip behaviour

`tests/integration/conftest.py` `fixture_db_url` fixture detects when the file is missing and **skips** dependent tests (rather than erroring). CI does not provide the file, so it skips them all; run `pytest tests/integration` locally to exercise them.
