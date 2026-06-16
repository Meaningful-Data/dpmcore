"""Unit tests for where-clause equality-pin extraction.

``collect_where_equality_pins`` reduces a where condition to the dimensions
it pins to a single literal value; ``merge_where_constraints`` combines the
pins of a nested operand with those of an enclosing where. Both feed the
binary-operator contradiction check (issue #121).
"""

from dpmcore.dpm_xl.ast.nodes import (
    BinOp,
    Constant,
    Dimension,
    ParExpr,
    Scalar,
)
from dpmcore.dpm_xl.ast.where_clause import (
    collect_where_equality_pins,
    merge_where_constraints,
)
from dpmcore.dpm_xl.utils import tokens


def _item_eq(dim: str, value: str) -> BinOp:
    """``dimension = [item]`` condition node."""
    return BinOp(Dimension(dim), tokens.EQ, Scalar(value, "Item"))


class TestCollectWhereEqualityPins:
    def test_single_item_equality(self):
        pins = collect_where_equality_pins(_item_eq("qEEA", "eba_qAE:qx2023"))
        assert pins == {"qEEA": "eba_qAE:qx2023"}

    def test_dimension_on_the_right(self):
        """The dimension may sit on either side of the ``=``."""
        node = BinOp(
            Scalar("eba_qAE:qx2023", "Item"), tokens.EQ, Dimension("qEEA")
        )
        assert collect_where_equality_pins(node) == {"qEEA": "eba_qAE:qx2023"}

    def test_literal_constant_value(self):
        node = BinOp(Dimension("qA"), tokens.EQ, Constant("Integer", 5))
        assert collect_where_equality_pins(node) == {"qA": "5"}

    def test_conjunction_collects_each_dimension(self):
        node = BinOp(_item_eq("qA", "X"), tokens.AND, _item_eq("qB", "Y"))
        assert collect_where_equality_pins(node) == {"qA": "X", "qB": "Y"}

    def test_repeated_dimension_same_value_kept(self):
        node = BinOp(_item_eq("qA", "X"), tokens.AND, _item_eq("qA", "X"))
        assert collect_where_equality_pins(node) == {"qA": "X"}

    def test_repeated_dimension_conflicting_value_dropped(self):
        """A dimension pinned two different ways is unreliable -> dropped."""
        node = BinOp(_item_eq("qA", "X"), tokens.AND, _item_eq("qA", "Y"))
        assert collect_where_equality_pins(node) == {}

    def test_parenthesised_condition_unwrapped(self):
        assert collect_where_equality_pins(ParExpr(_item_eq("qA", "X"))) == {
            "qA": "X"
        }

    def test_disjunction_yields_no_pins(self):
        node = BinOp(_item_eq("qA", "X"), tokens.OR, _item_eq("qB", "Y"))
        assert collect_where_equality_pins(node) == {}

    def test_inequality_yields_no_pins(self):
        node = BinOp(Dimension("qA"), tokens.NEQ, Scalar("X", "Item"))
        assert collect_where_equality_pins(node) == {}

    def test_dimension_to_dimension_yields_no_pins(self):
        node = BinOp(Dimension("qA"), tokens.EQ, Dimension("qB"))
        assert collect_where_equality_pins(node) == {}

    def test_value_to_value_yields_no_pins(self):
        node = BinOp(Scalar("X", "Item"), tokens.EQ, Scalar("Y", "Item"))
        assert collect_where_equality_pins(node) == {}

    def test_non_binop_condition_yields_no_pins(self):
        assert collect_where_equality_pins(Constant("Boolean", True)) == {}


class TestMergeWhereConstraints:
    def test_distinct_dimensions_unite(self):
        assert merge_where_constraints({"qA": "X"}, {"qB": "Y"}) == {
            "qA": "X",
            "qB": "Y",
        }

    def test_same_dimension_same_value_kept(self):
        assert merge_where_constraints({"qA": "X"}, {"qA": "X"}) == {"qA": "X"}

    def test_same_dimension_conflicting_value_dropped(self):
        assert merge_where_constraints({"qA": "X"}, {"qA": "Y"}) == {}

    def test_empty_base(self):
        assert merge_where_constraints({}, {"qA": "X"}) == {"qA": "X"}
