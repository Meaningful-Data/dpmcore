#!/usr/bin/env python3
"""Generate a portable, self-contained HTML execution graph for a DPM-XL
calculations script.

A calculations script (CSV with ``Code,Expression`` columns) is a set of
DPM-XL assignment operations that a runtime must order by their dependencies.
Each operation has the shape::

    <lhs selection> <- with {default:..., interval:...}: (<rhs expression>)

The left-hand side selection is the operation's *output*; the right-hand side
references its *inputs* through selection operators ``{...}``.  A dependency
edge ``A -> B`` is created whenever operation ``B`` consumes the output of
operation ``A`` -- either explicitly via an operation reference ``{o<code>,...}``
or implicitly by selecting a cell that ``A`` produces (matching table/row/col).

The output is a single ``.html`` file with Cytoscape.js (+ dagre layout)
embedded inline, so it works offline with no external requests.  Each node
shows the operation code; clicking a node reveals its full expression.

Usage::

    python scripts/generate_calculations_graph.py \
        input/calculations_script.csv -o output/calculations_graph.html
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
VENDOR_FILES = ("cytoscape.min.js", "dagre.min.js", "cytoscape-dagre.min.js")

# A selection operator is anything inside curly braces.  Used both for the LHS
# target and to find input references inside the RHS expression.
SELECTION_RE = re.compile(r"\{([^{}]*)\}")
# The "with" properties clause, e.g. ``with {default:0, interval:false}``.  It
# uses braces too, so it must be stripped before scanning for real selections.
WITH_CLAUSE_RE = re.compile(r"with\s*\{[^{}]*\}", re.IGNORECASE)


@dataclass
class Operation:
    code: str
    expression: str
    lhs_raw: str  # the raw LHS selection content, e.g. "tK_61.00, r0010, c0010"
    rhs: str  # the right-hand side expression (after the with-clause colon)
    produces: tuple[str, ...]  # normalized cell keys this op writes to
    consumes: set[str] = field(default_factory=set)  # cell keys it reads
    op_refs: set[str] = field(default_factory=set)  # explicit {o<code>} refs


def split_assignment(expression: str) -> tuple[str, str]:
    """Split an operation expression into (lhs, rhs).

    ``lhs <- with {..}: rhs``  ->  ("lhs", "rhs").  The with-clause is
    optional; we always split on the first ``<-`` and then drop a leading
    ``with {..}:`` (or just ``:``) from the right side.
    """
    if "<-" not in expression:
        # Not an assignment; treat the whole thing as the rhs with no target.
        return "", expression.strip()
    lhs, rhs = expression.split("<-", 1)
    rhs = WITH_CLAUSE_RE.sub("", rhs, count=1)
    # Drop the leading colon that separates the with-clause from the expression.
    rhs = rhs.lstrip()
    if rhs.startswith(":"):
        rhs = rhs[1:]
    return lhs.strip(), rhs.strip()


def normalize_cell(selection_body: str) -> list[str]:
    """Turn a selection body into one or more normalized cell keys.

    A key is ``<ref>|<row>|<col>`` (sheet ignored for matching).  ``ref`` keeps
    its type prefix stripped so that an LHS ``tK_61.00`` and an RHS ``tK_61.00``
    compare equal.  Multi-cell selections (comma lists, parenthesised groups)
    expand to the cartesian product of their rows and columns so that producing
    or consuming any of those cells is detected.
    """
    # Flatten parenthesised groups like "(c0140, c0150)" -> "c0140, c0150".
    body = selection_body.replace("(", " ").replace(")", " ")
    tokens = [t.strip() for t in body.split(",") if t.strip()]
    if not tokens:
        return []

    ref = tokens[0]
    # Strip the leading type marker (t=table, v=variable, o=operation).
    ref_id = ref[1:] if ref[:1] in {"t", "v", "o"} else ref

    rows: list[str] = []
    cols: list[str] = []
    sheets: list[str] = []
    for tok in tokens[1:]:
        head = tok[:1]
        if head == "r":
            rows.append(tok)
        elif head == "c":
            cols.append(tok)
        elif head == "s":
            sheets.append(tok)
    rows = rows or ["*"]
    cols = cols or ["*"]

    return [f"{ref_id}|{r}|{c}" for r in rows for c in cols]


def parse_operations(csv_path: Path) -> list[Operation]:
    ops: list[Operation] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if not header or header[0].strip().lower() != "code":
            raise ValueError(
                f"Expected a 'Code,Expression' header, got: {header!r}"
            )
        for row in reader:
            if not row or not row[0].strip():
                continue
            code = row[0].strip()
            expression = row[1].strip() if len(row) > 1 else ""
            lhs, rhs = split_assignment(expression)

            lhs_match = SELECTION_RE.search(lhs)
            lhs_body = lhs_match.group(1) if lhs_match else lhs
            produces = tuple(normalize_cell(lhs_body)) if lhs_body else ()

            consumes: set[str] = set()
            op_refs: set[str] = set()
            for m in SELECTION_RE.finditer(rhs):
                body = m.group(1)
                first = body.split(",", 1)[0].strip()
                if first[:1] == "o":  # explicit operation reference {o<code>,...}
                    op_refs.add(first[1:])
                consumes.update(normalize_cell(body))

            ops.append(
                Operation(
                    code=code,
                    expression=expression,
                    lhs_raw=lhs_body,
                    rhs=rhs,
                    produces=produces,
                    consumes=consumes,
                    op_refs=op_refs,
                )
            )
    return ops


def build_graph(ops: list[Operation]) -> tuple[list[dict], list[dict]]:
    """Return (nodes, edges) as Cytoscape element dicts."""
    # Map every produced cell to the operation code that produces it.
    cell_to_code: dict[str, str] = {}
    for op in ops:
        for cell in op.produces:
            cell_to_code[cell] = op.code
    codes = {op.code for op in ops}

    nodes = [
        {
            "data": {
                "id": op.code,
                "label": op.code,
                "expression": op.expression,
                "target": op.lhs_raw,
                "rhs": op.rhs,
            }
        }
        for op in ops
    ]

    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add_edge(src: str, dst: str) -> None:
        if src == dst or src not in codes:
            return
        key = (src, dst)
        if key in seen:
            return
        seen.add(key)
        edges.append({"data": {"id": f"{src}->{dst}", "source": src, "target": dst}})

    for op in ops:
        # Implicit dependency: this op consumes a cell another op produces.
        for cell in op.consumes:
            producer = cell_to_code.get(cell)
            if producer:
                add_edge(producer, op.code)
        # Explicit dependency: {o<code>} reference.
        for ref in op.op_refs:
            if ref in codes:
                add_edge(ref, op.code)

    return nodes, edges


def read_vendor() -> dict[str, str]:
    libs: dict[str, str] = {}
    for name in VENDOR_FILES:
        path = VENDOR_DIR / name
        if not path.exists():
            raise FileNotFoundError(
                f"Missing vendored library: {path}.\n"
                "Download it once into scripts/vendor/ (see the project docs)."
            )
        libs[name] = path.read_text(encoding="utf-8")
    return libs


def render_html(nodes: list[dict], edges: list[dict], title: str) -> str:
    libs = read_vendor()
    elements = json.dumps(nodes + edges)
    n_nodes, n_edges = len(nodes), len(edges)
    roots = sum(1 for n in nodes if not any(e["data"]["target"] == n["data"]["id"] for e in edges))
    return TEMPLATE.format(
        title=html.escape(title),
        cytoscape_js=libs["cytoscape.min.js"],
        dagre_js=libs["dagre.min.js"],
        dagre_ext_js=libs["cytoscape-dagre.min.js"],
        elements=elements,
        n_nodes=n_nodes,
        n_edges=n_edges,
        n_roots=roots,
    )


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --bg:#0f1117; --panel:#1b1f2a; --border:#2c3242; --text:#e6e9ef;
           --muted:#9aa3b2; --accent:#4f9cff; --root:#3ddc97; --edge:#5b6477; }}
  * {{ box-sizing:border-box; }}
  html,body {{ margin:0; height:100%; font-family:-apple-system,Segoe UI,Roboto,sans-serif;
               background:var(--bg); color:var(--text); }}
  #app {{ display:flex; height:100vh; }}
  #cy {{ flex:1; height:100%; }}
  #side {{ width:420px; min-width:300px; max-width:50vw; background:var(--panel);
           border-left:1px solid var(--border); display:flex; flex-direction:column; }}
  header {{ padding:14px 16px; border-bottom:1px solid var(--border); }}
  header h1 {{ font-size:15px; margin:0 0 6px; }}
  header .stats {{ font-size:12px; color:var(--muted); }}
  .controls {{ padding:10px 16px; border-bottom:1px solid var(--border);
               display:flex; gap:8px; flex-wrap:wrap; align-items:center; }}
  .controls input {{ flex:1; min-width:120px; background:var(--bg); color:var(--text);
                     border:1px solid var(--border); border-radius:6px; padding:6px 8px; font-size:12px; }}
  .controls button {{ background:var(--bg); color:var(--text); border:1px solid var(--border);
                      border-radius:6px; padding:6px 10px; font-size:12px; cursor:pointer; }}
  .controls button:hover {{ border-color:var(--accent); }}
  #detail {{ padding:16px; overflow:auto; flex:1; }}
  #detail .empty {{ color:var(--muted); font-size:13px; }}
  #detail h2 {{ font-size:14px; margin:0 0 4px; color:var(--accent); word-break:break-all; }}
  #detail .field {{ margin:14px 0 4px; font-size:11px; text-transform:uppercase;
                    letter-spacing:.05em; color:var(--muted); }}
  #detail pre {{ background:var(--bg); border:1px solid var(--border); border-radius:6px;
                 padding:10px; font-size:12px; white-space:pre-wrap; word-break:break-word;
                 line-height:1.5; margin:0; }}
  .legend {{ font-size:11px; color:var(--muted); padding:8px 16px; border-top:1px solid var(--border); }}
  .legend span {{ display:inline-flex; align-items:center; gap:5px; margin-right:14px; }}
  .dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
</style>
</head>
<body>
<div id="app">
  <div id="cy"></div>
  <aside id="side">
    <header>
      <h1>{title}</h1>
      <div class="stats">{n_nodes} operations &middot; {n_edges} dependencies &middot; {n_roots} roots (no inputs from other ops)</div>
    </header>
    <div class="controls">
      <input id="search" type="text" placeholder="Filter by code...">
      <button id="fit">Fit</button>
      <button id="relayout">Re-layout</button>
    </div>
    <div id="detail"><div class="empty">Click a node to see its expression.</div></div>
    <div class="legend">
      <span><span class="dot" style="background:var(--root)"></span>root</span>
      <span><span class="dot" style="background:var(--accent)"></span>operation</span>
    </div>
  </aside>
</div>

<script>{cytoscape_js}</script>
<script>{dagre_js}</script>
<script>{dagre_ext_js}</script>
<script>
const ELEMENTS = {elements};

const cy = cytoscape({{
  container: document.getElementById('cy'),
  elements: ELEMENTS,
  wheelSensitivity: 0.2,
  style: [
    {{ selector: 'node', style: {{
        'background-color': '#4f9cff',
        'label': 'data(label)', 'color': '#e6e9ef',
        'font-size': 9, 'text-valign': 'center', 'text-halign': 'center',
        'width': 'label', 'height': 18, 'shape': 'round-rectangle',
        'padding': '6px', 'text-wrap': 'none', 'border-width': 1, 'border-color': '#2c3242'
    }} }},
    {{ selector: 'node[?isRoot]', style: {{ 'background-color': '#3ddc97', 'color':'#0f1117' }} }},
    {{ selector: 'edge', style: {{
        'width': 1.4, 'line-color': '#5b6477', 'target-arrow-color': '#5b6477',
        'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'arrow-scale': 0.8
    }} }},
    {{ selector: '.selected', style: {{ 'background-color': '#ffd166', 'color':'#0f1117', 'border-color':'#ffd166' }} }},
    {{ selector: '.faded', style: {{ 'opacity': 0.12 }} }},
    {{ selector: '.hl-in', style: {{ 'line-color':'#3ddc97', 'target-arrow-color':'#3ddc97', 'width':2.5 }} }},
    {{ selector: '.hl-out', style: {{ 'line-color':'#ffd166', 'target-arrow-color':'#ffd166', 'width':2.5 }} }}
  ]
}});

// Mark roots (nodes with no incoming edge) for styling.
cy.nodes().forEach(n => {{ if (n.indegree(false) === 0) n.data('isRoot', true); }});

function runLayout() {{
  const hasEdges = cy.edges().length > 0;
  const layout = hasEdges
    ? {{ name: 'dagre', rankDir: 'TB', nodeSep: 18, rankSep: 55, edgeSep: 8, animate: false }}
    : {{ name: 'grid', avoidOverlap: true, condense: true }};
  cy.layout(layout).run();
}}
runLayout();

const detail = document.getElementById('detail');
function esc(s) {{ return (s||'').replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c])); }}

function showNode(n) {{
  const d = n.data();
  detail.innerHTML =
    '<h2>' + esc(d.label) + '</h2>' +
    '<div class="field">Target (output)</div><pre>' + esc(d.target) + '</pre>' +
    '<div class="field">Expression</div><pre>' + esc(d.expression) + '</pre>' +
    '<div class="field">Right-hand side</div><pre>' + esc(d.rhs) + '</pre>';
}}

function highlight(n) {{
  cy.elements().removeClass('selected faded hl-in hl-out');
  const inc = n.incomers();
  const out = n.outgoers();
  const keep = n.union(inc).union(out);
  cy.elements().not(keep).addClass('faded');
  n.addClass('selected');
  inc.edges().addClass('hl-in');
  out.edges().addClass('hl-out');
}}

cy.on('tap', 'node', e => {{ showNode(e.target); highlight(e.target); }});
cy.on('tap', e => {{ if (e.target === cy) {{
  cy.elements().removeClass('selected faded hl-in hl-out');
  detail.innerHTML = '<div class="empty">Click a node to see its expression.</div>';
}} }});

document.getElementById('fit').onclick = () => cy.fit(undefined, 30);
document.getElementById('relayout').onclick = runLayout;
document.getElementById('search').addEventListener('input', e => {{
  const q = e.target.value.trim().toLowerCase();
  cy.elements().removeClass('faded');
  if (!q) return;
  cy.nodes().forEach(n => {{
    if (!n.data('label').toLowerCase().includes(q)) n.addClass('faded');
  }});
}});
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", type=Path, help="Path to the calculations script CSV.")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("output/calculations_graph.html"),
        help="Output HTML path (default: output/calculations_graph.html).",
    )
    parser.add_argument(
        "-t", "--title", default=None, help="Graph title (default: input file name)."
    )
    args = parser.parse_args(argv)

    if not args.csv.exists():
        parser.error(f"Input CSV not found: {args.csv}")

    ops = parse_operations(args.csv)
    nodes, edges = build_graph(ops)
    title = args.title or f"Execution graph — {args.csv.name}"
    output_html = render_html(nodes, edges, title)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output_html, encoding="utf-8")

    print(
        f"Parsed {len(ops)} operations, {len(edges)} dependency edges.\n"
        f"Wrote portable graph to {args.output} "
        f"({args.output.stat().st_size // 1024} KiB, self-contained)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
