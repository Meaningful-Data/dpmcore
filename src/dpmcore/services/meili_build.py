"""End-to-end Meilisearch JSON build service."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dpmcore.services.ecb_validations_import import EcbValidationsImportService
from dpmcore.services.export_csv import ExportCsvService
from dpmcore.services.meili_json import MeiliJsonResult, MeiliJsonService
from dpmcore.loaders.migration import MigrationService


class MeiliBuildError(Exception):
    """Raised when the end-to-end Meilisearch JSON build fails."""


@dataclass(frozen=True)
class MeiliBuildResult:
    """Outcome of a full Meilisearch JSON build."""

    operations_written: int
    output_file: Path
    source_dir: Path
    used_access_file: bool
    ecb_validations_imported: bool


class MeiliBuildService:
    """Build Meilisearch JSON from CSV tables or an Access source file."""

    def build(
        self,
        *,
        output_file: str,
        source_dir: Optional[str] = None,
        access_file: Optional[str] = None,
        ecb_validations_file: Optional[str] = None,
    ) -> MeiliBuildResult:
        """Build the Meilisearch JSON and write it to *output_file*."""
        if access_file and source_dir:
            raise MeiliBuildError(
                "Use either '--access-file' or '--source-dir', not both."
            )

        resolved_source_dir = Path(source_dir or "data/DPM")

        with tempfile.TemporaryDirectory(prefix="dpmcore-meili-") as temp_root:
            temp_root_path = Path(temp_root)
            csv_dir = resolved_source_dir
            used_access_file = access_file is not None

            if access_file is not None:
                csv_dir = temp_root_path / "csv"
                ExportCsvService().export(access_file, csv_dir)

            db_path = temp_root_path / "dpmcore_meili.db"
            database_url = f"sqlite:///{db_path.as_posix()}"
            engine = create_engine(database_url)
            migration_service = MigrationService(engine)

            try:
                migration_service.migrate_from_csv_dir(str(csv_dir))
                if ecb_validations_file:
                    EcbValidationsImportService(engine).import_csv(
                        ecb_validations_file
                    )

                session = sessionmaker(bind=engine)()
                try:
                    json_result: MeiliJsonResult = MeiliJsonService(
                        session
                    ).generate(output_file)
                finally:
                    session.close()
            except Exception as exc:
                raise MeiliBuildError(str(exc)) from exc
            finally:
                engine.dispose()

        return MeiliBuildResult(
            operations_written=json_result.operations_written,
            output_file=json_result.output_file,
            source_dir=csv_dir,
            used_access_file=used_access_file,
            ecb_validations_imported=ecb_validations_file is not None,
        )
