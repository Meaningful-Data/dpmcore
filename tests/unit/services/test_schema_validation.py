"""Unit tests for SchemaValidationService."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from dpmcore.orm.base import Base
from dpmcore.services.schema_validation import (
    REQUIRED_NON_EMPTY_TABLES,
    SchemaValidationResult,
    SchemaValidationService,
)


@pytest.fixture
def empty_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield engine
    engine.dispose()


@pytest.fixture
def full_engine(empty_engine):
    Base.metadata.create_all(empty_engine)
    with empty_engine.begin() as conn:
        for name in REQUIRED_NON_EMPTY_TABLES:
            _insert_minimal_row(conn, name)
    return empty_engine


def _insert_minimal_row(conn, table_name: str) -> None:
    """Insert one row with type-appropriate sample values for every column.

    Uses :func:`_sample_value` per column so NOT NULL / typed constraints
    are satisfied across SQLite, PostgreSQL, and SQL Server — the goal is
    just to make the table non-empty for the seed-table sanity check.
    """
    table = Base.metadata.tables[table_name]
    quoted = conn.dialect.identifier_preparer.quote(table_name)
    cols = list(table.columns)
    col_list = ", ".join(
        conn.dialect.identifier_preparer.quote(c.name) for c in cols
    )
    placeholders = ", ".join([":v" + str(i) for i in range(len(cols))])
    values = {f"v{i}": _sample_value(c) for i, c in enumerate(cols)}
    sql = f"INSERT INTO {quoted} ({col_list}) VALUES ({placeholders})"  # noqa: S608
    conn.execute(text(sql), values)


def _sample_value(column) -> object:
    """Produce a plausible value for any column type."""
    type_str = str(column.type).upper()
    if "INT" in type_str:
        return 1
    if "NUMERIC" in type_str or "DECIMAL" in type_str or "FLOAT" in type_str:
        return 0.0
    if "BOOL" in type_str:
        return 0
    if "DATE" in type_str or "TIME" in type_str:
        return "2024-01-01"
    return "x"


class TestEmptyDatabase:
    def test_reports_all_tables_missing(self, empty_engine):
        result = SchemaValidationService(empty_engine).validate()

        assert isinstance(result, SchemaValidationResult)
        assert result.is_valid is False
        assert set(result.missing_tables) == set(Base.metadata.tables.keys())
        assert result.missing_columns == {}
        assert result.empty_required_tables == []
        assert result.backend == "sqlite"
        assert result.elapsed_ms >= 0.0

    def test_does_not_raise(self, empty_engine):
        # Sanity: must not raise on a non-DPM DB.
        SchemaValidationService(empty_engine).validate()


class TestFullyPopulatedDatabase:
    def test_is_valid(self, full_engine):
        result = SchemaValidationService(full_engine).validate()
        assert result.is_valid is True
        assert result.missing_tables == []
        assert result.missing_columns == {}
        assert result.empty_required_tables == []


class TestEmptySeedTable:
    def test_reports_empty_required(self, full_engine):
        # Wipe one required seed table; expect it flagged as empty.
        with full_engine.begin() as conn:
            conn.execute(text('DELETE FROM "Variable"'))

        result = SchemaValidationService(full_engine).validate()

        assert result.is_valid is False
        assert "Variable" in result.empty_required_tables
        assert result.missing_tables == []
        assert result.missing_columns == {}


class TestMissingColumn:
    def test_reports_missing_columns(self, empty_engine):
        # Create only one table with a single column to force a mismatch.
        with empty_engine.begin() as conn:
            conn.execute(text('CREATE TABLE "Variable" (variable_id INTEGER)'))

        result = SchemaValidationService(empty_engine).validate()

        assert result.is_valid is False
        # "Variable" exists, so it is not in missing_tables.
        assert "Variable" not in result.missing_tables
        # Several real columns should be flagged as missing.
        assert "Variable" in result.missing_columns
        assert len(result.missing_columns["Variable"]) > 0


class TestCaseInsensitiveMatch:
    def test_lowercase_table_still_matches(self, empty_engine):
        # Postgres-style: tables exist but with lowercased names.
        # Reflect just the Variable model with a lowercased name.
        with empty_engine.begin() as conn:
            cols = Base.metadata.tables["Variable"].columns
            col_defs = ", ".join(f'"{c.name}" TEXT' for c in cols)
            conn.execute(text(f"CREATE TABLE variable ({col_defs})"))

        result = SchemaValidationService(empty_engine).validate()

        # The lowercase "variable" table should satisfy the "Variable"
        # expectation — i.e. NOT appear in missing_tables.
        assert "Variable" not in result.missing_tables
