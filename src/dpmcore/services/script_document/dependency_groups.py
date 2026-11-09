"""The ``dependency_groups`` section of the validations script.

Every validation reads the instance being validated. Some read more: a
table of another module, or the own module at another reference date.
:class:`DependencyResolver` writes what one validation needs besides
the instance being validated as its ``requires``, and
:func:`build_dependency_groups` groups the validations with the same
``requires``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    FrozenSet,
    Hashable,
    Iterable,
    List,
    Literal,
    Mapping,
    Sequence,
    Set,
    Tuple,
    Union,
)

from sqlalchemy.orm import Session

from dpmcore.dpm_xl.model_queries import VariableVersionQuery
from dpmcore.orm.packaging import ModuleVersion
from dpmcore.orm.query_utils import chunked_in
from dpmcore.services.script_document.modules import AT_T, Read, RefDateLag
from dpmcore.services.script_document.queries import (
    modules_of_filing_indicators,
    modules_of_table_vids,
    windowed_table_vids,
)

_UNIT_ORDER = "ASQMWD"


class NoDependencyGroup(Exception):
    """What a validation needs cannot be written as ``requires`` yet."""


@dataclass(frozen=True)
class ModuleRef:
    """An instance of module ``code``, ``lag`` away from the one validated."""

    code: str
    lag: RefDateLag

    def sort_key(self) -> Tuple[Any, ...]:
        """Order by code; then lag ``0``, unit, size, earlier first.

        A lag only known at run time comes last.
        """
        value, unit = self.lag.value, self.lag.unit
        if value == 0:
            return (self.code, 0)
        if value is None:
            return (self.code, 2, _UNIT_ORDER.index(unit))
        return (self.code, 1, _UNIT_ORDER.index(unit), abs(value), value)

    def to_json(self) -> Dict[str, Any]:
        """Return the module reference as ``requires`` writes it."""
        ref: Dict[str, Any] = {
            "code": self.code,
            "ref_date_lag": self.lag.value,
        }
        if self.lag.value != 0:
            ref["ref_date_lag_unit"] = self.lag.unit
        return ref


class DependencyResolver:
    """Writes the ``requires`` of the validations of one script.

    A table the own module holds is read from the instance being
    validated, or from the own module at another date when shifted. A
    table it does not hold is read from the modules holding it, and each
    scope that combines the own module with some of them is one
    alternative. A filing indicator a precondition needs to be true,
    when only other modules declare it, needs one of them as well. Tables
    and filing indicators are resolved to modules as ``modules`` resolves
    them, so every module ``requires`` names is listed there.

    Args:
        session: SQLAlchemy session.
        own_module_id: ``ModuleID`` of the module the script is for.
        own_code: Its code, the key of ``modules``.
        release_id: The release the script is resolved at.
        filing_indicators: The codes of the filing indicators the
            preconditions of each validation need to be true.
    """

    def __init__(
        self,
        session: Session,
        own_module_id: int,
        own_code: str,
        release_id: int,
        filing_indicators: Mapping[str, Sequence[str]],
    ) -> None:
        """Bind the resolver to the script's own module and release."""
        self.session = session
        self.own_module_id = own_module_id
        self.own_code = own_code
        self.release_id = release_id
        self.filing_indicators = filing_indicators
        self._table_holders: Dict[str, Set[Tuple[int, str]]] = {}
        self._version_modules: Dict[int, Tuple[int, str]] = {}
        self._indicator_modules: Dict[str, Set[str]] = {}

    def requires(
        self,
        code: str,
        scopes: Sequence[FrozenSet[int]],
        reads: Sequence[Read],
    ) -> Dict[str, Any]:
        """Return the ``requires`` of one validation.

        Args:
            code: The validation's code.
            scopes: The module versions of each of its scopes.
            reads: What it reads.

        Raises:
            NoDependencyGroup: When it reads dates no lag gives,
                its ``if-then-else`` branches read different instances,
                or no scope with the own module holds what it reads.
        """
        unfixed = sorted({read.table for read in reads if read.lag is None})
        if unfixed:
            raise NoDependencyGroup(
                f"It reads {', '.join(unfixed)} at reference dates no lag "
                "gives (a where or sub on refPeriod, or an analytic over "
                "refPeriod without a range window bounded on both sides), "
                "which its dependency group cannot state."
            )

        holders = self._holders({read.table for read in reads})
        own_refs: Set[ModuleRef] = set()
        # The tables only other modules hold, with the lags they are read at.
        external: Dict[str, Set[RefDateLag]] = {}
        # The instances each branch reads: the own module at a lag, or
        # the modules holding a table at a lag.
        branch_reads: Dict[Tuple[int, str], Set[Hashable]] = {}
        for read in reads:
            modules = holders[read.table]
            lag = read.lag
            # No version at the script's release, or read from the
            # instance being validated: nothing else is needed.
            if lag is None or not modules:
                continue
            need: Hashable
            if any(
                module_id == self.own_module_id for module_id, _ in modules
            ):
                if lag.value == 0:
                    continue
                need = ModuleRef(self.own_code, lag)
                own_refs.add(need)
            else:
                external.setdefault(read.table, set()).add(lag)
                need = (frozenset(code for _, code in modules), lag)
            for branch in read.branch:
                branch_reads.setdefault(branch, set()).add(need)

        for (conditional, side), then_reads in branch_reads.items():
            else_reads = branch_reads.get((conditional, "else"))
            if side == "then" and else_reads and then_reads != else_reads:
                raise NoDependencyGroup(
                    "Its if-then-else branches read different instances, "
                    "so it needs one or the other, which its dependency "
                    "group cannot state yet."
                )

        alternatives = (
            [
                refs | own_refs
                for refs in self._alternatives(scopes, external, holders)
            ]
            if external
            else [own_refs]
        )
        for codes in self._filing_indicator_modules(
            self.filing_indicators.get(code, [])
        ):
            alternatives = [
                refs | {ModuleRef(module_code, AT_T)}
                for refs in alternatives
                for module_code in codes
            ]
        return Requires.combine(
            "or",
            (Requires.combine("and", refs) for refs in alternatives),
        ).to_json()

    def _alternatives(
        self,
        scopes: Sequence[FrozenSet[int]],
        external: Mapping[str, Set[RefDateLag]],
        holders: Mapping[str, Set[Tuple[int, str]]],
    ) -> List[Set[ModuleRef]]:
        """Return the instances each scope with the own module reads.

        A scope missing a module for some table in ``external`` is no
        alternative.

        Raises:
            NoDependencyGroup: When no scope is an alternative.
        """
        versions = self._modules(set().union(*scopes))
        alternatives: List[Set[ModuleRef]] = []
        with_own = False
        for scope in scopes:
            modules = {versions.get(vid, (0, "")) for vid in scope}
            if not any(mid == self.own_module_id for mid, _ in modules):
                continue
            with_own = True
            codes = {
                code for mid, code in modules if mid != self.own_module_id
            }
            refs: Set[ModuleRef] = set()
            for table, lags in external.items():
                holding = codes & {code for _, code in holders[table]}
                if not holding:
                    break
                refs.update(
                    ModuleRef(code, lag) for code in holding for lag in lags
                )
            else:
                if refs not in alternatives:
                    alternatives.append(refs)
        if alternatives:
            return alternatives

        tables = ", ".join(sorted(external))
        if not with_own:
            raise NoDependencyGroup(
                f"None of its scopes includes module {self.own_code}: it "
                f"reads {tables} from other modules and no table of its own."
            )
        raise NoDependencyGroup(
            f"No scope with module {self.own_code} holds every table it "
            f"reads from other modules: {tables}."
        )

    def _holders(self, tables: Set[str]) -> Dict[str, Set[Tuple[int, str]]]:
        """Return the ``(ModuleID, code)`` of the modules holding each table.

        Resolved at the script's release, as ``modules`` resolves them;
        a table with no version there has none.
        """
        missing = sorted(tables - set(self._table_holders))
        if missing:
            table_vids = windowed_table_vids(
                self.session, missing, self.release_id
            )
            rows = modules_of_table_vids(
                self.session, set(table_vids.values()), self.release_id
            )
            for table in missing:
                self._table_holders[table] = {
                    (int(row.module_id), str(row.module_code))
                    for row in rows.get(table_vids.get(table, -1), [])
                }
        return self._table_holders

    def _filing_indicator_modules(
        self, codes: Sequence[str]
    ) -> List[Set[str]]:
        """Return the codes of the modules declaring each filing indicator.

        Resolved at the script's release, as ``modules`` resolves them.
        A filing indicator the own module declares, or no module does,
        needs nothing else and is left out.
        """
        missing = sorted(set(codes) - set(self._indicator_modules))
        if missing:
            variables = VariableVersionQuery.get_variable_vids_by_codes(
                self.session, missing, release_id=self.release_id
            )
            rows = modules_of_filing_indicators(
                self.session,
                {variable["variable_id"] for variable in variables.values()},
                self.release_id,
            )
            for code in missing:
                variable = variables.get(code)
                declaring = (
                    rows.get(variable["variable_id"], []) if variable else []
                )
                self._indicator_modules[code] = (
                    set()
                    if any(
                        int(row.module_id) == self.own_module_id
                        for row in declaring
                    )
                    else {str(row.module_code) for row in declaring}
                )
        return [
            self._indicator_modules[code]
            for code in codes
            if self._indicator_modules[code]
        ]

    def _modules(self, module_vids: Set[int]) -> Dict[int, Tuple[int, str]]:
        """Return the ``(ModuleID, code)`` of each module version."""
        missing = sorted(module_vids - set(self._version_modules))
        if missing:
            query = self.session.query(
                ModuleVersion.module_vid,
                ModuleVersion.module_id,
                ModuleVersion.code,
            )
            for row in chunked_in(query, ModuleVersion.module_vid, missing):
                self._version_modules[int(row.module_vid)] = (
                    int(row.module_id),
                    str(row.code),
                )
        return self._version_modules


