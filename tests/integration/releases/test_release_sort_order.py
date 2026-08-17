"""Tests for date-based release range comparison.

DPM ``ReleaseID`` values are no longer monotonic (4.2.1 has
``ReleaseID = 1010000003`` while older releases are still 1..5), so
range filters must compare against a ``Release.date``-based sort order
rather than against the raw integer ID.

The headline scenario is a *backport*: a ``4.0.1`` release that carries
a high ``ReleaseID`` (assigned after ``4.2.1``) but a date that follows
its ``4.0`` lineage. Ordering by date places it correctly; ordering by
id would not. Ordering never parses ``Release.code``, so non-versioned
codes (``"Playground"``) and four-segment codes (``4.2.1.3``) order the
same way — the regression that motivated issue #185.
"""

from datetime import date

import pytest

from dpmcore.orm.glossary import (
    Category,
    Item,
    ItemCategory,
)
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.operations import Operation, OperationVersion
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.release_sort_order import (
    compute_sort_order,
    resolve_sort_order,
)
from dpmcore.orm.rendering import Table, TableVersion
from dpmcore.orm.variables import Variable, VariableVersion
from dpmcore.services.data_dictionary import DataDictionaryService
from dpmcore.services.hierarchy import HierarchyService

# --------------------------------------------------------------------- #
# compute_sort_order / resolve_sort_order
# --------------------------------------------------------------------- #


def test_compute_sort_order_from_date() -> None:
    assert (
        compute_sort_order(date(2025, 3, 4), None)
        == date(2025, 3, 4).toordinal()
    )
    # Earlier date sorts before a later one.
    assert compute_sort_order(date(2024, 1, 1), None) < compute_sort_order(
        date(2024, 6, 1), None
    )
    # An undated (unpublished) release sorts after every real date.
    assert compute_sort_order(None, None) > compute_sort_order(
        date(9999, 12, 31), None
    )


def test_compute_sort_order_is_monotone_in_date() -> None:
    """Chronological dates map to strictly increasing sort orders."""
    dates = [
        date(2024, 2, 6),
        date(2024, 7, 11),
        date(2024, 12, 19),
        date(2025, 2, 1),  # a backport, published within the 4.0 lineage
        date(2025, 4, 28),
        date(2025, 10, 31),
        date(2026, 2, 15),
    ]
    orders = [compute_sort_order(d, None) for d in dates]
    assert orders == sorted(orders)
    # Distinct dates → distinct keys, so no tiebreak is ever needed.
    assert len(set(orders)) == len(orders)


def test_resolve_sort_order_undated_is_latest_unknown_raises(memory_session):
    """resolve_sort_order ranks an undated release as the latest.

    An undated (unpublished) release resolves to the "latest" sentinel,
    sorting after every dated release; only a genuinely unknown id (no
    Release row) raises.
    """
    session = memory_session
    session.add(Release(release_id=1, code="4.2", date=date(2025, 10, 31)))
    session.add(Release(release_id=2, code="Playground", date=None))
    session.commit()

    assert resolve_sort_order(session, 2) > resolve_sort_order(session, 1)
    with pytest.raises(ValueError, match="no Release row matches"):
        resolve_sort_order(session, 999)


