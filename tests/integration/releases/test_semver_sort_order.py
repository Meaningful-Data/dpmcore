"""Tests for semver-based release range comparison.

DPM ``ReleaseID`` values are no longer monotonic (4.2.1 has
``ReleaseID = 1010000003`` while older releases are still 1..5), so
range filters must compare against ``Release.sort_order`` (parsed
from semver ``code``) rather than against the raw integer ID.

The headline scenario is a *backport*: a hypothetical ``4.0.1``
published chronologically after ``4.2.1`` but semantically belonging
to the ``4.0`` lineage.

Pre-fix this looked broken in two distinct ways depending on which
ID the backport got, and both are exercised here.
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
    parse_version,
)
from dpmcore.orm.rendering import Table, TableVersion
from dpmcore.services.data_dictionary import DataDictionaryService
from dpmcore.services.hierarchy import HierarchyService

# --------------------------------------------------------------------- #
# parse_version / compute_sort_order
# --------------------------------------------------------------------- #


def test_parse_version_padding() -> None:
    assert parse_version("4.2") == (4, 2, 0)
    assert parse_version("4.2.1") == (4, 2, 1)
    assert parse_version("3") == (3, 0, 0)


def test_parse_version_unparseable_returns_none() -> None:
    assert parse_version(None) is None
    assert parse_version("") is None
    assert parse_version("draft") is None
    assert parse_version("4.2-rc1") is None


def test_compute_sort_order_is_monotone() -> None:
    """If parse_version(a) < parse_version(b) then sort_order(a) < sort_order(b)."""
    samples = [
        "1.0",
        "3.4",
        "3.5",
        "4.0",
        "4.0.1",  # backport
        "4.1",
        "4.2",
        "4.2.1",
        "4.2.10",  # multi-digit segment — lexical comparison would break
    ]
    parsed = [parse_version(s) for s in samples]
    sorts = [compute_sort_order(s) for s in samples]
    pairs = list(zip(parsed, sorts, strict=True))
    assert sorted(pairs) == pairs
    # And specifically: 4.2.10 sorts after 4.2.1 (lexical would say opposite).
    assert compute_sort_order("4.2.10") > compute_sort_order("4.2.1")
    # Backport sits between 4.0 and 4.1.
    assert compute_sort_order("4.0") < compute_sort_order("4.0.1")
    assert compute_sort_order("4.0.1") < compute_sort_order("4.1")


def test_release_sort_order_auto_populated() -> None:
    """The ``before_insert`` listener fills ``sort_order`` from ``code``."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from dpmcore.orm import Base

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
        rows = {r.release_id: r.sort_order for r in session.query(Release)}
    # 4.2 → (4, 2, 0); 4.2.1 → (4, 2, 1) — the latter must compare greater.
    assert rows[1] is not None
    assert rows[1010000003] is not None
    assert rows[1] < rows[1010000003]


# --------------------------------------------------------------------- #
# Backport scenario — the whole reason for this refactor
# --------------------------------------------------------------------- #


@pytest.fixture
def backport_session(memory_session):
    """A DB where 4.0.1 has a higher ID than 4.2.1.

    Layout::

        ReleaseID  Code    Date         (chronology)
        --------   -----   ----------   ------------
        1          3.4     2024-02-06
        2          3.5     2024-07-11
        3          4.0     2024-12-19
        4          4.1     2025-04-28
        5          4.2     2025-10-31
        1010000003 4.2.1   2026-02-15
        1010000004 4.0.1   2026-06-30   <- backport, post-4.2.1 by date

    A module version valid from ``4.0`` to ``4.2`` (start_release_id=3,
    end_release_id=5) should be considered valid at ``4.0.1`` because
    4.0.1 ∈ [4.0, 4.2). ID-based comparison says no (1010000004 > 5);
    code-based comparison says yes.
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
                date=date(2026, 6, 30),
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
    """DataDictionary.get_tables filters TableVersions by code-version."""
    svc = DataDictionaryService(backport_session)
    tables = svc.get_tables(release_code="4.0.1")
    assert "T1" in tables, (
        "TableVersion(start=4.0, end=4.2) must include the 4.0.1 backport"
    )


def test_unparseable_release_code_excluded(memory_session):
    """A Release whose code can't be parsed has no sort_order.

    Filtering against such a release_id raises a clear error rather
    than silently mis-counting rows.
    """
    from dpmcore.dpm_xl.utils.filters import filter_by_release

    session = memory_session
    session.add(Release(release_id=1, code="draft", date=date(2024, 1, 1)))
    session.commit()

    q = session.query(TableVersion)
    with pytest.raises(ValueError, match="could not be parsed"):
        filter_by_release(
            q,
            start_col=TableVersion.start_release_id,
            end_col=TableVersion.end_release_id,
            release_id=1,
        )


# --------------------------------------------------------------------- #
# filter_item_version (per-row sort_order subqueries)
# --------------------------------------------------------------------- #


def test_filter_item_version_handles_backport(backport_session):
    """ItemCategory range filter pulls in the right metadata for a backport.

    The query joins TableVersion to ItemCategory using
    ``filter_item_version`` — the JOIN condition compares
    ``Release.sort_order``. An ItemCategory valid 4.0..4.2 (FK
    start=3 end=5) must match a TableVersion at the 4.0.1 backport.
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
        "4.0.1 backport via filter_item_version's sort_order JOIN."
    )
