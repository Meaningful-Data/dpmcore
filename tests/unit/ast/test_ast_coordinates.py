"""Unit tests for AST coordinate assignment functionality.

Tests the _add_coordinates_to_ast and _clean_ast_data_entries methods
in ASTGeneratorAPI to prevent regressions in x/y/z coordinate assignment.

Rules:
- x is added when rows vary (len(rows) > 1), with "row" field kept
- y is added when columns vary (len(cols) > 1), with "column" field kept
- z is added when sheets vary (len(sheets) > 1), with "sheet" field kept
- When a dimension is fixed (single value), no coordinate is added and the field is removed
- Base fields (datapoint, operand_reference_id) are always kept
- Internal fields (data_type, cell_code, table_code, table_vid) are always removed
"""

import copy

import pytest
from py_dpm.api.dpm_xl.ast_generator import ASTGeneratorAPI


class TestAddCoordinatesToAst:
    """Tests for _add_coordinates_to_ast method."""

    @pytest.fixture
    def api(self):
        """Create ASTGeneratorAPI instance without database."""
        return ASTGeneratorAPI(enable_semantic_validation=False)

    # ========== SINGLE DIMENSION VARIATION TESTS ==========

    def test_multiple_rows_adds_x_coordinate(self, api):
        """When rows vary, x coordinate should be added with correct 1-indexed values."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0020",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0010",
                    "column": "0010",
                },
            ],
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        # Rows sorted: ["0010", "0020"] -> 0010=x:1, 0020=x:2
        assert result["data"][0]["x"] == 2  # row 0020
        assert result["data"][1]["x"] == 1  # row 0010

    def test_multiple_columns_adds_y_coordinate(self, api):
        """When columns vary, y coordinate should be added with correct 1-indexed values."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0020",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0010",
                    "column": "0010",
                },
            ],
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        # Columns sorted: ["0010", "0020"] -> 0010=y:1, 0020=y:2
        assert result["data"][0]["y"] == 2  # column 0020
        assert result["data"][1]["y"] == 1  # column 0010

    def test_multiple_sheets_adds_z_coordinate(self, api):
        """When sheets vary, z coordinate should be added with correct 1-indexed values."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                    "sheet": "0020",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0010",
                    "column": "0010",
                    "sheet": "0010",
                },
            ],
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        # Sheets sorted: ["0010", "0020"] -> 0010=z:1, 0020=z:2
        assert result["data"][0]["z"] == 2  # sheet 0020
        assert result["data"][1]["z"] == 1  # sheet 0010

    # ========== SINGLE VALUE (NO VARIATION) TESTS ==========

    def test_single_row_no_x_coordinate(self, api):
        """When only one row exists, no x coordinate should be added."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0010",
                    "column": "0020",
                },
            ],
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        assert "x" not in result["data"][0]
        assert "x" not in result["data"][1]

    def test_single_column_no_y_coordinate(self, api):
        """When only one column exists, no y coordinate should be added."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0020",
                    "column": "0010",
                },
            ],
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        assert "y" not in result["data"][0]
        assert "y" not in result["data"][1]

    def test_single_sheet_no_z_coordinate(self, api):
        """When only one sheet exists, no z coordinate should be added."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                    "sheet": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0020",
                    "column": "0010",
                    "sheet": "0010",
                },
            ],
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        assert "z" not in result["data"][0]
        assert "z" not in result["data"][1]

    # ========== MIXED DIMENSION TESTS ==========

    def test_multiple_rows_single_column(self, api):
        """Multiple rows with single column: x added, no y."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0020",
                    "column": "0010",
                },
                {
                    "datapoint": 3,
                    "operand_reference_id": 102,
                    "row": "0030",
                    "column": "0010",
                },
            ],
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        # x should be present (multiple rows)
        assert result["data"][0]["x"] == 1
        assert result["data"][1]["x"] == 2
        assert result["data"][2]["x"] == 3
        # y should NOT be present (single column)
        assert "y" not in result["data"][0]
        assert "y" not in result["data"][1]
        assert "y" not in result["data"][2]

    def test_single_row_multiple_columns(self, api):
        """Single row with multiple columns: no x, y added."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0010",
                    "column": "0020",
                },
                {
                    "datapoint": 3,
                    "operand_reference_id": 102,
                    "row": "0010",
                    "column": "0030",
                },
            ],
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        # x should NOT be present (single row)
        assert "x" not in result["data"][0]
        assert "x" not in result["data"][1]
        assert "x" not in result["data"][2]
        # y should be present (multiple columns)
        assert result["data"][0]["y"] == 1
        assert result["data"][1]["y"] == 2
        assert result["data"][2]["y"] == 3

    def test_multiple_rows_multiple_columns(self, api):
        """Multiple rows and columns: both x and y added."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0010",
                    "column": "0020",
                },
                {
                    "datapoint": 3,
                    "operand_reference_id": 102,
                    "row": "0020",
                    "column": "0010",
                },
                {
                    "datapoint": 4,
                    "operand_reference_id": 103,
                    "row": "0020",
                    "column": "0020",
                },
            ],
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        # Both x and y should be present
        assert result["data"][0]["x"] == 1
        assert result["data"][0]["y"] == 1
        assert result["data"][1]["x"] == 1
        assert result["data"][1]["y"] == 2
        assert result["data"][2]["x"] == 2
        assert result["data"][2]["y"] == 1
        assert result["data"][3]["x"] == 2
        assert result["data"][3]["y"] == 2

    # ========== CONTEXT OVERRIDE TESTS ==========

    def test_context_rows_override_data_rows(self, api):
        """Context-provided rows should override rows extracted from data."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0020",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0030",
                    "column": "0010",
                },
            ],
        }
        # Context has different order than sorted data would give
        context = {"rows": ["0030", "0020", "0010"]}

        result = api._add_coordinates_to_ast(ast, context=context)

        # Using context order: 0030=x:1, 0020=x:2, 0010=x:3
        assert result["data"][0]["x"] == 2  # row 0020 is at index 1 in context
        assert result["data"][1]["x"] == 1  # row 0030 is at index 0 in context

    def test_context_none_uses_data_values(self, api):
        """None context should use data-extracted values."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0020",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0010",
                    "column": "0010",
                },
            ],
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        # Data-extracted rows sorted: ["0010", "0020"]
        assert result["data"][0]["x"] == 2  # row 0020
        assert result["data"][1]["x"] == 1  # row 0010

    def test_wildcard_cols_uses_data_values(self, api):
        """Context with wildcard columns should use data-extracted column values.

        This is a regression test for issue #75: when context contains c* (wildcard),
        the y coordinates should be calculated from the actual column codes in data.
        """
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0010",
                    "column": "0020",
                },
                {
                    "datapoint": 3,
                    "operand_reference_id": 102,
                    "row": "0010",
                    "column": "0030",
                },
            ],
        }
        # Context with wildcard - should fall back to data-extracted values
        context = {"cols": ["*"]}

        result = api._add_coordinates_to_ast(ast, context=context)

        # y should be calculated from data columns sorted: ["0010", "0020", "0030"]
        assert result["data"][0]["y"] == 1  # column 0010
        assert result["data"][1]["y"] == 2  # column 0020
        assert result["data"][2]["y"] == 3  # column 0030

    def test_wildcard_rows_uses_data_values(self, api):
        """Context with wildcard rows should use data-extracted row values.

        Similar to test_wildcard_cols_uses_data_values but for row wildcards.
        """
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0020",
                    "column": "0010",
                },
                {
                    "datapoint": 3,
                    "operand_reference_id": 102,
                    "row": "0030",
                    "column": "0010",
                },
            ],
        }
        # Context with wildcard - should fall back to data-extracted values
        context = {"rows": ["*"]}

        result = api._add_coordinates_to_ast(ast, context=context)

        # x should be calculated from data rows sorted: ["0010", "0020", "0030"]
        assert result["data"][0]["x"] == 1  # row 0010
        assert result["data"][1]["x"] == 2  # row 0020
        assert result["data"][2]["x"] == 3  # row 0030

    # ========== EDGE CASES ==========

    def test_empty_data_array(self, api):
        """Empty data array should not cause errors."""
        ast = {"class_name": "VarID", "data": []}

        result = api._add_coordinates_to_ast(ast, context=None)

        assert result["data"] == []

    def test_missing_row_field_in_entry(self, api):
        """Data entries without row field should be handled gracefully."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "column": "0020",
                },
            ],
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        # No x coordinate since no rows
        assert "x" not in result["data"][0]
        assert "x" not in result["data"][1]
        # y should be present (multiple columns)
        assert result["data"][0]["y"] == 1
        assert result["data"][1]["y"] == 2

    # ========== NESTED AST STRUCTURE TESTS ==========

    def test_nested_varid_nodes_processed(self, api):
        """VarID nodes nested in complex AST structures should be processed."""
        ast = {
            "class_name": "BinOp",
            "op": ">",
            "left": {
                "class_name": "VarID",
                "data": [
                    {
                        "datapoint": 1,
                        "operand_reference_id": 100,
                        "row": "0010",
                        "column": "0010",
                    },
                    {
                        "datapoint": 2,
                        "operand_reference_id": 101,
                        "row": "0020",
                        "column": "0010",
                    },
                ],
            },
            "right": {"class_name": "Constant", "value": 0},
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        # Nested VarID should have x coordinates
        assert result["left"]["data"][0]["x"] == 1
        assert result["left"]["data"][1]["x"] == 2

    def test_multiple_varid_nodes_each_processed(self, api):
        """Multiple VarID nodes at different levels should each be processed."""
        ast = {
            "class_name": "BinOp",
            "op": "and",
            "left": {
                "class_name": "VarID",
                "data": [
                    {
                        "datapoint": 1,
                        "operand_reference_id": 100,
                        "row": "0010",
                        "column": "0010",
                    },
                    {
                        "datapoint": 2,
                        "operand_reference_id": 101,
                        "row": "0020",
                        "column": "0010",
                    },
                ],
            },
            "right": {
                "class_name": "VarID",
                "data": [
                    {
                        "datapoint": 3,
                        "operand_reference_id": 102,
                        "row": "0010",
                        "column": "0010",
                    },
                    {
                        "datapoint": 4,
                        "operand_reference_id": 103,
                        "row": "0010",
                        "column": "0020",
                    },
                ],
            },
        }

        result = api._add_coordinates_to_ast(ast, context=None)

        # Left VarID: multiple rows, single column -> x only
        assert result["left"]["data"][0]["x"] == 1
        assert result["left"]["data"][1]["x"] == 2
        assert "y" not in result["left"]["data"][0]

        # Right VarID: single row, multiple columns -> y only
        assert "x" not in result["right"]["data"][0]
        assert result["right"]["data"][0]["y"] == 1
        assert result["right"]["data"][1]["y"] == 2

    # ========== IMMUTABILITY TEST ==========

    def test_original_ast_not_modified(self, api):
        """Original AST dictionary should not be modified (deep copy)."""
        original_ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0020",
                    "column": "0010",
                },
            ],
        }
        original_copy = copy.deepcopy(original_ast)

        api._add_coordinates_to_ast(original_ast, context=None)

        assert original_ast == original_copy


