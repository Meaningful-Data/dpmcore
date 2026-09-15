"""Tests for the standalone release-window predicates.

:func:`filter_by_release` applies its window as a ``WHERE`` clause,
which is wrong for an outer join — it narrows the join back to an inner
one. :func:`release_window_condition` hands the same predicate back as
an expression for the ``ON`` clause instead, and
:func:`release_window_conditions` builds several of them from a single
load of the release ordering (#359).

Seed model: three dated releases 1..3, plus an undated working release
9 that always ranks as the latest.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, aliased
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.dpm_xl.utils.filters import (
    filter_by_release,
    release_window_condition,
    release_window_conditions,
)
from dpmcore.orm.base import Base
from dpmcore.orm.glossary import Category, SupercategoryComposition
from dpmcore.orm.infrastructure import Release


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = Session(bind=engine)
    s.add_all(
        [
            Release(release_id=1, code="1.0", date=date(2024, 1, 1)),
            Release(release_id=2, code="1.1", date=date(2024, 2, 1)),
            Release(release_id=3, code="1.2", date=date(2024, 3, 1)),
            Release(release_id=9, code="Playground", date=None),
        ]
    )
    s.add_all(
        Category(
            category_id=cid,
            code=code,
            name=code,
            is_enumerated=True,
            is_active=True,
            is_external_ref_data=False,
        )
        for cid, code in [(1, "SUP"), (2, "MEM")]
    )
    s.add(
        SupercategoryComposition(
            supercategory_id=1,
            category_id=2,
            start_release_id=2,
            end_release_id=None,
        )
    )
    s.commit()
    yield s
    s.close()


def _windowed(session, release_id):
    """Compositions matching the standalone predicate at *release_id*."""
    condition = release_window_condition(
        session,
        start_col=SupercategoryComposition.start_release_id,
        end_col=SupercategoryComposition.end_release_id,
        release_id=release_id,
    )
    return session.query(SupercategoryComposition).filter(condition).all()


def _filtered(session, release_id):
    """The same, via ``filter_by_release``."""
    return filter_by_release(
        session.query(SupercategoryComposition),
        start_col=SupercategoryComposition.start_release_id,
        end_col=SupercategoryComposition.end_release_id,
        release_id=release_id,
        active_only_fallback=True,
    ).all()


class TestSingleCondition:
    @pytest.mark.parametrize("release_id", [1, 2, 3, 9, None])
    def test_it_matches_filter_by_release(self, session, release_id):
        assert len(_windowed(session, release_id)) == len(
            _filtered(session, release_id)
        )

    def test_a_row_before_its_start_release_is_out(self, session):
        assert _windowed(session, 1) == []

    def test_a_row_from_its_start_release_on_is_in(self, session):
        assert len(_windowed(session, 2)) == 1

    def test_an_undated_release_ranks_as_the_latest(self, session):
        assert len(_windowed(session, 9)) == 1

    def test_an_unknown_release_raises(self, session):
        with pytest.raises(ValueError, match="has no sort_order"):
            _windowed(session, 42)


class TestSeveralConditions:
    def test_one_predicate_per_window(self, session):
        conditions = release_window_conditions(
            session,
            [
                (
                    SupercategoryComposition.start_release_id,
                    SupercategoryComposition.end_release_id,
                ),
                (Category.created_release_id, Category.created_release_id),
            ],
            2,
        )

        assert len(conditions) == 2

    def test_they_are_loaded_from_one_release_query(self, session):
        from sqlalchemy import event

        statements: list[str] = []
        engine = session.get_bind()

        def record(conn, cursor, statement, params, context, executemany):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            release_window_conditions(
                session,
                [
                    (
                        SupercategoryComposition.start_release_id,
                        SupercategoryComposition.end_release_id,
                    ),
                    (
                        SupercategoryComposition.start_release_id,
                        SupercategoryComposition.end_release_id,
                    ),
                ],
                2,
            )
        finally:
            event.remove(engine, "before_cursor_execute", record)
        assert len(statements) == 1


class TestOuterJoinStaysOuter:
    """The reason the predicate has to be an expression at all."""

    def test_the_on_clause_keeps_unmatched_rows(self, session):
        from sqlalchemy import and_

        member = aliased(Category)
        condition = release_window_condition(
            session,
            start_col=SupercategoryComposition.start_release_id,
            end_col=SupercategoryComposition.end_release_id,
            release_id=1,
        )
        rows = (
            session.query(Category.code, member.code)
            .outerjoin(
                SupercategoryComposition,
                and_(
                    SupercategoryComposition.supercategory_id
                    == Category.category_id,
                    condition,
                ),
            )
            .outerjoin(
                member,
                member.category_id == SupercategoryComposition.category_id,
            )
            .all()
        )

        # The composition is not open at release 1, but SUP is still
        # listed — with no member. A WHERE clause would have dropped it.
        assert ("SUP", None) in rows
