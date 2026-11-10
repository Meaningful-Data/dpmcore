"""Integration regression: one module needed at several instances (#326).

The reference period is a property of a declared module and only one was
kept per module, so an operation reading two tables of the same
dependency module at different instances — or one table both plain and
shifted — was declared against a single instance and evaluated against
the wrong one. Every distinct period is now its own module reference
in the operation's ``requires``.

A shift number that is not an integer literal used to render as
``T-nQ``, which names no resolvable instance; it now needs the module
at a lag only known at run time. A range over refPeriod needs every
period it covers, and an if-then-else needs one of its branches. What a
precondition reads is needed by every operation it gates.

``C_47.00`` is a COREP_LR table (the home module here) and ``C_01.00`` /
``C_05.01`` are COREP_OF tables, so each expression crosses into a real
dependency module of the fixture dictionary.
"""

from __future__ import annotations

import pytest

from dpmcore.services.ast_generator import ASTGeneratorService

_MODULE_CODE = "COREP_LR"
_MODULE_VERSION = "3.1.0"
_DEPENDENCY = "COREP_OF"

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
_PARAMETER_SHIFT = (
    "{tC_47.00, r0310, c0010} > time_shift({tC_47.00, r0310, c0010}, "
    "A, {p_FREQ, integer}, refPeriod)[get refPeriod]"
)
_RANGE = (
    "{tC_47.00, r0310, c0010} <= 1.5 * avg({tC_01.00, r0020, c0010} "
    "over (order by refPeriod range between 2 Q preceding "
    "and current data point))"
)
_CONDITIONAL = (
    "{tC_47.00, r0310, c0010} > if {tC_47.00, r0370, c0010} > 0 "
    "then time_shift({tC_01.00, r0020, c0010}, Q, 1, refPeriod)"
    "[get refPeriod] "
    "else time_shift({tC_01.00, r0020, c0010}, Q, 2, refPeriod)"
    "[get refPeriod] endif"
)
_ONE_ARM_READING = (
    "{tC_47.00, r0310, c0010} > if {tC_47.00, r0370, c0010} > 0 "
    "then {tC_01.00, r0020, c0010} else 0 endif"
)
# The end of the previous financial year, one of four periods back.
_YEAR_END = (
    "with {tF_25.01.a, (c0030, c0040), default: 0, interval: true}: "
    "{r0010} = "
    "if (month({r0010}[get refPeriod]) - "
    "{p_FINANCIAL_YEAR_END_MONTH, integer}) in {0} "
    "then time_shift({r0120}, M, 12, refPeriod) "
    "else if (month({r0010}[get refPeriod]) - "
    "{p_FINANCIAL_YEAR_END_MONTH, integer}) in {(-9), 3} "
    "then time_shift({r0120}, M, 3, refPeriod) "
    "else if (month({r0010}[get refPeriod]) - "
    "{p_FINANCIAL_YEAR_END_MONTH, integer}) in {(-6), 6} "
    "then time_shift({r0120}, M, 6, refPeriod) "
    "else if (month({r0010}[get refPeriod]) - "
    "{p_FINANCIAL_YEAR_END_MONTH, integer}) in {(-3), 9} "
    "then time_shift({r0120}, M, 9, refPeriod) "
    "endif endif endif endif"
)
# The third branch reads C_18.00, of COREP_OF and of IF_CLASS2.
_YEAR_END_OR_OWN_FUNDS = _YEAR_END.replace(
    "time_shift({r0120}, M, 6, refPeriod)", "{tC_18.00, r0012, c0010, s0001}"
)
_UNBOUNDED_RANGE = (
    "{tC_47.00, r0310, c0010} <= 1.5 * avg({tC_01.00, r0020, c0010} "
    "over (order by refPeriod range between unbounded preceding "
    "and current data point))"
)


def _script(session, expressions, preconditions=None):
    result = ASTGeneratorService(session).script(
        expressions=expressions,
        module_code=_MODULE_CODE,
        module_version=_MODULE_VERSION,
        preconditions=preconditions,
    )
    assert result["success"], result["error"]
    module = result["enriched_ast"]
    return result, module


def _requires(module):
    """The ``requires`` of each operation, by code."""
    return {
        code: group["requires"]
        for group in module["dependency_groups"].values()
        for code in group["validations"]
    }


def _ref(lag):
    """A reference to the dependency module, ``lag`` quarters away."""
    ref = {"code": _DEPENDENCY, "ref_date_lag": lag}
    if lag:
        ref["ref_date_lag_unit"] = "Q"
    return ref


def _both(left, right):
    return {"and": {"left": left, "right": right, "decided_by": "scope"}}


def test_two_shifted_tables_of_one_module_declare_both_instances(
    fixture_session,
):
    _, module = _script(fixture_session, [(_TWO_TABLES, "OP_BOTH")])
    assert _requires(module) == {"OP_BOTH": _both(_ref(1), _ref(4))}


def test_a_table_read_shifted_and_plain_declares_both_instances(
    fixture_session,
):
    """The plain operand used to be sent to the shifted instance."""
    _, module = _script(fixture_session, [(_SHIFTED_AND_PLAIN, "OP_MIX")])
    assert _requires(module) == {"OP_MIX": _both(_ref(0), _ref(1))}


def test_the_declared_instances_do_not_depend_on_input_order(fixture_session):
    """Whichever operation came first used to fix the period for both."""
    _, forward = _script(
        fixture_session, [(_SHIFT_Q1, "OP_Q1"), (_SHIFT_Q4, "OP_Q4")]
    )
    _, reverse = _script(
        fixture_session, [(_SHIFT_Q4, "OP_Q4"), (_SHIFT_Q1, "OP_Q1")]
    )
    assert _requires(forward) == _requires(reverse)
    assert _requires(forward) == {
        "OP_Q1": {"is": _ref(1)},
        "OP_Q4": {"is": _ref(4)},
    }


