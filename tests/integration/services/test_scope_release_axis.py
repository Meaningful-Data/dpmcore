"""Regression tests for issue #151 (release axis) + #182 (ghost fallback).

Rules pinned here, verified against EBA's own pre-calculated
``OperationScope`` / ``OperationScopeComposition`` shipped in the dictionary
(an oracle straight from the data, not hand-built fixtures):

1. **Release axis only.** A module version is in scope for release R purely
   on the release-validity axis (``StartReleaseID``..``EndReleaseID``, compared
   on the date sort order). The old reference-date ``_apply_fallback_for_equal_dates``
   could substitute a version absent from R -- e.g. ``FINREP9DP 1.1.0`` (a 4.2.1
   version) leaking into release 4.2 -- producing an invalid scope and the
   downstream ``Release X predates module version ...`` error a consumer hit.
   The #182 fallback is still bound by this: it only ever reaches *backward*
   (a version whose release window starts on or before R), never forward.

2. **Ghost (single-day) versions are never scoped as-is.** A module version
   whose reference-date window is collapsed (``FromReferenceDate ==
   ToReferenceDate``) describes one reporting date and is never placed in scope.

3. **#182 ghost fallback.** When the only version whose release window covers R
   is a ghost, the scope falls back to the most recent *prior* non-collapsed
   version of the same module (e.g. release 4.0/4.1 for F_01.02 fall back to
   ``FINREP9 3.1.0``). When no such prior version exists -- the ghost is the
   earliest usable version of its module (e.g. ``FINREP9DP 1.0.0`` at 4.2) --
   the release keeps the clean "no module versions found" error (rule 2 wins).

So the release-R oracle is: the operation's persisted versions valid in R by
the release axis and not collapsed, plus -- for a module whose only R-covering
version is a ghost -- that module's latest prior non-collapsed version.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import ModuleVersion
from dpmcore.orm.release_sort_order import compute_sort_order
from dpmcore.services.ast_generator import ASTGeneratorService
from dpmcore.services.scope_calculator import ScopeCalculatorService

# v3898_s references a single table (F_01.02) and has one operation version
# spanning every release, so its persisted scope maps cleanly onto each
# release. Its persisted scope mixes open/range versions (FINREP9 3.1.0/3.3.0,
# FINREP9DP 1.1.0) with collapsed single-day ones (FINREP9 3.2.0, FINREP9DP
# 1.0.0) -- so it exercises both rules in one operation.
_ISSUE_OPERATION = "v3898_s"

# How many real F_01.02 operations the broad invariant sweeps. Each operation
# is scoped against all six releases; kept modest so the test stays brisk.
_INVARIANT_SAMPLE = 15


def _ordered_releases(session):
    """All releases, sorted by date sort order (not the opaque ID)."""
    return sorted(
        session.query(Release).all(),
        key=lambda r: compute_sort_order(r.date) or 0,
    )


def _release_sort_by_id(session):
    """``{release_id: sort_order}`` for window/release-axis comparisons.

    Asserts every release has a date, so ``target_sort`` is always an
    ``int`` downstream: a missing date would otherwise make the oracle
    crash with a ``TypeError`` (``int <= None``) instead of failing clearly.
    """
    sort_by_id = {
        r.release_id: compute_sort_order(r.date)
        for r in session.query(Release).all()
    }
    assert all(v is not None for v in sort_by_id.values()), (
        "fixture has a Release with no date; the oracle assumes every "
        "release has a date to order by"
    )
    return sort_by_id


def _valid_in_release(mv, target_sort, sort_by_id):
    """Whether ``mv``'s release window contains ``target_sort``.

    Faithful mirror of ``filter_by_release`` (``start <= target`` and
    ``(end is open or target < end)`` on the date sort order), including
    its handling of unresolved bounds: a start/end whose release yields no
    sort order (no date or orphan FK) excludes the row, exactly as
    ``release_ids_for_sort_order`` drops ``None`` sort orders from the
    in-lists. Only a NULL ``end_release_id`` is a genuinely open window.
    """
    if mv.start_release_id is None:
        return False
    start = sort_by_id.get(mv.start_release_id)
    if start is None or start > target_sort:
        return False
    if mv.end_release_id is None:
        return True
    end = sort_by_id.get(mv.end_release_id)
    if end is None:
        return False
    return target_sort < end


def _is_collapsed(mv):
    """Whether ``mv``'s reference-date window is a single day (from == to).

    Open-ended windows (``to`` is ``None``) are genuine ranges, not collapsed.
    """
    return (
        mv.from_reference_date is not None
        and mv.to_reference_date is not None
        and mv.from_reference_date == mv.to_reference_date
    )


def _starts_on_or_before(mv, target_sort, sort_by_id):
    """Whether ``mv``'s release window starts on or before ``target_sort``.

    The #182 fallback may return a version whose window ended before R (it
    reaches backward), but it must *never* return one that begins after R --
    that is the #151 guarantee. This is the weakened form of
    :func:`_valid_in_release` used by the invariant sweep.
    """
    if mv.start_release_id is None:
        return False
    start = sort_by_id.get(mv.start_release_id)
    return start is not None and start <= target_sort


def _latest_prior_non_collapsed(module_versions, target_sort, sort_by_id):
    """Oracle mirror of ``_latest_prior_non_collapsed_vids`` for one module.

    Returns the ``ModuleVID`` of the newest non-collapsed version whose
    release-window start sort order is ``<= target_sort`` (strictly backward),
    or ``None`` when the module has no such version.
    """
    best = None  # (start_sort, module_vid)
    for mv in module_versions:
        if _is_collapsed(mv) or mv.start_release_id is None:
            continue
        order = sort_by_id.get(mv.start_release_id)
        if order is None or order > target_sort:
            continue
        if best is None or (order, mv.module_vid) > best:
            best = (order, mv.module_vid)
    return None if best is None else best[1]


def _latest_expression(session, op_code):
    """Return the open (current) operation version's expression text."""
    expr = session.execute(
        text(
            "SELECT ov.Expression FROM OperationVersion ov "
            "JOIN Operation o ON ov.OperationID = o.OperationID "
            "WHERE o.Code = :c AND ov.EndReleaseID IS NULL "
            "ORDER BY ov.OperationVID DESC LIMIT 1"
        ),
        {"c": op_code},
    ).scalar()
    assert expr is not None, f"{op_code} not in fixture DB"
    return expr


