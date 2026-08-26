"""Issue #333 — the ``then``/``else`` agreement rule of ``if-then-else``.

The rule of §8.1.5 is the *Matched join structure* constraint: the key
components of ``then`` and ``else`` must either be the same, or both be
equal to (or a subset of) those of the condition. Equivalently, and this is
how it is checked here, ``join(condition, then)`` and
``join(condition, else)`` must carry the same key components.

Two consequences are easy to get backwards:

* with a **scalar** condition the constraint collapses to "both branches
  carry the same key components", so a scalar branch cannot be paired with
  a recordset one (§8.1.7, example 5);
* with a **recordset** condition that same pairing is *allowed* — the
  scalar is applied to every record of the condition (§8.1.7, examples 3
  and 6). What is rejected there is a branch carrying a key component the
  condition lacks while the other branch does not (§8.1.7, example 8).

A single-cell selection — a recordset whose key components are all global —
counts as scalar-like: it contributes no key component a scalar lacks.
"""

import pytest

import dpmcore.dpm_xl.semantic_analyzer  # noqa: F401 (resolves circular imports)
from dpmcore.dpm_xl.operators.conditional import IfOperator
from dpmcore.dpm_xl.symbols import (
    FactComponent,
    KeyComponent,
    RecordSet,
    Scalar,
    ScalarSet,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import Boolean, Item, Null, Number, String
from dpmcore.dpm_xl.utils.tokens import DPM, STANDARD
from dpmcore.errors import SemanticError

MATCHED_JOIN = "same key components once joined with the condition"
DIFFERENT_STRUCTURES = "Structures are different"
NOT_A_BRANCH = "have to be a recordset or a scalar"


def _recordset(name: str, keys: list[KeyComponent], type_=None) -> RecordSet:
    structure = Structure(
        [
            KeyComponent("refPeriod", String(), DPM, name, is_global=True),
            *keys,
            FactComponent(type_ or Number(), name),
        ]
    )
    return RecordSet(structure, name, name)


def _scalar(name: str = "scalar", type_=None) -> Scalar:
    return Scalar(type_=type_ or Number(), name=name, origin=name)


def _null(name: str = "null") -> Scalar:
    """The ``null`` literal, as the analyzer hands it to the operator."""
    return Scalar(type_=Null(), name=name, origin=name)


def _single_cell(name: str = "cell", type_=None) -> RecordSet:
    """A recordset whose key components are all global — a single cell."""
    return _recordset(name, [], type_)


def _rows(name: str = "rows", type_=None) -> RecordSet:
    """A recordset keyed on the row axis — many cells."""
    return _recordset(
        name, [KeyComponent("r", String(), STANDARD, name)], type_
    )


def _columns(name: str = "cols", type_=None) -> RecordSet:
    """A recordset keyed on the column axis."""
    return _recordset(
        name, [KeyComponent("c", String(), STANDARD, name)], type_
    )


def _rows_and_columns(name: str = "grid", type_=None) -> RecordSet:
    """A recordset keyed on both axes — a superset of ``_rows``."""
    return _recordset(
        name,
        [
            KeyComponent("r", String(), STANDARD, name),
            KeyComponent("c", String(), STANDARD, name),
        ],
        type_,
    )


def _rows_with_open_key(name: str = "open", type_=None) -> RecordSet:
    """A recordset carrying an open key component on top of ``_rows``."""
    return _recordset(
        name,
        [
            KeyComponent("qEEA", Item(), DPM, name),
            KeyComponent("r", String(), STANDARD, name),
        ],
        type_,
    )


def _set(name: str = "set") -> ScalarSet:
    return ScalarSet(type_=Number(), name=name, origin=name)


class TestRecordsetCondition:
    """A recordset condition applies a scalar branch to each of its records."""

    def test_recordset_then_with_scalar_else_is_accepted(self):
        """§8.1.7 example 6 — the shape #333 claimed had to be rejected."""
        result = IfOperator.validate(
            _rows("cond", Boolean()), _rows(), _scalar()
        )
        assert isinstance(result, RecordSet)
        assert "r" in result.get_key_components_names()

    def test_scalar_then_with_recordset_else_is_accepted(self):
        """The mirror shape — the ``if A = x then y else A`` idiom."""
        result = IfOperator.validate(
            _rows("cond", Boolean()), _scalar(), _rows()
        )
        assert isinstance(result, RecordSet)
        assert "r" in result.get_key_components_names()

    def test_both_scalar_branches_take_the_condition_structure(self):
        """§8.1.7 example 3 — the condition is evaluated per record."""
        result = IfOperator.validate(
            _rows("cond", Boolean()), _scalar("a"), _scalar("b")
        )
        assert isinstance(result, RecordSet)
        assert "r" in result.get_key_components_names()

    def test_a_branch_wider_than_the_condition_needs_the_other_to_match(self):
        """§8.1.7 example 8 — the defect #333 should have reported."""
        with pytest.raises(SemanticError, match=MATCHED_JOIN):
            IfOperator.validate(
                _single_cell("cond", Boolean()), _scalar(), _rows()
            )

    def test_a_branch_wider_than_the_condition_mirror(self):
        with pytest.raises(SemanticError, match=MATCHED_JOIN):
            IfOperator.validate(
                _single_cell("cond", Boolean()), _rows(), _scalar()
            )

    def test_an_open_key_on_one_branch_only_is_rejected(self):
        """The open key reaches the result, so the other branch cannot fill it."""
        with pytest.raises(SemanticError, match=MATCHED_JOIN):
            IfOperator.validate(
                _rows("cond", Boolean()), _rows_with_open_key(), _scalar()
            )

    def test_an_open_key_on_both_branches_is_accepted(self):
        result = IfOperator.validate(
            _rows("cond", Boolean()),
            _rows_with_open_key("then"),
            _rows_with_open_key("else"),
        )
        assert isinstance(result, RecordSet)
        assert "qEEA" in result.get_key_components_names()

    def test_branches_on_different_axes_of_the_condition_are_accepted(self):
        """Case (b) of §8.1.5: both branches are subsets of the condition.

        The branches disagree on their own key components, but each joins
        with the condition to the same structure, so the result is well
        defined — which is why the constraint is stated on the joins.
        """
        result = IfOperator.validate(
            _rows_and_columns("cond", Boolean()), _rows(), _columns()
        )
        assert isinstance(result, RecordSet)
        assert {"r", "c"} <= set(result.get_key_components_names())

    def test_branches_outside_the_condition_are_rejected(self):
        with pytest.raises(SemanticError, match=MATCHED_JOIN):
            IfOperator.validate(
                _single_cell("cond", Boolean()), _rows(), _columns()
            )


class TestScalarCondition:
    """A scalar condition contributes no key component of its own."""

    def test_mixed_branches_are_rejected(self):
        """§8.1.7 example 5 — the case ``4-6-1-3`` has always covered."""
        with pytest.raises(SemanticError, match=MATCHED_JOIN):
            IfOperator.validate(_scalar("cond", Boolean()), _scalar(), _rows())

    def test_mixed_branches_are_rejected_in_either_order(self):
        with pytest.raises(SemanticError, match=MATCHED_JOIN):
            IfOperator.validate(_scalar("cond", Boolean()), _rows(), _scalar())

    def test_both_scalars_stay_a_scalar(self):
        """§8.1.6: all operands scalars, so the result is a scalar."""
        result = IfOperator.validate(
            _scalar("cond", Boolean()), _scalar("a"), _scalar("b")
        )
        assert isinstance(result, Scalar)

    @pytest.mark.parametrize(
        ("then_op", "else_op"),
        [(_single_cell, _scalar), (_scalar, _single_cell)],
        ids=["cell-then", "cell-else"],
    )
    def test_a_single_cell_branch_pairs_with_a_scalar(self, then_op, else_op):
        """A fully specified cell is scalar-like, so this pair agrees.

        Every operand holds one value per global key combination, so §8.1.6
        makes the result a scalar — whichever side the cell is on.
        """
        result = IfOperator.validate(
            _scalar("cond", Boolean()), then_op("then"), else_op("else")
        )
        assert isinstance(result, Scalar)

    def test_recordset_branches_must_have_the_same_key_components(self):
        result = IfOperator.validate(
            _scalar("cond", Boolean()), _rows("a"), _rows("b")
        )
        assert isinstance(result, RecordSet)
        assert "r" in result.get_key_components_names()

    def test_recordset_branches_with_different_keys_are_rejected(self):
        with pytest.raises(SemanticError, match=DIFFERENT_STRUCTURES):
            IfOperator.validate(
                _scalar("cond", Boolean()), _rows(), _rows_and_columns()
            )


class TestOmittedAndNullBranches:
    """An omitted or ``null`` branch contributes no Record."""

    @pytest.mark.parametrize(
        "condition",
        [_scalar("cond", Boolean()), _single_cell("cond", Boolean())],
        ids=["scalar-condition", "single-cell-condition"],
    )
    def test_a_wider_then_is_accepted_without_an_else(self, condition):
        """§8.1.7 example 9 — the Null literal exception."""
        result = IfOperator.validate(condition, _rows())
        assert isinstance(result, RecordSet)
        assert "r" in result.get_key_components_names()

    @pytest.mark.parametrize(
        "condition",
        [_scalar("cond", Boolean()), _single_cell("cond", Boolean())],
        ids=["scalar-condition", "single-cell-condition"],
    )
    def test_an_explicit_null_else_reads_as_an_omitted_else(self, condition):
        result = IfOperator.validate(condition, _rows(), _null())
        assert isinstance(result, RecordSet)
        assert "r" in result.get_key_components_names()

    @pytest.mark.parametrize(
        "condition",
        [_scalar("cond", Boolean()), _single_cell("cond", Boolean())],
        ids=["scalar-condition", "single-cell-condition"],
    )
    def test_a_null_then_leaves_the_else_structure(self, condition):
        result = IfOperator.validate(condition, _null(), _rows())
        assert isinstance(result, RecordSet)
        assert "r" in result.get_key_components_names()

    def test_a_scalar_then_without_else_follows_the_condition(self):
        assert isinstance(
            IfOperator.validate(_scalar("cond", Boolean()), _scalar()), Scalar
        )
        assert isinstance(
            IfOperator.validate(_rows("cond", Boolean()), _scalar()), RecordSet
        )


class TestBranchOperandKind:
    """Only recordsets and scalars can be combined by the operator."""

    CONDITIONS = {
        "scalar": lambda: _scalar("cond", Boolean()),
        "single-cell": lambda: _single_cell("cond", Boolean()),
        "rows": lambda: _rows("cond", Boolean()),
    }

    @pytest.mark.parametrize("condition_kind", list(CONDITIONS))
    def test_a_set_then_branch_is_a_semantic_error(self, condition_kind):
        """A set branch used to be dropped, or to crash the analysis."""
        with pytest.raises(SemanticError, match=NOT_A_BRANCH):
            IfOperator.validate(
                self.CONDITIONS[condition_kind](), _set(), _scalar()
            )

    @pytest.mark.parametrize("condition_kind", list(CONDITIONS))
    def test_a_set_else_branch_is_a_semantic_error(self, condition_kind):
        with pytest.raises(SemanticError, match=NOT_A_BRANCH):
            IfOperator.validate(
                self.CONDITIONS[condition_kind](), _scalar(), _set()
            )

    @pytest.mark.parametrize("condition_kind", list(CONDITIONS))
    def test_a_set_then_branch_without_else_is_a_semantic_error(
        self, condition_kind
    ):
        with pytest.raises(SemanticError, match=NOT_A_BRANCH):
            IfOperator.validate(self.CONDITIONS[condition_kind](), _set())
