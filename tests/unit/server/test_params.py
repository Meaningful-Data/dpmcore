"""Unit tests for the SDMX URL parameter parser."""

from dpmcore.server.params import (
    ReleaseKeyword,
    StructureParams,
    parse_structure_params,
)


class TestParseDefaults:
    def test_all_defaults(self):
        p = parse_structure_params()
        assert p.owners == ["*"]
        assert p.ids == ["*"]
        assert p.release is ReleaseKeyword.LATEST
        assert p.release_code is None

    def test_is_owner_wildcard(self):
        p = parse_structure_params()
        assert p.is_owner_wildcard is True

    def test_is_id_wildcard(self):
        p = parse_structure_params()
        assert p.is_id_wildcard is True

    def test_wants_latest(self):
        p = parse_structure_params()
        assert p.wants_latest is True
        assert p.wants_all_releases is False
        assert p.wants_latest_stable is False


class TestWildcards:
    def test_explicit_wildcards(self):
        p = parse_structure_params(
            owner="*",
            id="*",
            release="*",
        )
        assert p.is_owner_wildcard is True
        assert p.is_id_wildcard is True
        assert p.wants_all_releases is True

    def test_release_latest_stable(self):
        p = parse_structure_params(release="+")
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


class TestReleaseCode:
    def test_literal_release(self):
        p = parse_structure_params(release="3.4")
        assert p.release is None
        assert p.release_code == "3.4"
        assert p.wants_latest is False
        assert p.wants_all_releases is False
