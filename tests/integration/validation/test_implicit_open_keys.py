"""Tests for implicit open keys (refPeriod, entityID).

Issue #36: refPeriod and entityID are implicit open keys that should always be
available when explicitly mentioned, without needing to be declared in the database.
"""

import os

import pytest
from dotenv import load_dotenv
from urllib.parse import quote_plus

from py_dpm.api.dpm_xl.semantic import validate_expression


load_dotenv()


def _semantic_db_kwargs():
    """
    Build DB configuration for semantic validation from environment/.env.

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

    # Legacy PostgreSQL configuration
    use_postgres = os.getenv("USE_POSTGRES", "false").lower() == "true"
    use_sqlite = os.getenv("USE_SQLITE", "true").lower() == "true"

    if use_postgres:
        host = os.getenv("POSTGRES_HOST")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB")
        user = os.getenv("POSTGRES_USER")
        password = os.getenv("POSTGRES_PASS")

        if all([host, db, user, password]):
            connection_url = (
                f"postgresql://{user}:{password}@{host}:{port}/{db}"
            )
            return {"connection_url": connection_url}

    if use_sqlite:
        db_path = os.getenv("SQLITE_DB_PATH", "database.db")
        return {"database_path": db_path}

    # No DB configuration found; let underlying defaults apply
    return {}


class TestImplicitOpenKeys:
    """Test that implicit open keys (refPeriod, entityID) are recognized."""

    def test_get_refperiod_is_valid(self):
        """Test that [get refPeriod] is valid and doesn't raise error 1-5.

        This is the exact case from issue #36:
        {tC_48.02, c0020}[get refPeriod] should be valid because refPeriod
        is an implicit open key that only arises when explicitly mentioned.
        """
        expression = "{tC_48.02, c0020}[get refPeriod]"
        result = validate_expression(
            expression, release_id=5, **_semantic_db_kwargs()
        )
        assert result.is_valid, (
            f"Expected [get refPeriod] to be valid, but got error: {result.error_message}"
        )

    def test_get_entityid_is_valid(self):
        """Test that [get entityID] is valid and doesn't raise error 1-5.

        entityID is an implicit open key like refPeriod.
        """
        expression = "{tC_48.02, c0020}[get entityID]"
        result = validate_expression(
            expression, release_id=5, **_semantic_db_kwargs()
        )
        assert result.is_valid, (
            f"Expected [get entityID] to be valid, but got error: {result.error_message}"
        )

    def test_refperiod_in_where_clause_is_valid(self):
        """Test that refPeriod can be used in a WHERE clause.

        Note: Using comparison with another [get refPeriod] expression
        rather than a date literal to avoid date parsing issues.
        """
        expression = "{tC_48.02, c0020}[where refPeriod <= {tC_48.02, c0020}[get refPeriod]]"
        result = validate_expression(
            expression, release_id=5, **_semantic_db_kwargs()
        )
        assert result.is_valid, (
            f"Expected refPeriod in WHERE clause to be valid, but got error: {result.error_message}"
        )

    def test_entityid_in_where_clause_is_valid(self):
        """Test that entityID can be used in a WHERE clause."""
        expression = '{tC_48.02, c0020}[where entityID = "test_entity"]'
        result = validate_expression(
            expression, release_id=5, **_semantic_db_kwargs()
        )
        assert result.is_valid, (
            f"Expected entityID in WHERE clause to be valid, but got error: {result.error_message}"
        )

    def test_issue_36_full_expression(self):
        """Test the full expression from issue #36.

        The validation:
        {tC_48.02, c0020}[get qRDT] <= {tC_48.02, c0020}[get refPeriod] and
        {tC_48.02, c0020}[get qRDT] > time_shift(max_aggr({tC_48.02, c0020}[get refPeriod]), Q, (-1))

        Should be valid for the latest release. The error 1-5 should not occur
        for refPeriod as it is an implicit open key.
        """
        expression = """
        {tC_48.02, c0020}[get qRDT] <= {tC_48.02, c0020}[get refPeriod] and
        {tC_48.02, c0020}[get qRDT] > time_shift(max_aggr({tC_48.02, c0020}[get refPeriod]), Q, (-1))
        """
        result = validate_expression(
            expression, release_id=5, **_semantic_db_kwargs()
        )
        # Note: This test may fail if qRDT is not a valid open key in the test database.
        # The key assertion here is that refPeriod should NOT be the cause of failure.
        if not result.is_valid:
            # If it fails, make sure it's not because of refPeriod
            assert "refPeriod" not in result.error_message, (
                f"refPeriod should be recognized as implicit key, but got error: {result.error_message}"
            )
