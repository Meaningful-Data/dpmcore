"""Tests for the ``dpmcore import-xbrl`` CLI command."""

from pathlib import Path

from click.testing import CliRunner

from dpmcore.cli.main import main

FIXTURES = (
    Path(__file__).parent.parent.parent / "fixtures" / "xbrl"
)


def run(*args):
    return CliRunner().invoke(main, ["import-xbrl", *args])


def seg_args(tmp_path, **extra):
    args = [
        "--source",
        str(FIXTURES / "seg2008"),
        "--framework-code",
        "SEG",
        "--release-code",
        "2008-01-01",
        "--release-date",
        "2008-01-01",
        "--database",
        f"sqlite:///{tmp_path / 'seg.db'}",
        "--offline",
    ]
    for key, value in extra.items():
        args.extend([f"--{key.replace('_', '-')}", value])
    return args


class TestImportXbrl:
    def test_fresh_import_reports_counts(self, tmp_path):
        result = run(*seg_args(tmp_path))
        assert result.exit_code == 0, result.output
        assert "XBRL Import Results" in result.output
        assert "eurofiling2006" in result.output
        assert "TableVersion" in result.output
        assert "Release ID:" in result.output
        assert "Database:" in result.output

    def test_dpm1_import(self, tmp_path):
        result = run(
            "--source",
            str(FIXTURES / "mini_dpm1"),
            "--framework-code",
            "MINI",
            "--release-code",
            "1.0.0",
            "--database",
            f"sqlite:///{tmp_path / 'mini.db'}",
        )
        assert result.exit_code == 0, result.output
        assert "dpm1" in result.output

    def test_into_existing_database(self, tmp_path):
        first = run(
            *seg_args(tmp_path),
            "--output",
            str(tmp_path / "dpm.db"),
        )
        assert first.exit_code == 0, first.output
        second = run(
            "--source",
            str(FIXTURES / "fib2008"),
            "--framework-code",
            "FIB",
            "--release-code",
            "FIB-2008",
            "--into",
            f"sqlite:///{tmp_path / 'dpm.db'}",
            "--offline",
        )
        assert second.exit_code == 0, second.output
        assert "Framework" in second.output

    def test_database_and_into_are_mutually_exclusive(self, tmp_path):
        result = run(
            *seg_args(tmp_path),
            "--into",
            f"sqlite:///{tmp_path / 'other.db'}",
        )
        assert result.exit_code == 1
        assert "exactly one of" in result.output

    def test_neither_database_nor_into(self):
        result = run(
            "--source",
            str(FIXTURES / "seg2008"),
            "--framework-code",
            "SEG",
            "--release-code",
            "2008-01-01",
        )
        assert result.exit_code == 1
        assert "exactly one of" in result.output

    def test_import_error_is_reported(self, tmp_path):
        result = run(
            "--source",
            str(FIXTURES / "seg2008"),
            "--framework-code",
            "SEG",
            "--release-code",
            "2008-01-01",
            "--architecture",
            "dpm1",
            "--database",
            f"sqlite:///{tmp_path / 'x.db'}",
        )
        assert result.exit_code == 1
        assert "Error:" in result.output

    def test_entry_option_is_forwarded(self, tmp_path):
        result = run(
            *seg_args(tmp_path),
            "--entry",
            "t-Segr-2008-01-01.xsd",
        )
        assert result.exit_code == 0, result.output

    def test_warnings_are_printed(self, tmp_path):
        result = run(
            *seg_args(tmp_path),
            "--max-columns",
            "1",
        )
        assert result.exit_code == 0, result.output
        assert "Warning:" in result.output
