"""Tests for engine/schema-aware query caching in ``model_queries``.

Covers the fix where ``_get_engine_cache_key`` and
``read_sql_with_connection`` started accounting for
``schema_translate_map``: two sessions bound to the same engine URL but
scoped to different schemas (e.g. distinct staging schemas, or staging
vs. the default schema) must never share a cache entry.
"""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dpmcore.dpm_xl import model_queries
from dpmcore.orm.base import Base
from dpmcore.orm.infrastructure import Release


def _session_for(engine):
    return sessionmaker(bind=engine)()


class TestGetEngineCacheKey:
    def test_same_engine_produces_equal_keys(self):
        engine = create_engine("sqlite:///:memory:")

        key_a = model_queries._get_engine_cache_key(_session_for(engine))
        key_b = model_queries._get_engine_cache_key(_session_for(engine))

        assert key_a == key_b

    def test_schema_translate_map_changes_the_key(self):
        engine = create_engine("sqlite:///:memory:")
        scoped_engine = engine.execution_options(
            schema_translate_map={None: "staging"}
        )

        plain_key = model_queries._get_engine_cache_key(
            _session_for(engine)
        )
        scoped_key = model_queries._get_engine_cache_key(
            _session_for(scoped_engine)
        )

        assert plain_key != scoped_key

    def test_different_schemas_produce_different_keys(self):
        engine = create_engine("sqlite:///:memory:")
        engine_a = engine.execution_options(
            schema_translate_map={None: "staging_a"}
        )
        engine_b = engine.execution_options(
            schema_translate_map={None: "staging_b"}
        )

        key_a = model_queries._get_engine_cache_key(_session_for(engine_a))
        key_b = model_queries._get_engine_cache_key(_session_for(engine_b))

        assert key_a != key_b

    def test_same_schema_translate_map_produces_equal_keys(self):
        engine = create_engine("sqlite:///:memory:")
        engine_a = engine.execution_options(
            schema_translate_map={None: "staging"}
        )
        engine_b = engine.execution_options(
            schema_translate_map={None: "staging"}
        )

        key_a = model_queries._get_engine_cache_key(_session_for(engine_a))
        key_b = model_queries._get_engine_cache_key(_session_for(engine_b))

        assert key_a == key_b


class TestReadSqlWithConnection:
    def test_returns_dataframe_matching_query_columns_and_rows(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = _session_for(engine)
        session.add(Release(release_id=1, code="4.0"))
        session.add(Release(release_id=2, code="4.2"))
        session.commit()

        stmt = select(Release.release_id, Release.code).order_by(
            Release.release_id
        )

        df = model_queries.read_sql_with_connection(stmt, session)

        assert list(df.columns) == ["release_id", "code"]
        assert df["code"].tolist() == ["4.0", "4.2"]

    def test_empty_result_returns_empty_dataframe_with_columns(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = _session_for(engine)

        stmt = select(Release.release_id, Release.code)

        df = model_queries.read_sql_with_connection(stmt, session)

        assert df.empty
        assert list(df.columns) == ["release_id", "code"]
