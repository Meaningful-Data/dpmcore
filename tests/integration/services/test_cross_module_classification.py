"""Integration regression: intra/cross-module classification.

A validation is intra-instance for a module when every table it references
belongs to that module; cross-instance when the module hosts only some of
them; and neither when the module hosts none. These tests pin that behaviour
for the affected validations.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from dpmcore.services.ast_generator import ASTGeneratorService


def _latest_expression(session, code: str) -> str:
    operation_id = session.execute(
        text("SELECT OperationID FROM Operation WHERE Code = :c"),
        {"c": code},
    ).scalar()
    assert operation_id is not None, f"{code} not in fixture DB"
    return session.execute(
        text(
            "SELECT Expression FROM OperationVersion "
            "WHERE OperationID = :o ORDER BY OperationVID DESC LIMIT 1"
        ),
        {"o": operation_id},
    ).scalar()


def _classify(session, code, module_code, module_version):
    expression = _latest_expression(session, code)
    result = ASTGeneratorService(session).script(
        expressions=[(expression, code)],
        module_code=module_code,
        module_version=module_version,
    )
    assert result["success"], result["error"]
    namespace = next(iter(result["enriched_ast"]))
    module = result["enriched_ast"][namespace]
    info = module["dependency_information"]
    return {
        "intra": info["intra_instance_validations"],
        "cross": len(info["cross_instance_dependencies"]),
        "tables": sorted(module["tables"].keys()),
    }


@pytest.mark.parametrize(
    ("code", "module_code", "module_version", "expect_intra", "expect_cross"),
    [
        # Both referenced tables belong to the module -> intra in both.
        ("v09808_m", "COREP_OF", "4.1.0", True, False),
        ("v09808_m", "IF_CLASS2", "1.4.0", True, False),
        # All tables in the primary, secondary requires the primary -> the
        # legit MIXED case: intra for COREP_OF, cross for IF_CLASS2.
        ("v22973_m", "COREP_OF", "4.1.0", True, False),
        ("v22973_m", "IF_CLASS2", "1.4.0", False, True),
        # v11120_m references I_04.00 (IF_CLASS2-only) and I_05.00 (both
        # IF_CLASS2 and IF_CLASS3): intra in IF_CLASS2, cross in IF_CLASS3.
        ("v11120_m", "IF_CLASS2", "1.4.0", True, False),
        ("v11120_m", "IF_CLASS3", "1.4.0", False, True),
    ],
)
def test_named_classification(
    fixture_session,
    code,
    module_code,
    module_version,
    expect_intra,
    expect_cross,
):
    """Each named validation classifies as expected."""
    result = _classify(fixture_session, code, module_code, module_version)
    assert (result["intra"] == [code]) is expect_intra
    assert (result["cross"] > 0) is expect_cross


def test_primary_hosting_no_tables_is_not_intra(fixture_session):
    """A module hosting none of a validation's tables is neither intra nor cross."""
    result = _classify(fixture_session, "v11120_m", "COREP_OF", "4.1.0")
    assert result["intra"] == []
    assert result["cross"] == 0
    assert result["tables"] == []