def test_a_non_literal_shift_needs_the_module_at_a_run_time_lag(
    fixture_session,
):
    result, module = _script(
        fixture_session,
        [(_NON_LITERAL_SHIFT, "OP_COMPUTED"), (_PARAMETER_SHIFT, "OP_PARAM")],
    )
    assert result["failed_operations"] == {}
    assert _requires(module) == {
        "OP_COMPUTED": {
            "is": {
                "code": _DEPENDENCY,
                "ref_date_lag": None,
                "ref_date_lag_unit": "Q",
            }
        },
        "OP_PARAM": {
            "is": {
                "code": _MODULE_CODE,
                "ref_date_lag": None,
                "ref_date_lag_unit": "A",
            }
        },
    }


def test_a_range_needs_every_period_it_covers(fixture_session):
    _, module = _script(fixture_session, [(_RANGE, "OP_RANGE")])
    assert _requires(module) == {
        "OP_RANGE": _both(_ref(0), _both(_ref(-1), _ref(-2)))
    }


def test_an_unbounded_range_has_no_group(fixture_session):
    result, module = _script(
        fixture_session, [(_UNBOUNDED_RANGE, "OP_BAD"), (_SHIFT_Q1, "OP_GOOD")]
    )
    assert list(result["failed_operations"]) == ["OP_BAD"]
    assert "range window" in result["failed_operations"]["OP_BAD"]
    assert _requires(module) == {"OP_GOOD": {"is": _ref(1)}}


@pytest.mark.parametrize(
    ("shift", "expected"),
    [("1", -1), ("-1", 1), ("4", -4), ("-4", 4)],
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
    assert _requires(module) == {"OP": {"is": _ref(expected)}}


def _either(left, right):
    return {"or": {"left": left, "right": right, "decided_by": "condition"}}


def test_an_if_then_else_needs_one_of_its_branches(fixture_session):
    _, module = _script(
        fixture_session,
        [(_CONDITIONAL, "OP_COND"), (_ONE_ARM_READING, "OP_ONE_ARM")],
    )
    assert _requires(module) == {
        "OP_COND": _either(_ref(-1), _ref(-2)),
        # The else branch reads nothing else: no alternative to the then.
        "OP_ONE_ARM": {"is": _ref(0)},
    }


def _year_end(months):
    return {
        "code": "FINREP9",
        "ref_date_lag": -months,
        "ref_date_lag_unit": "M",
    }


def test_a_chain_of_conditions_needs_any_of_its_periods(fixture_session):
    result = ASTGeneratorService(fixture_session).script(
        expressions=[
            (_YEAR_END, "EGDQ_0663"),
            (_YEAR_END_OR_OWN_FUNDS, "EGDQ_0663_OF"),
        ],
        module_code="FINREP9",
        module_version="3.3.0",
    )
    assert result["success"], result["error"]

    either_module = {
        "or": {
            "left": {"code": "COREP_OF", "ref_date_lag": 0},
            "right": {"code": "IF_CLASS2", "ref_date_lag": 0},
            "decided_by": "scope",
        }
    }
    assert _requires(result["enriched_ast"]) == {
        "EGDQ_0663": _either(
            _year_end(3),
            _either(_year_end(6), _either(_year_end(9), _year_end(12))),
        ),
        # The modules either scope admits, inside the branch reading them.
        "EGDQ_0663_OF": _either(
            _year_end(3),
            _either(_year_end(9), _either(_year_end(12), either_module)),
        ),
    }


# _SHIFT_Q1 reads COREP_OF a quarter ahead, whatever gates it.
@pytest.mark.parametrize(
    ("gate", "requires"),
    [
        ("{tC_47.00, r0370, c0010} > 0", {"is": _ref(1)}),
        ("{tC_01.00, r0020, c0010} > 0", _both(_ref(0), _ref(1))),
        (
            "time_shift({tC_47.00, r0370, c0010}, Q, 1, refPeriod) > 0",
            _both(
                {
                    "code": _MODULE_CODE,
                    "ref_date_lag": -1,
                    "ref_date_lag_unit": "Q",
                },
                _ref(1),
            ),
        ),
        (
            "{v_C_47.00} and {tC_01.00, r0020, c0010} > 0",
            _both(_ref(0), _ref(1)),
        ),
    ],
)
def test_what_a_precondition_reads_its_operations_need(
    fixture_session, gate, requires
):
    result, module = _script(
        fixture_session,
        [(_SHIFT_Q1, "OP_GATED"), (_SHIFT_Q4, "OP_FREE")],
        preconditions=[(gate, ["OP_GATED"])],
    )
    assert result["failed_operations"] == {}
    (precondition,) = module["preconditions"].values()
    assert precondition["affected_operations"] == ["OP_GATED"]
    assert _requires(module) == {
        "OP_GATED": requires,
        "OP_FREE": {"is": _ref(4)},
    }


def test_a_precondition_that_is_no_single_boolean_fails_its_operations(
    fixture_session,
):
    result, module = _script(
        fixture_session,
        [(_SHIFT_Q1, "OP_GATED"), (_SHIFT_Q4, "OP_FREE")],
        preconditions=[("{tC_47.00, c0010} > 0", ["OP_GATED"])],
    )
    assert list(result["failed_operations"]) == ["OP_GATED"]
    assert "boolean scalar" in result["failed_operations"]["OP_GATED"]
    assert module["preconditions"] == {}
    assert list(module["operations"]) == ["OP_FREE"]