def _persisted_module_vids(session, op_code):
    """EBA's persisted scope: every module version hosting the operation."""
    rows = session.execute(
        text(
            "SELECT DISTINCT osc.ModuleVID FROM Operation o "
            "JOIN OperationVersion ov ON ov.OperationID = o.OperationID "
            "JOIN OperationScope os ON os.OperationVID = ov.OperationVID "
            "JOIN OperationScopeComposition osc "
            "  ON osc.OperationScopeID = os.OperationScopeID "
            "WHERE o.Code = :c"
        ),
        {"c": op_code},
    ).all()
    return {r[0] for r in rows}


def _f0102_operation_codes(session, limit):
    """Sample of operations referencing F_01.02 that have persisted scopes."""
    rows = session.execute(
        text(
            "SELECT DISTINCT o.Code FROM Operation o "
            "JOIN OperationVersion ov ON ov.OperationID = o.OperationID "
            "WHERE ov.EndReleaseID IS NULL "
            "  AND ov.Expression LIKE '%tF_01.02%' "
            "  AND EXISTS (SELECT 1 FROM OperationScope os "
            "              WHERE os.OperationVID = ov.OperationVID) "
            "ORDER BY o.Code LIMIT :n"
        ),
        {"n": limit},
    ).all()
    return [r[0] for r in rows]


