"""Paired expression + precondition analysis against the real dictionary (#279).

Every module-version number below is measured against the shipped DPM 4.2.1
fixture, not hand-built: at release ``4.2.1``, ``F_01.02`` is hosted by FINREP9
(462) and FINREP9DP (513), and ``C_01.00`` by COREP_OF (499). Pairing a FINREP
expression with a COREP gate is therefore a real cross-framework case, which is
what makes the scope-change warning exercisable.
"""

from __future__ import annotations

import pytest

from dpmcore.services.scope_calculator import ScopeCalculatorService
from dpmcore.services.semantic import SemanticService

RELEASE = "4.2.1"

# Main expression: FINREP, hosted by two module versions.
MAIN = "{tF_01.02, r0010, c0010} >= 0"
# Gate on the same table — contributes an operand already present.
SAME_TABLE_GATE = "{tF_01.02, r0010, c0010} > 0"
# Gate on a COREP table — no module hosts both, so the scope widens.
CROSS_GATE = "{tC_01.00, r0010, c0010} > 0"
# Filing-indicator gate reported by COREP only.
CROSS_FI_GATE = "{v_C_01.00}"
# Filing-indicator gate reported by the expression's own modules.
OWN_FI_GATE = "{v_F_01.02}"

MAIN_MODULES = [462, 513]
CROSS_MODULES = [462, 499, 513]


@pytest.fixture
def scopes(fixture_session):
    return ScopeCalculatorService(fixture_session)


@pytest.fixture
def semantic(fixture_session):
    return SemanticService(fixture_session)


def _scope(svc, gate=None, **kwargs):
    return svc.calculate_from_expression(
        MAIN, release_code=RELEASE, precondition_expression=gate, **kwargs
    )


class TestBaselineIsUnchanged:
    def test_no_gate_matches_the_pre_change_result(self, scopes):
        result = _scope(scopes)
        assert not result.has_error
        assert result.total_scopes == 2
        assert not result.is_cross_module
        assert sorted(result.module_versions) == MAIN_MODULES
        assert result.warning is None
        assert result.error_source is None

    def test_gate_adding_no_operand_changes_nothing(self, scopes):
        gated = _scope(scopes, SAME_TABLE_GATE)
        assert not gated.has_error
        assert gated.warning is None
        assert sorted(gated.module_versions) == MAIN_MODULES
        assert gated.total_scopes == 2

    def test_own_module_filing_indicator_gate_changes_nothing(self, scopes):
        gated = _scope(scopes, OWN_FI_GATE)
        assert not gated.has_error
        assert gated.warning is None
        assert sorted(gated.module_versions) == MAIN_MODULES


class TestScopeChangeWarning:
    def test_cross_framework_table_gate_widens_the_scope(self, scopes):
        gated = _scope(scopes, CROSS_GATE)
        assert not gated.has_error
        assert gated.is_cross_module
        assert sorted(gated.module_versions) == CROSS_MODULES
        assert gated.warning is not None
        assert "[462, 513] -> [462, 499, 513]" in gated.warning
        assert "tables C_01.00" in gated.warning

    def test_cross_framework_filing_indicator_gate_empties_the_scope(
        self, scopes
    ):
        # No module version hosts F_01.02 and reports the COREP filing
        # indicator, so the pair cannot be evaluated anywhere. That is not an
        # error, but it must not be silent either.
        gated = _scope(scopes, CROSS_FI_GATE)
        assert not gated.has_error
        assert gated.total_scopes == 0
        assert gated.module_versions == []
        assert gated.warning is not None
        assert "not evaluable in any module version" in gated.warning
        assert "filing indicators C_01.00" in gated.warning


class TestDisjunctiveGate:
    def test_disjunction_does_not_constrain_the_scope(self, scopes):
        # A flat union of these three filing indicators resolves to 1-14 on the
        # real dictionary; only the mandatory (intersected) set is passed on,
        # which for a pure disjunction is empty.
        gate = "{v_C_06.02} or {v_C_105.01} or {v_C_27.00}"
        gated = _scope(scopes, gate)
        assert not gated.has_error
        assert sorted(gated.module_versions) == MAIN_MODULES
        assert gated.warning is None

    def test_conjunct_inside_a_disjunction_still_constrains(self, scopes):
        # ``A and (B or C)`` requires A, so the COREP indicator still applies
        # and still empties the scope.
        gate = "{v_C_01.00} and ({v_C_06.02} or {v_C_105.01})"
        gated = _scope(scopes, gate)
        assert gated.total_scopes == 0
        assert gated.warning is not None


