"""AST passes the calculations export runs over a module's script.

Four walks, in the order the exporter runs them:

1. :class:`CalculationsOperandsChecking` resolves every operand against
   the dictionary (inherited) *and* the assignment targets.
2. :class:`DependencyTableExtractor` collects the tables and datapoints
   the calculations read, and :class:`OutputExtractor` those they write.
3. :class:`VarIDDataEnricher` precomputes each ``VarID``'s ``data``
   array, so operand reference IDs follow visit order.
4. :class:`CalculationsJSONVisitor` serialises the result.

:class:`DAGAnalyzer` is not a serialisation pass: it reorders the
script's statements so a calculation always follows the ones it
consumes.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Set

import pandas as pd

from dpmcore.dpm_xl.ast.nodes import (
    AST,
    Constant,
    ParExpr,
    PersistentAssignment,
    TemporaryAssignment,
    UnaryOp,
    VarID,
    VarRef,
    WithExpression,
)
from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.model_queries import (
    ViewDatapointsQuery,
    ViewKeyComponentsQuery,
)
from dpmcore.dpm_xl.utils.data_handlers import filter_all_data, generate_xyz
from dpmcore.dpm_xl.utils.serialization import (
    ASTToJSONVisitor,
    NodeDict,
    NodeValue,
)
from dpmcore.errors import InternalError, Invalid, SemanticError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_FIRST_OPERAND_REFERENCE_ID = 100000
"""Base of the synthetic operand reference IDs handed to the engine."""


class CalculationsOperandsChecking(OperandsChecking):
    """``OperandsChecking`` that also resolves *cell* assignment targets.

    The base class skips a ``PersistentAssignment``'s left side
    entirely. A calculations export has to describe what each statement
    *writes*, so a cell target is visited like any other operand: it is
    registered, gets its datapoint data attached, and is enriched in the
    output.

    A ``VarRef`` target is deliberately not visited. It names the
    calculation variable the statement produces, and the base visitor
    reads a ``VarRef`` as a *precondition* reference -- which scripting
    mode rejects outright (``6-3``). It is collected by
    :class:`OutputExtractor` and resolved against the dictionary there
    instead.
    """

    def visit_PersistentAssignment(self, node: PersistentAssignment) -> None:
        """Visit a cell assignment target, then the expression."""
        if not isinstance(node.left, VarRef):
            self.visit(node.left)
        self.visit(node.right)


class DAGAnalyzer(ASTTemplate):
    """Reorders ``ast.children`` so producers precede their consumers.

    Applies ``with`` contexts itself, so it runs before operand checking.
    A cell selection is keyed cell by cell, so a range, a list or a
    wildcard read is linked to the statement writing any cell in it.
    """

    def __init__(
        self,
        session: Optional[Session] = None,
        release_id: Optional[int] = None,
        live_table_versions: bool = False,
    ) -> None:
        """Start with an empty dependency map.

        Args:
            session: Resolves each selection into the cells it holds.
                Without one, a selection is keyed as written.
            release_id: Release the selections are resolved against.
            live_table_versions: Forwarded to
                :meth:`ViewDatapointsQuery.get_table_data`.
        """
        super().__init__()
        self.session = session
        self.release_id = release_id
        self.live_table_versions = live_table_versions
        self.inputs: List[str] = []
        self.outputs: List[str] = []
        self.dependencies: Dict[int, Dict[str, List[str]]] = {}
        self.calculation_number = 1
        self.partial_selection: Optional[VarID] = None
        self.operation_codes: Optional[Sequence[Optional[str]]] = None

    def create_dag(
        self,
        ast: Any,
        *,
        check_overwriting: bool = True,
        operation_codes: Optional[Sequence[Optional[str]]] = None,
    ) -> None:
        """Reorder ``ast.children`` into dependency order, in place.

        Args:
            ast: The ``Start`` node holding the script's statements.
            check_overwriting: Whether to reject two statements that
                assign the same output. Semantic validation leaves it to
                its own ``6-1`` check, which also catches overlapping
                ranges.
            operation_codes: The code of each statement, positionally
                matching ``ast.children``, to name the statements of a
                cycle. Without one, a statement is named by its first
                output.

        Raises:
            SemanticError: ``6-4`` if the calculations form a cycle.
            Invalid: If two calculations assign the same output.
            InternalError: If the reordering would lose a statement.
        """
        self.operation_codes = operation_codes
        self.visit(ast)

        # Every statement is a vertex, including one that assigns
        # nothing: leaving it out would drop it from the reordered
        # script instead of merely leaving it unconstrained.
        vertex = list(self.dependencies)
        # Indexed by cell, so each input is looked up once.
        producers: Dict[str, List[int]] = {}
        for key, calc in self.dependencies.items():
            for output in calc["outputs"]:
                producers.setdefault(output, []).append(key)
        # One edge per producer, not one per cell read from it.
        edges: Dict[tuple[int, int], None] = {}
        for key, calc in self.dependencies.items():
            for cell in calc["inputs"]:
                for producer in producers.get(cell, ()):
                    # Never against itself. A statement that reads the
                    # cell it writes -- a time_shift carry-forward reads
                    # the previous period -- is not a cycle, but a
                    # self-edge keeps its own indegree above zero and
                    # Kahn's algorithm reports one.
                    if producer != key:
                        edges[(producer, key)] = None

        sorting = self._topological_sort(vertex, list(edges))
        # The overwrite check is about the statements themselves, not
        # about their order: run it even when nothing needs reordering,
        # or two independent calculations writing the same cell go
        # unreported.
        if check_overwriting:
            self._check_overwriting(producers)
        if edges:
            self._sort_ast(ast, sorting)

    def _topological_sort(
        self, nodes: List[int], edges: List[tuple[int, int]]
    ) -> List[int]:
        """Kahn's algorithm, FIFO in node insertion order.

        Args:
            nodes: The statement numbers to order.
            edges: ``(producer, consumer)`` pairs.

        Returns:
            The statement numbers in dependency order.

        Raises:
            SemanticError: ``6-4`` if the graph has a cycle.
        """
        indegree = dict.fromkeys(nodes, 0)
        successors: Dict[int, List[int]] = {n: [] for n in nodes}
        for a, b in edges:
            if a in indegree and b in indegree:
                successors[a].append(b)
                indegree[b] += 1
        queue = deque(n for n in nodes if indegree[n] == 0)
        order: List[int] = []
        while queue:
            n = queue.popleft()
            order.append(n)
            for m in successors[n]:
                indegree[m] -= 1
                if indegree[m] == 0:
                    queue.append(m)
        if len(order) != len(nodes):
            op1, op2 = self._cycle_edge(
                [n for n in nodes if indegree[n] > 0], edges
            )
            raise SemanticError(
                "6-4", op1=self._name(op1), op2=self._name(op2)
            )
        return order

    def _name(self, statement: int) -> str:
        """The statement's operation code, or else its first output."""
        if self.operation_codes is not None:
            code = self.operation_codes[statement - 1]
            if code is not None:
                return code
        return self.dependencies[statement]["outputs"][0]

    @staticmethod
    def _cycle_edge(
        unsorted: List[int], edges: List[tuple[int, int]]
    ) -> tuple[int, int]:
        """Two consecutive statements on a cycle among *unsorted*.

        Each unsorted statement is fed by another unsorted one, so
        walking back from any of them ends on a cycle.

        Returns:
            ``(statement, producer)``, both on the cycle.
        """
        remaining = set(unsorted)
        producer = {
            b: a for a, b in edges if a in remaining and b in remaining
        }
        met: Set[int] = set()
        node = unsorted[0]
        while node not in met:
            met.add(node)
            node = producer[node]
        return node, producer[node]

    def _sort_ast(self, ast: Any, sorting: List[int]) -> None:
        """Apply the computed order to ``ast.children``.

        Raises:
            InternalError: If the order does not account for every
                statement -- reordering must never lose one.
        """
        calculations = list(ast.children)
        ordered = [
            calculations[x - 1]
            for x in sorting
            if 0 <= x - 1 < len(calculations)
        ]
        if len(ordered) != len(calculations):
            raise InternalError(
                title="Incomplete calculation ordering",
                description=(
                    f"Dependency order covers {len(ordered)} of "
                    f"{len(calculations)} calculations."
                ),
            )
        ast.children = ordered

    @staticmethod
    def _check_overwriting(producers: Dict[str, List[int]]) -> None:
        """Raise if two statements assign the same output.

        The outputs are compared cell by cell, so a range and a single
        cell inside it writing the same cell are caught too.

        Args:
            producers: The statements assigning each output.

        Raises:
            Invalid: If an output is assigned more than once.
        """
        for output, statements in producers.items():
            if len(statements) > 1:
                raise Invalid(
                    title="Duplicate calculation output",
                    description=(
                        f"Output {output} is assigned by more than one "
                        "calculation."
                    ),
                )

    def visit_Start(self, node: Any) -> None:
        """Record one dependency entry per statement."""
        for child in node.children:
            self.visit(child)
            # dict.fromkeys, not set(): the outputs decide the DAG's
            # edges, and a set's iteration order varies with the
            # interpreter's hash seed -- so the exported statement order
            # would too.
            self.dependencies[self.calculation_number] = {
                "inputs": list(dict.fromkeys(self.inputs)),
                "outputs": list(dict.fromkeys(self.outputs)),
            }
            self.calculation_number += 1
            self.inputs = []
            self.outputs = []

    def visit_PersistentAssignment(self, node: PersistentAssignment) -> None:
        """Record the assigned cells as outputs."""
        self.outputs.extend(self._cells(node.left))
        self.visit(node.right)

    def visit_TemporaryAssignment(self, node: TemporaryAssignment) -> None:
        """Record the temporary variable as an output."""
        self.outputs.append(node.left.value)
        self.visit(node.right)

    def visit_OperationRef(self, node: Any) -> None:
        """Record a referenced operation as an input."""
        self.inputs.append(node.operation_code)

    def visit_WithExpression(self, node: WithExpression) -> None:
        """Walk the guarded expression with its context applied."""
        previous = self.partial_selection
        self.partial_selection = node.partial_selection
        self.visit(node.expression)
        self.partial_selection = previous

    def visit_VarID(self, node: VarID) -> None:
        """Record the referenced cells, completed by their context."""
        self.inputs.extend(self._cells(node, self.partial_selection))

    def _cells(self, node: Any, context: Optional[VarID] = None) -> List[str]:
        """Key each cell a selection holds, completed by its context.

        A table selection is resolved against the database; anything
        else is keyed as written.
        """
        if self.session is not None and isinstance(node, VarID):
            table, rows, cols, sheets = self._completed(node, context)
            if table and not node.is_table_group:
                data = ViewDatapointsQuery.get_table_data(
                    self.session,
                    table,
                    rows,
                    cols,
                    sheets,
                    self.release_id,
                    live_table_versions=self.live_table_versions,
                )
                if not data.empty:
                    return list(data["cell_code"])
        return [self._cell_code(node, context)]

    @staticmethod
    def _cell_code(node: Any, context: Optional[VarID] = None) -> str:
        """Key a cell, completed by its ``with`` context, or a variable."""
        if isinstance(node, VarID):
            table, rows, cols, sheets = DAGAnalyzer._completed(node, context)
            return f"t{table}-{rows}-{cols}-{sheets}"
        return str(node.variable)

    @staticmethod
    def _completed(node: VarID, context: Optional[VarID]) -> tuple[Any, ...]:
        """The node's table, rows, cols and sheets, gaps from *context*."""
        return tuple(
            getattr(node, attribute)
            if getattr(node, attribute) is not None or context is None
            else getattr(context, attribute)
            for attribute in ("table", "rows", "cols", "sheets")
        )


