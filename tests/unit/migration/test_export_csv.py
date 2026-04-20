import pytest
from unittest.mock import patch

from dpmcore.services.export_csv import ExportCsvError, ExportCsvService


def test_list_tables_filters_system_tables():
    service = ExportCsvService()

    raw_tables = "Release\nModule\nCell\n"

    with patch("subprocess.check_output", return_value=raw_tables):
        tables = service._list_tables("/fake.accdb")

    assert tables == ["Release", "Module", "Cell"]

def test_export_table_release_uses_date_format(tmp_path):
    service = ExportCsvService()
    target = tmp_path / "Release.csv"

    with patch("subprocess.check_output", return_value="id\n1\n") as mock_output:
        service._export_table("/fake.accdb", "Release", target)

    mock_output.assert_called_once_with(
        ["mdb-export", "-d", ",", "-T", "%Y-%m-%d", "/fake.accdb", "Release"],
        text=True,
    )
    assert target.read_text(encoding="utf-8") == "id\n1\n"

def test_export_table_non_release_without_date_format(tmp_path):
    service = ExportCsvService()
    target = tmp_path / "Module.csv"

    with patch("subprocess.check_output", return_value="id\n1\n") as mock_output:
        service._export_table("/fake.accdb", "Module", target)

    mock_output.assert_called_once_with(
        ["mdb-export", "-d", ",", "/fake.accdb", "Module"],
        text=True,
    )

def test_check_mdbtools_raises_if_missing():
    service = ExportCsvService()

    with patch("shutil.which", return_value=None):
        with pytest.raises(ExportCsvError, match="Missing commands"):
            service._check_mdbtools()

def test_export_returns_result(tmp_path):
    service = ExportCsvService()

    with (
        patch.object(service, "_check_mdbtools"),
        patch.object(service, "_list_tables", return_value=["Release", "Module"]),
        patch.object(service, "_export_table"),
    ):
        result = service.export("/fake.accdb", tmp_path)

    assert result.tables_exported == 2
    assert result.output_dir == tmp_path
    assert result.table_names == ["Release", "Module"]