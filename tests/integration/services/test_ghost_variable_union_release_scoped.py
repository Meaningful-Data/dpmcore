"""A #182 ghost-variable union must be scoped to the covering ghost only.

Companion to ``test_ghost_variable_union.py``: that file covers a
fallback with a *single* ghost sibling (IF_CLASS3). COREP_FRTB-3.1.0
has *two* -- 3.2.0 (ModuleVID 392) then 3.3.0 (ModuleVID 434) -- and
its table ``C_96.05.2`` has two ``TableVersion`` rows with completely
disjoint variable_ids, one composed with each ghost. Unioning the
*whole* ghost chain regardless of which release is being resolved (as
opposed to only the one ghost whose own window covers the resolved
release) leaked a later ghost's variables into an earlier release, and
vice versa -- the same class of leak PR #396 already fixed once for
validation scope (see ``_release_ghost_fallbacks``), just recurring in
the table/variable union added on top of it.
"""

from __future__ import annotations

from sqlalchemy import text

from dpmcore.services.ast_generator import ASTGeneratorService

_MODULE = "COREP_FRTB"
_FALLBACK = "3.1.0"
_TABLE = "C_96.05.2"
# Covered by ghost 3.2.0 (ModuleVID 392) only.
_RELEASE_UNDER_FIRST_GHOST = "3.5"
# Covered by ghost 3.3.0 (ModuleVID 434) only.
_RELEASES_UNDER_SECOND_GHOST = ("4.0", "4.1")
# VariableIDs living on exactly one of the table's two TableVersion rows.
_FIRST_GHOST_ONLY_VARIABLE_ID = "486275"
_SECOND_GHOST_ONLY_VARIABLE_ID = "3291677"


def _module_vid(session, code, version):
    return session.execute(
        text(
            "SELECT ModuleVID FROM ModuleVersion "
            "WHERE Code = :c AND VersionNumber = :v"
        ),
        {"c": code, "v": version},
    ).scalar()


def test_fixture_still_has_two_ghosts_with_disjoint_table_variables(
    fixture_session,
):
    """Guard the fixture: the scenario below relies on this shape."""
    session = fixture_session
    ghost_vids = [
        r.ModuleVID
        for r in session.execute(
            text(
                "SELECT ModuleVID FROM ModuleVersion WHERE Code = :c "
                "AND FromReferenceDate = ToReferenceDate "
                "AND FromReferenceDate IS NOT NULL"
            ),
            {"c": _MODULE},
        ).fetchall()
    ]
    assert len(ghost_vids) >= 2, (
        f"fixture: {_MODULE} no longer has two (or more) ghost siblings"
    )

    table_vids = {
        r.TableVID
        for r in session.execute(
            text("SELECT TableVID FROM TableVersion WHERE Code = :t"),
            {"t": _TABLE},
        ).fetchall()
    }
    assert len(table_vids) >= 2, (
        f"fixture: {_TABLE} no longer has multiple TableVersion rows"
    )

    for var_id, expected_count in (
        (_FIRST_GHOST_ONLY_VARIABLE_ID, 1),
        (_SECOND_GHOST_ONLY_VARIABLE_ID, 1),
    ):
        rows = session.execute(
            text(
                """
                SELECT DISTINCT tvc.TableVID
                FROM TableVersionCell tvc
                JOIN VariableVersion vv ON vv.VariableVID = tvc.VariableVID
                WHERE vv.VariableID = :vid
                """
            ),
            {"vid": var_id},
        ).fetchall()
        assert len(rows) == expected_count, (
            f"fixture: VariableID {var_id} no longer lives on exactly "
            f"one TableVersion of {_TABLE} -- pick a different pair for "
            "this regression"
        )


def test_ghost_union_is_scoped_to_the_release_covering_ghost(
    fixture_session,
):
    """Each release must only see its own covering ghost's variables.

    Without the fix, ``_assemble_script`` unioned the fallback's
    *whole* ghost chain (``_ghost_chain_vids``) into every release's
    table/variable declarations, regardless of which ghost's own
    window actually covers the resolved release. The fix threads the
    release through ``_release_ghost_fallbacks`` instead, mirroring
    the same release-scoped lookup already used for validation scope.
    """
    service = ASTGeneratorService(fixture_session)

    result = service.script_for_module(
        module_code=_MODULE,
        module_version=_FALLBACK,
        release=_RELEASE_UNDER_FIRST_GHOST,
    )
    assert result["success"], result.get("error")
    ns = next(iter(result["enriched_ast"].values()))
    variables = ns["tables"][_TABLE]["variables"]
    assert _FIRST_GHOST_ONLY_VARIABLE_ID in variables
    assert _SECOND_GHOST_ONLY_VARIABLE_ID not in variables, (
        f"{_RELEASE_UNDER_FIRST_GHOST} is only covered by the first "
        "ghost -- the second ghost's variable must not leak in"
    )

    for release in _RELEASES_UNDER_SECOND_GHOST:
        result = service.script_for_module(
            module_code=_MODULE,
            module_version=_FALLBACK,
            release=release,
        )
        assert result["success"], result.get("error")
        ns = next(iter(result["enriched_ast"].values()))
        variables = ns["tables"][_TABLE]["variables"]
        assert _SECOND_GHOST_ONLY_VARIABLE_ID in variables
        assert _FIRST_GHOST_ONLY_VARIABLE_ID not in variables, (
            f"{release} is only covered by the second ghost -- the "
            "first ghost's variable must not leak in"
        )
