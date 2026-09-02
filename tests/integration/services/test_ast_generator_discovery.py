
"""Integration tests for ``ASTGeneratorService.script_for_module``.

Verifies the auto-discovery path (issue #625): given only a
``module_code``/``module_version``, the active validations, severities and
preconditions are looked up from the database instead of being supplied by
the caller.

Assertions are checked against an independent raw-SQL oracle rather than by
re-deriving expected values from the code under test. The oracle
deliberately does not replicate dpmcore's release-window resolution (a code
can have several historical ``OperationVersion`` rows) — instead, each
assertion matches the row whose ``Expression`` equals what
``script_for_module`` actually picked, so it is correct regardless of which
historical version dpmcore resolves to.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from dpmcore.services.ast_generator import (
    _VAR_REF_PATTERN,
    ASTGeneratorService,
)

# Also exercised by test_ast_generator_condexpr.py — known to have active,
# type-checking validations in the fixture DB.
_MODULE_CODE = "REM_DBM"
_MODULE_VERSION = "2.3.0"


def _active_scope_rows(session, module_code, module_version):
    """Raw-SQL oracle: active OperationScope rows for a module version.

    Deliberately re-implemented with plain SQL (not reusing
    ``_discover_module_validations``) so it serves as independent ground
    truth. Returns ``{code: [rows]}`` — a code may have more than one
    historical ``OperationVersion`` row in scope.
    """
    module_vid = session.execute(
        text(
            "SELECT ModuleVID FROM ModuleVersion "
            "WHERE Code = :c AND VersionNumber = :v"
        ),
        {"c": module_code, "v": module_version},
    ).scalar()
    assert module_vid is not None, (
        f"{module_code} {module_version} not in fixture DB"
    )

    rows = session.execute(
        text(
            """
            SELECT o.Code, ov.Expression, os.Severity,
                   ov.PreconditionOperationVID
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
    by_code: dict[str, list] = {}
    for row in rows:
        by_code.setdefault(row.Code, []).append(row)
    return by_code


def _precondition_expression(session, precondition_operation_vid):
    return session.execute(
        text(
            "SELECT o.Code, ov.Expression "
            "FROM OperationVersion ov "
            "JOIN Operation o ON o.OperationID = ov.OperationID "
            "WHERE ov.OperationVID = :vid"
        ),
        {"vid": precondition_operation_vid},
    ).first()


def _active_module_versions_oracle(session, module_code):
    """Raw-SQL oracle: non-phantom ``ModuleVersion`` rows for a module code.

    Phantom rows (``FromReferenceDate == ToReferenceDate``, both non-null)
    are excluded, mirroring ``list_module_versions``'s own filter.
    """
    rows = session.execute(
        text(
            "SELECT Code, VersionNumber, FromReferenceDate, ToReferenceDate "
            "FROM ModuleVersion WHERE Code = :c"
        ),
        {"c": module_code},
    ).fetchall()
    return {
        (r.Code, r.VersionNumber)
        for r in rows
        if r.FromReferenceDate is None
        or r.ToReferenceDate is None
        or r.FromReferenceDate != r.ToReferenceDate
    }


def test_list_module_versions_excludes_phantom_rows(fixture_session):
    oracle = _active_module_versions_oracle(fixture_session, _MODULE_CODE)
    assert oracle, "fixture DB has no ModuleVersion rows for this module"

    result = set(
        ASTGeneratorService(fixture_session).list_module_versions(
            module_code=_MODULE_CODE
        )
    )

    assert result == oracle


def test_list_module_versions_all_modules_is_a_superset(fixture_session):
    single = set(
        ASTGeneratorService(fixture_session).list_module_versions(
            module_code=_MODULE_CODE
        )
    )
    assert single, "fixture DB has no non-phantom versions for this module"

    everything = set(
        ASTGeneratorService(fixture_session).list_module_versions()
    )

    assert single <= everything


