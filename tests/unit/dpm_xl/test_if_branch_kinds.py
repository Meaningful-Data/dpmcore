"""Issue #333 — the ``then``/``else`` branches of an ``if`` must agree in kind.

The rule already existed as ``4-6-1-3``, but it was only enforced when the
condition of the ``if`` was a scalar. With a recordset condition — the usual
case, any comparison over a cell selection being one — the check was skipped
entirely: each branch was validated against the condition on its own, and
whichever branch happened to be a recordset supplied the result structure.

A single-cell selection (a recordset whose key components are all global)
counts as scalar-like on both paths: it contributes no key component a scalar
lacks. What it does keep is its global key components in the result, which is
what makes the reported kind independent of the condition's own kind.
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
from dpmcore.dpm_xl.types.scalar import Boolean, Item, Number, String
from dpmcore.dpm_xl.utils.tokens import DPM, STANDARD
from dpmcore.errors import SemanticError

BOTH_KINDS = "both recordset or both scalars"
NOT_A_BRANCH = "have to be a recordset or a scalar"


def _scalar(name: str = "scalar", type_=None) -> Scalar:
    return Scalar(type_=type_ or Number(), name=name, origin=name)


def _single_cell(name: str = "cell", type_=None) -> RecordSet:
    """A recordset whose key components are all global — a single cell."""
    structure = Structure(
        [
            KeyComponent("refPeriod", String(), DPM, name, is_global=True),
            FactComponent(type_ or Number(), name),
        ]
    )
    return RecordSet(structure, name, name)


def _multi_cell(name: str = "rows", type_=None) -> RecordSet:
    """A recordset with a standard key component — many cells."""
    structure = Structure(
        [
            KeyComponent("refPeriod", String(), DPM, name, is_global=True),
            KeyComponent("r", String(), STANDARD, name),
            FactComponent(type_ or Number(), name),
        ]
    )
    return RecordSet(structure, name, name)


def _multi_cell_with_open_key(name: str = "open", type_=None) -> RecordSet:
    """A recordset whose key components are a superset of ``_multi_cell``."""
    structure = Structure(
        [
            KeyComponent("refPeriod", String(), DPM, name, is_global=True),
            KeyComponent("qEEA", Item(), DPM, name),
            KeyComponent("r", String(), STANDARD, name),
            FactComponent(type_ or Number(), name),
        ]
    )
    return RecordSet(structure, name, name)


def _other_axis(name: str = "cols", type_=None) -> RecordSet:
    """A recordset keyed on another axis — unrelated to ``_multi_cell``."""
    structure = Structure(
        [
            KeyComponent("refPeriod", String(), DPM, name, is_global=True),
            KeyComponent("c", String(), STANDARD, name),
            FactComponent(type_ or Number(), name),
        ]
    )
    return RecordSet(structure, name, name)


def _set(name: str = "set") -> ScalarSet:
    return ScalarSet(type_=Number(), name=name, origin=name)


CONDITIONS = {
    "scalar": lambda: _scalar("cond", Boolean()),
    "single-cell": lambda: _single_cell("cond", Boolean()),
    "multi-cell": lambda: _multi_cell("cond", Boolean()),
}


@pytest.mark.parametrize("condition_kind", list(CONDITIONS))
class TestBranchKindAgreement:
    """The ``then``/``else`` rule holds for every kind of condition."""

    def test_scalar_then_with_multi_cell_else_is_rejected(
        self, condition_kind
    ):
        """The shape reported in #333 — accepted for a recordset condition."""
        with pytest.raises(SemanticError, match=BOTH_KINDS):
            IfOperator.validate(
                CONDITIONS[condition_kind](), _scalar(), _multi_cell()
            )

    def test_multi_cell_then_with_scalar_else_is_rejected(
        self, condition_kind
    ):
        """Order must not decide the verdict: the mirror shape also fails."""
        with pytest.raises(SemanticError, match=BOTH_KINDS):
            IfOperator.validate(
                CONDITIONS[condition_kind](), _multi_cell(), _scalar()
            )

    def test_scalar_then_with_single_cell_else_is_accepted(
        self, condition_kind
    ):
        """A single-cell selection is scalar-like, so this pair agrees."""
        result = IfOperator.validate(
            CONDITIONS[condition_kind](), _scalar(), _single_cell()
        )
        assert isinstance(result, RecordSet)

    def test_both_scalars_are_accepted(self, condition_kind):
        result = IfOperator.validate(
            CONDITIONS[condition_kind](), _scalar("a"), _scalar("b")
        )
        # A recordset condition is evaluated per record, so its own key
        # components stay in the result even when both branches are scalars.
        expected = RecordSet if condition_kind != "scalar" else Scalar
        assert isinstance(result, expected)

    def test_both_multi_cell_are_accepted(self, condition_kind):
        result = IfOperator.validate(
            CONDITIONS[condition_kind](), _multi_cell("a"), _multi_cell("b")
        )
        assert isinstance(result, RecordSet)
        assert "r" in result.get_key_components_names()

    def test_set_branch_raises_a_semantic_error(self, condition_kind):
        """A set branch used to be dropped, or to crash the analysis."""
        with pytest.raises(SemanticError, match=NOT_A_BRANCH):
            IfOperator.validate(
                CONDITIONS[condition_kind](), _set(), _scalar()
            )

    def test_set_else_branch_raises_a_semantic_error(self, condition_kind):
        with pytest.raises(SemanticError, match=NOT_A_BRANCH):
            IfOperator.validate(
                CONDITIONS[condition_kind](), _scalar(), _set()
            )

    def test_set_then_branch_without_else_raises(self, condition_kind):
        with pytest.raises(SemanticError, match=NOT_A_BRANCH):
            IfOperator.validate(CONDITIONS[condition_kind](), _set())


