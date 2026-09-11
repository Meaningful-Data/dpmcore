"""Integration regression: intra/cross-module classification.

A validation is intra-instance for a module when every table it references
belongs to that module; cross-instance when the module hosts only some of
them *and* no other module hosts them all (#304 — a module that can evaluate
the validation alone makes every pairing around it redundant); and neither
when the module hosts none. These tests pin that behaviour for the affected
validations.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from dpmcore.services.ast_generator import ASTGeneratorService
from dpmcore.services.scope_calculator import ScopeCalculatorService

# A validation no single module can evaluate: C_43.00.c is COREP_LR's and
# C_08.01.a is COREP_OF's, so its scope is genuinely cross-instance and
# survives the #304 pruning. Used by the #250/#251 regressions below.
_CROSS_CODE = "v0709_m"
_CROSS_MODULE = "COREP_LR"
_CROSS_VERSION = "4.1.0"

# Issue #304, measured against the shipped 4.2.1 fixture DB: C_16.00.b
# exists only in COREP_OF 3.1.0 (module VID 344) and only up to release
# 4.0, hence the 3.4 pin.
_SHARED_TABLE_EXPRESSION = (
    "if {tC_16.00.b, r0130, c0070} > 0 "
    "and {tC_00.01, r0020, c0010} = [eba_SC:x7] "
    "then {p_OPRISKCONS_AMA, string} = 'Y' "
    "else {p_OPRISKSOLO_AMA, string} = 'Y' endif"
)
_SHARED_TABLE_RELEASE = "3.4"
_COREP_OF_3_1_0 = 344


def _latest_expression(session, code: str) -> str:
    operation_id = session.execute(
        text("SELECT OperationID FROM Operation WHERE Code = :c"),
        {"c": code},
    ).scalar()
    assert operation_id is not None, f"{code} not in fixture DB"
    expression = session.execute(
        text(
            "SELECT Expression FROM OperationVersion "
            "WHERE OperationID = :o ORDER BY OperationVID DESC LIMIT 1"
        ),
        {"o": operation_id},
    ).scalar()
    assert expression is not None, f"{code} has no expression in fixture DB"
    return expression


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
        # All tables in the primary -> intra for COREP_OF. IF_CLASS2 only
        # holds a shared subset, so pairing it with COREP_OF adds nothing
        # COREP_OF cannot do alone: no cross scope survives (#304).
        ("v22973_m", "COREP_OF", "4.1.0", True, False),
        ("v22973_m", "IF_CLASS2", "1.4.0", False, False),
        # v11120_m references I_04.00 (IF_CLASS2-only) and I_05.00 (both
        # IF_CLASS2 and IF_CLASS3): intra in IF_CLASS2. IF_CLASS3 only
        # duplicates I_05.00, so it is not a dependency either (#304).
        ("v11120_m", "IF_CLASS2", "1.4.0", True, False),
        ("v11120_m", "IF_CLASS3", "1.4.0", False, False),
        # A genuinely cross-instance validation: C_43.00.c lives in
        # COREP_LR and C_08.01.a in COREP_OF, so neither module can
        # evaluate it alone and the cross scope is real.
        ("v0709_m", "COREP_LR", "4.1.0", False, True),
        ("v0709_m", "COREP_OF", "4.1.0", False, True),
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


def test_shared_table_yields_only_the_intra_scope(fixture_session):
    """Regression for #304: a table hosted by many modules must not
    spawn a cross scope per host when one module already covers the
    whole expression.

    ``C_00.01`` lives in every COREP module, but only COREP_OF also has
    ``C_16.00.b`` — so COREP_OF evaluates the expression alone and each
    ``{sibling, COREP_OF}`` pair is a redundant superset of that scope.
    """
    result = ScopeCalculatorService(fixture_session).calculate_from_expression(
        expression=_SHARED_TABLE_EXPRESSION,
        release_code=_SHARED_TABLE_RELEASE,
    )
    assert not result.has_error, result.error_message
    assert result.total_scopes == 1
    assert not result.is_cross_module
    assert result.module_versions == [_COREP_OF_3_1_0]


def _operand_datapoints(node) -> set[str]:
    """Every ``VarID`` datapoint id in a serialised operation AST."""
    found: set[str] = set()
    if isinstance(node, dict):
        if node.get("class_name") == "VarID":
            for entry in node.get("data") or []:
                if isinstance(entry, dict) and entry.get("datapoint"):
                    found.add(str(entry["datapoint"]))
        for value in node.values():
            if isinstance(value, (dict, list)):
                found |= _operand_datapoints(value)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, (dict, list)):
                found |= _operand_datapoints(item)
    return found


def test_cross_validation_operands_declared_in_dependency(fixture_session):
    """Regression for #251: every operand datapoint of a cross-instance
    validation — home-module ones included — is declared in the
    ``variables`` map of each module the validation depends on.
    """
    code = _CROSS_CODE
    expression = _latest_expression(fixture_session, code)
    result = ASTGeneratorService(fixture_session).script(
        expressions=[(expression, code)],
        module_code=_CROSS_MODULE,
        module_version=_CROSS_VERSION,
    )
    assert result["success"], result["error"]
    module = next(iter(result["enriched_ast"].values()))
    dep_modules = module["dependency_modules"]
    assert dep_modules, f"{code} must be cross-instance for {_CROSS_MODULE}"

    operands = _operand_datapoints(module["operations"][code]["ast"])
    assert operands, "the validation must reference at least one datapoint"
    home_variables = set(module["variables"])
    assert operands & home_variables, (
        f"{code} has home-module operands: they are what #251 was about"
    )

    for uri, dep in dep_modules.items():
        missing = operands - set(dep["variables"])
        assert not missing, f"{uri} omits operand datapoints {sorted(missing)}"


def test_dependency_declares_only_referenced_subset(fixture_session):
    """Regression for #250: a dependency module is declared as the subset
    the cross-rules reference, not as the whole module.
    """
    code = _CROSS_CODE
    expression = _latest_expression(fixture_session, code)
    result = ASTGeneratorService(fixture_session).script(
        expressions=[(expression, code)],
        module_code=_CROSS_MODULE,
        module_version=_CROSS_VERSION,
    )
    assert result["success"], result["error"]
    module = next(iter(result["enriched_ast"].values()))
    dep_modules = module["dependency_modules"]
    assert dep_modules, f"{code} must be cross-instance for {_CROSS_MODULE}"

    referenced_tables = set(
        _referenced_tables(module["operations"][code]["ast"])
    )
    operands = _operand_datapoints(module["operations"][code]["ast"])
    for uri, dep in dep_modules.items():
        assert set(dep["tables"]) <= referenced_tables, (
            f"{uri} declares tables no operation references: "
            f"{sorted(set(dep['tables']) - referenced_tables)}"
        )
        for tcode, table in dep["tables"].items():
            assert table["variables"], f"{uri}/{tcode} declares no variables"
            extra = set(table["variables"]) - operands
            assert not extra, (
                f"{uri}/{tcode} declares unreferenced datapoints "
                f"{sorted(extra)[:10]}"
            )


def _referenced_tables(node) -> set[str]:
    """Every ``VarID`` table code in a serialised operation AST."""
    found: set[str] = set()
    if isinstance(node, dict):
        if node.get("class_name") == "VarID" and node.get("table"):
            found.add(node["table"])
        for value in node.values():
            if isinstance(value, (dict, list)):
                found |= _referenced_tables(value)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, (dict, list)):
                found |= _referenced_tables(item)
    return found
