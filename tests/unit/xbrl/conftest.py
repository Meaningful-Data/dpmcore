"""Shared fixtures for the XBRL importer unit tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def schema_engine():
    """In-memory SQLite engine with the full DPM schema created."""
    engine = create_engine("sqlite:///:memory:")
    from dpmcore.orm.base import Base

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def schema_session(schema_engine):
    """Session bound to the in-memory DPM schema."""
    session = sessionmaker(bind=schema_engine)()
    yield session
    session.close()
