import unittest

from py_dpm.dpm.data import (
    get_module_schema_ref,
    get_module_schema_ref_by_version,
)


class TestModuleSchemaMapping(unittest.TestCase):
    """Test cases for the module schema mapping lookup."""

    def test_lookup_with_date_returns_correct_url(self):
        """Test that looking up with a date returns the correct URL."""
        # COREP_Con on 2014-01-15 should match the 2013-12-01 version (2.0.1)
        url = get_module_schema_ref("COREP_Con", "2014-01-15")
        assert url == "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/its-2013-02/2013-12-01/mod/corep_con.json"

    def test_lookup_different_date_returns_different_url(self):
        """Test that different dates return different URLs for same module."""
        # COREP_Con on 2014-10-15 should match the 2014-03-31 version (2.0.2)
        url = get_module_schema_ref("COREP_Con", "2014-10-15")
        assert url == "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/its-2013-02/2014-03-31/mod/corep_con.json"

    def test_lookup_case_insensitive(self):
        """Test that module code lookup is case insensitive."""
        url_upper = get_module_schema_ref("COREP_CON", "2014-01-15")
        url_lower = get_module_schema_ref("corep_con", "2014-01-15")
        url_mixed = get_module_schema_ref("Corep_Con", "2014-01-15")

        assert url_upper == url_lower
        assert url_lower == url_mixed

    def test_lookup_without_date_returns_latest(self):
        """Test that lookup without date returns the latest version."""
        url = get_module_schema_ref("COREP_Con")
        assert url is not None
        # Should be a valid URL
        assert url.startswith("http://www.eba.europa.eu/")

    def test_lookup_nonexistent_module_returns_none(self):
        """Test that looking up a non-existent module returns None."""
        url = get_module_schema_ref("NONEXISTENT_MODULE", "2014-01-15")
        assert url is None

    def test_lookup_with_invalid_date_returns_none(self):
        """Test that invalid date format returns None."""
        url = get_module_schema_ref("COREP_Con", "invalid-date")
        assert url is None

    def test_lookup_finrep_module(self):
        """Test lookup for FINREP module."""
        url = get_module_schema_ref("FINREP_Con_IFRS", "2014-01-15")
        assert url == "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/finrep/its-2013-02/2013-12-01/mod/finrep_con_ifrs.json"

    def test_url_ends_with_xsd(self):
        """Test that older module URLs end with .json extension."""
        url = get_module_schema_ref("COREP_Con", "2014-01-15")
        assert url.endswith(".json")


class TestModuleSchemaMappingByVersion(unittest.TestCase):
    """Test cases for the version-based module schema mapping lookup."""

    def test_lookup_by_version_returns_correct_url(self):
        """Test that looking up by version returns the correct URL."""
        url = get_module_schema_ref_by_version("AE", "1.2.0")
        assert url == "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/ae/its-005-2020/2022-03-01/mod/ae.json"

    def test_lookup_by_version_case_insensitive(self):
        """Test that module code lookup is case insensitive."""
        url_upper = get_module_schema_ref_by_version("AE", "1.2.0")
        url_lower = get_module_schema_ref_by_version("ae", "1.2.0")
        assert url_upper == url_lower

    def test_lookup_by_version_nonexistent_module_returns_none(self):
        """Test that a non-existent module returns None."""
        url = get_module_schema_ref_by_version("NONEXISTENT", "1.0.0")
        assert url is None

    def test_lookup_by_version_nonexistent_version_returns_none(self):
        """Test that a non-existent version returns None."""
        url = get_module_schema_ref_by_version("AE", "99.99.99")
        assert url is None

    def test_lookup_by_version_corep(self):
        """Test lookup for COREP module by version."""
        url = get_module_schema_ref_by_version("COREP_Con", "2.0.1")
        assert url == "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/its-2013-02/2013-12-01/mod/corep_con.json"


if __name__ == "__main__":
    unittest.main()
