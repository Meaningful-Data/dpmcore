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
from dpmcore.services.data_dictionary import DataDictionaryService
from dpmcore.services.hierarchy import HierarchyService

# --------------------------------------------------------------------- #
# compute_sort_order / resolve_sort_order
# --------------------------------------------------------------------- #


def test_compute_sort_order_from_date() -> None:
    assert compute_sort_order(None) is None
    assert compute_sort_order(date(2025, 3, 4)) == date(2025, 3, 4).toordinal()
    # Earlier date sorts before a later one.
    assert compute_sort_order(date(2024, 1, 1)) < compute_sort_order(
        date(2024, 6, 1)
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
    orders = [compute_sort_order(d) for d in dates]
    assert orders == sorted(orders)
    # Distinct dates → distinct keys, so no tiebreak is ever needed.
    assert len(set(orders)) == len(orders)


def test_resolve_sort_order_raises_for_undated_and_unknown(memory_session):
    """resolve_sort_order raises on a missing date or an unknown id."""
    session = memory_session
    session.add(Release(release_id=1, code="4.2", date=None))
    session.commit()

    with pytest.raises(ValueError, match="has no date"):
        resolve_sort_order(session, 1)
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
