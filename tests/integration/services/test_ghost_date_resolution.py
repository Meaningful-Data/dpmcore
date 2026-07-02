"""Pin the date-mode side of issue #182.

The #182 code fix lives on the *release* axis (scope calculation). On the
*reference-date* axis the desired behaviour -- resolve to the module version
that would actually be executed, i.e. the prior non-ghost when the covering
version is a ghost -- already holds without a code change, because a collapsed
window (``from == to``) matches no date under ``from <= date < to`` and the
prior non-ghost's genuine (wide) window already covers the ghost's era.

These tests pin that so a future change to ``filter_by_date`` / the date
branches of ``_apply_module_filter`` cannot silently regress it. Concretely,
FINREP9's ghost ``3.2.0`` claims the instant ``2024-12-31``; the prior
non-ghost ``3.1.0`` (window ``2022-12-31 -> 2026-03-30``) covers it, so a
reference-date lookup for F_01.02 there must resolve to ``3.1.0``'s structure,
never the ghost's and never empty.
"""

from __future__ import annotations

from dpmcore.orm.packaging import ModuleVersion, ModuleVersionComposition
from dpmcore.services.data_dictionary import DataDictionaryService
from dpmcore.services.hierarchy import HierarchyService

# A reporting reference date inside FINREP9's ghost era (3.2.0's collapsed
# instant); the prior non-ghost 3.1.0 covers it.
_GHOST_ERA_DATE = "2024-12-31"


def _module_vid(session, code, version):
    """Return the ``ModuleVID`` for a ``(code, version_number)`` pair."""
    mv = (
        session.query(ModuleVersion)
        .filter(
            ModuleVersion.code == code,
            ModuleVersion.version_number == version,
        )
        .one()
    )
    return mv.module_vid


def _hosts_table_vid(session, module_vid, table_vid):
    """Whether ``module_vid``'s composition contains ``table_vid``."""
    return (
        session.query(ModuleVersionComposition)
        .filter(
            ModuleVersionComposition.module_vid == module_vid,
            ModuleVersionComposition.table_vid == table_vid,
        )
        .first()
        is not None
    )


def test_date_lookup_resolves_to_prior_non_ghost(fixture_session):
    """A ghost-era reference-date lookup lands on the prior non-ghost.

    ``get_table_details('F_01.02', date=<ghost era>)`` must resolve, and the
    table version it returns must belong to the prior non-ghost FINREP9 3.1.0
    -- never the ghost 3.2.0.
    """
    session = fixture_session
    prior = _module_vid(session, "FINREP9", "3.1.0")
    ghost = _module_vid(session, "FINREP9", "3.2.0")

    details = HierarchyService(session).get_table_details(
        "F_01.02", date=_GHOST_ERA_DATE
    )
    assert details is not None, "ghost-era date must resolve, not go empty"

    table_vid = details["table_vid"]
    assert _hosts_table_vid(session, prior, table_vid), (
        "date lookup should resolve to the prior non-ghost's table version"
    )
    assert not _hosts_table_vid(session, ghost, table_vid), (
        "date lookup must not resolve to the ghost's table version"
    )


def test_get_tables_by_date_includes_ghost_era_table(fixture_session):
    """A table hosted only via a ghost era is still listed by date.

    F_01.02 must appear in ``get_tables(date=<ghost era>)`` because the prior
    non-ghost FINREP9 3.1.0 covers that reference date.
    """
    tables = DataDictionaryService(fixture_session).get_tables(
        date=_GHOST_ERA_DATE
    )
    assert "F_01.02" in tables