def test_load_release_sort_orders_from_date() -> None:
    """``load_release_sort_orders`` derives order from ``Release.date``."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from dpmcore.orm import Base
    from dpmcore.orm.release_sort_order import load_release_sort_orders

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Release(release_id=1, code="4.2", date=date(2025, 10, 31)))
        session.add(
            Release(
                release_id=1010000003,
                code="4.2.1",
                date=date(2026, 2, 15),
            ),
        )
        session.commit()
        rows = load_release_sort_orders(session)
    # 4.2 (Oct 2025) must sort before 4.2.1 (Feb 2026), despite the huge id.
    assert rows[1] is not None
    assert rows[1010000003] is not None
    assert rows[1] < rows[1010000003]


# --------------------------------------------------------------------- #
# Backport scenario — high id, in-lineage date
# --------------------------------------------------------------------- #


@pytest.fixture
def backport_session(memory_session):
    """A DB where 4.0.1 has a higher ID than 4.2.1 but an in-lineage date.

    Layout::

        ReleaseID  Code    Date         (id vs lineage)
        --------   -----   ----------   ------------
        1          3.4     2024-02-06
        2          3.5     2024-07-11
        3          4.0     2024-12-19
        4          4.1     2025-04-28
        5          4.2     2025-10-31
        1010000003 4.2.1   2026-02-15
        1010000004 4.0.1   2025-02-01   <- highest id, date within 4.0 lineage

    A module version valid from ``4.0`` to ``4.2`` (start_release_id=3,
    end_release_id=5) should be considered valid at ``4.0.1`` because
    4.0.1's date (2025-02-01) falls in [4.0, 4.2). ID-based comparison
    says no (1010000004 > 5); date-based comparison says yes.
    """
    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="3.4", date=date(2024, 2, 6)),
            Release(release_id=2, code="3.5", date=date(2024, 7, 11)),
            Release(release_id=3, code="4.0", date=date(2024, 12, 19)),
            Release(release_id=4, code="4.1", date=date(2025, 4, 28)),
            Release(release_id=5, code="4.2", date=date(2025, 10, 31)),
            Release(
                release_id=1010000003,
                code="4.2.1",
                date=date(2026, 2, 15),
            ),
            Release(
                release_id=1010000004,
                code="4.0.1",
                date=date(2025, 2, 1),
            ),
            Framework(framework_id=1, code="FW"),
            Module(module_id=1, framework_id=1),
            # MV valid on 4.0..4.2 (i.e. spans the backport target).
            ModuleVersion(
                module_vid=10,
                module_id=1,
                code="MV1",
                start_release_id=3,
                end_release_id=5,
            ),
            Table(table_id=100),
            TableVersion(
                table_vid=1000,
                table_id=100,
                code="T1",
                start_release_id=3,
                end_release_id=5,
            ),
            ModuleVersionComposition(
                module_vid=10, table_vid=1000, table_id=100
            ),
        ]
    )
    session.commit()
    return session


def test_backport_release_includes_module_in_lineage(backport_session):
    """A 4.0..4.2 ModuleVersion is valid at the 4.0.1 backport."""
    svc = HierarchyService(backport_session)

    deep = svc.get_all_frameworks(deep=True, release_code="4.0.1")
    fws = [fw for fw in deep if fw["code"] == "FW"]
    assert len(fws) == 1
    mv_codes = {mv["code"] for mv in fws[0]["module_versions"]}
    assert mv_codes == {"MV1"}, (
        "MV with start=4.0 / end=4.2 must include the 4.0.1 backport"
    )


def test_backport_release_excludes_post_4_2(backport_session):
    """A 4.0..4.2 ModuleVersion is NOT valid at 4.2.1.

    Sanity check that the inclusive/exclusive end-bound logic still
    rejects releases beyond the lineage.
    """
    svc = HierarchyService(backport_session)
    deep = svc.get_all_frameworks(deep=True, release_code="4.2.1")
    fws = [fw for fw in deep if fw["code"] == "FW"]
    if fws:
        mv_codes = {mv["code"] for mv in fws[0]["module_versions"]}
        assert mv_codes == set(), (
            "MV with end=4.2 must NOT match 4.2.1 (end is exclusive)"
        )
    # Otherwise framework was filtered out entirely — also acceptable.


def test_backport_release_excludes_pre_4_0(backport_session):
    """A 4.0..4.2 ModuleVersion is NOT valid at 3.5."""
    svc = HierarchyService(backport_session)
    deep = svc.get_all_frameworks(deep=True, release_code="3.5")
    fws = [fw for fw in deep if fw["code"] == "FW"]
    if fws:
        mv_codes = {mv["code"] for mv in fws[0]["module_versions"]}
        assert mv_codes == set()


# --------------------------------------------------------------------- #
# filter_by_release helper level
# --------------------------------------------------------------------- #


def test_get_tables_at_backport_release(backport_session):
    """DataDictionary.get_tables filters TableVersions by date-version."""
    svc = DataDictionaryService(backport_session)
    tables = svc.get_tables(release_code="4.0.1")
    assert "T1" in tables, (
        "TableVersion(start=4.0, end=4.2) must include the 4.0.1 backport"
    )


def test_nonsemver_release_code_orders_by_date(memory_session):
    """A non-versioned working release (``"Playground"``) orders by date.

    Regression for issue #185: exporting/scoping at a release whose code
    is not ``MAJOR.MINOR[.PATCH]`` used to crash. With date ordering the
    code is never parsed — a "Playground" release published last simply
    resolves to the current rows, with no special-casing and no crash.
    """
    from dpmcore.dpm_xl.utils.filters import filter_by_release

    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(release_id=9999, code="Playground", date=date(2026, 9, 1)),
            # Live from 4.2, never ended -> active at Playground.
            TableVersion(
                table_vid=1,
                table_id=1,
                start_release_id=1,
                end_release_id=None,
            ),
            # Ended at 4.2 -> superseded before Playground.
            TableVersion(
                table_vid=2, table_id=2, start_release_id=1, end_release_id=1
            ),
        ]
    )
    session.commit()

    q = session.query(TableVersion)
    filtered = filter_by_release(
        q,
        start_col=TableVersion.start_release_id,
        end_col=TableVersion.end_release_id,
        release_id=9999,
    )
    vids = {tv.table_vid for tv in filtered.all()}
    assert vids == {1}, "Playground (latest date) yields the current rows"


def test_four_segment_release_orders_by_date(memory_session):
    """A four-segment EBA code (``4.2.1.3``) range-filters its lineage.

    Regression for the CODIS export at release ``4.2.1.3``: the code has
    too many segments to parse as semver, but date ordering never parses
    it, so it behaves as a real release sitting just after ``4.2.1``.
    """
    from dpmcore.dpm_xl.utils.filters import filter_by_release

    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(release_id=2, code="4.2.1", date=date(2026, 2, 15)),
            Release(release_id=3, code="4.2.1.3", date=date(2026, 6, 11)),
            Release(release_id=4, code="4.3", date=date(2026, 10, 1)),
            # Live from 4.2, never ended -> active at 4.2.1.3.
            TableVersion(
                table_vid=1,
                table_id=1,
                start_release_id=1,
                end_release_id=None,
            ),
            # Window [4.2, 4.3) -> covers 4.2.1.3.
            TableVersion(
                table_vid=2, table_id=2, start_release_id=1, end_release_id=4
            ),
            # Window [4.2, 4.2.1) -> ended before 4.2.1.3.
            TableVersion(
                table_vid=3, table_id=3, start_release_id=1, end_release_id=2
            ),
            # Starts at 4.3 -> after the target.
            TableVersion(
                table_vid=4,
                table_id=4,
                start_release_id=4,
                end_release_id=None,
            ),
        ]
    )
    session.commit()

    q = session.query(TableVersion)
    filtered = filter_by_release(
        q,
        start_col=TableVersion.start_release_id,
        end_col=TableVersion.end_release_id,
        release_id=3,
    )
    vids = {tv.table_vid for tv in filtered.all()}
    assert vids == {1, 2}, (
        "4.2.1.3 range-filters its lineage: includes rows live across it, "
        "excludes rows that ended before it or start after it"
    )


def test_unknown_release_id_still_raises(memory_session):
    """An unknown release_id (no Release row) still raises loudly."""
    from dpmcore.dpm_xl.utils.filters import filter_by_release

    session = memory_session
    q = session.query(TableVersion)
    with pytest.raises(ValueError, match="no Release row matches"):
        filter_by_release(
            q,
            start_col=TableVersion.start_release_id,
            end_col=TableVersion.end_release_id,
            release_id=424242,
        )


# --------------------------------------------------------------------- #
# filter_item_version (IN-list expanded from date-based sort order)
# --------------------------------------------------------------------- #


def test_filter_item_version_handles_backport(backport_session):
    """ItemCategory range filter pulls in the right metadata for a backport.

    The query joins TableVersion to ItemCategory using
    ``filter_item_version`` — the JOIN condition expands into
    ``release_id IN (...)`` lists built from the date-based sort order of
    each release's ``date``. An ItemCategory valid 4.0..4.2 (FK start=3
    end=5) must match a TableVersion at the 4.0.1 backport.
    """
    session = backport_session
    session.add(Category(category_id=1, code="C1"))
    session.add(Item(item_id=42, name="Property name"))
    session.add(
        ItemCategory(
            item_id=42,
            start_release_id=3,
            end_release_id=5,
            category_id=1,
            signature="prop:42",
        ),
    )
    # Add a TableVersion specifically at the 4.0.1 backport, on a
    # fresh Table so it can be composed under the same MV.
    session.add(Table(table_id=200))
    session.add(
        TableVersion(
            table_vid=2000,
            table_id=200,
            code="T_BACKPORT",
            start_release_id=1010000004,
            end_release_id=None,
        ),
    )
    session.commit()

    # Use the get_table_modelling pipeline which uses filter_item_version.
    # Need TableVersionHeader + HeaderVersion linking property_id=42.
    from dpmcore.orm.rendering import Header, HeaderVersion, TableVersionHeader

    session.add(Header(header_id=99))
    session.add(
        HeaderVersion(
            header_vid=999,
            header_id=99,
            code="H",
            property_id=42,
        )
    )
    session.add(
        TableVersionHeader(
            table_vid=2000, header_vid=999, header_id=99, order=1
        )
    )
    session.add(
        ModuleVersionComposition(module_vid=10, table_vid=2000, table_id=200)
    )
    session.commit()

    svc = HierarchyService(session)
    modelling = svc.get_table_modelling("T_BACKPORT", release_code="4.0.1")
    main_entries = [
        e
        for entries in modelling.values()
        for e in entries
        if "main_property_code" in e
    ]
    assert any(
        e.get("main_property_code") == "prop:42" for e in main_entries
    ), (
        "ItemCategory valid 4.0..4.2 must match a TableVersion at the "
        "4.0.1 backport via filter_item_version's IN-list filter."
    )


# --------------------------------------------------------------------- #
# get_last_release — latest by date, not by opaque id
# --------------------------------------------------------------------- #


def test_get_last_release_orders_by_date_not_id(memory_session):
    """``get_last_release`` returns the latest release by date, not max id.

    Regression for the non-monotonic ``ReleaseID`` scheme: the backport
    ``4.0.1`` carries the highest id (``1010000004``) but an in-lineage
    date, so ``max(release_id)`` would wrongly pick it as "latest". The
    true latest by date is ``4.2.1``.
    """
    from dpmcore.dpm_xl.model_queries import ModuleVersionQuery

    session = memory_session
    session.add_all(
        [
            Release(release_id=5, code="4.2", date=date(2025, 10, 31)),
            Release(
                release_id=1010000003,
                code="4.2.1",
                date=date(2026, 2, 15),
            ),
            Release(
                release_id=1010000004,
                code="4.0.1",
                date=date(2025, 2, 1),
            ),
        ]
    )
    session.commit()

    assert ModuleVersionQuery.get_last_release(session) == 1010000003


def test_get_last_release_undated_release_is_latest(memory_session):
    """An undated (unpublished) release is the latest, beating dated ones."""
    from dpmcore.dpm_xl.model_queries import ModuleVersionQuery

    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(release_id=2, code="4.2.1", date=date(2026, 2, 15)),
            Release(release_id=9999, code="Playground", date=None),
        ]
    )
    session.commit()

    assert ModuleVersionQuery.get_last_release(session) == 9999


def test_get_last_release_none_when_no_releases(memory_session):
    """``get_last_release`` returns ``None`` when there are no releases."""
    from dpmcore.dpm_xl.model_queries import ModuleVersionQuery

    assert ModuleVersionQuery.get_last_release(memory_session) is None


def test_undated_release_resolves_to_current_rows(memory_session):
    """An undated working release range-filters to the current rows.

    The real issue #185 scenario: an unpublished "Playground" release
    with no date. It ranks as the latest, so ``filter_by_release`` at it
    keeps rows live from the last dated release and drops those already
    superseded — with no code parsing and no crash.
    """
    from dpmcore.dpm_xl.utils.filters import filter_by_release

    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(release_id=9999, code="Playground", date=None),
            # Live from 4.2, never ended -> active at Playground.
            TableVersion(
                table_vid=1,
                table_id=1,
                start_release_id=1,
                end_release_id=None,
            ),
            # Ended at 4.2 -> superseded before Playground.
            TableVersion(
                table_vid=2, table_id=2, start_release_id=1, end_release_id=1
            ),
        ]
    )
    session.commit()

    q = session.query(TableVersion)
    filtered = filter_by_release(
        q,
        start_col=TableVersion.start_release_id,
        end_col=TableVersion.end_release_id,
        release_id=9999,
    )
    vids = {tv.table_vid for tv in filtered.all()}
    assert vids == {1}, "undated Playground (latest) yields the current rows"


# --------------------------------------------------------------------- #
# Non-chronological release type
# A NOT NULL Release.Date schema marks its perpetual release via Release.Type instead, with an irrelevant placeholder date.
# --------------------------------------------------------------------- #


def test_compute_sort_order_playground_type_ignores_its_date() -> None:
    """A ``"playground"``-typed release sorts latest despite an early date."""
    assert compute_sort_order(
        date(1970, 1, 1), "playground"
    ) == compute_sort_order(None, None)
    assert compute_sort_order(date(1970, 1, 1), "playground") > (
        compute_sort_order(date(2026, 12, 31), None)
    )


def test_resolve_sort_order_playground_type_with_real_date_is_latest(
    memory_session,
):
    """A dated ``"playground"`` release still resolves as the latest."""
    session = memory_session
    session.add(Release(release_id=1, code="4.2", date=date(2025, 10, 31)))
    session.add(
        Release(
            release_id=9999,
            code="Playground",
            date=date(1970, 1, 1),
            type="playground",
        )
    )
    session.commit()

    assert resolve_sort_order(session, 9999) > resolve_sort_order(session, 1)


def test_get_last_release_ignores_dated_playground_type(memory_session):
    """``get_last_release`` is not fooled by a dated ``"playground"`` row."""
    from dpmcore.dpm_xl.model_queries import ModuleVersionQuery

    session = memory_session
    session.add_all(
        [
            Release(
                release_id=9999,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            ),
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(release_id=2, code="4.2.1", date=date(2026, 2, 15)),
        ]
    )
    session.commit()

    assert ModuleVersionQuery.get_last_release(session) == 9999


def test_module_version_open_via_dated_playground_end_release(
    memory_session,
):
    """A ``ModuleVersion`` kept open via a dated ``"playground"`` end."""
    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(release_id=2, code="4.2.1", date=date(2026, 2, 15)),
            Release(
                release_id=9999,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            ),
            Framework(framework_id=1, code="FW"),
            Module(module_id=1, framework_id=1),
            # Open-ended via the dated Playground sentinel, not None.
            ModuleVersion(
                module_vid=10,
                module_id=1,
                code="MV1",
                start_release_id=1,
                end_release_id=9999,
            ),
            Table(table_id=100),
            TableVersion(
                table_vid=1000,
                table_id=100,
                code="T1",
                start_release_id=1,
                end_release_id=9999,
            ),
            ModuleVersionComposition(
                module_vid=10, table_vid=1000, table_id=100
            ),
        ]
    )
    session.commit()

    svc = HierarchyService(session)
    deep = svc.get_all_frameworks(deep=True, release_code="4.2.1")
    fws = [fw for fw in deep if fw["code"] == "FW"]
    assert len(fws) == 1
    mv_codes = {mv["code"] for mv in fws[0]["module_versions"]}
    assert mv_codes == {"MV1"}, (
        "a ModuleVersion open via a dated 'playground' end_release_id "
        "must still cover a real, later release — it must not appear "
        "closed in 1970"
    )


def test_filter_by_release_self_reference_at_playground_type(memory_session):
    """A row ending at Playground is still open when querying AT Playground."""
    from dpmcore.dpm_xl.model_queries import ModuleVersionQuery
    from dpmcore.dpm_xl.utils.filters import filter_by_release

    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(
                release_id=9999,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            ),
            Table(table_id=1),
            TableVersion(
                table_vid=1,
                table_id=1,
                code="T1",
                start_release_id=1,
                end_release_id=9999,
            ),
        ]
    )
    session.commit()

    last_release = ModuleVersionQuery.get_last_release(session)
    assert last_release == 9999

    q = session.query(TableVersion)
    filtered = filter_by_release(
        q,
        start_col=TableVersion.start_release_id,
        end_col=TableVersion.end_release_id,
        release_id=last_release,
    )
    vids = {tv.table_vid for tv in filtered.all()}
    assert vids == {1}, (
        "T1 ends at the perpetual release itself — querying AT that same "
        "release must not treat it as closed"
    )


def test_filter_by_release_self_reference_at_undated_release(memory_session):
    """The same self-reference gap, with a genuinely undated release."""
    from dpmcore.dpm_xl.utils.filters import filter_by_release

    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(release_id=2, code="Playground", date=None),
            TableVersion(
                table_vid=1,
                table_id=1,
                start_release_id=1,
                end_release_id=2,
            ),
        ]
    )
    session.commit()

    q = session.query(TableVersion)
    filtered = filter_by_release(
        q,
        start_col=TableVersion.start_release_id,
        end_col=TableVersion.end_release_id,
        release_id=2,
    )
    vids = {tv.table_vid for tv in filtered.all()}
    assert vids == {1}, (
        "a row ending at an undated release must still be open when "
        "querying AT that same undated release"
    )


def test_filter_item_version_self_reference_at_playground_type(
    memory_session,
):
    """``filter_item_version`` has the same self-reference gap as above."""
    from dpmcore.dpm_xl.utils.filters import filter_item_version
    from dpmcore.orm.release_sort_order import load_release_sort_orders

    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(
                release_id=9999,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            ),
            Item(item_id=42, name="Property name"),
            Category(category_id=1, code="C1"),
            ItemCategory(
                item_id=42,
                start_release_id=1,
                end_release_id=9999,
                category_id=1,
                signature="prop:42",
            ),
        ]
    )
    session.commit()

    sort_orders = load_release_sort_orders(session)
    ref_sort_order = resolve_sort_order(session, 9999)
    assert ref_sort_order == sort_orders[9999]

    q = session.query(ItemCategory).filter(
        filter_item_version(
            sort_orders,
            ref_sort_order,
            ItemCategory.start_release_id,
            ItemCategory.end_release_id,
        )
    )
    item_ids = {ic.item_id for ic in q.all()}
    assert item_ids == {42}, (
        "ItemCategory ends at the perpetual release itself — querying AT "
        "that same release must not treat it as closed"
    )


def test_filter_active_only_dated_playground_end_is_active(memory_session):
    """A row ending at Playground is still "active" with no release given."""
    from dpmcore.dpm_xl.utils.filters import filter_active_only

    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(
                release_id=9999,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            ),
            Table(table_id=1),
            TableVersion(
                table_vid=1,
                table_id=1,
                code="T1",
                start_release_id=1,
                end_release_id=9999,
            ),
        ]
    )
    session.commit()

    q = filter_active_only(
        session.query(TableVersion), TableVersion.end_release_id
    )
    vids = {tv.table_vid for tv in q.all()}
    assert vids == {1}, (
        "T1 ends at the dated Playground sentinel, which never closes, "
        "so it must still count as active"
    )


# --------------------------------------------------------------------- #
# Same self-reference gap in three more call sites: ECB validations
# import, and the AST generator's release-window resolution.
# --------------------------------------------------------------------- #


def test_ecb_valid_release_ids_self_reference_at_playground_type(
    memory_session,
):
    """A validation ending at Playground is valid AT Playground too."""
    from dpmcore.services.ecb_validations_import import (
        EcbValidationsImportService,
    )

    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(
                release_id=9999,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            ),
        ]
    )
    session.commit()

    ids = EcbValidationsImportService._get_valid_release_ids(
        session, start_release_id=1, end_release_id=9999
    )
    assert set(ids) == {1, 9999}, (
        "a validation ending at the perpetual release itself must still "
        "be valid at that same release"
    )


def test_latest_release_in_window_self_reference_at_playground_type(
    memory_session,
):
    """The AST generator resolves Playground itself, not an older release."""
    from dpmcore.services.ast_generator import ASTGeneratorService

    session = memory_session
    mv = ModuleVersion(
        module_vid=10,
        module_id=1,
        code="MV1",
        start_release_id=1,
        end_release_id=9999,
    )
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(
                release_id=9999,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            ),
            Framework(framework_id=1, code="FW"),
            Module(module_id=1, framework_id=1),
            mv,
        ]
    )
    session.commit()

    svc = ASTGeneratorService(session)
    latest = svc._latest_release_in_window(mv)
    assert latest is not None
    assert latest.release_id == 9999, (
        "a module version open via the perpetual release must resolve "
        "to that release, not fall back to an older one"
    )


def test_resolve_explicit_release_self_reference_at_playground_type(
    memory_session,
):
    """Requesting Playground explicitly is not "past the end" at Playground."""
    from dpmcore.services.ast_generator import ASTGeneratorService

    session = memory_session
    mv = ModuleVersion(
        module_vid=10,
        module_id=1,
        code="MV1",
        start_release_id=1,
        end_release_id=9999,
    )
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(
                release_id=9999,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            ),
            Framework(framework_id=1, code="FW"),
            Module(module_id=1, framework_id=1),
            mv,
        ]
    )
    session.commit()

    svc = ASTGeneratorService(session)
    release_row = svc._resolve_explicit_release("Playground", mv, "MOD", "1.0")
    assert release_row.release_id == 9999


# --------------------------------------------------------------------- #
# VariableVersionQuery / ItemCategoryQuery / TableVersionQuery
# release filters must date-order, not numerically compare, release_id
# --------------------------------------------------------------------- #


@pytest.fixture
def non_monotonic_id_session(memory_session):
    """A row started by release ``4.3`` (id ``1010000050``), which is
    chronologically before but numerically larger than the ``9999``
    ``Playground`` sentinel. Eexposes a raw numeric ``<=`` comparison.
    """
    session = memory_session
    session.add_all(
        [
            Release(release_id=1, code="4.2", date=date(2025, 10, 31)),
            Release(release_id=1010000050, code="4.3", date=date(2026, 6, 28)),
            Release(
                release_id=9999,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            ),
            Variable(variable_id=1),
            VariableVersion(
                variable_id=1,
                variable_vid=1,
                code="W_04.10",
                start_release_id=1010000050,
                end_release_id=None,
            ),
            ItemCategory(
                item_id=1,
                signature="eba_qEH:qx2005",
                code="qx2005",
                category_id=1,
                start_release_id=1010000050,
                end_release_id=None,
            ),
            Table(table_id=1),
            TableVersion(
                table_vid=1,
                table_id=1,
                code="F_20.04",
                start_release_id=1010000050,
                end_release_id=None,
            ),
            Operation(operation_id=1, code="OP_1"),
            OperationVersion(
                operation_vid=1,
                operation_id=1,
                expression="1 + 1",
                start_release_id=1010000050,
                end_release_id=None,
            ),
        ]
    )
    session.commit()
    return session


def test_check_variable_exists_finds_row_introduced_after_playground_id(
    non_monotonic_id_session,
):
    from dpmcore.dpm_xl.model_queries import VariableVersionQuery

    session = non_monotonic_id_session
    assert (
        VariableVersionQuery.check_variable_exists(session, "W_04.10", 9999)
        is True
    )
    assert (
        VariableVersionQuery.check_variable_exists(
            session, "W_04.10", 1010000050
        )
        is True
    )


def test_get_variable_id_finds_row_introduced_after_playground_id(
    non_monotonic_id_session,
):
    from dpmcore.dpm_xl.model_queries import VariableVersionQuery

    session = non_monotonic_id_session
    assert VariableVersionQuery.get_variable_id(session, "W_04.10", 9999) == [
        1
    ]


def test_get_items_finds_row_introduced_after_playground_id(
    non_monotonic_id_session,
):
    from dpmcore.dpm_xl.model_queries import ItemCategoryQuery

    session = non_monotonic_id_session
    df = ItemCategoryQuery.get_items(session, ["eba_qEH:qx2005"], 9999)
    assert list(df["Signature"]) == ["eba_qEH:qx2005"]


def test_check_table_exists_finds_row_introduced_after_playground_id(
    non_monotonic_id_session,
):
    from dpmcore.dpm_xl.model_queries import TableVersionQuery

    session = non_monotonic_id_session
    assert (
        TableVersionQuery.check_table_exists(session, "F_20.04", 9999) is True
    )


def test_check_table_exists_unknown_release_id_returns_false(
    non_monotonic_id_session,
):
    from dpmcore.dpm_xl.model_queries import TableVersionQuery

    session = non_monotonic_id_session
    assert (
        TableVersionQuery.check_table_exists(session, "F_20.04", 424242)
        is False
    )


def test_get_variable_vids_by_codes_finds_row_introduced_after_playground_id(
    non_monotonic_id_session,
):
    from dpmcore.dpm_xl.model_queries import VariableVersionQuery

    session = non_monotonic_id_session
    resolved = VariableVersionQuery.get_variable_vids_by_codes(
        session, ["W_04.10"], 9999
    )
    assert resolved == {"W_04.10": {"variable_id": 1, "variable_vid": 1}}


def test_get_operations_from_codes_finds_row_introduced_after_playground_id(
    non_monotonic_id_session,
):
    from dpmcore.dpm_xl.model_queries import OperationQuery

    session = non_monotonic_id_session
    df = OperationQuery.get_operations_from_codes(session, ["OP_1"], 9999)
    assert list(df["Code"]) == ["OP_1"]