class OutputExtractor(ASTTemplate):
    """Collect what the calculations assign to.

    A ``PersistentAssignment`` writes either a calculation variable
    (``VarRef``, resolved to a ``VariableVID`` later) or a table cell
    (``VarID``, resolved to its datapoints here, against the operands
    frame).
    """

    def __init__(self, data: Optional[pd.DataFrame] = None) -> None:
        """Track outputs, resolving ``VarID`` cells against *data*."""
        super().__init__()
        self.data = data
        self.output_variables: List[str] = []
        self.output_variable_ids: List[int] = []
        self.output_table_variables: Dict[str, List[int]] = {}

    def visit_PersistentAssignment(self, node: PersistentAssignment) -> None:
        """Collect the assignment's target, then walk its expression."""
        if isinstance(node.left, VarRef):
            self.output_variables.append(node.left.variable)
        elif isinstance(node.left, VarID) and self.data is not None:
            self._extract_varid_outputs(node.left)
        self.visit(node.right)

    def visit_TemporaryAssignment(self, node: TemporaryAssignment) -> None:
        """Walk the expression only -- a temporary produces no output."""
        self.visit(node.right)

    def _extract_varid_outputs(self, varid_node: VarID) -> None:
        """Resolve a cell target to the datapoints it covers."""
        filtered = _filter_node_data(self.data, varid_node, "output VarID")
        if filtered is None or filtered.empty:
            return
        var_ids = [
            int(v) for v in filtered["variable_id"].dropna().unique().tolist()
        ]
        if not var_ids:
            return
        self.output_variable_ids.extend(var_ids)
        if varid_node.table:
            self.output_table_variables.setdefault(
                varid_node.table, []
            ).extend(var_ids)


