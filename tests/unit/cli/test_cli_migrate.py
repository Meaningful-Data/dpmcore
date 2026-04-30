"""Tests for the dpmcore CLI."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from dpmcore.cli.main import main


@pytest.fixture
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
            "dpmcore.loaders.migration.MigrationService"
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

        from dpmcore.loaders.migration import MigrationError

        with patch(
            "dpmcore.loaders.migration.MigrationService"
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
        assert "serve" in result.output


class TestVersion:
    def test_version_output(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "dpmcore" in result.output
