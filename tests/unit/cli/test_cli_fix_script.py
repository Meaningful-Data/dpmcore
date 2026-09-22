"""Tests for the ``dpmcore fix-script`` CLI subcommand."""

import json

import pytest
from click.testing import CliRunner

from dpmcore.cli.main import main


@pytest.fixture
def runner():
    return CliRunner()


def _script(operations):
    return {
        "http://example.org/mod": {
            "module_code": "MOD",
            "operations": operations,
        }
    }


class TestFixScriptSingleFile:
    def test_known_issue_is_fixed_in_place(self, runner, tmp_path):
        path = tmp_path / "script.json"
        data = _script(
            {
                "v8713_m": {
                    "ast": {
                        "class_name": "VarID",
                        "data": [{"datapoint": 55299}],
                        "default": "",
                    }
                }
            }
        )
        path.write_text(json.dumps(data))

        result = runner.invoke(main, ["fix-script", "--input-path", str(path)])

        assert result.exit_code == 0, result.output
        # Rich may hard-wrap the long absolute tmp_path printed alongside
        # the summary, so only check the whitespace-normalized text.
        assert "1 validations" in " ".join(result.output.split())
        written = json.loads(path.read_text())
        ast = written["http://example.org/mod"]["operations"]["v8713_m"]["ast"]
        assert "default" not in ast

    def test_no_known_issues_leaves_file_untouched(self, runner, tmp_path):
        path = tmp_path / "script.json"
        data = _script(
            {"v0001": {"ast": {"class_name": "VarID", "data": []}}}
        )
        original_text = json.dumps(data)
        path.write_text(original_text)

        result = runner.invoke(main, ["fix-script", "--input-path", str(path)])

        assert result.exit_code == 0, result.output
        assert "No known data-quality issues found" in result.output
        assert path.read_text() == original_text

    def test_missing_file_rejected(self, runner, tmp_path):
        result = runner.invoke(
            main,
            ["fix-script", "--input-path", str(tmp_path / "missing.json")],
        )
        assert result.exit_code != 0

    def test_non_json_file_rejected(self, runner, tmp_path):
        path = tmp_path / "script.txt"
        path.write_text("{}")
        result = runner.invoke(main, ["fix-script", "--input-path", str(path)])
        assert result.exit_code == 1
        assert "not a .json file" in result.output

    def test_directory_without_bulk_flag_rejected(self, runner, tmp_path):
        result = runner.invoke(main, ["fix-script", "--input-path", str(tmp_path)])
        assert result.exit_code == 1
        assert "not a .json file" in result.output

    def test_bulk_against_a_single_file_is_rejected(self, runner, tmp_path):
        path = tmp_path / "script.json"
        path.write_text(json.dumps(_script({})))
        result = runner.invoke(
            main, ["fix-script", "--input-path", str(path), "--bulk"]
        )
        assert result.exit_code == 1
        assert "directory" in result.output


class TestFixScriptBulk:
    def test_fixes_every_json_file_in_directory(self, runner, tmp_path):
        fixed = tmp_path / "a.json"
        fixed.write_text(
            json.dumps(
                _script(
                    {
                        "v7364_m": {
                            "ast": {
                                "class_name": "Constant",
                                "type_": "Integer",
                                "value": 0,
                            }
                        }
                    }
                )
            )
        )
        untouched_data = _script(
            {"v0001": {"ast": {"class_name": "VarID", "data": []}}}
        )
        untouched = tmp_path / "b.json"
        untouched.write_text(json.dumps(untouched_data))

        result = runner.invoke(
            main, ["fix-script", "--input-path", str(tmp_path), "--bulk"]
        )

        assert result.exit_code == 0, result.output
        fixed_ast = json.loads(fixed.read_text())[
            "http://example.org/mod"
        ]["operations"]["v7364_m"]["ast"]
        assert fixed_ast["value"] is True
        assert json.loads(untouched.read_text()) == untouched_data

    def test_empty_directory_rejected(self, runner, tmp_path):
        result = runner.invoke(
            main, ["fix-script", "--input-path", str(tmp_path), "--bulk"]
        )
        assert result.exit_code == 1
        assert "No .json files found" in result.output


class TestHelpExposesCommand:
    def test_help_lists_fix_script(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "fix-script" in result.output
