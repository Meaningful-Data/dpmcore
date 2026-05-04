"""Safe database update service."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select, text

from dpmcore.services.ecb_validations_import import EcbValidationsImportService
from dpmcore.services.export_csv import ExportCsvService
from dpmcore.loaders.migration import (
    MigrationError,
    MigrationResult,
    MigrationService,
)


class DatabaseUpdateError(Exception):
    """Raised when a safe database update cannot be completed."""


@dataclass(frozen=True)
class DatabaseUpdateResult:
    """Result of a safe database update."""

    target_type: str
    target: Path
    source: str
    used_access_file: bool
    migration_result: MigrationResult
    ecb_validations_imported: bool


class DatabaseUpdateService:
    """Safely update DPM databases."""

    def update(
        self,
        *,
        target: str,
        access_file: str | None = None,
        ecb_validations_file: str | None = None,
        source_dir: str = "data/DPM",
    ) -> DatabaseUpdateResult:
        """Update a target database from CSVs or an Access file."""
        target_type = self.detect_target_type(target)

        if target_type != "sqlite":
            raise DatabaseUpdateError(
                f"Target type '{target_type}' is not implemented yet."
            )

        with tempfile.TemporaryDirectory(prefix="dpmcore-update-") as tmp:
            csv_dir = Path(source_dir)
            source = str(csv_dir)
            used_access_file = access_file is not None

            if access_file is not None:
                csv_dir = Path(tmp) / "csv"
                ExportCsvService().export_safely(access_file, csv_dir)
                source = access_file

            return self._update_sqlite(
                target_path=self._sqlite_path_from_target(target),
                csv_dir=csv_dir,
                source=source,
                used_access_file=used_access_file,
                ecb_validations_file=ecb_validations_file,
            )

    @staticmethod
    def detect_target_type(target: str) -> str:
        """Detect target type from URL or file path."""
        lowered = target.lower()

        if (
            lowered.startswith("sqlite:///")
            or lowered.endswith(".sqlite")
            or lowered.endswith(".sqlite3")
            or lowered.endswith(".db")
        ):
            return "sqlite"

        if lowered.startswith(("postgresql://", "postgres://")):
            return "postgresql"

        if lowered.startswith(("mssql+pyodbc://", "sqlserver://")):
            return "sqlserver"

        raise DatabaseUpdateError(
            "Could not detect target type. Use a SQLite path/URL, "
            "PostgreSQL URL, or SQL Server URL."
        )

    def _update_sqlite(
        self,
        *,
        target_path: Path,
        csv_dir: Path,
        source: str,
        used_access_file: bool,
        ecb_validations_file: str | None,
    ) -> DatabaseUpdateResult:
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if target_path.exists() and not target_path.is_file():
            raise DatabaseUpdateError(
                f"SQLite target '{target_path}' is not a file."
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        temp_path = target_path.with_name(f".{target_path.name}.tmp-{timestamp}")
        backup_path = target_path.with_name(f"{target_path.name}.backup-{timestamp}")

        try:
            engine = create_engine(f"sqlite:///{temp_path.as_posix()}")

            try:
                migration_result = MigrationService(
                    engine
                ).migrate_from_csv_dir(str(csv_dir))

                if ecb_validations_file is not None:
                    EcbValidationsImportService(engine).import_csv(
                        ecb_validations_file
                    )

                self._validate_sqlite(engine, migration_result)
            finally:
                engine.dispose()

            self._replace_sqlite_file(
                target_path=target_path,
                temp_path=temp_path,
                backup_path=backup_path,
            )

            final_engine = create_engine(f"sqlite:///{target_path.as_posix()}")
            try:
                self._validate_sqlite(final_engine, migration_result)
            finally:
                final_engine.dispose()

            if backup_path.exists():
                backup_path.unlink()

            return DatabaseUpdateResult(
                target_type="sqlite",
                target=target_path,
                source=source,
                used_access_file=used_access_file,
                migration_result=migration_result,
                ecb_validations_imported=ecb_validations_file is not None,
            )

        except MigrationError as exc:
            raise DatabaseUpdateError(str(exc)) from exc
        except DatabaseUpdateError:
            self._restore_sqlite_backup(target_path, backup_path)
            raise
        except Exception as exc:
            self._restore_sqlite_backup(target_path, backup_path)
            raise DatabaseUpdateError(
                f"SQLite update failed for '{target_path}': {exc}"
            ) from exc
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def _sqlite_path_from_target(target: str) -> Path:
        if target.lower().startswith("sqlite:///"):
            return Path(unquote(target[len("sqlite:///") :]))

        if target.lower().startswith("sqlite://"):
            raise DatabaseUpdateError(
                "SQLite URL must use sqlite:///path/to/file.db"
            )

        return Path(target)

    def _replace_sqlite_file(
        self,
        *,
        target_path: Path,
        temp_path: Path,
        backup_path: Path,
    ) -> None:
        if target_path.exists():
            target_path.replace(backup_path)

        try:
            temp_path.replace(target_path)
        except Exception:
            self._restore_sqlite_backup(target_path, backup_path)
            raise

    @staticmethod
    def _restore_sqlite_backup(
        target_path: Path,
        backup_path: Path,
    ) -> None:
        if not backup_path.exists():
            return

        if target_path.exists():
            target_path.unlink()

        backup_path.replace(target_path)

    @staticmethod
    def _validate_sqlite(
        engine,
        migration_result: MigrationResult,
    ) -> None:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        expected_tables = set(migration_result.table_details)

        missing_tables = sorted(expected_tables - existing_tables)
        if missing_tables:
            raise DatabaseUpdateError(
                f"SQLite validation failed. Missing tables: {missing_tables}"
            )

        metadata = MetaData()

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

            for table_name, expected_rows in (
                migration_result.table_details.items()
            ):
                table = Table(table_name, metadata, autoload_with=engine)
                actual_rows = conn.execute(
                    select(func.count()).select_from(table)
                ).scalar_one()

                if actual_rows != expected_rows:
                    raise DatabaseUpdateError(
                        f"SQLite validation failed for table '{table_name}'. "
                        f"Expected {expected_rows} rows, got {actual_rows}."
                    )