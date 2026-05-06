"""CLI tests for ``dpmcore export-layout``."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from dpmcore.cli.main import main


def _fake_db():
    """Return a MagicMock that quacks like the connect() context manager."""
    fake_svc = MagicMock()
    fake_svc.export_module.return_value = Path(str(Path("out.xlsx").resolve()))
    fake_svc.export_tables.return_value = Path(str(Path("out.xlsx").resolve()))
    db = MagicMock()
    db.services.layout_exporter = fake_svc
    cm = MagicMock()
    cm.__enter__.return_value = db
    cm.__exit__.return_value = False
    return cm, fake_svc


def test_export_layout_requires_module_or_tables():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["export-layout", "--database", "sqlite:///:memory:"],
    )
    assert result.exit_code != 0
    assert "Provide --module or --tables." in result.output


def test_export_layout_module_invokes_service():
    runner = CliRunner()
    cm, svc = _fake_db()
    with patch("dpmcore.connection.connect", return_value=cm):
        result = runner.invoke(
            main,
            [
                "export-layout",
                "--database",
                "sqlite:///:memory:",
                "--module",
                "FINREP9",
                "--release",
                "4.2",
                "--output",
                str(Path("out.xlsx").resolve()),
            ],
        )
    assert result.exit_code == 0, result.output
    svc.export_module.assert_called_once()
    args, _ = svc.export_module.call_args
    assert args[0] == "FINREP9"
    assert args[1] == "4.2"
    assert args[2] == str(Path("out.xlsx").resolve())
    assert "Exported to" in result.output


def test_export_layout_tables_invokes_service():
    runner = CliRunner()
    cm, svc = _fake_db()
    with patch("dpmcore.connection.connect", return_value=cm):
        result = runner.invoke(
            main,
            [
                "export-layout",
                "--database",
                "sqlite:///:memory:",
                "--tables",
                "F_01.01, F_01.02",
                "--no-annotate",
                "--no-comments",
            ],
        )
    assert result.exit_code == 0, result.output
    svc.export_tables.assert_called_once()
    args, _ = svc.export_tables.call_args
    assert args[0] == ["F_01.01", "F_01.02"]
    config = args[3]
    assert config.annotate is False
    assert config.add_cell_comments is False
    assert config.add_header_comments is False