def test_scope_matches_eba_persisted_scope_per_release(fixture_session):
    """Computed scope == persisted scope per release, with #182 ghost fallback.

    The #151 scenario plus the #182 rule: release 4.2 yields ``FINREP9 3.3.0``
    only -- never the 4.2.1 version ``1.1.0`` (release axis), and the ghost
    ``FINREP9DP 1.0.0`` is dropped with no prior to fall back to. Releases
    4.0/4.1, whose only FINREP9 version (``3.2.0``) is a ghost, now fall back
    to the prior non-collapsed ``FINREP9 3.1.0`` instead of ending up empty.
    """
    session = fixture_session
    expression = _latest_expression(session, _ISSUE_OPERATION)
    persisted = _persisted_module_vids(session, _ISSUE_OPERATION)
    assert persisted, "fixture DB has no persisted scope for the oracle"

    sort_by_id = _release_sort_by_id(session)
    versions = {
        mv.module_vid: mv
        for mv in session.query(ModuleVersion)
        .filter(ModuleVersion.module_vid.in_(persisted))
        .all()
    }
    collapsed = {vid for vid, mv in versions.items() if _is_collapsed(mv)}
    assert collapsed, "oracle should include collapsed versions to exercise"

    # Every module version of every module hosting this operation, so the
    # oracle can reproduce the fallback's backward search across versions EBA
    # never persisted for the operation.
    module_ids = {mv.module_id for mv in versions.values()}
    all_by_module: dict[int, list] = {}
    for mv in (
        session.query(ModuleVersion)
        .filter(ModuleVersion.module_id.in_(module_ids))
        .all()
    ):
        all_by_module.setdefault(mv.module_id, []).append(mv)

    svc = ScopeCalculatorService(session)

    saw_fallback = False
    for rel in _ordered_releases(session):
        target_sort = compute_sort_order(rel.date)
        base = {
            vid
            for vid, mv in versions.items()
            if _valid_in_release(mv, target_sort, sort_by_id)
            and not _is_collapsed(mv)
        }
        base_modules = {versions[v].module_id for v in base}
        # Modules whose only R-covering version is a ghost -> need a fallback.
        ghost_only_modules = {
            mv.module_id
            for mv in versions.values()
            if _valid_in_release(mv, target_sort, sort_by_id)
            and _is_collapsed(mv)
        } - base_modules

        oracle = set(base)
        for module_id in ghost_only_modules:
            cand = _latest_prior_non_collapsed(
                all_by_module.get(module_id, []), target_sort, sort_by_id
            )
            # The resolver re-fetches the fallback version's tables and keeps
            # it only if it still hosts the operation; persisted membership is
            # that guarantee for this single-table operation.
            if cand is not None and cand in persisted:
                oracle.add(cand)
                saw_fallback = True

        result = svc.calculate_from_expression(
            expression=expression, release_code=rel.code
        )
        assert set(result.module_versions) == oracle, (
            f"release {rel.code}: computed "
            f"{sorted(result.module_versions)} != oracle {sorted(oracle)} "
            f"(has_error={result.has_error}, msg={result.error_message})"
        )
        # A ghost (single-day) version must never be selected, in any release.
        assert not (set(result.module_versions) & collapsed)
        if not oracle:
            # No eligible version and no prior -> clean "no modules" error.
            assert result.has_error
            assert "No module versions found" in (result.error_message or "")

    assert saw_fallback, (
        "expected a release (4.0/4.1 for F_01.02) whose only covering version "
        "is a ghost to fall back to a prior non-collapsed version"
    )


