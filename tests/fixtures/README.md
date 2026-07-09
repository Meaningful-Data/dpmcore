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

## XBRL taxonomy fixtures (`xbrl/`)

Unlike `test_data.db`, the XBRL fixtures **are** committed:

- `xbrl/seg2008/`, `xbrl/fib2008/` — the National Bank of Belgium
  SEG (seg2008) and FIB (fib2008) taxonomies, copied verbatim from
  the public downloads at <https://www.nbb.be/doc/dd/onegate/data/>
  (`seg2008-taxonomy.zip`, `fib2008-taxonomy.zip`). They are tiny
  (one table each) and serve as real-world integration fixtures for
  the 2006-Eurofiling reader. © National Bank of Belgium; included
  here solely for testing the importer.
- `xbrl/mini_dpm1/` — a hand-crafted minimal TREP-style (dpm1
  architecture) taxonomy exercising every reader branch: one
  explicit and one typed dimension, a three-member domain with a
  hierarchy, two metrics, one module and one table with x/y/z
  breakdowns.

The xbrl.org core schemas the SEG/FIB DTSes reference are served
from Arelle's bundled resource cache, so the related tests run
fully offline.
