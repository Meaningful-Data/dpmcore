"""Export Access database tables to CSV files.

Calls ``mdb-tables`` and ``mdb-export`` (mdb-tools) as subprocesses and
writes the raw CSV output directly to disk.
"""

from __future__ import annotations

import subprocess
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

_DATE_FORMAT_TABLES = ("Release",)


class ExportCsvError(Exception):
    """Raised when CSV export cannot proceed."""


@dataclass(frozen=True)
class ExportCsvResult:
    """Outcome of a successful export run."""

    tables_exported: int
    output_dir: Path
    table_names: List[str] = field(default_factory=list)


class ExportCsvService:
    """Export all user tables from a Microsoft Access file to CSV files.

    Requires mdb-tools (``mdb-tables`` + ``mdb-export``) to be installed.
    """

    def export(self, access_path: str, output_dir: Path) -> ExportCsvResult:
        """Export every user table in *access_path* to *output_dir*.

        Args:
            access_path: Filesystem path to an ``.accdb`` or ``.mdb`` file.
            output_dir: Directory where ``<TableName>.csv`` files are written.
                Created (including parents) if it does not exist.

        Returns:
            An :class:`ExportCsvResult` describing what was exported.

        Raises:
            ExportCsvError: If mdb-tools is not available or the file cannot
                be read.
        """
        self._check_mdbtools()
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            table_names = self._list_tables(access_path)
        except subprocess.CalledProcessError as exc:
            raise ExportCsvError(
                f"Could not read tables from '{access_path}': {exc}"
            ) from exc

        max_workers = min(8, max(1, len(table_names)))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_table = {}
            for table in table_names:
                future = executor.submit(
                        self._export_table,
                        access_path,
                        table,
                        output_dir / f"{table}.csv",
                    )

                future_to_table[future] = table

            for future in as_completed(future_to_table):
                table = future_to_table[future]
                try:
                    future.result()
                except Exception as exc:
                    raise ExportCsvError(
                        f"Failed to export table '{table}' from '{access_path}': {exc}"
                    ) from exc
        return ExportCsvResult(
            tables_exported=len(table_names),
            output_dir=output_dir,
            table_names=table_names,
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _check_mdbtools(self) -> None:
        missing = []
        for command in ["mdb-tables", "mdb-export"]:
            if shutil.which(command) is None:
                missing.append(command)
        if missing:
            raise ExportCsvError(
                "mdb-tools is not installed or not available in PATH. "
                f"Missing commands: {', '.join(missing)}"
            )

    def _list_tables(self, access_path: str) -> List[str]:
        raw = subprocess.check_output(  # noqa: S603
            ["mdb-tables", "-1", access_path],  # noqa: S607
            text=True,
        )
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _export_table(
        self, access_path: str, table: str, target_path: Path
    ) -> None:
        cmd = ["mdb-export", "-d", ","]  # noqa: S607
        if table in _DATE_FORMAT_TABLES:
            cmd += ["-T", "%Y-%m-%d"]
        cmd += [access_path, table]

        try:
            csv_text = subprocess.check_output(cmd, text=True)  # noqa: S603
        except subprocess.CalledProcessError as exc:
            raise ExportCsvError(
                f"Failed to export table '{table}' from '{access_path}': {exc}"
            ) from exc

        target_path.write_text(csv_text, encoding="utf-8")
