"""Tests for ``_print_capped_warnings``."""

from unittest.mock import MagicMock

from dpmcore.cli.main import _print_capped_warnings


class TestPrintCappedWarnings:
    def test_empty_list_prints_nothing(self):
        console = MagicMock()

        _print_capped_warnings(console, "Warning", [])

        console.print.assert_not_called()

    def test_small_list_prints_every_warning_without_omission_note(self):
        console = MagicMock()

        _print_capped_warnings(console, "Warning", ["a", "b"])

        assert console.print.call_count == 2
        printed = [call.args[0] for call in console.print.call_args_list]
        assert "Warning:[/yellow] a" in printed[0]
        assert "Warning:[/yellow] b" in printed[1]
        assert not any("omitted" in line for line in printed)

    def test_exactly_at_default_limit_prints_no_omission_note(self):
        console = MagicMock()
        warnings = [f"w{i}" for i in range(20)]

        _print_capped_warnings(console, "Warning", warnings)

        assert console.print.call_count == 20

    def test_over_default_limit_caps_at_20_and_reports_the_rest(self):
        console = MagicMock()
        warnings = [f"w{i}" for i in range(25)]

        _print_capped_warnings(console, "Warning", warnings)

        assert console.print.call_count == 21
        printed = [call.args[0] for call in console.print.call_args_list]
        assert "w19" in printed[19]
        assert "w20" not in printed[19]
        assert "... and 5 more warning(s) omitted." in printed[20]

    def test_respects_custom_limit(self):
        console = MagicMock()

        _print_capped_warnings(console, "Warning", ["a", "b", "c"], limit=2)

        assert console.print.call_count == 3
        printed = [call.args[0] for call in console.print.call_args_list]
        assert "... and 1 more warning(s) omitted." in printed[2]

    def test_label_is_lowercased_in_omission_note(self):
        console = MagicMock()
        warnings = [f"w{i}" for i in range(3)]

        _print_capped_warnings(console, "Error", warnings, limit=1)

        printed = [call.args[0] for call in console.print.call_args_list]
        assert "Error:[/yellow] w0" in printed[0]
        assert "2 more error(s) omitted." in printed[1]
