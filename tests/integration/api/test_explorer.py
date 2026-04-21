import unittest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from py_dpm.api.dpm.explorer import ExplorerQueryAPI
from py_dpm.dpm.models import Base, Framework, Module, ModuleVersion, Release
from py_dpm.dpm.queries.explorer_queries import ExplorerQuery


# Mock models to avoid importing actual DB models which require DB connection


@dataclass
class MockProperty:
    code: str


class TestDPMExplorer(unittest.TestCase):
    def setUp(self):
        self.mock_api = MagicMock()
        self.mock_session = MagicMock()
        self.mock_api.session = self.mock_session
        self.explorer = ExplorerQueryAPI(data_dict_api=self.mock_api)

    @patch("sqlalchemy.or_")
    @patch("py_dpm.dpm.models.TableVersion")
    def test_search_table(self, mock_table_version, mock_or):
        # Setup mock return values

        # Setup column mocks to behave like SQLAlchemy columns for comparison
        mock_col = MagicMock()
        mock_col.__gt__.return_value = MagicMock()
        mock_col.__le__.return_value = MagicMock()
        mock_col.is_.return_value = MagicMock()
        mock_col.like.return_value = MagicMock()

        mock_table_version.endreleaseid = mock_col
        mock_table_version.startreleaseid = mock_col
        mock_table_version.code = mock_col
        mock_table_version.name = mock_col

        # When or_ is called, return a mock expression
        mock_or.return_value = MagicMock()

        # Mock the query result items
        # We need the items returned by the query to have attributes matching what search_table expects
        row_mock = MagicMock()
        row_mock.tablevid = 1
        row_mock.code = "TABLE_A"
        row_mock.name = "Table A"
        row_mock.description = "Desc"

        # Mock the session.query chain
        mock_query = self.mock_session.query.return_value
        mock_query.filter.return_value.all.return_value = [row_mock]

        # With release_id filter
        mock_query.filter.return_value.filter.return_value.all.return_value = [
            row_mock
        ]

        # Test search
        results = self.explorer.search_table("TABLE", release_id=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], dict)
        self.assertEqual(results[0]["code"], "TABLE_A")

    @patch("sqlalchemy.orm.aliased")
    @patch("py_dpm.dpm.models.Category")
    @patch("py_dpm.dpm.models.PropertyCategory")
    @patch("py_dpm.dpm.models.ItemCategory")
    def test_get_properties_using_item(
        self, mock_ic, mock_pc, mock_cat, mock_aliased
    ):
        # Setup mock return values
        mock_result = MagicMock()
        mock_result.code = "PROP_CODE"

        # Setup aliased return values
        mock_aliased_ic = MagicMock()
        mock_aliased.return_value = mock_aliased_ic

        # Mock the session.query chain
        # The chain is: query(ic_parent.code).select_from().join().join().join().filter().distinct().all()
        mock_query = self.mock_session.query.return_value
        (
            mock_query.select_from.return_value.join.return_value.join.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value
        ) = [mock_result]

        results = self.explorer.get_properties_using_item("ITEM_CODE")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], "PROP_CODE")

    def test_audit_table(self):
        # Setup mock values for dependent API calls
        mock_table_info = {
            "table_vid": 1,
            "code": "TABLE_X",
            "name": "Table X",
            "description": "Desc",
        }
        self.mock_api.get_table_version.return_value = mock_table_info

        mock_open_keys = [
            {
                "table_version_code": "TABLE_X",
                "property_code": "P1",
                "data_type_name": "String",
            }
        ]
        self.mock_api.get_open_keys_for_table.return_value = mock_open_keys

        # Test audit
        audit = self.explorer.audit_table("TABLE_X", release_id=1)

        self.assertEqual(audit["info"], mock_table_info)
        self.assertEqual(audit["open_keys"], mock_open_keys)
        self.assertEqual(audit["open_keys_count"], 1)

    def test_audit_table_not_found(self):
        self.mock_api.get_table_version.return_value = None

        audit = self.explorer.audit_table("NON_EXISTENT")
        self.assertIn("error", audit)

    @patch(
        "py_dpm.dpm.queries.explorer_queries.ExplorerQuery.get_variable_usage"
    )
    def test_get_variable_usage_delegates_to_query(
        self, mock_get_variable_usage
    ):
        # Arrange
        expected_result = [
            {
                "cell_code": "A1",
                "cell_sign": "+",
                "table_code": "TBL_X",
                "table_name": "Table X",
                "module_code": "MOD_X",
                "module_name": "Module X",
            }
        ]
        mock_get_variable_usage.return_value = expected_result

        # Act
        result = self.explorer.get_variable_usage(
            variable_id=123, release_id=5, date=None, release_code=None
        )

        # Assert
        mock_get_variable_usage.assert_called_once_with(
            self.mock_api.session,
            variable_id=123,
            variable_vid=None,
            release_id=5,
            date=None,
            release_code=None,
        )
        self.assertEqual(result, expected_result)

    @patch("py_dpm.dpm.queries.explorer_queries.ExplorerQuery.get_module_url")
    def test_get_module_url_delegates_to_query(self, mock_get_module_url):
        # Arrange
        expected_url = "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/FRM/1.0/mod/MOD_aaaX.json"
        mock_get_module_url.return_value = expected_url

        # Act
        result = self.explorer.get_module_url(
            module_code="MOD_X", date=None, release_id=1, release_code=None
        )

        # Assert
        mock_get_module_url.assert_called_once_with(
            self.mock_api.session,
            module_code="MOD_X",
            date=None,
            release_id=1,
            release_code=None,
        )

        print(result)
        self.assertEqual(result, expected_url)

    @patch(
        "py_dpm.dpm.queries.explorer_queries.ExplorerQuery.get_variable_from_cell_address"
    )
    def test_get_variable_from_cell_address_delegates_to_query(
        self, mock_get_variable_from_cell_address
    ):
        # Arrange
        expected = [
            {
                "variable_id": 1,
                "variable_vid": 10,
                "table_code": "TBL_X",
                "cell_code": "A1",
                "row_code": "0010",
                "column_code": "0100",
                "sheet_code": "0001",
            }
        ]
        mock_get_variable_from_cell_address.return_value = expected

        # Act
        result = self.explorer.get_variable_from_cell_address(
            table_code="TBL_X",
            row_code="0010",
            column_code="0100",
            sheet_code="0001",
            release_id=1,
            release_code=None,
            date=None,
        )

        # Assert
        mock_get_variable_from_cell_address.assert_called_once_with(
            self.mock_api.session,
            table_code="TBL_X",
            row_code="0010",
            column_code="0100",
            sheet_code="0001",
            module_code=None,
            release_id=1,
            release_code=None,
            date=None,
        )
        self.assertEqual(result, expected)


