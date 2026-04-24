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
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

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

        table_details = {name: len(df) for name, df in data.items()}
        total_rows = sum(table_details.values())

        return MigrationResult(
            tables_migrated=len(table_details),
            total_rows=total_rows,
            table_details=table_details,
            warnings=warnings,
            backend_used=backend,
        )

    def migrate_from_csv_dir(self, csv_dir: str) -> MigrationResult:
        """Load every CSV file from *csv_dir* into the target database."""
        path = Path(csv_dir)
        if not path.exists():
            raise MigrationError(f"CSV directory '{csv_dir}' does not exist.")
        if not path.is_dir():
            raise MigrationError(f"CSV path '{csv_dir}' is not a directory.")

        data = self._extract_from_csv_dir(path)
        if not data:
            raise MigrationError(f"No CSV files found in '{csv_dir}'.")

        return self._migrate_data(data, backend="csv")

    # -------------------------------------------------------------- #
    # Extraction
    # -------------------------------------------------------------- #

    def _extract_tables(self, access_path: str) -> tuple[Dict[str, Any], str]:
        """Try mdb-tools first, fall back to pyodbc."""
        try:
            data = self._extract_with_mdbtools(access_path)
            return data, "mdbtools"
        except (FileNotFoundError, OSError, subprocess.CalledProcessError):
            logger.debug("mdb-tools not available, falling back to pyodbc")

        try:
            data = self._extract_with_pyodbc(access_path)
            return data, "pyodbc"
        except Exception as exc:
            raise MigrationError(
                "Could not read the Access file. Install mdb-tools "
                "(Linux) or the Microsoft Access ODBC driver "
                "(Windows/macOS), then try again."
            ) from exc

    def _extract_with_mdbtools(self, access_path: str) -> Dict[str, Any]:
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

    def _extract_with_pyodbc(self, access_path: str) -> Dict[str, Any]:
        """Use pyodbc with the Access ODBC driver."""
        import decimal

        import pandas as pd  # lazy
        import pyodbc  # lazy

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
                row.table_name.startswith(p) for p in _SYSTEM_TABLE_PREFIXES
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

            df = pd.DataFrame.from_records(rows, columns=col_names)

            # Apply schema-based type enforcement: keep text columns
            # as text even when values look numeric.
            for name, col_type in zip(col_names, col_types, strict=True):
                if col_type in numeric_types:
                    df[name] = pd.to_numeric(df[name], errors="coerce")
                else:
                    df[name] = df[name].astype(object)

            data[table] = df

        conn.close()
        return data

    def _extract_from_csv_dir(self, csv_dir: Path) -> Dict[str, Any]:
        """Read all CSV files from *csv_dir* keyed by table name."""
        import pandas as pd  # lazy

        csv_files = sorted(csv_dir.glob("*.csv"))
        data: Dict[str, Any] = {}

        for csv_file in csv_files:
            table_name = csv_file.stem
            df = pd.read_csv(
                csv_file,
                dtype=str,
                keep_default_na=False,
                na_values=[""],
            )
            data[table_name] = self._coerce_numeric_columns_for_csv(df)

        return self._order_data_by_schema(data)

    def _order_data_by_schema(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Return *data* ordered using ORM metadata dependency order."""
        ordered: Dict[str, Any] = {}
        for table in Base.metadata.sorted_tables:
            if table.name in data:
                ordered[table.name] = data[table.name]

        for name, frame in data.items():
            if name not in ordered:
                ordered[name] = frame

        return ordered

    def _migrate_data(
        self,
        data: Dict[str, Any],
        *,
        backend: str,
    ) -> MigrationResult:
        """Create schema, load *data*, and build a standard result."""
        self._create_schema()
        warnings = self._load_data(data)

        table_details = {name: len(df) for name, df in data.items()}
        total_rows = sum(table_details.values())

        return MigrationResult(
            tables_migrated=len(table_details),
            total_rows=total_rows,
            table_details=table_details,
            warnings=warnings,
            backend_used=backend,
        )

    @staticmethod
    def _coerce_numeric_columns(df: Any) -> Any:
        """Try to convert string columns to numeric where possible."""
        import contextlib

        import pandas as pd  # lazy

        for col in df.columns:
            with contextlib.suppress(ValueError, TypeError):
                df[col] = pd.to_numeric(df[col])
        return df

    @staticmethod
    def _coerce_numeric_columns_for_csv(df: Any) -> Any:
        import pandas as pd  # lazy

        string_columns = {"row", "column", "sheet"}

        for column in df.columns:
            if str(column).lower() in string_columns:
                continue

            non_null = df[column].dropna()
            if non_null.empty:
                continue

            if non_null.astype(str).str.match(r"^0\d+").any():
                continue

            coerced = pd.to_numeric(non_null, errors="coerce")
            if not coerced.isna().any():
                df[column] = pd.to_numeric(df[column], errors="coerce")

        return df

    @staticmethod
    def _coerce_temporal_columns_for_schema(df: Any, orm_table: Any) -> Any:  # noqa: C901
        """Convert date/datetime columns to Python objects before loading."""
        import pandas as pd  # lazy
        from sqlalchemy.sql.sqltypes import Date, DateTime

        # fromisoformat() (Python 3.11+) covers all YYYY-MM-DD* variants;
        # these fallbacks handle non-ISO formats from mdb-export and similar.
        _DATE_FMTS = ("%d/%m/%Y", "%m/%d/%Y", "%m/%d/%y")
        _DATETIME_FMTS = (
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%y %H:%M:%S",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%y %H:%M:%S",
        )

        def is_missing(value: Any) -> bool:
            try:
                return (
                    value is None
                    or bool(pd.isna(value))
                    or (isinstance(value, str) and not value.strip())
                )
            except (TypeError, ValueError):
                return False

        def parse_date_value(value: Any) -> Optional[date]:
            if is_missing(value):
                return None
            text = str(value).strip()
            try:
                return datetime.fromisoformat(text).date()
            except ValueError:
                pass
            for fmt in _DATE_FMTS + _DATETIME_FMTS:
                try:
                    return datetime.strptime(text, fmt).date()  # noqa: DTZ007
                except ValueError:  # noqa: PERF203
                    continue
            raise MigrationError(f"Unsupported date value {value!r}")

        def parse_datetime_value(value: Any) -> Optional[datetime]:
            if is_missing(value):
                return None
            text = str(value).strip()
            try:
                return datetime.fromisoformat(text)
            except ValueError:
                pass
            for fmt in _DATETIME_FMTS:
                try:
                    return datetime.strptime(text, fmt)  # noqa: DTZ007
                except ValueError:  # noqa: PERF203
                    continue
            for fmt in _DATE_FMTS:
                try:
                    return datetime.combine(
                        datetime.strptime(text, fmt).date(),  # noqa: DTZ007
                        datetime.min.time(),
                    )
                except ValueError:  # noqa: PERF203
                    continue
            raise MigrationError(f"Unsupported datetime value {value!r}")

        for column in orm_table.columns:
            column_name = column.name
            if column_name not in df.columns:
                continue
            if not isinstance(column.type, (Date, DateTime)):
                continue

            converted_values = []
            bad_values = []
            for raw_value in df[column_name].tolist():
                try:
                    if isinstance(column.type, Date):
                        converted_values.append(parse_date_value(raw_value))
                    else:
                        converted_values.append(
                            parse_datetime_value(raw_value)
                        )
                except MigrationError:  # noqa: PERF203
                    bad_values.append(raw_value)

            if bad_values:
                unique_bad = list(
                    dict.fromkeys(
                        "<missing>" if is_missing(v) else repr(v)
                        for v in bad_values
                    )
                )
                raise MigrationError(
                    f"Table '{orm_table.name}', column '{column_name}' "
                    f"contains unsupported date values: {unique_bad[:5]}"
                )

            df[column_name] = pd.Series(converted_values, index=df.index)

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
                df = df[[c for c in df.columns if c in known_cols]]

            df = self._coerce_temporal_columns_for_schema(df, orm_table)

        try:
            df.to_sql(
                table_name,
                self._engine,
                if_exists="append",
                index=False,
            )
        except Exception as exc:
            raise MigrationError(
                f"Failed to load table '{table_name}': {exc}"
            ) from exc
