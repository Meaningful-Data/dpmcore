"""Unit tests for super-category expansion (issue #359).

A super-category's value set is its own items plus those of the
categories composing it, and ``ItemCategory`` files each item under the
one category that owns it. Every domain-resolving path in the codebase
goes through :mod:`dpmcore.orm.supercategories` for that expansion, so
the query itself — the join, the member filters, the release window and
the transitive walk — is exercised here against an in-memory SQLite
database rather than only through the fixture-DB integration tests,
which CI skips.

Seed model, four releases 1..4:

    SUPER  composes  ALPHA   from release 1 (never closed)
    SUPER  composes  BETA    from release 3 (never closed)
    SUPER  composes  RAW     from release 1  — RAW is not enumerated
    OUTER  composes  SUPER   from release 1  — one level of nesting
    PLAIN  composes  nothing
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import dpmcore.orm  # noqa: F401  — ensure all models are loaded
from dpmcore.orm.base import Base
from dpmcore.orm.glossary import Category, SupercategoryComposition
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.supercategories import (
    load_supercategory_compositions,
    load_supercategory_member_codes,
    load_supercategory_members,
)

ALPHA, BETA, RAW, SUPER, OUTER, PLAIN = 1, 2, 3, 4, 5, 6


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
        Release(
            release_id=rid,
            code=f"1.{rid}",
            date=date(2024, rid, 1),
            status="Final",
            is_current=rid == 4,
        )
        for rid in (1, 2, 3, 4)
    )
    s.add_all(
        Category(
            category_id=cid,
            code=code,
            name=code.title(),
            is_enumerated=enumerated,
            is_active=True,
            is_external_ref_data=False,
            created_release_id=1,
        )
        for cid, code, enumerated in [
            (ALPHA, "ALPHA", True),
            (BETA, "BETA", True),
            (RAW, "RAW", False),
            (SUPER, "SUPER", True),
            (OUTER, "OUTER", True),
            (PLAIN, "PLAIN", True),
        ]
    )
    s.add_all(
        SupercategoryComposition(
            supercategory_id=parent,
            category_id=member,
            start_release_id=start,
            end_release_id=end,
        )
        for parent, member, start, end in [
            (SUPER, ALPHA, 1, None),
            (SUPER, BETA, 3, None),
            (SUPER, RAW, 1, None),
            (OUTER, SUPER, 1, None),
        ]
    )
    s.commit()
    yield s
    s.close()


class TestMembersById:
    def test_a_plain_category_expands_to_nothing(self, session):
        members = load_supercategory_members(session, {PLAIN}, release_id=None)

        assert members == {}

    def test_the_composing_categories_are_returned(self, session):
        members = load_supercategory_members(session, {SUPER}, release_id=4)

        assert members == {SUPER: {ALPHA, BETA}}

    def test_a_member_outside_its_window_is_left_out(self, session):
        """BETA only joins at release 3."""
        members = load_supercategory_members(session, {SUPER}, release_id=2)

        assert members == {SUPER: {ALPHA}}

    def test_a_non_enumerated_member_is_never_a_value_set(self, session):
        """RAW composes SUPER at every release but holds no values."""
        members = load_supercategory_members(session, {SUPER}, release_id=None)

        assert RAW not in members[SUPER]

    def test_nesting_is_followed_to_the_end(self, session):
        """OUTER composes SUPER, so it also takes SUPER's members."""
        members = load_supercategory_members(session, {OUTER}, release_id=4)

        assert members == {OUTER: {SUPER, ALPHA, BETA}}

    def test_a_cycle_terminates(self, session):
        session.add(
            SupercategoryComposition(
                supercategory_id=ALPHA,
                category_id=SUPER,
                start_release_id=1,
                end_release_id=None,
            )
        )
        session.commit()

        members = load_supercategory_members(session, {SUPER}, release_id=4)

        # SUPER reaches ALPHA, ALPHA reaches back to SUPER; a key is
        # never expanded twice, so the walk ends instead of looping,
        # and a category is not reported as composing itself.
        assert members == {SUPER: {ALPHA, BETA}}

    def test_several_categories_resolve_in_one_call(self, session):
        members = load_supercategory_members(
            session, {SUPER, PLAIN, ALPHA}, release_id=4
        )

        assert members == {SUPER: {ALPHA, BETA}}

    def test_nothing_to_expand_costs_no_query(self):
        from unittest.mock import MagicMock

        session = MagicMock()

        assert (
            load_supercategory_members(session, set(), release_id=None) == {}
        )
        session.query.assert_not_called()


class TestMembersByCode:
    def test_codes_mirror_the_id_keyed_answer(self, session):
        members = load_supercategory_member_codes(
            session, {"SUPER"}, release_id=4
        )

        assert members == {"SUPER": {"ALPHA", "BETA"}}

    def test_the_same_release_window_applies(self, session):
        members = load_supercategory_member_codes(
            session, {"SUPER"}, release_id=2
        )

        assert members == {"SUPER": {"ALPHA"}}

    def test_the_same_member_filters_apply(self, session):
        """The two keyings must not disagree on what counts as a member."""
        by_code = load_supercategory_member_codes(
            session, {"SUPER"}, release_id=None
        )
        by_id = load_supercategory_members(session, {SUPER}, release_id=None)
        codes = {c.category_id: c.code for c in session.query(Category).all()}

        assert by_code["SUPER"] == {codes[cid] for cid in by_id[SUPER]}

    def test_nothing_to_expand_costs_no_query(self):
        from unittest.mock import MagicMock

        session = MagicMock()

        assert (
            load_supercategory_member_codes(session, set(), release_id=None)
            == {}
        )
        session.query.assert_not_called()


class TestCompositions:
    def test_every_window_is_kept(self, session):
        compositions = load_supercategory_compositions(session, {SUPER})

        assert {
            (c.category_id, c.start_release_id) for c in compositions[SUPER]
        } == {(ALPHA, 1), (BETA, 3)}

    def test_a_non_enumerated_member_is_left_out(self, session):
        compositions = load_supercategory_compositions(session, {SUPER})

        assert RAW not in {c.category_id for c in compositions[SUPER]}

    def test_a_plain_category_has_no_entry(self, session):
        assert load_supercategory_compositions(session, {PLAIN}) == {}

    def test_nesting_is_loaded_too(self, session):
        """OUTER composes SUPER, so SUPER's own rows are needed as well.

        The windows stay separate — the caller decides, release by
        release, whether both links are open.
        """
        compositions = load_supercategory_compositions(session, {OUTER})

        assert {c.category_id for c in compositions[OUTER]} == {SUPER}
        assert {c.category_id for c in compositions[SUPER]} == {ALPHA, BETA}

    def test_a_cycle_terminates(self, session):
        session.add(
            SupercategoryComposition(
                supercategory_id=ALPHA,
                category_id=SUPER,
                start_release_id=1,
                end_release_id=None,
            )
        )
        session.commit()

        compositions = load_supercategory_compositions(session, {SUPER})

        assert {c.category_id for c in compositions[ALPHA]} == {SUPER}

    def test_nothing_to_load_costs_no_query(self):
        from unittest.mock import MagicMock

        session = MagicMock()

        assert load_supercategory_compositions(session, set()) == {}
        session.query.assert_not_called()
