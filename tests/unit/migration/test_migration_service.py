"""Tests for the MigrationService."""


from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from dpmcore.services.migration import (
    MigrationError,
    MigrationResult,
    MigrationService,
)


@pytest.fixture
def sqlite_engine():
    return create_engine("sqlite:///:memory:")


@pytest.fixture
def service(sqlite_engine):
    return MigrationService(sqlite_engine)


class TestMigrateMdbtoolsSuccess:
    def test_returns_migration_result(self, service):
        csv_data = "id,name\n1,Alice\n2,Bob\n"

        with patch("subprocess.check_output") as mock_sub:
            mock_sub.side_effect = [
                "Users\n",  # mdb-tables
                csv_data,  # mdb-export
            ]
            result = service.migrate_from_access("/fake.accdb")

        assert isinstance(result, MigrationResult)
        assert result.tables_migrated == 1
        assert result.total_rows == 2
        assert result.table_details == {"Users": 2}
        assert result.backend_used == "mdbtools"

    def test_multiple_tables(self, service):
        with patch("subprocess.check_output") as mock_sub:
            mock_sub.side_effect = [
                "T1\nT2\n",
                "a,b\n1,2\n",
                "x,y\n3,4\n5,6\n",
            ]
            result = service.migrate_from_access("/fake.accdb")

        assert result.tables_migrated == 2
        assert result.total_rows == 3
        assert result.table_details == {"T1": 1, "T2": 2}


class TestMigratePyodbcFallback:
    def test_falls_back_to_pyodbc(self, service):
        mock_pyodbc = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.tables.return_value = [
            MagicMock(table_name="Items"),
        ]
        mock_cursor.description = [
            ("id", int, None, None, None, None, None),
            ("name", str, None, None, None, None, None),
        ]
        mock_cursor.fetchall.return_value = [
            (1, "Widget"),
            (2, "Gadget"),
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        import sys

        with (
            patch(
                "subprocess.check_output",
                side_effect=FileNotFoundError,
            ),
            patch.dict(sys.modules, {"pyodbc": mock_pyodbc}),
        ):
            result = service.migrate_from_access("/fake.accdb")

        assert result.backend_used == "pyodbc"
        assert result.tables_migrated == 1
        assert result.total_rows == 2


class TestMigrateBothFail:
    def test_raises_migration_error(self, service):
        with (
            patch(
                "subprocess.check_output",
                side_effect=FileNotFoundError,
            ),
            patch(
                "dpmcore.services.migration.MigrationService"
                "._extract_with_pyodbc",
                side_effect=ImportError("no pyodbc"),
            ),pytest.raises(MigrationError, match="Could not read")
        ):
            service.migrate_from_access("/fake.accdb")


class TestCreateSchema:
    def test_calls_create_all(self):
        mock_engine = MagicMock()
        service = MigrationService(mock_engine)

        with patch(
            "dpmcore.services.migration.Base.metadata.create_all"
        ) as mock_create:
            service._create_schema()
            mock_create.assert_called_once_with(mock_engine)


class TestLoadData:
    def test_rows_inserted(self, sqlite_engine):
        service = MigrationService(sqlite_engine)

        # Create a table manually.
        with sqlite_engine.connect() as conn:
            conn.execute(text("CREATE TABLE items (id INTEGER, name TEXT)"))
            conn.commit()

        df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
        warnings = service._load_data({"items": df})

        assert warnings == []

        with sqlite_engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM items")).fetchall()

        assert len(rows) == 2

    def test_load_failure_returns_warning(self, sqlite_engine):
        service = MigrationService(sqlite_engine)

        # Table does not exist — to_sql with append on a non-existent
        # table will still create it with pandas, so we mock to_sql.
        df = MagicMock()
        df.to_sql.side_effect = Exception("boom")

        warnings = service._load_data({"bad_table": df})

        assert len(warnings) == 1
        assert "bad_table" in warnings[0]


class TestSystemTablesFiltered:
    def test_mdbtools_filters_system_tables(self, service):
        raw_tables = "Users\nMSysObjects\nMSysACEs\n~TmpTable\nOrders\n"
        csv_users = "id\n1\n"
        csv_orders = "id\n2\n"

        with patch("subprocess.check_output") as mock_sub:
            mock_sub.side_effect = [
                raw_tables,
                csv_users,
                csv_orders,
            ]
            result = service.migrate_from_access("/fake.accdb")

        assert "MSysObjects" not in result.table_details
        assert "MSysACEs" not in result.table_details
        assert "~TmpTable" not in result.table_details
        assert "Users" in result.table_details
        assert "Orders" in result.table_details
