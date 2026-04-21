import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from py_dpm.api.dpm.instance import InstanceAPI


class TestInstanceAPI(unittest.TestCase):
    """Test cases for the InstanceAPI class."""

    def setUp(self):
        """Set up test fixtures."""
        self.api = InstanceAPI()
        self.temp_dir = tempfile.mkdtemp()
        self.output_folder = Path(self.temp_dir)

        # Sample instance data for testing
        self.sample_instance_data = {
            "module_code": "F_01.01",
            "parameters": {
                "refPeriod": "2024-12-31",
                "entityID": "rs:TESTLEI123456789012.CON",
            },
            "facts": [
                {
                    "table_code": "t001",
                    "row_code": "r010",
                    "column_code": "c010",
                    "value": 1000000,
                }
            ],
        }

    @patch("py_dpm.instance.instance.Instance.from_dict")
    def test_build_package_from_dict(self, mock_from_dict):
        """Test building a package from a dictionary."""
        # Setup mock
        mock_instance = MagicMock()
        expected_path = self.output_folder / "test_package.zip"
        mock_instance.build_package.return_value = expected_path
        mock_from_dict.return_value = mock_instance

        # Call the method
        result = self.api.build_package_from_dict(
            self.sample_instance_data, self.output_folder, file_prefix="test"
        )

        # Assertions
        mock_from_dict.assert_called_once_with(self.sample_instance_data)
        mock_instance.build_package.assert_called_once_with(
            output_folder=self.output_folder, file_prefix="test"
        )
        self.assertEqual(result, expected_path)

    @patch("py_dpm.instance.instance.Instance.from_dict")
    def test_build_package_from_dict_without_prefix(self, mock_from_dict):
        """Test building a package from a dictionary without file prefix."""
        # Setup mock
        mock_instance = MagicMock()
        expected_path = self.output_folder / "package.zip"
        mock_instance.build_package.return_value = expected_path
        mock_from_dict.return_value = mock_instance

        # Call the method
        result = self.api.build_package_from_dict(
            self.sample_instance_data, self.output_folder
        )

        # Assertions
        mock_from_dict.assert_called_once_with(self.sample_instance_data)
        mock_instance.build_package.assert_called_once_with(
            output_folder=self.output_folder, file_prefix=None
        )
        self.assertEqual(result, expected_path)

    @patch("py_dpm.instance.instance.Instance.from_json_file")
    def test_build_package_from_json(self, mock_from_json):
        """Test building a package from a JSON file."""
        # Create a temporary JSON file
        json_file = self.output_folder / "test_instance.json"
        with open(json_file, "w") as f:
            json.dump(self.sample_instance_data, f)

        # Setup mock
        mock_instance = MagicMock()
        expected_path = self.output_folder / "test_package.zip"
        mock_instance.build_package.return_value = expected_path
        mock_from_json.return_value = mock_instance

        # Call the method
        result = self.api.build_package_from_json(
            json_file, self.output_folder, file_prefix="test"
        )

        # Assertions
        mock_from_json.assert_called_once_with(json_file)
        mock_instance.build_package.assert_called_once_with(
            output_folder=self.output_folder, file_prefix="test"
        )
        self.assertEqual(result, expected_path)

    @patch("py_dpm.instance.instance.Instance.from_json_file")
    def test_build_package_from_json_with_string_path(self, mock_from_json):
        """Test building a package from a JSON file using string path."""
        # Create a temporary JSON file
        json_file = self.output_folder / "test_instance.json"
        with open(json_file, "w") as f:
            json.dump(self.sample_instance_data, f)

        # Setup mock
        mock_instance = MagicMock()
        expected_path = self.output_folder / "test_package.zip"
        mock_instance.build_package.return_value = expected_path
        mock_from_json.return_value = mock_instance

        # Call the method with string path
        result = self.api.build_package_from_json(
            str(json_file), str(self.output_folder)
        )

        # Assertions
        mock_from_json.assert_called_once_with(json_file)
        mock_instance.build_package.assert_called_once()
        self.assertEqual(result, expected_path)

    def test_build_package_from_json_file_not_found(self):
        """Test that FileNotFoundError is raised for non-existent JSON file."""
        non_existent_file = self.output_folder / "non_existent.json"

        with self.assertRaises(FileNotFoundError) as context:
            self.api.build_package_from_json(
                non_existent_file, self.output_folder
            )

        self.assertIn("JSON file not found", str(context.exception))


if __name__ == "__main__":
    unittest.main()
