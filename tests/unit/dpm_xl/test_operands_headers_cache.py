"""Tests for the schema-aware ``_HEADERS_CACHE`` in ``OperandsChecking``.

Before the fix, ``_HEADERS_CACHE`` keyed cached header lookups only by
engine URL. Two sessions bound to the same engine URL but scoped to
different schemas (e.g. two distinct staging schemas from separate
``update-db`` runs, or a staging schema vs. the default schema) would
collide on the same cache entry and silently reuse headers resolved
against the wrong schema. This module verifies ``check_headers`` now
keys its cache on ``schema_translate_map`` too.
"""

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import dpmcore.dpm_xl.model_queries as model_queries
from dpmcore.dpm_xl.ast import operands as operands_module

_HEADER_COLUMNS = [
    "Code",
    "StartReleaseID",
    "EndReleaseID",
    "Direction",
    "HasOpenRows",
    "HasOpenColumns",
    "HasOpenSheets",
]


@pytest.fixture(autouse=True)
def _clear_headers_cache():
    yield
    operands_module._HEADERS_CACHE.clear()


def _make_oc(session, table="C_01.00"):
    oc = object.__new__(operands_module.OperandsChecking)
    oc.session = session
    oc.release_id = 5
    oc.tables = {table: {}}
    return oc


@pytest.fixture
def patched_query_helpers(monkeypatch):
    """Stub the pieces that would otherwise hit a real DB.

    Returns the list of sessions ``read_sql_with_connection`` was
    called with, so tests can assert how many times the "DB" was
    actually queried.
    """
    monkeypatch.setattr(
        operands_module, "filter_by_release", lambda query, **kwargs: query
    )

    calls = []

    def fake_read_sql(stmt, session):
        calls.append(session)
        return pd.DataFrame(columns=_HEADER_COLUMNS)

    monkeypatch.setattr(
        model_queries, "read_sql_with_connection", fake_read_sql
    )
    return calls


class TestHeadersCacheSchemaAwareness:
    def test_different_schema_translate_maps_both_query_the_db(
        self, patched_query_helpers
    ):
        engine = create_engine("sqlite:///:memory:")
        engine_a = engine.execution_options(
            schema_translate_map={None: "staging_a"}
        )
        engine_b = engine.execution_options(
            schema_translate_map={None: "staging_b"}
        )

        _make_oc(sessionmaker(bind=engine_a)()).check_headers()
        _make_oc(sessionmaker(bind=engine_b)()).check_headers()

        assert len(patched_query_helpers) == 2

    def test_schema_scoped_and_unscoped_sessions_both_query_the_db(
        self, patched_query_helpers
    ):
        engine = create_engine("sqlite:///:memory:")
        scoped_engine = engine.execution_options(
            schema_translate_map={None: "staging"}
        )

        _make_oc(sessionmaker(bind=engine)()).check_headers()
        _make_oc(sessionmaker(bind=scoped_engine)()).check_headers()

        assert len(patched_query_helpers) == 2

    def test_same_schema_translate_map_reuses_cached_result(
        self, patched_query_helpers
    ):
        engine = create_engine("sqlite:///:memory:")
        engine_a = engine.execution_options(
            schema_translate_map={None: "staging"}
        )
        engine_b = engine.execution_options(
            schema_translate_map={None: "staging"}
        )

        _make_oc(sessionmaker(bind=engine_a)()).check_headers()
        _make_oc(sessionmaker(bind=engine_b)()).check_headers()

        assert len(patched_query_helpers) == 1

    def test_repeated_call_on_same_session_reuses_cached_result(
        self, patched_query_helpers
    ):
        engine = create_engine("sqlite:///:memory:")
        oc = _make_oc(sessionmaker(bind=engine)())

        oc.check_headers()
        oc.check_headers()

        assert len(patched_query_helpers) == 1
