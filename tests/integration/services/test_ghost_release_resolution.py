"""The release-axis companion of ``test_ghost_date_resolution`` (#356).

``HierarchyService`` resolves a table version through the module-version
join, so a release whose only covering module version is a ghost used to
answer with the ghost's table version -- while the very same lookup by
reference date answered with the prior non-ghost's. The two axes describe
the same reporting era and must agree.

FINREP9's ghost ``3.2.0`` claims the instant ``2024-12-31`` and spans
releases 4.0 -> 4.2; the prior non-ghost ``3.1.0`` covers that date, and
F_40.01 has a different table version in each.
"""

from __future__ import annotations

from dpmcore.orm.packaging import ModuleVersion, ModuleVersionComposition
from dpmcore.services.hierarchy import HierarchyService

_GHOST_ERA_DATE = "2024-12-31"
_GHOST_RELEASES = ("4.0", "4.1")
_TABLE = "F_40.01"
# A table the ghost introduced: the prior non-ghost does not contain it,
# so there is nothing to fall back to.
_GHOST_ONLY_TABLE = "C_94.02"


def _module_vid(session, code, version):
    """Return the ``ModuleVID`` for a ``(code, version_number)`` pair."""
    return (
        session.query(ModuleVersion.module_vid)
        .filter(
            ModuleVersion.code == code,
            ModuleVersion.version_number == version,
        )
        .one()[0]
    )


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


def test_release_lookup_resolves_to_prior_non_ghost(fixture_session):
    """Across the ghost's releases the table details come from 3.1.0."""
    session = fixture_session
    prior = _module_vid(session, "FINREP9", "3.1.0")
    ghost = _module_vid(session, "FINREP9", "3.2.0")
    service = HierarchyService(session)

    for release_code in _GHOST_RELEASES:
        details = service.get_table_details(_TABLE, release_code=release_code)
        assert details is not None, release_code
        table_vid = details["table_vid"]
        assert _hosts_table_vid(session, prior, table_vid), release_code
        assert not _hosts_table_vid(session, ghost, table_vid), release_code


def test_release_and_date_axes_agree(fixture_session):
    """The ghost era resolves to one table version, whichever axis asks."""
    service = HierarchyService(fixture_session)

    by_release = service.get_table_details(_TABLE, release_code="4.0")
    by_date = service.get_table_details(_TABLE, date=_GHOST_ERA_DATE)

    assert by_release["table_vid"] == by_date["table_vid"]


def test_release_after_the_ghost_keeps_its_own_version(fixture_session):
    """From 4.2 the module version is live again and answers for itself."""
    session = fixture_session
    current = _module_vid(session, "FINREP9", "3.3.0")

    details = HierarchyService(session).get_table_details(
        _TABLE, release_code="4.2"
    )

    assert _hosts_table_vid(session, current, details["table_vid"])


def test_table_introduced_by_a_ghost_still_resolves(fixture_session):
    """With nothing to fall back to the table stays reachable."""
    details = HierarchyService(fixture_session).get_table_details(
        _GHOST_ONLY_TABLE, release_code="4.0"
    )

    assert details is not None
    assert details["code"] == _GHOST_ONLY_TABLE
