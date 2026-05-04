from unittest.mock import patch

from click.testing import CliRunner

from dpmcore.cli.main import main
from dpmcore.services.export_csv import ExportCsvResult


def test_export_csv_cli_success(tmp_path):
    runner = CliRunner()

    source = tmp_path / "fake.accdb"
    source.write_text("dummy")

    fake_result = ExportCsvResult(
        tables_exported=2,
        output_dir=tmp_path,
        table_names=["Release", "Module"],
    )

    with patch(
        "dpmcore.services.export_csv.ExportCsvService.export_safely",
        return_value=fake_result,
    ):
        result = runner.invoke(
            main,
            ["export-csv", str(source), "--output-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