class TestExplorerQueryModuleUrlIntegration(unittest.TestCase):
    def setUp(self):
        # Use an in-memory SQLite database for integration-style testing
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine)
        self.session = SessionLocal()

        # Minimal data setup: one Release, Framework, Module, and ModuleVersion
        release = Release(releaseid=1, code="2.0")
        framework = Framework(frameworkid=10, code="FRM")
        module = Module(moduleid=100, frameworkid=framework.frameworkid)
        module_version = ModuleVersion(
            modulevid=1000,
            moduleid=module.moduleid,
            code="MOD_X",
            startreleaseid=release.releaseid,
            endreleaseid=None,
        )

        self.session.add_all([release, framework, module, module_version])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_get_module_url_uses_lowercase_codes(self):
        url = ExplorerQuery.get_module_url(
            self.session,
            module_code="MOD_X",
            date=None,
            release_id=None,
            release_code=None,
        )

        expected_url = "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/frm/2.0/mod/mod_x.json"
        self.assertEqual(url, expected_url)

    def test_get_module_url_by_release_id_uses_static_mapping(self):
        """Test that querying by release_id returns the static mapping URL
        when the module version matches a known entry in the CSV."""
        # Add a release and module version that matches a static mapping entry.
        # AE version 1.2.0 is in the CSV with the correct ITS-based URL.
        release_34 = Release(releaseid=34, code="3.4")
        framework_ae = Framework(frameworkid=20, code="AE")
        module_ae = Module(moduleid=200, frameworkid=framework_ae.frameworkid)
        module_version_ae = ModuleVersion(
            modulevid=2000,
            moduleid=module_ae.moduleid,
            code="AE",
            versionnumber="1.2.0",
            startreleaseid=1,
            endreleaseid=None,
        )

        self.session.add_all(
            [release_34, framework_ae, module_ae, module_version_ae]
        )
        self.session.commit()

        url = ExplorerQuery.get_module_url(
            self.session,
            module_code="AE",
            release_id=34,
        )

        expected_url = (
            "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/ae/"
            "its-005-2020/2022-03-01/mod/ae.json"
        )
        self.assertEqual(url, expected_url)


