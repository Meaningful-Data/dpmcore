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
# Validations active for DORA at a release covered only by the ghost.
_VALIDATIONS_AT_GHOST_RELEASE = 67
_ALL_RELEASES = ("3.4", "3.5", "4.0", "4.1", "4.2", "4.2.1")


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
    assert (_NO_FALLBACK_MODULE, "1.0.0") in _ghost_pairs(fixture_session), (
        f"fixture: {_NO_FALLBACK_MODULE} 1.0.0 is no longer a ghost, so this "
        f"no longer covers the 'nothing prior to stand in for it' branch"
    )

    targets = ASTGeneratorService(fixture_session).list_module_versions(
        module_code=_NO_FALLBACK_MODULE, release="4.2"
    )

    assert targets == []


def test_module_scoped_sweep_matches_the_all_modules_slice(fixture_session):
    """``--module-code`` and ``--all-modules`` must agree on the target.

    Checked for *every* code in the dictionary at every release, not just
    a module that happens to substitute: the case that broke was a module
    renamed across versions (``REM_BM`` -> ``REM_BM_CI``), where the
    scoped call answered with the predecessor's code -- a pair absent
    from the all-modules result, so a spot check on one module could not
    see it.
    """
    service = ASTGeneratorService(fixture_session)
    every_code = {
        r.Code
        for r in fixture_session.execute(
            text("SELECT DISTINCT Code FROM ModuleVersion")
        ).fetchall()
    }
    assert len(every_code) > 1

    for release in _ALL_RELEASES:
        everything = set(service.list_module_versions(release=release))
        for code in every_code:
            scoped = set(
                service.list_module_versions(module_code=code, release=release)
            )
            assert scoped == {p for p in everything if p[0] == code}, (
                f"{code} at {release}"
            )


def test_renamed_module_does_not_answer_with_its_old_code(fixture_session):
    """A rename must not make the fallback leak out under the new name.

    ``REM_BM_CI`` 2.2.0 starts at 4.2; at 4.0 the module is still named
    ``REM_BM`` and its only covering version is a ghost. Resolving the
    requested code to a *module* and returning that module's fallback
    answered the request with ``('REM_BM', '2.0.0')``.
    """
    service = ASTGeneratorService(fixture_session)

    for code, release in (
        ("REM_BM_CI", "4.0"),
        ("REM_HE_CI", "4.0"),
        ("REM_GAP_CI", "4.0"),
        ("RESOL1", "4.0"),
        ("CODIS", "4.0"),
        ("REM_BM_CI", "4.1"),
    ):
        targets = service.list_module_versions(
            module_code=code, release=release
        )

        assert targets == [], f"{code} at {release}"


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

    # Subset, not intersection: the bug was that the fallback scripted to
    # 30 of the 67 validations active at 4.2, which a non-empty
    # intersection would also have satisfied.
    assert ghost_only <= codes
    assert len(codes) == _VALIDATIONS_AT_GHOST_RELEASE


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


def test_default_release_matches_the_explicit_one(fixture_session):
    """Both entry points must agree on where the window ends.

    ``_resolve_explicit_release`` accepts 4.2 for DORA 1.1.0 because the
    version stands in for the ghost there (#221), but
    ``_latest_release_in_window`` read the raw ``EndReleaseID``, so
    omitting the release picked 4.1 and silently returned the narrower
    pre-#372 script.
    """
    service = ASTGeneratorService(fixture_session)

    default_codes, _ = _script_codes(service, _FALLBACK, None)
    explicit_codes, _ = _script_codes(service, _FALLBACK, _GHOST_RELEASES[-1])

    assert default_codes == explicit_codes
    assert len(default_codes) == _VALIDATIONS_AT_GHOST_RELEASE
