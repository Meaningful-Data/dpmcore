"""Build a self-contained HTML dependency graph for a calculations script.

A *calculations script* is a ``Code,Expression`` CSV in which every row is a
DPM-XL assignment operation of the form::

    <lhs selection> <- with {default:..., interval:...}: (<rhs expression>)

The left-hand side selection is the operation's *output*; the right-hand side
reads its *inputs* through selection operators ``{...}``. A dependency edge
``A -> B`` exists when operation ``B`` reads a cell that operation ``A`` writes
(implicit), or when ``B`` explicitly references ``{o<A-code>}`` (explicit).

Dependencies are resolved by the DPM-XL **engine** (:class:`OperandsChecking`)
against a database and release: every selection — including row/column ranges,
wildcards and the sheet dimension — is expanded to the concrete ``VariableID``
set it covers, and an implicit edge is drawn only on an *exact* variable match.
Every input mode (CSV file, inline expressions, or the DPM dictionary itself)
therefore needs a database connection; there is no approximate, database-free
mode.
"""

from __future__ import annotations

import csv
import html
import importlib.resources as importlib_resources
import json
import re
import string
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Literal

from dpmcore.dpm_xl.ast.nodes import (
    AST,
    OperationRef,
    VarID,
)
from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.dpm_xl.model_queries import ModuleVersionQuery
from dpmcore.dpm_xl.utils.filters import resolve_release_id
from dpmcore.errors import InternalError, Invalid
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_PACKAGE = "dpmcore.services.calculations_graph"
_TEMPLATE_NAME = "_template.html"
_ASSET_FILES = (
    "cytoscape.min.js",
    "dagre.min.js",
    "cytoscape-dagre.min.js",
)

# The ``with {default:..., interval:...}`` clause uses braces too; strip it
# before showing the right-hand side text in the detail panel.
_WITH_CLAUSE_RE = re.compile(r"with\s*\{[^{}]*\}", re.IGNORECASE)


@dataclass(frozen=True)
class GraphNode:
    """One operation in the dependency graph."""

    code: str
    expression: str
    target: str
    rhs: str
    is_root: bool


@dataclass(frozen=True)
class GraphEdge:
    """A dependency arrow ``source -> target`` between two operations."""

    source: str
    target: str
    kind: Literal["implicit", "explicit"]