class DependencyTableExtractor(ASTTemplate):
    """Collect the tables and datapoints the calculations read.

    Must run *after* operand resolution: a ``VarID`` inside a ``with``
    block has no table of its own until the with-context has been
    grafted onto it, and would otherwise be skipped silently.
    """

    def __init__(
        self,
        session: "Session",
        release_id: Optional[int] = None,
    ) -> None:
        """Collect dependency tables using *session* for lookups."""
        super().__init__()
        self.session = session
        self.release_id = release_id
        self.tables: Dict[str, Dict[str, Any]] = {}
        self.all_datapoints: List[int] = []
        # Operands repeat across a module's calculations, and
        # get_filtered_datapoints is uncached: without this, the same
        # selection is resolved once per occurrence, each time reloading
        # the release sort orders behind the live-version filter.
        self._datapoints_cache: Dict[
            tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]],
            List[int],
        ] = {}

    def visit_PersistentAssignment(self, node: PersistentAssignment) -> None:
        """Walk the expression only -- the target is written, not read.

        ``ASTTemplate`` visits the assignment target as well, which
        would register the cell the calculation *writes* as one of the
        tables it depends on.
        """
        self.visit(node.right)

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
        # module join as well would empty the dependency set for a table
        # whose live version has moved into a newer module version.
        # ``group_tables_by_module`` applies the release scoping.
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

    def _get_open_keys(self, table_code: str) -> Dict[str, str]:
        """Return ``{property_code: data_type}`` for a table's open keys."""
        key_df = ViewKeyComponentsQuery.get_by_table(
            self.session, table_code, self.release_id
        )
        if key_df.empty:
            return {}
        return dict(
            zip(
                key_df["property_code"],
                key_df["data_type"],
                strict=False,
            )
        )

    def visit_VarID(self, node: VarID) -> None:
        """Register the node's table and the datapoints it selects."""
        table = node.table
        if not table:
            return

        variable_ids = self._variable_ids(table, node)
        if not variable_ids:
            return

        # Not setdefault: its default is evaluated eagerly, so the
        # open-key query would run again on every operand naming a
        # table already collected.
        if table not in self.tables:
            self.tables[table] = {
                "variables": set(),
                "open_keys": self._get_open_keys(table),
            }
        entry = self.tables[table]
        entry["variables"].update(variable_ids)
        self.all_datapoints.extend(variable_ids)


