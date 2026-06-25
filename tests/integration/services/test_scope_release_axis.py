"""Regression tests for issue #151: release-axis scope selection + single-day exclusion.

Two rules are pinned here, both verified against EBA's own pre-calculated
``OperationScope`` / ``OperationScopeComposition`` shipped in the dictionary
(an oracle straight from the data, not hand-built fixtures):

1. **Release axis only.** A module version is in scope for release R purely
   on the release-validity axis (``StartReleaseID``..``EndReleaseID``, compared
   on the semver sort order). The old reference-date ``_apply_fallback_for_equal_dates``
   could substitute a version absent from R -- e.g. ``FINREP9DP 1.1.0`` (a 4.2.1
   version) leaking into release 4.2 -- producing an invalid scope and the
   downstream ``Release X predates module version ...`` error a consumer hit.

2. **Single-day module versions are excluded (EBA business rule).** A module
   version whose reference-date window is collapsed (``FromReferenceDate ==
   ToReferenceDate``) describes one reporting date and is never in scope, even
   when it is the only version valid in a release -- that release then has no
   scope and reports a clean "no module versions found" error.

So the release-R oracle is the operation's persisted module versions, filtered
to R by the release axis, minus any collapsed-window version.
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
    """All releases, sorted by semver sort order (not the opaque ID)."""
    return sorted(
        session.query(Release).all(),
        key=lambda r: compute_sort_order(r.code) or 0,
    )


def _release_sort_by_id(session):
    """``{release_id: sort_order}`` for window/release-axis comparisons.

    Asserts every ``Release.code`` parses, so ``target_sort`` is always an
    ``int`` downstream: an unparseable code would otherwise make the oracle
    crash with a ``TypeError`` (``int <= None``) instead of failing clearly.
    """
    sort_by_id = {
        r.release_id: compute_sort_order(r.code)
        for r in session.query(Release).all()
    }
    assert all(v is not None for v in sort_by_id.values()), (
        "fixture has an unparseable Release.code; the oracle assumes every "
        "release code parses as MAJOR.MINOR[.PATCH]"
    )
    return sort_by_id


def _valid_in_release(mv, target_sort, sort_by_id):
    """Whether ``mv``'s release window contains ``target_sort``.

    Faithful mirror of ``filter_by_release`` (``start <= target`` and
    ``(end is open or target < end)`` on the semver sort order), including
    its handling of unresolved bounds: a start/end whose release yields no
    sort order (unparseable code or orphan FK) excludes the row, exactly as
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
    """Computed scope == persisted scope per release, minus single-day versions.

    The exact #151 scenario plus the business rule: release 4.2 yields
    ``FINREP9 3.3.0`` only -- never the 4.2.1 version ``1.1.0`` (release axis)
    and never the single-day ``FINREP9DP 1.0.0`` (exclusion rule). Releases
    4.0/4.1, whose only FINREP9 version (``3.2.0``) is single-day, end up with
    no scope at all.
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

    svc = ScopeCalculatorService(session)

    saw_empty_release = False
    for rel in _ordered_releases(session):
        target_sort = compute_sort_order(rel.code)
        oracle = {
            vid
            for vid, mv in versions.items()
            if _valid_in_release(mv, target_sort, sort_by_id)
            and not _is_collapsed(mv)
        }
        result = svc.calculate_from_expression(
            expression=expression, release_code=rel.code
        )
        assert set(result.module_versions) == oracle, (
            f"release {rel.code}: computed "
            f"{sorted(result.module_versions)} != oracle {sorted(oracle)} "
            f"(has_error={result.has_error}, msg={result.error_message})"
        )
        # A single-day version must never be selected, in any release.
        assert not (set(result.module_versions) & collapsed)
        if not oracle:
            # No eligible module version -> clean "no module versions" error.
            saw_empty_release = True
            assert result.has_error
            assert "No module versions found" in (result.error_message or "")

    assert saw_empty_release, (
        "expected a release whose only module version is single-day "
        "(4.0/4.1 for F_01.02) to end up with no scope"
    )


def test_scoped_versions_are_release_valid_and_not_single_day(fixture_session):
    """No computed scope returns a release-invalid or single-day version.

    The two invariants, swept across a sample of real F_01.02 operations:
    every module version in a computed scope must (a) satisfy
    ``start <= release < end`` on the semver sort order and (b) have a
    non-collapsed reference-date window.
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
            target_sort = compute_sort_order(rel.code)
            result = svc.calculate_from_expression(
                expression=expression, release_code=rel.code
            )
            if result.has_error:
                continue
            for vid in result.module_versions:
                checks += 1
                mv = versions[vid]
                assert _valid_in_release(mv, target_sort, sort_by_id), (
                    f"{code} @ {rel.code}: module version {vid} "
                    f"({mv.code} {mv.version_number}) is not valid in "
                    f"release {rel.code}"
                )
                assert not _is_collapsed(mv), (
                    f"{code} @ {rel.code}: single-day module version {vid} "
                    f"({mv.code} {mv.version_number}) must not be in scope"
                )

    assert checks, "invariant swept zero module versions"


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


class TestResolveExplicitReleaseSemverOrder:
    """Window checks against an in-memory schema (no optional fixture DB).

    ``TestResolveExplicitRelease`` above skips whenever ``test_data.db`` is
    absent, so on a bare checkout / CI the semver sort-order branches of
    ``_resolve_explicit_release`` would go uncovered. These tests seed a tiny
    schema with a deliberately NON-monotonic ``ReleaseID`` layout -- release
    4.2 is given a larger id than 4.2.1 -- so each one fails if the window
    check ever compares the raw ``release_id`` instead of the semver sort
    order derived from ``Release.code``.
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

    def test_before_window_predates_by_semver(self, svc):
        # MODX starts at 4.2.1 (id 5); request 4.2 (id 1010000003). Raw-id
        # compare (1010000003 < 5) would NOT predate; semver (4.2 < 4.2.1) does.
        with pytest.raises(ValueError, match="predates module version"):
            svc._resolve_release("MODX", "1.0.0", "4.2")

    def test_past_end_by_semver(self, svc):
        # MODY ends at 4.2 (id 1010000003); request 4.2.1 (id 5). Raw-id
        # compare (5 >= 1010000003) would say in-window; semver (4.2.1 >= 4.2)
        # is past the end.
        with pytest.raises(ValueError, match="past the end"):
            svc._resolve_release("MODY", "1.0.0", "4.2.1")

    def test_in_window_resolves(self, svc):
        mv, rel = svc._resolve_release("MODY", "1.0.0", "4.0")
        assert rel.code == "4.0"
        assert mv.version_number == "1.0.0"

    def test_unknown_release_rejected(self, svc):
        with pytest.raises(ValueError, match="Release not found"):
            svc._resolve_release("MODX", "1.0.0", "9.9")