class TestResultKindIsIndependentOfTheCondition:
    """Same branches, different condition kind — same kind of result.

    This is the second half of #333: the branch that "won" used to depend
    on which side happened to be a recordset, so a harmless rewrite of the
    condition changed the type reported for the whole expression.
    """

    @pytest.mark.parametrize(
        ("then_op", "else_op"),
        [
            (_scalar, _single_cell),
            (_single_cell, _scalar),
            (_single_cell, _single_cell),
        ],
        ids=["scalar-cell", "cell-scalar", "cell-cell"],
    )
    def test_single_cell_branch_keeps_its_global_keys(self, then_op, else_op):
        results = {
            kind: IfOperator.validate(
                make_condition(), then_op("then"), else_op("else")
            )
            for kind, make_condition in CONDITIONS.items()
        }
        assert all(isinstance(r, RecordSet) for r in results.values()), (
            "a single-cell branch must keep its global key components "
            f"whatever the condition is, got {results}"
        )

    def test_multi_cell_then_without_else_keeps_its_structure(self):
        for make_condition in CONDITIONS.values():
            result = IfOperator.validate(make_condition(), _multi_cell())
            assert isinstance(result, RecordSet)
            assert "r" in result.get_key_components_names()

    def test_single_cell_then_without_else_keeps_its_structure(self):
        for make_condition in CONDITIONS.values():
            result = IfOperator.validate(make_condition(), _single_cell())
            assert isinstance(result, RecordSet)

    def test_scalar_then_without_else_follows_the_condition(self):
        """Only an all-scalar ``if`` collapses to a scalar."""
        assert isinstance(
            IfOperator.validate(CONDITIONS["scalar"](), _scalar()), Scalar
        )
        assert isinstance(
            IfOperator.validate(CONDITIONS["single-cell"](), _scalar()),
            RecordSet,
        )


class TestRecordsetBranchStructures:
    """Two recordset branches still have to line up structurally."""

    def test_unrelated_structures_are_rejected(self):
        """Neither branch's keys contain the other's: no result to pick."""
        with pytest.raises(SemanticError, match="Structures are different"):
            IfOperator.validate(
                CONDITIONS["single-cell"](), _multi_cell(), _other_axis()
            )

    def test_a_subset_branch_yields_the_larger_structure(self):
        result = IfOperator.validate(
            CONDITIONS["single-cell"](),
            _multi_cell(),
            _multi_cell_with_open_key(),
        )
        assert isinstance(result, RecordSet)
        assert "qEEA" in result.get_key_components_names()
