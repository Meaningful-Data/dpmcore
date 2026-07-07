"""Validate that ORM table and column definitions match the Access DB schema.

Requires ``mdb-schema`` from the mdbtools package to be available on PATH.
The path to the reference Access database is configurable via the
``DPM_ACCDB_PATH`` environment variable (defaults to the conventional
location on the mounted Windows drive).

Run with::

    pytest tests/unit/orm/test_schema_alignment.py -v
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Dict, Set

import pytest

from dpmcore.orm import Base

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

# Tables in the Access DB that are auxiliary / not part of the core
# ORM and are intentionally excluded from validation.
EXCLUDED_TABLES: Set[str] = {
    "ATTT2Hierarchies",
    "PSCurrentItemCategory",
    "PSCurrentPropertyCategory",
    "VarGeneration_Detail",
    "VarGeneration_Summary",
}

# ORM columns that are synthetic (e.g. surrogate PKs added because
# the Access table has no natural primary key).  {table: {col, …}}
SYNTHETIC_ORM_COLUMNS: Dict[str, Set[str]] = {
    "ModelViolations": {"id"},
}

# Access types → canonical type names used for comparison.
_ACCESS_TYPE_MAP: Dict[str, str] = {
    "Long Integer": "INTEGER",
    "Integer": "INTEGER",
    "Byte": "INTEGER",
    "Text": "VARCHAR",
    "Memo/Hyperlink": "VARCHAR",
    "Replication ID": "VARCHAR",
    "DateTime": "DATETIME",
    "Numeric": "NUMERIC",
}


def _parse_accdb_schema(raw_sql: str) -> Dict[str, Set[str]]:
    """Parse mdb-schema output into {table_name: {column_name, …}}."""
    tables: Dict[str, Set[str]] = {}
    current_table = None
    for line in raw_sql.splitlines():
        m = re.match(r"CREATE TABLE \[(.+?)\]", line)
        if m:
            current_table = m.group(1)
            tables[current_table] = set()
            continue
        if current_table is not None:
            col_match = re.match(r"\s+\[(.+?)\]", line)
            if col_match:
                tables[current_table].add(col_match.group(1))
        if line.strip() == ");":
            current_table = None
    return tables


def _get_orm_schema() -> Dict[str, Set[str]]:
    """Return {table_name: {column_name, …}} from SQLAlchemy metadata."""
    tables: Dict[str, Set[str]] = {}
    for table_name, table in Base.metadata.tables.items():
        tables[table_name] = {col.name for col in table.columns}
    return tables


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture(scope="module")
def accdb_schema() -> Dict[str, Set[str]]:
    """Extract schema from the reference Access database."""
    if not shutil.which("mdb-schema"):
        pytest.skip("mdb-schema (mdbtools) not available on PATH")

    accdb_path = os.environ.get(
        "DPM_ACCDB_PATH",
        "/mnt/c/Pap/DPM2 Database_v 4_2_1.accdb",
    )
    if not os.path.isfile(accdb_path):
        pytest.skip(f"Access database not found at {accdb_path}")

    result = subprocess.run(
        ["mdb-schema", accdb_path],
        capture_output=True,
        text=True,
        check=True,
    )
    return _parse_accdb_schema(result.stdout)


@pytest.fixture(scope="module")
def orm_schema() -> Dict[str, Set[str]]:
    return _get_orm_schema()


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #


def test_all_db_tables_have_orm_models(
    accdb_schema: Dict[str, Set[str]],
    orm_schema: Dict[str, Set[str]],
) -> None:
    """Every non-excluded Access table must have a corresponding ORM model."""
    db_tables = set(accdb_schema) - EXCLUDED_TABLES
    missing = db_tables - set(orm_schema)
    assert not missing, (
        f"Access DB tables without ORM models: {sorted(missing)}"
    )


def test_orm_tables_exist_in_db(
    accdb_schema: Dict[str, Set[str]],
    orm_schema: Dict[str, Set[str]],
) -> None:
    """Every ORM table must correspond to a real Access DB table."""
    extra = set(orm_schema) - set(accdb_schema)
    assert not extra, f"ORM tables not present in Access DB: {sorted(extra)}"


@pytest.mark.parametrize(
    "table_name",
    sorted(set(Base.metadata.tables) - EXCLUDED_TABLES),
)
def test_columns_match(
    table_name: str,
    accdb_schema: Dict[str, Set[str]],
    orm_schema: Dict[str, Set[str]],
) -> None:
    """ORM columns for each table must match the Access DB columns."""
    if table_name not in accdb_schema:
        pytest.skip(f"{table_name} not in Access DB")

    db_cols = accdb_schema[table_name]
    orm_cols = orm_schema.get(table_name, set())
    synthetic = SYNTHETIC_ORM_COLUMNS.get(table_name, set())

    missing_in_orm = db_cols - orm_cols
    extra_in_orm = orm_cols - db_cols - synthetic

    errors = []
    if missing_in_orm:
        errors.append(
            f"  columns in DB but missing from ORM: {sorted(missing_in_orm)}"
        )
    if extra_in_orm:
        errors.append(
            f"  columns in ORM but missing from DB: {sorted(extra_in_orm)}"
        )
    assert not errors, f"Column mismatch for [{table_name}]:\n" + "\n".join(
        errors
    )
