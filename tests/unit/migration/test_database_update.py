from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

from dpmcore.loaders.migration import MigrationError, MigrationResult
from dpmcore.orm.base import Base
from dpmcore.services.database_update import (
    DatabaseUpdateError,
    DatabaseUpdateService,
)


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
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as conn:
        for name, count in tables.items():
            conn.execute(
                text(f'CREATE TABLE "{name}" (id INTEGER PRIMARY KEY)')
            )
            for i in range(count):
                conn.execute(text(f'INSERT INTO "{name}" VALUES ({i})'))  # noqa: S608
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
        assert (
            service.detect_target_type("postgresql://host/db") == "postgresql"
        )

    def test_postgres_url(self, service):
        assert service.detect_target_type("postgres://host/db") == "postgresql"

    def test_mssql_url(self, service):
        assert (
            service.detect_target_type("mssql+pyodbc://host/db") == "sqlserver"
        )

    def test_unknown_raises(self, service):
        with pytest.raises(
            DatabaseUpdateError, match="Could not detect target type"
        ):
            service.detect_target_type("unknown_format")


class TestSqlitePathFromTarget:
    def test_plain_path(self, service):
        assert service._sqlite_path_from_target("data/dpm.sqlite") == Path(
            "data/dpm.sqlite"
        )

    def test_sqlite_url(self, service):
        assert service._sqlite_path_from_target(
            "sqlite:///data/dpm.db"
        ) == Path("data/dpm.db")

    def test_sqlite_url_two_slashes_raises(self, service):
        with pytest.raises(DatabaseUpdateError, match="sqlite:///"):
            service._sqlite_path_from_target("sqlite://data/dpm.db")


class TestUpdateDispatch:
    def test_unsupported_target_raises(self, service):
        with pytest.raises(DatabaseUpdateError, match="Could not detect"):
            service.update(target="oracle://host/db")

    def test_calls_update_sqlite_from_csv_dir(self, service, tmp_path):
        target = tmp_path / "out.sqlite"
        with patch.object(
            service, "_update_sqlite", return_value=MagicMock()
        ) as mock_update:
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
            patch(
                "dpmcore.services.database_update.ExportCsvService"
            ) as MockExport,
            patch.object(service, "_update_sqlite", return_value=MagicMock()),
        ):
            MockExport.return_value.export_safely.return_value = MagicMock()
            service.update(target=str(target), access_file=str(access_file))

        MockExport.return_value.export_safely.assert_called_once()
        assert MockExport.return_value.export_safely.call_args.args[0] == str(
            access_file
        )

    def test_used_access_file_flag_true_when_provided(self, service, tmp_path):
        target = tmp_path / "out.sqlite"
        access_file = tmp_path / "source.accdb"
        access_file.touch()

        with (
            patch(
                "dpmcore.services.database_update.ExportCsvService"
            ) as MockExport,
            patch.object(
                service, "_update_sqlite", return_value=MagicMock()
            ) as mock_update,
        ):
            MockExport.return_value.export_safely.return_value = MagicMock()
            service.update(target=str(target), access_file=str(access_file))

        assert mock_update.call_args.kwargs["used_access_file"] is True

    def test_dry_run_and_keep_staging_forwarded_to_update_sqlite(
        self, service, tmp_path
    ):
        target = tmp_path / "out.sqlite"
        with patch.object(
            service, "_update_sqlite", return_value=MagicMock()
        ) as mock_update:
            service.update(
                target=str(target),
                source_dir=str(tmp_path),
                dry_run=True,
                keep_staging=True,
            )

        kw = mock_update.call_args.kwargs
        assert kw["dry_run"] is True
        assert kw["keep_staging"] is True