class TestCleanAstDataEntries:
    """Tests for _clean_ast_data_entries method."""

    @pytest.fixture
    def api(self):
        """Create ASTGeneratorAPI instance without database."""
        return ASTGeneratorAPI(enable_semantic_validation=False)

    # ========== BASE FIELDS RETENTION ==========

    def test_datapoint_always_kept(self, api):
        """Datapoint field should always be kept."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 123,
                    "operand_reference_id": 456,
                    "data_type": "m",
                },
            ],
        }

        result = api._clean_ast_data_entries(ast)

        assert result["data"][0]["datapoint"] == 123

    def test_operand_reference_id_always_kept(self, api):
        """operand_reference_id field should always be kept."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 123,
                    "operand_reference_id": 456,
                    "data_type": "m",
                },
            ],
        }

        result = api._clean_ast_data_entries(ast)

        assert result["data"][0]["operand_reference_id"] == 456

    # ========== COORDINATE-DEPENDENT FIELD RETENTION ==========

    def test_x_present_keeps_x_and_row(self, api):
        """When x coordinate exists, both x and row should be kept."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 123,
                    "operand_reference_id": 456,
                    "x": 1,
                    "row": "0010",
                },
            ],
        }

        result = api._clean_ast_data_entries(ast)

        assert result["data"][0]["x"] == 1
        assert result["data"][0]["row"] == "0010"

    def test_y_present_keeps_y_and_column(self, api):
        """When y coordinate exists, both y and column should be kept."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 123,
                    "operand_reference_id": 456,
                    "y": 1,
                    "column": "0010",
                },
            ],
        }

        result = api._clean_ast_data_entries(ast)

        assert result["data"][0]["y"] == 1
        assert result["data"][0]["column"] == "0010"

    def test_z_present_keeps_z_and_sheet(self, api):
        """When z coordinate exists, both z and sheet should be kept."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 123,
                    "operand_reference_id": 456,
                    "z": 1,
                    "sheet": "0010",
                },
            ],
        }

        result = api._clean_ast_data_entries(ast)

        assert result["data"][0]["z"] == 1
        assert result["data"][0]["sheet"] == "0010"

    def test_no_x_removes_row(self, api):
        """When no x coordinate, row field should be removed."""
        ast = {
            "class_name": "VarID",
            "data": [
                {"datapoint": 123, "operand_reference_id": 456, "row": "0010"},
            ],
        }

        result = api._clean_ast_data_entries(ast)

        assert "row" not in result["data"][0]

    def test_no_y_removes_column(self, api):
        """When no y coordinate, column field should be removed."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 123,
                    "operand_reference_id": 456,
                    "column": "0010",
                },
            ],
        }

        result = api._clean_ast_data_entries(ast)

        assert "column" not in result["data"][0]

    def test_no_z_removes_sheet(self, api):
        """When no z coordinate, sheet field should be removed."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 123,
                    "operand_reference_id": 456,
                    "sheet": "0010",
                },
            ],
        }

        result = api._clean_ast_data_entries(ast)

        assert "sheet" not in result["data"][0]

    # ========== INTERNAL/DEBUG FIELD REMOVAL ==========

    def test_internal_fields_removed(self, api):
        """Internal fields (data_type, cell_code, table_code, table_vid) should be removed."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 123,
                    "operand_reference_id": 456,
                    "data_type": "m",
                    "cell_code": "{F_01.01, r0010, c0010}",
                    "table_code": "F_01.01",
                    "table_vid": 1234,
                },
            ],
        }

        result = api._clean_ast_data_entries(ast)

        assert "data_type" not in result["data"][0]
        assert "cell_code" not in result["data"][0]
        assert "table_code" not in result["data"][0]
        assert "table_vid" not in result["data"][0]

    # ========== COMBINATION TESTS ==========

    def test_x_and_y_present_keeps_both(self, api):
        """When both x and y exist, keep x, row, y, column."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 123,
                    "operand_reference_id": 456,
                    "x": 1,
                    "row": "0010",
                    "y": 2,
                    "column": "0020",
                },
            ],
        }

        result = api._clean_ast_data_entries(ast)

        assert result["data"][0]["x"] == 1
        assert result["data"][0]["row"] == "0010"
        assert result["data"][0]["y"] == 2
        assert result["data"][0]["column"] == "0020"

    def test_no_coordinates_keeps_only_base_fields(self, api):
        """When no coordinates, only datapoint and operand_reference_id kept."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 123,
                    "operand_reference_id": 456,
                    "row": "0010",
                    "column": "0020",
                    "sheet": "0030",
                    "data_type": "m",
                },
            ],
        }

        result = api._clean_ast_data_entries(ast)

        assert set(result["data"][0].keys()) == {
            "datapoint",
            "operand_reference_id",
        }

    # ========== NESTED STRUCTURE TESTS ==========

    def test_nested_varid_nodes_cleaned(self, api):
        """VarID nodes nested in complex structures should be cleaned."""
        ast = {
            "class_name": "BinOp",
            "left": {
                "class_name": "VarID",
                "data": [
                    {
                        "datapoint": 123,
                        "operand_reference_id": 456,
                        "x": 1,
                        "row": "0010",
                        "data_type": "m",
                    },
                ],
            },
        }

        result = api._clean_ast_data_entries(ast)

        assert "data_type" not in result["left"]["data"][0]
        assert result["left"]["data"][0]["x"] == 1
        assert result["left"]["data"][0]["row"] == "0010"


