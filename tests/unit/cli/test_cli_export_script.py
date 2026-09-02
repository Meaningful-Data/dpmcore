"""Tests for the ``dpmcore export-script`` CLI subcommand."""

import json
import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from dpmcore.cli.main import main


@pytest.fixture
def runner():
    return CliRunner()


_NS_URI = "http://example.org/mod"


def _success_result():
    return {
        "success": True,
        "enriched_ast": {
            _NS_URI: {
                "module_code": "FINREP_Con",
                "module_version": "2.0.1",
                "framework_code": "FINREP",
                "dpm_release": {
                    "release": "4.2",
                    "publication_date": "2025-04-28",
                },
                "dates": {"from": "2026-03-31", "to": None},
                "operations": {
                    "v0001": {
                        "version_id": 1234,
                        "code": "v0001",
                        "expression": "expr",
                        "root_operator_id": 24,
                        "ast": {"class_name": "BinOp"},
                        "from_submission_date": "2026-03-31",
                        "severity": "error",
                    },
                    "v0002": {
                        "version_id": 1235,
                        "code": "v0002",
                        "expression": "expr2",
                        "root_operator_id": 24,
                        "ast": {"class_name": "BinOp"},
                        "from_submission_date": "2026-03-31",
                        "severity": "warning",
                    },
                },
                "variables": {},
                "tables": {},
                "preconditions": {},
                "precondition_variables": {},
                "dependency_information": {
                    "intra_instance_validations": ["v0001", "v0002"],
                    "cross_instance_dependencies": [],
                    "alternative_dependencies": [],
                },
                "dependency_modules": {
                    "http://example.org/m1": {
                        "tables": {},
                        "variables": {},
                    },
                },
            }
        },
        "error": None,
        "failed_operations": {},
    }


