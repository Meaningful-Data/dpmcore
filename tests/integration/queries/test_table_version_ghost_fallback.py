"""Ghost-module-version fallback on the table-version axis (issue #356).

The fallback added for issues #182/#151/#221 covered *module* resolution
only: a table version open at a release solely through a ghost module
version (collapsed reference-date window) was still the one datapoints
were read from, so the same release answered "FINREP9 3.1.0" for the
module and "3.2.0's table version" for the cells -- and reported the
variables, properties and domains the ghost introduced.

These tests pin the substitution rule and its three limits: a live
module version is never overridden, and a ghost with nothing to fall back
to (no prior non-ghost version, or one that does not contain the table)
keeps its own table version rather than making the table disappear.
"""

from __future__ import annotations

from datetime import date

from dpmcore.dpm_xl.model_queries import (
    ModuleVersionQuery,
    ViewDatapointsQuery,
)
from dpmcore.dpm_xl.utils.filters import resolve_release_id
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
from dpmcore.services.semantic import SemanticService

# Releases: the ghost's window is [OLD, NEW); the target sits inside it.
OLD = 7001
GHOST_ERA = 7002
NEW = 7003


def _seed_releases(session):
    session.add_all(
        [
            Release(release_id=OLD, code="7.0", date=date(2024, 1, 1)),
            Release(release_id=GHOST_ERA, code="7.1", date=date(2025, 1, 1)),
            Release(release_id=NEW, code="7.2", date=date(2026, 1, 1)),
        ]
    )


def _seed_module_versions(session, *, ghost_only=False):
    """A module with a live version, then a ghost covering ``GHOST_ERA``.

    Args:
        session: SQLAlchemy session.
        ghost_only: When True the live prior version is omitted, so the
            ghost is the module's only version.
    """
    session.add(Framework(framework_id=1, code="FW"))
    session.add(Module(module_id=1, framework_id=1))
    if not ghost_only:
        session.add(
            ModuleVersion(
                module_vid=10,
                module_id=1,
                code="M",
                version_number="1.0.0",
                from_reference_date=date(2023, 12, 31),
                to_reference_date=date(2027, 12, 31),
                start_release_id=OLD,
                end_release_id=GHOST_ERA,
            )
        )
    # Collapsed reference-date window: a ghost.
    session.add(
        ModuleVersion(
            module_vid=11,
            module_id=1,
            code="M",
            version_number="1.1.0",
            from_reference_date=date(2024, 12, 31),
            to_reference_date=date(2024, 12, 31),
            start_release_id=GHOST_ERA,
            end_release_id=NEW,
        )
    )


def _seed_table_version(session, *, table_vid, module_vid, start, end, code):
    """One table version, its single cell and the variable behind it."""
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
    # The variable id is what a caller reads back: distinct per version, so
    # the assertions say which table version answered.
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


def _seed_shared_rendering(session):
    """The row header and cell both table versions map."""
    session.add(Table(table_id=1))
    session.add(Header(header_id=1, direction="Y", is_key=True))
    session.add(HeaderVersion(header_vid=10, header_id=1, code="0010"))
    session.add(Cell(cell_id=900, table_id=1, row_id=1))


def _seed_ghost_supersedes_live(session, code):
    """Live version at ``OLD``, ghost carrying its own table version."""
    _seed_releases(session)
    _seed_module_versions(session)
    _seed_shared_rendering(session)
    _seed_table_version(
        session,
        table_vid=101,
        module_vid=10,
        start=OLD,
        end=GHOST_ERA,
        code=code,
    )
    _seed_table_version(
        session,
        table_vid=102,
        module_vid=11,
        start=GHOST_ERA,
        end=NEW,
        code=code,
    )
    session.commit()


def test_cells_come_from_the_prior_non_ghost_version(memory_session):
    """The ghost's table version is substituted with the live one's."""
    session = memory_session
    _seed_ghost_supersedes_live(session, "T_GHOST_SUB")

    data = ViewDatapointsQuery.get_table_data(
        session, "T_GHOST_SUB", release_id=GHOST_ERA
    )

    assert data["table_vid"].unique().tolist() == [101]
    assert data["variable_id"].tolist() == [101]


def test_datapoints_agree_with_module_resolution(memory_session):
    """The module version behind the cells is the one modules resolve to."""
    session = memory_session
    _seed_ghost_supersedes_live(session, "T_GHOST_AGREE")

    scope = ViewDatapointsQuery._resolve_table_version_scope(
        session, "T_GHOST_AGREE", GHOST_ERA
    )
    modules = ModuleVersionQuery.get_from_table_codes(
        session, ["T_GHOST_AGREE"], GHOST_ERA
    )

    assert scope.table_vids == [101]
    # The fallback's release window ends before GHOST_ERA, so the join has
    # to be narrowed to its VID instead of filtered by release.
    assert scope.fallback_module_vids == [10]
    assert sorted(set(modules["ModuleVID"])) == [10]


def test_filtered_datapoints_use_the_same_fallback(memory_session):
    """``get_filtered_datapoints`` resolves through the same scope."""
    session = memory_session
    _seed_ghost_supersedes_live(session, "T_GHOST_FILTERED")

    data = ViewDatapointsQuery.get_filtered_datapoints(
        session,
        "T_GHOST_FILTERED",
        {"rows": ["0010"], "cols": None, "sheets": None},
        release_id=GHOST_ERA,
    )

    assert data["table_vid"].unique().tolist() == [101]
    assert data["variable_id"].tolist() == [101]