class VarIDDataEnricher(ASTTemplate):
    """Precompute each ``VarID``'s exported ``data`` array.

    Two passes on purpose: the enrichment runs in ``ASTTemplate`` visit
    order so ``operand_reference_id`` values are handed out in the order
    the engine expects, and :class:`CalculationsJSONVisitor` then simply
    emits what was computed here.
    """

    def __init__(self, data: Optional[pd.DataFrame]) -> None:
        """Enrich against the operands *data* frame."""
        super().__init__()
        self.data = data
        # Keyed by ``id(node)``: the AST owns every node for the whole
        # export, so the identities stay valid and unique, and nothing
        # is stamped onto the node classes.
        self.payloads: Dict[int, NodeDict] = {}
        self._ref_counter = 0

    def _next_ref_id(self) -> int:
        """Hand out the next operand reference ID."""
        self._ref_counter += 1
        return _FIRST_OPERAND_REFERENCE_ID + self._ref_counter

    def visit_VarID(self, node: VarID) -> None:
        """Record the operand's exported form under ``id(node)``."""
        if self.data is None or self.data.empty:
            return
        filtered = _filter_node_data(self.data, node, "VarID enrichment")
        if filtered is None or filtered.empty:
            return

        # Keep the *_order columns: generate_xyz ranks X/Y/Z by the
        # stored display order when they are present, and falls back to
        # the code text when they are not -- which is the pre-#209
        # ordering, wrong for any table showing a code out of sequence.
        projection = [
            "row_code",
            "column_code",
            "sheet_code",
            "variable_id",
            "cell_id",
        ]
        projection += [
            column
            for column in ("row_order", "column_order", "sheet_order")
            if column in filtered.columns
        ]
        xyz_data = generate_xyz(filtered[projection].copy())

        unique_rows = filtered["row_code"].dropna().unique()
        unique_cols = filtered["column_code"].dropna().unique()
        # One code is reported once on the operand; several stay
        # per-entry as x/row and y/column. An axis the operand does not
        # select, and one with no code at all, is reported neither way.
        multi_rows = len(unique_rows) > 1
        multi_cols = len(unique_cols) > 1
        single_row = _sole_code(unique_rows) if node.rows else None
        single_col = _sole_code(unique_cols) if node.cols else None

        data_list: List[NodeValue] = []
        for item in xyz_data:
            # A grey cell is part of the rendering and carries no
            # variable, so a selection covering one yields NaN where a
            # datapoint id would be. It has nothing to report and must
            # not reach ``int()``, which raises on NaN.
            variable_id = item.get("variable_id")
            if variable_id is None or pd.isna(variable_id):
                continue
            entry: NodeDict = {}
            if multi_rows and item.get("x") is not None:
                entry["x"] = int(item["x"])
                entry["row"] = item["row_code"]
            if multi_cols and item.get("y") is not None:
                entry["y"] = int(item["y"])
                entry["column"] = item["column_code"]
            entry["datapoint"] = int(variable_id)
            entry["operand_reference_id"] = self._next_ref_id()
            data_list.append(entry)

        result: NodeDict = {
            "class_name": "VarID",
            "data": data_list,
            "table": node.table,
        }
        if single_row is not None:
            result["row"] = single_row
        if single_col is not None:
            result["column"] = single_col
        sheets: NodeValue = (
            [str(sheet) for sheet in node.sheets]
            if node.sheets is not None
            else None
        )
        result["sheet"] = sheets
        result["interval"] = bool(node.interval) if node.interval else False
        result["default"] = _constant_value(node.default)
        self.payloads[id(node)] = result


