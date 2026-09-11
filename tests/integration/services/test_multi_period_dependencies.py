"""Integration regression: one module needed at several instances (#326).

The reference period is a property of a declared module and only one was
kept per module, so an operation reading two tables of the same
dependency module at different instances — or one table both plain and
shifted — was declared against a single instance and evaluated against
the wrong one. Every distinct period is now its own
``cross_instance_dependencies`` entry.

A shift number that is not an integer literal used to render as
``T-nQ``, which names no resolvable instance; the operation is now
skipped with a reason instead.

``C_47.00`` is a COREP_LR table (the home module here) and ``C_01.00`` /
``C_05.01`` are COREP_OF tables, so each expression crosses into a real
dependency module of the fixture dictionary.
"""

from __future__ import annotations

import pytest

from dpmcore.services.ast_generator import ASTGeneratorService

_MODULE_CODE = "COREP_LR"
_MODULE_VERSION = "3.1.0"
_DEPENDENCY = "corep_of"

_SHIFT_Q1 = (
    "{tC_47.00, r0310, c0010} > "
    "time_shift({tC_01.00, r0020, c0010}, Q, -1, refPeriod)[get refPeriod]"
)
_SHIFT_Q4 = (
    "{tC_47.00, r0370, c0010} > "
    "time_shift({tC_01.00, r0030, c0010}, Q, -4, refPeriod)[get refPeriod]"
)
# One expression shifting two tables of the same dependency module by
# different amounts: reachable without any merging of operations.
_TWO_TABLES = (
    "{tC_47.00, r0310, c0010} > "
    "time_shift({tC_01.00, r0020, c0010}, Q, -1, refPeriod)[get refPeriod] and "
    "{tC_47.00, r0370, c0010} > "
    "time_shift({tC_05.01, r0010, c0010}, Q, -4, refPeriod)[get refPeriod]"
)
# One expression reading the same dependency table shifted and plain.
_SHIFTED_AND_PLAIN = (
    "{tC_47.00, r0310, c0010} > "
    "time_shift({tC_01.00, r0020, c0010}, Q, -1, refPeriod)[get refPeriod] and "
    "{tC_47.00, r0370, c0010} = {tC_01.00, r0020, c0010}"
)
_NON_LITERAL_SHIFT = (
    "{tC_47.00, r0310, c0010} > "
    "time_shift({tC_01.00, r0020, c0010}, Q, 2 * 2, refPeriod)[get refPeriod]"
)


def _script(session, expressions):
    result = ASTGeneratorService(session).script(
        expressions=expressions,
        module_code=_MODULE_CODE,
        module_version=_MODULE_VERSION,
    )
    assert result["success"], result["error"]
    module = next(iter(result["enriched_ast"].values()))
    return result, module


def _declared(module):
    """The ``(module code, ref_period, affected operations)`` triples."""
    return [
        (
            entry["URI"].rsplit("/", 1)[-1],
            entry["ref_period"],
            tuple(dependency["affected_operations"]),
        )
        for dependency in module["dependency_information"][
            "cross_instance_dependencies"
        ]
        for entry in dependency["modules"]
    ]


def test_two_shifted_tables_of_one_module_declare_both_instances(
    fixture_session,
):
    _, module = _script(fixture_session, [(_TWO_TABLES, "OP_BOTH")])
    assert _declared(module) == [
        (_DEPENDENCY, "T+1Q", ("OP_BOTH",)),
        (_DEPENDENCY, "T+4Q", ("OP_BOTH",)),
    ]


def test_a_table_read_shifted_and_plain_declares_both_instances(
    fixture_session,
):
    """The plain operand used to be sent to the shifted instance."""
    _, module = _script(fixture_session, [(_SHIFTED_AND_PLAIN, "OP_MIX")])
    assert _declared(module) == [
        (_DEPENDENCY, "T", ("OP_MIX",)),
        (_DEPENDENCY, "T+1Q", ("OP_MIX",)),
    ]


def test_the_declared_instances_do_not_depend_on_input_order(fixture_session):
    """Whichever operation came first used to fix the period for both."""
    _, forward = _script(
        fixture_session, [(_SHIFT_Q1, "OP_Q1"), (_SHIFT_Q4, "OP_Q4")]
    )
    _, reverse = _script(
        fixture_session, [(_SHIFT_Q4, "OP_Q4"), (_SHIFT_Q1, "OP_Q1")]
    )
    assert sorted(_declared(forward)) == sorted(_declared(reverse))
    assert sorted(_declared(forward)) == [
        (_DEPENDENCY, "T+1Q", ("OP_Q1",)),
        (_DEPENDENCY, "T+4Q", ("OP_Q4",)),
    ]


def test_the_dependency_module_is_declared_once(fixture_session):
    """Two instances, one set of table and datapoint definitions."""
    _, module = _script(fixture_session, [(_TWO_TABLES, "OP_BOTH")])
    assert len(module["dependency_modules"]) == 1


def test_a_non_literal_shift_skips_only_its_own_operation(fixture_session):
    result, module = _script(
        fixture_session,
        [(_NON_LITERAL_SHIFT, "OP_BAD"), (_SHIFT_Q1, "OP_GOOD")],
    )
    assert list(result["failed_operations"]) == ["OP_BAD"]
    assert "integer literal" in result["failed_operations"]["OP_BAD"]
    assert "OP_BAD" not in module["operations"]
    assert "OP_GOOD" in module["operations"]
    assert _declared(module) == [(_DEPENDENCY, "T+1Q", ("OP_GOOD",))]


@pytest.mark.parametrize(
    ("shift", "expected"),
    [("1", "T-1Q"), ("-1", "T+1Q"), ("4", "T-4Q"), ("-4", "T+4Q")],
)
def test_the_declared_period_inverts_the_shift_sign(
    fixture_session, shift, expected
):
    """A forward and a backward shift used to report the same period."""
    expression = (
        "{tC_47.00, r0310, c0010} > "
        f"time_shift({{tC_01.00, r0020, c0010}}, Q, {shift}, refPeriod)"
        "[get refPeriod]"
    )
    _, module = _script(fixture_session, [(expression, "OP")])
    assert _declared(module) == [(_DEPENDENCY, expected, ("OP",))]
