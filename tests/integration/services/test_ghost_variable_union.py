"""A #182 ghost-rescued operation must not reference an undeclared variable.

Companion to ``test_ghost_script_export.py``: that file covers the
scope side of the #182 rescue (a ghost's *validations* reaching the
fallback's script). This covers a gap the scope-only rescue left open
-- a ghost-rescued ``OperationVersion`` can reference a ``VariableID``
that only exists on the ghost's own ``TableVersion``, never composed
against the fallback's own ``ModuleVID``. Left undeclared, the
downstream DPM-XL engine cannot build a Scalar for that operand
("Scalar can't be created for this data").

IF_CLASS3 is the fixture's case: ``1.2.0`` (ModuleVID 349) is the
fallback for its ghost ``1.3.0`` (ModuleVID 429, ``FromReferenceDate
== ToReferenceDate``). ``v11131_m``'s ghost-scoped ``OperationVersion``
references ``VariableID`` 455022/455023, which live only on the
ghost's own ``TableVersion`` for ``I_01.01`` (TableVID 5863), absent
from the fallback's own (TableVID 2070).
"""

from __future__ import annotations

from sqlalchemy import text

from dpmcore.services.ast_generator import ASTGeneratorService

_MODULE = "IF_CLASS3"
_FALLBACK = "1.2.0"
_GHOST = "1.3.0"
_GHOST_RELEASE = "4.1"
_TABLE = "I_01.01"
_OPERATION = "v11131_m"
_GHOST_ONLY_VARIABLE_IDS = ("455022", "455023")


def _module_vid(session, code, version):
    return session.execute(
        text(
            "SELECT ModuleVID FROM ModuleVersion "
            "WHERE Code = :c AND VersionNumber = :v"
        ),
        {"c": code, "v": version},
    ).scalar()


def test_fixture_still_has_the_ghost_and_its_own_variable_ids(fixture_session):
    """Guard the fixture: the scenario below relies on this shape."""
    session = fixture_session
    ghost_vid = _module_vid(session, _MODULE, _GHOST)
    assert ghost_vid is not None, f"fixture: {_MODULE} {_GHOST} not found"

    is_ghost = session.execute(
        text(
            "SELECT FromReferenceDate = ToReferenceDate FROM ModuleVersion "
            "WHERE ModuleVID = :vid"
        ),
        {"vid": ghost_vid},
    ).scalar()
    assert is_ghost, f"fixture: {_MODULE} {_GHOST} is no longer a ghost"

    variable_ids = {
        str(r.VariableID)
        for r in session.execute(
            text(
                """
                SELECT DISTINCT orf.VariableID
                FROM Operation o
                JOIN OperationVersion ov ON ov.OperationID = o.OperationID
                JOIN OperationNode n ON n.OperationVID = ov.OperationVID
                JOIN OperandReference orf ON orf.NodeID = n.NodeID
                WHERE o.Code = :code
                """
            ),
            {"code": _OPERATION},
        ).fetchall()
    }
    missing = set(_GHOST_ONLY_VARIABLE_IDS) - variable_ids
    assert not missing, (
        f"fixture: {_OPERATION} no longer references {missing} -- "
        "pick a different ghost-only operand for this regression"
    )


def test_ghost_only_variables_are_declared_in_the_fallback_script(
    fixture_session,
):
    """The rescued operation's ghost-only operands must be declared.

    Without the fix, ``_get_module_tables`` only resolved the
    fallback's own ``ModuleVersionComposition`` -- the script would
    still include ``v11131_m`` (the #182 scope rescue already handled
    that), but its table's ``variables`` map would be missing the
    ghost-only VariableIDs the operation actually references.
    """
    result = ASTGeneratorService(fixture_session).script_for_module(
        module_code=_MODULE, module_version=_FALLBACK, release=_GHOST_RELEASE
    )
    assert result["success"], result.get("error")

    modules = list(result["enriched_ast"].values())
    assert len(modules) == 1, modules
    ns_block = modules[0]

    assert _OPERATION in ns_block["operations"], (
        f"{_OPERATION} missing from the script -- the #182 scope rescue "
        "regressed, this test can't isolate the variable-union gap"
    )

    table_variables = ns_block["tables"][_TABLE]["variables"]
    top_level_variables = ns_block["variables"]
    for var_id in _GHOST_ONLY_VARIABLE_IDS:
        assert var_id in table_variables, (
            f"{var_id} missing from tables[{_TABLE!r}].variables"
        )
        assert var_id in top_level_variables, (
            f"{var_id} missing from the top-level variables block"
        )
