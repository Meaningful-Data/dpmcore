"""Out-of-domain item comparisons against the real dictionary (#332).

Every domain named below is measured against the shipped DPM 4.2.1 fixture,
not hand-built. At release ``4.2.1``:

* ``{tC_14.00, c0060}`` takes items from ``qPO``, ``c0061`` from ``qST`` and
  ``c0160`` from ``qTU`` -- so ``eba_PL:x72`` (``PL``), ``eba_RT:x14``
  (``RT``) and ``eba_UE:x23`` (``UE``) are all impossible there, which is what
  the shipped ``v7368_m`` and ``v7364_m`` do.
* ``{tF_00.01, r0010, c0010}`` takes items from ``qAS`` while the pre-refit
  ``eba_AS:x2`` is still in ``AS`` -- the domain rename that five more shipped
  operations were never updated for.
* ``C_09.01.a`` has the enumerated open key ``CEG``, whose domain is ``GA``.
* ``{tF_40.01, c0095}`` takes items from ``qSR``.

The warning must never become an error: the operations above ship in 4.2.1 and
have to keep validating.
"""

from __future__ import annotations

import pytest

from dpmcore.services.semantic import SemanticService

RELEASE = "4.2.1"

MARKER = "takes items from domain"


@pytest.fixture
def semantic(fixture_session):
    return SemanticService(fixture_session)


def _domain_warnings(semantic, expression):
    result = semantic.validate(expression, release_code=RELEASE)
    assert result.is_valid, result.error_message
    return [
        line for line in (result.warning or "").splitlines() if MARKER in line
    ]


class TestShippedOperations:
    """The 4.2.1 operations the issue was raised from."""

    def test_v7368_m_reports_its_dead_set_member_and_inequality(
        self, semantic
    ):
        expression = (
            "with {tC_14.00, interval: true}:"
            "if ( {c0060} in { [eba_qPO:qx2001], [eba_PL:x72] }"
            "     and {c0171} >= 0.95"
            "     and {c0061} != [eba_RT:x14] )"
            "then not( isnull({c0222}) )endif"
        )

        warnings = _domain_warnings(semantic, expression)

        assert len(warnings) == 2
        dead_member = next(w for w in warnings if "eba_PL:x72" in w)
        assert "domain PL" in dead_member
        assert "domain qPO" in dead_member
        assert "this member of the set never matches" in dead_member
        always_true = next(w for w in warnings if "eba_RT:x14" in w)
        assert "domain qST" in always_true
        assert "the comparison is always true" in always_true

    def test_v7364_m_reports_both_members_of_an_unmatchable_set(
        self, semantic
    ):
        expression = (
            "with {tC_14.00, default: null, interval: false}: "
            "if ( {c0446} = true ) then "
            "( ({c0040} in { [eba_qST:qx2020], [eba_qST:qx2019], "
            "[eba_qST:qx2018] } or ({c0040} = [eba_qST:qx2005] and "
            "{c0160} in { [eba_qFI:qx2370], [eba_UE:x23] } )) ) endif"
        )

        warnings = _domain_warnings(semantic, expression)

        # c0040 is qST, so the three qST members are silent; c0160 is qTU, so
        # both of its members are impossible.
        assert len(warnings) == 2
        assert all("domain qTU" in w for w in warnings)
        assert any("eba_qFI:qx2370" in w for w in warnings)
        assert any("eba_UE:x23" in w for w in warnings)

    def test_the_pre_refit_accounting_standard_rename_is_reported(
        self, semantic
    ):
        expression = "{tF_00.01, r0010, c0010} = [eba_AS:x2]"

        (warning,) = _domain_warnings(semantic, expression)

        assert "domain AS" in warning
        assert "domain qAS" in warning
        assert "{ tF_00.01, r0010, c0010 }" in warning

    def test_the_refit_item_for_the_same_cell_is_silent(self, semantic):
        expression = "{tF_00.01, r0010, c0010} = [eba_qAS:qx2000]"

        assert _domain_warnings(semantic, expression) == []


class TestComponentKinds:
    def test_an_open_key_in_a_where_clause_is_checked(self, semantic):
        expression = "{tC_09.01.a, r0010, c0010}[where CEG = [eba_CU:EUR]]"

        (warning,) = _domain_warnings(semantic, expression)

        assert "but CEG takes items from domain GA" in warning
        assert "domain CU" in warning

    def test_an_open_key_holding_the_item_is_silent(self, semantic):
        expression = "{tC_09.01.a, r0010, c0010}[where CEG = [eba_GA:AT]]"

        assert _domain_warnings(semantic, expression) == []

    def test_a_sub_clause_value_is_checked(self, semantic):
        expression = "{tC_09.01.a, r0010, c0010}[sub CEG = [eba_CU:EUR]]"

        (warning,) = _domain_warnings(semantic, expression)

        assert "the substitution matches no record" in warning

    def test_a_get_clause_checks_the_promoted_key(self, semantic):
        expression = "{tC_09.01.a, r0010, c0010}[get CEG] = [eba_CU:EUR]"

        (warning,) = _domain_warnings(semantic, expression)

        assert "but CEG takes items from domain GA" in warning

    def test_the_fact_component_inside_a_where_clause_is_checked(
        self, semantic
    ):
        expression = (
            "{tF_40.01, c0095}[where f in {[eba_CT:x12], [eba_CT:x18]}]"
        )

        warnings = _domain_warnings(semantic, expression)

        assert len(warnings) == 2
        assert all("domain qSR" in w for w in warnings)

    def test_a_non_enumerated_component_is_never_judged(self, semantic):
        """``refPeriod`` is a date, not a member of any domain."""
        expression = (
            '{tC_09.01.a, r0010, c0010}[where refPeriod = "2026-12-31"]'
        )

        assert _domain_warnings(semantic, expression) == []