def test_scoped_versions_are_backward_only_and_not_single_day(fixture_session):
    """No computed scope returns a forward or single-day version.

    The two invariants, swept across a sample of real F_01.02 operations:
    every module version in a computed scope must (a) start on or before the
    target release on the date sort order (never forward -- the #151
    guarantee, which the #182 fallback must not break; the fallback may reach
    backward past the release window, so full ``start <= release < end``
    validity is not required) and (b) have a non-collapsed reference-date
    window (the #182 fallback always resolves to a genuine version).
    """
    session = fixture_session
    sort_by_id = _release_sort_by_id(session)
    versions = {mv.module_vid: mv for mv in session.query(ModuleVersion).all()}
    svc = ScopeCalculatorService(session)
    releases = _ordered_releases(session)

    codes = _f0102_operation_codes(session, limit=_INVARIANT_SAMPLE)
    assert codes, "fixture DB has no F_01.02 operations with scopes"

    checks = 0
    for code in codes:
        expression = _latest_expression(session, code)
        for rel in releases:
            target_sort = compute_sort_order(rel.date)
            result = svc.calculate_from_expression(
                expression=expression, release_code=rel.code
            )
            if result.has_error:
                continue
            for vid in result.module_versions:
                checks += 1
                mv = versions[vid]
                assert _starts_on_or_before(mv, target_sort, sort_by_id), (
                    f"{code} @ {rel.code}: module version {vid} "
                    f"({mv.code} {mv.version_number}) begins after "
                    f"release {rel.code} (forward selection, #151)"
                )
                assert not _is_collapsed(mv), (
                    f"{code} @ {rel.code}: single-day module version {vid} "
                    f"({mv.code} {mv.version_number}) must not be in scope"
                )

    assert checks, "invariant swept zero module versions"


def test_ghost_only_release_falls_back_to_prior_version(fixture_session):
    """#182 reproduction: F_01.02 @ 4.1 falls back to FINREP9 3.1.0.

    Release 4.1's only covering FINREP9 version is the ghost ``3.2.0`` (VID
    404). Before the fix this errored ``No module versions found``; now it
    resolves to the prior non-collapsed ``3.1.0`` (VID 356) and never the
    ghost.
    """
    svc = ScopeCalculatorService(fixture_session)
    result = svc.calculate_from_expression(
        expression="{tF_01.02, r0010, c0010} >= 0", release_code="4.1"
    )
    assert not result.has_error, result.error_message
    assert 356 in result.module_versions, result.module_versions
    assert 404 not in result.module_versions, "ghost 3.2.0 must not be scoped"


def test_no_prior_non_ghost_keeps_clean_no_scope_error(fixture_session):
    """#182 no-prior case: a ghost with no prior non-collapsed version errors.

    ``SEPA_IPR 1.0.0`` is the earliest version of its module, is a ghost, and
    covers release 4.1; its only sibling ``1.1.0`` starts later (4.2), so there
    is nothing to fall back to. ``S_01.01`` is hosted only by SEPA_IPR, so the
    release keeps the clean "no module versions found" error rather than
    scoping the ghost.
    """
    svc = ScopeCalculatorService(fixture_session)
    result = svc.calculate_from_expression(
        expression="{tS_01.01, r0010, c0010} >= 0", release_code="4.1"
    )
    assert result.has_error
    assert "No module versions found" in (result.error_message or "")
    assert not result.module_versions