@dataclass(frozen=True)
class Requires:
    """What a validation needs besides the instance being validated.

    Nothing else when it has no operands, one module reference when it
    has one, and otherwise an ``and`` or an ``or`` over module references
    and other :class:`Requires`. Built by :meth:`combine`, which keeps it
    in the canonical form of ``requires``.

    Attributes:
        operator: ``"and"`` or ``"or"``; ``"and"`` with fewer than two
            operands.
        decided_by: ``"scope"`` or ``"condition"``; ``"scope"`` with fewer
            than two operands.
        operands: The module references and :class:`Requires` joined.
    """

    operator: Literal["and", "or"]
    decided_by: Literal["scope", "condition"]
    operands: FrozenSet[Union[ModuleRef, Requires]]

    @classmethod
    def combine(
        cls,
        operator: Literal["and", "or"],
        operands: Iterable[Union[ModuleRef, Requires]],
        decided_by: Literal["scope", "condition"] = "scope",
    ) -> Requires:
        """Join ``operands`` with ``operator``, in canonical form.

        An operand that needs nothing is left out of an ``and`` and makes
        an ``or`` need nothing. An operand that is the same operator,
        decided the same way, is merged into it, so that a chain is one
        :class:`Requires`. A repeated operand is kept once. An operand of
        an ``or`` that needs all another needs, or of an ``and`` that
        allows all another allows, adds nothing and is dropped.

        Raises:
            ValueError: When an ``or`` has no operand.
        """
        flat: Set[Union[ModuleRef, Requires]] = set()
        for operand in operands:
            if isinstance(operand, Requires) and len(operand.operands) == 1:
                (operand,) = operand.operands
            if isinstance(operand, ModuleRef):
                flat.add(operand)
            elif not operand.operands:
                if operator == "or":
                    return cls("and", "scope", frozenset())
            elif (operand.operator, operand.decided_by) == (
                operator,
                decided_by,
            ):
                flat.update(operand.operands)
            else:
                flat.add(operand)
        if not flat and operator == "or":
            raise ValueError("An or needs at least one operand.")

        # What each operand needs (``or``) or allows (``and``), as a set.
        dual = "and" if operator == "or" else "or"
        terms = {
            operand: operand.operands
            if isinstance(operand, Requires) and operand.operator == dual
            else frozenset({operand})
            for operand in flat
        }
        kept = [
            operand
            for operand in flat
            if not any(terms[other] < terms[operand] for other in flat)
        ]
        if len(kept) == 1 and isinstance(kept[0], Requires):
            return kept[0]
        if len(kept) < 2:
            # Nothing else, or one module reference: no operator joins them.
            return cls("and", "scope", frozenset(kept))
        return cls(operator, decided_by, frozenset(kept))

    def _ordered(self) -> List[Union[ModuleRef, Requires]]:
        """Return the operands in the order they are written.

        Module references first, by :meth:`ModuleRef.sort_key`, then
        operators, by their references as written.
        """
        return sorted(
            self.operands,
            key=lambda operand: (
                isinstance(operand, Requires),
                operand.sort_key(),
            ),
        )

    def sort_key(self) -> Tuple[Any, ...]:
        """Order by the references as written, then by the whole chain.

        The chain itself breaks ties between operators over the same
        references, so the order never depends on the input's.
        """
        keys: List[Tuple[Any, ...]] = []
        for operand in self._ordered():
            if isinstance(operand, Requires):
                references, _ = operand.sort_key()
                keys.extend(references)
            else:
                keys.append(operand.sort_key())
        return (keys, json.dumps(self.to_json()))

    def to_json(self) -> Dict[str, Any]:
        """Return it as ``requires`` writes it.

        ``{}`` when it needs nothing else, an ``is`` for one module
        reference, and otherwise a chain nested to the right.
        """
        operands = self._ordered()
        if not operands:
            return {}
        if len(operands) == 1:
            return {"is": operands[0].to_json()}
        right = operands[-1].to_json()
        for left in reversed(operands[:-1]):
            right = {
                self.operator: {
                    "left": left.to_json(),
                    "right": right,
                    "decided_by": self.decided_by,
                }
            }
        return right


def build_dependency_groups(
    requires: Mapping[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Group the validations with the same ``requires``.

    Args:
        requires: The ``requires`` of each validation, in the order of
            ``operations``.

    Returns:
        ``{"G1": {"requires": ..., "validations": [...]}, ...}``: the
        group that needs nothing else first, then the others in the
        order of their first validation.
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for code, group_requires in requires.items():
        group = groups.setdefault(
            json.dumps(group_requires),
            {"requires": group_requires, "validations": []},
        )
        group["validations"].append(code)
    ordered = sorted(
        groups.values(), key=lambda group: group["requires"] != {}
    )
    return {f"G{index}": group for index, group in enumerate(ordered, 1)}
