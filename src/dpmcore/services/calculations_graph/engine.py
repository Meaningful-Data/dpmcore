"""Engine-based dependency extraction from the DPM database.

The shipped DPM dictionary stores every operation as a validation/equality
(``with {scope}: {LHS} = {RHS}``), not a ``<-`` assignment, and the engine has
already resolved each operand to concrete cells. This module reads that
resolved data — the operand tree (``OperationNode`` + ``Operator`` /
``OperatorArgument``) and its leaves' resolved cells (``OperandReference`` →
``VariableID``) — to build operation-to-operation dependencies.

For an ``=`` operation the root operator's ``left`` argument subtree is the
**output** and the ``right`` subtree the **inputs**; an edge ``A -> B`` exists
when ``B`` reads a variable that ``A`` writes (exact ``VariableID`` match).
Other root operators (``>=``, ``if`` …) define no output, so their operands
are all inputs.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, cast

from dpmcore.dpm_xl.utils.filters import (
    filter_by_release,
    resolve_release_id,
)
from dpmcore.errors import Invalid
from dpmcore.orm.operations import (
    OperandReference,
    OperandReferenceLocation,
    Operation,
    OperationNode,
    OperationScope,
    OperationScopeComposition,
    OperationVersion,
    Operator,
    OperatorArgument,
)
from dpmcore.orm.packaging import ModuleVersion
from dpmcore.orm.release_sort_order import load_release_sort_orders
from dpmcore.services.calculations_graph.service import (
    GraphEdge,
    GraphNode,
    _implicit_edges,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_EQUALS = "="
_LEFT = "left"


def select_operations(
    session: "Session",
    release_code: str | None,
    module_code: str | None,
    table_code: str | None,
) -> dict[int, tuple[str, str]]:
    """Return ``{operation_vid: (code, expression)}`` after filters + dedup.

    The release window is applied by the shared
    :func:`~dpmcore.dpm_xl.utils.filters.filter_by_release` helper, so it
    follows the same half-open convention as every other query: a version
    is alive while ``start <= target < end`` (an ``end`` equal to the
    target release means the version was retired in it). Operations are
    then de-duplicated by ``code``, keeping the version with the greatest
    start-release sort order (the latest).
    """
    query = session.query(
        OperationVersion.operation_vid,
        Operation.code,
        OperationVersion.expression,
        OperationVersion.start_release_id,
        OperationVersion.end_release_id,
    ).join(Operation, Operation.operation_id == OperationVersion.operation_id)
    if module_code is not None:
        query = (
            query.join(
                OperationScope,
                OperationScope.operation_vid == OperationVersion.operation_vid,
            )
            .join(
                OperationScopeComposition,
                OperationScopeComposition.operation_scope_id
                == OperationScope.operation_scope_id,
            )
            .join(
                ModuleVersion,
                ModuleVersion.module_vid
                == OperationScopeComposition.module_vid,
            )
            .filter(ModuleVersion.code == module_code)
        )
    if table_code is not None:
        query = (
            query.join(
                OperationNode,
                OperationNode.operation_vid == OperationVersion.operation_vid,
            )
            .join(
                OperandReference,
                OperandReference.node_id == OperationNode.node_id,
            )
            .join(
                OperandReferenceLocation,
                OperandReferenceLocation.operand_reference_id
                == OperandReference.operand_reference_id,
            )
            .filter(OperandReferenceLocation.table == table_code)
        )
    if release_code is not None:
        query = filter_by_release(
            query,
            start_col=OperationVersion.start_release_id,
            end_col=OperationVersion.end_release_id,
            release_id=_target_release_id(session, release_code),
        )
    rows = [tuple(row) for row in query.all()]
    return _dedupe_latest(session, rows)


def _target_release_id(session: "Session", release_code: str) -> int:
    """Resolve *release_code* to its release id.

    Raises:
        Invalid: If the code matches no release.
    """
    try:
        release_id = resolve_release_id(session, release_code=release_code)
    except ValueError as exc:
        raise Invalid(
            "Invalid release code",
            f"Unknown release code {release_code!r}.",
        ) from exc
    return cast(int, release_id)


def _dedupe_latest(
    session: "Session", rows: list[tuple[Any, ...]]
) -> dict[int, tuple[str, str]]:
    """Keep one version per code — the latest by start-release sort order."""
    sort_orders = load_release_sort_orders(session)
    best: dict[str, tuple[int, int, str]] = {}
    for vid, code, expression, start_rid, _end_rid in rows:
        if not code:
            continue
        order = sort_orders.get(start_rid)
        rank = order if order is not None else -1
        current = best.get(code)
        if current is None or (rank, vid) > (current[0], current[1]):
            best[code] = (rank, vid, expression or "")
    return {vid: (code, expr) for code, (_rank, vid, expr) in best.items()}


def _root_child(node_id: int, parent: dict[int, int | None]) -> int:
    """Return the ancestor of *node_id* that is a direct child of the root."""
    node = node_id
    while (
        parent.get(node) is not None and parent.get(parent[node]) is not None  # type: ignore[arg-type]
    ):
        node = parent[node]  # type: ignore[assignment]
    return node


def operation_cells(
    session: "Session", vids: list[int]
) -> dict[int, tuple[set[int], set[int]]]:
    """Return ``{vid: (output_variable_ids, input_variable_ids)}``."""
    if not vids:
        return {}
    node_rows = (
        session.query(
            OperationNode.node_id,
            OperationNode.operation_vid,
            OperationNode.parent_node_id,
            OperationNode.argument_id,
            Operator.symbol,
        )
        .outerjoin(Operator, Operator.operator_id == OperationNode.operator_id)
        .filter(OperationNode.operation_vid.in_(vids))
        .all()
    )
    arg_name: dict[int, str | None] = {
        row[0]: row[1]
        for row in session.query(
            OperatorArgument.argument_id, OperatorArgument.name
        ).all()
    }
    operand_rows = (
        session.query(OperandReference.node_id, OperandReference.variable_id)
        .join(OperationNode, OperationNode.node_id == OperandReference.node_id)
        .filter(
            OperationNode.operation_vid.in_(vids),
            OperandReference.variable_id.isnot(None),
        )
        .all()
    )
    vars_of_node: dict[int, set[int]] = defaultdict(set)
    for node_id, variable_id in operand_rows:
        vars_of_node[node_id].add(variable_id)

    parent: dict[int, int | None] = {}
    arg_of: dict[int, int | None] = {}
    nodes_of_vid: dict[int, list[int]] = defaultdict(list)
    root_symbol: dict[int, str | None] = {}
    for node_id, vid, parent_id, argument_id, symbol in node_rows:
        parent[node_id] = parent_id
        arg_of[node_id] = argument_id
        nodes_of_vid[vid].append(node_id)
        if parent_id is None:
            root_symbol[vid] = symbol

    result: dict[int, tuple[set[int], set[int]]] = {}
    for vid in vids:
        outputs: set[int] = set()
        inputs: set[int] = set()
        is_equality = root_symbol.get(vid) == _EQUALS
        for node_id in nodes_of_vid.get(vid, []):
            here = vars_of_node.get(node_id)
            if not here:
                continue
            if not is_equality:
                inputs |= here
                continue
            argument_id = arg_of.get(_root_child(node_id, parent))
            side = (
                arg_name.get(argument_id) if argument_id is not None else None
            )
            if side == _LEFT:
                outputs |= here
            else:
                inputs |= here
        result[vid] = (outputs, inputs)
    return result


def build(
    operations: dict[int, tuple[str, str]],
    cells: dict[int, tuple[set[int], set[int]]],
) -> tuple[tuple[GraphNode, ...], tuple[GraphEdge, ...], tuple[str, ...]]:
    """Build nodes, edges and warnings from resolved operation cells."""
    edges = _implicit_edges(
        {code: cells[vid][0] for vid, (code, _expr) in operations.items()},
        {code: cells[vid][1] for vid, (code, _expr) in operations.items()},
    )

    indegree: dict[str, int] = defaultdict(int)
    for _src, dst in edges:
        indegree[dst] += 1
    # ``target``/``rhs`` are the lhs/rhs split shown in the detail panel; the
    # engine works from resolved operands rather than the expression text, so
    # it leaves them empty and the template shows the raw expression only.
    nodes = tuple(
        GraphNode(
            code=code,
            expression=expression,
            target="",
            rhs="",
            is_root=indegree[code] == 0,
        )
        for _vid, (code, expression) in operations.items()
    )
    edge_objs = tuple(
        GraphEdge(source=src, target=dst, kind="implicit")
        for src, dst in edges
    )
    warnings: tuple[str, ...] = ()
    if not operations:
        warnings = ("No operations matched the given filters.",)
    return nodes, edge_objs, warnings


def default_title(
    module_code: str | None,
    table_code: str | None,
    release_code: str | None,
) -> str:
    """Derive a graph title from the active filters."""
    parts: list[str] = []
    if module_code:
        parts.append(f"module {module_code}")
    if table_code:
        parts.append(f"table {table_code}")
    if release_code:
        parts.append(f"release {release_code}")
    scope = ", ".join(parts) if parts else "all operations"
    return f"Execution graph — {scope}"