class TestResolveExplicitRelease:
    """Explicit-release window checks (the #151 predates symptom).

    These resolve an explicitly named module version against a release on the
    release axis. ``FINREP9DP`` has two versions in the fixture: ``1.0.0``
    (release 4.2, single-day, ends at 4.2.1) and ``1.1.0`` (release 4.2.1,
    open). Explicit resolution is independent of the scope-level single-day
    exclusion -- it only checks the release window.
    """

    def test_in_window_release_resolves(self, fixture_session):
        svc = ASTGeneratorService(fixture_session)
        mv, rel = svc._resolve_release("FINREP9DP", "1.0.0", "4.2")
        assert rel.code == "4.2"
        assert mv.version_number == "1.0.0"

    def test_release_before_window_predates(self, fixture_session):
        # Requesting the 4.2.1 version at release 4.2 is exactly the error a
        # consumer hit when the buggy scope handed them ``1.1.0`` for 4.2.
        svc = ASTGeneratorService(fixture_session)
        with pytest.raises(ValueError, match="predates module version"):
            svc._resolve_release("FINREP9DP", "1.1.0", "4.2")

    def test_release_past_end_rejected(self, fixture_session):
        # 1.0.0 ends at 4.2.1, so 4.2.1 is past its end.
        svc = ASTGeneratorService(fixture_session)
        with pytest.raises(ValueError, match="past the end"):
            svc._resolve_release("FINREP9DP", "1.0.0", "4.2.1")

    def test_unknown_release_rejected(self, fixture_session):
        svc = ASTGeneratorService(fixture_session)
        with pytest.raises(ValueError, match="Release not found"):
            svc._resolve_release("FINREP9DP", "1.0.0", "9.9.9")


class TestResolveExplicitReleaseDateOrder:
    """Window checks against an in-memory schema (no optional fixture DB).

    ``TestResolveExplicitRelease`` above skips whenever ``test_data.db`` is
    absent, so on a bare checkout / CI the date sort-order branches of
    ``_resolve_explicit_release`` would go uncovered. These tests seed a tiny
    schema with a deliberately NON-monotonic ``ReleaseID`` layout -- release
    4.2 is given a larger id than 4.2.1, while the dates follow the lineage --
    so each one fails if the window check ever compares the raw ``release_id``
    instead of the ``Release.date`` sort order.
    """

    @pytest.fixture
    def svc(self, memory_session):
        memory_session.add_all(
            [
                # id order (3 < 5 < 1010000003) deliberately disagrees with
                # version order (4.0 < 4.2 < 4.2.1).
                Release(release_id=3, code="4.0", date=date(2025, 1, 1)),
                Release(
                    release_id=1010000003,
                    code="4.2",
                    date=date(2026, 3, 1),
                ),
                Release(release_id=5, code="4.2.1", date=date(2026, 6, 1)),
                # MODX is valid only from 4.2.1 (small id 5), open-ended.
                ModuleVersion(
                    module_vid=1,
                    module_id=1,
                    code="MODX",
                    version_number="1.0.0",
                    start_release_id=5,
                    end_release_id=None,
                    from_reference_date=date(2026, 6, 30),
                    to_reference_date=None,
                ),
                # MODY is valid from 4.0 (id 3) up to 4.2 (large id), end-excl.
                ModuleVersion(
                    module_vid=2,
                    module_id=2,
                    code="MODY",
                    version_number="1.0.0",
                    start_release_id=3,
                    end_release_id=1010000003,
                    from_reference_date=date(2025, 1, 31),
                    to_reference_date=date(2026, 3, 30),
                ),
            ]
        )
        memory_session.flush()
        return ASTGeneratorService(memory_session)

    def test_before_window_predates_by_date(self, svc):
        # MODX starts at 4.2.1 (id 5); request 4.2 (id 1010000003). Raw-id
        # compare (1010000003 < 5) would NOT predate; by date (4.2 < 4.2.1)
        # it does.
        with pytest.raises(ValueError, match="predates module version"):
            svc._resolve_release("MODX", "1.0.0", "4.2")

    def test_past_end_by_date(self, svc):
        # MODY ends at 4.2 (id 1010000003); request 4.2.1 (id 5). Raw-id
        # compare (5 >= 1010000003) would say in-window; by date (4.2.1 >= 4.2)
        # it is past the end.
        with pytest.raises(ValueError, match="past the end"):
            svc._resolve_release("MODY", "1.0.0", "4.2.1")

    def test_in_window_resolves(self, svc):
        mv, rel = svc._resolve_release("MODY", "1.0.0", "4.0")
        assert rel.code == "4.0"
        assert mv.version_number == "1.0.0"

    def test_unknown_release_rejected(self, svc):
        with pytest.raises(ValueError, match="Release not found"):
            svc._resolve_release("MODX", "1.0.0", "9.9")


