"""Unit tests for :func:`dpmcore.orm.query_utils.chunked_in`.

The helper splits an ``IN (...)`` filter into batches to stay under SQL
Server's 2,100-bound-parameter limit. These tests run on SQLite and
prove the chunked result is identical to a single unchunked statement,
exercising the batch boundary with a deliberately tiny chunk size.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base

from dpmcore.orm import query_utils
from dpmcore.orm._compat import Mapped, mapped_column
from dpmcore.orm.query_utils import chunked_in

# Isolated registry so the throwaway table never pollutes Base.metadata.
_IsolatedBase = declarative_base()


class _Widget(_IsolatedBase):
    __tablename__ = "_widgets_chunked_in_test"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group: Mapped[str] = mapped_column(String(10))


@pytest.fixture
def session() -> Session:
    """An in-memory SQLite session seeded with ten widgets."""
    engine = create_engine("sqlite:///:memory:")
    _IsolatedBase.metadata.create_all(engine, tables=[_Widget.__table__])
    db = Session(bind=engine)
    for i in range(1, 11):
        db.add(_Widget(id=i, group="A" if i % 2 else "B"))
    db.commit()
    return db


def test_empty_values_issues_no_query(session: Session) -> None:
    """An empty collection yields an empty list and runs no statement."""
    assert chunked_in(session.query(_Widget), _Widget.id, []) == []


def test_single_chunk_returns_all_matches(session: Session) -> None:
    """Below the chunk size, results match a plain ``IN`` query."""
    ids = [2, 4, 6]
    rows = chunked_in(session.query(_Widget), _Widget.id, ids)
    assert sorted(w.id for w in rows) == ids


def test_multiple_chunks_equal_unchunked(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spanning several batches equals the single-statement result."""
    monkeypatch.setattr(query_utils, "IN_CHUNK_SIZE", 2)
    ids = [1, 2, 3, 5, 7, 9]
    chunked = chunked_in(session.query(_Widget), _Widget.id, ids)
    unchunked = session.query(_Widget).filter(_Widget.id.in_(ids)).all()
    assert sorted(w.id for w in chunked) == sorted(w.id for w in unchunked)
    assert sorted(w.id for w in chunked) == ids


def test_duplicates_across_chunks_yield_each_row_once(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate values that straddle batches don't duplicate rows.

    Without de-duplication ``[1, 2, 1]`` at chunk size 2 would query id
    1 in both batches and return its row twice, diverging from a single
    ``IN (...)`` (which ignores duplicate bound values).
    """
    monkeypatch.setattr(query_utils, "IN_CHUNK_SIZE", 2)
    rows = chunked_in(session.query(_Widget), _Widget.id, [1, 2, 1])
    assert sorted(w.id for w in rows) == [1, 2]


def test_base_query_filters_preserved_across_chunks(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filters already on the base query apply to every batch."""
    monkeypatch.setattr(query_utils, "IN_CHUNK_SIZE", 2)
    base = session.query(_Widget).filter(_Widget.group == "A")
    rows = chunked_in(base, _Widget.id, [1, 2, 3, 4, 5, 6])
    # Only odd ids are group "A".
    assert sorted(w.id for w in rows) == [1, 3, 5]