class CalculationsJSONVisitor(ASTToJSONVisitor):
    """dpmcore's AST serializer, in the shape the export contract wants.

    Args:
        payloads: :attr:`VarIDDataEnricher.payloads`, the precomputed
            ``VarID`` forms keyed by ``id(node)``.
    """

    def __init__(self, payloads: Optional[Dict[int, NodeDict]] = None) -> None:
        """Serialize against *payloads*, falling back to the library form."""
        super().__init__()
        self.payloads = payloads or {}

    def visit_VarID(self, node: Any) -> NodeDict:
        """Emit the dict :class:`VarIDDataEnricher` precomputed, if any."""
        enriched = self.payloads.get(id(node))
        if enriched is not None:
            return dict(enriched)
        # An operand with no datapoint data (nothing matched the
        # selection) falls back to the library serializer.
        return super().visit_VarID(node)

    def visit_TimeShiftOp(self, node: Any) -> NodeDict:
        """Emit a flat shift: no ``Constant`` wrapper, ``component`` key."""
        return {
            "class_name": "TimeShiftOp",
            "operand": self.visit(node.operand),
            "period_indicator": node.period_indicator,
            "component": node.component,
            "shift_number": _shift_number_text(node.shift_number),
        }

    def visit_AggregationOp(self, node: Any) -> NodeDict:
        """Drop ``analytic_clause`` when absent rather than emitting null."""
        result = super().visit_AggregationOp(node)
        if result.get("analytic_clause") is None:
            result.pop("analytic_clause", None)
        return result

    def visit_CondExpr(self, node: Any) -> NodeDict:
        """Always emit ``else_expr`` -- null for an if-then with no else."""
        return {
            "class_name": "CondExpr",
            "condition": self.visit(node.condition),
            "then_expr": self.visit(node.then_expr),
            "else_expr": self.visit(node.else_expr),
        }


