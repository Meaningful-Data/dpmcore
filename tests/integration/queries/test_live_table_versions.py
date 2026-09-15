"""The live-table-version scope on ``ViewDatapointsQuery``.

``live_table_versions=True`` reads a table's *current* version -- open
now and already published -- instead of the version effective at
``release_id``. It is the rule the EBA ``drr_datapoints`` view bakes in
as ``(EndReleaseID IS NULL OR EndReleaseID = 9999) AND StartReleaseID !=
9999``; dpmcore identifies the perpetual release by
``compute_sort_order`` rather than by that literal ID, so the same rule
holds on a database that numbers its working release differently, or has
none at all.

These tests pin the four cases the flag actually changes, plus the
guarantee that it only moves the *table-version* axis: the release
window still scopes which module versions the cells are read through.
"""

from __future__ import annotations

from datetime import date

import pytest

from dpmcore.dpm_xl.model_queries import ViewDatapointsQuery
from dpmcore.dpm_xl.utils.filters import filter_live_only
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import (
    Cell,
    Header,
    HeaderVersion,
    Table,
    TableVersion,
    TableVersionCell,
)
from dpmcore.orm.variables import VariableVersion

OLD = 9001
NEW = 9002
# Numbered like any other release: the perpetual one is recognised by
# its type, not by a 9999 sentinel.
WORKING = 9003


@pytest.fixture(autouse=True)
def _clear_query_caches():
    """The table-data and axis caches are keyed per engine, not per test."""
    yield
    ViewDatapointsQuery._TABLE_DATA_CACHE.clear()
    ViewDatapointsQuery._AXIS_ORDER_CACHE.clear()


def _seed_releases(session, *, with_working=True):
    session.add_all(
        [
            Release(release_id=OLD, code="9.0", date=date(2024, 1, 1)),
            Release(release_id=NEW, code="9.1", date=date(2025, 1, 1)),
        ]
    )
    if with_working:
        session.add(
            Release(
                release_id=WORKING,
                code="Working",
                date=date(1970, 1, 1),
                type="playground",
            )
        )


def _seed_rendering(session):
    """Two open module versions, one row header and one cell, shared by all.

    ``ModuleVersionComposition`` is keyed by ``(ModuleVID, TableID)`` and
    ``ModuleVersion`` is unique on ``(ModuleID, StartReleaseID)``, so two
    versions of the same table need a module of their own each. Both stay
    open for the whole timeline, which keeps the module axis out of the
    way of the table-version assertions.
    """
    session.add(Framework(framework_id=1, code="FW"))
    for module_id, module_vid in ((1, 10), (2, 11)):
        session.add(Module(module_id=module_id, framework_id=1))
        session.add(
            ModuleVersion(
                module_vid=module_vid,
                module_id=module_id,
                code=f"M{module_id}",
                start_release_id=OLD,
                end_release_id=None,
            )
        )
    session.add(Table(table_id=1))
    session.add(Header(header_id=1, direction="Y", is_key=True))
    session.add(HeaderVersion(header_vid=10, header_id=1, code="0010"))
    session.add(Cell(cell_id=900, table_id=1, row_id=1))


def _seed_table_version(
    session, *, table_vid, code, start, end, module_vid=10
):
    """A table version whose single cell identifies it by variable id."""
    session.add(
        TableVersion(
            table_vid=table_vid,
            table_id=1,
            code=code,
            start_release_id=start,
            end_release_id=end,
        )
    )
    session.add(
        ModuleVersionComposition(
            module_vid=module_vid, table_vid=table_vid, table_id=1
        )
    )
    session.add(
        VariableVersion(
            variable_vid=table_vid * 10,
            variable_id=table_vid,
            code=f"V{table_vid}",
        )
    )
    session.add(
        TableVersionCell(
            table_vid=table_vid,
            cell_id=900,
            cell_code=f"{{{code}, r0010}}",
            variable_vid=table_vid * 10,
            is_nullable=True,
            is_void=False,
            is_excluded=False,
        )
    )


def _variable_ids(data):
    return sorted(data["variable_id"].dropna().astype(int).unique().tolist())


class TestDraftTableVersions:
    def test_a_draft_only_table_is_excluded(self, memory_session):
        """A table introduced in the working release is not published yet."""
        session = memory_session
        _seed_releases(session)
        _seed_rendering(session)
        _seed_table_version(
            session, table_vid=201, code="T_DRAFT", start=WORKING, end=None
        )
        session.commit()

        assert _variable_ids(
            ViewDatapointsQuery.get_table_data(session, "T_DRAFT")
        ) == [201]
        assert (
            ViewDatapointsQuery.get_table_data(
                session, "T_DRAFT", live_table_versions=True
            ).empty
            is True
        )

    def test_a_draft_alongside_a_published_version_is_excluded(
        self, memory_session
    ):
        session = memory_session
        _seed_releases(session)
        _seed_rendering(session)
        _seed_table_version(
            session, table_vid=202, code="T_BOTH", start=OLD, end=None
        )
        _seed_table_version(
            session,
            table_vid=203,
            code="T_BOTH",
            start=WORKING,
            end=None,
            module_vid=11,
        )
        session.commit()

        data = ViewDatapointsQuery.get_table_data(
            session, "T_BOTH", live_table_versions=True
        )

        assert _variable_ids(data) == [202]

    def test_the_working_release_itself_sees_no_draft(self, memory_session):
        """Asking at the working release still reports the published state."""
        session = memory_session
        _seed_releases(session)
        _seed_rendering(session)
        _seed_table_version(
            session, table_vid=204, code="T_AT_WORKING", start=OLD, end=None
        )
        _seed_table_version(
            session,
            table_vid=205,
            code="T_AT_WORKING",
            start=WORKING,
            end=None,
            module_vid=11,
        )
        session.commit()

        data = ViewDatapointsQuery.get_table_data(
            session,
            "T_AT_WORKING",
            release_id=WORKING,
            live_table_versions=True,
        )

        assert _variable_ids(data) == [204]


