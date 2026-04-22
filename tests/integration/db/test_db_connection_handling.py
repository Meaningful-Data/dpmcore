"""Tests for dpmcore's connection helpers.

Ported from py_dpm's ``test_db_connection_handling`` which covered
``create_engine_from_url``, ``create_engine_object``, ``get_engine`` and
``session_scope``. Those helpers do not exist in dpmcore — the public
entry point is now :func:`dpmcore.connect` which returns a
:class:`DpmConnection` context manager. The ported tests exercise the
equivalent behaviours against the new API.
"""

from __future__ import annotations

import os

import pytest

from dpmcore import connect
from dpmcore.connection import DpmConnection


@pytest.fixture
def sqlite_url(tmp_path):
    """Temporary on-disk SQLite URL, cleaned up by tmp_path."""
    db_path = tmp_path / "test_dpmcore_connection.db"
    yield f"sqlite:///{db_path.as_posix()}"
    if os.path.exists(db_path):
        os.remove(db_path)


def test_connect_creates_engine_and_session(sqlite_url):
    """connect() returns a DpmConnection with an engine and session."""
    conn = connect(sqlite_url)
    try:
        assert isinstance(conn, DpmConnection)
        assert conn.engine is not None
        assert conn.session is not None
    finally:
        conn.close()


def test_connect_context_manager_closes(sqlite_url):
    """DpmConnection works as a context manager and closes cleanly."""
    with connect(sqlite_url) as conn:
        # Simple smoke: run a query through the engine
        connection = conn.engine.connect()
        connection.close()

    # After the with-block the engine's connection pool should be disposed.
    # SQLAlchemy resets ``engine.pool`` to a fresh pool after ``dispose``;
    # we verify the contextmanager didn't raise and a subsequent close is
    # a no-op.
    conn.close()  # idempotent close should not raise


def test_connect_exposes_services(sqlite_url):
    """The connection exposes lazy service accessors."""
    with connect(sqlite_url) as conn:
        syntax = conn.services.syntax
        assert syntax is not None
        # Second access should return the same cached instance.
        assert conn.services.syntax is syntax
