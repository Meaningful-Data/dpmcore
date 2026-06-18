"""Integration regression for intra/cross-module classification.

These pin, against the real 4.2.1 dictionary, the dependency-information
classification that ``ASTGeneratorService.script`` emits for the validations
the downstream engine flagged. The agreed rule: a validation is intra-instance for
module M when every table it references belongs to M; otherwise, for a module
that hosts only some of the tables it is a cross-instance dependency; and for
a module that hosts *none* of its tables it is neither (empty classification).

Synthetic-fixture greens are what let the rc2 misclassifications slip, so
these run end-to-end on the shipped dictionary.
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
    """Each named validation classifies as agreed against real data."""
    result = _classify(fixture_session, code, module_code, module_version)
    assert (result["intra"] == [code]) is expect_intra
    assert (result["cross"] > 0) is expect_cross


def test_primary_hosting_no_tables_is_not_intra(fixture_session):
    """v11120_m for COREP_OF (hosts neither I_04.00 nor I_05.00).

    Regression for the misclassification where a validation generated for a
    module that hosts none of its tables was emitted as intra-instance with
    an empty ``tables`` block. It must be neither intra nor cross.
    """
    result = _classify(fixture_session, "v11120_m", "COREP_OF", "4.1.0")
    assert result["intra"] == []
    assert result["cross"] == 0
    assert result["tables"] == []
