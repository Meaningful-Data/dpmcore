"""Tests for the out-of-domain item comparison warning (issue #332).

Comparing an enumerated component with an item from a different domain is
accepted by every other check but can never hold. These tests drive
``DomainMembershipChecker`` over hand-built ASTs with the two dictionary
lookups stubbed, so the traversal and the decision rules are exercised
without a database.
"""

from __future__ import annotations

import pandas as pd
import pytest

from dpmcore.dpm_xl.ast import domain_membership
from dpmcore.dpm_xl.ast.domain_membership import (
    DomainMembershipChecker,
    _item_literals,
)
from dpmcore.dpm_xl.ast.nodes import (
    BinOp,
    Constant,
    Dimension,
    FilterOp,
    GetOp,
    ParameterRef,
    ParExpr,
    RenameNode,
    RenameOp,
    Scalar,
    Set,
    SubAssignment,
    SubOp,
    VarID,
    WhereClauseOp,
)
from dpmcore.dpm_xl.warning_collector import collect_warnings

# property_id -> domain, as the dictionary would resolve it at a release.
PROPERTY_DOMAINS = {
    901: {"qPO"},
    902: {"qST"},
    903: {"qAS"},
    # A property in a non-enumerated category resolves to no domain.
    904: set(),
}

# item signature -> domain.
ITEM_DOMAINS = {
    "eba_qPO:qx2001": {"qPO"},
    "eba_PL:x72": {"PL"},
    "eba_RT:x14": {"RT"},
    "eba_AS:x2": {"AS"},
    "eba_qAS:qx1": {"qAS"},
}


@pytest.fixture(autouse=True)
def stub_dictionary(monkeypatch):
    """Answer both domain lookups from the tables above."""

    def properties(session, property_ids, release_id=None):
        return {
            property_id: PROPERTY_DOMAINS[property_id]
            for property_id in property_ids
            if PROPERTY_DOMAINS.get(property_id)
        }

    def items(session, signatures, release_id=None):
        return {
            signature: ITEM_DOMAINS[signature]
            for signature in signatures
            if signature in ITEM_DOMAINS
        }

    monkeypatch.setattr(
        domain_membership.PropertyCategoryQuery,
        "get_property_domains",
        staticmethod(properties),
    )
    monkeypatch.setattr(
        domain_membership.ItemCategoryQuery,
        "get_item_domains",
        staticmethod(items),
    )


@pytest.fixture
def fixture_keys(monkeypatch):
    """Answer every ``sub`` target with property 901, recording the lookups."""
    asked: list[str] = []

    def get_keys(session, dimension_codes, release_id=None):
        asked.extend(dimension_codes)
        return pd.DataFrame(
            [
                {"property_id": 901, "property_code": code, "data_type": "e"}
                for code in dimension_codes
            ]
        )

    monkeypatch.setattr(
        domain_membership.ViewOpenKeysQuery,
        "get_keys",
        staticmethod(get_keys),
    )
    return asked


def _selection(*property_ids, table="C_14.00", cols=("0060",)):
    """A cell selection resolving to one data point per property."""
    node = VarID(
        table=table,
        rows=None,
        cols=list(cols) if cols else None,
        sheets=None,
        interval=None,
        default=None,
    )
    node.data = pd.DataFrame({"property_id": list(property_ids)})
    return node


def _item(signature):
    return Scalar(item=signature, scalar_type="Item")


def _run(node) -> list[str]:
    with collect_warnings() as wc:
        DomainMembershipChecker(session=None, ast=node, release_id=None)
        return wc.get_warnings()


class TestComparisonOperators:
    def test_equality_against_a_foreign_domain_warns(self):
        node = BinOp(_selection(901), "=", _item("eba_PL:x72"))

        (warning,) = _run(node)

        assert "[eba_PL:x72]" in warning
        assert "domain PL" in warning
        assert "domain qPO" in warning
        assert "the comparison is never true" in warning

    def test_inequality_reports_the_opposite_effect(self):
        node = BinOp(_selection(902), "!=", _item("eba_RT:x14"))

        (warning,) = _run(node)

        assert "the comparison is always true" in warning

    def test_item_inside_the_domain_is_silent(self):
        node = BinOp(_selection(901), "=", _item("eba_qPO:qx2001"))

        assert _run(node) == []

    def test_operand_order_does_not_matter(self):
        node = BinOp(_item("eba_PL:x72"), "=", _selection(901))

        (warning,) = _run(node)

        assert "the comparison is never true" in warning

    def test_parentheses_do_not_hide_either_side(self):
        node = BinOp(
            ParExpr(_selection(901)), "=", ParExpr(_item("eba_PL:x72"))
        )

        assert len(_run(node)) == 1

    def test_ordering_comparison_is_not_checked(self):
        """Only ``=``, ``!=`` and ``in`` take an item literal."""
        node = BinOp(_selection(901), ">", _item("eba_PL:x72"))

        assert _run(node) == []

    def test_two_literals_are_not_a_component(self):
        node = BinOp(_item("eba_PL:x72"), "=", _item("eba_RT:x14"))

        assert _run(node) == []