class TestGetVariableByCode(unittest.TestCase):
    """Tests for get_variable_by_code and get_variables_by_codes methods."""

    def setUp(self):
        self.mock_api = MagicMock()
        self.mock_session = MagicMock()
        self.mock_api.session = self.mock_session
        self.explorer = ExplorerQueryAPI(data_dict_api=self.mock_api)

    @patch(
        "py_dpm.dpm.queries.explorer_queries.ExplorerQuery.get_variable_by_code"
    )
    def test_get_variable_by_code_delegates_to_query(
        self, mock_get_variable_by_code
    ):
        """Test that API method delegates to query layer correctly."""
        # Arrange
        expected_result = {
            "variable_id": 2201,
            "variable_vid": 2201,
            "variable_code": "C_01.00",
            "variable_name": "Filing indicator for C_01.00",
        }
        mock_get_variable_by_code.return_value = expected_result

        # Act
        result = self.explorer.get_variable_by_code(
            variable_code="C_01.00",
            release_id=3,
        )

        # Assert
        mock_get_variable_by_code.assert_called_once_with(
            self.mock_api.session,
            variable_code="C_01.00",
            release_id=3,
            release_code=None,
        )
        self.assertEqual(result, expected_result)

    @patch(
        "py_dpm.dpm.queries.explorer_queries.ExplorerQuery.get_variable_by_code"
    )
    def test_get_variable_by_code_with_release_code(
        self, mock_get_variable_by_code
    ):
        """Test get_variable_by_code with release_code parameter."""
        expected_result = {
            "variable_id": 1935,
            "variable_vid": 1935,
            "variable_code": "C_47.00",
            "variable_name": "Filing indicator for C_47.00",
        }
        mock_get_variable_by_code.return_value = expected_result

        result = self.explorer.get_variable_by_code(
            variable_code="C_47.00",
            release_code="4.2",
        )

        mock_get_variable_by_code.assert_called_once_with(
            self.mock_api.session,
            variable_code="C_47.00",
            release_id=None,
            release_code="4.2",
        )
        self.assertEqual(result, expected_result)

    @patch(
        "py_dpm.dpm.queries.explorer_queries.ExplorerQuery.get_variable_by_code"
    )
    def test_get_variable_by_code_not_found(self, mock_get_variable_by_code):
        """Test get_variable_by_code returns None when variable not found."""
        mock_get_variable_by_code.return_value = None

        result = self.explorer.get_variable_by_code(
            variable_code="NONEXISTENT"
        )

        self.assertIsNone(result)

    @patch(
        "py_dpm.dpm.queries.explorer_queries.ExplorerQuery.get_variables_by_codes"
    )
    def test_get_variables_by_codes_delegates_to_query(
        self, mock_get_variables_by_codes
    ):
        """Test that batch API method delegates to query layer correctly."""
        # Arrange
        expected_result = {
            "C_01.00": {
                "variable_id": 2201,
                "variable_vid": 2201,
                "variable_code": "C_01.00",
                "variable_name": "Filing indicator for C_01.00",
            },
            "C_47.00": {
                "variable_id": 1935,
                "variable_vid": 1935,
                "variable_code": "C_47.00",
                "variable_name": "Filing indicator for C_47.00",
            },
        }
        mock_get_variables_by_codes.return_value = expected_result

        # Act
        result = self.explorer.get_variables_by_codes(
            variable_codes=["C_01.00", "C_47.00"],
            release_id=3,
        )

        # Assert
        mock_get_variables_by_codes.assert_called_once_with(
            self.mock_api.session,
            variable_codes=["C_01.00", "C_47.00"],
            release_id=3,
            release_code=None,
        )
        self.assertEqual(result, expected_result)

    @patch(
        "py_dpm.dpm.queries.explorer_queries.ExplorerQuery.get_variables_by_codes"
    )
    def test_get_variables_by_codes_empty_list(
        self, mock_get_variables_by_codes
    ):
        """Test get_variables_by_codes with empty list returns empty dict."""
        mock_get_variables_by_codes.return_value = {}

        result = self.explorer.get_variables_by_codes(variable_codes=[])

        mock_get_variables_by_codes.assert_called_once_with(
            self.mock_api.session,
            variable_codes=[],
            release_id=None,
            release_code=None,
        )
        self.assertEqual(result, {})

    @patch(
        "py_dpm.dpm.queries.explorer_queries.ExplorerQuery.get_variables_by_codes"
    )
    def test_get_variables_by_codes_partial_match(
        self, mock_get_variables_by_codes
    ):
        """Test that only found variables are returned (missing codes excluded)."""
        # Only C_01.00 found, C_99.99 not in database
        expected_result = {
            "C_01.00": {
                "variable_id": 2201,
                "variable_vid": 2201,
                "variable_code": "C_01.00",
                "variable_name": "Filing indicator for C_01.00",
            },
        }
        mock_get_variables_by_codes.return_value = expected_result

        result = self.explorer.get_variables_by_codes(
            variable_codes=["C_01.00", "C_99.99"],
            release_code="4.2",
        )

        self.assertEqual(len(result), 1)
        self.assertIn("C_01.00", result)
        self.assertNotIn("C_99.99", result)


