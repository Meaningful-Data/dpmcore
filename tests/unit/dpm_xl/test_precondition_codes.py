"""Tests for the shared precondition-code extractors (issue #279).

``required_precondition_codes`` is the one scope calculation may use: it counts
each returned code as an operand a module must supply, so a disjunctive gate
has to return the *intersection* of its branches. Flattening instead is not a
theoretical problem — of the 965 precondition expressions persisted in the EBA
dictionary, 62 use ``or``, and the widest flattens to 20 filing indicators
spanning frameworks, which no module reports together.
"""

import pytest

from dpmcore.services._precondition_codes import (
    extract_precondition_codes,
    required_precondition_codes,
)
from dpmcore.services.syntax import SyntaxService


def _ast(expression):
    return SyntaxService().parse(expression)


class TestExtractPreconditionCodes:
    """Every variable code the gate mentions, first-seen order."""

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("{v_C_01.00}", ["C_01.00"]),
            ("{v_C_09.01} and {v_C_07.00}", ["C_09.01", "C_07.00"]),
            ("{v_B} or {v_A}", ["B", "A"]),
            ("not {v_C_01.00}", ["C_01.00"]),
            # A cell selection is a table reference, not a variable one.
            ("{tC_01.00, r0010, c0010} > 0", []),
            # Mixed: only the variable half is collected here.
            ("{v_C_01.00} and {tC_01.00, r0010, c0010} > 0", ["C_01.00"]),
        ],
    )
    def test_collects_variable_codes(self, expression, expected):
        assert extract_precondition_codes(_ast(expression)) == expected

    def test_dedupes_preserving_first_seen_order(self):
        ast = _ast("{v_B} and {v_A} and {v_B}")
        assert extract_precondition_codes(ast) == ["B", "A"]

    def test_unwalkable_input_returns_empty(self):
        # Logged and swallowed: a malformed AST must not abort the caller.
        assert extract_precondition_codes(object()) == []


class TestRequiredPreconditionCodes:
    """Only the codes a module *must* provide to evaluate the gate."""

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            # A bare reference is mandatory.
            ("{v_C_01.00}", ["C_01.00"]),
            # ``and`` unions its branches' requirements.
            ("{v_C_09.01} and {v_C_07.00}", ["C_09.01", "C_07.00"]),
            # ``or`` intersects: neither branch is individually required.
            ("{v_A} or {v_B}", []),
            ("{v_A} xor {v_B}", []),
            # Nested: only the conjunct survives the disjunction.
            ("{v_F_31.01} and ({v_F_09.01} or {v_F_09.01.1})", ["F_31.01"]),
            # A wide disjunction requires nothing — the case that would
            # otherwise resolve to 1-14 on the real dictionary.
            ("{v_C_06.02} or {v_C_105.01} or {v_C_27.00}", []),
            # ``not`` requires nothing: the gate holds when the code does not.
            ("not {v_C_01.00}", []),
            ("not ({v_A} or {v_B})", []),
            # A comparison is opaque, so its operands stay required.
            ("{v_C_01.00} and {tC_01.00, r0010, c0010} > 0", ["C_01.00"]),
        ],
    )
    def test_mandatory_set(self, expression, expected):
        assert required_precondition_codes(_ast(expression)) == expected

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("not {v_A} and {v_B}", ["B"]),
            ("{v_A} and not {v_B}", ["A"]),
        ],
    )
    def test_a_negated_conjunct_drops_out_of_the_union(
        self, expression, expected
    ):
        """A negated code is dropped even inside a conjunction.

        The set is "codes that must be **true**", not "codes the engine has
        to read" — the same criterion that makes ``{v_A} or {v_B}`` require
        neither. Each returned code is counted as an operand the module must
        supply, so requiring the operand of a ``not`` would exclude exactly
        the modules a "template not filed" gate is written for.
        """
        assert required_precondition_codes(_ast(expression)) == expected

    def test_repeated_disjunct_is_still_optional(self):
        # ``{v_A} or {v_A}`` intersects to {A}: every branch needs it.
        assert required_precondition_codes(_ast("{v_A} or {v_A}")) == ["A"]

    def test_never_exceeds_the_flat_set(self):
        expression = "{v_F_31.01} and ({v_F_09.01} or {v_F_09.01.1})"
        ast = _ast(expression)
        flat = extract_precondition_codes(ast)
        assert set(required_precondition_codes(ast)) <= set(flat)

    def test_unwalkable_input_returns_empty(self):
        assert required_precondition_codes(object()) == []


class TestIssueExampleIsNotValidDpmXl:
    """Pin the malformed gate quoted in issue #279.

    ``{v_C_07.00, r0010, c0010} > 0`` cannot parse: ``varRef`` takes no
    arguments. The real forms are ``{v_C_07.00}`` (filing indicator) or
    ``{tC_07.00, r0010, c0010} > 0`` (data cell).
    """

    def test_issue_example_does_not_parse(self):
        result = SyntaxService().validate("{v_C_07.00, r0010, c0010} > 0")
        assert not result.is_valid

    @pytest.mark.parametrize(
        "expression",
        ["{v_C_07.00}", "{tC_07.00, r0010, c0010} > 0"],
    )
    def test_intended_forms_do_parse(self, expression):
        assert SyntaxService().validate(expression).is_valid