@dataclass(frozen=True)
class CalculationsGraphResult:
    """Outcome of building a calculations graph."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    html: str
    warnings: tuple[str, ...]

    @property
    def n_nodes(self) -> int:
        """Number of operations (nodes)."""
        return len(self.nodes)

    @property
    def n_edges(self) -> int:
        """Number of dependency edges."""
        return len(self.edges)

    @property
    def n_roots(self) -> int:
        """Number of root operations (no inputs from other operations)."""
        return sum(1 for node in self.nodes if node.is_root)


@dataclass
class _Operation:
    """Parsed view of a single CSV row used to build the graph."""

    code: str
    expression: str
    lhs_text: str
    rhs_text: str
    output_var_ids: set[int] = field(default_factory=set)
    input_var_ids: set[int] = field(default_factory=set)
    op_refs: set[str] = field(default_factory=set)
    parse_error: str | None = None


# --------------------------------------------------------------------------- #
# AST traversal
# --------------------------------------------------------------------------- #


def _ast_children(value: Any) -> list[AST]:
    """Return the AST children held by an attribute value."""
    if isinstance(value, AST):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, AST)]
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, AST)]
    return []


def _iter_ast(root: AST) -> Iterable[AST]:
    """Yield every AST node reachable from *root* (cycle-safe)."""
    seen: set[int] = set()
    stack: list[AST] = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        yield node
        for value in vars(node).values():
            stack.extend(_ast_children(value))


def _collect_op_refs(root: AST) -> set[str]:
    """Return the explicit operation references ``{o<code>}`` in *root*.

    A :class:`VarID` carrying an ``operation`` (or a bare
    :class:`OperationRef`) is an explicit operation reference rather than a
    cell selection. These need no database resolution — the edge is drawn by
    operation code alone.
    """
    op_refs: set[str] = set()
    for node in _iter_ast(root):
        if isinstance(node, VarID):
            if node.operation is not None:
                op_refs.add(node.operation)
        elif isinstance(node, OperationRef):
            op_refs.add(node.operation_code)
    return op_refs


def _variable_ids_from_ast(root: AST) -> set[int]:
    """Return the concrete ``variable_id`` set resolved onto *root*.

    After :class:`OperandsChecking` runs, every cell-selecting :class:`VarID`
    carries a ``data`` frame whose ``variable_id`` column lists the exact
    variables the selection covers (ranges/wildcards already expanded). Grey
    cells (no variable) contribute nothing.
    """
    var_ids: set[int] = set()
    for node in _iter_ast(root):
        if not isinstance(node, VarID):
            continue
        data = getattr(node, "data", None)
        if data is None:
            continue
        try:
            column = data["variable_id"]
        except (KeyError, TypeError):
            continue
        var_ids |= {int(value) for value in column.dropna().unique()}
    return var_ids


# --------------------------------------------------------------------------- #
# Edge building
# --------------------------------------------------------------------------- #


def _implicit_edges(
    outputs_by_code: dict[str, set[int]],
    inputs_by_code: dict[str, set[int]],
) -> dict[tuple[str, str], str]:
    """Return implicit edges from exact ``variable_id`` producer→consumer.

    An edge ``A -> B`` exists when ``B`` reads a variable that ``A`` writes.
    Both the CSV/inline path and the database path share this matcher so a
    dependency is always an exact variable match, never a range *overlap*.
    """
    producers: dict[int, set[str]] = defaultdict(set)
    for code, outputs in outputs_by_code.items():
        for variable_id in outputs:
            producers[variable_id].add(code)

    edges: dict[tuple[str, str], str] = {}
    for code, inputs in inputs_by_code.items():
        for variable_id in inputs:
            for producer in sorted(producers.get(variable_id, set())):
                if producer != code:
                    edges.setdefault((producer, code), "implicit")
    return edges


def _add_edge(
    edges: dict[tuple[str, str], str],
    source: str,
    target: str,
    kind: str,
) -> None:
    """Record an edge, keeping an existing (explicit) kind if present."""
    edges.setdefault((source, target), kind)


# --------------------------------------------------------------------------- #
# Display helpers
# --------------------------------------------------------------------------- #


def _split_assignment(expression: str) -> tuple[str, str]:
    """Split ``lhs <- with {..}: rhs`` into display ``(lhs, rhs)`` text."""
    if "<-" not in expression:
        return "", expression.strip()
    lhs, rhs = expression.split("<-", 1)
    rhs = _WITH_CLAUSE_RE.sub("", rhs, count=1).lstrip().removeprefix(":")
    return lhs.strip(), rhs.strip()


def _json_for_html(payload: Any) -> str:
    """Serialise *payload* to JSON safe to embed inside ``<script>``."""
    text = json.dumps(payload)
    for unsafe, escaped in (
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("&", "\\u0026"),
    ):
        text = text.replace(unsafe, escaped)
    return text


def _op_warnings(op: _Operation) -> list[str]:
    """Return advisory warnings for a single operation."""
    out: list[str] = []
    if op.parse_error is not None:
        out.append(
            f"Operation {op.code!r}: expression could not be resolved "
            f"({op.parse_error}); its dependencies were skipped."
        )
    if op.code.startswith("o"):
        out.append(
            f"Operation code {op.code!r} starts with 'o'; explicit "
            "{o...} references use that prefix, so operation codes "
            "should not begin with 'o'."
        )
    return out


# --------------------------------------------------------------------------- #
# Resource loading
# --------------------------------------------------------------------------- #


def _assets_path() -> Any:
    """Return the traversable directory holding the vendored JS assets."""
    return importlib_resources.files(_PACKAGE) / "assets"


def _read_asset(base: Any, name: str) -> str:
    """Read one vendored asset file as text."""
    try:
        return str((base / name).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError) as exc:
        raise InternalError(
            "Missing vendored asset for the calculations graph",
            f"Expected {name} under {_PACKAGE}/assets/.",
        ) from exc


def _load_assets() -> dict[str, str]:
    """Read the vendored JavaScript libraries as text."""
    base = _assets_path()
    return {name: _read_asset(base, name) for name in _ASSET_FILES}


def _load_template() -> string.Template:
    """Load the HTML shell template."""
    text = (importlib_resources.files(_PACKAGE) / _TEMPLATE_NAME).read_text(
        encoding="utf-8"
    )
    return string.Template(text)


# --------------------------------------------------------------------------- #
# CSV reading
# --------------------------------------------------------------------------- #


def _read_csv_rows(csv_path: Path) -> list[tuple[str, str]]:
    """Read ``Code,Expression`` rows, validating the header."""
    rows: list[tuple[str, str]] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header or header[0].strip().lower() != "code":
            raise Invalid(
                "Invalid calculations script",
                f"Expected a 'Code,Expression' header, got: {header!r}.",
            )
        for row in reader:
            if not row or not row[0].strip():
                continue
            code = row[0].strip()
            expression = row[1].strip() if len(row) > 1 else ""
            rows.append((code, expression))
    return rows


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #


class CalculationsGraphService:
    """Turn a calculations-script CSV into a portable HTML dependency graph.

    The service is stateless: a SQLAlchemy ``Session`` is passed to each
    generate call. Dependencies are always resolved by the DPM-XL engine
    against that database and a release, so every input mode is exact.
    """

    def __init__(self) -> None:
        """Build a stateless calculations-graph service."""
        self._syntax = SyntaxService()

    def _resolve_release(
        self, session: "Session", release_code: str | None
    ) -> int | None:
        """Return the release id to resolve against (latest when unset).

        Defaults to the latest release, matching the DPM-XL engine
        convention used by the semantic service.
        """
        release_id = resolve_release_id(session, release_code=release_code)
        if release_id is None:
            release_id = ModuleVersionQuery.get_last_release(session)
        return release_id

    def _resolve_side(
        self,
        text: str,
        session: "Session",
        release_id: int | None,
        *,
        collect_refs: bool,
    ) -> tuple[set[int], set[str], str | None]:
        """Resolve one side of an assignment via the engine.

        Returns ``(variable_ids, op_refs, error)``. Explicit operation
        references are collected from the parse tree even when engine
        resolution fails, since they need no cell resolution. A resolution
        failure is not fatal: it is recorded so the node still renders.
        """
        if not text.strip():
            return set(), set(), None
        try:
            ast = self._syntax.parse(text)
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            return set(), set(), str(exc)
        op_refs = _collect_op_refs(ast) if collect_refs else set()
        try:
            OperandsChecking(
                session=session,
                expression=text,
                ast=ast,
                release_id=release_id,
                is_scripting=True,
            )
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            return set(), op_refs, str(exc)
        return _variable_ids_from_ast(ast), op_refs, None

    def _extract(
        self, expression: str, session: "Session", release_id: int | None
    ) -> tuple[set[int], set[int], set[str], str | None]:
        """Return ``(outputs, inputs, op_refs, error)`` for an expression.

        The left-hand selection (before ``<-``) resolves to the written
        variables; the right-hand side resolves to the read variables and
        supplies the explicit operation references. An expression without
        ``<-`` has no writes (validation-style).
        """
        lhs_text, rhs_text = _split_assignment(expression)
        outputs: set[int] = set()
        lhs_error: str | None = None
        if "<-" in expression:
            outputs, _, lhs_error = self._resolve_side(
                lhs_text, session, release_id, collect_refs=False
            )
        inputs, op_refs, rhs_error = self._resolve_side(
            rhs_text, session, release_id, collect_refs=True
        )
        error = "; ".join(e for e in (lhs_error, rhs_error) if e) or None
        return outputs, inputs, op_refs, error

    def parse_operations(
        self,
        rows: Iterable[tuple[str, str]],
        session: "Session",
        release_id: int | None,
    ) -> list[_Operation]:
        """Parse and engine-resolve ``(code, expression)`` rows.

        An expression that fails to resolve is not fatal: its dependencies
        are skipped and the failure is recorded on the operation so the node
        still renders.
        """
        ops: list[_Operation] = []
        for code, expression in rows:
            lhs_text, rhs_text = _split_assignment(expression)
            outputs, inputs, op_refs, error = self._extract(
                expression, session, release_id
            )
            ops.append(
                _Operation(
                    code=code,
                    expression=expression,
                    lhs_text=lhs_text,
                    rhs_text=rhs_text,
                    output_var_ids=outputs,
                    input_var_ids=inputs,
                    op_refs=op_refs,
                    parse_error=error,
                )
            )
        return ops

    def build_graph(
        self, ops: list[_Operation]
    ) -> tuple[tuple[GraphNode, ...], tuple[GraphEdge, ...], tuple[str, ...]]:
        """Build nodes, edges and warnings from resolved operations."""
        codes = {op.code for op in ops}
        edges: dict[tuple[str, str], str] = {}
        warnings: list[str] = []

        # Explicit references are recorded first so they win over an implicit
        # edge between the same pair.
        for op in ops:
            warnings.extend(_op_warnings(op))
            for ref in sorted(op.op_refs):
                if ref in codes:
                    _add_edge(edges, ref, op.code, "explicit")
                else:
                    warnings.append(
                        f"Operation {op.code!r}: explicit reference "
                        f"{{o{ref}}} points to an unknown operation; "
                        "no edge was drawn."
                    )

        implicit = _implicit_edges(
            {op.code: op.output_var_ids for op in ops},
            {op.code: op.input_var_ids for op in ops},
        )
        for (source, target), kind in implicit.items():
            _add_edge(edges, source, target, kind)

        nodes = _build_nodes(ops, edges)
        edge_objs = tuple(
            GraphEdge(source=src, target=dst, kind=kind)  # type: ignore[arg-type]
            for (src, dst), kind in edges.items()
        )
        return nodes, edge_objs, tuple(warnings)

    def render_html(
        self,
        nodes: tuple[GraphNode, ...],
        edges: tuple[GraphEdge, ...],
        title: str,
    ) -> str:
        """Render the self-contained HTML document."""
        elements: list[dict[str, Any]] = [
            {
                "data": {
                    "id": node.code,
                    "label": node.code,
                    "expression": node.expression,
                    "target": node.target,
                    "rhs": node.rhs,
                    "isRoot": node.is_root,
                }
            }
            for node in nodes
        ]
        elements += [
            {
                "data": {
                    "id": f"{edge.source}->{edge.target}",
                    "source": edge.source,
                    "target": edge.target,
                    "kind": edge.kind,
                }
            }
            for edge in edges
        ]
        libs = _load_assets()
        template = _load_template()
        n_roots = sum(1 for node in nodes if node.is_root)
        return template.substitute(
            title=html.escape(title),
            cytoscape_js=libs["cytoscape.min.js"],
            dagre_js=libs["dagre.min.js"],
            dagre_ext_js=libs["cytoscape-dagre.min.js"],
            elements=_json_for_html(elements),
            n_nodes=len(nodes),
            n_edges=len(edges),
            n_roots=n_roots,
        )

    def generate_from_rows(
        self,
        rows: Iterable[tuple[str, str]],
        session: "Session",
        title: str,
        release_code: str | None = None,
    ) -> CalculationsGraphResult:
        """Produce the full graph result from ``(code, expression)`` rows.

        Dependencies are resolved by the engine against *session* at
        *release_code* (latest when omitted).
        """
        release_id = self._resolve_release(session, release_code)
        ops = self.parse_operations(rows, session, release_id)
        nodes, edges, warnings = self.build_graph(ops)
        document = self.render_html(nodes, edges, title)
        return CalculationsGraphResult(
            nodes=nodes,
            edges=edges,
            html=document,
            warnings=warnings,
        )

    def generate(
        self,
        csv_path: Path,
        session: "Session",
        title: str | None = None,
        release_code: str | None = None,
    ) -> CalculationsGraphResult:
        """Read a CSV and produce the full graph result, HTML included.

        Dependencies are resolved by the engine against *session* at
        *release_code* (latest when omitted).
        """
        rows = _read_csv_rows(csv_path)
        final_title = title or f"Execution graph — {csv_path.name}"
        return self.generate_from_rows(
            rows, session, final_title, release_code
        )

    def generate_from_database(
        self,
        session: "Session",
        *,
        release_code: str | None = None,
        module_code: str | None = None,
        table_code: str | None = None,
        title: str | None = None,
    ) -> CalculationsGraphResult:
        """Build the graph from the DPM database using engine-resolved cells.

        Dependencies come from each operation's resolved operand tree (the
        engine's ``OperationNode`` / ``OperandReference`` data), matched on
        exact ``VariableID``. Filter by ``module_code``, ``table_code`` and/or
        ``release_code`` to bound the graph.
        """
        from dpmcore.services.calculations_graph import engine

        operations = engine.select_operations(
            session, release_code, module_code, table_code
        )
        cells = engine.operation_cells(session, list(operations))
        nodes, edges, warnings = engine.build(operations, cells)
        final_title = title or engine.default_title(
            module_code, table_code, release_code
        )
        document = self.render_html(nodes, edges, final_title)
        return CalculationsGraphResult(
            nodes=nodes,
            edges=edges,
            html=document,
            warnings=warnings,
        )


def _build_nodes(
    ops: list[_Operation], edges: dict[tuple[str, str], str]
) -> tuple[GraphNode, ...]:
    """Build node objects, marking roots (no incoming edge)."""
    indegree = {op.code: 0 for op in ops}
    for _src, dst in edges:
        indegree[dst] += 1
    return tuple(
        GraphNode(
            code=op.code,
            expression=op.expression,
            target=op.lhs_text,
            rhs=op.rhs_text,
            is_root=indegree[op.code] == 0,
        )
        for op in ops
    )
