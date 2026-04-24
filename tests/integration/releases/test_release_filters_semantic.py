"""Tests for release-aware query filters used by semantic analysis.

Ported from py_dpm. Exercises:
1. ``filter_by_release`` uses SQLAlchemy ``IS NULL`` for the end column
   (critical for PostgreSQL's strict NULL comparison semantics).
2. ``OperandsChecking.check_headers`` wires ``filter_by_release`` with
   the correct start/end columns and propagates the instance's
   ``release_id``.
"""

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dpmcore.dpm_xl.ast import operands as operands_module
from dpmcore.dpm_xl.utils.filters import filter_by_release
from dpmcore.orm import Base
from dpmcore.orm.rendering import TableVersion


def _make_session():
    """Create a lightweight in-memory SQLAlchemy session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_filter_by_release_uses_is_null_for_end_release():
    """End-column NULL handling must compile to ``IS NULL``."""
    session = _make_session()

    query = session.query(TableVersion)
    filtered = filter_by_release(
        query,
        start_col=TableVersion.start_release_id,
        end_col=TableVersion.end_release_id,
        release_id=5,
    )

    sql = str(
        filtered.statement.compile(
            dialect=session.get_bind().dialect,
            compile_kwargs={"literal_binds": True},
        )
    ).upper()

    assert "IS NULL" in sql
    assert "= NULL" not in sql


def test_operands_check_headers_calls_filter_by_release_with_correct_args(
    monkeypatch,
):
    """check_headers passes the correct columns/release_id to filter_by_release."""
    called = {}

    def fake_filter_by_release(
        query,
        start_col,
        end_col,
        release_id=None,
        release_code=None,
    ):
        called["query"] = query
        called["start_col"] = start_col
        called["end_col"] = end_col
        called["release_id"] = release_id
        called["release_code"] = release_code
        return query

    monkeypatch.setattr(
        operands_module, "filter_by_release", fake_filter_by_release
    )

    # Stub out the pandas/SQLAlchemy helpers so the test doesn't touch
    # a real DB.
    import dpmcore.dpm_xl.model_queries as model_queries

    monkeypatch.setattr(
        model_queries,
        "compile_query_for_pandas",
        lambda stmt, session: stmt,
    )

    def fake_read_sql(sql, session):
        return pd.DataFrame(
            columns=[
                "Code",
                "StartReleaseID",
                "EndReleaseID",
                "Direction",
                "HasOpenRows",
                "HasOpenColumns",
                "HasOpenSheets",
            ]
        )

    monkeypatch.setattr(
        model_queries, "read_sql_with_connection", fake_read_sql
    )

    session = _make_session()

    # Build a minimal OperandsChecking instance without running __init__
    # (which would require a fully-populated AST and database).
    oc = object.__new__(operands_module.OperandsChecking)
    oc.session = session
    oc.release_id = 7
    oc.tables = {"DummyTable": {}}

    operands_module.OperandsChecking.check_headers(oc)

    assert called["start_col"] is TableVersion.start_release_id
    assert called["end_col"] is TableVersion.end_release_id
    assert called["release_id"] == 7
    assert called["release_code"] is None
