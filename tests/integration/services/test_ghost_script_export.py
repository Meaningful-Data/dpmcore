"""Script export honours the ghost-module-version fallback (#372).

The export companion of ``test_ghost_release_resolution`` (#356): scope
resolution substitutes a ghost with the prior non-ghost version, and the
export path now does the same in the two places it did not -- enumerating
a release's sweep targets, and discovering a module version's active
validations.

DORA is the fixture's clean case. Its ``1.2.0`` claims the single instant
``2026-03-31`` while spanning 4.2 onwards, so 4.2 has no non-ghost
covering version and resolves to ``1.1.0``; the validations activated by
4.2 are scoped to the ghost's ``ModuleVID``. FINREP9DP is the other
half: its ghost is the module's first version, so there is nothing to
stand in for it and the module stays out of the release.
"""

from __future__ import annotations

from sqlalchemy import text

from dpmcore.services.ast_generator import ASTGeneratorService

_MODULE = "DORA"
_FALLBACK = "1.1.0"
_GHOST = "1.2.0"
# The releases whose only covering DORA version is the ghost.
_GHOST_RELEASES = ("4.2", "4.2.1")
# A release DORA 1.1.0 covers in its own right.
_OWN_RELEASE = "4.1"
# Ghost with no prior non-ghost version: nothing to fall back to.
_NO_FALLBACK_MODULE = "FINREP9DP"


def _module_vid(session, code, version):
    return session.execute(
        text(
            "SELECT ModuleVID FROM ModuleVersion "
            "WHERE Code = :c AND VersionNumber = :v"
        ),
        {"c": code, "v": version},
    ).scalar()


def _scoped_codes(session, module_vid):
    """Raw-SQL oracle: validation codes actively scoped to a ModuleVID.

    Deliberately not release-filtered -- replicating dpmcore's
    point-release window resolution here would only re-derive the code
    under test. It bounds what a script may contain, not what it must.
    """
    rows = session.execute(
        text(
            """
            SELECT DISTINCT o.Code
            FROM OperationScopeComposition osc
            JOIN OperationScope os
                ON os.OperationScopeID = osc.OperationScopeID
            JOIN OperationVersion ov ON ov.OperationVID = os.OperationVID
            JOIN Operation o ON o.OperationID = ov.OperationID
            WHERE osc.ModuleVID = :mvid
              AND os.IsActive IN (-1, 1)
              AND (o.Code LIKE 'v%' OR o.Code LIKE 'e%')
            """
        ),
        {"mvid": module_vid},
    ).fetchall()
    return {r.Code for r in rows}


def _ghost_pairs(session):
    """Raw-SQL oracle: every ``(code, version)`` with a collapsed window."""
    rows = session.execute(
        text(
            "SELECT Code, VersionNumber FROM ModuleVersion "
            "WHERE FromReferenceDate IS NOT NULL "
            "AND ToReferenceDate IS NOT NULL "
            "AND FromReferenceDate = ToReferenceDate"
        )
    ).fetchall()
    return {(r.Code, r.VersionNumber) for r in rows}


def _script_codes(service, version, release):
    result = service.script_for_module(
        module_code=_MODULE, module_version=version, release=release
    )
    assert result["success"], result.get("error")
    modules = list(result["enriched_ast"].values())
    assert len(modules) == 1, modules
    return set(modules[0]["operations"]), modules[0]["dates"]


def test_sweep_substitutes_the_ghost_fallback(fixture_session):
    """At a ghost-only release the module is swept as its fallback."""
    service = ASTGeneratorService(fixture_session)

    for release in _GHOST_RELEASES:
        targets = set(service.list_module_versions(release=release))
        assert (_MODULE, _FALLBACK) in targets, release
        assert (_MODULE, _GHOST) not in targets, release


def test_sweep_never_surfaces_a_ghost(fixture_session):
    """Substituting a ghost must not smuggle one into the sweep."""
    service = ASTGeneratorService(fixture_session)
    ghosts = _ghost_pairs(fixture_session)
    assert ghosts, "fixture DB has no ghost module versions"

    for release in _GHOST_RELEASES:
        targets = set(service.list_module_versions(release=release))
        assert not targets & ghosts, release


def test_ghost_with_nothing_prior_stays_out(fixture_session):
    """A module whose first version is a ghost has no target (#182)."""
    targets = ASTGeneratorService(fixture_session).list_module_versions(
        module_code=_NO_FALLBACK_MODULE, release="4.2"
    )

    assert targets == []


def test_module_scoped_sweep_matches_the_all_modules_slice(fixture_session):
    """``--module-code`` and ``--all-modules`` must agree on the target."""
    service = ASTGeneratorService(fixture_session)

    everything = set(service.list_module_versions(release="4.2"))
    scoped = set(
        service.list_module_versions(module_code=_MODULE, release="4.2")
    )

    assert scoped == {p for p in everything if p[0] == _MODULE}


def test_fallback_script_reaches_the_ghosts_validations(fixture_session):
    """The fallback's script carries what is scoped to the ghost."""
    session = fixture_session
    ghost_only = _scoped_codes(
        session, _module_vid(session, _MODULE, _GHOST)
    ) - _scoped_codes(session, _module_vid(session, _MODULE, _FALLBACK))
    assert ghost_only, "fixture: the ghost carries no validations of its own"

    codes, _dates = _script_codes(
        ASTGeneratorService(session), _FALLBACK, "4.2"
    )

    assert ghost_only & codes


def test_fallback_script_stays_within_both_scopes(fixture_session):
    """Widening the scope filter must not invent validations."""
    session = fixture_session
    reachable = _scoped_codes(
        session, _module_vid(session, _MODULE, _GHOST)
    ) | _scoped_codes(session, _module_vid(session, _MODULE, _FALLBACK))

    codes, _dates = _script_codes(
        ASTGeneratorService(session), _FALLBACK, "4.2"
    )

    assert codes <= reachable


def test_fallback_script_keeps_a_usable_reporting_window(fixture_session):
    """The whole point of the substitution: dates that span a period.

    Reaching the ghost's validations through the ghost itself emits its
    collapsed single-day window; through the fallback they arrive with
    the fallback's own reporting period.
    """
    codes, dates = _script_codes(
        ASTGeneratorService(fixture_session), _FALLBACK, "4.2"
    )

    assert codes
    assert dates["from"] == "2025-03-31"
    assert dates["to"] != dates["from"]


def test_release_the_version_covers_itself_is_unaffected(fixture_session):
    """No ghost covers 4.1, so nothing is added to DORA 1.1.0's scope."""
    session = fixture_session
    ghost_only = _scoped_codes(
        session, _module_vid(session, _MODULE, _GHOST)
    ) - _scoped_codes(session, _module_vid(session, _MODULE, _FALLBACK))

    codes, _dates = _script_codes(
        ASTGeneratorService(session), _FALLBACK, _OWN_RELEASE
    )

    assert not codes & ghost_only
