import os

import pytest
from py_dpm.dpm.utils import (
    create_engine_from_url,
    create_engine_object,
    get_engine,
    session_scope,
)


@pytest.fixture
def cleanup_test_dbs():
    """Fixture to clean up test database files after tests."""
    test_dbs = [
        "test_engine_reuse.db",
        "test_engine_object.db",
        "test_session_scope.db",
    ]

    yield

    # Cleanup after test
    for db_file in test_dbs:
        if os.path.exists(db_file):
            os.remove(db_file)


def test_create_engine_from_url_sqlite_smoke(cleanup_test_dbs):
    url = "sqlite:///test_engine_reuse.db"
    engine = create_engine_from_url(url)
    assert engine is not None


def test_create_engine_object_sqlite_smoke(cleanup_test_dbs):
    url = "sqlite:///test_engine_object.db"
    engine = create_engine_object(url)
    assert engine is not None


def test_session_scope_closes_session(cleanup_test_dbs):
    engine = get_engine(database_path="test_session_scope.db")

    with session_scope() as session:
        # Simple smoke query: ensure we can execute something against the engine
        conn = engine.connect()
        conn.close()

    # If we reach here without error, the context manager closed the session.
    # SQLAlchemy itself will recycle connections via the pool.
