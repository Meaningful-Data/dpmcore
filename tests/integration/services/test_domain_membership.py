"""Out-of-domain item comparisons against the real dictionary (#332).

Every domain named below is measured against the shipped DPM 4.2.1 fixture,
not hand-built. At release ``4.2.1``:

* ``{tC_14.00, c0060}`` takes items from ``qPO``, ``c0061`` from ``qST`` and
  ``c0160`` from ``qTU`` -- so ``eba_PL:x72`` (``PL``), ``eba_RT:x14``
  (``RT``) and ``eba_UE:x23`` (``UE``) are all impossible there, which is what
  the shipped ``v7368_m`` and ``v7364_m`` do. ``qPO`` and ``qTU`` are
  super-categories, so their value set is their own items plus those of the
  categories composing them (#359).
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
        # qPO is a super-category: qOR and qPL are in its value set,
        # PL is not.
        assert "domain qOR, qPL, qPO" in dead_member
        assert "this member of the set never matches" in dead_member
        always_true = next(w for w in warnings if "eba_RT:x14" in w)
        assert "domain qST" in always_true
        assert "the comparison is always true" in always_true

    def test_v7364_m_reports_only_the_member_outside_the_value_set(
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

        # c0040 is qST, so the three qST members are silent. c0160 is the
        # super-category qTU, which composes qFI among others, so only
        # ``eba_UE:x23`` is impossible there (#359).
        (warning,) = warnings
        assert "eba_UE:x23" in warning
        assert "domain qAI, qFI, qSR, qTA, qTU" in warning

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


class TestSuperCategories:
    """A super-category's value set is its own items plus its members'.

    ``{tC_14.00, c0160}`` is typed on ``qTU``, which composes ``qAI``,
    ``qFI``, ``qSR`` and ``qTA`` and holds a single item of its own. The
    18 items the column actually offers come almost entirely from the
    members, so judging them against ``qTU`` alone condemned all of them.
    """

    def test_the_reported_expression_is_silent(self, semantic):
        """The expression the issue was raised with (#359)."""
        expression = (
            "with {tC_14.00}: if {c0446} and {c0160} in "
            "{[eba_qFI:qx2366], [eba_qFI:qx2369], [eba_qFI:qx2370], "
            "[eba_qFI:qx2372], [eba_qFI:qx2374]} then "
            "{c0223, default: 0} / 0.08 <= 0.75 endif"
        )

        assert _domain_warnings(semantic, expression) == []

    @pytest.mark.parametrize(
        "signature",
        [
            "eba_qAI:qx2006",
            "eba_qFI:qx2366",
            "eba_qSR:qx2018",
            "eba_qTA:qx2042",
        ],
    )
    def test_an_item_of_each_composing_category_is_silent(
        self, semantic, signature
    ):
        expression = f"{{tC_14.00, c0160}} = [{signature}]"

        assert _domain_warnings(semantic, expression) == []

    def test_the_super_categorys_own_item_is_silent(self, semantic):
        expression = "{tC_14.00, c0160} = [eba_qTU:qx0]"

        assert _domain_warnings(semantic, expression) == []

    def test_an_item_outside_every_composing_category_still_warns(
        self, semantic
    ):
        expression = "{tC_14.00, c0160} = [eba_qCQ:qx2060]"

        (warning,) = _domain_warnings(semantic, expression)

        assert "domain qCQ" in warning
        assert "domain qAI, qFI, qSR, qTA, qTU" in warning
        assert "the comparison is never true" in warning


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
