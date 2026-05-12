"""Integration tests for SchemaValidationService against fixture DB."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from dpmcore.services.schema_validation import SchemaValidationService


class TestFixtureDatabase:
    def test_fixture_db_is_valid(self, fixture_db_url):
        engine = create_engine(fixture_db_url)
        try:
            result = SchemaValidationService(engine).validate()
        finally:
            engine.dispose()

        assert result.is_valid is True, (
            f"Fixture DB unexpectedly invalid. "
            f"missing_tables={result.missing_tables[:10]}, "
            f"missing_columns={list(result.missing_columns)[:10]}, "
            f"empty_required_tables={result.empty_required_tables}"
        )
        assert result.backend == "sqlite"
        assert result.missing_tables == []
        assert result.missing_columns == {}
        assert result.empty_required_tables == []

    def test_dropping_required_table_makes_it_invalid(
        self, fixture_db_url, tmp_path
    ):
        # Copy fixture so we don't mutate the shared file, drop one
        # required table, and re-validate.
        import shutil
        from pathlib import Path
        from urllib.parse import urlparse

        src = Path(urlparse(fixture_db_url).path)
        dst = tmp_path / "copy.db"
        shutil.copy(src, dst)

        engine = create_engine(f"sqlite:///{dst}")
        try:
            with engine.begin() as conn:
                conn.execute(text('DROP TABLE "Variable"'))
            result = SchemaValidationService(engine).validate()
        finally:
            engine.dispose()

        assert result.is_valid is False
        assert "Variable" in result.missing_tables
