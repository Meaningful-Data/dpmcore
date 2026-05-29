"""Unit tests for ``dpmcore.orm.base.Base.to_dict``.

The serialiser must skip deferred columns so callers never trigger a
lazy DB load for columns they did not request. This contract was
previously enforced via a monkey-patch in dpm-renderer; the test here
keeps the upstream fix from regressing.
"""

from __future__ import annotations

from typing import Optional

import pytest
from sqlalchemy import Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from dpmcore.orm.base import Base


class _IsolatedBase(DeclarativeBase):
    """Isolated declarative base for to_dict tests.

    Lives on its own ``registry`` / ``MetaData`` so the test table never
    pollutes ``Base.metadata`` — which schema-validation tests read at
    pytest collection time. ``Base.to_dict`` is reused unchanged so the
    test still exercises the real implementation.
    """

    to_dict = Base.to_dict


class _Item(_IsolatedBase):
    __tablename__ = "_items_to_dict_test"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[Optional[str]] = mapped_column(String(20))
    payload: Mapped[Optional[str]] = mapped_column(String(2000), deferred=True)


@pytest.fixture
def item_class() -> type:
    return _Item


def _seed_session(item_cls: type) -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[item_cls.__table__])
    session = Session(bind=engine)
    session.add(item_cls(id=1, code="A", payload="a" * 100))
    session.commit()
    return session


def test_to_dict_skips_deferred_columns(item_class: type) -> None:
    """Deferred columns must not appear in the serialised mapping."""
    session = _seed_session(item_class)
    instance = session.query(item_class).filter_by(id=1).one()
    # Expire so deferred 'payload' is not loaded; touching it later
    # would emit a second SELECT.
    session.expire(instance)
    instance.code  # noqa: B018  -- load the eager set only

    result = instance.to_dict()

    assert "id" in result
    assert "code" in result
    assert "payload" not in result


def test_to_dict_includes_non_deferred_columns(item_class: type) -> None:
    """Non-deferred columns must round-trip through to_dict unchanged."""
    session = _seed_session(item_class)
    instance = session.query(item_class).filter_by(id=1).one()

    result = instance.to_dict()

    assert result["id"] == 1
    assert result["code"] == "A"
