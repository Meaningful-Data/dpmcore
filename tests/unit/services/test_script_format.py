"""Unit tests for the shared Script Format 2.0 helpers."""

import pytest

from dpmcore.services.script_format import FORMAT_VERSION, script_file_name


class TestFormatVersion:
    def test_is_two_zero(self):
        assert FORMAT_VERSION == "2.0"


class TestScriptFileName:
    def test_owner_module_and_version(self):
        assert (
            script_file_name("ECB", "FINREP9", "3.3.0")
            == "ECB-FINREP9-3.3.0.json"
        )

    @pytest.mark.parametrize(
        ("owner", "code", "version"),
        [("", "FINREP9", "3.3.0"), ("ECB", "", "3.3.0"), ("ECB", "X", "")],
    )
    def test_rejects_a_blank_part(self, owner, code, version):
        with pytest.raises(ValueError, match="file name"):
            script_file_name(owner, code, version)
