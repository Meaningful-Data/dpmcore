from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dpmcore.services.meili_build import MeiliBuildError, MeiliBuildService


class TestMeiliBuildService:
    def test_uses_default_source_dir_when_not_provided(self, tmp_path):
        output_file = tmp_path / "operations.json"
        fake_result = MagicMock()
        fake_result.operations_written = 12
        fake_result.output_file = output_file

        with (
            patch(
                "dpmcore.services.meili_build.MigrationService.migrate_from_csv_dir"
            ) as migrate_csv,
            patch(
                "dpmcore.services.meili_build.MeiliJsonService.generate",
                return_value=fake_result,
            ),
        ):
            result = MeiliBuildService().build(output_file=str(output_file))

        migrate_csv.assert_called_once_with(str(Path("data/DPM")))
        assert result.operations_written == 12
        assert result.used_access_file is False
        assert result.ecb_validations_imported is False

    def test_access_file_exports_to_temporary_csv_dir(self, tmp_path):
        access_file = tmp_path / "source.accdb"
        access_file.touch()
        output_file = tmp_path / "operations.json"
        fake_result = MagicMock()
        fake_result.operations_written = 4
        fake_result.output_file = output_file

        with (
            patch(
                "dpmcore.services.meili_build.ExportCsvService.export"
            ) as export_csv,
            patch(
                "dpmcore.services.meili_build.MigrationService.migrate_from_csv_dir"
            ) as migrate_csv,
            patch(
                "dpmcore.services.meili_build.MeiliJsonService.generate",
                return_value=fake_result,
            ),
        ):
            result = MeiliBuildService().build(
                output_file=str(output_file),
                access_file=str(access_file),
            )

        export_csv.assert_called_once()
        migrate_csv.assert_called_once()
        migrated_dir = Path(migrate_csv.call_args.args[0])
        assert migrated_dir.name == "csv"
        assert result.used_access_file is True

    def test_import_ecb_validations_file_when_provided(self, tmp_path):
        validation_csv = tmp_path / "ecb_validations_file.csv"
        validation_csv.write_text(
            "vr_code,start_release\nV1,4.0\n", encoding="utf-8"
        )
        output_file = tmp_path / "operations.json"
        fake_result = MagicMock()
        fake_result.operations_written = 2
        fake_result.output_file = output_file

        with (
            patch(
                "dpmcore.services.meili_build.MigrationService.migrate_from_csv_dir"
            ),
            patch(
                "dpmcore.services.meili_build.EcbValidationsImportService.import_csv"
            ) as import_validations,
            patch(
                "dpmcore.services.meili_build.MeiliJsonService.generate",
                return_value=fake_result,
            ),
        ):
            result = MeiliBuildService().build(
                output_file=str(output_file),
                source_dir="data/DPM",
                ecb_validations_file=str(validation_csv),
            )

        import_validations.assert_called_once_with(str(validation_csv))
        assert result.ecb_validations_imported is True

    def test_access_file_and_source_dir_are_mutually_exclusive(self, tmp_path):
        access_file = tmp_path / "source.accdb"
        access_file.touch()

        with pytest.raises(
            MeiliBuildError, match="either '--access-file' or '--source-dir'"
        ):
            MeiliBuildService().build(
                output_file=str(tmp_path / "operations.json"),
                source_dir="data/DPM",
                access_file=str(access_file),
            )

    def test_does_not_import_ecb_validations_when_not_provided(self, tmp_path):
        output_file = tmp_path / "operations.json"
        fake_result = MagicMock()
        fake_result.operations_written = 12
        fake_result.output_file = output_file

        with (
            patch(
                "dpmcore.services.meili_build.MigrationService.migrate_from_csv_dir"
            ),
            patch(
                "dpmcore.services.meili_build.EcbValidationsImportService.import_csv"
            ) as import_validations,
            patch(
                "dpmcore.services.meili_build.MeiliJsonService.generate",
                return_value=fake_result,
            ),
        ):
            result = MeiliBuildService().build(output_file=str(output_file))

        import_validations.assert_not_called()
        assert result.ecb_validations_imported is False

    def test_inner_exception_is_wrapped_as_meili_build_error(self, tmp_path):
        output_file = tmp_path / "operations.json"

        with patch(
            "dpmcore.services.meili_build.MigrationService.migrate_from_csv_dir",
            side_effect=Exception("CSV parse failed"),
        ):
            with pytest.raises(MeiliBuildError, match="CSV parse failed"):
                MeiliBuildService().build(output_file=str(output_file))

    def test_custom_source_dir_is_passed_to_migration(self, tmp_path):
        custom_dir = tmp_path / "my_csvs"
        custom_dir.mkdir()
        output_file = tmp_path / "operations.json"
        fake_result = MagicMock()
        fake_result.operations_written = 1
        fake_result.output_file = output_file

        with (
            patch(
                "dpmcore.services.meili_build.MigrationService.migrate_from_csv_dir"
            ) as migrate_csv,
            patch(
                "dpmcore.services.meili_build.MeiliJsonService.generate",
                return_value=fake_result,
            ),
        ):
            result = MeiliBuildService().build(
                output_file=str(output_file),
                source_dir=str(custom_dir),
            )

        migrate_csv.assert_called_once_with(str(custom_dir))
        assert result.used_access_file is False
        assert result.source_dir == Path(str(custom_dir))

    def test_default_source_dir_stored_in_result(self, tmp_path):
        output_file = tmp_path / "operations.json"
        fake_result = MagicMock()
        fake_result.operations_written = 0
        fake_result.output_file = output_file

        with (
            patch(
                "dpmcore.services.meili_build.MigrationService.migrate_from_csv_dir"
            ),
            patch(
                "dpmcore.services.meili_build.MeiliJsonService.generate",
                return_value=fake_result,
            ),
        ):
            result = MeiliBuildService().build(output_file=str(output_file))

        assert result.source_dir == Path("data/DPM")