class TestResolveExplicitReleaseGhostFallback:
    """Window-check coordination with ghost-fallback (issue #221).

    When the release-window resolution has legitimately handed the AST
    generator a non-ghost ModuleVersion as the fallback for a ghost of
    the same module (see
    ``dpm_xl.model_queries._resolve_with_ghost_fallback``), the strict
    window-check on the non-ghost must NOT reject the requested release
    -- it belongs to the ghost's window. The check must still reject
    releases that no ghost of that module covers.
    """

    @pytest.fixture
    def svc(self, memory_session):
        # Non-monotonic IDs (mirrors TestResolveExplicitReleaseDateOrder)
        # to make sure the ghost check uses date sort order, not raw IDs.
        memory_session.add_all(
            [
                Release(release_id=3, code="4.0", date=date(2025, 1, 1)),
                Release(
                    release_id=1010000003,
                    code="4.2",
                    date=date(2026, 3, 1),
                ),
                Release(release_id=5, code="4.2.1", date=date(2026, 6, 1)),
                # MODA -- past-the-end scenario (the DORA/issue-#221 shape).
                # Non-ghost 1.0.0 covers [4.0, 4.2); ghost 1.1.0 covers
                # [4.2, ∞). Request 4.2 against 1.0.0 must succeed.
                ModuleVersion(
                    module_vid=1,
                    module_id=1,
                    code="MODA",
                    version_number="1.0.0",
                    start_release_id=3,
                    end_release_id=1010000003,
                    from_reference_date=date(2025, 1, 31),
                    to_reference_date=date(2026, 3, 30),
                ),
                ModuleVersion(
                    module_vid=2,
                    module_id=1,
                    code="MODA",
                    version_number="1.1.0",
                    start_release_id=1010000003,
                    end_release_id=None,
                    from_reference_date=date(2026, 3, 31),
                    to_reference_date=date(2026, 3, 31),
                ),
                # MODC -- no ghost anywhere. Non-ghost 1.0.0 covers
                # [4.2, 4.2.1). Request 4.2.1 must still raise
                # "past the end" (no ghost of MODC covers it), and 4.0
                # must still raise "predates".
                ModuleVersion(
                    module_vid=5,
                    module_id=3,
                    code="MODC",
                    version_number="1.0.0",
                    start_release_id=1010000003,
                    end_release_id=5,
                    from_reference_date=date(2026, 3, 31),
                    to_reference_date=date(2026, 5, 30),
                ),
                # MODD -- ghost of a DIFFERENT module (id=1) must not
                # relax MODD's window. MODD 1.0.0 covers [4.0, 4.2);
                # 4.2 must still be rejected.
                ModuleVersion(
                    module_vid=6,
                    module_id=4,
                    code="MODD",
                    version_number="1.0.0",
                    start_release_id=3,
                    end_release_id=1010000003,
                    from_reference_date=date(2025, 1, 31),
                    to_reference_date=date(2026, 3, 30),
                ),
                # MODE -- open-ended ghost (start_release_id=None,
                # end_release_id=None). Should cover every release of
                # its module. Non-ghost MODE 1.0.0 covers [4.0, 4.2);
                # 4.2.1 must succeed thanks to the open-ended ghost.
                ModuleVersion(
                    module_vid=7,
                    module_id=5,
                    code="MODE",
                    version_number="1.0.0",
                    start_release_id=3,
                    end_release_id=1010000003,
                    from_reference_date=date(2025, 1, 31),
                    to_reference_date=date(2026, 3, 30),
                ),
                ModuleVersion(
                    module_vid=8,
                    module_id=5,
                    code="MODE",
                    version_number="1.1.0",
                    start_release_id=None,
                    end_release_id=None,
                    from_reference_date=date(2026, 3, 31),
                    to_reference_date=date(2026, 3, 31),
                ),
                # MODF -- ghost between two non-ghosts. Non-ghost 1.0.0
                # covers [4.0, 4.2); ghost 1.1.0 covers [4.2, 4.2.1);
                # non-ghost 1.2.0 covers [4.2.1, ∞). Effective end of
                # 1.0.0 extends past the ghost to 1.2.0's start (4.2.1):
                # 4.2 is accepted (inside chain), 4.2.1 is rejected
                # (past the next non-ghost's start).
                ModuleVersion(
                    module_vid=9,
                    module_id=6,
                    code="MODF",
                    version_number="1.0.0",
                    start_release_id=3,
                    end_release_id=1010000003,
                    from_reference_date=date(2025, 1, 31),
                    to_reference_date=date(2026, 3, 30),
                ),
                ModuleVersion(
                    module_vid=10,
                    module_id=6,
                    code="MODF",
                    version_number="1.1.0",
                    start_release_id=1010000003,
                    end_release_id=5,
                    from_reference_date=date(2026, 3, 31),
                    to_reference_date=date(2026, 3, 31),
                ),
                ModuleVersion(
                    module_vid=11,
                    module_id=6,
                    code="MODF",
                    version_number="1.2.0",
                    start_release_id=5,
                    end_release_id=None,
                    from_reference_date=date(2026, 6, 1),
                    to_reference_date=None,
                ),
            ]
        )
        memory_session.flush()
        return ASTGeneratorService(memory_session)

    def test_past_end_allowed_when_ghost_covers_release(self, svc):
        # Reproduction of issue #221: MODA 1.0.0 ends at 4.2, but ghost
        # MODA 1.1.0 covers 4.2 onwards, so 4.2 must be accepted.
        mv, rel = svc._resolve_release("MODA", "1.0.0", "4.2")
        assert rel.code == "4.2"
        assert mv.version_number == "1.0.0"

    def test_past_end_still_raised_when_no_ghost(self, svc):
        with pytest.raises(ValueError, match="past the end"):
            svc._resolve_release("MODC", "1.0.0", "4.2.1")

    def test_predates_still_raised_when_no_ghost(self, svc):
        # Predates branch is never relaxed by a ghost: ghost-fallback in
        # ``_latest_prior_non_collapsed_vids`` picks strictly backward,
        # so a ghost of the same module cannot legitimately produce this
        # scenario. Kept as regression against accidental relaxation.
        with pytest.raises(ValueError, match="predates module version"):
            svc._resolve_release("MODC", "1.0.0", "4.0")

    def test_ghost_of_another_module_does_not_relax(self, svc):
        # MODD has no ghost of its own; MODA's ghost covers 4.2 but must
        # not leak across modules.
        with pytest.raises(ValueError, match="past the end"):
            svc._resolve_release("MODD", "1.0.0", "4.2")

    def test_open_ended_ghost_covers_every_release(self, svc):
        # MODE ghost has start/end release ids both NULL -- covers all
        # releases of its module, so 4.2.1 is accepted against 1.0.0.
        mv, rel = svc._resolve_release("MODE", "1.0.0", "4.2.1")
        assert rel.code == "4.2.1"
        assert mv.version_number == "1.0.0"

    def test_extension_stops_at_next_non_ghost_start(self, svc):
        # MODF 1.0.0 ends at 4.2; ghost 1.1.0 covers [4.2, 4.2.1);
        # non-ghost 1.2.0 starts at 4.2.1. 4.2 sits inside the ghost's
        # region so is accepted (extension bridges the ghost), but 4.2.1
        # is the next non-ghost's start -- extension stops there.
        mv, rel = svc._resolve_release("MODF", "1.0.0", "4.2")
        assert rel.code == "4.2"
        assert mv.version_number == "1.0.0"
        with pytest.raises(ValueError, match="past the end"):
            svc._resolve_release("MODF", "1.0.0", "4.2.1")