class TestSupersededTableVersions:
    def test_a_closed_version_is_not_read_at_its_own_release(
        self, memory_session
    ):
        """The live scope ignores the requested release on the table axis."""
        session = memory_session
        _seed_releases(session)
        _seed_rendering(session)
        _seed_table_version(
            session, table_vid=301, code="T_SUPERSEDED", start=OLD, end=NEW
        )
        _seed_table_version(
            session,
            table_vid=302,
            code="T_SUPERSEDED",
            start=NEW,
            end=None,
            module_vid=11,
        )
        session.commit()

        at_old = ViewDatapointsQuery.get_table_data(
            session, "T_SUPERSEDED", release_id=OLD
        )
        live = ViewDatapointsQuery.get_table_data(
            session,
            "T_SUPERSEDED",
            release_id=OLD,
            live_table_versions=True,
        )

        assert _variable_ids(at_old) == [301]
        assert _variable_ids(live) == [302]

    def test_filtered_datapoints_scope_without_a_release(self, memory_session):
        """``get_filtered_datapoints`` scopes the table even with no release."""
        session = memory_session
        _seed_releases(session)
        _seed_rendering(session)
        _seed_table_version(
            session, table_vid=303, code="T_FILTERED", start=WORKING, end=None
        )
        _seed_table_version(
            session,
            table_vid=304,
            code="T_FILTERED",
            start=OLD,
            end=None,
            module_vid=11,
        )
        session.commit()

        table_info = {"rows": ["0010"], "cols": None, "sheets": None}
        unscoped = ViewDatapointsQuery.get_filtered_datapoints(
            session, "T_FILTERED", table_info
        )
        live = ViewDatapointsQuery.get_filtered_datapoints(
            session, "T_FILTERED", table_info, live_table_versions=True
        )

        assert _variable_ids(unscoped) == [303, 304]
        assert _variable_ids(live) == [304]


class TestModuleScopingIsUnaffected:
    def test_the_release_window_still_scopes_the_module_versions(
        self, memory_session
    ):
        """A module version closed before the release contributes no cells."""
        session = memory_session
        _seed_releases(session)
        _seed_rendering(session)
        session.query(ModuleVersion).update(
            {ModuleVersion.end_release_id: NEW}
        )
        _seed_table_version(
            session, table_vid=401, code="T_MODULE_SCOPE", start=OLD, end=None
        )
        session.commit()

        at_old = ViewDatapointsQuery.get_table_data(
            session,
            "T_MODULE_SCOPE",
            release_id=OLD,
            live_table_versions=True,
        )
        at_new = ViewDatapointsQuery.get_table_data(
            session,
            "T_MODULE_SCOPE",
            release_id=NEW,
            live_table_versions=True,
        )

        assert _variable_ids(at_old) == [401]
        assert at_new.empty


class TestFilterLiveOnly:
    def test_without_a_perpetual_release_only_the_end_filter_applies(
        self, memory_session
    ):
        """Every release is dated: nothing can be a draft."""
        session = memory_session
        _seed_releases(session, with_working=False)
        _seed_rendering(session)
        _seed_table_version(
            session, table_vid=501, code="T_NO_WORKING", start=OLD, end=NEW
        )
        _seed_table_version(
            session,
            table_vid=502,
            code="T_NO_WORKING",
            start=NEW,
            end=None,
            module_vid=11,
        )
        session.commit()

        query = filter_live_only(
            session.query(TableVersion.table_vid).filter(
                TableVersion.code == "T_NO_WORKING"
            ),
            TableVersion.start_release_id,
            TableVersion.end_release_id,
        )

        assert [row.table_vid for row in query.all()] == [502]

    def test_a_null_start_release_counts_as_published(self, memory_session):
        """``NULL`` means "has always existed", not "unpublished"."""
        session = memory_session
        _seed_releases(session)
        _seed_rendering(session)
        _seed_table_version(
            session, table_vid=503, code="T_NULL_START", start=None, end=None
        )
        session.commit()

        query = filter_live_only(
            session.query(TableVersion.table_vid).filter(
                TableVersion.code == "T_NULL_START"
            ),
            TableVersion.start_release_id,
            TableVersion.end_release_id,
        )

        assert [row.table_vid for row in query.all()] == [503]

    def test_a_core_select_is_rejected(self, memory_session):
        from sqlalchemy import select

        with pytest.raises(TypeError, match="session-bound"):
            filter_live_only(
                select(TableVersion.table_vid),
                TableVersion.start_release_id,
                TableVersion.end_release_id,
            )