class TestSetMembership:
    def test_each_impossible_member_is_reported(self):
        node = BinOp(
            _selection(901),
            "in",
            Set([_item("eba_PL:x72"), _item("eba_RT:x14")]),
        )

        warnings = _run(node)

        assert len(warnings) == 2
        assert all(
            "this member of the set never matches" in w for w in warnings
        )

    def test_a_partly_dead_set_reports_only_the_dead_member(self):
        node = BinOp(
            _selection(901),
            "in",
            Set([_item("eba_qPO:qx2001"), _item("eba_PL:x72")]),
        )

        (warning,) = _run(node)

        assert "[eba_PL:x72]" in warning

    def test_a_repeated_member_is_reported_once(self):
        node = BinOp(
            _selection(901),
            "in",
            Set([_item("eba_PL:x72"), _item("eba_PL:x72")]),
        )

        (warning,) = _run(node)

        assert "[eba_PL:x72]" in warning

    def test_non_item_members_are_ignored(self):
        """A parameter member has no signature; the item member still counts."""
        node = BinOp(
            _selection(901),
            "in",
            Set(
                [
                    ParameterRef(code="p_x", param_type="item"),
                    _item("eba_PL:x72"),
                ]
            ),
        )

        (warning,) = _run(node)

        assert "[eba_PL:x72]" in warning

    def test_empty_set_is_silent(self):
        node = BinOp(_selection(901), "in", Set([]))

        assert _run(node) == []

    def test_constant_set_is_silent(self):
        node = BinOp(
            _selection(901),
            "in",
            Set([Constant(type_="Integer", value=1)]),
        )

        assert _run(node) == []


class TestComponentResolution:
    def test_a_selection_spanning_two_domains_accepts_either(self):
        """Warn only when the item belongs to none of the domains spanned."""
        node = BinOp(_selection(901, 903), "=", _item("eba_qAS:qx1"))

        assert _run(node) == []

    def test_a_selection_spanning_two_domains_still_rejects_a_third(self):
        node = BinOp(_selection(901, 903), "=", _item("eba_PL:x72"))

        assert len(_run(node)) == 1

    def test_a_non_enumerated_component_is_never_judged(self):
        node = BinOp(_selection(904), "=", _item("eba_PL:x72"))

        assert _run(node) == []

    def test_one_unresolvable_data_point_silences_the_selection(self):
        """The item cannot be ruled out when part of the span is unknown."""
        node = BinOp(_selection(901, 904), "=", _item("eba_PL:x72"))

        assert _run(node) == []

    def test_a_selection_without_resolved_data_is_skipped(self):
        node = VarID(
            table="C_14.00",
            rows=None,
            cols=["0060"],
            sheets=None,
            interval=None,
            default=None,
        )

        assert _run(BinOp(node, "=", _item("eba_PL:x72"))) == []

    def test_a_grey_data_point_silences_the_selection(self):
        node = _selection(901)
        node.data = pd.DataFrame({"property_id": [901, None]})

        assert _run(BinOp(node, "=", _item("eba_PL:x72"))) == []

    def test_an_unknown_item_is_left_to_the_not_found_check(self):
        node = BinOp(_selection(901), "=", _item("eba_ZZ:x999"))

        assert _run(node) == []

    def test_rename_preserves_the_fact_component_domain(self):
        renamed = RenameOp(
            _selection(901), [RenameNode(old_name="r", new_name="row")]
        )

        assert len(_run(BinOp(renamed, "=", _item("eba_PL:x72")))) == 1

    def test_filter_preserves_the_fact_component_domain(self):
        filtered = FilterOp(
            selection=_selection(901),
            condition=BinOp(_selection(901), ">", Constant("Integer", 0)),
        )

        assert len(_run(BinOp(filtered, "=", _item("eba_PL:x72")))) == 1

    def test_an_item_is_looked_up_once_across_comparisons(self):
        """The second comparison answers from the per-expression cache."""
        node = BinOp(
            BinOp(_selection(901), "=", _item("eba_PL:x72")),
            "and",
            BinOp(_selection(902), "=", _item("eba_PL:x72")),
        )

        assert len(_run(node)) == 2