class TestCoordinateAndCleanIntegration:
    """Integration tests for _add_coordinates_to_ast followed by _clean_ast_data_entries."""

    @pytest.fixture
    def api(self):
        """Create ASTGeneratorAPI instance without database."""
        return ASTGeneratorAPI(enable_semantic_validation=False)

    def test_multiple_rows_pipeline_keeps_x_and_row(self, api):
        """Full pipeline: multiple rows -> x added -> cleaning keeps x and row.

        THIS IS THE EXACT REGRESSION CASE that was fixed.
        """
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                    "data_type": "m",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0020",
                    "column": "0010",
                    "data_type": "m",
                },
            ],
        }

        with_coords = api._add_coordinates_to_ast(ast, context=None)
        result = api._clean_ast_data_entries(with_coords)

        for entry in result["data"]:
            # x and row should be present (multiple rows)
            assert "x" in entry, "x should be present when rows vary"
            assert "row" in entry, "row should be kept when x is present"
            # y and column should NOT be present (single column)
            assert "y" not in entry, (
                "y should NOT be present when column is fixed"
            )
            assert "column" not in entry, "column should NOT be kept when no y"
            # Base fields always present
            assert "datapoint" in entry
            assert "operand_reference_id" in entry
            # Internal fields removed
            assert "data_type" not in entry

    def test_single_row_pipeline_removes_row(self, api):
        """Full pipeline: single row -> no x -> cleaning removes row."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                    "data_type": "m",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0010",
                    "column": "0020",
                    "data_type": "m",
                },
            ],
        }

        with_coords = api._add_coordinates_to_ast(ast, context=None)
        result = api._clean_ast_data_entries(with_coords)

        for entry in result["data"]:
            # x and row should NOT be present (single row)
            assert "x" not in entry
            assert "row" not in entry
            # y and column should be present (multiple columns)
            assert "y" in entry
            assert "column" in entry

    def test_multiple_columns_pipeline_keeps_y_and_column(self, api):
        """Full pipeline: multiple columns -> y added -> cleaning keeps y and column."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0010",
                    "column": "0020",
                },
                {
                    "datapoint": 3,
                    "operand_reference_id": 102,
                    "row": "0010",
                    "column": "0030",
                },
            ],
        }

        with_coords = api._add_coordinates_to_ast(ast, context=None)
        result = api._clean_ast_data_entries(with_coords)

        for entry in result["data"]:
            assert "y" in entry, "y should be present when columns vary"
            assert "column" in entry, "column should be kept when y is present"
            assert "x" not in entry, (
                "x should NOT be present when row is fixed"
            )
            assert "row" not in entry, "row should NOT be kept when no x"

    def test_single_column_pipeline_removes_column(self, api):
        """Full pipeline: single column -> no y -> cleaning removes column."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0020",
                    "column": "0010",
                },
            ],
        }

        with_coords = api._add_coordinates_to_ast(ast, context=None)
        result = api._clean_ast_data_entries(with_coords)

        for entry in result["data"]:
            assert "y" not in entry
            assert "column" not in entry
            assert "x" in entry
            assert "row" in entry

    def test_full_pipeline_all_dimensions_vary(self, api):
        """Full pipeline with all dimensions varying."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                    "sheet": "0010",
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0020",
                    "column": "0020",
                    "sheet": "0020",
                },
            ],
        }

        with_coords = api._add_coordinates_to_ast(ast, context=None)
        result = api._clean_ast_data_entries(with_coords)

        for entry in result["data"]:
            # All coordinates and dimension fields should be present
            assert "x" in entry
            assert "row" in entry
            assert "y" in entry
            assert "column" in entry
            assert "z" in entry
            assert "sheet" in entry

    def test_full_pipeline_no_dimensions_vary(self, api):
        """Full pipeline with no dimensions varying (single values for all)."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                    "sheet": "0010",
                    "data_type": "m",
                },
            ],
        }

        with_coords = api._add_coordinates_to_ast(ast, context=None)
        result = api._clean_ast_data_entries(with_coords)

        entry = result["data"][0]
        # Only base fields should remain
        assert set(entry.keys()) == {"datapoint", "operand_reference_id"}

    def test_full_pipeline_removes_internal_fields(self, api):
        """Full pipeline removes internal fields like data_type, cell_code."""
        ast = {
            "class_name": "VarID",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 100,
                    "row": "0010",
                    "column": "0010",
                    "data_type": "monetary",
                    "cell_code": "{F_01.01, r0010, c0010}",
                    "table_code": "F_01.01",
                    "table_vid": 1234,
                },
                {
                    "datapoint": 2,
                    "operand_reference_id": 101,
                    "row": "0020",
                    "column": "0010",
                    "data_type": "monetary",
                    "cell_code": "{F_01.01, r0020, c0010}",
                    "table_code": "F_01.01",
                    "table_vid": 1234,
                },
            ],
        }

        with_coords = api._add_coordinates_to_ast(ast, context=None)
        result = api._clean_ast_data_entries(with_coords)

        for entry in result["data"]:
            assert "data_type" not in entry
            assert "cell_code" not in entry
            assert "table_code" not in entry
            assert "table_vid" not in entry