def unwrap_with_expressions(node: Any) -> None:
    """Replace every ``WithExpression`` in the AST with its expression.

    Run only after operand resolution has grafted the with-context onto
    the inner ``VarID``s: the wrapper has no information left to carry,
    and the export contract has no node for it.

    The walk is restricted to AST nodes and remembers what it has seen,
    so a shared subtree is rewritten once and a back-reference cannot
    send it into unbounded recursion. By this point ``VarID`` nodes hold
    pandas frames, which an attribute-blind walk would descend into.

    Args:
        node: Any AST node; the rewrite is in place.
    """
    _unwrap(node, set())


def _unwrap(node: Any, seen: Set[int]) -> None:
    """Rewrite ``node``'s attributes in place, tracking visited nodes."""
    if not _is_ast_node(node) or id(node) in seen:
        return
    seen.add(id(node))

    for attr_name, attr_value in list(vars(node).items()):
        if isinstance(attr_value, WithExpression):
            unwrapped = _strip_with(attr_value)
            setattr(node, attr_name, unwrapped)
            _unwrap(unwrapped, seen)
        elif isinstance(attr_value, list) and any(
            isinstance(item, WithExpression) for item in attr_value
        ):
            new_list = [_strip_with(item) for item in attr_value]
            setattr(node, attr_name, new_list)
            for item in new_list:
                _unwrap(item, seen)
        elif isinstance(attr_value, list):
            for item in attr_value:
                _unwrap(item, seen)
        else:
            _unwrap(attr_value, seen)


def _strip_with(node: Any) -> Any:
    """Return the innermost expression of a ``WithExpression`` chain."""
    while isinstance(node, WithExpression):
        node = node.expression
    return node


def _is_ast_node(node: Any) -> bool:
    """Whether ``node`` is an AST node the unwrap walk may descend into."""
    return isinstance(node, AST)


def _shift_number_text(node: Any) -> str:
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
            f"({node}); the calculations export can only carry an "
            "integer literal."
        ),
    )


def _sole_code(codes: Any) -> Optional[str]:
    """Return the single code in ``codes``, or ``None`` if not exactly one."""
    if len(codes) != 1:
        return None
    return str(codes[0])


def _constant_value(value: Any) -> Any:
    """Unwrap a ``Constant`` node to its Python scalar."""
    if not isinstance(value, Constant):
        return value
    if value.type == "Integer":
        raw = value.value
        if isinstance(raw, str) and "." in raw:
            raw = float(raw)
        return int(raw)
    if value.type == "Number":
        return float(value.value)
    return value.value


def _filter_node_data(
    data: Optional[pd.DataFrame], node: VarID, what: str
) -> Optional[pd.DataFrame]:
    """Select ``node``'s rows from the operands frame, or ``None`` on error.

    Args:
        data: The operands frame; ``None`` yields ``None``.
        node: The operand to select for.
        what: Short label naming the caller, for the log line.

    Returns:
        The matching rows, or ``None`` when the selection could not be
        resolved (logged, not raised -- one unresolvable operand must
        not abort a module's export).
    """
    if data is None or not node.table:
        return None
    try:
        return filter_all_data(
            data,
            node.table,
            node.rows or [],
            node.cols or [],
            node.sheets or [],
        )
    except Exception:
        logger.warning(
            "Failed to filter data for %s, table=%s", what, node.table
        )
        return None