class TestUpdateSqliteInternal:
    """Tests for _update_sqlite.

    MigrationService is mocked to return an empty result (no tables).  This
    lets create_engine and _validate_sqlite run with real SQLite, so every
    branch in _update_sqlite, _replace_sqlite_file, and _validate_sqlite is
    actually executed instead of short-circuited by a MagicMock engine.
    """

    def _run(self, service, target, tmp_path, **kwargs):
        """Call _update_sqlite with MigrationService mocked to return no tables."""
        with (
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch.object(DatabaseUpdateService, "_validate_csv_count"),
            patch.object(DatabaseUpdateService, "_validate_required_content"),
        ):
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
        assert result.target == str(target)
        assert result.used_access_file is False
        assert result.ecb_validations_imported is False

    def test_migrate_called_with_output_path_to_prevent_relocation(
        self, service, tmp_path
    ):
        # Regression: without output_path, MigrationService._finalize renames
        # the temp file, leaving the engine pointing at a non-existent path and
        # causing _validate_sqlite to see an empty DB ("missing tables").
        target = tmp_path / "dpm.sqlite"
        with (
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch.object(DatabaseUpdateService, "_validate_csv_count"),
            patch.object(DatabaseUpdateService, "_validate_required_content"),
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = (
                _empty_migration_result()
            )
            service._update_sqlite(
                target_path=target,
                csv_dir=tmp_path,
                source=str(tmp_path),
                used_access_file=False,
                ecb_validations_file=None,
            )

        call_kwargs = (
            MockMigration.return_value.migrate_from_csv_dir.call_args.kwargs
        )
        output_path = call_kwargs["output_path"]
        assert output_path.parent == tmp_path
        assert output_path.name.startswith(".dpm.sqlite.tmp-")

    def test_temp_file_removed_after_success(self, service, tmp_path):
        target = tmp_path / "dpm.sqlite"
        self._run(service, target, tmp_path)

        assert list(tmp_path.glob(".dpm.sqlite.tmp-*")) == []

    def test_backup_removed_after_success_when_target_existed(
        self, service, tmp_path
    ):
        target = tmp_path / "dpm.sqlite"
        target.write_bytes(b"old")

        self._run(service, target, tmp_path)

        assert list(tmp_path.glob("dpm.sqlite.backup-*")) == []
        assert target.exists()

    def test_result_contains_correct_migration_result(
        self, service, fake_migration_result, tmp_path
    ):
        target = tmp_path / "dpm.sqlite"

        with (
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch.object(DatabaseUpdateService, "_validate_csv_count"),
            patch.object(DatabaseUpdateService, "_validate_sqlite"),
            patch.object(service, "_replace_sqlite_file"),
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = (
                fake_migration_result
            )
            result = service._update_sqlite(
                target_path=target,
                csv_dir=tmp_path,
                source=str(tmp_path),
                used_access_file=False,
                ecb_validations_file=None,
            )

        assert result.migration_result is fake_migration_result

    def test_migration_error_raises_database_update_error(
        self, service, tmp_path
    ):
        target = tmp_path / "dpm.sqlite"

        with patch(
            "dpmcore.services.database_update.MigrationService"
        ) as MockMigration:
            MockMigration.return_value.migrate_from_csv_dir.side_effect = (
                MigrationError("bad csv")
            )

            with pytest.raises(DatabaseUpdateError, match="bad csv"):
                service._update_sqlite(
                    target_path=target,
                    csv_dir=tmp_path,
                    source=str(tmp_path),
                    used_access_file=False,
                    ecb_validations_file=None,
                )

        assert not target.exists()

    def test_generic_exception_wrapped_as_database_update_error(
        self, service, tmp_path
    ):
        target = tmp_path / "dpm.sqlite"

        with patch(
            "dpmcore.services.database_update.MigrationService"
        ) as MockMigration:
            MockMigration.return_value.migrate_from_csv_dir.side_effect = (
                RuntimeError("disk full")
            )

            with pytest.raises(DatabaseUpdateError, match="disk full"):
                service._update_sqlite(
                    target_path=target,
                    csv_dir=tmp_path,
                    source=str(tmp_path),
                    used_access_file=False,
                    ecb_validations_file=None,
                )

    def test_existing_target_restored_on_migration_error(
        self, service, tmp_path
    ):
        target = tmp_path / "dpm.sqlite"
        target.write_bytes(b"old content")

        with patch(
            "dpmcore.services.database_update.MigrationService"
        ) as MockMigration:
            MockMigration.return_value.migrate_from_csv_dir.side_effect = (
                MigrationError("fail")
            )

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
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch(
                "dpmcore.services.database_update.EcbValidationsImportService"
            ) as MockEcb,
            patch.object(DatabaseUpdateService, "_validate_csv_count"),
            patch.object(DatabaseUpdateService, "_validate_required_content"),
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = (
                _empty_migration_result()
            )
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
        assert service._sqlite_path_from_target(
            "sqlite:///path/to/my%20file.db"
        ) == Path("path/to/my file.db")


class TestUpdateDispatchEdgeCases:
    def test_ecb_validations_file_passed_to_update_sqlite(
        self, service, tmp_path
    ):
        target = tmp_path / "out.sqlite"
        ecb_file = tmp_path / "ecb.csv"
        ecb_file.touch()

        with patch.object(
            service, "_update_sqlite", return_value=MagicMock()
        ) as mock_update:
            service.update(
                target=str(target), ecb_validations_file=str(ecb_file)
            )

        assert mock_update.call_args.kwargs["ecb_validations_file"] == str(
            ecb_file
        )

    def test_no_ecb_file_passes_none(self, service, tmp_path):
        target = tmp_path / "out.sqlite"

        with patch.object(
            service, "_update_sqlite", return_value=MagicMock()
        ) as mock_update:
            service.update(target=str(target))

        assert mock_update.call_args.kwargs["ecb_validations_file"] is None


class TestReplaceSqliteFile:
    def test_fresh_target_moves_temp_to_target(self, service, tmp_path):
        temp = tmp_path / "temp.db"
        temp.write_bytes(b"new")
        target = tmp_path / "target.db"
        backup = tmp_path / "backup.db"

        service._replace_sqlite_file(
            target_path=target, temp_path=temp, backup_path=backup
        )

        assert target.read_bytes() == b"new"
        assert not temp.exists()
        assert not backup.exists()

    def test_existing_target_moved_to_backup(self, service, tmp_path):
        temp = tmp_path / "temp.db"
        temp.write_bytes(b"new")
        target = tmp_path / "target.db"
        target.write_bytes(b"old")
        backup = tmp_path / "backup.db"

        service._replace_sqlite_file(
            target_path=target, temp_path=temp, backup_path=backup
        )

        assert target.read_bytes() == b"new"
        assert backup.read_bytes() == b"old"
        assert not temp.exists()

    def test_temp_replace_fails_restores_backup(self, service, tmp_path):
        temp = tmp_path / "temp.db"
        temp.write_bytes(b"new")
        target = tmp_path / "target.db"
        target.write_bytes(b"old")
        backup = tmp_path / "backup.db"

        with patch.object(
            Path, "replace", side_effect=[None, OSError("disk full")]
        ):
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
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch.object(DatabaseUpdateService, "_validate_csv_count"),
            patch.object(
                DatabaseUpdateService,
                "_validate_sqlite",
                side_effect=DatabaseUpdateError("first validation failed"),
            ),
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = (
                _empty_migration_result()
            )

            with pytest.raises(
                DatabaseUpdateError, match="first validation failed"
            ):
                service._update_sqlite(
                    target_path=target,
                    csv_dir=tmp_path,
                    source=str(tmp_path),
                    used_access_file=False,
                    ecb_validations_file=None,
                )

        assert target.read_bytes() == b"original"
        assert not list(tmp_path.glob(".dpm.sqlite.tmp-*"))

    def test_final_validation_failure_restores_old_target(
        self, service, tmp_path
    ):
        target = tmp_path / "dpm.sqlite"
        target.write_bytes(b"old content")

        validate_calls = []

        def _validate(engine, migration_result, **kwargs):
            validate_calls.append(1)
            if len(validate_calls) == 2:
                raise DatabaseUpdateError("final validation failed")

        with (
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch.object(DatabaseUpdateService, "_validate_csv_count"),
            patch.object(
                DatabaseUpdateService,
                "_validate_sqlite",
                side_effect=_validate,
            ),
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = (
                _empty_migration_result()
            )

            with pytest.raises(
                DatabaseUpdateError, match="final validation failed"
            ):
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

        with (
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch.object(DatabaseUpdateService, "_validate_csv_count"),
            patch.object(DatabaseUpdateService, "_validate_required_content"),
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = (
                _empty_migration_result()
            )
            service._update_sqlite(
                target_path=target,
                csv_dir=tmp_path,
                source=str(tmp_path),
                used_access_file=False,
                ecb_validations_file=None,
            )

        assert target.exists()

    def test_validation_exact_counts_logic_with_ecb_file(
        self, service, tmp_path
    ):
        # Regression guard: when an ECB file is provided the pre-ECB validation
        # must use exact_counts=True, and both the post-ECB and final validations
        # must use exact_counts=False (ECB import may add rows beyond the CSV count).
        target = tmp_path / "dpm.sqlite"
        ecb_file = str(tmp_path / "ecb.csv")
        validate_calls = []

        def capture(engine, migration_result, **kwargs):
            validate_calls.append(kwargs)

        with (
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch(
                "dpmcore.services.database_update.EcbValidationsImportService"
            ),
            patch.object(DatabaseUpdateService, "_validate_csv_count"),
            patch.object(DatabaseUpdateService, "_replace_sqlite_file"),
            patch.object(
                DatabaseUpdateService, "_validate_sqlite", side_effect=capture
            ),
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = (
                _empty_migration_result()
            )
            service._update_sqlite(
                target_path=target,
                csv_dir=tmp_path,
                source=str(tmp_path),
                used_access_file=False,
                ecb_validations_file=ecb_file,
            )

        assert len(validate_calls) == 3
        assert validate_calls[0]["exact_counts"] is True  # pre-ECB: strict
        assert (
            validate_calls[1]["exact_counts"] is False
        )  # post-ECB: allows extra rows
        assert (
            validate_calls[2]["exact_counts"] is False
        )  # final: allows extra rows


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
            with patch.object(service, "_validate_required_content"):
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
            with pytest.raises(
                DatabaseUpdateError, match="Expected 5 rows, got 3"
            ):
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
            with patch.object(service, "_validate_required_content"):
                service._validate_sqlite(
                    engine, migration_result
                )  # must not raise
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
            with patch.object(service, "_validate_required_content"):
                service._validate_sqlite(
                    engine, migration_result
                )  # must not raise
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# _validate_sqlite – exact_counts parameter
# ---------------------------------------------------------------------------


class TestValidateSqliteExactCounts:
    def test_exact_counts_false_passes_when_actual_equals_expected(
        self, service, tmp_path
    ):
        migration_result = MigrationResult(
            tables_migrated=1,
            total_rows=4,
            table_details={"T1": 4},
            warnings=[],
            backend_used="csv",
        )
        engine = _engine_with_tables(tmp_path, {"T1": 4})
        try:
            with patch.object(service, "_validate_required_content"):
                service._validate_sqlite(
                    engine, migration_result, exact_counts=False
                )
        finally:
            engine.dispose()

    def test_exact_counts_false_passes_when_actual_exceeds_expected(
        self, service, tmp_path
    ):
        migration_result = MigrationResult(
            tables_migrated=1,
            total_rows=4,
            table_details={"T1": 4},
            warnings=[],
            backend_used="csv",
        )
        engine = _engine_with_tables(tmp_path, {"T1": 6})
        try:
            with patch.object(service, "_validate_required_content"):
                service._validate_sqlite(
                    engine, migration_result, exact_counts=False
                )
        finally:
            engine.dispose()

    def test_exact_counts_false_raises_when_actual_below_expected(
        self, service, tmp_path
    ):
        migration_result = MigrationResult(
            tables_migrated=1,
            total_rows=5,
            table_details={"T1": 5},
            warnings=[],
            backend_used="csv",
        )
        engine = _engine_with_tables(tmp_path, {"T1": 3})
        try:
            with pytest.raises(DatabaseUpdateError, match="at least 5 rows"):
                service._validate_sqlite(
                    engine, migration_result, exact_counts=False
                )
        finally:
            engine.dispose()

    def test_exact_counts_true_raises_when_actual_exceeds_expected(
        self, service, tmp_path
    ):
        migration_result = MigrationResult(
            tables_migrated=1,
            total_rows=4,
            table_details={"T1": 4},
            warnings=[],
            backend_used="csv",
        )
        engine = _engine_with_tables(tmp_path, {"T1": 6})
        try:
            with pytest.raises(
                DatabaseUpdateError, match="Expected 4 rows, got 6"
            ):
                service._validate_sqlite(
                    engine, migration_result, exact_counts=True
                )
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# update() dispatch to _update_staged_database
# ---------------------------------------------------------------------------


class TestUpdateDispatchStagedDatabase:
    def test_postgresql_target_calls_update_staged_database(
        self, service, tmp_path
    ):
        with patch.object(
            service, "_update_staged_database", return_value=MagicMock()
        ) as mock_staged:
            service.update(
                target="postgresql://host/db", source_dir=str(tmp_path)
            )

        kw = mock_staged.call_args.kwargs
        assert kw["target_type"] == "postgresql"
        assert kw["active_schema"] == "public"
        assert kw["target"] == "postgresql://host/db"

    def test_sqlserver_target_calls_update_staged_database(
        self, service, tmp_path
    ):
        with patch.object(
            service, "_update_staged_database", return_value=MagicMock()
        ) as mock_staged:
            service.update(
                target="mssql+pyodbc://host/db", source_dir=str(tmp_path)
            )

        kw = mock_staged.call_args.kwargs
        assert kw["target_type"] == "sqlserver"
        assert kw["active_schema"] == "dbo"

    def test_postgresql_passes_ecb_file(self, service, tmp_path):
        ecb = tmp_path / "ecb.csv"
        ecb.touch()

        with patch.object(
            service, "_update_staged_database", return_value=MagicMock()
        ) as mock_staged:
            service.update(
                target="postgresql://host/db", ecb_validations_file=str(ecb)
            )

        kw = mock_staged.call_args.kwargs
        assert kw["ecb_validations_file"] == str(ecb)


# ---------------------------------------------------------------------------
# _create_target_engine
# ---------------------------------------------------------------------------


class TestCreateTargetEngine:
    def test_sqlserver_creates_engine_with_fast_executemany(self, service):
        with patch(
            "dpmcore.services.database_update.create_engine"
        ) as mock_create:
            mock_create.return_value = MagicMock()
            service._create_target_engine(
                "mssql+pyodbc://host/db", "sqlserver"
            )

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs.get("fast_executemany") is True

    def test_non_sqlserver_creates_engine_without_fast_executemany(
        self, service
    ):
        with patch(
            "dpmcore.services.database_update.create_engine"
        ) as mock_create:
            mock_create.return_value = MagicMock()
            service._create_target_engine("postgresql://host/db", "postgresql")

        call_kwargs = mock_create.call_args.kwargs
        assert "fast_executemany" not in call_kwargs


# ---------------------------------------------------------------------------
# _engine_for_schema
# ---------------------------------------------------------------------------


class TestEngineForSchema:
    def test_creates_schema_translate_map(self, service):
        engine = MagicMock()
        translated = MagicMock()
        engine.execution_options.return_value = translated

        result = service._engine_for_schema(engine, "staging")

        engine.execution_options.assert_called_once_with(
            schema_translate_map={None: "staging"}
        )
        assert result is translated


# ---------------------------------------------------------------------------
# _ordered_tables_for_schema
# ---------------------------------------------------------------------------


class TestOrderedTablesForSchema:
    def _mock_engine_with_tables(self, tables):
        engine = MagicMock()
        inspector = MagicMock()
        inspector.get_table_names.return_value = list(tables)
        return engine, inspector

    def test_orm_tables_come_before_extras(self, service):
        orm_names = {t.name for t in Base.metadata.sorted_tables}
        one_orm = next(iter(orm_names))

        engine, inspector = self._mock_engine_with_tables(
            [one_orm, "ExtraTable"]
        )

        with patch(
            "dpmcore.services.database_update.inspect", return_value=inspector
        ):
            result = service._ordered_tables_for_schema(
                engine=engine, schema="s"
            )

        assert result.index(one_orm) < result.index("ExtraTable")

    def test_extra_tables_sorted_alphabetically(self, service):
        engine, inspector = self._mock_engine_with_tables(["Zzz", "Aaa"])

        with patch(
            "dpmcore.services.database_update.inspect", return_value=inspector
        ):
            result = service._ordered_tables_for_schema(
                engine=engine, schema="s"
            )

        extras = [t for t in result if t in {"Aaa", "Zzz"}]
        assert extras == ["Aaa", "Zzz"]

    def test_reverse_orm_order(self, service):
        orm_names_forward = [t.name for t in Base.metadata.sorted_tables]
        if len(orm_names_forward) < 2:
            pytest.skip("need at least two ORM tables")

        engine, inspector = self._mock_engine_with_tables(
            orm_names_forward[:2]
        )

        with patch(
            "dpmcore.services.database_update.inspect", return_value=inspector
        ):
            fwd = service._ordered_tables_for_schema(
                engine=engine, schema="s", reverse_orm_order=False
            )
            rev = service._ordered_tables_for_schema(
                engine=engine, schema="s", reverse_orm_order=True
            )

        assert list(fwd) == list(reversed(rev))


# ---------------------------------------------------------------------------
# _create_schema_if_missing
# ---------------------------------------------------------------------------


class TestCreateSchemaIfMissing:
    def test_skips_create_when_schema_already_exists(self, service):
        engine = MagicMock()
        engine.dialect.identifier_preparer.quote_schema.side_effect = (
            lambda s: f'"{s}"'
        )
        inspector = MagicMock()
        inspector.get_schema_names.return_value = ["staging"]
        conn = engine.begin.return_value.__enter__.return_value

        with patch(
            "dpmcore.services.database_update.inspect", return_value=inspector
        ):
            service._create_schema_if_missing(engine, "staging")

        conn.execute.assert_not_called()

    def test_executes_create_schema_when_missing(self, service):
        engine = MagicMock()
        engine.dialect.identifier_preparer.quote_schema.side_effect = (
            lambda s: f'"{s}"'
        )
        inspector = MagicMock()
        inspector.get_schema_names.return_value = []
        conn = engine.begin.return_value.__enter__.return_value

        with patch(
            "dpmcore.services.database_update.inspect", return_value=inspector
        ):
            service._create_schema_if_missing(engine, "staging")

        conn.execute.assert_called_once()
        sql = str(conn.execute.call_args.args[0])
        assert "CREATE SCHEMA" in sql


# ---------------------------------------------------------------------------
# _safe_drop_schema
# ---------------------------------------------------------------------------


class TestSafeDropSchema:
    def test_none_engine_returns_without_error(self, service):
        service._safe_drop_schema(
            None, "postgresql", "staging"
        )  # must not raise

    def test_exception_in_drop_schema_is_swallowed(self, service):
        with patch.object(
            service, "_drop_schema", side_effect=RuntimeError("locked")
        ):
            service._safe_drop_schema(MagicMock(), "postgresql", "staging")


# ---------------------------------------------------------------------------
# _drop_schema
# ---------------------------------------------------------------------------


class TestDropSchema:
    def _inspector_with_schemas(self, schemas):
        inspector = MagicMock()
        inspector.get_schema_names.return_value = list(schemas)
        inspector.get_table_names.return_value = []
        return inspector

    def test_schema_not_found_returns_early(self, service):
        engine = MagicMock()
        inspector = self._inspector_with_schemas([])
        conn = engine.begin.return_value.__enter__.return_value

        with patch(
            "dpmcore.services.database_update.inspect", return_value=inspector
        ):
            service._drop_schema(engine, "postgresql", "missing")

        conn.execute.assert_not_called()

    def test_postgresql_drops_schema_with_cascade(self, service):
        engine = MagicMock()
        engine.dialect.identifier_preparer.quote_schema.side_effect = (
            lambda s: f'"{s}"'
        )
        engine.dialect.identifier_preparer.quote.side_effect = lambda s: (
            f'"{s}"'
        )
        inspector = self._inspector_with_schemas(["staging"])
        conn = engine.begin.return_value.__enter__.return_value

        with patch(
            "dpmcore.services.database_update.inspect", return_value=inspector
        ):
            service._drop_schema(engine, "postgresql", "staging")

        sql = str(conn.execute.call_args.args[0])
        assert "DROP SCHEMA" in sql
        assert "CASCADE" in sql

    def test_sqlserver_drops_fk_constraints_before_tables(self, service):
        engine = MagicMock()
        engine.dialect.identifier_preparer.quote_schema.side_effect = (
            lambda s: f'"{s}"'
        )
        engine.dialect.identifier_preparer.quote.side_effect = lambda s: (
            f'"{s}"'
        )
        inspector = self._inspector_with_schemas(["staging"])
        inspector.get_table_names.return_value = []

        with (
            patch(
                "dpmcore.services.database_update.inspect",
                return_value=inspector,
            ),
            patch.object(
                service, "_drop_sqlserver_foreign_keys_for_schema"
            ) as mock_drop_fk,
        ):
            service._drop_schema(engine, "sqlserver", "staging")

        mock_drop_fk.assert_called_once_with(engine, "staging")

    def test_sqlserver_drops_each_table_then_schema(self, service):
        engine = MagicMock()
        engine.dialect.identifier_preparer.quote_schema.side_effect = (
            lambda s: f'"{s}"'
        )
        engine.dialect.identifier_preparer.quote.side_effect = lambda s: (
            f'"{s}"'
        )
        inspector = self._inspector_with_schemas(["staging"])
        conn = engine.begin.return_value.__enter__.return_value

        with (
            patch(
                "dpmcore.services.database_update.inspect",
                return_value=inspector,
            ),
            patch.object(
                service,
                "_ordered_tables_for_schema",
                return_value=["T1", "T2"],
            ),
            patch.object(service, "_drop_sqlserver_foreign_keys_for_schema"),
        ):
            service._drop_schema(engine, "sqlserver", "staging")

        sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
        drop_table_count = sum(1 for s in sqls if "DROP TABLE" in s)
        drop_schema_count = sum(
            1 for s in sqls if "DROP SCHEMA" in s and "TABLE" not in s
        )
        assert drop_table_count == 2
        assert drop_schema_count == 1


# ---------------------------------------------------------------------------
# Quote helpers
# ---------------------------------------------------------------------------


class TestQualifyHelpers:
    def test_quote_schema_uses_dialect_preparer(self, service):
        engine = MagicMock()
        engine.dialect.identifier_preparer.quote_schema.return_value = (
            '"myschema"'
        )
        assert service._quote_schema(engine, "myschema") == '"myschema"'

    def test_quote_name_uses_dialect_preparer(self, service):
        engine = MagicMock()
        engine.dialect.identifier_preparer.quote.return_value = '"mytable"'
        assert service._quote_name(engine, "mytable") == '"mytable"'

    def test_qualified_table_combines_schema_and_name(self, service):
        engine = MagicMock()
        engine.dialect.identifier_preparer.quote_schema.side_effect = (
            lambda s: f'"{s}"'
        )
        engine.dialect.identifier_preparer.quote.side_effect = lambda s: (
            f'"{s}"'
        )
        result = service._qualified_table(engine, "myschema", "mytable")
        assert result == '"myschema"."mytable"'


# ---------------------------------------------------------------------------
# _validate_schema
# ---------------------------------------------------------------------------


class TestValidateSchema:
    def _mock_engine(self, tables, row_count_return=None):
        engine = MagicMock()
        engine.dialect.identifier_preparer.quote_schema.side_effect = (
            lambda s: f'"{s}"'
        )
        engine.dialect.identifier_preparer.quote.side_effect = lambda s: (
            f'"{s}"'
        )
        inspector = MagicMock()
        inspector.get_table_names.return_value = list(tables)
        conn = engine.connect.return_value.__enter__.return_value
        if row_count_return is not None:
            conn.execute.return_value.scalar_one.return_value = str(
                row_count_return
            )
        return engine, inspector

    def test_missing_tables_raises(self, service):
        engine, inspector = self._mock_engine(["T1"])
        migration_result = MigrationResult(
            tables_migrated=2,
            total_rows=6,
            table_details={"T1": 3, "T2": 3},
            warnings=[],
            backend_used="csv",
        )

        with (
            pytest.raises(DatabaseUpdateError, match="Missing tables"),
            patch(
                "dpmcore.services.database_update.inspect",
                return_value=inspector,
            ),
        ):
            service._validate_schema(
                engine=engine,
                schema="s",
                migration_result=migration_result,
                ecb_validations_file=None,
            )

    def test_passes_when_all_tables_exist_and_counts_sufficient(self, service):
        engine, inspector = self._mock_engine(["T1"], row_count_return=4)
        migration_result = MigrationResult(
            tables_migrated=1,
            total_rows=4,
            table_details={"T1": 4},
            warnings=[],
            backend_used="csv",
        )

        with (
            patch(
                "dpmcore.services.database_update.inspect",
                return_value=inspector,
            ),
            patch.object(service, "_validate_required_content"),
        ):
            service._validate_schema(
                engine=engine,
                schema="s",
                migration_result=migration_result,
                ecb_validations_file=None,
            )


# ---------------------------------------------------------------------------
# _validate_schema_counts
# ---------------------------------------------------------------------------


class TestValidateSchemaCounts:
    def _setup(self, actual_row_count):
        engine = MagicMock()
        engine.dialect.identifier_preparer.quote_schema.side_effect = (
            lambda s: f'"{s}"'
        )
        engine.dialect.identifier_preparer.quote.side_effect = lambda s: (
            f'"{s}"'
        )
        conn = MagicMock()
        conn.execute.return_value.scalar_one.return_value = str(
            actual_row_count
        )
        return engine, conn

    def test_raises_when_actual_below_expected(self, service):
        engine, conn = self._setup(2)
        migration_result = MigrationResult(
            tables_migrated=1,
            total_rows=5,
            table_details={"T1": 5},
            warnings=[],
            backend_used="csv",
        )
        with pytest.raises(DatabaseUpdateError, match="Expected at least 5"):
            service._validate_schema_counts(
                conn=conn,
                engine=engine,
                schema="s",
                migration_result=migration_result,
            )

    def test_passes_when_actual_equals_expected(self, service):
        engine, conn = self._setup(5)
        migration_result = MigrationResult(
            tables_migrated=1,
            total_rows=5,
            table_details={"T1": 5},
            warnings=[],
            backend_used="csv",
        )
        service._validate_schema_counts(
            conn=conn,
            engine=engine,
            schema="s",
            migration_result=migration_result,
        )

    def test_passes_when_actual_exceeds_expected(self, service):
        engine, conn = self._setup(10)
        migration_result = MigrationResult(
            tables_migrated=1,
            total_rows=5,
            table_details={"T1": 5},
            warnings=[],
            backend_used="csv",
        )
        service._validate_schema_counts(
            conn=conn,
            engine=engine,
            schema="s",
            migration_result=migration_result,
        )


# ---------------------------------------------------------------------------
# _check_swap_locks
# ---------------------------------------------------------------------------


class TestCheckSwapLocks:
    def _setup_engine(self, existing_tables):
        engine = MagicMock()
        engine.dialect.identifier_preparer.quote_schema.side_effect = (
            lambda s: f'"{s}"'
        )
        engine.dialect.identifier_preparer.quote.side_effect = lambda s: (
            f'"{s}"'
        )
        inspector = MagicMock()
        inspector.get_table_names.return_value = list(existing_tables)
        return engine, inspector

    def test_unsupported_target_type_raises_immediately(self, service):
        engine = MagicMock()
        inspector = MagicMock()
        inspector.get_table_names.return_value = []

        with (
            pytest.raises(
                DatabaseUpdateError, match="Unsupported staged target"
            ),
            patch(
                "dpmcore.services.database_update.inspect",
                return_value=inspector,
            ),
        ):
            service._check_swap_locks(
                engine=engine,
                target_type="oracle",
                active_schema="public",
                table_names=[],
            )

    def test_table_not_in_existing_is_skipped(self, service):
        engine, inspector = self._setup_engine([])
        conn = engine.connect.return_value.__enter__.return_value
        transaction = conn.begin.return_value

        with patch(
            "dpmcore.services.database_update.inspect", return_value=inspector
        ):
            service._check_swap_locks(
                engine=engine,
                target_type="postgresql",
                active_schema="public",
                table_names=["NoSuchTable"],
            )

        sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
        assert not any("LOCK TABLE" in s for s in sqls)
        transaction.rollback.assert_called()

    def test_lock_failure_raises_database_update_error_postgresql(
        self, service
    ):
        engine, inspector = self._setup_engine(["T1"])
        conn = engine.connect.return_value.__enter__.return_value
        transaction = conn.begin.return_value
        conn.execute.side_effect = [None, Exception("deadlock")]

        with (
            pytest.raises(DatabaseUpdateError, match="PostgreSQL locks"),
            patch(
                "dpmcore.services.database_update.inspect",
                return_value=inspector,
            ),
        ):
            service._check_swap_locks(
                engine=engine,
                target_type="postgresql",
                active_schema="public",
                table_names=["T1"],
            )

        transaction.rollback.assert_called()

    def test_lock_failure_raises_database_update_error_sqlserver(
        self, service
    ):
        engine, inspector = self._setup_engine(["T1"])
        conn = engine.connect.return_value.__enter__.return_value
        transaction = conn.begin.return_value
        conn.execute.side_effect = [None, Exception("timeout")]

        with (
            pytest.raises(DatabaseUpdateError, match="SQL Server locks"),
            patch(
                "dpmcore.services.database_update.inspect",
                return_value=inspector,
            ),
        ):
            service._check_swap_locks(
                engine=engine,
                target_type="sqlserver",
                active_schema="dbo",
                table_names=["T1"],
            )

        transaction.rollback.assert_called()

    def test_successful_lock_check_rolls_back(self, service):
        engine, inspector = self._setup_engine(["T1"])
        conn = engine.connect.return_value.__enter__.return_value
        transaction = conn.begin.return_value

        with patch(
            "dpmcore.services.database_update.inspect", return_value=inspector
        ):
            service._check_swap_locks(
                engine=engine,
                target_type="postgresql",
                active_schema="public",
                table_names=["T1"],
            )

        transaction.rollback.assert_called()


# ---------------------------------------------------------------------------
# _set_swap_timeout
# ---------------------------------------------------------------------------


class TestSetSwapTimeout:
    def test_postgresql_sets_lock_timeout(self, service):
        conn = MagicMock()
        service._set_swap_timeout(conn, "postgresql")
        sql = str(conn.execute.call_args.args[0])
        assert "lock_timeout" in sql

    def test_sqlserver_sets_lock_timeout(self, service):
        conn = MagicMock()
        service._set_swap_timeout(conn, "sqlserver")
        sql = str(conn.execute.call_args.args[0])
        assert "LOCK_TIMEOUT" in sql

    def test_unknown_type_does_not_execute(self, service):
        conn = MagicMock()
        service._set_swap_timeout(conn, "oracle")
        conn.execute.assert_not_called()


# ---------------------------------------------------------------------------
# _move_table
# ---------------------------------------------------------------------------


class TestMoveTable:
    def _make_engine(self):
        engine = MagicMock()
        engine.dialect.identifier_preparer.quote_schema.side_effect = (
            lambda s: f'"{s}"'
        )
        engine.dialect.identifier_preparer.quote.side_effect = lambda s: (
            f'"{s}"'
        )
        return engine

    def test_postgresql_uses_alter_table_set_schema(self, service):
        engine = self._make_engine()
        conn = MagicMock()

        service._move_table(
            conn=conn,
            engine=engine,
            target_type="postgresql",
            source_schema="staging",
            destination_schema="public",
            table_name="T1",
        )

        sql = str(conn.execute.call_args.args[0])
        assert "SET SCHEMA" in sql

    def test_sqlserver_uses_alter_schema_transfer(self, service):
        engine = self._make_engine()
        conn = MagicMock()

        service._move_table(
            conn=conn,
            engine=engine,
            target_type="sqlserver",
            source_schema="staging",
            destination_schema="dbo",
            table_name="T1",
        )

        sql = str(conn.execute.call_args.args[0])
        assert "TRANSFER" in sql

    def test_unknown_type_raises(self, service):
        engine = self._make_engine()
        conn = MagicMock()

        with pytest.raises(
            DatabaseUpdateError, match="Unsupported target type"
        ):
            service._move_table(
                conn=conn,
                engine=engine,
                target_type="oracle",
                source_schema="s",
                destination_schema="d",
                table_name="T",
            )


# ---------------------------------------------------------------------------
# _swap_staging_to_active
# ---------------------------------------------------------------------------


class TestSwapStagingToActive:
    def test_calls_move_table_for_each_active_and_staging_table(self, service):
        engine = MagicMock()
        migration_result = MigrationResult(
            tables_migrated=2,
            total_rows=6,
            table_details={"T1": 3, "T2": 3},
            warnings=[],
            backend_used="csv",
        )

        with (
            patch.object(
                service, "_ordered_tables_for_schema"
            ) as mock_ordered,
            patch.object(service, "_set_swap_timeout"),
            patch.object(service, "_move_table") as mock_move,
            patch.object(service, "_validate_schema_counts"),
            patch.object(service, "_validate_required_content"),
        ):
            mock_ordered.side_effect = [["T2", "T1"], ["T1", "T2"]]

            service._swap_staging_to_active(
                engine=engine,
                target_type="postgresql",
                staging_schema="staging",
                active_schema="public",
                backup_schema="backup",
                migration_result=migration_result,
                ecb_validations_file=None,
            )

        assert mock_move.call_count == 4

    def test_validates_counts_after_swap(self, service):
        engine = MagicMock()
        migration_result = MigrationResult(
            tables_migrated=0,
            total_rows=0,
            table_details={},
            warnings=[],
            backend_used="csv",
        )

        with (
            patch.object(
                service, "_ordered_tables_for_schema", return_value=[]
            ),
            patch.object(service, "_set_swap_timeout"),
            patch.object(service, "_move_table"),
            patch.object(service, "_validate_schema_counts") as mock_validate,
            patch.object(service, "_validate_required_content"),
        ):
            service._swap_staging_to_active(
                engine=engine,
                target_type="postgresql",
                staging_schema="staging",
                active_schema="public",
                backup_schema="backup",
                migration_result=migration_result,
                ecb_validations_file=None,
            )

        mock_validate.assert_called_once()


# ---------------------------------------------------------------------------
# _update_staged_database
# ---------------------------------------------------------------------------


class TestUpdateStagedDatabase:
    def test_returns_correct_result(self, service, tmp_path):
        fake_result = MigrationResult(
            tables_migrated=1,
            total_rows=5,
            table_details={"T1": 5},
            warnings=[],
            backend_used="csv",
        )

        with (
            patch.object(service, "_create_target_engine"),
            patch.object(service, "_create_schema_if_missing"),
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch.object(service, "_validate_csv_count"),
            patch.object(service, "_validate_schema"),
            patch.object(service, "_check_swap_locks"),
            patch.object(service, "_swap_staging_to_active"),
            patch.object(service, "_safe_drop_schema"),
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = (
                fake_result
            )

            result = service._update_staged_database(
                target="postgresql://host/db",
                target_type="postgresql",
                active_schema="public",
                csv_dir=tmp_path,
                source="postgresql://host/db",
                used_access_file=False,
                ecb_validations_file=None,
            )

        assert result.target_type == "postgresql"
        assert result.target == "postgresql://host/db"
        assert result.migration_result is fake_result
        assert result.ecb_validations_imported is False

    def test_ecb_validations_imported_flag(self, service, tmp_path):
        fake_result = MigrationResult(
            tables_migrated=0,
            total_rows=0,
            table_details={},
            warnings=[],
            backend_used="csv",
        )
        ecb_file = tmp_path / "ecb.csv"
        ecb_file.touch()

        with (
            patch.object(service, "_create_target_engine"),
            patch.object(service, "_create_schema_if_missing"),
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch(
                "dpmcore.services.database_update.EcbValidationsImportService"
            ),
            patch.object(service, "_engine_for_schema"),
            patch.object(service, "_validate_csv_count"),
            patch.object(service, "_validate_schema"),
            patch.object(service, "_check_swap_locks"),
            patch.object(service, "_swap_staging_to_active"),
            patch.object(service, "_safe_drop_schema"),
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = (
                fake_result
            )

            result = service._update_staged_database(
                target="postgresql://host/db",
                target_type="postgresql",
                active_schema="public",
                csv_dir=tmp_path,
                source="postgresql://host/db",
                used_access_file=False,
                ecb_validations_file=str(ecb_file),
            )

        assert result.ecb_validations_imported is True

    def test_migration_error_raised_as_database_update_error(
        self, service, tmp_path
    ):
        with (
            patch.object(service, "_create_target_engine"),
            patch.object(service, "_create_schema_if_missing"),
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch.object(service, "_safe_drop_schema"),
        ):
            MockMigration.return_value.migrate_from_csv_dir.side_effect = (
                MigrationError("csv fail")
            )

            with pytest.raises(DatabaseUpdateError, match="csv fail"):
                service._update_staged_database(
                    target="postgresql://host/db",
                    target_type="postgresql",
                    active_schema="public",
                    csv_dir=tmp_path,
                    source="postgresql://host/db",
                    used_access_file=False,
                    ecb_validations_file=None,
                )

    def test_staging_schema_dropped_on_error(self, service, tmp_path):
        with (
            patch.object(service, "_create_target_engine"),
            patch.object(service, "_create_schema_if_missing"),
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch.object(service, "_safe_drop_schema") as mock_drop,
        ):
            MockMigration.return_value.migrate_from_csv_dir.side_effect = (
                MigrationError("fail")
            )

            with pytest.raises(DatabaseUpdateError):
                service._update_staged_database(
                    target="postgresql://host/db",
                    target_type="postgresql",
                    active_schema="public",
                    csv_dir=tmp_path,
                    source="postgresql://host/db",
                    used_access_file=False,
                    ecb_validations_file=None,
                )

        assert mock_drop.call_count >= 1

    def test_generic_exception_wrapped_as_database_update_error(
        self, service, tmp_path
    ):
        with (
            patch.object(service, "_create_target_engine"),
            patch.object(service, "_create_schema_if_missing"),
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch.object(service, "_safe_drop_schema"),
        ):
            MockMigration.return_value.migrate_from_csv_dir.side_effect = (
                RuntimeError("oom")
            )

            with pytest.raises(DatabaseUpdateError, match="oom"):
                service._update_staged_database(
                    target="postgresql://host/db",
                    target_type="postgresql",
                    active_schema="public",
                    csv_dir=tmp_path,
                    source="postgresql://host/db",
                    used_access_file=False,
                    ecb_validations_file=None,
                )


# ---------------------------------------------------------------------------
# _validate_csv_count
# ---------------------------------------------------------------------------


class TestValidateCsvCount:
    def test_no_csv_files_raises(self, service, tmp_path):
        migration_result = MigrationResult(
            tables_migrated=0,
            total_rows=0,
            table_details={},
            warnings=[],
            backend_used="csv",
        )
        with pytest.raises(DatabaseUpdateError, match="No CSV files found"):
            service._validate_csv_count(
                csv_dir=tmp_path, migration_result=migration_result
            )

    def test_count_mismatch_raises(self, service, tmp_path):
        (tmp_path / "T1.csv").touch()
        (tmp_path / "T2.csv").touch()
        migration_result = MigrationResult(
            tables_migrated=1,
            total_rows=5,
            table_details={"T1": 5},
            warnings=[],
            backend_used="csv",
        )
        with pytest.raises(DatabaseUpdateError, match="2 CSV files"):
            service._validate_csv_count(
                csv_dir=tmp_path, migration_result=migration_result
            )

    def test_matching_count_passes(self, service, tmp_path):
        (tmp_path / "T1.csv").touch()
        migration_result = MigrationResult(
            tables_migrated=1,
            total_rows=5,
            table_details={"T1": 5},
            warnings=[],
            backend_used="csv",
        )
        service._validate_csv_count(
            csv_dir=tmp_path, migration_result=migration_result
        )


# ---------------------------------------------------------------------------
# _update_sqlite – dry_run / keep_staging
# ---------------------------------------------------------------------------


class TestUpdateSqliteDryRun:
    def _patched_sqlite(self, service, tmp_path, **kwargs):
        with (
            patch(
                "dpmcore.services.database_update.MigrationService"
            ) as MockMigration,
            patch.object(DatabaseUpdateService, "_validate_sqlite"),
            patch.object(DatabaseUpdateService, "_validate_csv_count"),
        ):
            MockMigration.return_value.migrate_from_csv_dir.return_value = (
                _empty_migration_result()
            )
            return service._update_sqlite(
                target_path=tmp_path / "dpm.sqlite",
                csv_dir=tmp_path,
                source=str(tmp_path),
                used_access_file=False,
                ecb_validations_file=None,
                **kwargs,
            )

    def test_dry_run_result_has_dry_run_true(self, service, tmp_path):
        result = self._patched_sqlite(service, tmp_path, dry_run=True)
        assert result.dry_run is True

    def test_dry_run_does_not_replace_target_file(self, service, tmp_path):
        target = tmp_path / "dpm.sqlite"
        target.write_bytes(b"original")
        self._patched_sqlite(service, tmp_path, dry_run=True)
        assert target.read_bytes() == b"original"

    def test_dry_run_keep_staging_sets_staging_location(
        self, service, tmp_path
    ):
        result = self._patched_sqlite(
            service, tmp_path, dry_run=True, keep_staging=True
        )
        assert result.staging_location is not None

    def test_dry_run_no_keep_staging_staging_location_is_none(
        self, service, tmp_path
    ):
        result = self._patched_sqlite(
            service, tmp_path, dry_run=True, keep_staging=False
        )
        assert result.staging_location is None
