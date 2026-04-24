"""Tests for the dpmcore CLI."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from dpmcore.cli.main import main


@pytest.fixture()
def runner():
    return CliRunner()


class TestMigrateSuccess:
    def test_exit_0_and_output(self, runner, tmp_path):
        fake_accdb = tmp_path / "test.accdb"
        fake_accdb.touch()

        mock_result = MagicMock()
        mock_result.tables_migrated = 2
        mock_result.total_rows = 10
        mock_result.table_details = {"T1": 4, "T2": 6}
        mock_result.warnings = []
        mock_result.backend_used = "mdbtools"

        with patch(
            "dpmcore.services.migration.MigrationService"
        ) as MockService:
            MockService.return_value.migrate_from_access.return_value = (
                mock_result
            )
            result = runner.invoke(
                main,
                [
                    "migrate",
                    "--source",
                    str(fake_accdb),
                    "--database",
                    "sqlite:///test.db",
                ],
            )

        assert result.exit_code == 0
        assert "T1" in result.output
        assert "T2" in result.output


class TestMigrateMissingOptions:
    def test_missing_source(self, runner):
        result = runner.invoke(
            main,
            ["migrate", "--database", "sqlite:///test.db"],
        )
        assert result.exit_code != 0
        assert (
            "source" in result.output.lower()
            or "missing" in result.output.lower()
            or "required" in result.output.lower()
        )

    def test_missing_database(self, runner, tmp_path):
        fake_accdb = tmp_path / "test.accdb"
        fake_accdb.touch()
        result = runner.invoke(
            main,
            ["migrate", "--source", str(fake_accdb)],
        )
        assert result.exit_code != 0


class TestMigrateError:
    def test_migration_error_exit_1(self, runner, tmp_path):
        fake_accdb = tmp_path / "test.accdb"
        fake_accdb.touch()

        from dpmcore.services.migration import MigrationError

        with patch(
            "dpmcore.services.migration.MigrationService"
        ) as MockService:
            MockService.return_value.migrate_from_access.side_effect = (
                MigrationError("Access driver missing")
            )
            result = runner.invoke(
                main,
                [
                    "migrate",
                    "--source",
                    str(fake_accdb),
                    "--database",
                    "sqlite:///test.db",
                ],
            )

        assert result.exit_code == 1
        assert "Access driver missing" in result.output


class TestHelpText:
    def test_help_shows_commands(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "migrate" in result.output
        assert "build-meili-json" in result.output
        assert "export-csv" in result.output
        assert "serve" in result.output
        assert "migrate-csv-dir" not in result.output
        assert "generate-meili-json" not in result.output


class TestVersion:
    def test_version_output(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "dpmcore" in result.output


class TestExportCsvCli:
    def test_exit_0_and_table_count_in_output(self, runner, tmp_path):
        fake_accdb = tmp_path / "source.accdb"
        fake_accdb.touch()

        mock_result = MagicMock()
        mock_result.tables_exported = 3
        mock_result.table_names = ["Release", "Module", "Organisation"]
        mock_result.output_dir = tmp_path / "data/DPM"

        with patch(
            "dpmcore.services.export_csv.ExportCsvService.export",
            return_value=mock_result,
        ):
            result = runner.invoke(main, ["export-csv", str(fake_accdb)])

        assert result.exit_code == 0
        assert "3 tables" in result.output

    def test_export_csv_error_exits_with_code_1(self, runner, tmp_path):
        fake_accdb = tmp_path / "source.accdb"
        fake_accdb.touch()

        from dpmcore.services.export_csv import ExportCsvError

        with patch(
            "dpmcore.services.export_csv.ExportCsvService.export",
            side_effect=ExportCsvError("mdbtools not found"),
        ):
            result = runner.invoke(main, ["export-csv", str(fake_accdb)])

        assert result.exit_code == 1
        assert "mdbtools not found" in result.output


class TestBuildMeiliJsonCli:
    def test_build_from_default_source_dir(self, runner, tmp_path):
        output_file = tmp_path / "operations.json"

        mock_result = MagicMock()
        mock_result.operations_written = 25
        mock_result.output_file = output_file
        mock_result.used_access_file = False
        mock_result.ecb_validations_imported = False

        with patch(
            "dpmcore.services.meili_build.MeiliBuildService.build",
            return_value=mock_result,
        ):
            result = runner.invoke(
                main,
                [
                    "build-meili-json",
                    "--output",
                    str(output_file),
                ],
            )

        assert result.exit_code == 0
        assert "Generated 25 operations" in result.output

    def test_build_accepts_access_and_validation_flags(self, runner, tmp_path):
        access_file = tmp_path / "source.accdb"
        access_file.touch()
        validation_file = tmp_path / "ecb_validations_file.csv"
        validation_file.write_text(
            "vr_code,start_release\nV1,4.0\n", encoding="utf-8"
        )
        output_file = tmp_path / "operations.json"

        mock_result = MagicMock()
        mock_result.operations_written = 12
        mock_result.output_file = output_file
        mock_result.used_access_file = True
        mock_result.ecb_validations_imported = True

        with patch(
            "dpmcore.services.meili_build.MeiliBuildService.build",
            return_value=mock_result,
        ) as build_mock:
            result = runner.invoke(
                main,
                [
                    "build-meili-json",
                    "--access-file",
                    str(access_file),
                    "--ecb-validations-file",
                    str(validation_file),
                    "--output",
                    str(output_file),
                ],
            )

        assert result.exit_code == 0
        assert "ECB validations imported" in result.output
        assert build_mock.call_args.kwargs["access_file"] == str(access_file)
        assert build_mock.call_args.kwargs["ecb_validations_file"] == str(
            validation_file
        )

    def test_build_rejects_source_dir_and_access_file_together(
        self, runner, tmp_path
    ):
        source_dir = tmp_path / "csv"
        source_dir.mkdir()

        access_file = tmp_path / "source.accdb"
        access_file.touch()

        result = runner.invoke(
            main,
            [
                "build-meili-json",
                "--source-dir",
                str(source_dir),
                "--access-file",
                str(access_file),
            ],
        )

        assert result.exit_code == 1
        assert "either '--access-file' or '--source-dir'" in result.output

    def test_build_prints_access_source_message(self, runner, tmp_path):
        output_file = tmp_path / "operations.json"

        mock_result = MagicMock()
        mock_result.operations_written = 10
        mock_result.output_file = output_file
        mock_result.used_access_file = True
        mock_result.ecb_validations_imported = False

        with patch(
            "dpmcore.services.meili_build.MeiliBuildService.build",
            return_value=mock_result,
        ):
            result = runner.invoke(
                main,
                [
                    "build-meili-json",
                    "--output",
                    str(output_file),
                ],
            )

        assert result.exit_code == 0
        assert "Main DPM source loaded from Access file" in result.output

    def test_build_prints_csv_source_message(self, runner, tmp_path):
        output_file = tmp_path / "operations.json"

        mock_result = MagicMock()
        mock_result.operations_written = 10
        mock_result.output_file = output_file
        mock_result.used_access_file = False
        mock_result.ecb_validations_imported = False

        with patch(
            "dpmcore.services.meili_build.MeiliBuildService.build",
            return_value=mock_result,
        ):
            result = runner.invoke(
                main,
                [
                    "build-meili-json",
                    "--output",
                    str(output_file),
                ],
            )

        assert result.exit_code == 0
        assert "Main DPM source loaded from CSV directory" in result.output

    def test_build_error_exits_with_code_1(self, runner, tmp_path):
        output_file = tmp_path / "operations.json"

        from dpmcore.services.meili_build import MeiliBuildError

        with patch(
            "dpmcore.services.meili_build.MeiliBuildService.build",
            side_effect=MeiliBuildError("CSV directory not found"),
        ):
            result = runner.invoke(
                main,
                ["build-meili-json", "--output", str(output_file)],
            )

        assert result.exit_code == 1
        assert "CSV directory not found" in result.output

    def test_build_with_explicit_source_dir(self, runner, tmp_path):
        source_dir = tmp_path / "my_csvs"
        source_dir.mkdir()
        output_file = tmp_path / "operations.json"

        mock_result = MagicMock()
        mock_result.operations_written = 3
        mock_result.output_file = output_file
        mock_result.used_access_file = False
        mock_result.ecb_validations_imported = False

        with patch(
            "dpmcore.services.meili_build.MeiliBuildService.build",
            return_value=mock_result,
        ) as build_mock:
            result = runner.invoke(
                main,
                [
                    "build-meili-json",
                    "--source-dir",
                    str(source_dir),
                    "--output",
                    str(output_file),
                ],
            )

        assert result.exit_code == 0
        assert build_mock.call_args.kwargs["source_dir"] == str(source_dir)
        assert build_mock.call_args.kwargs["access_file"] is None
