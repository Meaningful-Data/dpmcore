"""Access-to-database migration service.

Extracts tables from a Microsoft Access ``.accdb`` / ``.mdb`` file and
loads them into any SQLAlchemy-supported database, preserving the ORM
schema created by ``Base.metadata.create_all``.

Two extraction backends are tried in order:

1. **mdb-tools** (``mdb-tables`` + ``mdb-export``) — works on Linux
   without ODBC drivers.
2. **pyodbc** — works on Windows / macOS with the Access ODBC driver
   installed.

Both ``pandas`` and ``pyodbc`` are optional dependencies; they are
imported lazily so the rest of dpmcore works without them.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from io import StringIO
from typing import Any, Dict, List

from sqlalchemy import Engine

from dpmcore.orm.base import Base

logger = logging.getLogger(__name__)

# Access system tables that should never be migrated.
_SYSTEM_TABLE_PREFIXES = ("MSys", "~")


class MigrationError(Exception):
    """Raised when migration cannot proceed."""


@dataclass(frozen=True)
class MigrationResult:
    """Outcome of a successful migration run."""

    tables_migrated: int
    total_rows: int
    table_details: Dict[str, int]
    warnings: List[str]
    backend_used: str


class MigrationService:
    """Migrate an Access database into a SQLAlchemy-managed database.

    Unlike other dpmcore services that accept a ``Session``, this
    service requires an ``Engine`` because it needs to run
    ``Base.metadata.create_all`` and ``DataFrame.to_sql``.

    Args:
        engine: A SQLAlchemy :class:`~sqlalchemy.engine.Engine`.
    """

    def __init__(self, engine: Engine) -> None:
        """Initialise with a SQLAlchemy Engine."""
        self._engine = engine

    # -------------------------------------------------------------- #
    # Public API
    # -------------------------------------------------------------- #

    def migrate_from_access(self, access_path: str) -> MigrationResult:
        """Extract tables from *access_path* and load into the database.

        Args:
            access_path: Filesystem path to an ``.accdb`` or ``.mdb``
                file.

        Returns:
            A :class:`MigrationResult` with details of what was loaded.

        Raises:
            MigrationError: If neither mdb-tools nor pyodbc can read
                the file.
        """
        data, backend = self._extract_tables(access_path)
        self._create_schema()
        warnings = self._load_data(data)

        table_details = {
            name: len(df) for name, df in data.items()
        }
        total_rows = sum(table_details.values())

        return MigrationResult(
            tables_migrated=len(table_details),
            total_rows=total_rows,
            table_details=table_details,
            warnings=warnings,
            backend_used=backend,
        )

    # -------------------------------------------------------------- #
    # Extraction
    # -------------------------------------------------------------- #

    def _extract_tables(
        self, access_path: str
    ) -> tuple[Dict[str, Any], str]:
        """Try mdb-tools first, fall back to pyodbc."""
        try:
            data = self._extract_with_mdbtools(access_path)
            return data, "mdbtools"
        except (FileNotFoundError, OSError, subprocess.CalledProcessError):
            logger.debug(
                "mdb-tools not available, falling back to pyodbc"
            )

        try:
            data = self._extract_with_pyodbc(access_path)
            return data, "pyodbc"
        except Exception as exc:
            raise MigrationError(
                "Could not read the Access file. Install mdb-tools "
                "(Linux) or the Microsoft Access ODBC driver "
                "(Windows/macOS), then try again."
            ) from exc

    def _extract_with_mdbtools(
        self, access_path: str
    ) -> Dict[str, Any]:
        """Use ``mdb-tables`` / ``mdb-export`` (subprocess)."""
        import pandas as pd  # lazy

        raw = subprocess.check_output(  # noqa: S603
            ["mdb-tables", "-1", access_path],  # noqa: S607
            text=True,
        )
        table_names = [
            t.strip()
            for t in raw.strip().split("\n")
            if t.strip()
            and not any(
                t.strip().startswith(p) for p in _SYSTEM_TABLE_PREFIXES
            )
        ]

        data: Dict[str, Any] = {}
        for table in table_names:
            csv_text = subprocess.check_output(  # noqa: S603
                ["mdb-export", access_path, table],  # noqa: S607
                text=True,
            )
            df = pd.read_csv(StringIO(csv_text), dtype=str)
            # Attempt numeric conversion where possible.
            data[table] = self._coerce_numeric_columns(df)

        return data

    def _extract_with_pyodbc(
        self, access_path: str
    ) -> Dict[str, Any]:
        """Use pyodbc with the Access ODBC driver."""
        import decimal

        import pandas as pd  # lazy
        import pyodbc  # lazy  # type: ignore[import-untyped]

        conn_str = (
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            f"DBQ={access_path};"
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Discover user tables (skip system tables).
        tables = [
            row.table_name
            for row in cursor.tables(tableType="TABLE")
            if not any(
                row.table_name.startswith(p)
                for p in _SYSTEM_TABLE_PREFIXES
            )
        ]

        numeric_types = (int, float, decimal.Decimal)

        data: Dict[str, Any] = {}
        for table in tables:
            cursor.execute(f"SELECT * FROM [{table}]")  # noqa: S608

            col_meta = cursor.description
            col_names = [col[0] for col in col_meta]
            col_types = [col[1] for col in col_meta]

            rows = cursor.fetchall()

            df = pd.DataFrame.from_records(
                rows, columns=col_names
            )

            # Apply schema-based type enforcement: keep text columns
            # as text even when values look numeric.
            for name, col_type in zip(
                col_names, col_types, strict=True
            ):
                if col_type in numeric_types:
                    df[name] = pd.to_numeric(
                        df[name], errors="coerce"
                    )
                else:
                    df[name] = df[name].astype(object)

            data[table] = df

        conn.close()
        return data

    @staticmethod
    def _coerce_numeric_columns(df: Any) -> Any:
        """Try to convert string columns to numeric where possible."""
        import contextlib

        import pandas as pd  # lazy

        for col in df.columns:
            with contextlib.suppress(ValueError, TypeError):
                df[col] = pd.to_numeric(df[col])
        return df

    # -------------------------------------------------------------- #
    # Schema creation & data loading
    # -------------------------------------------------------------- #

    def _create_schema(self) -> None:
        """Drop and recreate all ORM tables for a clean migration."""
        Base.metadata.drop_all(self._engine)
        Base.metadata.create_all(self._engine)

    def _load_data(self, data: Dict[str, Any]) -> List[str]:
        """Write DataFrames into the database.

        Uses ``if_exists="append"`` so that ORM-created column types
        and constraints are preserved.

        Returns:
            A list of warning messages (e.g. tables that could not be
            loaded).
        """
        warnings: List[str] = []

        for table_name, df in data.items():
            self._load_table(table_name, df, warnings)

        return warnings

    def _load_table(
        self,
        table_name: str,
        df: Any,
        warnings: List[str],
    ) -> None:
        """Load a single DataFrame into the database."""
        # Filter DataFrame columns to only those present in the
        # ORM schema so that unexpected Access columns produce a
        # warning instead of a hard failure.
        orm_table = Base.metadata.tables.get(table_name)
        if orm_table is not None:
            known_cols = {c.name for c in orm_table.columns}
            extra_cols = set(df.columns) - known_cols
            if extra_cols:
                msg = (
                    f"Table '{table_name}': dropping unknown "
                    f"columns {sorted(extra_cols)}"
                )
                logger.info(msg)
                warnings.append(msg)
                df = df[[
                    c for c in df.columns if c in known_cols
                ]]

        try:
            df.to_sql(
                table_name,
                self._engine,
                if_exists="append",
                index=False,
            )
        except Exception as exc:
            msg = f"Failed to load table '{table_name}': {exc}"
            logger.warning(msg)
            warnings.append(msg)
