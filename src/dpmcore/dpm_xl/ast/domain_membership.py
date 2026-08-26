"""Domain-membership check for comparisons against item literals.

An enumerated component takes its values from exactly one *domain* (a
``Category``). Comparing it with an item that belongs to a different domain is
accepted by every other check -- the item exists (1-1) and ``Item`` is
type-compatible with ``Item`` -- yet the comparison can never hold: ``=`` and
``in`` are always false, ``!=`` is always true, and a ``sub`` clause on an
out-of-domain item yields an empty recordset. The rule silently does something
other than what it says.

This pass reports that mismatch as a warning, not an error: EBA DPM 4.2.1
ships operations that trip it (domain renames such as ``AS`` -> ``qAS`` leave
legacy signatures behind in expressions that still validate clean), and those
must keep validating.

Domain resolution is the same for every component kind -- the component's
property, then the category that property is typed on at the script's release.
``Category.IsEnumerated`` is the gate: a property in a non-enumerated category
(dates, identifiers, free text, "not applicable") describes no value set, so
nothing is claimed about it. The dictionary offers nothing finer: the
subcategory link on variable versions is unpopulated, so the check is domain
membership and nothing more.

The pass runs after semantic analysis has succeeded, so a genuine type error
is reported on its own rather than alongside this warning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from dpmcore.dpm_xl.ast.nodes import (
    AST,
    BinOp,
    Dimension,
    FilterOp,
    GetOp,
    ParExpr,
    RenameOp,
    Set,
    SubAssignment,
    SubOp,
    TimeShiftOp,
    VarID,
    WhereClauseOp,
)
from dpmcore.dpm_xl.ast.nodes import (
    Scalar as ScalarNode,
)
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.model_queries import (
    ItemCategoryQuery,
    PropertyCategoryQuery,
    ViewOpenKeysQuery,
)
from dpmcore.dpm_xl.utils import tokens
from dpmcore.dpm_xl.utils.operands_mapping import generate_operand_expression
from dpmcore.dpm_xl.warning_collector import add_semantic_warning

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# What an out-of-domain item does to each operator that accepts one.
_EFFECTS: dict[str, str] = {
    tokens.EQ: "the comparison is never true",
    tokens.NEQ: "the comparison is always true",
    tokens.IN: "this member of the set never matches",
}

_SUB_EFFECT = "the substitution matches no record"

# Components whose structure carries the operand's Fact Component through
# unchanged, so the domain of the result is the domain of the operand.
_FACT_PRESERVING = (WhereClauseOp, RenameOp, TimeShiftOp, SubOp)


def _unwrap(node: AST) -> AST:
    """Strip redundant parentheses around *node*."""
    while isinstance(node, ParExpr):
        node = node.expression
    return node


def _item_literals(node: AST) -> list[str]:
    """Return the item signatures *node* contributes as literals.

    A set literal contributes one entry per item member: a set can be
    partly dead, so each member is judged on its own. Members that are not
    item literals (a parameter reference, a constant) carry no signature and
    are simply not returned.
    """
    node = _unwrap(node)
    if isinstance(node, ScalarNode) and node.scalar_type == "Item":
        return [node.item]
    if isinstance(node, Set):
        return [
            child.item
            for child in map(_unwrap, node.children)
            if isinstance(child, ScalarNode) and child.scalar_type == "Item"
        ]
    return []


def _join(domains: Iterable[str]) -> str:
    return ", ".join(sorted(domains))


class DomainMembershipChecker(ASTTemplate):
    """Warns on comparisons an item's domain makes impossible.

    :parameter session: Session used to resolve domains.
    :parameter ast: AST already enriched by ``OperandsChecking``.
    :parameter release_id: Release the domains are resolved at.
    """

    def __init__(
        self,
        session: "Session",
        ast: AST,
        release_id: int | None,
    ) -> None:
        super().__init__()
        self.session = session
        self.release_id = release_id
        # Operands of the clause operators currently being visited, innermost
        # last, so a condition on the Fact Component ("f") resolves against
        # the recordset the clause filters.
        self._clause_operands: list[AST] = []
        self._property_domains: dict[int, set[str]] = {}
        self._item_domains: dict[str, set[str]] = {}
        self._sub_property_ids: dict[str, int | None] = {}
        self.visit(ast)

    # -- traversal ------------------------------------------------- #

    def visit_BinOp(self, node: BinOp) -> None:
        effect = _EFFECTS.get(node.op) if node.op is not None else None
        if effect is not None:
            self._check_comparison(node, effect)
        self.visit(node.left)
        self.visit(node.right)

    def visit_WhereClauseOp(self, node: WhereClauseOp) -> None:
        self.visit(node.operand)
        self._clause_operands.append(node.operand)
        try:
            self.visit(node.condition)
        finally:
            self._clause_operands.pop()

    def visit_SubOp(self, node: SubOp) -> None:
        self.visit(node.operand)
        for substitution in node.substitutions:
            self._check_substitution(substitution)
            self.visit(substitution.value)

    # -- checks ---------------------------------------------------- #

    def _check_comparison(self, node: BinOp, effect: str) -> None:
        """Report the members of a comparison the component can never take."""
        for component_side, literal_side in (
            (node.left, node.right),
            (node.right, node.left),
        ):
            # Resolving the item literals first keeps the domain queries out
            # of every comparison that has no item literal to judge.
            literals = _item_literals(literal_side)
            if not literals:
                continue
            component = self._component_domains(component_side)
            if component is None:
                continue
            self._report(component, literals, effect)
            return

    def _check_substitution(self, substitution: SubAssignment) -> None:
        """Report a ``sub`` clause value outside its target's domain."""
        literals = _item_literals(substitution.value)
        if not literals:
            return
        component = self._property_component(
            substitution.property_code,
            self._sub_property_id(substitution.property_code),
        )
        if component is None:
            return
        self._report(component, literals, _SUB_EFFECT)

    def _report(
        self,
        component: tuple[str, set[str]],
        literals: Iterable[str],
        effect: str,
    ) -> None:
        reference, domains = component
        # A set literal may repeat a member. The mismatch is one fact about
        # the item, so it is reported once however often it is written.
        signatures = list(dict.fromkeys(literals))
        item_domains = self._domains_of_items(signatures)
        for signature in signatures:
            found = item_domains.get(signature)
            # An item with no domain open at this release is reported as
            # not-found (1-1) before this pass runs; a set member the
            # dictionary places in no enumerated category says nothing.
            if not found or found & domains:
                continue
            add_semantic_warning(
                f"Item [{signature}] belongs to domain {_join(found)}, "
                f"but {reference} takes items from domain "
                f"{_join(domains)}: {effect}."
            )

    # -- domain resolution ----------------------------------------- #

    def _component_domains(self, node: AST) -> tuple[str, set[str]] | None:
        """Return ``(component reference, domains)`` for *node*.

        ``None`` whenever the domain cannot be pinned down -- an expression
        that is not a component reference, a selection spanning a property
        with no enumerated domain, an implicit open key.
        """
        node = _unwrap(node)
        if isinstance(node, VarID):
            return self._selection_domains(node)
        if isinstance(node, Dimension):
            return self._dimension_domains(node)
        if isinstance(node, GetOp):
            # ``[get X]`` promotes key component X to the Fact Component, so
            # the result takes X's values, not the operand's.
            return self._property_component(node.component, node.property_id)
        if isinstance(node, _FACT_PRESERVING):
            return self._component_domains(node.operand)
        if isinstance(node, FilterOp):
            return self._component_domains(node.selection)
        return None

    def _selection_domains(self, node: VarID) -> tuple[str, set[str]] | None:
        """Domains of the Fact Component of a cell selection.

        A selection can span several data points, each with its own variable
        and so its own domain. The result is their union: an item is only
        impossible when it belongs to none of them. A single data point
        without an enumerated domain makes the whole selection unjudgeable.
        """
        data = getattr(node, "data", None)
        if data is None or data.empty or "property_id" not in data.columns:
            return None
        properties = data["property_id"]
        if properties.isnull().any():
            # A data point with no variable is a grey cell and is rejected
            # with 1-17 before this pass; one with no property is unjudgeable.
            return None
        property_ids = {int(value) for value in properties.unique()}
        resolved = self._domains_of_properties(property_ids)
        domains: set[str] = set()
        for property_id in property_ids:
            found = resolved.get(property_id)
            if not found:
                return None
            domains |= found
        return generate_operand_expression(node), domains

    def _dimension_domains(
        self, node: Dimension
    ) -> tuple[str, set[str]] | None:
        """Domains of an open key, or of the Fact Component for ``f``."""
        if node.dimension_code == tokens.FACT:
            if not self._clause_operands:
                return None
            return self._component_domains(self._clause_operands[-1])
        return self._property_component(node.dimension_code, node.property_id)

    def _property_component(
        self, code: str, property_id: int | None
    ) -> tuple[str, set[str]] | None:
        """Domains of the component built on property *property_id*.

        Implicit open keys (``refPeriod``, ``entityID``, ``baseCurrency``)
        carry the sentinel ``-1`` and belong to no category.
        """
        if property_id is None or property_id < 0:
            return None
        domains = self._domains_of_properties([property_id]).get(property_id)
        if not domains:
            return None
        return code, domains

    def _sub_property_id(self, code: str) -> int | None:
        """Resolve a ``sub`` clause target property code to its ID."""
        if code not in self._sub_property_ids:
            keys = ViewOpenKeysQuery.get_keys(
                self.session, [code], self.release_id
            )
            matches = keys[keys["property_code"] == code]
            self._sub_property_ids[code] = (
                int(matches["property_id"].iloc[0])
                if not matches.empty
                else None
            )
        return self._sub_property_ids[code]

    def _domains_of_properties(
        self, property_ids: Iterable[int]
    ) -> dict[int, set[str]]:
        missing = [
            property_id
            for property_id in property_ids
            if property_id not in self._property_domains
        ]
        if missing:
            found = PropertyCategoryQuery.get_property_domains(
                self.session, missing, self.release_id
            )
            for property_id in missing:
                self._property_domains[property_id] = found.get(
                    property_id, set()
                )
        return self._property_domains

    def _domains_of_items(
        self, signatures: Iterable[str]
    ) -> dict[str, set[str]]:
        missing = [
            signature
            for signature in signatures
            if signature not in self._item_domains
        ]
        if missing:
            found = ItemCategoryQuery.get_item_domains(
                self.session, missing, self.release_id
            )
            for signature in missing:
                self._item_domains[signature] = found.get(signature, set())
        return self._item_domains