class TestExportScriptSuccess:
    def test_writes_output_file(self, runner, tmp_path):
        out = tmp_path / "script.json"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.script_for_module.return_value = (
                _success_result()
            )
            result = runner.invoke(
                main,
                [
                    "export-script",
                    "--module-code",
                    "FINREP_Con",
                    "--module-version",
                    "2.0.1",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out),
                ],
            )

        assert result.exit_code == 0, result.output
        assert out.exists()
        payload = json.loads(out.read_text())
        assert payload["success"] is True
        ns = payload["enriched_ast"][_NS_URI]
        assert "dependency_modules" in ns
        # Rich wraps long lines according to console width, and the tmp_path
        # in the printed line varies in length across runs/machines, so the
        # wrap point can land inside these phrases; normalize whitespace
        # before matching.
        normalized_output = " ".join(result.output.split())
        assert "2 validations discovered" in normalized_output
        assert "1 dependency modules" in normalized_output

    def test_passes_all_args_to_service(self, runner, tmp_path):
        # --release is intentionally omitted: it is mutually exclusive
        # with --module-version (see TestExportScriptSweepValidation).
        # Release pass-through for a single target is covered by
        # TestExportScriptReleaseOnlyMode instead.
        out = tmp_path / "script.json"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.script_for_module.return_value = (
                _success_result()
            )
            runner.invoke(
                main,
                [
                    "export-script",
                    "--module-code",
                    "FINREP_Con",
                    "--module-version",
                    "2.0.1",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out),
                ],
            )

        kwargs = Svc.return_value.script_for_module.call_args.kwargs
        assert kwargs["module_code"] == "FINREP_Con"
        assert kwargs["module_version"] == "2.0.1"
        assert kwargs["release"] is None

    def test_no_expressions_option_exists(self, runner, tmp_path):
        out = tmp_path / "script.json"
        result = runner.invoke(
            main,
            [
                "export-script",
                "--expressions",
                "does-not-matter.json",
                "--module-code",
                "MOD",
                "--module-version",
                "1.0",
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code != 0
        assert "no such option" in result.output.lower()


class TestExportScriptFailure:
    def test_service_failure_exits_1(self, runner, tmp_path):
        out = tmp_path / "script.json"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.script_for_module.return_value = {
                "success": False,
                "enriched_ast": None,
                "error": "boom",
                "failed_operations": {},
            }
            result = runner.invoke(
                main,
                [
                    "export-script",
                    "--module-code",
                    "FINREP_Con",
                    "--module-version",
                    "2.0.1",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out),
                ],
            )

        assert result.exit_code == 1
        assert "boom" in result.output
        assert not out.exists()


class TestExportScriptValidation:
    def test_missing_required_database(self, runner, tmp_path):
        out = tmp_path / "script.json"
        result = runner.invoke(
            main,
            [
                "export-script",
                "--module-code",
                "MOD",
                "--module-version",
                "1.0",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code != 0

    def test_missing_required_module_code(self, runner, tmp_path):
        out = tmp_path / "script.json"
        result = runner.invoke(
            main,
            [
                "export-script",
                "--module-version",
                "1.0",
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code != 0

    def test_missing_required_module_version(self, runner, tmp_path):
        out = tmp_path / "script.json"
        result = runner.invoke(
            main,
            [
                "export-script",
                "--module-code",
                "MOD",
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code != 0


class TestExportScriptDatabaseArgument:
    def test_invalid_database_url_shows_friendly_error(self, runner, tmp_path):
        result = runner.invoke(
            main,
            [
                "export-script",
                "--module-code",
                "MOD",
                "--module-version",
                "1.0",
                "--database",
                "/not/a/sqlalchemy/url",
                "--output",
                str(tmp_path / "out.json"),
            ],
        )
        assert result.exit_code == 1
        assert "not a valid SQLAlchemy URL" in result.output
        assert "/not/a/sqlalchemy/url" in result.output


class TestExportScriptListModuleVersionsError:
    def test_value_error_from_list_module_versions_is_reported(
        self, runner, tmp_path
    ):
        out_dir = tmp_path / "out"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.list_module_versions.side_effect = ValueError(
                "Unknown release code. Possible values: ['4.2', '4.3']"
            )
            result = runner.invoke(
                main,
                [
                    "export-script",
                    "--all-modules",
                    "--release",
                    "9.9",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out_dir),
                ],
            )

        assert result.exit_code == 1
        assert "Unknown release code" in result.output
        assert not out_dir.exists()


class TestHelpExposesCommand:
    def test_help_lists_export_script(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "export-script" in result.output


class TestExportScriptSweep:
    def test_all_modules_all_versions_writes_one_file_per_target(
        self, runner, tmp_path
    ):
        out_dir = tmp_path / "out"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.list_module_versions.return_value = [
                ("MOD_A", "1.0"),
                ("MOD_B", "2.0"),
            ]
            Svc.return_value.script_for_module.return_value = (
                _success_result()
            )
            result = runner.invoke(
                main,
                [
                    "export-script",
                    "--all-modules",
                    "--all-versions",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out_dir),
                ],
            )

        assert result.exit_code == 0, result.output
        assert (out_dir / "MOD_A-1.0.json").exists()
        assert (out_dir / "MOD_B-2.0.json").exists()
        assert "2 succeeded, 0 failed" in result.output

    def test_failed_target_does_not_abort_sweep(self, runner, tmp_path):
        out_dir = tmp_path / "out"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.list_module_versions.return_value = [
                ("MOD_A", "1.0"),
                ("MOD_B", "2.0"),
            ]
            Svc.return_value.script_for_module.side_effect = [
                {
                    "success": False,
                    "enriched_ast": None,
                    "error": "boom",
                    "failed_operations": {},
                },
                _success_result(),
            ]
            result = runner.invoke(
                main,
                [
                    "export-script",
                    "--module-code",
                    "FINREP_Con",
                    "--all-versions",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out_dir),
                ],
            )

        assert result.exit_code == 1
        assert not (out_dir / "MOD_A-1.0.json").exists()
        assert (out_dir / "MOD_B-2.0.json").exists()
        assert "1 succeeded, 1 failed" in result.output
        assert "boom" in result.output

    def test_no_targets_found_exits_1(self, runner, tmp_path):
        out_dir = tmp_path / "out"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.list_module_versions.return_value = []
            result = runner.invoke(
                main,
                [
                    "export-script",
                    "--all-modules",
                    "--all-versions",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out_dir),
                ],
            )
        assert result.exit_code == 1

    def test_sweep_defaults_output_to_current_directory(self, runner):
        with runner.isolated_filesystem():
            with patch(
                "dpmcore.services.ast_generator.ASTGeneratorService"
            ) as Svc:
                Svc.return_value.list_module_versions.return_value = [
                    ("MOD_A", "1.0"),
                ]
                Svc.return_value.script_for_module.return_value = (
                    _success_result()
                )
                result = runner.invoke(
                    main,
                    [
                        "export-script",
                        "--all-modules",
                        "--all-versions",
                        "--database",
                        "sqlite:///:memory:",
                    ],
                )
            assert result.exit_code == 0, result.output
            assert os.path.exists("MOD_A-1.0.json")

    def test_output_must_be_a_directory_when_sweeping(self, runner, tmp_path):
        existing_file = tmp_path / "not_a_dir.json"
        existing_file.write_text("{}")
        result = runner.invoke(
            main,
            [
                "export-script",
                "--all-modules",
                "--all-versions",
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(existing_file),
            ],
        )
        assert result.exit_code != 0
        assert "must be a directory" in result.output


class TestExportScriptOutputDefaults:
    def test_single_target_defaults_output_filename(self, runner):
        with runner.isolated_filesystem():
            with patch(
                "dpmcore.services.ast_generator.ASTGeneratorService"
            ) as Svc:
                Svc.return_value.script_for_module.return_value = (
                    _success_result()
                )
                result = runner.invoke(
                    main,
                    [
                        "export-script",
                        "--module-code",
                        "FINREP_Con",
                        "--module-version",
                        "2.0.1",
                        "--database",
                        "sqlite:///:memory:",
                    ],
                )
            assert result.exit_code == 0, result.output
            assert os.path.exists("FINREP_Con-2.0.1.json")


class TestExportScriptSweepValidation:
    def test_module_code_and_all_modules_mutually_exclusive(
        self, runner, tmp_path
    ):
        result = runner.invoke(
            main,
            [
                "export-script",
                "--module-code",
                "MOD",
                "--all-modules",
                "--all-versions",
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code != 0
        assert "exactly one of --module-code" in result.output

    def test_module_version_and_all_versions_mutually_exclusive(
        self, runner, tmp_path
    ):
        result = runner.invoke(
            main,
            [
                "export-script",
                "--module-code",
                "MOD",
                "--module-version",
                "1.0",
                "--all-versions",
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    def test_module_version_with_all_modules_rejected(self, runner, tmp_path):
        result = runner.invoke(
            main,
            [
                "export-script",
                "--all-modules",
                "--module-version",
                "1.0",
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code != 0
        assert "requires --module-code" in result.output

    def test_no_version_selector_rejected_with_module_code(
        self, runner, tmp_path
    ):
        result = runner.invoke(
            main,
            [
                "export-script",
                "--module-code",
                "MOD",
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(tmp_path / "out.json"),
            ],
        )
        assert result.exit_code != 0
        assert (
            "Specify one of --module-version, --all-versions, or "
            "--release" in result.output
        )

    def test_no_version_selector_rejected_with_all_modules(
        self, runner, tmp_path
    ):
        result = runner.invoke(
            main,
            [
                "export-script",
                "--all-modules",
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code != 0
        assert (
            "Specify one of --module-version, --all-versions, or "
            "--release" in result.output
        )

    def test_release_with_module_version_mutually_exclusive(
        self, runner, tmp_path
    ):
        result = runner.invoke(
            main,
            [
                "export-script",
                "--module-code",
                "MOD",
                "--module-version",
                "1.0",
                "--release",
                "4.2",
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(tmp_path / "out.json"),
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    def test_release_with_all_versions_mutually_exclusive(
        self, runner, tmp_path
    ):
        result = runner.invoke(
            main,
            [
                "export-script",
                "--module-code",
                "MOD",
                "--all-versions",
                "--release",
                "4.2",
                "--database",
                "sqlite:///:memory:",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output


class TestExportScriptReleaseOnlyMode:
    """``--release`` alone (no ``--module-version``/``--all-versions``)
    resolves each targeted module to its version active at that release.
    """

    def test_module_code_with_release_only_resolves_single_target(
        self, runner, tmp_path
    ):
        out_dir = tmp_path / "out"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.list_module_versions.return_value = [
                ("FINREP_Con", "2.0.1"),
            ]
            Svc.return_value.script_for_module.return_value = (
                _success_result()
            )
            result = runner.invoke(
                main,
                [
                    "export-script",
                    "--module-code",
                    "FINREP_Con",
                    "--release",
                    "4.2",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out_dir),
                ],
            )

        assert result.exit_code == 0, result.output
        assert (out_dir / "FINREP_Con-2.0.1.json").exists()
        list_kwargs = Svc.return_value.list_module_versions.call_args.kwargs
        assert list_kwargs["module_code"] == "FINREP_Con"
        assert list_kwargs["release"] == "4.2"

    def test_all_modules_with_release_only_sweeps_every_module(
        self, runner, tmp_path
    ):
        out_dir = tmp_path / "out"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.list_module_versions.return_value = [
                ("MOD_A", "1.0"),
                ("MOD_B", "2.0"),
            ]
            Svc.return_value.script_for_module.return_value = (
                _success_result()
            )
            result = runner.invoke(
                main,
                [
                    "export-script",
                    "--all-modules",
                    "--release",
                    "4.2",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out_dir),
                ],
            )

        assert result.exit_code == 0, result.output
        assert (out_dir / "MOD_A-1.0.json").exists()
        assert (out_dir / "MOD_B-2.0.json").exists()
        list_kwargs = Svc.return_value.list_module_versions.call_args.kwargs
        assert list_kwargs["module_code"] is None
        assert list_kwargs["release"] == "4.2"

    def test_release_only_passes_release_through_to_script_for_module(
        self, runner, tmp_path
    ):
        out_dir = tmp_path / "out"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.list_module_versions.return_value = [
                ("FINREP_Con", "2.0.1"),
            ]
            Svc.return_value.script_for_module.return_value = (
                _success_result()
            )
            runner.invoke(
                main,
                [
                    "export-script",
                    "--module-code",
                    "FINREP_Con",
                    "--release",
                    "4.2",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out_dir),
                ],
            )

        kwargs = Svc.return_value.script_for_module.call_args.kwargs
        assert kwargs["module_code"] == "FINREP_Con"
        assert kwargs["module_version"] == "2.0.1"
        assert kwargs["release"] == "4.2"

    def test_no_targets_at_release_exits_1(self, runner, tmp_path):
        out_dir = tmp_path / "out"
        with patch(
            "dpmcore.services.ast_generator.ASTGeneratorService"
        ) as Svc:
            Svc.return_value.list_module_versions.return_value = []
            result = runner.invoke(
                main,
                [
                    "export-script",
                    "--module-code",
                    "FINREP_Con",
                    "--release",
                    "4.2",
                    "--database",
                    "sqlite:///:memory:",
                    "--output",
                    str(out_dir),
                ],
            )
        assert result.exit_code == 1
        assert "No active module versions matched" in result.output
