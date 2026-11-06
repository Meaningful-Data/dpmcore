"""AST walks shared by the documents written in Script Format 2.0.

:class:`DependencyTableExtractor` collects what each statement reads,
and at which lag, for the ``modules`` section.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from dpmcore.dpm_xl.ast.nodes import (
    Constant,
    ParExpr,
    PersistentAssignment,
    UnaryOp,
    VarID,
)
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.ast.where_clause import WhereClauseChecker
from dpmcore.dpm_xl.model_queries import ViewDatapointsQuery
from dpmcore.dpm_xl.utils import tokens
from dpmcore.errors import Invalid
from dpmcore.services.script_document.modules import (
    AT_T,
    Read,
    RefDateLag,
    combine_lags,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _constrains_ref_period(condition: Any) -> bool:
    """Whether a ``where`` or ``sub`` condition names ``refPeriod``."""
    if condition is None:
        return False
    checker = WhereClauseChecker()
    checker.visit(condition)
    return tokens.REF_PERIOD in checker.key_components


class DependencyTableExtractor(ASTTemplate):
    """Collect what each statement reads, and at which lag.

    Must run *after* operand resolution: a ``VarID`` inside a ``with``
    block has no table of its own until the with-context has been
    grafted onto it, and would otherwise be skipped silently.

    Every ``VarID`` read becomes a :class:`~.modules.Read`. A
    ``time_shift`` without component, or on ``refPeriod``, moves its
    operand's lag by the period shifted. A ``where`` or ``sub`` on
    ``refPeriod``, and an analytic ordered by it, read periods no lag
    describes, so their operands get the lag ``None``. Each read also
    records the ``if-then-else`` branches it sits in.
    """

    def __init__(self, session: "Session") -> None:
        """Collect the reads using *session* for the datapoint lookups."""
        super().__init__()
        self.session = session
        self.reads: List[Read] = []
        self._statement = 0
        self._lag: Optional[RefDateLag] = AT_T
        self._branch: Tuple[Tuple[int, str], ...] = ()
        self._conditionals = 0
        # Operands repeat across a module's calculations, and
        # get_filtered_datapoints is uncached: without this, the same
        # selection is resolved once per occurrence, each time reloading
        # the release sort orders behind the live-version filter.
        self._datapoints_cache: Dict[
            tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]],
            List[int],
        ] = {}

    def visit_Start(self, node: Any) -> None:
        """Visit each statement, numbered by its position."""
        for index, child in enumerate(node.children):
            self._statement = index
            self.visit(child)

    def visit_PersistentAssignment(self, node: PersistentAssignment) -> None:
        """Walk the expression only -- the target is written, not read.

        ``ASTTemplate`` visits the assignment target as well, which
        would register the cell the calculation *writes* as one of the
        tables it depends on.
        """
        self.visit(node.right)

    def _visit_at(self, operand: Any, lag: Optional[RefDateLag]) -> None:
        """Visit ``operand`` as read at ``lag``."""
        previous = self._lag
        self._lag = lag
        self.visit(operand)
        self._lag = previous

    def visit_CondExpr(self, node: Any) -> None:
        """Mark the reads of each branch with the branch they sit in."""
        self.visit(node.condition)
        self._conditionals += 1
        conditional = self._conditionals
        previous = self._branch
        for side, operand in (
            ("then", node.then_expr),
            ("else", node.else_expr),
        ):
            if operand is not None:
                self._branch = (*previous, (conditional, side))
                self.visit(operand)
        self._branch = previous

    def visit_TimeShiftOp(self, node: Any) -> None:
        """A shift without component, or on ``refPeriod``, moves the lag."""
        lag = self._lag
        if node.component in (None, tokens.REF_PERIOD):
            lag = combine_lags(lag, _time_shift_lag(node))
        self._visit_at(node.operand, lag)

    def visit_WhereClauseOp(self, node: Any) -> None:
        """A ``where`` constraining ``refPeriod`` reads other periods."""
        shifted = _constrains_ref_period(node.condition)
        self._visit_at(node.operand, None if shifted else self._lag)
        self.visit(node.condition)

    def visit_SubOp(self, node: Any) -> None:
        """A ``sub`` on, or constrained by, ``refPeriod`` is shifted."""
        shifted = any(
            sub.property_code == tokens.REF_PERIOD
            or _constrains_ref_period(sub.value)
            for sub in node.substitutions
        )
        self._visit_at(node.operand, None if shifted else self._lag)
        for sub in node.substitutions:
            self.visit(sub.value)

    def visit_AggregationOp(self, node: Any) -> None:
        """An analytic ordered by ``refPeriod`` reads other periods."""
        clause = node.analytic_clause
        shifted = clause is not None and any(
            item.key_name == tokens.REF_PERIOD for item in clause.order_by
        )
        self._visit_at(node.operand, None if shifted else self._lag)

    def _variable_ids(self, table: str, node: VarID) -> List[int]:
        """Return the datapoint ids *node* selects, resolved once per key.

        Args:
            table: The operand's table code, already known non-empty.
            node: The operand to resolve.

        Returns:
            The distinct ``VariableID``s the selection covers.
        """
        key = (
            table,
            tuple(node.rows or ()),
            tuple(node.cols or ()),
            tuple(node.sheets or ()),
        )
        cached = self._datapoints_cache.get(key)
        if cached is not None:
            return cached

        # No release on the datapoints query on purpose. The table
        # version is already pinned to the live one, and windowing the
        # module join as well would empty the read for a table whose
        # live version has moved into a newer module version. The
        # ``modules`` section applies the release scoping.
        datapoints_df = ViewDatapointsQuery.get_filtered_datapoints(
            self.session,
            table,
            {"rows": node.rows, "cols": node.cols, "sheets": node.sheets},
            live_table_versions=True,
        )
        # A grey cell carries no variable: it is part of the rendering,
        # never a datapoint, and its NaN would poison the id list.
        variable_ids = (
            []
            if datapoints_df.empty
            else [
                int(v)
                for v in datapoints_df["variable_id"]
                .dropna()
                .unique()
                .tolist()
            ]
        )
        self._datapoints_cache[key] = variable_ids
        return variable_ids

    def visit_VarID(self, node: VarID) -> None:
        """Record the datapoints the node selects, at the current lag."""
        table = node.table
        if not table:
            return
        variable_ids = self._variable_ids(table, node)
        if not variable_ids:
            return
        self.reads.append(
            Read(
                self._statement,
                table,
                frozenset(variable_ids),
                self._lag,
                self._branch,
            )
        )


def _time_shift_lag(node: Any) -> Optional[RefDateLag]:
    """Return the lag a ``time_shift`` adds, ``None`` if not a literal."""
    try:
        shift = int(shift_number_text(node.shift_number))
    except Invalid:
        return None
    return RefDateLag.of_time_shift(node.period_indicator, shift)


def shift_number_text(node: Any) -> str:
    """Render a ``time_shift`` shift number as the contract's string.

    The same written literal arrives in several shapes -- ``-1`` is a
    ``UnaryOp`` over a ``Constant``, ``( -1 )`` a ``ParExpr`` around one,
    ``(-1)`` a negative ``Constant`` -- and all of them mean the same
    integer. Serializing the node instead would put a Python repr into
    the exported contract.

    Args:
        node: The ``shift_number`` sub-expression.

    Returns:
        The signed integer as a string, e.g. ``"-1"``.

    Raises:
        Invalid: If the shift is not an integer literal. The exported
            shape has nowhere to put an expression, so this fails
            loudly rather than emitting something unreadable.
    """
    sign = 1
    current = node
    while True:
        if isinstance(current, ParExpr):
            current = current.expression
        elif isinstance(current, UnaryOp) and current.op in ("+", "-"):
            if current.op == "-":
                sign = -sign
            current = current.operand
        else:
            break
    if isinstance(current, Constant):
        try:
            return str(sign * int(current.value))
        except (TypeError, ValueError):
            pass
    raise Invalid(
        title="Shift number is not a literal",
        description=(
            "time_shift was given a computed shift number "
            f"({node}); the export can only carry an "
            "integer literal."
        ),
    )
