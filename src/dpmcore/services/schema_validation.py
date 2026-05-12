"""Schema validation service.

Performs a fast, shallow check that a DPM database has the expected
shape and a small set of canonical seed tables are populated. The
intent is a sanity gate runnable in CI/healthchecks, not a deep
audit — comparisons are case-insensitive and types/constraints are
deliberately not checked.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from sqlalchemy import Engine, inspect, text

from dpmcore.orm.base import Base

REQUIRED_NON_EMPTY_TABLES: Tuple[str, ...] = (
    "Category",
    "Variable",
    "Item",
    "Operator",
    "Table",
    "TableVersion",
)


@dataclass
class SchemaValidationResult:
    """Outcome of a shallow schema-validation pass.

    Attributes:
        is_valid: True when no missing tables/columns and all required
            seed tables are non-empty.
        backend: SQLAlchemy dialect name of the validated engine.
        missing_tables: Expected table names absent from the database.
        missing_columns: Per-table list of expected columns absent.
        empty_required_tables: Required seed tables that exist but
            contain no rows.
        elapsed_ms: Wall-clock time spent validating, in milliseconds.
    """

    is_valid: bool
    backend: str
    missing_tables: List[str] = field(default_factory=list)
    missing_columns: Dict[str, List[str]] = field(default_factory=dict)
    empty_required_tables: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


class SchemaValidationService:
    """Validate that an engine points at a structurally valid DPM DB."""

    def __init__(self, engine: Engine) -> None:
        """Bind the service to a SQLAlchemy ``Engine``.

        Args:
            engine: Engine pointing at the database to validate.
        """
        self._engine = engine

    def validate(self) -> SchemaValidationResult:
        """Run a shape + data-sanity check.

        Returns:
            A :class:`SchemaValidationResult` describing what (if
            anything) failed. A database with zero DPM tables yields a
            result where every expected table is reported missing and
            ``is_valid`` is False — no exception is raised.
        """
        start = time.perf_counter()
        backend = self._engine.dialect.name

        expected = {
            name: {c.name for c in table.columns}
            for name, table in Base.metadata.tables.items()
        }

        inspector = inspect(self._engine)
        actual_names = inspector.get_table_names()
        actual_lower_to_real = {n.lower(): n for n in actual_names}

        missing_tables: List[str] = []
        missing_columns: Dict[str, List[str]] = {}

        for table_name, expected_cols in expected.items():
            real_name = actual_lower_to_real.get(table_name.lower())
            if real_name is None:
                missing_tables.append(table_name)
                continue

            actual_cols_lower = {
                c["name"].lower() for c in inspector.get_columns(real_name)
            }
            absent = sorted(
                col
                for col in expected_cols
                if col.lower() not in actual_cols_lower
            )
            if absent:
                missing_columns[table_name] = absent

        empty_required = self._probe_required_tables(actual_lower_to_real)

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        is_valid = not (missing_tables or missing_columns or empty_required)
        return SchemaValidationResult(
            is_valid=is_valid,
            backend=backend,
            missing_tables=sorted(missing_tables),
            missing_columns=dict(sorted(missing_columns.items())),
            empty_required_tables=empty_required,
            elapsed_ms=elapsed_ms,
        )

    def _probe_required_tables(
        self,
        actual_lower_to_real: Dict[str, str],
    ) -> List[str]:
        """Return required seed tables that exist but contain no rows.

        Uses ``SELECT 1 FROM <t> LIMIT 1`` to avoid a full scan. Tables
        that are missing entirely are not reported here — they are
        already covered by ``missing_tables``.
        """
        empty: List[str] = []
        with self._engine.connect() as conn:
            for required in REQUIRED_NON_EMPTY_TABLES:
                real_name = actual_lower_to_real.get(required.lower())
                if real_name is None:
                    continue
                quoted = conn.dialect.identifier_preparer.quote(real_name)
                stmt = text(f"SELECT 1 FROM {quoted} LIMIT 1")  # noqa: S608
                row = conn.execute(stmt).first()
                if row is None:
                    empty.append(required)
        return empty
