"""Integration regression: an expression that is no operation (#484).

``semantic.validate()`` accepts a bare selection like ``{tC_00.01}``, but
``ASTGeneratorService.script`` cannot declare it: its root applies no
operator. The same holds for a function with no ``Operator`` row, such as
``nvl``. ``script()`` used to raise outside its per-operation handling,
failing the whole module with an empty ``failed_operations``. Each such
expression must now be reported under its own code, with the rest of the
module still generated.
"""

from __future__ import annotations

from dpmcore.services.ast_generator import ASTGeneratorService

_GOOD = "{tC_01.00, r0010, c0010} >= 0"


def test_unresolvable_roots_fail_only_their_own_operation(fixture_session):
    """Bare selection, constant and ``nvl`` roots fail one by one."""
    service = ASTGeneratorService(fixture_session)

    result = service.script(
        expressions=[
            (_GOOD, "good_1"),
            ("{tC_00.01}", "bad_selection"),
            ("1", "bad_constant"),
            ("nvl({tC_01.00, r0010, c0010}, 0)", "bad_nvl"),
        ],
        module_code="COREP_OF",
        module_version="4.1.0",
    )

    assert result["success"], result["error"]
    namespace = next(iter(result["enriched_ast"]))
    operations = result["enriched_ast"][namespace]["operations"]
    assert set(operations) == {"good_1"}
    assert result["failed_operations"] == {
        "bad_selection": (
            "Cannot resolve root operator: the expression root "
            "'VarID' is not an operation"
        ),
        "bad_constant": (
            "Cannot resolve root operator: the expression root "
            "'Constant' is not an operation"
        ),
        "bad_nvl": (
            "Cannot resolve root operator: no Operator has the symbol 'nvl'"
        ),
    }
