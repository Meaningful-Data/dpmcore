"""Safe database update service."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from sqlalchemy import Connection, Engine, create_engine, inspect, text

from dpmcore.loaders.migration import (
    MigrationError,
    MigrationResult,
    MigrationService,
)
from dpmcore.orm.base import Base
from dpmcore.services.ecb_validations_import import EcbValidationsImportService
from dpmcore.services.export_csv import ExportCsvService


class DatabaseUpdateError(Exception):
    """Raised when a safe database update cannot be completed."""


@dataclass(frozen=True)
class DatabaseUpdateResult:
    """Result of a safe database update."""

    target_type: str
    target: str
    source: str
    used_access_file: bool
    migration_result: MigrationResult
    ecb_validations_imported: bool
    dry_run: bool = False
    staging_location: str | None = None


class DatabaseUpdateService:
    """Safely update DPM databases."""

    def update(
        self,
        *,
        target: str,
        access_file: str | None = None,
        ecb_validations_file: str | None = None,
        source_dir: str = "data/DPM",
        dry_run: bool = False,
        keep_staging: bool = False,
    ) -> DatabaseUpdateResult:
        """Update a target database from CSVs or an Access file."""
        target_type = self.detect_target_type(target)

        if target_type not in {"sqlite", "postgresql", "sqlserver"}:
            raise DatabaseUpdateError(
                f"Target type '{target_type}' is not supported."
            )

        with tempfile.TemporaryDirectory(prefix="dpmcore-update-") as tmp:
            csv_dir = Path(source_dir)
            source = str(csv_dir)
            used_access_file = access_file is not None

            if access_file is not None:
                csv_dir = Path(tmp) / "csv"
                ExportCsvService().export_safely(access_file, csv_dir)
                source = access_file

            if target_type == "sqlite":
                return self._update_sqlite(
                    target_path=self._sqlite_path_from_target(target),
                    csv_dir=csv_dir,
                    source=source,
                    used_access_file=used_access_file,
                    ecb_validations_file=ecb_validations_file,
                    dry_run=dry_run,
                    keep_staging=keep_staging,
                )

            else:
                active_schema = (
                    "dbo" if target_type == "sqlserver" else "public"
                )

                return self._update_staged_database(
                    target=target,
                    target_type=target_type,
                    active_schema=active_schema,
                    csv_dir=csv_dir,
                    source=source,
                    used_access_file=used_access_file,
                    ecb_validations_file=ecb_validations_file,
                    dry_run=dry_run,
                    keep_staging=keep_staging,
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

    @staticmethod
    def _sqlite_path_from_target(target: str) -> Path:
        if target.lower().startswith("sqlite:///"):
            return Path(unquote(target[len("sqlite:///") :]))

        if target.lower().startswith("sqlite://"):
            raise DatabaseUpdateError(
                "SQLite URL must use sqlite:///path/to/file.db"
            )

        return Path(target)

    def _update_staged_database(
        self,
        *,
        target: str,
        target_type: str,
        active_schema: str,
        csv_dir: Path,
        source: str,
        used_access_file: bool,
        ecb_validations_file: str | None,
        dry_run: bool = False,
        keep_staging: bool = False,
    ) -> DatabaseUpdateResult:
        """Run a staged update for PostgreSQL or SQL Server targets.

        Loads CSV data into a temporary staging schema, validates it, then
        atomically swaps the staging schema into the active position.  On
        failure, staging and backup schemas are dropped silently unless
        ``keep_staging`` is set.

        Args:
            target: Database connection URL.
            target_type: Either ``'postgresql'`` or ``'sqlserver'``.
            active_schema: Schema name to replace (usually ``'public'``).
            csv_dir: Directory containing source CSV files.
            source: Human-readable source path included in the result.
            used_access_file: Whether the CSVs came from an Access file.
            ecb_validations_file: Optional path to an ECB validations CSV.
            dry_run: Validate but do not swap the staging schema into active.
            keep_staging: Keep staging/backup schemas on success or failure.

        Returns:
            A `DatabaseUpdateResult` describing the completed update.

        Raises:
            DatabaseUpdateError: If migration, validation, or the schema swap
                fails.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        staging_schema = f"dpmcore_staging_{timestamp}"
        backup_schema = f"dpmcore_backup_{timestamp}"

        engine: Engine | None = None

        try:
            engine = self._create_target_engine(target, target_type)
            self._create_schema_if_missing(engine, staging_schema)

            migration_result = MigrationService(
                engine, schema=staging_schema
            ).migrate_from_csv_dir(str(csv_dir))

            self._validate_csv_count(
                csv_dir=csv_dir, migration_result=migration_result
            )

            if ecb_validations_file is not None:
                staging_engine = self._engine_for_schema(
                    engine, staging_schema
                )
                EcbValidationsImportService(staging_engine).import_csv(
                    ecb_validations_file
                )

            self._validate_schema(
                engine=engine,
                schema=staging_schema,
                migration_result=migration_result,
                ecb_validations_file=ecb_validations_file,
            )
            self._check_swap_locks(
                engine=engine,
                target_type=target_type,
                active_schema=active_schema,
                table_names=list(migration_result.table_details),
            )

            if dry_run:
                return DatabaseUpdateResult(
                    target_type=target_type,
                    target=target,
                    source=source,
                    used_access_file=used_access_file,
                    migration_result=migration_result,
                    ecb_validations_imported=ecb_validations_file is not None,
                    dry_run=True,
                    staging_location=staging_schema if keep_staging else None,
                )

            self._create_schema_if_missing(engine, backup_schema)

            self._swap_staging_to_active(
                engine=engine,
                target_type=target_type,
                staging_schema=staging_schema,
                active_schema=active_schema,
                backup_schema=backup_schema,
                migration_result=migration_result,
                ecb_validations_file=ecb_validations_file,
            )

            return DatabaseUpdateResult(
                target_type=target_type,
                target=target,
                source=source,
                used_access_file=used_access_file,
                migration_result=migration_result,
                ecb_validations_imported=ecb_validations_file is not None,
            )

        except MigrationError as exc:
            raise DatabaseUpdateError(str(exc)) from exc

        except Exception as exc:
            if isinstance(exc, DatabaseUpdateError):
                raise
            raise DatabaseUpdateError(
                f"{target_type} update failed for '{target}': {exc}"
            ) from exc

        finally:
            if not keep_staging:
                self._safe_drop_schema(engine, target_type, staging_schema)
                self._safe_drop_schema(engine, target_type, backup_schema)
            if engine is not None:
                engine.dispose()

    @staticmethod
    def _create_target_engine(target: str, target_type: str) -> Engine:
        """Create a SQLAlchemy engine for the given database URL.

        Enables ``fast_executemany`` for SQL Server targets to improve
        bulk-insert throughput.

        Args:
            target: Database connection URL.
            target_type: Either ``'postgresql'`` or ``'sqlserver'``.

        Returns:
            A connected `Engine` instance.
        """
        if target_type == "sqlserver":
            return create_engine(
                target, fast_executemany=True, pool_pre_ping=True
            )

        return create_engine(target, pool_pre_ping=True)

    def _create_schema_if_missing(self, engine: Engine, schema: str) -> None:
        """Create ``schema`` in the database if it does not already exist.

        Args:
            engine: Connected engine.
            schema: Schema name to create.
        """
        inspector = inspect(engine)
        if schema in inspector.get_schema_names():
            return

        with engine.begin() as conn:
            conn.execute(
                text(f"CREATE SCHEMA {self._quote_schema(engine, schema)}")
            )

    @staticmethod
    def _validate_csv_count(
        *, csv_dir: Path, migration_result: MigrationResult
    ) -> None:
        """Raise if the CSV file count does not match the tables migrated.

        Args:
            csv_dir: Directory that was scanned for ``.csv`` files.
            migration_result: Result of the preceding migration step.

        Raises:
            DatabaseUpdateError: If no CSVs are found or the count mismatches.
        """
        csv_count = len(list(csv_dir.glob("*.csv")))

        if csv_count == 0:
            raise DatabaseUpdateError(f"No CSV files found in '{csv_dir}'.")

        if migration_result.tables_migrated != csv_count:
            raise DatabaseUpdateError(
                f"Validation failed. Found {csv_count} CSV files in "
                f"'{csv_dir}', but migrated "
                f"{migration_result.tables_migrated} "
                "tables."
            )

    @staticmethod
    def _engine_for_schema(engine: Engine, schema: str) -> Engine:
        """Return an engine variant that redirects the default schema.

        Uses ``execution_options(schema_translate_map={None: schema})`` so
        ORM queries targeting the default schema are redirected transparently.

        Args:
            engine: Base engine to wrap.
            schema: Target schema name.

        Returns:
            An engine with the schema translation applied.
        """
        return engine.execution_options(schema_translate_map={None: schema})

    def _validate_schema(
        self,
        *,
        engine: Engine,
        schema: str,
        migration_result: MigrationResult,
        ecb_validations_file: str | None,
    ) -> None:
        """Validate all expected tables exist in ``schema`` with enough rows.

        Args:
            engine: Connected engine.
            schema: Schema to validate.
            migration_result: Expected tables and minimum row counts.
            ecb_validations_file: When set, also requires ``Operation`` and
                ``OperationVersion`` to contain at least one row each.

        Raises:
            DatabaseUpdateError: If tables are missing, row counts are too low,
                or critical content is absent.
        """
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names(schema=schema))
        expected_tables = set(migration_result.table_details)

        missing_tables = sorted(expected_tables - existing_tables)
        if missing_tables:
            raise DatabaseUpdateError(
                f"Validation failed for schema '{schema}'. "
                f"Missing tables: {missing_tables}"
            )

        with engine.connect() as conn:
            self._validate_schema_counts(
                conn=conn,
                engine=engine,
                schema=schema,
                migration_result=migration_result,
            )

            self._validate_required_content(
                conn=conn,
                engine=engine,
                schema=schema,
                ecb_validations_file=ecb_validations_file,
            )

    def _validate_schema_counts(
        self,
        *,
        conn: Connection,
        engine: Engine,
        schema: str,
        migration_result: MigrationResult,
    ) -> None:
        """Raise if a migrated table in ``schema`` has too few rows.

        Args:
            conn: Open database connection (within the caller's transaction).
            engine: Engine whose dialect builds quoted identifiers.
            schema: Schema that holds the tables.
            migration_result: Expected minimum row counts per table.

        Raises:
            DatabaseUpdateError: If any table's actual row count is below the
                expected minimum.
        """
        for (
            table_name,
            expected_rows,
        ) in migration_result.table_details.items():
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM "  # noqa: S608
                    f"{self._qualified_table(engine, schema, table_name)}"
                )
            )
            actual_rows = int(result.scalar_one())

            if actual_rows < expected_rows:
                raise DatabaseUpdateError(
                    f"Validation failed for table '{schema}.{table_name}'. "
                    f"Expected at least {expected_rows} rows, "
                    f"got {actual_rows}."
                )

    def _qualified_table(
        self, engine: Engine, schema: str, table_name: str
    ) -> str:
        """Return a fully-qualified ``"schema"."table"`` SQL identifier."""
        return (
            f"{self._quote_schema(engine, schema)}."
            f"{self._quote_name(engine, table_name)}"
        )

    @staticmethod
    def _quote_schema(engine: Engine, schema: str) -> str:
        """Return ``schema`` quoted for safe use in SQL statements."""
        return engine.dialect.identifier_preparer.quote_schema(schema)

    @staticmethod
    def _quote_name(engine: Engine, name: str) -> str:
        """Return ``name`` quoted for safe use in SQL statements."""
        return engine.dialect.identifier_preparer.quote(name)

    def _validate_required_content(
        self,
        *,
        conn: Connection,
        engine: Engine,
        schema: str | None,
        ecb_validations_file: str | None,
    ) -> None:
        """Raise if critical tables are missing or contain no rows.

        Always checks that ``Release`` and ``Organisation`` each contain at
        least one row.  When ``ecb_validations_file`` is provided, also checks
        ``Operation`` and ``OperationVersion``.

        Args:
            conn: Open database connection (within the caller's transaction).
            engine: Engine whose dialect builds quoted identifiers.
            schema: Schema to check, or ``None`` for the default (SQLite).
            ecb_validations_file: When not ``None``, enables the ECB-specific
                checks.

        Raises:
            DatabaseUpdateError: If any required table is absent or empty.
        """
        required_tables = {"Release": 1, "Organisation": 1}

        if ecb_validations_file is not None:
            required_tables.update({"Operation": 1, "OperationVersion": 1})

        inspector = inspect(conn)
        if schema is None:
            existing_tables = set(inspector.get_table_names())
        else:
            existing_tables = set(inspector.get_table_names(schema=schema))

        missing_tables = sorted(set(required_tables) - existing_tables)
        if missing_tables:
            raise DatabaseUpdateError(
                f"Validation failed. Missing tables: {missing_tables}"
            )

        for table_name, min_rows in required_tables.items():
            if schema is None:
                qualified = self._quote_name(engine, table_name)
            else:
                qualified = self._qualified_table(engine, schema, table_name)

            actual_rows = int(
                conn.execute(
                    text(f"SELECT COUNT(*) FROM {qualified}")  # noqa: S608
                ).scalar_one()
            )

            if actual_rows < min_rows:
                raise DatabaseUpdateError(
                    f"Validation failed. Critical table '{table_name}' "
                    f"must have at least {min_rows} row(s), got {actual_rows}."
                )

    def _check_swap_locks(
        self,
        *,
        engine: Engine,
        target_type: str,
        active_schema: str,
        table_names: list[str],
    ) -> None:
        """Verify that exclusive locks can be acquired on all active tables.

        Starts a transaction, sets a short lock timeout, and attempts to lock
        every table in ``active_schema``.  The transaction is always rolled
        back — this is a preflight check only and never modifies the database.

        This check is *advisory*: locks are released when this method
        returns, so another transaction can re-acquire them before
        :meth:`_swap_staging_to_active` runs. A passing preflight means
        "no contention right now", not "the swap is guaranteed to
        succeed". The real swap still uses its own ``lock_timeout`` and
        will surface the same error if a competing transaction has
        meanwhile taken the locks.

        Args:
            engine: Connected engine.
            target_type: Either ``'postgresql'`` or ``'sqlserver'``.
            active_schema: Schema holding the live tables to lock.
            table_names: Names of the tables to attempt to lock.

        Raises:
            DatabaseUpdateError: If any lock cannot be acquired within the
                timeout.
        """
        if target_type == "postgresql":
            # ``lock_timeout`` gives competing transactions up to 2s to
            # release the lock before failing. ``NOWAIT`` would short-
            # circuit that window and make ``lock_timeout`` dead code.
            timeout_sql = "SET LOCAL lock_timeout = '2s'"
            dialect_label = "PostgreSQL"

            def lock_sql(table: str) -> str:
                return f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE"
        elif target_type == "sqlserver":
            timeout_sql = "SET LOCK_TIMEOUT 2000"
            dialect_label = "SQL Server"

            def lock_sql(table: str) -> str:
                return (
                    f"SELECT TOP (0) * FROM {table}"  # noqa: S608
                    " WITH (TABLOCKX, HOLDLOCK)"
                )
        else:
            raise DatabaseUpdateError(
                f"Unsupported staged target '{target_type}'."
            )

        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names(schema=active_schema))

        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                conn.execute(text(timeout_sql))

                for table_name in table_names:
                    if table_name not in existing_tables:
                        continue

                    qualified = self._qualified_table(
                        engine, active_schema, table_name
                    )
                    conn.execute(text(lock_sql(qualified)))

            except Exception as exc:
                transaction.rollback()
                raise DatabaseUpdateError(
                    f"Final swap was not started because "
                    f"{dialect_label} locks could not be acquired. "
                    "The active database was not modified."
                ) from exc

            transaction.rollback()

    def _swap_staging_to_active(
        self,
        *,
        engine: Engine,
        target_type: str,
        staging_schema: str,
        active_schema: str,
        backup_schema: str,
        migration_result: MigrationResult,
        ecb_validations_file: str | None,
    ) -> None:
        """Atomically replace the active schema with the validated staging one.

        Within a single transaction:

        1. Moves all tables from ``active_schema`` → ``backup_schema``.
        2. Moves all tables from ``staging_schema`` → ``active_schema``.
        3. Validates row counts and required content in the new active one.

        If validation fails the transaction rolls back, leaving the active
        schema untouched.

        Args:
            engine: Connected engine.
            target_type: Either ``'postgresql'`` or ``'sqlserver'``.
            staging_schema: Schema holding the freshly-loaded data.
            active_schema: Schema that will be replaced.
            backup_schema: Schema to receive the old active tables.
            migration_result: Expected minimum row counts per table.
            ecb_validations_file: Optional path used by
                ``_validate_required_content``.

        Raises:
            DatabaseUpdateError: If any table move or post-swap validation
                fails.
        """
        active_tables_to_backup = self._ordered_tables_for_schema(
            engine=engine,
            schema=active_schema,
            reverse_orm_order=True,
        )

        staging_tables_to_activate = self._ordered_tables_for_schema(
            engine=engine,
            schema=staging_schema,
            reverse_orm_order=False,
        )

        with engine.begin() as conn:
            self._set_swap_timeout(conn, target_type)

            for table_name in active_tables_to_backup:
                self._move_table(
                    conn=conn,
                    engine=engine,
                    target_type=target_type,
                    source_schema=active_schema,
                    destination_schema=backup_schema,
                    table_name=table_name,
                )

            for table_name in staging_tables_to_activate:
                self._move_table(
                    conn=conn,
                    engine=engine,
                    target_type=target_type,
                    source_schema=staging_schema,
                    destination_schema=active_schema,
                    table_name=table_name,
                )

            self._validate_schema_counts(
                conn=conn,
                engine=engine,
                schema=active_schema,
                migration_result=migration_result,
            )
            self._validate_required_content(
                conn=conn,
                engine=engine,
                schema=active_schema,
                ecb_validations_file=ecb_validations_file,
            )

    def _ordered_tables_for_schema(
        self,
        *,
        engine: Engine,
        schema: str,
        reverse_orm_order: bool = False,
    ) -> list[str]:
        """Return table names in ``schema`` ordered by ORM dependency order.

        Tables present in the ORM metadata are returned first, sorted by
        ``Base.metadata.sorted_tables`` (reversed when ``reverse_orm_order``
        is set).  Any extra tables not known to the ORM are appended
        alphabetically.

        Args:
            engine: Connected engine.
            schema: Schema to inspect.
            reverse_orm_order: When ``True``, reverse the ORM dependency order
                (useful for safe DROP sequencing).

        Returns:
            A list of table names safe to process in the returned order.
        """
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names(schema=schema))

        orm_tables = [table.name for table in Base.metadata.sorted_tables]
        if reverse_orm_order:
            orm_tables.reverse()

        ordered = [
            table_name
            for table_name in orm_tables
            if table_name in existing_tables
        ]

        remaining = sorted(existing_tables - set(ordered))

        return ordered + remaining

    def _set_swap_timeout(self, conn: Connection, target_type: str) -> None:
        """Set a short lock timeout for the current swap transaction.

        Issues ``SET LOCAL lock_timeout`` for PostgreSQL or
        ``SET LOCK_TIMEOUT`` for SQL Server so that the swap fails fast
        rather than blocking indefinitely on a contested table.

        Args:
            conn: Open connection within the swap transaction.
            target_type: Either ``'postgresql'`` or ``'sqlserver'``.
        """
        if target_type == "postgresql":
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            return

        if target_type == "sqlserver":
            conn.execute(text("SET LOCK_TIMEOUT 5000"))
            return

    def _move_table(
        self,
        *,
        conn: Connection,
        engine: Engine,
        target_type: str,
        source_schema: str,
        destination_schema: str,
        table_name: str,
    ) -> None:
        """Move a table from ``source_schema`` to ``destination_schema``.

        For PostgreSQL, uses ``ALTER TABLE … SET SCHEMA``.  For SQL Server,
        uses ``ALTER SCHEMA … TRANSFER``.

        Args:
            conn: Open connection within the swap transaction.
            engine: Engine whose dialect is used to build quoted identifiers.
            target_type: Either ``'postgresql'`` or ``'sqlserver'``.
            source_schema: Schema that currently holds the table.
            destination_schema: Schema to move the table into.
            table_name: Unquoted table name.

        Raises:
            DatabaseUpdateError: If ``target_type`` is not supported.
        """
        source_table = self._qualified_table(engine, source_schema, table_name)
        destination_schema_quoted = self._quote_schema(
            engine, destination_schema
        )

        if target_type == "postgresql":
            conn.execute(
                text(
                    f"ALTER TABLE {source_table} "
                    f"SET SCHEMA {destination_schema_quoted}"
                )
            )
            return

        if target_type == "sqlserver":
            conn.execute(
                text(
                    f"ALTER SCHEMA {destination_schema_quoted} "
                    f"TRANSFER {source_table}"
                )
            )
            return

        raise DatabaseUpdateError(f"Unsupported target type '{target_type}'.")

    def _safe_drop_schema(
        self,
        engine: Engine | None,
        target_type: str,
        schema: str,
    ) -> None:
        """Drop ``schema`` silently, ignoring any errors.

        Args:
            engine: Connected engine, or ``None`` (no-op).
            target_type: Either ``'postgresql'`` or ``'sqlserver'``.
            schema: Schema to drop.
        """
        if engine is None:
            return

        try:
            self._drop_schema(engine, target_type, schema)
        except Exception:
            return

    def _drop_schema(
        self, engine: Engine, target_type: str, schema: str
    ) -> None:
        """Drop ``schema`` and all its tables.

        For PostgreSQL, issues ``DROP SCHEMA … CASCADE``.  For SQL Server,
        drops all foreign keys touching the schema first, then drops tables in
        reverse-ORM order, and finally drops the schema itself.

        Args:
            engine: Connected engine.
            target_type: Either ``'postgresql'`` or ``'sqlserver'``.
            schema: Schema to drop.
        """
        inspector = inspect(engine)
        if schema not in inspector.get_schema_names():
            return

        if target_type == "postgresql":
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"DROP SCHEMA IF EXISTS "
                        f"{self._quote_schema(engine, schema)} CASCADE"
                    )
                )
            return

        if target_type == "sqlserver":
            self._drop_sqlserver_foreign_keys_for_schema(engine, schema)

        ordered_tables = self._ordered_tables_for_schema(
            engine=engine,
            schema=schema,
            reverse_orm_order=True,
        )

        with engine.begin() as conn:
            for table_name in ordered_tables:
                conn.execute(
                    text(
                        f"DROP TABLE "
                        f"{self._qualified_table(engine, schema, table_name)}"
                    )
                )

            conn.execute(
                text(f"DROP SCHEMA {self._quote_schema(engine, schema)}")
            )

    def _drop_sqlserver_foreign_keys_for_schema(
        self, engine: Engine, schema: str
    ) -> None:
        """Drop all FK constraints that reference or belong to ``schema``.

        Queries ``sys.foreign_keys`` to find every FK where either the parent
        or the referenced table lives in ``schema``, then issues an
        ``ALTER TABLE … DROP CONSTRAINT`` for each one.

        Args:
            engine: Connected engine.
            schema: Schema name whose FK constraints should be removed.
        """
        query = text(
            """
            SELECT ps.name AS parent_schema,
                   pt.name AS parent_table,
                   fk.name AS fk_name
            FROM sys.foreign_keys fk
                     JOIN sys.tables pt ON fk.parent_object_id = pt.object_id
                     JOIN sys.schemas ps ON pt.schema_id = ps.schema_id
                     JOIN sys.tables rt
                       ON fk.referenced_object_id = rt.object_id
                     JOIN sys.schemas rs ON rt.schema_id = rs.schema_id
            WHERE ps.name = :schema
               OR rs.name = :schema
            """
        )

        with engine.begin() as conn:
            rows = conn.execute(query, {"schema": schema}).fetchall()

            for parent_schema, parent_table, fk_name in rows:
                parent_table_q = self._qualified_table(
                    engine, parent_schema, parent_table
                )
                fk_name_q = self._quote_name(engine, fk_name)
                conn.execute(
                    text(
                        f"ALTER TABLE {parent_table_q} "
                        f"DROP CONSTRAINT {fk_name_q}"
                    )
                )

    def _update_sqlite(
        self,
        *,
        target_path: Path,
        csv_dir: Path,
        source: str,
        used_access_file: bool,
        ecb_validations_file: str | None,
        dry_run: bool = False,
        keep_staging: bool = False,
    ) -> DatabaseUpdateResult:
        """Update a SQLite database file from CSV data.

        Builds a staging temp file, runs migration and two-phase validation
        (pre- and post-ECB import), then atomically replaces the target file.
        On failure the original file is restored from a backup.

        Args:
            target_path: Filesystem path to the target ``.db`` file.
            csv_dir: Directory containing source CSV files.
            source: Human-readable source path included in the result.
            used_access_file: Whether the CSVs came from an Access file.
            ecb_validations_file: Optional path to an ECB validations CSV.
            dry_run: Validate but do not replace the active database file.
            keep_staging: Keep the staging temp file when ``dry_run`` is set.

        Returns:
            A `DatabaseUpdateResult` describing the completed update.

        Raises:
            DatabaseUpdateError: If migration, validation, or the file swap
                fails.
        """
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if target_path.exists() and not target_path.is_file():
            raise DatabaseUpdateError(
                f"SQLite target '{target_path}' is not a file."
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        temp_path = target_path.with_name(
            f".{target_path.name}.tmp-{timestamp}"
        )
        backup_path = target_path.with_name(
            f"{target_path.name}.backup-{timestamp}"
        )

        try:
            engine = create_engine(f"sqlite:///{temp_path.as_posix()}")

            try:
                migration_result = MigrationService(
                    engine
                ).migrate_from_csv_dir(str(csv_dir), output_path=temp_path)

                self._validate_csv_count(
                    csv_dir=csv_dir, migration_result=migration_result
                )

                self._validate_sqlite(
                    engine,
                    migration_result,
                    exact_counts=True,
                    ecb_validations_file=None,
                )

                if ecb_validations_file is not None:
                    EcbValidationsImportService(engine).import_csv(
                        ecb_validations_file
                    )

                self._validate_sqlite(
                    engine,
                    migration_result,
                    exact_counts=ecb_validations_file is None,
                    ecb_validations_file=ecb_validations_file,
                )
            finally:
                engine.dispose()

            if dry_run:
                return DatabaseUpdateResult(
                    target_type="sqlite",
                    target=str(target_path),
                    source=source,
                    used_access_file=used_access_file,
                    migration_result=migration_result,
                    ecb_validations_imported=ecb_validations_file is not None,
                    dry_run=True,
                    staging_location=str(temp_path) if keep_staging else None,
                )

            self._replace_sqlite_file(
                target_path=target_path,
                temp_path=temp_path,
                backup_path=backup_path,
            )

            final_engine = create_engine(f"sqlite:///{target_path.as_posix()}")
            try:
                self._validate_sqlite(
                    final_engine,
                    migration_result,
                    exact_counts=ecb_validations_file is None,
                    ecb_validations_file=ecb_validations_file,
                )
            finally:
                final_engine.dispose()

            if backup_path.exists():
                backup_path.unlink()

            return DatabaseUpdateResult(
                target_type="sqlite",
                target=str(target_path),
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
            if temp_path.exists() and not keep_staging:
                temp_path.unlink()

    def _validate_sqlite(
        self,
        engine: Engine,
        migration_result: MigrationResult,
        *,
        exact_counts: bool = True,
        ecb_validations_file: str | None = None,
    ) -> None:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        expected_tables = set(migration_result.table_details)

        missing_tables = sorted(expected_tables - existing_tables)
        if missing_tables:
            raise DatabaseUpdateError(
                f"SQLite validation failed. Missing tables: {missing_tables}"
            )

        with engine.connect() as conn:
            for (
                table_name,
                expected_rows,
            ) in migration_result.table_details.items():
                actual_rows = conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')  # noqa: S608
                ).scalar_one()

                if exact_counts and actual_rows != expected_rows:
                    raise DatabaseUpdateError(
                        f"SQLite validation failed for table '{table_name}'. "
                        f"Expected {expected_rows} rows, got {actual_rows}."
                    )

                if not exact_counts and actual_rows < expected_rows:
                    raise DatabaseUpdateError(
                        f"SQLite validation failed for table '{table_name}'. "
                        f"Expected at least {expected_rows} rows, "
                        f"got {actual_rows}."
                    )

            self._validate_required_content(
                conn=conn,
                engine=engine,
                schema=None,
                ecb_validations_file=ecb_validations_file,
            )

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
