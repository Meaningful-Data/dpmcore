from unittest.mock import patch

import pytest

from dpmcore.services.export_csv import ExportCsvError, ExportCsvResult, ExportCsvService


def test_list_tables_filters_system_tables():
    service = ExportCsvService()

    raw_tables = "Release\nModule\nMSysObjects\n~TmpTable\nCell\n"

    with patch("subprocess.check_output", return_value=raw_tables) as mock_output:
        tables = service._list_tables("/fake.accdb")

    assert tables == ["Release", "Module", "Cell"]
    cmd = mock_output.call_args.args[0]
    assert "-1" in cmd


def test_list_tables_one_per_line_not_split_on_spaces():
    """Table names with spaces must not be split (mdb-tables -1 gives one per line)."""
    service = ExportCsvService()

    raw_tables = "Release\nSome Table\nModule\n"

    with patch("subprocess.check_output", return_value=raw_tables):
        tables = service._list_tables("/fake.accdb")

    assert "Some Table" in tables


def test_export_table_release_uses_date_format(tmp_path):
    service = ExportCsvService()
    target = tmp_path / "Release.csv"

    with patch(
        "subprocess.check_output", return_value="id\n1\n"
    ) as mock_output:
        service._export_table("/fake.accdb", "Release", target)

    mock_output.assert_called_once_with(
        ["mdb-export", "-d", ",", "-T", "%Y-%m-%d", "/fake.accdb", "Release"],
        text=True,
    )
    assert target.read_text(encoding="utf-8") == "id\n1\n"


def test_export_table_non_release_without_date_format(tmp_path):
    service = ExportCsvService()
    target = tmp_path / "Module.csv"

    with patch(
        "subprocess.check_output", return_value="id\n1\n"
    ) as mock_output:
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
        patch.object(
            service, "_list_tables", return_value=["Release", "Module"]
        ),
        patch.object(service, "_export_table"),
    ):
        result = service._export("/fake.accdb", tmp_path)

    assert result.tables_exported == 2
    assert result.output_dir == tmp_path
    assert result.table_names == ["Release", "Module"]


class TestExportSafely:
    def _fake_result(self, tables, output_dir):
        return ExportCsvResult(
            tables_exported=len(tables),
            output_dir=output_dir,
            table_names=tables,
        )

    def test_success_fresh_output_dir(self, tmp_path):
        service = ExportCsvService()
        output_dir = tmp_path / "DPM"

        with patch.object(
            service, "_export", return_value=self._fake_result(["T1", "T2"], output_dir)
        ):
            result = service.export_safely("/fake.accdb", output_dir)

        assert result.tables_exported == 2
        assert result.output_dir == output_dir
        assert output_dir.exists()
        assert not list(tmp_path.glob("DPM.backup-*"))

    def test_success_existing_output_dir_backup_cleaned_up(self, tmp_path):
        service = ExportCsvService()
        output_dir = tmp_path / "DPM"
        output_dir.mkdir()
        (output_dir / "old.csv").write_text("old")

        with patch.object(
            service, "_export", return_value=self._fake_result(["T1"], output_dir)
        ):
            result = service.export_safely("/fake.accdb", output_dir)

        assert result.tables_exported == 1
        assert output_dir.exists()
        assert not list(tmp_path.glob("DPM.backup-*"))

    def test_raises_if_output_is_a_file(self, tmp_path):
        service = ExportCsvService()
        output_path = tmp_path / "DPM"
        output_path.write_text("not a dir")

        with pytest.raises(ExportCsvError, match="not a directory"):
            service.export_safely("/fake.accdb", output_path)

    def test_restores_backup_on_export_csv_error(self, tmp_path):
        service = ExportCsvService()
        output_dir = tmp_path / "DPM"
        output_dir.mkdir()
        (output_dir / "original.csv").write_text("original")

        with patch.object(service, "_export", side_effect=ExportCsvError("mdbtools failed")):
            with pytest.raises(ExportCsvError, match="mdbtools failed"):
                service.export_safely("/fake.accdb", output_dir)

        assert output_dir.exists()
        assert (output_dir / "original.csv").read_text() == "original"

    def test_restores_backup_on_generic_exception(self, tmp_path):
        service = ExportCsvService()
        output_dir = tmp_path / "DPM"
        output_dir.mkdir()
        (output_dir / "original.csv").write_text("original")

        with patch.object(service, "_export", side_effect=RuntimeError("unexpected")):
            with pytest.raises(ExportCsvError, match="unexpected"):
                service.export_safely("/fake.accdb", output_dir)

        assert output_dir.exists()
        assert (output_dir / "original.csv").read_text() == "original"

    def test_temp_dir_cleaned_up_on_success(self, tmp_path):
        service = ExportCsvService()
        output_dir = tmp_path / "DPM"

        with patch.object(
            service, "_export", return_value=self._fake_result(["T1"], output_dir)
        ):
            service.export_safely("/fake.accdb", output_dir)

        assert not list(tmp_path.glob(".DPM.tmp-*"))

    def test_temp_dir_cleaned_up_on_error(self, tmp_path):
        service = ExportCsvService()
        output_dir = tmp_path / "DPM"

        with patch.object(service, "_export", side_effect=ExportCsvError("fail")):
            with pytest.raises(ExportCsvError):
                service.export_safely("/fake.accdb", output_dir)

        assert not list(tmp_path.glob(".DPM.tmp-*"))