class TestOpenKeys:
    def test_an_open_key_is_resolved_from_its_property(self):
        condition = BinOp(
            Dimension("qPO", property_id=901), "=", _item("eba_PL:x72")
        )
        node = WhereClauseOp(_selection(902), condition)

        (warning,) = _run(node)

        assert "but qPO takes items from domain qPO" in warning

    def test_the_fact_component_resolves_against_the_clause_operand(self):
        condition = BinOp(Dimension("f"), "=", _item("eba_PL:x72"))
        node = WhereClauseOp(_selection(902), condition)

        (warning,) = _run(node)

        assert "domain qST" in warning

    def test_an_implicit_open_key_is_skipped(self):
        """``refPeriod`` and friends carry the ``-1`` sentinel."""
        condition = BinOp(
            Dimension("refPeriod", property_id=-1), "=", _item("eba_PL:x72")
        )
        node = WhereClauseOp(_selection(902), condition)

        assert _run(node) == []

    def test_an_unenriched_dimension_is_skipped(self):
        condition = BinOp(Dimension("qPO"), "=", _item("eba_PL:x72"))
        node = WhereClauseOp(_selection(902), condition)

        assert _run(node) == []

    def test_get_promotes_the_key_to_the_fact_component(self):
        node = BinOp(GetOp(_selection(902), "qPO"), "=", _item("eba_PL:x72"))
        node.left.property_id = 901

        (warning,) = _run(node)

        # The domain checked is the key's (qPO), not the operand's (qST).
        assert "domain qPO" in warning

    def test_a_bare_fact_dimension_outside_a_clause_is_skipped(self):
        assert _run(BinOp(Dimension("f"), "=", _item("eba_PL:x72"))) == []

    def test_an_open_key_with_no_enumerated_domain_is_skipped(self):
        condition = BinOp(
            Dimension("qDT", property_id=904), "=", _item("eba_PL:x72")
        )
        node = WhereClauseOp(_selection(902), condition)

        assert _run(node) == []


class TestSubClause:
    def test_an_out_of_domain_substitution_warns(self, monkeypatch):
        monkeypatch.setattr(
            DomainMembershipChecker,
            "_sub_property_id",
            lambda self, code: 901,
        )
        node = SubOp(
            _selection(902), [SubAssignment("qPO", _item("eba_PL:x72"))]
        )

        (warning,) = _run(node)

        assert "the substitution matches no record" in warning

    def test_an_in_domain_substitution_is_silent(self, monkeypatch):
        monkeypatch.setattr(
            DomainMembershipChecker,
            "_sub_property_id",
            lambda self, code: 901,
        )
        node = SubOp(
            _selection(902), [SubAssignment("qPO", _item("eba_qPO:qx2001"))]
        )

        assert _run(node) == []

    def test_an_unresolvable_target_is_skipped(self, monkeypatch):
        monkeypatch.setattr(
            DomainMembershipChecker,
            "_sub_property_id",
            lambda self, code: None,
        )
        node = SubOp(
            _selection(902), [SubAssignment("qPO", _item("eba_PL:x72"))]
        )

        assert _run(node) == []

    def test_a_non_item_value_is_skipped(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            DomainMembershipChecker,
            "_sub_property_id",
            lambda self, code: called.append(code),
        )
        node = SubOp(
            _selection(902),
            [SubAssignment("qPO", Constant(type_="Integer", value=1))],
        )

        assert _run(node) == []
        assert called == []

    def test_a_target_is_looked_up_once_per_expression(self, fixture_keys):
        """The second ``sub`` on the same key answers from the cache."""
        node = SubOp(
            _selection(902),
            [
                SubAssignment("qPO", _item("eba_PL:x72")),
                SubAssignment("qPO", _item("eba_RT:x14")),
            ],
        )

        assert len(_run(node)) == 2
        assert fixture_keys == ["qPO"]

    def test_the_substituted_operand_keeps_its_own_domain(self, monkeypatch):
        monkeypatch.setattr(
            DomainMembershipChecker,
            "_sub_property_id",
            lambda self, code: 901,
        )
        sub = SubOp(
            _selection(902),
            [SubAssignment("qPO", _item("eba_qPO:qx2001"))],
        )

        (warning,) = _run(BinOp(sub, "=", _item("eba_PL:x72")))

        assert "domain qST" in warning


class TestItemLiterals:
    def test_a_bare_item_yields_its_signature(self):
        assert _item_literals(_item("eba_PL:x72")) == ["eba_PL:x72"]

    def test_parentheses_are_stripped(self):
        assert _item_literals(ParExpr(_item("eba_PL:x72"))) == ["eba_PL:x72"]

    def test_a_set_yields_every_item_member(self):
        node = Set([_item("eba_PL:x72"), _item("eba_RT:x14")])

        assert _item_literals(node) == ["eba_PL:x72", "eba_RT:x14"]

    def test_anything_else_yields_nothing(self):
        assert _item_literals(Constant(type_="Integer", value=1)) == []
