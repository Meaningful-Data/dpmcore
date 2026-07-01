"""Build a self-contained HTML dependency graph for a calculations script.

A *calculations script* is a ``Code,Expression`` CSV in which every row is a
DPM-XL assignment operation of the form::

    <lhs selection> <- with {default:..., interval:...}: (<rhs expression>)

The left-hand side selection is the operation's *output*; the right-hand side
reads its *inputs* through selection operators ``{...}``. A dependency edge
``A -> B`` exists when operation ``B`` reads a cell that operation ``A`` writes
(implicit), or when ``B`` explicitly references ``{o<A-code>}`` (explicit).

Dependencies are derived from the DPM-XL **AST** (via :class:`SyntaxService`,
which needs no database), so wildcards, the sheet dimension, nested braces, the
``with`` clause and operation references are handled by the real parser rather
than by regular expressions. Concrete row-range expansion (the actual row codes
a ``0010-0050`` range covers) needs the database and is out of scope here; this
service does best-effort numeric range *overlap* instead.
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
_WILDCARD = "*"

# A cell key is ``(table, row, column, sheet)`` with each dimension being an
# exact code, a numeric range ``"lo-hi"``, or the wildcard ``"*"``.
CellKey = tuple[str, str, str, str]

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
    write_keys: set[CellKey] = field(default_factory=set)
    read_keys: set[CellKey] = field(default_factory=set)
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


def _varid_keys(node: VarID) -> set[CellKey]:
    """Expand a cell-selecting :class:`VarID` to its cartesian cell keys.

    A :class:`VarID` carrying neither a table nor any row/column/sheet (for
    example a ``with {default: 0}`` configuration clause) is not a cell
    selection and yields no keys — otherwise it would become an all-matching
    wildcard and link every operation to every other.
    """
    if (
        node.table is None
        and not node.rows
        and not node.cols
        and not node.sheets
    ):
        return set()
    table = node.table or _WILDCARD
    rows = node.rows or [_WILDCARD]
    cols = node.cols or [_WILDCARD]
    sheets = node.sheets or [_WILDCARD]
    return {
        (table, row, col, sheet)
        for row in rows
        for col in cols
        for sheet in sheets
    }


def _collect(root: AST) -> tuple[set[CellKey], set[str]]:
    """Return ``(cell_keys, op_refs)`` for one parsed expression part.

    A :class:`VarID` carrying an ``operation`` (or a bare
    :class:`OperationRef`) is an explicit operation reference rather than a
    cell selection.
    """
    keys: set[CellKey] = set()
    op_refs: set[str] = set()
    for node in _iter_ast(root):
        if isinstance(node, VarID):
            if node.operation is not None:
                op_refs.add(node.operation)
            else:
                keys |= _varid_keys(node)
        elif isinstance(node, OperationRef):
            op_refs.add(node.operation_code)
    return keys, op_refs


# --------------------------------------------------------------------------- #
# Cell-key matching
# --------------------------------------------------------------------------- #


def _as_range(token: str) -> tuple[int, int] | None:
    """Parse ``"lo-hi"`` into ``(lo, hi)`` ints, or ``None`` if not a range."""
    parts = token.split("-")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]), int(parts[1])
    return None


def _in_range(token: str, bounds: tuple[int, int]) -> bool:
    """Return whether a numeric *token* falls within *bounds* (inclusive)."""
    return token.isdigit() and bounds[0] <= int(token) <= bounds[1]


def _dim_overlap(left: str, right: str) -> bool:
    """Return whether two dimension values can refer to the same code."""
    if left == _WILDCARD or right == _WILDCARD:
        return True
    left_range = _as_range(left)
    right_range = _as_range(right)
    if left_range is None and right_range is None:
        return left == right
    if left_range is None:
        return _in_range(left, right_range)  # type: ignore[arg-type]
    if right_range is None:
        return _in_range(right, left_range)
    return left_range[0] <= right_range[1] and right_range[0] <= left_range[1]


def _cells_overlap(write_key: CellKey, read_key: CellKey) -> bool:
    """Return whether a written cell and a read cell can be the same cell."""
    return all(_dim_overlap(write_key[dim], read_key[dim]) for dim in range(4))


def _producers_for(
    read_keys: set[CellKey],
    writes_by_table: dict[str, list[tuple[str, CellKey]]],
) -> set[str]:
    """Return codes of operations that write any cell in *read_keys*."""
    producers: set[str] = set()
    for read_key in read_keys:
        table = read_key[0]
        if table == _WILDCARD:
            candidates = [
                entry
                for bucket in writes_by_table.values()
                for entry in bucket
            ]
        else:
            candidates = writes_by_table.get(table, []) + writes_by_table.get(
                _WILDCARD, []
            )
        for producer_code, write_key in candidates:
            if _cells_overlap(write_key, read_key):
                producers.add(producer_code)
    return producers


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
            f"Operation {op.code!r}: expression could not be parsed "
            f"({op.parse_error}); its dependencies were skipped."
        )
    if op.code.startswith("o"):
        out.append(
            f"Operation code {op.code!r} starts with 'o'; explicit "
            "{o...} references use that prefix, so operation codes "
            "should not begin with 'o'."
        )
    return out


def _add_edge(
    edges: dict[tuple[str, str], str],
    source: str,
    target: str,
    kind: str,
) -> None:
    """Record an edge, keeping an existing (explicit) kind if present."""
    edges.setdefault((source, target), kind)


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

    The service is stateless and needs **no** database connection — it parses
    each expression with :class:`SyntaxService` and derives dependencies from
    the resulting AST.
    """

    def __init__(self) -> None:
        """Build a stateless calculations-graph service."""
        self._syntax = SyntaxService()

    def parse_operations(
        self, rows: Iterable[tuple[str, str]]
    ) -> list[_Operation]:
        """Parse ``(code, expression)`` rows into operations.

        An expression that fails to parse is not fatal: its dependencies are
        skipped and the failure is recorded on the operation so the node still
        renders.
        """
        ops: list[_Operation] = []
        for code, expression in rows:
            lhs_text, rhs_text = _split_assignment(expression)
            write_keys, read_keys, op_refs, error = self._extract_keys(
                expression
            )
            ops.append(
                _Operation(
                    code=code,
                    expression=expression,
                    lhs_text=lhs_text,
                    rhs_text=rhs_text,
                    write_keys=write_keys,
                    read_keys=read_keys,
                    op_refs=op_refs,
                    parse_error=error,
                )
            )
        return ops

    def _collect_part(
        self, text: str
    ) -> tuple[set[CellKey], set[str], str | None]:
        """Parse one expression part, returning keys, op refs and any error.

        The ``<-`` persistent-assignment form is not a valid top-level
        statement, so each side is parsed independently — a selection or a
        ``with {..}: expr`` body both parse standalone.
        """
        if not text.strip():
            return set(), set(), None
        try:
            ast = self._syntax.parse(text)
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            return set(), set(), str(exc)
        keys, op_refs = _collect(ast)
        return keys, op_refs, None

    def _extract_keys(
        self, expression: str
    ) -> tuple[set[CellKey], set[CellKey], set[str], str | None]:
        """Return ``(writes, reads, op_refs, error)`` for an expression.

        The left-hand selection (before ``<-``) supplies the written cells;
        the right-hand side supplies the read cells and operation references.
        An expression without ``<-`` has no writes (validation-style).
        """
        lhs_text, rhs_text = _split_assignment(expression)
        write_keys: set[CellKey] = set()
        lhs_error: str | None = None
        if "<-" in expression:
            write_keys, _, lhs_error = self._collect_part(lhs_text)
        read_keys, op_refs, rhs_error = self._collect_part(rhs_text)
        error = "; ".join(e for e in (lhs_error, rhs_error) if e) or None
        return write_keys, read_keys, op_refs, error

    def build_graph(
        self, ops: list[_Operation]
    ) -> tuple[tuple[GraphNode, ...], tuple[GraphEdge, ...], tuple[str, ...]]:
        """Build nodes, edges and warnings from parsed operations."""
        codes = {op.code for op in ops}
        writes_by_table: dict[str, list[tuple[str, CellKey]]] = defaultdict(
            list
        )
        for op in ops:
            for key in op.write_keys:
                writes_by_table[key[0]].append((op.code, key))

        edges: dict[tuple[str, str], str] = {}
        warnings: list[str] = []
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
            for producer in sorted(
                _producers_for(op.read_keys, writes_by_table)
            ):
                if producer != op.code:
                    _add_edge(edges, producer, op.code, "implicit")

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
        self, rows: Iterable[tuple[str, str]], title: str
    ) -> CalculationsGraphResult:
        """Produce the full graph result from ``(code, expression)`` rows."""
        ops = self.parse_operations(rows)
        nodes, edges, warnings = self.build_graph(ops)
        document = self.render_html(nodes, edges, title)
        return CalculationsGraphResult(
            nodes=nodes,
            edges=edges,
            html=document,
            warnings=warnings,
        )

    def generate(
        self, csv_path: Path, title: str | None = None
    ) -> CalculationsGraphResult:
        """Read a CSV and produce the full graph result, HTML included."""
        rows = _read_csv_rows(csv_path)
        final_title = title or f"Execution graph — {csv_path.name}"
        return self.generate_from_rows(rows, final_title)

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
