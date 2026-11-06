"""Integration regression: the dependency group of a validation.

A validation needs nothing else in a module that holds every table it
references; it requires another module when the module holds only some
of them *and* no other module holds them all (#304 — a module that can
evaluate the validation alone makes every pairing around it redundant);
and it has no group when the module holds none. These tests pin that
behaviour for the affected validations.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from dpmcore.services.ast_generator import ASTGeneratorService
from dpmcore.services.scope_calculator import ScopeCalculatorService

# A validation no single module can evaluate: C_43.00.c is COREP_LR's and
# C_08.01.a is COREP_OF's, so its scope is genuinely cross-instance and
# survives the #304 pruning. Used by the #250 regression below.
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


def _own_version(document):
    """The script's own module version, as ``modules`` lists it."""
    (version,) = [
        version
        for version in document["modules"][document["module_code"]]["versions"]
        if version["URI"] == document["module_uri"]
    ]
    return version


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
    """Every ``FactVarID`` datapoint id in a serialised operation AST."""
    found: set[str] = set()
    if isinstance(node, dict):
        if node.get("class_name") == "FactVarID":
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


def test_another_module_lists_only_what_is_read(fixture_session):
    """Regression for #250: a module the validation depends on lists the
    tables and datapoints it reads, not the whole module.
    """
    code = _CROSS_CODE
    expression = _latest_expression(fixture_session, code)
    result = ASTGeneratorService(fixture_session).script(
        expressions=[(expression, code)],
        module_code=_CROSS_MODULE,
        module_version=_CROSS_VERSION,
    )
    assert result["success"], result["error"]
    module = result["enriched_ast"]
    others = {
        module_code: entry
        for module_code, entry in module["modules"].items()
        if module_code != _CROSS_MODULE
    }
    assert others, f"{code} must read another module than {_CROSS_MODULE}"

    referenced_tables = _referenced_tables(module["operations"][code]["ast"])
    operands = _operand_datapoints(module["operations"][code]["ast"])
    for module_code, entry in others.items():
        for version in entry["versions"]:
            tables = version["tables"]
            assert set(tables) <= referenced_tables, (
                f"{module_code} lists tables no operation references: "
                f"{sorted(set(tables) - referenced_tables)}"
            )
            for tcode, table in tables.items():
                assert table["variables"], f"{module_code}/{tcode} is empty"
                extra = set(table["variables"]) - operands
                assert not extra, (
                    f"{module_code}/{tcode} lists unreferenced datapoints "
                    f"{sorted(extra)[:10]}"
                )


def _referenced_tables(node) -> set[str]:
    """Every ``FactVarID`` table code in a serialised operation AST."""
    found: set[str] = set()
    if isinstance(node, dict):
        if node.get("class_name") == "FactVarID" and node.get("table"):
            found.add(node["table"])
        for value in node.values():
            if isinstance(value, (dict, list)):
                found |= _referenced_tables(value)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, (dict, list)):
                found |= _referenced_tables(item)
    return found


@pytest.mark.parametrize(
    ("code", "module_code", "module_version", "requires"),
    [
        # Both referenced tables belong to the module.
        ("v09808_m", "COREP_OF", "4.1.0", {}),
        ("v09808_m", "IF_CLASS2", "1.4.0", {}),
        ("v22973_m", "COREP_OF", "4.1.0", {}),
        # v11120_m references I_04.00 (IF_CLASS2-only) and I_05.00 (both
        # IF_CLASS2 and IF_CLASS3).
        ("v11120_m", "IF_CLASS2", "1.4.0", {}),
        # A genuinely cross-instance validation: C_43.00.c lives in
        # COREP_LR and C_08.01.a in COREP_OF, so neither module can
        # evaluate it alone and the cross scope is real.
        (
            "v0709_m",
            "COREP_LR",
            "4.1.0",
            {"is": {"code": "COREP_OF", "ref_date_lag": 0}},
        ),
        (
            "v0709_m",
            "COREP_OF",
            "4.1.0",
            {"is": {"code": "COREP_LR", "ref_date_lag": 0}},
        ),
    ],
)
def test_dependency_group(
    fixture_session, code, module_code, module_version, requires
):
    """An intra-instance validation needs nothing else; a cross-instance
    one requires the module holding the tables the own one does not.
    """
    expression = _latest_expression(fixture_session, code)
    result = ASTGeneratorService(fixture_session).script(
        expressions=[(expression, code)],
        module_code=module_code,
        module_version=module_version,
    )
    assert result["success"], result["error"]
    assert result["enriched_ast"]["dependency_groups"] == {
        "G1": {"requires": requires, "validations": [code]}
    }


@pytest.mark.parametrize(
    ("code", "module_code", "module_version"),
    [
        ("v11120_m", "COREP_OF", "4.1.0"),
        # IF_CLASS2 only holds a shared subset, so pairing it with
        # COREP_OF adds nothing COREP_OF cannot do alone: no scope with
        # IF_CLASS2 survives (#304).
        ("v22973_m", "IF_CLASS2", "1.4.0"),
        # IF_CLASS3 only duplicates I_05.00 of IF_CLASS2 (#304).
        ("v11120_m", "IF_CLASS3", "1.4.0"),
    ],
)
def test_a_validation_reading_no_own_table_has_no_group(
    fixture_session, code, module_code, module_version
):
    """A module hosting none of a validation's tables cannot place it in
    a dependency group, so it is reported in ``failed_operations``.
    """
    expression = _latest_expression(fixture_session, code)
    result = ASTGeneratorService(fixture_session).script(
        expressions=[(expression, code)],
        module_code=module_code,
        module_version=module_version,
    )
    assert result["success"], result["error"]
    document = result["enriched_ast"]
    assert document["operations"] == {}
    assert document["dependency_groups"] == {}
    assert (
        f"None of its scopes includes module {module_code}"
        in (result["failed_operations"][code])
    )
