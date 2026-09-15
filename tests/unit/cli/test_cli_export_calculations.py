"""Tests for the ``dpmcore export-calculations`` CLI subcommand."""

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from dpmcore.cli.main import main
from dpmcore.errors import ConfigurationError
from dpmcore.services.calculations_export import CalculationsExport

_NS_URI = "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/fw/1.0/mod/kri"


@pytest.fixture
def runner():
    return CliRunner()


def _export():
    return CalculationsExport(
        calculations={
            _NS_URI: {
                "module_code": "KRI",
                "framework_code": "FW",
                "module_version": "1.0.0",
                "dpm_release": {
                    "release": "1.0",
                    "publication_date": "2026-01-01",
                },
                "dates": {"from": "2026-01-01", "to": None},
                "calculations": {
                    "ast": {"class_name": "Start", "children": []},
                    "operation_codes": ["c_0001", "c_0002"],
                },
                "output_variables": {"1": "m"},
                "output_tables": {},
                "dependency_modules": {
                    "http://example.org/m1": {"tables": {}}
                },
            }
        },
        datapoints={
            "1": {"table": "T", "row": "0010", "column": "0010", "sheet": None}
        },
    )


@contextmanager
def _patched_connection(export=None, error=None):
    """Patch ``connect`` so the CLI runs without touching a database."""
    db = MagicMock()
    accessor = db.services.ast_generator.calculations_export
    if error is not None:
        accessor.side_effect = error
    else:
        accessor.return_value = export

    connection = MagicMock()
    connection.__enter__.return_value = db
    connection.__exit__.return_value = False
    with patch("dpmcore.connection.connect", return_value=connection) as conn:
        yield conn, accessor


class TestExportCalculationsSuccess:
    def test_writes_both_files(self, runner, tmp_path):
        out = tmp_path / "kri.json"
        with _patched_connection(_export()):
            result = runner.invoke(
                main,
                [
                    "export-calculations",
                    "--module-code",
                    "KRI",
                    "--reference-date",
                    "2026-12-31",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out),
                ],
            )

        assert result.exit_code == 0, result.output
        payload = json.loads(out.read_text())
        assert list(payload) == [_NS_URI]
        datapoints = json.loads((tmp_path / "kri_datapoints.json").read_text())
        assert datapoints["1"]["table"] == "T"

    def test_reports_what_it_wrote(self, runner, tmp_path):
        out = tmp_path / "kri.json"
        with _patched_connection(_export()):
            result = runner.invoke(
                main,
                [
                    "export-calculations",
                    "--module-code",
                    "KRI",
                    "--reference-date",
                    "2026-12-31",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out),
                ],
            )

        normalized = " ".join(result.output.split())
        assert "2 calculations" in normalized
        assert "1 dependency modules" in normalized
        assert "1 datapoints" in normalized

    def test_honours_an_explicit_datapoints_path(self, runner, tmp_path):
        out = tmp_path / "kri.json"
        dp = tmp_path / "elsewhere" / "dp.json"
        with _patched_connection(_export()):
            result = runner.invoke(
                main,
                [
                    "export-calculations",
                    "--module-code",
                    "KRI",
                    "--reference-date",
                    "2026-12-31",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out),
                    "--datapoints-output",
                    str(dp),
                ],
            )

        assert result.exit_code == 0, result.output
        assert dp.exists()
        assert not (tmp_path / "kri_datapoints.json").exists()

    def test_defaults_the_output_to_the_module_code(self, runner):
        with runner.isolated_filesystem(), _patched_connection(_export()):
            result = runner.invoke(
                main,
                [
                    "export-calculations",
                    "--module-code",
                    "KRI",
                    "--reference-date",
                    "2026-12-31",
                    "--database",
                    "sqlite:///:memory:",
                ],
            )

            assert result.exit_code == 0, result.output
            assert "KRI.json" in result.output
            assert "KRI_datapoints.json" in result.output

    def test_passes_every_argument_through(self, runner, tmp_path):
        with _patched_connection(_export()) as (connect, accessor):
            runner.invoke(
                main,
                [
                    "export-calculations",
                    "--module-code",
                    "KRI",
                    "--reference-date",
                    "2026-12-31",
                    "--publication-date",
                    "2026-01-01",
                    "--database",
                    "sqlite:///dpm.db",
                    "--output",
                    str(tmp_path / "kri.json"),
                ],
            )

        connect.assert_called_once_with("sqlite:///dpm.db")
        assert accessor.call_args.args == ("KRI", "2026-12-31", "2026-01-01")


class TestExportCalculationsFailure:
    def test_a_dictionary_error_exits_non_zero(self, runner, tmp_path):
        error = ConfigurationError(
            title="OperationOutput table missing",
            description="This database has no OperationOutput table",
        )
        with _patched_connection(error=error):
            result = runner.invoke(
                main,
                [
                    "export-calculations",
                    "--module-code",
                    "KRI",
                    "--reference-date",
                    "2026-12-31",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(tmp_path / "kri.json"),
                ],
            )

        assert result.exit_code == 1
        assert "OperationOutput table missing" in result.output
        assert not (tmp_path / "kri.json").exists()

    @pytest.mark.parametrize(
        "missing", ["--module-code", "--reference-date", "--database"]
    )
    def test_the_required_options_are_required(self, runner, missing):
        args = [
            "export-calculations",
            "--module-code",
            "KRI",
            "--reference-date",
            "2026-12-31",
            "--database",
            "sqlite:///:memory:",
        ]
        index = args.index(missing)
        del args[index : index + 2]

        result = runner.invoke(main, args)

        assert result.exit_code != 0
        assert missing in result.output
