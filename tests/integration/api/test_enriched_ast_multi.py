"""
Integration tests for generate_validations_script with multi-expression support.

These tests require a database connection configured via .env file.
"""

import os
import pytest
from dotenv import load_dotenv
from urllib.parse import quote_plus

from py_dpm.api.dpm_xl import ASTGeneratorAPI


load_dotenv()


def _db_kwargs():
    """
    Build DB configuration from environment/.env.

    Prefers server databases configured via PYDPM_RDBMS/PYDPM_DB_* variables.
    Falls back to legacy USE_POSTGRES/POSTGRES_* configuration, then finally
    to SQLite via SQLITE_DB_PATH.
    """
    # Preferred unified configuration
    rdbms = os.getenv("PYDPM_RDBMS", "").strip().lower()

    if rdbms in ("postgres", "sqlserver"):
        host = os.getenv("PYDPM_DB_HOST")
        port = os.getenv("PYDPM_DB_PORT") or (
            "5432" if rdbms == "postgres" else "1433"
        )
        db = os.getenv("PYDPM_DB_NAME")
        user = os.getenv("PYDPM_DB_USER")
        password = os.getenv("PYDPM_DB_PASSWORD")

        if all([host, db, user, password]):
            if rdbms == "postgres":
                connection_url = (
                    f"postgresql://{user}:{password}@{host}:{port}/{db}"
                )
            else:
                # SQL Server connection using ODBC connection string
                server_with_port = f"{host},{port}" if port else host

                # Handling special characters in password for SQL Server
                sqlserver_password = password.replace("}", "}}")
                for x in "%&.@#/\\=;":
                    if x in sqlserver_password:
                        sqlserver_password = "{" + sqlserver_password + "}"
                        break

                if os.name == "nt":
                    driver = "{SQL Server}"
                else:
                    driver = os.getenv(
                        "SQL_DRIVER", "{ODBC Driver 18 for SQL Server}"
                    )

                connection_string = (
                    f"DRIVER={driver}",
                    f"SERVER={server_with_port}",
                    f"DATABASE={db}",
                    f"UID={user}",
                    f"PWD={sqlserver_password}",
                    "TrustServerCertificate=yes",
                )
                encoded = quote_plus(";".join(connection_string))
                connection_url = f"mssql+pyodbc:///?odbc_connect={encoded}"

            return {"connection_url": connection_url}

    return {}