def test_list_module_versions_release_filter_stays_within_module(
    fixture_session,
):
    release_code = fixture_session.execute(
        text("SELECT Code FROM Release ORDER BY ReleaseID LIMIT 1")
    ).scalar()
    assert release_code is not None, "fixture DB has no Release rows"

    oracle = _active_module_versions_oracle(fixture_session, _MODULE_CODE)

    result = set(
        ASTGeneratorService(fixture_session).list_module_versions(
            module_code=_MODULE_CODE, release=release_code
        )
    )

    # A release filter must never surface a phantom row or a version of a
    # different module; it may only narrow the non-phantom set down.
    assert result <= oracle


def test_list_module_versions_unknown_release_raises(fixture_session):
    with pytest.raises(ValueError, match="not found"):
        ASTGeneratorService(fixture_session).list_module_versions(
            release="not-a-real-release-code-xyz"
        )


def test_discovers_active_validations(fixture_session):
    oracle = _active_scope_rows(fixture_session, _MODULE_CODE, _MODULE_VERSION)
    assert oracle, "fixture DB has no active validations for this module"

    result = ASTGeneratorService(fixture_session).script_for_module(
        module_code=_MODULE_CODE,
        module_version=_MODULE_VERSION,
    )

    assert result["success"] is True, result.get("error")
    assert result["failed_operations"] == {}

    _, ns_block = next(iter(result["enriched_ast"].items()))
    operations = ns_block["operations"]
    assert operations, "script_for_module discovered no validations"

    # Every discovered code must be a real, active-scoped operation for this
    # module version (no bogus/unscoped code leaks through).
    assert set(operations) <= set(oracle)

    for code, entry in operations.items():
        candidates = oracle[code]
        matching = [r for r in candidates if r.Expression == entry["expression"]]
        assert matching, (
            f"discovered expression for {code!r} matches none of the "
            f"active OperationVersion rows for it in the fixture DB"
        )
        oracle_row = matching[0]
        if oracle_row.Severity:
            assert entry["severity"] == oracle_row.Severity.lower()


def test_discovered_preconditions_reference_affected_operations(
    fixture_session,
):
    """Preconditions whose expression uses the ``{v_<code>}`` marker form
    (the only form ``_build_preconditions_block`` understands — see the
    note on ``ASTGeneratorService._resolve_preconditions``) must surface in
    the output with the right ``affected_operations``. Preconditions using
    any other DPM-XL expression form are expected to resolve to no
    variables and be silently dropped, same as pydpm — this test only
    asserts on the former.
    """
    oracle = _active_scope_rows(fixture_session, _MODULE_CODE, _MODULE_VERSION)

    result = ASTGeneratorService(fixture_session).script_for_module(
        module_code=_MODULE_CODE,
        module_version=_MODULE_VERSION,
    )
    assert result["success"] is True, result.get("error")

    _, ns_block = next(iter(result["enriched_ast"].items()))
    operations = ns_block["operations"]
    preconditions = ns_block["preconditions"]

    checked_any = False
    for code, candidates in oracle.items():
        if code not in operations:
            continue
        entry = operations[code]
        matching = [r for r in candidates if r.Expression == entry["expression"]]
        if not matching or not matching[0].PreconditionOperationVID:
            continue
        prec_row = _precondition_expression(
            fixture_session, matching[0].PreconditionOperationVID
        )
        assert prec_row is not None
        if not _VAR_REF_PATTERN.search(prec_row.Expression):
            continue  # not in the form _build_preconditions_block supports
        checked_any = True
        matches = [
            prec
            for prec in preconditions.values()
            if code in prec["affected_operations"]
        ]
        assert matches, (
            f"{code} has a precondition in the DB "
            f"({matching[0].PreconditionOperationVID}) but no matching "
            f"precondition entry was generated"
        )

    if not checked_any:
        pytest.skip(
            f"No discovered validation in {_MODULE_CODE} {_MODULE_VERSION} "
            "has a precondition using the {v_<code>} marker form that "
            "_build_preconditions_block supports."
        )
