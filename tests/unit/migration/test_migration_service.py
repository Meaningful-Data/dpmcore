"""Tests for the MigrationService."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from dpmcore.loaders.migration import (
    MigrationError,
    MigrationResult,
    MigrationService,
)

FIXED_TOKEN = "20260512"  # noqa: S105


@pytest.fixture
def sqlite_engine():
    return create_engine("sqlite:///:memory:", future=True)


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
                "dpmcore.loaders.migration.MigrationService"
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
            "dpmcore.loaders.migration.Base.metadata.create_all"
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

        result = service._coerce_numeric_columns(df)

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


class TestRenameWithMetadata:
    @staticmethod
    def _csv_dir_with_release(tmp_path, code="4.2", is_current=1):
        (tmp_path / "Release.csv").write_text(
            "ReleaseID,Code,Date,IsCurrent\n"
            f"1,{code},2026-01-01,{is_current}\n",
            encoding="utf-8",
        )
        return tmp_path

    @pytest.fixture(autouse=True)
    def _frozen_today(self):
        with patch.object(
            MigrationService, "_today_token", return_value=FIXED_TOKEN
        ):
            yield

    def test_renames_sqlite_file_with_release_and_date(self, tmp_path):
        db_path = tmp_path / "dpm.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        service = MigrationService(engine)

        csv_dir = tmp_path / "csv"
        csv_dir.mkdir()
        self._csv_dir_with_release(csv_dir)

        result = service.migrate_from_csv_dir(str(csv_dir))

        expected = tmp_path / f"dpm_4.2_{FIXED_TOKEN}.db"
        assert result.database_path == expected
        assert expected.exists()
        assert not db_path.exists()

    def test_renames_without_release_token_when_no_release(self, tmp_path):
        db_path = tmp_path / "dpm.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        service = MigrationService(engine)

        csv_dir = tmp_path / "csv"
        csv_dir.mkdir()
        (csv_dir / "Organisation.csv").write_text(
            "OrgID,Name,Acronym,IDPrefix\n1,EBA,EBA,1\n",
            encoding="utf-8",
        )

        result = service.migrate_from_csv_dir(str(csv_dir))

        expected = tmp_path / f"dpm_{FIXED_TOKEN}.db"
        assert result.database_path == expected
        assert expected.exists()

    def test_falls_back_to_any_release_when_none_is_current(self, tmp_path):
        db_path = tmp_path / "dpm.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        service = MigrationService(engine)

        csv_dir = tmp_path / "csv"
        csv_dir.mkdir()
        self._csv_dir_with_release(csv_dir, code="3.9", is_current=0)

        result = service.migrate_from_csv_dir(str(csv_dir))

        assert result.database_path is not None
        assert "3.9" in result.database_path.name

    def test_undated_current_release_is_latest(self, tmp_path):
        db_path = tmp_path / "dpm.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        service = MigrationService(engine)

        csv_dir = tmp_path / "csv"
        csv_dir.mkdir()
        # Two current releases: a dated 4.2 and an undated working
        # release. The undated one ranks as the latest, so its code
        # names the exported file.
        (csv_dir / "Release.csv").write_text(
            "ReleaseID,Code,Date,IsCurrent\n"
            "1,4.2,2026-01-01,1\n"
            "2,Playground,,1\n",
            encoding="utf-8",
        )

        result = service.migrate_from_csv_dir(str(csv_dir))

        assert result.database_path is not None
        assert "Playground" in result.database_path.name

    def test_sanitises_unsafe_characters_in_release_code(self, tmp_path):
        db_path = tmp_path / "dpm.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        service = MigrationService(engine)

        csv_dir = tmp_path / "csv"
        csv_dir.mkdir()
        self._csv_dir_with_release(csv_dir, code="4.2/rc1")

        result = service.migrate_from_csv_dir(str(csv_dir))

        assert result.database_path is not None
        assert "/" not in result.database_path.name
        assert "4.2-rc1" in result.database_path.name

    def test_returns_none_path_for_in_memory_engine(self, service, tmp_path):
        csv_dir = tmp_path / "csv"
        csv_dir.mkdir()
        self._csv_dir_with_release(csv_dir)

        result = service.migrate_from_csv_dir(str(csv_dir))

        assert result.database_path is None

    def test_sqlite_file_path_returns_none_for_non_sqlite_url(self):
        engine = MagicMock()
        engine.url.get_backend_name.return_value = "postgresql"
        engine.url.database = "dpm"

        service = MigrationService(engine)
        assert service._sqlite_file_path() is None

    def test_sqlite_file_path_returns_none_when_file_missing(self, tmp_path):
        missing = tmp_path / "nope.db"
        engine = create_engine(f"sqlite:///{missing}", future=True)
        service = MigrationService(engine)
        assert service._sqlite_file_path() is None

    def test_sqlite_file_path_returns_none_when_database_is_blank(self):
        engine = MagicMock()
        engine.url.get_backend_name.return_value = "sqlite"
        engine.url.database = ""
        service = MigrationService(engine)
        assert service._sqlite_file_path() is None

    def test_release_code_sanitises_to_none_when_only_unsafe(self, tmp_path):
        db_path = tmp_path / "dpm.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        service = MigrationService(engine)

        csv_dir = tmp_path / "csv"
        csv_dir.mkdir()
        self._csv_dir_with_release(csv_dir, code="///")

        result = service.migrate_from_csv_dir(str(csv_dir))

        assert result.database_path is not None
        assert result.database_path.name == f"dpm_{FIXED_TOKEN}.db"


class TestOutputPathOverride:
    @pytest.fixture(autouse=True)
    def _frozen_today(self):
        with patch.object(
            MigrationService, "_today_token", return_value=FIXED_TOKEN
        ):
            yield

    def test_output_path_overrides_convention(self, tmp_path):
        db_path = tmp_path / "dpm.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        service = MigrationService(engine)

        csv_dir = tmp_path / "csv"
        csv_dir.mkdir()
        (csv_dir / "Release.csv").write_text(
            "ReleaseID,Code,IsCurrent\n1,4.2,1\n",
            encoding="utf-8",
        )

        target = tmp_path / "custom" / "mydb.sqlite"
        result = service.migrate_from_csv_dir(str(csv_dir), output_path=target)

        assert result.database_path == target
        assert target.exists()
        assert not db_path.exists()

    def test_output_path_creates_parent_dirs(self, tmp_path):
        db_path = tmp_path / "dpm.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        service = MigrationService(engine)

        csv_dir = tmp_path / "csv"
        csv_dir.mkdir()
        (csv_dir / "Organisation.csv").write_text(
            "OrgID,Name,Acronym,IDPrefix\n1,EBA,EBA,1\n",
            encoding="utf-8",
        )

        target = tmp_path / "nested" / "deeper" / "out.db"
        result = service.migrate_from_csv_dir(str(csv_dir), output_path=target)

        assert result.database_path == target
        assert target.exists()

    def test_output_path_ignored_for_in_memory_engine(self, service, tmp_path):
        csv_dir = tmp_path / "csv"
        csv_dir.mkdir()
        (csv_dir / "Organisation.csv").write_text(
            "OrgID,Name,Acronym,IDPrefix\n1,EBA,EBA,1\n",
            encoding="utf-8",
        )

        result = service.migrate_from_csv_dir(
            str(csv_dir), output_path=tmp_path / "ignored.db"
        )

        assert result.database_path is None
        assert not (tmp_path / "ignored.db").exists()

    def test_output_path_noop_when_same_as_current(self, tmp_path):
        db_path = tmp_path / "dpm.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        service = MigrationService(engine)

        csv_dir = tmp_path / "csv"
        csv_dir.mkdir()
        (csv_dir / "Organisation.csv").write_text(
            "OrgID,Name,Acronym,IDPrefix\n1,EBA,EBA,1\n",
            encoding="utf-8",
        )

        result = service.migrate_from_csv_dir(
            str(csv_dir), output_path=db_path
        )

        assert result.database_path == db_path
        assert db_path.exists()

    def test_migrate_from_access_accepts_output_path(self, tmp_path):
        db_path = tmp_path / "dpm.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        service = MigrationService(engine)

        with patch("subprocess.check_output") as mock_sub:
            mock_sub.side_effect = [
                "Organisation\n",
                "OrgID,Name,Acronym,IDPrefix\n1,EBA,EBA,1\n",
            ]
            target = tmp_path / "renamed.db"
            result = service.migrate_from_access(
                "/fake.accdb", output_path=target
            )

        assert result.database_path == target
        assert target.exists()


class TestTodayToken:
    def test_returns_utc_yyyymmdd_string(self):
        token = MigrationService._today_token()
        assert len(token) == 8
        assert token.isdigit()


# ---------------------------------------------------------------------------
# MigrationService.__init__ – schema parameter
# ---------------------------------------------------------------------------


class TestMigrationServiceInit:
    def test_schema_none_ddl_engine_is_engine(self):
        engine = MagicMock()
        service = MigrationService(engine)
        assert service._ddl_engine is engine

    def test_schema_set_ddl_engine_uses_execution_options(self):
        engine = MagicMock()
        translated = MagicMock()
        engine.execution_options.return_value = translated

        service = MigrationService(engine, schema="staging")

        engine.execution_options.assert_called_once_with(
            schema_translate_map={None: "staging"}
        )
        assert service._ddl_engine is translated

    def test_schema_stored(self):
        engine = MagicMock()
        service = MigrationService(engine, schema="staging")
        assert service._schema == "staging"

    def test_schema_none_stored(self):
        engine = MagicMock()
        service = MigrationService(engine)
        assert service._schema is None


# ---------------------------------------------------------------------------
# _coerce_boolean_columns_for_schema
# ---------------------------------------------------------------------------


def _make_bool_table():
    from sqlalchemy import Column, MetaData, Table
    from sqlalchemy.types import Boolean, String

    meta = MetaData()
    return Table(
        "TestBool", meta, Column("Flag", Boolean()), Column("Name", String(20))
    )


class TestCoerceBooleanColumnsForSchema:
    @pytest.fixture
    def bool_table(self):
        return _make_bool_table()

    @staticmethod
    def _coerce(values, table):
        df = pd.DataFrame({"Flag": list(values)})
        result = MigrationService._coerce_boolean_columns_for_schema(df, table)
        out = []
        for v in result["Flag"]:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                out.append(None)
            else:
                out.append(bool(v))
        return out

    # --- string true values ---
    def test_string_minus_one_is_true(self, bool_table):
        assert self._coerce(["-1"], bool_table) == [True]

    def test_string_one_is_true(self, bool_table):
        assert self._coerce(["1"], bool_table) == [True]

    def test_string_true_is_true(self, bool_table):
        assert self._coerce(["true"], bool_table) == [True]

    def test_string_yes_is_true(self, bool_table):
        assert self._coerce(["yes"], bool_table) == [True]

    def test_string_y_is_true(self, bool_table):
        assert self._coerce(["y"], bool_table) == [True]

    def test_string_t_is_true(self, bool_table):
        assert self._coerce(["t"], bool_table) == [True]

    def test_string_minus_one_float_is_true(self, bool_table):
        assert self._coerce(["-1.0"], bool_table) == [True]

    def test_string_one_float_is_true(self, bool_table):
        assert self._coerce(["1.0"], bool_table) == [True]

    # --- string false values ---
    def test_string_zero_is_false(self, bool_table):
        assert self._coerce(["0"], bool_table) == [False]

    def test_string_false_is_false(self, bool_table):
        assert self._coerce(["false"], bool_table) == [False]

    def test_string_no_is_false(self, bool_table):
        assert self._coerce(["no"], bool_table) == [False]

    def test_string_n_is_false(self, bool_table):
        assert self._coerce(["n"], bool_table) == [False]

    def test_string_f_is_false(self, bool_table):
        assert self._coerce(["f"], bool_table) == [False]

    def test_string_zero_float_is_false(self, bool_table):
        assert self._coerce(["0.0"], bool_table) == [False]

    # --- null values ---
    def test_empty_string_is_none(self, bool_table):
        assert self._coerce([""], bool_table) == [None]

    def test_string_nan_is_none(self, bool_table):
        assert self._coerce(["nan"], bool_table) == [None]

    def test_string_none_is_none(self, bool_table):
        assert self._coerce(["none"], bool_table) == [None]

    def test_string_null_is_none(self, bool_table):
        assert self._coerce(["null"], bool_table) == [None]

    def test_string_na_is_none(self, bool_table):
        assert self._coerce(["<na>"], bool_table) == [None]

    def test_python_none_is_none(self, bool_table):
        assert self._coerce([None], bool_table) == [None]

    def test_pandas_na_is_none(self, bool_table):
        assert self._coerce([pd.NA], bool_table) == [None]

    # --- Python type passthroughs ---
    def test_bool_true_passthrough(self, bool_table):
        assert self._coerce([True], bool_table) == [True]

    def test_bool_false_passthrough(self, bool_table):
        assert self._coerce([False], bool_table) == [False]

    def test_int_minus_one_is_true(self, bool_table):
        assert self._coerce([-1], bool_table) == [True]

    def test_int_one_is_true(self, bool_table):
        assert self._coerce([1], bool_table) == [True]

    def test_int_zero_is_false(self, bool_table):
        assert self._coerce([0], bool_table) == [False]

    def test_float_minus_one_is_true(self, bool_table):
        assert self._coerce([-1.0], bool_table) == [True]

    def test_float_one_is_true(self, bool_table):
        assert self._coerce([1.0], bool_table) == [True]

    def test_float_zero_is_false(self, bool_table):
        assert self._coerce([0.0], bool_table) == [False]

    # --- error cases ---
    def test_unsupported_string_raises_migration_error(self, bool_table):
        with pytest.raises(MigrationError):
            self._coerce(["maybe"], bool_table)

    def test_unsupported_numeric_string_raises_migration_error(
        self, bool_table
    ):
        with pytest.raises(MigrationError):
            self._coerce(["2.5"], bool_table)

    def test_unsupported_int_raises_migration_error(self, bool_table):
        with pytest.raises(MigrationError):
            self._coerce([2], bool_table)

    def test_unsupported_float_raises_migration_error(self, bool_table):
        with pytest.raises(MigrationError):
            self._coerce([2.5], bool_table)

    def test_error_message_includes_table_and_column(self, bool_table):
        with pytest.raises(MigrationError, match="TestBool"):
            self._coerce(["bad_value"], bool_table)

        with pytest.raises(MigrationError, match="Flag"):
            self._coerce(["bad_value"], bool_table)

    # --- skipping behavior ---
    def test_non_boolean_column_not_modified(self, bool_table):
        df = pd.DataFrame({"Name": ["yes"]})
        result = MigrationService._coerce_boolean_columns_for_schema(
            df, bool_table
        )
        assert result["Name"].iloc[0] == "yes"

    def test_column_not_in_df_skipped(self, bool_table):
        df = pd.DataFrame({"OtherCol": ["yes"]})
        result = MigrationService._coerce_boolean_columns_for_schema(
            df, bool_table
        )
        assert "Flag" not in result.columns

    # --- case insensitive ---
    def test_case_insensitive_true(self, bool_table):
        assert self._coerce(["TRUE"], bool_table) == [True]
        assert self._coerce(["Yes"], bool_table) == [True]

    def test_case_insensitive_false(self, bool_table):
        assert self._coerce(["FALSE"], bool_table) == [False]
        assert self._coerce(["NO"], bool_table) == [False]

    # --- multiple rows ---
    def test_multiple_rows(self, bool_table):
        result = self._coerce(["-1", "0", None, "true", "false"], bool_table)
        assert result == [True, False, None, True, False]


# ---------------------------------------------------------------------------
# _prepare_bulk_load_constraints
# ---------------------------------------------------------------------------


class TestPrepareBulkLoadConstraints:
    def test_schema_none_is_noop(self):
        engine = MagicMock()
        service = MigrationService(engine)
        service._prepare_bulk_load_constraints()
        engine.begin.assert_not_called()

    def test_postgresql_calls_drop_fk(self):
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        service = MigrationService(engine, schema="staging")

        with patch.object(
            service, "_drop_postgresql_foreign_keys_for_bulk_load"
        ) as mock_drop:
            service._prepare_bulk_load_constraints()

        mock_drop.assert_called_once()

    def test_mssql_calls_disable_constraints(self):
        engine = MagicMock()
        engine.dialect.name = "mssql"
        service = MigrationService(engine, schema="staging")

        with patch.object(
            service, "_disable_sqlserver_constraints_for_bulk_load"
        ) as mock_disable:
            service._prepare_bulk_load_constraints()

        mock_disable.assert_called_once()

    def test_other_dialect_is_noop(self):
        engine = MagicMock()
        engine.dialect.name = "oracle"
        service = MigrationService(engine, schema="staging")

        with (
            patch.object(
                service, "_drop_postgresql_foreign_keys_for_bulk_load"
            ) as mock_pg,
            patch.object(
                service, "_disable_sqlserver_constraints_for_bulk_load"
            ) as mock_ms,
        ):
            service._prepare_bulk_load_constraints()

        mock_pg.assert_not_called()
        mock_ms.assert_not_called()


# ---------------------------------------------------------------------------
# _drop_postgresql_foreign_keys_for_bulk_load
# ---------------------------------------------------------------------------


class TestDropPostgresqlForeignKeysForBulkLoad:
    def _make_service(self):
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        engine.dialect.identifier_preparer.quote_schema.side_effect = (
            lambda s: f'"{s}"'
        )
        engine.dialect.identifier_preparer.quote.side_effect = lambda s: (
            f'"{s}"'
        )
        return MigrationService(engine, schema="staging"), engine

    def test_drops_each_constraint(self):
        service, engine = self._make_service()
        conn = engine.begin.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = [
            ("MyTable", "fk_one"),
            ("MyTable", "fk_two"),
        ]

        service._drop_postgresql_foreign_keys_for_bulk_load()

        assert conn.execute.call_count == 3  # 1 SELECT + 2 ALTER

    def test_no_constraints_executes_only_select(self):
        service, engine = self._make_service()
        conn = engine.begin.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = []

        service._drop_postgresql_foreign_keys_for_bulk_load()

        assert conn.execute.call_count == 1

    def test_alter_sql_contains_drop_constraint(self):
        service, engine = self._make_service()
        conn = engine.begin.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = [("T1", "fk_x")]

        service._drop_postgresql_foreign_keys_for_bulk_load()

        alter_sql = str(conn.execute.call_args_list[1].args[0])
        assert "DROP CONSTRAINT" in alter_sql
        assert "ALTER TABLE" in alter_sql


# ---------------------------------------------------------------------------
# _disable_sqlserver_constraints_for_bulk_load
# ---------------------------------------------------------------------------


class TestDisableSqlserverConstraintsForBulkLoad:
    def _make_service(self):
        engine = MagicMock()
        engine.dialect.name = "mssql"
        engine.dialect.identifier_preparer.quote_schema.side_effect = (
            lambda s: f'"{s}"'
        )
        engine.dialect.identifier_preparer.quote.side_effect = lambda s: (
            f'"{s}"'
        )
        return MigrationService(engine, schema="staging"), engine

    def test_disables_constraint_for_each_table(self):
        service, engine = self._make_service()
        conn = engine.begin.return_value.__enter__.return_value

        with patch("dpmcore.loaders.migration.inspect") as mock_inspect:
            mock_inspect.return_value.get_table_names.return_value = [
                "T1",
                "T2",
                "T3",
            ]
            service._disable_sqlserver_constraints_for_bulk_load()

        assert conn.execute.call_count == 3
        sql_str = str(conn.execute.call_args_list[0].args[0])
        assert "NOCHECK CONSTRAINT ALL" in sql_str

    def test_no_tables_executes_nothing(self):
        service, engine = self._make_service()
        conn = engine.begin.return_value.__enter__.return_value

        with patch("dpmcore.loaders.migration.inspect") as mock_inspect:
            mock_inspect.return_value.get_table_names.return_value = []
            service._disable_sqlserver_constraints_for_bulk_load()

        conn.execute.assert_not_called()


# ---------------------------------------------------------------------------
# _mssql_identity_columns
# ---------------------------------------------------------------------------


class TestMssqlIdentityColumns:
    def test_schema_none_returns_empty_dict_without_db_call(self):
        engine = MagicMock()
        service = MigrationService(engine)

        result = service._mssql_identity_columns()

        assert result == {}
        engine.connect.assert_not_called()

    def test_schema_set_returns_mapping_from_query(self):
        engine = MagicMock()
        conn = engine.connect.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = [
            ("TableA", "ColID"),
            ("TableB", "AnotherID"),
        ]

        service = MigrationService(engine, schema="staging")
        result = service._mssql_identity_columns()

        assert result == {"TableA": "ColID", "TableB": "AnotherID"}

    def test_schema_set_empty_result_returns_empty_dict(self):
        engine = MagicMock()
        conn = engine.connect.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = []

        service = MigrationService(engine, schema="staging")
        result = service._mssql_identity_columns()

        assert result == {}


# ---------------------------------------------------------------------------
# _load_table – identity-insert path
# ---------------------------------------------------------------------------


def _mssql_engine_mock() -> MagicMock:
    """MagicMock engine wired to a real MSSQL identifier preparer.

    The identifier preparer is what produces ``[name]`` quoting. Using
    the real MSSQL preparer (rather than letting the mock return
    further mocks) exercises the actual dialect quoting path.
    """
    from sqlalchemy.dialects.mssql import pyodbc as mssql_pyodbc

    engine = MagicMock()
    engine.dialect.identifier_preparer = (
        mssql_pyodbc.MSDialect_pyodbc().identifier_preparer
    )
    return engine


class TestLoadTableIdentityInsert:
    def test_identity_column_present_sets_identity_insert_on_and_off(self):
        engine = _mssql_engine_mock()
        conn = engine.begin.return_value.__enter__.return_value
        df = pd.DataFrame({"MyID": [1, 2], "Name": ["a", "b"]})

        service = MigrationService(engine, schema="myschema")
        with patch.object(df, "to_sql"):
            service._load_table(
                "UnknownTable", df, [], {"UnknownTable": "MyID"}
            )

        sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
        assert any("IDENTITY_INSERT" in s and "ON" in s for s in sqls)
        assert any("IDENTITY_INSERT" in s and "OFF" in s for s in sqls)

    def test_identity_insert_with_schema_uses_qualified_name(self):
        engine = _mssql_engine_mock()
        conn = engine.begin.return_value.__enter__.return_value
        df = pd.DataFrame({"MyID": [1]})

        service = MigrationService(engine, schema="myschema")
        with patch.object(df, "to_sql"):
            service._load_table("T1", df, [], {"T1": "MyID"})

        on_sql = str(conn.execute.call_args_list[0].args[0])
        # MSSQL preparer brackets table names always, schema only when
        # needed. Asserting the fully-qualified ``schema.[table]`` form
        # guards both the dot separator and the table-name quoting.
        assert "myschema.[T1]" in on_sql

    def test_identity_insert_without_schema_uses_unqualified_bracket_name(
        self,
    ):
        engine = _mssql_engine_mock()
        conn = engine.begin.return_value.__enter__.return_value
        df = pd.DataFrame({"MyID": [1]})

        service = MigrationService(engine)
        with patch.object(df, "to_sql"):
            service._load_table("T1", df, [], {"T1": "MyID"})

        on_sql = str(conn.execute.call_args_list[0].args[0])
        assert "[T1]" in on_sql
        assert "[None]" not in on_sql

    def test_identity_insert_brackets_reserved_table_name(self):
        """``_load_table`` must route reserved-word table names through
        the preparer so the emitted ``SET IDENTITY_INSERT`` is valid
        T-SQL. ``Order`` is a reserved keyword and not present in
        ``Base.metadata`` so the column-filtering path is skipped.
        """
        engine = _mssql_engine_mock()
        conn = engine.begin.return_value.__enter__.return_value
        df = pd.DataFrame({"MyID": [1]})

        service = MigrationService(engine, schema="dbo")
        with patch.object(df, "to_sql"):
            service._load_table("Order", df, [], {"Order": "MyID"})

        on_sql = str(conn.execute.call_args_list[0].args[0])
        assert "[Order]" in on_sql
        assert "dbo.[Order]" in on_sql

    def test_identity_column_not_in_df_uses_direct_to_sql(self):
        engine = _mssql_engine_mock()
        df = pd.DataFrame({"Name": ["a"]})

        service = MigrationService(engine)
        with patch.object(df, "to_sql") as mock_to_sql:
            service._load_table("T1", df, [], {"T1": "MyID"})

        mock_to_sql.assert_called_once()
        call_kwargs = mock_to_sql.call_args
        assert call_kwargs.args[1] is engine

    def test_identity_insert_off_called_even_when_to_sql_raises(self):
        engine = _mssql_engine_mock()
        conn = engine.begin.return_value.__enter__.return_value
        df = pd.DataFrame({"MyID": [1]})

        service = MigrationService(engine, schema="s")
        with patch.object(df, "to_sql", side_effect=RuntimeError("disk full")):
            with pytest.raises(MigrationError, match="disk full"):
                service._load_table("T1", df, [], {"T1": "MyID"})

        sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
        assert any("OFF" in s for s in sqls)