class TestExplorerQueryVariableByCodeIntegration(unittest.TestCase):
    """Integration tests for get_variable_by_code using in-memory SQLite."""

    def setUp(self):
        from py_dpm.dpm.models import VariableVersion

        # Use an in-memory SQLite database for integration-style testing
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine)
        self.session = SessionLocal()

        # Create test releases
        release_1 = Release(releaseid=1, code="4.1")
        release_2 = Release(releaseid=2, code="4.2")

        # Create test variable versions
        # Variable active in release 4.1 only (ended in 4.2)
        var_v1 = VariableVersion(
            variablevid=1001,
            variableid=1001,
            code="C_01.00",
            name="Filing indicator for C_01.00 (v4.1)",
            startreleaseid=1,
            endreleaseid=2,
        )
        # Variable active in release 4.2 (current)
        var_v2 = VariableVersion(
            variablevid=2001,
            variableid=2001,
            code="C_01.00",
            name="Filing indicator for C_01.00 (v4.2)",
            startreleaseid=2,
            endreleaseid=None,
        )
        # Another variable active in both releases
        var_v3 = VariableVersion(
            variablevid=3001,
            variableid=3001,
            code="C_47.00",
            name="Filing indicator for C_47.00",
            startreleaseid=1,
            endreleaseid=None,
        )

        self.session.add_all([release_1, release_2, var_v1, var_v2, var_v3])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_get_variable_by_code_active_only(self):
        """Test that default behavior returns active-only (endreleaseid is NULL)."""
        result = ExplorerQuery.get_variable_by_code(
            self.session,
            variable_code="C_01.00",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["variable_vid"], 2001)
        self.assertEqual(result["variable_code"], "C_01.00")
        self.assertIn("v4.2", result["variable_name"])

    def test_get_variable_by_code_with_release_id(self):
        """Test filtering by release_id returns correct version."""
        # Release 1 should return the v4.1 version
        result = ExplorerQuery.get_variable_by_code(
            self.session,
            variable_code="C_01.00",
            release_id=1,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["variable_vid"], 1001)
        self.assertIn("v4.1", result["variable_name"])

    def test_get_variable_by_code_with_release_code(self):
        """Test filtering by release_code returns correct version."""
        result = ExplorerQuery.get_variable_by_code(
            self.session,
            variable_code="C_01.00",
            release_code="4.2",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["variable_vid"], 2001)

    def test_get_variable_by_code_not_found(self):
        """Test returns None when variable code doesn't exist."""
        result = ExplorerQuery.get_variable_by_code(
            self.session,
            variable_code="NONEXISTENT",
        )

        self.assertIsNone(result)

    def test_get_variable_by_code_mutual_exclusion_error(self):
        """Test that providing both release_id and release_code raises error."""
        with self.assertRaises(ValueError) as ctx:
            ExplorerQuery.get_variable_by_code(
                self.session,
                variable_code="C_01.00",
                release_id=1,
                release_code="4.2",
            )

        self.assertIn("maximum of one", str(ctx.exception))

    def test_get_variables_by_codes_batch(self):
        """Test batch lookup returns multiple variables."""
        result = ExplorerQuery.get_variables_by_codes(
            self.session,
            variable_codes=["C_01.00", "C_47.00"],
        )

        self.assertEqual(len(result), 2)
        self.assertIn("C_01.00", result)
        self.assertIn("C_47.00", result)
        # Should return active versions (endreleaseid is NULL)
        self.assertEqual(result["C_01.00"]["variable_vid"], 2001)
        self.assertEqual(result["C_47.00"]["variable_vid"], 3001)

    def test_get_variables_by_codes_empty_list(self):
        """Test empty input returns empty dict without database query."""
        result = ExplorerQuery.get_variables_by_codes(
            self.session,
            variable_codes=[],
        )

        self.assertEqual(result, {})

    def test_get_variables_by_codes_partial_match(self):
        """Test that missing codes are simply not included in result."""
        result = ExplorerQuery.get_variables_by_codes(
            self.session,
            variable_codes=["C_01.00", "NONEXISTENT", "C_47.00"],
        )

        self.assertEqual(len(result), 2)
        self.assertIn("C_01.00", result)
        self.assertIn("C_47.00", result)
        self.assertNotIn("NONEXISTENT", result)

    def test_get_variables_by_codes_with_release_id(self):
        """Test batch lookup with release_id filter."""
        result = ExplorerQuery.get_variables_by_codes(
            self.session,
            variable_codes=["C_01.00", "C_47.00"],
            release_id=1,
        )

        self.assertEqual(len(result), 2)
        # Release 1 should return v4.1 version for C_01.00
        self.assertEqual(result["C_01.00"]["variable_vid"], 1001)
        # C_47.00 is active in both releases
        self.assertEqual(result["C_47.00"]["variable_vid"], 3001)

    def test_get_variables_by_codes_mutual_exclusion_error(self):
        """Test that providing both release_id and release_code raises error."""
        with self.assertRaises(ValueError) as ctx:
            ExplorerQuery.get_variables_by_codes(
                self.session,
                variable_codes=["C_01.00"],
                release_id=1,
                release_code="4.2",
            )

        self.assertIn("maximum of one", str(ctx.exception))
