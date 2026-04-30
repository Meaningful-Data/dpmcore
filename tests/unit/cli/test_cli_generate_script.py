"""Tests for the ``dpmcore generate-script`` CLI subcommand."""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from dpmcore.cli.main import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def expressions_file(tmp_path):
    """A JSON expressions file in the new object format."""
    path = tmp_path / "expressions.json"
    path.write_text(
        json.dumps(
            {
                "expressions": [
                    [
                        "{tF_01.01, r0010, c0010} = {tF_01.01, r0020, c0010}",
                        "v0001",
                    ],
                    ["{tF_01.01, r0030, c0010} >= 0", "v0002"],
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def expressions_with_preconditions_file(tmp_path):
    """A JSON file with both expressions and preconditions."""
    path = tmp_path / "expressions_with_pre.json"
    path.write_text(
        json.dumps(
            {
                "expressions": [
                    ["{tF_01.01, r0010, c0010} >= 0", "v0001"],
                    ["{tF_01.01, r0020, c0010} >= 0", "v0002"],
                ],
                "preconditions": [
                    ["{is_reporting_entity}", ["v0001", "v0002"]],
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _success_result():
    return {
        "success": True,
        "enriched_ast": [{"ml": "stub"}],
        "dependency_information": {
            "intra_instance_validations": ["v0001"],
            "cross_instance_dependencies": [],
            "alternative_dependencies": [],
        },
        "dependency_modules": {
            "http://example.org/m1": {"tables": {}, "variables": {}},
        },
    }


class TestGenerateScriptSuccess:
    def test_writes_output_file(self, runner, expressions_file, tmp_path):
        out = tmp_path / "script.json"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.script.return_value = _success_result()
            result = runner.invoke(
                main,
                [
                    "generate-script",
                    "--expressions",
                    str(expressions_file),
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out),
                    "--module-code",
                    "FINREP_Con",
                    "--module-version",
                    "2.0.1",
                ],
            )

        assert result.exit_code == 0, result.output
        assert out.exists()
        payload = json.loads(out.read_text())
        assert payload["success"] is True
        assert "dependency_modules" in payload
        assert "1 dependency modules" in result.output

    def test_passes_all_args_to_service(
        self, runner, expressions_file, tmp_path
    ):
        out = tmp_path / "script.json"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.script.return_value = _success_result()
            runner.invoke(
                main,
                [
                    "generate-script",
                    "--expressions",
                    str(expressions_file),
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out),
                    "--module-code",
                    "FINREP_Con",
                    "--module-version",
                    "2.0.1",
                    "--severity",
                    "error",
                ],
            )

        kwargs = Svc.return_value.script.call_args.kwargs
        assert kwargs["module_code"] == "FINREP_Con"
        assert kwargs["module_version"] == "2.0.1"
        assert kwargs["severity"] == "error"
        assert kwargs["expressions"] == [
            (
                "{tF_01.01, r0010, c0010} = {tF_01.01, r0020, c0010}",
                "v0001",
            ),
            ("{tF_01.01, r0030, c0010} >= 0", "v0002"),
        ]
        # No preconditions in the file -> None.
        assert kwargs["preconditions"] is None

    def test_propagates_preconditions(
        self, runner, expressions_with_preconditions_file, tmp_path
    ):
        out = tmp_path / "script.json"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.script.return_value = _success_result()
            runner.invoke(
                main,
                [
                    "generate-script",
                    "--expressions",
                    str(expressions_with_preconditions_file),
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out),
                    "--module-code",
                    "FINREP_Con",
                    "--module-version",
                    "2.0.1",
                ],
            )

        kwargs = Svc.return_value.script.call_args.kwargs
        assert kwargs["preconditions"] == [
            ("{is_reporting_entity}", ["v0001", "v0002"]),
        ]


class TestGenerateScriptFailure:
    def test_service_failure_exits_1(self, runner, expressions_file, tmp_path):
        out = tmp_path / "script.json"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.script.return_value = {
                "success": False,
                "enriched_ast": None,
                "error": "boom",
            }
            result = runner.invoke(
                main,
                [
                    "generate-script",
                    "--expressions",
                    str(expressions_file),
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out),
                    "--module-code",
                    "FINREP_Con",
                    "--module-version",
                    "2.0.1",
                ],
            )

        assert result.exit_code == 1
        assert "boom" in result.output
        assert not out.exists()

    def test_legacy_flat_list_rejected(self, runner, tmp_path):
        legacy = tmp_path / "expressions.json"
        legacy.write_text(json.dumps([["expr", "v"]]), encoding="utf-8")
        out = tmp_path / "script.json"

        result = runner.invoke(
            main,
            [
                "generate-script",
                "--expressions",
                str(legacy),
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(out),
                "--module-code",
                "MOD",
                "--module-version",
                "1.0",
            ],
        )

        assert result.exit_code == 1
        assert "Invalid expressions file" in result.output
        assert "flat-list form is no longer supported" in result.output


class TestGenerateScriptValidation:
    def test_missing_expressions_file_rejected_by_click(
        self, runner, tmp_path
    ):
        out = tmp_path / "script.json"
        result = runner.invoke(
            main,
            [
                "generate-script",
                "--expressions",
                str(tmp_path / "does-not-exist.json"),
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(out),
                "--module-code",
                "MOD",
                "--module-version",
                "1.0",
            ],
        )
        assert result.exit_code != 0
        assert (
            "does not exist" in result.output.lower()
            or "no such file" in result.output.lower()
        )

    def test_missing_required_database(
        self, runner, expressions_file, tmp_path
    ):
        out = tmp_path / "script.json"
        result = runner.invoke(
            main,
            [
                "generate-script",
                "--expressions",
                str(expressions_file),
                "--output",
                str(out),
                "--module-code",
                "MOD",
                "--module-version",
                "1.0",
            ],
        )
        assert result.exit_code != 0

    def test_missing_required_module_code(
        self, runner, expressions_file, tmp_path
    ):
        out = tmp_path / "script.json"
        result = runner.invoke(
            main,
            [
                "generate-script",
                "--expressions",
                str(expressions_file),
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(out),
                "--module-version",
                "1.0",
            ],
        )
        assert result.exit_code != 0

    def test_missing_required_module_version(
        self, runner, expressions_file, tmp_path
    ):
        out = tmp_path / "script.json"
        result = runner.invoke(
            main,
            [
                "generate-script",
                "--expressions",
                str(expressions_file),
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(out),
                "--module-code",
                "MOD",
            ],
        )
        assert result.exit_code != 0


class TestHelpExposesCommand:
    def test_help_lists_generate_script(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "generate-script" in result.output
