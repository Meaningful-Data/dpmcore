"""Regression tests for issue #151: module-version selection is release-axis only.

Before the fix, a reference-date fallback (``_apply_fallback_for_equal_dates``)
could substitute a module version that does not exist in the queried release
-- e.g. ``FINREP9DP 1.1.0`` (a release-4.2.1 version) leaking into release 4.2
-- producing an invalid scope and the downstream ``Release X predates module
version ...`` error a consumer reported.

The oracle here is EBA's own pre-calculated ``OperationScope`` /
``OperationScopeComposition`` shipped in the dictionary, not hand-built
fixtures: the persisted scope of an operation is the union of the module
versions hosting it across that operation version's lifetime, so the
release-R answer is exactly that set filtered onto release R by the release
axis.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import ModuleVersion
from dpmcore.orm.release_sort_order import compute_sort_order
from dpmcore.services.ast_generator import ASTGeneratorService
from dpmcore.services.scope_calculator import ScopeCalculatorService

# v3898_s references a single table (F_01.02) and has one operation version
# spanning every release, so its persisted scope maps cleanly onto each
# release. Its EBA scope holds collapsed-window versions (FINREP9 3.2.0,
# FINREP9DP 1.0.0) as first-class targets -- the exact rows the bug rewrote.
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
    """``{release_id: sort_order}`` for window/release-axis comparisons."""
    return {
        r.release_id: compute_sort_order(r.code)
        for r in session.query(Release).all()
    }


def _valid_in_release(mv, target_sort, sort_by_id):
    """Whether ``mv``'s release window contains ``target_sort``.

    Mirrors the end-exclusive release filter: ``start <= target`` and
    ``(end is open or target < end)``, compared on the semver sort order.
    """
    start = (
        sort_by_id.get(mv.start_release_id)
        if mv.start_release_id is not None
        else None
    )
    end = (
        sort_by_id.get(mv.end_release_id)
        if mv.end_release_id is not None
        else None
    )
    if start is None:
        return False
    return start <= target_sort and (end is None or target_sort < end)


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
    """Computed scope equals EBA's persisted scope filtered to each release.

    The exact #151 scenario: for release 4.2 the scope must contain
    ``FINREP9DP 1.0.0`` (the collapsed-window release-4.2 version), never
    the open-ended ``1.1.0`` that belongs to release 4.2.1.
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
    svc = ScopeCalculatorService(session)

    selected_a_collapsed_version = False
    for rel in _ordered_releases(session):
        target_sort = compute_sort_order(rel.code)
        oracle = {
            vid
            for vid, mv in versions.items()
            if _valid_in_release(mv, target_sort, sort_by_id)
        }
        result = svc.calculate_from_expression(
            expression=expression, release_code=rel.code
        )
        assert not result.has_error, result.error_message
        assert set(result.module_versions) == oracle, (
            f"release {rel.code}: computed "
            f"{sorted(result.module_versions)} != EBA oracle "
            f"{sorted(oracle)}"
        )
        # The fix must still *select* release-valid collapsed-window
        # versions, not blanket-drop every ``from == to`` version.
        for vid in oracle:
            mv = versions[vid]
            if mv.from_reference_date == mv.to_reference_date:
                selected_a_collapsed_version = True

    assert selected_a_collapsed_version, (
        "expected at least one collapsed-window version (e.g. FINREP9DP "
        "1.0.0) to be a valid release-keyed selection"
    )


def test_returned_module_versions_are_release_valid(fixture_session):
    """No computed scope returns a module version absent from the release.

    The release-axis invariant the bug violated, swept across a sample of
    real F_01.02 operations: every module version in a computed scope must
    satisfy ``start <= release < end`` on the semver sort order.
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

    assert checks, "invariant swept zero module versions"


class TestResolveExplicitRelease:
    """Window checks resolve on the release axis (the #151 predates symptom).

    ``FINREP9DP`` has two versions in the fixture: ``1.0.0`` (release 4.2,
    collapsed window, ends at 4.2.1) and ``1.1.0`` (release 4.2.1, open).
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
