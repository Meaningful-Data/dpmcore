"""Unit tests for dpmcore.services._open_keys.get_open_keys_for_tables.

Regression coverage for dpmcore#381: the query walks ``TableVersion``
-> ``TableVersionHeader`` -> ``Header`` (filtered to ``Header.IsKey``)
-> ``HeaderVersion`` -> ``Property`` -> ``ItemCategory`` -> ``DataType``,
not the wrong ``KeyComposition``/``VariableVersion`` path. Runs against
a real in-memory SQLite database (no external fixture needed) so the
join itself is exercised, not a mock of it.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from dpmcore.orm.base import Base
from dpmcore.orm.glossary import Category, Item, ItemCategory, Property
from dpmcore.orm.infrastructure import DataType, Release
from dpmcore.orm.rendering import (
    Header,
    HeaderVersion,
    Table,
    TableVersion,
    TableVersionHeader,
)
from dpmcore.services._open_keys import get_open_keys_for_tables

pytestmark = pytest.mark.unit


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _add_key_header(
    session,
    *,
    table_vid,
    table_id,
    header_id,
    item_id,
    property_code,
    data_type_id=1,
    is_key=True,
    ic_start_release_id=1,
    ic_end_release_id=None,
):
    """Wire one Header (key or not) with its property code onto a table."""
    session.add_all(
        [
            Header(header_id=header_id, table_id=table_id, is_key=is_key),
            Item(item_id=item_id),
            Property(property_id=item_id, data_type_id=data_type_id),
            ItemCategory(
                item_id=item_id,
                start_release_id=ic_start_release_id,
                end_release_id=ic_end_release_id,
                category_id=1,
                code=property_code,
            ),
            HeaderVersion(
                header_vid=header_id, header_id=header_id, property_id=item_id
            ),
            TableVersionHeader(
                table_vid=table_vid, header_id=header_id, header_vid=header_id
            ),
        ]
    )


@pytest.fixture
def base_table(session):
    """One table (T_01.01, table_vid=1) with the shared scaffolding rows."""
    session.add_all(
        [
            Release(release_id=1, code="1.0", date=datetime.date(2020, 1, 1)),
            Release(release_id=2, code="2.0", date=datetime.date(2021, 1, 1)),
            Release(release_id=3, code="3.0", date=datetime.date(2022, 1, 1)),
            Category(category_id=1),
            DataType(data_type_id=1, code="s"),
            Table(table_id=1),
            TableVersion(
                table_vid=1,
                table_id=1,
                code="T_01.01",
                start_release_id=1,
                end_release_id=None,
            ),
        ]
    )
    return session


class TestGetOpenKeysForTables:
    def test_empty_table_codes_returns_empty_dict(self, session):
        assert get_open_keys_for_tables(session, []) == {}

    def test_unknown_table_code_returns_empty_dict(self, base_table):
        assert get_open_keys_for_tables(base_table, ["NOPE"]) == {
            "NOPE": {}
        }

    def test_key_header_returns_property_and_type(self, base_table):
        _add_key_header(
            base_table,
            table_vid=1,
            table_id=1,
            header_id=1,
            item_id=100,
            property_code="qCDF",
        )
        base_table.commit()

        result = get_open_keys_for_tables(base_table, ["T_01.01"])
        assert result == {"T_01.01": {"qCDF": "s"}}

    def test_non_key_header_excluded(self, base_table):
        _add_key_header(
            base_table,
            table_vid=1,
            table_id=1,
            header_id=1,
            item_id=100,
            property_code="qCDF",
            is_key=False,
        )
        base_table.commit()

        result = get_open_keys_for_tables(base_table, ["T_01.01"])
        assert result == {"T_01.01": {}}

    def test_multiple_key_headers_all_returned(self, base_table):
        _add_key_header(
            base_table,
            table_vid=1,
            table_id=1,
            header_id=1,
            item_id=100,
            property_code="qCDF",
        )
        _add_key_header(
            base_table,
            table_vid=1,
            table_id=1,
            header_id=2,
            item_id=200,
            property_code="ei1452",
        )
        base_table.commit()

        result = get_open_keys_for_tables(base_table, ["T_01.01"])
        assert result == {"T_01.01": {"qCDF": "s", "ei1452": "s"}}

    def test_release_window_excludes_table_version_outside_it(
        self, base_table
    ):
        # The TableVersion only starts at release 1; querying at a
        # release before that must not see it.
        base_table.add(
            TableVersion(
                table_vid=2,
                table_id=1,
                code="T_02.00",
                start_release_id=2,
                end_release_id=None,
            )
        )
        _add_key_header(
            base_table,
            table_vid=2,
            table_id=1,
            header_id=1,
            item_id=100,
            property_code="qCDF",
        )
        base_table.commit()

        result = get_open_keys_for_tables(
            base_table, ["T_02.00"], release_id=1
        )
        assert result == {"T_02.00": {}}

    def test_renamed_property_without_release_keeps_current_alias(
        self, base_table
    ):
        """Regression: LES renamed to qLES at release 3 must not
        duplicate the open key under both codes when no release is
        given — only the currently open (``qLES``) alias survives.
        """
        base_table.add_all(
            [
                Header(header_id=1, table_id=1, is_key=True),
                Item(item_id=100),
                Property(property_id=100, data_type_id=1),
                ItemCategory(
                    item_id=100,
                    start_release_id=1,
                    end_release_id=3,
                    category_id=1,
                    code="LES",
                ),
                ItemCategory(
                    item_id=100,
                    start_release_id=3,
                    end_release_id=None,
                    category_id=1,
                    code="qLES",
                ),
                HeaderVersion(header_vid=1, header_id=1, property_id=100),
                TableVersionHeader(table_vid=1, header_id=1, header_vid=1),
            ]
        )
        base_table.commit()

        result = get_open_keys_for_tables(base_table, ["T_01.01"])
        assert result == {"T_01.01": {"qLES": "s"}}

    def test_renamed_property_at_release_uses_the_alias_active_then(
        self, base_table
    ):
        """The pre-rename release sees ``LES``, the post-rename release
        sees ``qLES`` — never both, and never the wrong one.
        """
        base_table.add_all(
            [
                Header(header_id=1, table_id=1, is_key=True),
                Item(item_id=100),
                Property(property_id=100, data_type_id=1),
                ItemCategory(
                    item_id=100,
                    start_release_id=1,
                    end_release_id=3,
                    category_id=1,
                    code="LES",
                ),
                ItemCategory(
                    item_id=100,
                    start_release_id=3,
                    end_release_id=None,
                    category_id=1,
                    code="qLES",
                ),
                HeaderVersion(header_vid=1, header_id=1, property_id=100),
                TableVersionHeader(table_vid=1, header_id=1, header_vid=1),
            ]
        )
        base_table.commit()

        pre = get_open_keys_for_tables(base_table, ["T_01.01"], release_id=1)
        post = get_open_keys_for_tables(base_table, ["T_01.01"], release_id=3)
        assert pre == {"T_01.01": {"LES": "s"}}
        assert post == {"T_01.01": {"qLES": "s"}}
