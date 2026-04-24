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
            ),
            pytest.raises(MigrationError, match="Could not read"),
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

    def test_load_failure_raises_migration_error(self, sqlite_engine):
        service = MigrationService(sqlite_engine)

        df = MagicMock()
        df.to_sql.side_effect = Exception("boom")

        with pytest.raises(MigrationError, match="bad_table"):
            service._load_data({"bad_table": df})


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


class TestMigrateCsvDir:
    def test_migrate_from_csv_dir_success(self, service, tmp_path):
        (tmp_path / "Release.csv").write_text(
            "ReleaseID,Code\n1,4.0\n",
            encoding="utf-8",
        )
        (tmp_path / "Organisation.csv").write_text(
            "OrgID,Name,Acronym,IDPrefix\n1,European Banking Authority,EBA,1\n",
            encoding="utf-8",
        )

        result = service.migrate_from_csv_dir(str(tmp_path))

        assert result.backend_used == "csv"
        assert result.tables_migrated == 2
        assert result.total_rows == 2
        assert result.table_details["Release"] == 1
        assert result.table_details["Organisation"] == 1

    def test_migrate_from_csv_dir_empty_dir_raises(self, service, tmp_path):
        with pytest.raises(MigrationError, match="No CSV files found"):
            service.migrate_from_csv_dir(str(tmp_path))

    def test_extract_from_csv_dir_preserves_row_column_sheet_as_strings(
        self,
        service,
        tmp_path,
    ):
        (tmp_path / "OperandReferenceLocation.csv").write_text(
            "OperandReferenceID,CellID,Table,Row,Column,Sheet\n"
            "1,10,T_01,01,002,003\n",
            encoding="utf-8",
        )

        data = service._extract_from_csv_dir(tmp_path)
        df = data["OperandReferenceLocation"]

        assert df["Row"].iloc[0] == "01"
        assert df["Column"].iloc[0] == "002"
        assert df["Sheet"].iloc[0] == "003"
        assert df["OperandReferenceID"].iloc[0] == 1
        assert df["CellID"].iloc[0] == 10

    def test_coerce_numeric_columns_for_csv_preserves_coordinates_and_numeric_ids(
        self, service
    ):
        import pandas as pd

        df = pd.DataFrame(
            {
                "Row": ["01"],
                "Column": ["002"],
                "Sheet": ["003"],
                "OperandReferenceID": ["1"],
                "CellID": ["10"],
                "Label": ["ABC"],
            }
        )

        result = service._coerce_numeric_columns_for_csv(df)

        assert result["Row"].iloc[0] == "01"
        assert result["Column"].iloc[0] == "002"
        assert result["Sheet"].iloc[0] == "003"
        assert result["OperandReferenceID"].iloc[0] == 1
        assert result["CellID"].iloc[0] == 10
        assert result["Label"].iloc[0] == "ABC"

    def test_coerce_temporal_columns_for_schema_parses_dd_mm_yyyy(
        self, service
    ):
        import pandas as pd
        from dpmcore.orm.base import Base

        df = pd.DataFrame(
            {
                "OperationScopeID": [1],
                "OperationVID": [10],
                "IsActive": [1],
                "Severity": ["warning"],
                "FromSubmissionDate": ["17/03/2026"],
            }
        )

        orm_table = Base.metadata.tables["OperationScope"]
        result = service._coerce_temporal_columns_for_schema(df, orm_table)

        assert str(result["FromSubmissionDate"].iloc[0]) == "2026-03-17"

    def test_coerce_temporal_columns_handles_missing_values(self, service):
        import pandas as pd
        from dpmcore.orm.base import Base

        df = pd.DataFrame(
            {
                "FromSubmissionDate": ["", None],
            }
        )

        orm_table = Base.metadata.tables["OperationScope"]
        result = service._coerce_temporal_columns_for_schema(df, orm_table)

        assert result["FromSubmissionDate"].iloc[0] is None
        assert result["FromSubmissionDate"].iloc[1] is None
