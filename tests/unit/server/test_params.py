"""Unit tests for the SDMX URL parameter parser."""

from dpmcore.server.params import (
    StructureParams,
    VersionKeyword,
    parse_structure_params,
)


class TestParseDefaults:
    def test_all_defaults(self):
        p = parse_structure_params()
        assert p.owners == ["*"]
        assert p.ids == ["*"]
        assert p.version is VersionKeyword.LATEST
        assert p.version_code is None

    def test_is_owner_wildcard(self):
        p = parse_structure_params()
        assert p.is_owner_wildcard is True

    def test_is_id_wildcard(self):
        p = parse_structure_params()
        assert p.is_id_wildcard is True

    def test_wants_latest(self):
        p = parse_structure_params()
        assert p.wants_latest is True
        assert p.wants_all_versions is False
        assert p.wants_latest_stable is False


class TestWildcards:
    def test_explicit_wildcards(self):
        p = parse_structure_params(owner="*", id="*", version="*")
        assert p.is_owner_wildcard is True
        assert p.is_id_wildcard is True
        assert p.wants_all_versions is True

    def test_version_latest_stable(self):
        p = parse_structure_params(version="+")
        assert p.wants_latest_stable is True
        assert p.wants_latest is False


class TestCommaSeparated:
    def test_multiple_owners(self):
        p = parse_structure_params(owner="EBA,ECB")
        assert p.owners == ["EBA", "ECB"]
        assert p.is_owner_wildcard is False

    def test_multiple_ids(self):
        p = parse_structure_params(id="3.4,3.3")
        assert p.ids == ["3.4", "3.3"]
        assert p.is_id_wildcard is False
        assert p.is_single_id is False

    def test_single_id(self):
        p = parse_structure_params(id="3.4")
        assert p.is_single_id is True


class TestVersionCode:
    def test_literal_version(self):
        p = parse_structure_params(version="3.4")
        assert p.version is None
        assert p.version_code == "3.4"
        assert p.wants_latest is False
        assert p.wants_all_versions is False
