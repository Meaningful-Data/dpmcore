from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

from dpmcore.services.database_update import (
    DatabaseUpdateError,
    DatabaseUpdateService,
)
from dpmcore.loaders.migration import MigrationError, MigrationResult


@pytest.fixture
def service():
    return DatabaseUpdateService()


@pytest.fixture
def fake_migration_result():
    return MigrationResult(
        tables_migrated=2,
        total_rows=10,
        table_details={"T1": 4, "T2": 6},
        warnings=[],
        backend_used="csv",
    )


def _engine_with_tables(tmp_path, tables: dict):
    db_path = tmp_path / "test.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        for name, count in tables.items():
            conn.execute(text(f'CREATE TABLE "{name}" (id INTEGER PRIMARY KEY)'))
            for i in range(count):
                conn.execute(text(f'INSERT INTO "{name}" VALUES ({i})'))
        conn.commit()
    return engine


def _empty_migration_result() -> MigrationResult:
    """Return a MigrationResult with no tables so _validate_sqlite always passes."""
    return MigrationResult(
        tables_migrated=0,
        total_rows=0,
        table_details={},
        warnings=[],
        backend_used="csv",
    )


class TestDetectTargetType:
    def test_sqlite_extension(self, service):
        assert service.detect_target_type("dpm.sqlite") == "sqlite"

    def test_sqlite3_extension(self, service):
        assert service.detect_target_type("dpm.sqlite3") == "sqlite"

    def test_db_extension(self, service):
        assert service.detect_target_type("dpm.db") == "sqlite"

    def test_sqlite_url(self, service):
        assert service.detect_target_type("sqlite:///dpm.db") == "sqlite"

    def test_postgresql_url(self, service):
        assert service.detect_target_type("postgresql://host/db") == "postgresql"

    def test_postgres_url(self, service):
        assert service.detect_target_type("postgres://host/db") == "postgresql"

    def test_mssql_url(self, service):
        assert service.detect_target_type("mssql+pyodbc://host/db") == "sqlserver"

    def test_unknown_raises(self, service):
        with pytest.raises(DatabaseUpdateError, match="Could not detect target type"):
            service.detect_target_type("unknown_format")


class TestSqlitePathFromTarget:
    def test_plain_path(self, service):
        assert service._sqlite_path_from_target("data/dpm.sqlite") == Path("data/dpm.sqlite")

    def test_sqlite_url(self, service):
        assert service._sqlite_path_from_target("sqlite:///data/dpm.db") == Path("data/dpm.db")

    def test_sqlite_url_two_slashes_raises(self, service):
        with pytest.raises(DatabaseUpdateError, match="sqlite:///"):
            service._sqlite_path_from_target("sqlite://data/dpm.db")


class TestUpdateDispatch:
    def test_unsupported_target_raises(self, service):
        with pytest.raises(DatabaseUpdateError, match="not implemented"):
            service.update(target="postgresql://host/db")

    def test_calls_update_sqlite_from_csv_dir(self, service, tmp_path):
        target = tmp_path / "out.sqlite"
        with patch.object(service, "_update_sqlite", return_value=MagicMock()) as mock_update:
            service.update(target=str(target), source_dir=str(tmp_path))

        kw = mock_update.call_args.kwargs
        assert kw["csv_dir"] == tmp_path
        assert kw["used_access_file"] is False
        assert kw["source"] == str(tmp_path)

    def test_calls_export_safely_with_access_file(self, service, tmp_path):
        target = tmp_path / "out.sqlite"
        access_file = tmp_path / "source.accdb"
        access_file.touch()

        with (
            patch("dpmcore.services.database_update.ExportCsvService") as MockExport,
            patch.object(service, "_update_sqlite", return_value=MagicMock()),
        ):
            MockExport.return_value.export_safely.return_value = MagicMock()
            service.update(target=str(target), access_file=str(access_file))

        MockExport.return_value.export_safely.assert_called_once()
        assert MockExport.return_value.export_safely.call_args.args[0] == str(access_file)

    def test_used_access_file_flag_true_when_provided(self, service, tmp_path):
        target = tmp_path / "out.sqlite"
        access_file = tmp_path / "source.accdb"
        access_file.touch()

        with (
            patch("dpmcore.services.database_update.ExportCsvService") as MockExport,
            patch.object(service, "_update_sqlite", return_value=MagicMock()) as mock_update,
        ):
            MockExport.return_value.export_safely.return_value = MagicMock()
            service.update(target=str(target), access_file=str(access_file))

        assert mock_update.call_args.kwargs["used_access_file"] is True