class TestErrorAttribution:
    def test_unknown_gate_table_is_attributed_and_prefixed(self, scopes):
        gated = _scope(scopes, "{tNOPE, r0010, c0010} > 0")
        assert gated.has_error
        assert gated.error_source == "precondition"
        assert gated.error_message.startswith("Precondition: ")

    def test_unknown_gate_variable_is_attributed(self, scopes):
        gated = _scope(scopes, "{v_NOPE}")
        assert gated.has_error
        assert gated.error_source == "precondition"
        assert gated.error_message.startswith("Precondition: ")

    def test_broken_expression_is_attributed_to_the_expression(self, scopes):
        result = scopes.calculate_from_expression(
            "{tNOPE, r0010, c0010} >= 0",
            release_code=RELEASE,
            precondition_expression=SAME_TABLE_GATE,
        )
        assert result.has_error
        assert result.error_source == "expression"
        assert not result.error_message.startswith("Precondition: ")

    def test_message_is_unprefixed_when_no_gate_is_supplied(self, scopes):
        result = scopes.calculate_from_expression(
            "{tNOPE, r0010, c0010} >= 0", release_code=RELEASE
        )
        assert result.has_error
        assert not result.error_message.startswith("Precondition: ")
        assert result.warning is None


class TestValidateWithPrecondition:
    def test_both_halves_valid(self, semantic):
        result = semantic.validate(MAIN, CROSS_GATE, release_code=RELEASE)
        assert result.is_valid
        assert result.precondition.is_valid
        assert result.error_source is None

    def test_no_gate_leaves_the_field_none(self, semantic):
        result = semantic.validate(MAIN, release_code=RELEASE)
        assert result.is_valid
        assert result.precondition is None

    def test_filing_indicator_gate_is_valid(self, semantic):
        result = semantic.validate(MAIN, CROSS_FI_GATE, release_code=RELEASE)
        assert result.is_valid

    def test_non_boolean_gate_fails_the_pair_with_2_1(self, semantic):
        # The same string is a perfectly valid main expression; it is only
        # invalid *as a gate*, because a gate must evaluate to a boolean.
        numeric = "{tC_01.00, r0010, c0010}"
        assert semantic.validate(numeric, release_code=RELEASE).is_valid

        result = semantic.validate(MAIN, numeric, release_code=RELEASE)
        assert not result.is_valid
        assert result.error_source == "precondition"
        assert result.error_code == "2-1"
        assert result.error_message.startswith("Precondition: ")
        assert result.precondition.error_code == "2-1"

    def test_broken_gate_invalidates_the_pair(self, semantic):
        result = semantic.validate(
            MAIN, "{tNOPE, r0010, c0010} > 0", release_code=RELEASE
        )
        assert not result.is_valid
        assert result.error_source == "precondition"
        assert not result.precondition.is_valid

    def test_broken_expression_is_attributed_to_the_expression(self, semantic):
        result = semantic.validate(
            "{tNOPE, r0010, c0010} >= 0", CROSS_GATE, release_code=RELEASE
        )
        assert not result.is_valid
        assert result.error_source == "expression"
        assert not result.error_message.startswith("Precondition: ")
        assert result.precondition.is_valid

    def test_both_halves_broken_names_both(self, semantic):
        result = semantic.validate(
            "{tNOPE, r0010, c0010} >= 0",
            "{v_ALSONOPE}",
            release_code=RELEASE,
        )
        assert not result.is_valid
        assert result.error_source == "both"
        # The expression's own failure and the gate's are both named, so the
        # caller does not fix one and then discover the other.
        assert "NOPE, r0010, c0010" in result.error_message
        assert "Precondition: " in result.error_message
        assert "ALSONOPE" in result.error_message
        assert result.error_code == "1-2"
        assert result.precondition.error_code == "1-3"

    def test_published_state_describes_the_main_expression(self, semantic):
        # The gate selects C_01.00; the main expression selects F_01.02. After
        # the call, the state consumers read must be the main expression's.
        semantic.validate(MAIN, CROSS_GATE, release_code=RELEASE)
        assert list(semantic.oc_tables) == ["F_01.02"]

    def test_cross_half_parameter_conflict_fails_the_pair(self, semantic):
        result = semantic.validate(
            "{tF_01.02, r0010, c0010} >= {p_thr, number}",
            "{tC_01.00, r0010, c0010} > {p_thr, integer}",
            release_code=RELEASE,
        )
        assert not result.is_valid
        assert result.error_source == "precondition"
        assert result.error_code == "3-8"

    def test_cross_half_parameter_agreement_passes(self, semantic):
        result = semantic.validate(
            "{tF_01.02, r0010, c0010} >= {p_thr, number}",
            "{tC_01.00, r0010, c0010} > {p_thr, number}",
            release_code=RELEASE,
        )
        assert result.is_valid

    def test_unknown_release_code_is_mirrored_onto_the_gate(self, semantic):
        result = semantic.validate(MAIN, CROSS_GATE, release_code="9.9.9")
        assert not result.is_valid
        assert result.error_message == result.precondition.error_message

    def test_is_valid_shortcut_is_pair_wide(self, semantic):
        assert semantic.is_valid(MAIN, CROSS_GATE, release_code=RELEASE)
        assert not semantic.is_valid(
            MAIN, "{tC_01.00, r0010, c0010}", release_code=RELEASE
        )