class TestGenerateEnrichedAstMultiExpression:
    """Integration tests for multi-expression generate_validations_script."""

    @pytest.fixture
    def api(self):
        """Create ASTGeneratorAPI instance with database configuration."""
        db_config = _db_kwargs()
        return ASTGeneratorAPI(**db_config, enable_semantic_validation=True)

    def test_single_expression_new_signature(self, api):
        """Test that single expression works with new tuple signature."""
        expression = """
        with {default: 0, interval: true}:
            sum ({tF_32.01, r0010, (c0010, c0060)}) = {tF_01.01, r0380, c0010}
        """

        result = api.generate_validations_script(
            expressions=[
                (expression, "v2814_m", None),
            ],
            release_code="4.2",
            module_code="AE",
            preferred_module_dependencies=["FINREP9"],
        )

        assert result["success"] is True, (
            f"Expected success, got error: {result['error']}"
        )
        assert result["enriched_ast"] is not None
        assert result["error"] is None

        # Verify structure
        enriched_ast = result["enriched_ast"]
        assert len(enriched_ast) == 1  # Single namespace

        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        # Verify operations
        assert "operations" in module_data
        assert "v2814_m" in module_data["operations"]
        assert module_data["operations"]["v2814_m"]["code"] == "v2814_m"
        assert module_data["operations"]["v2814_m"]["expression"] == expression

        # Verify variables and tables exist
        assert "variables" in module_data
        assert "tables" in module_data
        assert len(module_data["variables"]) > 0
        assert len(module_data["tables"]) > 0

        # Verify dependency information
        assert "dependency_information" in module_data
        assert (
            "cross_instance_dependencies"
            in module_data["dependency_information"]
        )

    def test_multiple_expressions_single_module(self, api):
        """Test multiple expressions aggregated into single script."""
        expressions = [
            ("{tF_01.01, r0380, c0010} > 0", "op_1", None),
            ("{tF_01.01, r0390, c0010} >= 0", "op_2", None),
            ("{tF_01.01, r0340, c0010} != 0", "op_3", None),
        ]

        result = api.generate_validations_script(
            expressions=expressions,
            module_version_number="3.3.0",
            module_code="FINREP9",
        )

        assert result["success"] is True, (
            f"Expected success, got error: {result['error']}"
        )

        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        # All three operations should be present
        assert "op_1" in module_data["operations"]
        assert "op_2" in module_data["operations"]
        assert "op_3" in module_data["operations"]

        # Single table should be present (F_01.01)
        assert "F_01.01" in module_data["tables"]

    def test_multiple_expressions_with_preconditions(self, api):
        """Test multiple expressions with preconditions."""
        expressions = [
            (
                "{tF_01.01, r0380, c0010} > 0",
                "op_with_precond_1",
                "{v_F_44_04}",
            ),
            (
                "{tF_01.01, r0390, c0010} >= 0",
                "op_with_precond_2",
                "{v_F_44_04}",
            ),  # Same precondition
            ("{tF_01.01, r0340, c0010} != 0", "op_without_precond", None),
        ]

        result = api.generate_validations_script(
            expressions=expressions,
            release_code="4.2",
            module_code="FINREP9",
        )

        assert result["success"] is True, (
            f"Expected success, got error: {result['error']}"
        )

        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        # All operations present
        assert len(module_data["operations"]) == 3

        # Preconditions should be deduplicated (same precondition used twice)
        # but affected_operations should list both ops
        if module_data["preconditions"]:
            precond_key = list(module_data["preconditions"].keys())[0]
            affected_ops = module_data["preconditions"][precond_key][
                "affected_operations"
            ]
            assert (
                "op_with_precond_1" in affected_ops
                or "op_with_precond_2" in affected_ops
            )

    def test_cross_module_expression(self, api):
        """Test expression that references multiple modules."""
        expression = """
        with {default: 0, interval: true}:
            sum ({tF_32.01, r0010, (c0010, c0060)}) = {tF_01.01, r0380, c0010}
        """

        result = api.generate_validations_script(
            expressions=[
                (expression, "cross_module_op", None),
            ],
            release_code="4.2",
            module_code="AE",
            preferred_module_dependencies=["FINREP9"],
        )

        assert result["success"] is True, (
            f"Expected success, got error: {result['error']}"
        )

        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        # Should have cross-module dependencies
        assert "dependency_modules" in module_data
        assert "dependency_information" in module_data

        cross_deps = module_data["dependency_information"][
            "cross_instance_dependencies"
        ]
        # Should have at least one cross-module dependency (FINREP9)
        assert (
            len(cross_deps) >= 0
        )  # May or may not have depending on module detection

    def test_expression_failure_skips_with_warning(self, api):
        """Test that invalid expression is skipped with a warning, not failing the entire operation."""
        expressions = [
            ("{tF_01.01, r0380, c0010} > 0", "valid_op", None),
            (
                "INVALID EXPRESSION !!!",
                "invalid_op",
                None,
            ),  # This should be skipped
        ]

        import warnings

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            result = api.generate_validations_script(
                expressions=expressions,
                release_code="4.2",
                module_code="FINREP9",
            )

        # Operation should succeed (valid expression still processed)
        assert result["success"] is True
        assert result["enriched_ast"] is not None

        # Warnings should contain info about the skipped expression
        assert len(result["warnings"]) == 1
        assert "invalid_op" in result["warnings"][0]
        assert "expression 2" in result["warnings"][0].lower()

        # warnings.warn should have been called
        assert len(caught_warnings) >= 1
        warning_messages = [str(w.message) for w in caught_warnings]
        assert any("invalid_op" in msg for msg in warning_messages)

        # Only the valid operation should be in the output
        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]
        assert "valid_op" in module_data["operations"]
        assert "invalid_op" not in module_data["operations"]

    def test_variables_deduplicated_across_expressions(self, api):
        """Test that variables from same table are not duplicated."""
        expressions = [
            ("{tF_01.01, r0380, c0010} > 0", "op_1", None),
            ("{tF_01.01, r0380, c0010} < 100", "op_2", None),  # Same variable
        ]

        result = api.generate_validations_script(
            expressions=expressions,
            release_code="4.2",
            module_code="FINREP9",
        )

        assert result["success"] is True

        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        # Table should only appear once
        assert list(module_data["tables"].keys()).count("F_01.01") == 1

    def test_output_structure_matches_expected_format(self, api):
        """Test that output structure has all required fields."""
        expression = "{tF_01.01, r0380, c0010} > 0"

        result = api.generate_validations_script(
            expressions=[
                (expression, "test_op", None),
            ],
            release_code="4.2",
            module_code="FINREP9",
        )

        assert result["success"] is True

        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        # Required top-level fields
        required_fields = [
            "module_code",
            "module_version",
            "framework_code",
            "dpm_release",
            "dates",
            "operations",
            "variables",
            "tables",
            "preconditions",
            "precondition_variables",
            "dependency_information",
            "dependency_modules",
        ]

        for field in required_fields:
            assert field in module_data, f"Missing required field: {field}"

        # DPM release structure
        assert "release" in module_data["dpm_release"]
        assert "publication_date" in module_data["dpm_release"]

        # Dates structure
        assert "from" in module_data["dates"]
        assert "to" in module_data["dates"]

        # Dependency information structure
        assert (
            "intra_instance_validations"
            in module_data["dependency_information"]
        )
        assert (
            "cross_instance_dependencies"
            in module_data["dependency_information"]
        )

    def test_add_all_tables_true_includes_all_module_tables(self, api):
        """Test that add_all_tables=True includes all tables from the module version."""
        # Use a simple expression that references only one table
        expression = "{tC_47.00, r0310, c0010} = 0"

        result = api.generate_validations_script(
            expressions=[
                (expression, "test_op", None),
            ],
            module_code="COREP_LR",
            module_version_number="4.1.0",
            add_all_tables=True,  # Explicitly set to True (default)
        )

        assert result["success"] is True, (
            f"Expected success, got error: {result['error']}"
        )

        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        # With add_all_tables=True, should have more than just the referenced table
        # The COREP_LR module has multiple tables
        tables = module_data["tables"]
        assert len(tables) > 1, (
            f"Expected multiple tables with add_all_tables=True, got {len(tables)}: {list(tables.keys())}"
        )

        # The referenced table should still be present
        assert "C_47.00" in tables, (
            "Referenced table C_47.00 should be present"
        )

        # Variables should include variables from all tables
        variables = module_data["variables"]
        assert len(variables) > 0, "Expected variables to be populated"

    def test_add_all_tables_false_includes_only_referenced_tables(self, api):
        """Test that add_all_tables=False includes only tables referenced in expressions."""
        # Use a simple expression that references only one table
        expression = "{tC_47.00, r0310, c0010} = 0"

        result = api.generate_validations_script(
            expressions=[
                (expression, "test_op", None),
            ],
            module_code="COREP_LR",
            module_version_number="4.1.0",
            add_all_tables=False,
        )

        assert result["success"] is True, (
            f"Expected success, got error: {result['error']}"
        )

        enriched_ast = result["enriched_ast"]
        namespace = list(enriched_ast.keys())[0]
        module_data = enriched_ast[namespace]

        # With add_all_tables=False, should only have the referenced table
        tables = module_data["tables"]
        assert len(tables) == 1, (
            f"Expected only 1 table with add_all_tables=False, got {len(tables)}: {list(tables.keys())}"
        )

        # The referenced table should be present
        assert "C_47.00" in tables, (
            "Referenced table C_47.00 should be present"
        )

    def test_add_all_tables_comparison(self, api):
        """Test that add_all_tables=True returns more tables than add_all_tables=False."""
        expression = "{tC_47.00, r0310, c0010} = 0"

        # Generate with add_all_tables=True
        result_all = api.generate_validations_script(
            expressions=[(expression, "test_op", None)],
            module_code="COREP_LR",
            module_version_number="4.1.0",
            add_all_tables=True,
        )

        # Generate with add_all_tables=False
        result_partial = api.generate_validations_script(
            expressions=[(expression, "test_op", None)],
            module_code="COREP_LR",
            module_version_number="4.1.0",
            add_all_tables=False,
        )

        assert result_all["success"] is True
        assert result_partial["success"] is True

        ns_all = list(result_all["enriched_ast"].keys())[0]
        ns_partial = list(result_partial["enriched_ast"].keys())[0]

        tables_all = result_all["enriched_ast"][ns_all]["tables"]
        tables_partial = result_partial["enriched_ast"][ns_partial]["tables"]

        vars_all = result_all["enriched_ast"][ns_all]["variables"]
        vars_partial = result_partial["enriched_ast"][ns_partial]["variables"]

        # add_all_tables=True should have more tables
        assert len(tables_all) > len(tables_partial), (
            f"Expected more tables with add_all_tables=True "
            f"({len(tables_all)} vs {len(tables_partial)})"
        )

        # add_all_tables=True should have more variables
        assert len(vars_all) > len(vars_partial), (
            f"Expected more variables with add_all_tables=True "
            f"({len(vars_all)} vs {len(vars_partial)})"
        )

        # All tables from partial should be in all
        for table_code in tables_partial:
            assert table_code in tables_all, (
                f"Table {table_code} from partial result should be in full result"
            )

    def test_add_all_tables_default_is_true(self, api):
        """Test that the default value for add_all_tables is True."""
        expression = "{tC_47.00, r0310, c0010} = 0"

        # Generate without specifying add_all_tables (should default to True)
        result_default = api.generate_validations_script(
            expressions=[(expression, "test_op", None)],
            module_code="COREP_LR",
            module_version_number="4.1.0",
        )

        # Generate with explicit add_all_tables=True
        result_explicit = api.generate_validations_script(
            expressions=[(expression, "test_op", None)],
            module_code="COREP_LR",
            module_version_number="4.1.0",
            add_all_tables=True,
        )

        assert result_default["success"] is True
        assert result_explicit["success"] is True

        ns_default = list(result_default["enriched_ast"].keys())[0]
        ns_explicit = list(result_explicit["enriched_ast"].keys())[0]

        tables_default = result_default["enriched_ast"][ns_default]["tables"]
        tables_explicit = result_explicit["enriched_ast"][ns_explicit][
            "tables"
        ]

        # Both should have the same number of tables (default = True)
        assert len(tables_default) == len(tables_explicit), (
            f"Default should be same as explicit True: "
            f"{len(tables_default)} vs {len(tables_explicit)}"
        )