class TestUpdateSqliteInternal:
    """Tests for _update_sqlite.

    MigrationService is mocked to return an empty result (no tables).  This
    lets create_engine and _validate_sqlite run with real SQLite, so every
    branch in _update_sqlite, _replace_sqlite_file, and _validate_sqlite is
    actually executed instead of short-circuited by a MagicMock engine.
    """

    def _run(self, service, target, tmp_path, **kwargs):
        """Call _update_sqlite with MigrationService mocked to return no tables."""
        with patch("dpmcore.services.database_update.MigrationService") as MockMigration:
            MockMigration.return_value.migrate_from_csv_dir.return_value = (
                _empty_migration_result()
            )
            return service._update_sqlite(
                target_path=target,
                csv_dir=tmp_path,
                source=str(tmp_path),
                used_access_file=False,
                ecb_validations_file=None,
                **kwargs,
            )

    def test_success_swaps_file_into_place(self, service, tmp_path):
        target = tmp_path / "dpm.sqlite"
        result = self._run(service, target, tmp_path)

        assert target.exists()
        assert result.target_type == "sqlite"
        assert result.target == target
        assert result.used_access_file is False
        assert result.ecb_validations_imported is False

    def test_temp_file_removed_after_success(self, service, tmp_path):
        target = tmp_path / "dpm.sqlite"
        self._run(service, target, tmp_path)

        assert list(tmp_path.glob(".dpm.sqlite.tmp-*")) == []

    def test_backup_removed_after_success_when_target_existed(self, service, tmp_path):
        target = tmp_path / "dpm.sqlite"
        target.write_bytes(b"old")

        self._run(service, target, tmp_path)

        assert list(tmp_path.glob("dpm.sqlite.backup-*")) == []
        assert target.exists()

    def test_result_contains_correct_migration_result(self, service, fake_migration_result, tmp_path):
        target = tmp_path / "dpm.sqlite"

        with patch("dpmcore.services.database_update.MigrationService") as MockMigration:
            MockMigration.return_value.migrate_from_csv_dir.return_value = fake_migration_result
            with patch.object(DatabaseUpdateService, "_validate_sqlite"):
                result = service._update_sqlite(
                    target_path=target,
                    csv_dir=tmp_path,
                    source=str(tmp_path),
                    used_access_file=False,
                    ecb_validations_file=None,
                )

        assert result.migration_result is fake_migration_result

    def test_migration_error_raises_database_update_error(self, service, tmp_path):
        target = tmp_path / "dpm.sqlite"

        with patch("dpmcore.services.database_update.MigrationService") as MockMigration:
            MockMigration.return_value.migrate_from_csv_dir.side_effect = MigrationError("bad csv")

            with pytest.raises(DatabaseUpdateError, match="bad csv"):
                service._update_sqlite(
                    target_path=target,
                    csv_dir=tmp_path,
                    source=str(tmp_path),
                    used_access_file=False,
                    ecb_validations_file=None,
                )

        assert not target.exists()

    def test_generic_exception_wrapped_as_database_update_error(self, service, tmp_path):
        target = tmp_path / "dpm.sqlite"

        with patch("dpmcore.services.database_update.MigrationService") as MockMigration:
            MockMigration.return_value.migrate_from_csv_dir.side_effect = RuntimeError("disk full")

            with pytest.raises(DatabaseUpdateError, match="disk full"):
                service._update_sqlite(
                    target_path=target,
                    csv_dir=tmp_path,
                    source=str(tmp_path),
                    used_access_file=False,
                    ecb_validations_file=None,
                )

    def test_existing_target_restored_on_migration_error(self, service, tmp_path):
        target = tmp_path / "dpm.sqlite"
        target.write_bytes(b"old content")

        with patch("dpmcore.services.database_update.MigrationService") as MockMigration:
            MockMigration.return_value.migrate_from_csv_dir.side_effect = MigrationError("fail")

            with pytest.raises(DatabaseUpdateError):
                service._update_sqlite(
                    target_path=target,
                    csv_dir=tmp_path,
                    source=str(tmp_path),
                    used_access_file=False,
                    ecb_validations_file=None,
                )

        assert target.exists()
        assert target.read_bytes() == b"old content"

    def test_target_not_a_file_raises(self, service, tmp_path):
        target = tmp_path / "dpm.sqlite"
        target.mkdir()

        with pytest.raises(DatabaseUpdateError, match="not a file"):
            service._update_sqlite(
                target_path=target,
                csv_dir=tmp_path,
                source=str(tmp_path),
                used_access_file=False,
                ecb_validations_file=None,
            )

    def test_ecb_validations_imported(self, service, tmp_path):
        target = tmp_path / "dpm.sqlite"
        ecb_file = tmp_path / "ecb.csv"
        ecb_file.write_text("vr_code,start_release\nV1,4.0\n")

        with (
            patch("dpmcore.services.database_update.MigrationService") as MockMigration,
            patch("dpmcore.services.database_update.EcbValidationsImportService") as MockEcb,
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = _empty_migration_result()
            result = service._update_sqlite(
                target_path=target,
                csv_dir=tmp_path,
                source=str(tmp_path),
                used_access_file=False,
                ecb_validations_file=str(ecb_file),
            )

        MockEcb.return_value.import_csv.assert_called_once_with(str(ecb_file))
        assert result.ecb_validations_imported is True


class TestDetectTargetTypeEdgeCases:
    def test_uppercase_sqlite_extension(self, service):
        assert service.detect_target_type("DPM.SQLITE") == "sqlite"

    def test_uppercase_db_extension(self, service):
        assert service.detect_target_type("DPM.DB") == "sqlite"

    def test_sqlite3_extension(self, service):
        assert service.detect_target_type("archive.sqlite3") == "sqlite"

    def test_sqlserver_url(self, service):
        assert service.detect_target_type("sqlserver://host/db") == "sqlserver"


class TestSqlitePathFromTargetEdgeCases:
    def test_url_encoded_spaces_in_path(self, service):
        assert service._sqlite_path_from_target("sqlite:///path/to/my%20file.db") == Path(
            "path/to/my file.db"
        )


class TestUpdateDispatchEdgeCases:
    def test_ecb_validations_file_passed_to_update_sqlite(self, service, tmp_path):
        target = tmp_path / "out.sqlite"
        ecb_file = tmp_path / "ecb.csv"
        ecb_file.touch()

        with patch.object(service, "_update_sqlite", return_value=MagicMock()) as mock_update:
            service.update(target=str(target), ecb_validations_file=str(ecb_file))

        assert mock_update.call_args.kwargs["ecb_validations_file"] == str(ecb_file)

    def test_no_ecb_file_passes_none(self, service, tmp_path):
        target = tmp_path / "out.sqlite"

        with patch.object(service, "_update_sqlite", return_value=MagicMock()) as mock_update:
            service.update(target=str(target))

        assert mock_update.call_args.kwargs["ecb_validations_file"] is None


class TestReplaceSqliteFile:
    def test_fresh_target_moves_temp_to_target(self, service, tmp_path):
        temp = tmp_path / "temp.db"
        temp.write_bytes(b"new")
        target = tmp_path / "target.db"
        backup = tmp_path / "backup.db"

        service._replace_sqlite_file(target_path=target, temp_path=temp, backup_path=backup)

        assert target.read_bytes() == b"new"
        assert not temp.exists()
        assert not backup.exists()

    def test_existing_target_moved_to_backup(self, service, tmp_path):
        temp = tmp_path / "temp.db"
        temp.write_bytes(b"new")
        target = tmp_path / "target.db"
        target.write_bytes(b"old")
        backup = tmp_path / "backup.db"

        service._replace_sqlite_file(target_path=target, temp_path=temp, backup_path=backup)

        assert target.read_bytes() == b"new"
        assert backup.read_bytes() == b"old"
        assert not temp.exists()

    def test_temp_replace_fails_restores_backup(self, service, tmp_path):
        temp = tmp_path / "temp.db"
        temp.write_bytes(b"new")
        target = tmp_path / "target.db"
        target.write_bytes(b"old")
        backup = tmp_path / "backup.db"

        with patch.object(Path, "replace", side_effect=[None, OSError("disk full")]):
            with pytest.raises(OSError, match="disk full"):
                service._replace_sqlite_file(
                    target_path=target, temp_path=temp, backup_path=backup
                )

        # original is restored; backup cleaned up by restore
        assert target.read_bytes() == b"old"
        assert not backup.exists()


class TestRestoreSqliteBackup:
    def test_no_backup_is_a_noop(self, service, tmp_path):
        target = tmp_path / "target.db"
        backup = tmp_path / "backup.db"

        service._restore_sqlite_backup(target, backup)  # must not raise

        assert not target.exists()

    def test_restores_backup_when_target_absent(self, service, tmp_path):
        target = tmp_path / "target.db"
        backup = tmp_path / "backup.db"
        backup.write_bytes(b"old")

        service._restore_sqlite_backup(target, backup)

        assert target.read_bytes() == b"old"
        assert not backup.exists()

    def test_removes_partial_target_before_restoring(self, service, tmp_path):
        target = tmp_path / "target.db"
        target.write_bytes(b"partial")
        backup = tmp_path / "backup.db"
        backup.write_bytes(b"old")

        service._restore_sqlite_backup(target, backup)

        assert target.read_bytes() == b"old"
        assert not backup.exists()


class TestUpdateSqliteInternalEdgeCases:
    def test_first_validation_failure_raises_and_preserves_existing_target(
        self, service, tmp_path
    ):
        target = tmp_path / "dpm.sqlite"
        target.write_bytes(b"original")

        with (
            patch("dpmcore.services.database_update.MigrationService") as MockMigration,
            patch.object(
                DatabaseUpdateService,
                "_validate_sqlite",
                side_effect=DatabaseUpdateError("first validation failed"),
            ),
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = _empty_migration_result()

            with pytest.raises(DatabaseUpdateError, match="first validation failed"):
                service._update_sqlite(
                    target_path=target,
                    csv_dir=tmp_path,
                    source=str(tmp_path),
                    used_access_file=False,
                    ecb_validations_file=None,
                )

        assert target.read_bytes() == b"original"
        assert not list(tmp_path.glob(".dpm.sqlite.tmp-*"))

    def test_final_validation_failure_restores_old_target(self, service, tmp_path):
        target = tmp_path / "dpm.sqlite"
        target.write_bytes(b"old content")

        validate_calls = []

        def _validate(engine, migration_result):
            validate_calls.append(1)
            if len(validate_calls) == 2:
                raise DatabaseUpdateError("final validation failed")

        with (
            patch("dpmcore.services.database_update.MigrationService") as MockMigration,
            patch.object(DatabaseUpdateService, "_validate_sqlite", side_effect=_validate),
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = _empty_migration_result()

            with pytest.raises(DatabaseUpdateError, match="final validation failed"):
                service._update_sqlite(
                    target_path=target,
                    csv_dir=tmp_path,
                    source=str(tmp_path),
                    used_access_file=False,
                    ecb_validations_file=None,
                )

        assert target.read_bytes() == b"old content"
        assert not list(tmp_path.glob("dpm.sqlite.backup-*"))

    def test_target_parent_dirs_created_if_missing(self, service, tmp_path):
        target = tmp_path / "nested" / "deep" / "dpm.sqlite"

        with patch("dpmcore.services.database_update.MigrationService") as MockMigration:
            MockMigration.return_value.migrate_from_csv_dir.return_value = _empty_migration_result()
            service._update_sqlite(
                target_path=target,
                csv_dir=tmp_path,
                source=str(tmp_path),
                used_access_file=False,
                ecb_validations_file=None,
            )

        assert target.exists()


class TestValidateSqlite:
    def test_passes_with_correct_tables_and_rows(self, service, tmp_path):
        migration_result = MigrationResult(
            tables_migrated=2,
            total_rows=10,
            table_details={"T1": 4, "T2": 6},
            warnings=[],
            backend_used="csv",
        )
        engine = _engine_with_tables(tmp_path, {"T1": 4, "T2": 6})
        try:
            service._validate_sqlite(engine, migration_result)
        finally:
            engine.dispose()

    def test_raises_on_missing_table(self, service, tmp_path):
        migration_result = MigrationResult(
            tables_migrated=2,
            total_rows=10,
            table_details={"T1": 4, "Missing": 6},
            warnings=[],
            backend_used="csv",
        )
        engine = _engine_with_tables(tmp_path, {"T1": 4})
        try:
            with pytest.raises(DatabaseUpdateError, match="Missing tables"):
                service._validate_sqlite(engine, migration_result)
        finally:
            engine.dispose()

    def test_raises_on_row_count_mismatch(self, service, tmp_path):
        migration_result = MigrationResult(
            tables_migrated=1,
            total_rows=5,
            table_details={"T1": 5},
            warnings=[],
            backend_used="csv",
        )
        engine = _engine_with_tables(tmp_path, {"T1": 3})
        try:
            with pytest.raises(DatabaseUpdateError, match="Expected 5 rows, got 3"):
                service._validate_sqlite(engine, migration_result)
        finally:
            engine.dispose()

    def test_extra_tables_in_db_do_not_cause_failure(self, service, tmp_path):
        migration_result = MigrationResult(
            tables_migrated=1,
            total_rows=4,
            table_details={"T1": 4},
            warnings=[],
            backend_used="csv",
        )
        engine = _engine_with_tables(tmp_path, {"T1": 4, "Extra": 2})
        try:
            service._validate_sqlite(engine, migration_result)  # must not raise
        finally:
            engine.dispose()

    def test_empty_table_details_passes(self, service, tmp_path):
        migration_result = MigrationResult(
            tables_migrated=0,
            total_rows=0,
            table_details={},
            warnings=[],
            backend_used="csv",
        )
        engine = _engine_with_tables(tmp_path, {})
        try:
            service._validate_sqlite(engine, migration_result)  # must not raise
        finally:
            engine.dispose()