def test_a_live_module_version_is_never_substituted(memory_session):
    """A ghost alongside a live version leaves resolution untouched."""
    session = memory_session
    _seed_releases(session)
    _seed_module_versions(session)
    _seed_shared_rendering(session)
    # The live version runs past the ghost's start, and the table is
    # unchanged between the two, so both compositions point at the same
    # table version -- a live version hosts it and nothing is substituted.
    session.query(ModuleVersion).filter(ModuleVersion.module_vid == 10).update(
        {ModuleVersion.end_release_id: NEW}
    )
    _seed_table_version(
        session,
        table_vid=201,
        module_vid=10,
        start=OLD,
        end=NEW,
        code="T_GHOST_LIVE",
    )
    session.add(
        ModuleVersionComposition(module_vid=11, table_vid=201, table_id=1)
    )
    session.commit()

    scope = ViewDatapointsQuery._resolve_table_version_scope(
        session, "T_GHOST_LIVE", GHOST_ERA
    )

    assert scope.table_vids == [201]
    assert scope.fallback_module_vids is None


def test_ghost_without_a_prior_version_keeps_its_table_version(
    memory_session,
):
    """Nothing to fall back to: the table still resolves, from the ghost."""
    session = memory_session
    _seed_releases(session)
    _seed_module_versions(session, ghost_only=True)
    _seed_shared_rendering(session)
    _seed_table_version(
        session,
        table_vid=301,
        module_vid=11,
        start=GHOST_ERA,
        end=NEW,
        code="T_GHOST_ALONE",
    )
    session.commit()

    scope = ViewDatapointsQuery._resolve_table_version_scope(
        session, "T_GHOST_ALONE", GHOST_ERA
    )
    data = ViewDatapointsQuery.get_table_data(
        session, "T_GHOST_ALONE", release_id=GHOST_ERA
    )

    assert scope.table_vids == [301]
    assert scope.fallback_module_vids is None
    assert data["variable_id"].tolist() == [301]


def test_table_introduced_by_the_ghost_keeps_its_table_version(
    memory_session,
):
    """The prior version exists but has no such table: no substitution."""
    session = memory_session
    _seed_releases(session)
    _seed_module_versions(session)
    _seed_shared_rendering(session)
    # The live version hosts a different table, so the fallback module
    # version has nothing to answer with for this code.
    _seed_table_version(
        session,
        table_vid=401,
        module_vid=10,
        start=OLD,
        end=GHOST_ERA,
        code="T_GHOST_OTHER",
    )
    _seed_table_version(
        session,
        table_vid=402,
        module_vid=11,
        start=GHOST_ERA,
        end=NEW,
        code="T_GHOST_NEW",
    )
    session.commit()

    scope = ViewDatapointsQuery._resolve_table_version_scope(
        session, "T_GHOST_NEW", GHOST_ERA
    )

    assert scope.table_vids == [402]
    assert scope.fallback_module_vids is None


def test_no_release_applies_no_fallback(memory_session):
    """Without a target release there is no "prior" version to pick."""
    session = memory_session
    _seed_ghost_supersedes_live(session, "T_GHOST_NORELEASE")

    scope = ViewDatapointsQuery._resolve_table_version_scope(
        session, "T_GHOST_NORELEASE", None
    )

    assert scope.fallback_module_vids is None


# ------------------------------------------------------------------ #
# The reported case, against the real dictionary
# ------------------------------------------------------------------ #

# F_40.01 belongs to FINREP9, whose 3.2.0 is a ghost spanning 4.0 -> 4.2.
_GHOST_RELEASES = ("4.0", "4.1")
_EXPRESSION = "{tF_40.01, c0095} = [eba_CT:x12]"


def _module_vid(session, code, version):
    return (
        session.query(ModuleVersion.module_vid)
        .filter(
            ModuleVersion.code == code,
            ModuleVersion.version_number == version,
        )
        .one()[0]
    )


def test_finrep9_datapoints_resolve_to_the_prior_non_ghost(fixture_session):
    """F_40.01's cells come from 3.1.0's table version across the ghost."""
    session = fixture_session
    prior = _module_vid(session, "FINREP9", "3.1.0")
    ghost = _module_vid(session, "FINREP9", "3.2.0")
    release_id = resolve_release_id(session, release_code="4.0")

    scope = ViewDatapointsQuery._resolve_table_version_scope(
        session, "F_40.01", release_id
    )
    hosted_by = {
        vid
        for (vid,) in session.query(ModuleVersionComposition.module_vid)
        .filter(ModuleVersionComposition.table_vid.in_(scope.table_vids))
        .distinct()
    }

    assert prior in hosted_by
    assert ghost not in hosted_by
    assert scope.fallback_module_vids == [prior]


def test_domain_warning_only_fires_where_the_retyping_is_real(
    fixture_session,
):
    """``c0095`` takes CT items until 4.2, qSR items from 4.2 on."""
    service = SemanticService(fixture_session)

    for release_code in _GHOST_RELEASES:
        result = service.validate(_EXPRESSION, release_code=release_code)
        assert result.is_valid, result.error_message
        assert result.warning is None, (
            f"{release_code}: the column still takes CT items there"
        )

    retyped = service.validate(_EXPRESSION, release_code="4.2")
    assert retyped.warning is not None
    assert "qSR" in retyped.warning
