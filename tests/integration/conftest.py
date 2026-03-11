"""Integration test configuration.

This module provides:
- Automatic marking of integration tests
- Database fixtures with proper cleanup
- Session management with nested transaction rollback pattern
- Shared SQLite fixture for tests that need real DPM data
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

FIXTURE_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "test_data.db"
)


def pytest_collection_modifyitems(items):
    """Automatically mark all tests in this directory as integration tests."""
    for item in items:
        if "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def cleanup_caches():
    """Clear module-level caches after each test to prevent state leakage."""
    yield

    from dpmcore.dpm_xl.ast.operands import _HEADERS_CACHE

    _HEADERS_CACHE.clear()


@pytest.fixture
def memory_engine():
    """Create an in-memory SQLite engine with StaticPool."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield engine
    engine.dispose()


@pytest.fixture
def memory_session(memory_engine):
    """Create a session with nested transaction rollback pattern."""
    from dpmcore.orm import Base

    Base.metadata.create_all(memory_engine)

    connection = memory_engine.connect()
    transaction = connection.begin()

    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def fixture_db_url():
    """Provide a connection URL to the local SQLite fixture database.

    The fixture DB contains real DPM data and is used by tests that
    require a populated database (semantic validation, release filters, etc.).
    """
    assert os.path.exists(FIXTURE_DB_PATH), (
        f"Fixture DB not found at {FIXTURE_DB_PATH}. "
        f"Copy it from pydpm/tests/fixtures/test_data.db."
    )
    return f"sqlite:///{os.path.abspath(FIXTURE_DB_PATH)}"


@pytest.fixture
def fixture_session(fixture_db_url):
    """Provide a SQLAlchemy session connected to the fixture database."""
    engine = create_engine(fixture_db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    engine.dispose()
