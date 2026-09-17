"""Build an engine-ready ``ast`` JSON dict directly from the persisted
``OperationNode``/``OperandReference``/``OperandReferenceLocation`` tree
(dpmcore#364), instead of re-parsing the expression text.

:class:`_Builder` reconstructs the same real ``dpm_xl.ast.nodes`` objects
a freshly-parsed expression would produce; :class:`_DbAstToJSONVisitor`
(a thin :class:`~dpmcore.dpm_xl.utils.serialization.ASTToJSONVisitor`
subclass) then serializes them the same way a fresh parse would — only
``VarID``/``VarRef``/a DB-only ``sub`` stand-in need overrides, each
documented at its class. The tree is read via
:class:`~dpmcore.services.structure.StructureService`'s existing
bulk-load helpers, not re-queried from scratch.

Where dpmcore's text-reparse path and mdpm's validated output disagree
(``VarID.data``'s coordinate handling), this module matches mdpm's
``util/mdm-export.py`` ``build_node`` — porting mdpm's correctness is
the goal, not preserving dpmcore's current output.

Standalone: every function here takes a SQLAlchemy ``session`` and DB
identifiers (``operation_vid``, ``release_id``), never an expression
string or anything from
:class:`~dpmcore.services.ast_generator.ASTGeneratorService`'s
``script()`` contract. Callers decide, per operation, whether to use
this module or fall back to the text-reparse path.

Not everything can be reconstructed from what's persisted today
(parameters, time shifts, ...). Whenever this module can't safely
rebuild a node it raises :class:`UnsupportedDbAst` — the caller falls
back to the text-reparse path. This module never guesses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from dpmcore.dpm_xl.ast import nodes as ast_nodes
from dpmcore.dpm_xl.utils.filters import filter_by_release
from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor
from dpmcore.orm.glossary import ItemCategory, Property
from dpmcore.orm.infrastructure import DataType
from dpmcore.orm.operations import (
    OperandReference,
    OperandReferenceLocation,
    OperationNode,
)
from dpmcore.orm.variables import VariableVersion
from dpmcore.services.structure import StructureService

__all__ = [
    "UnsupportedDbAst",
    "build_ast_dict_from_db",
    "_load_tree",
    "_root",
]


class UnsupportedDbAst(Exception):
    """Raised when an operation's AST cannot be safely rebuilt from the DB.

    Always a request to fall back to the text-reparse path for this one
    operation — never a signal that the DB data itself is broken.
    """


@dataclass
class _Tree:
    """The rows :class:`StructureService` already loaded for one
    ``OperationVID``, re-indexed the way this module needs to walk them.
    """

    children_by_parent: Dict[Optional[int], List[OperationNode]] = field(
        default_factory=dict
    )
    refs_by_node: Dict[int, List[OperandReference]] = field(
        default_factory=dict
    )
    locations_by_ref: Dict[int, OperandReferenceLocation] = field(
        default_factory=dict
    )


def _load_tree(session: Session, operation_vid: int) -> _Tree:
    """Load *operation_vid*'s node tree via ``StructureService``'s own
    bulk-load helpers (the same ones behind the ``explorer``/structure
    API), instead of duplicating their queries here.
    """
    structure = StructureService(session)

    nodes_by_vid = structure._bulk_load_operation_nodes([operation_vid])
    nodes = nodes_by_vid.get(operation_vid, [])
    if not nodes:
        raise UnsupportedDbAst(
            f"No OperationNode rows for OperationVID={operation_vid}"
        )

    tree = _Tree()
    node_ids: List[int] = []
    for n in nodes:
        tree.children_by_parent.setdefault(n.parent_node_id, []).append(n)
        node_ids.append(n.node_id)

    refs_by_node = structure._bulk_load_operand_references(node_ids)
    tree.refs_by_node = dict(refs_by_node)

    ref_ids = [
        r.operand_reference_id for rs in refs_by_node.values() for r in rs
    ]
    if ref_ids:
        locs_by_ref = structure._bulk_load_reference_locations(ref_ids)
        for ref_id, locs in locs_by_ref.items():
            if locs:
                tree.locations_by_ref[ref_id] = locs[0]

    return tree


def _root(tree: _Tree) -> OperationNode:
    """Return the tree's single root node (``parent_node_id is None``)."""
    roots = tree.children_by_parent.get(None, [])
    if len(roots) != 1:
        raise UnsupportedDbAst(
            f"Expected exactly one root OperationNode, found {len(roots)}"
        )
    return roots[0]


# --------------------------------------------------------------------- #
# Operator classification (OperatorID -> how to rebuild the node),
# derived at runtime from ``Operator``/``OperatorArgument`` via
# :class:`~dpmcore.dpm_xl.model_queries.OperatorQuery` — dpmcore's own
# equivalent of mdpm's ``load_data()``/``get_class_names()`` masks
# (``util/mdm-export.py``). No hardcoded OperatorIDs: classifying by
# ``Type``/``Name``/argument-name-set mirrors mdpm's approach and won't
# silently break if the schema renumbers or adds a same-shape operator.
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class _OperatorShape:
    class_name: str
    # For BinOp only: the (left_arg_name, right_arg_name) pair to map to
    # the wire "left"/"right" keys — differs per operator (e.g. "in"'s
    # "operand"/"set", "match"'s "operand"/"pattern").
    binop_args: Optional[Tuple[str, str]] = None


def _classify_operators(session: Session) -> Dict[int, _OperatorShape]:
    """``{OperatorID: _OperatorShape}`` for every operator in the DB."""
    from dpmcore.dpm_xl.model_queries import OperatorQuery

    operators = OperatorQuery.get_operators(session)
    arguments = OperatorQuery.get_arguments(session)

    arg_names_by_op: Dict[int, List[str]] = {}
    for row in arguments.itertuples():
        arg_names_by_op.setdefault(int(row.OperatorID), []).append(row.Name)

    shapes: Dict[int, _OperatorShape] = {}
    for row in operators.itertuples():
        op_id = int(row.OperatorID)
        name_set = set(arg_names_by_op.get(op_id, []))

        if row.Type == "Conditional" and name_set == {
            "condition",
            "then",
            "else",
        }:
            shapes[op_id] = _OperatorShape("CondExpr")
        elif row.Name == "Parenthesis Expression":
            shapes[op_id] = _OperatorShape("ParExpr")
        elif row.Name == "Grouping clause":
            shapes[op_id] = _OperatorShape("GroupingClause")
        elif row.Type == "Aggregate" and "grouping_clause" in name_set:
            shapes[op_id] = _OperatorShape("AggregationOp")
        elif row.Name in ("Numeric maximum", "Numeric minimum"):
            shapes[op_id] = _OperatorShape("ComplexNumericOp")
        elif row.Name == "Match characters":
            shapes[op_id] = _OperatorShape("BinOp", ("operand", "pattern"))
        elif name_set == {"operand", "set"}:
            shapes[op_id] = _OperatorShape("BinOp", ("operand", "set"))
        elif name_set == {"left", "right"} and row.Type != "Assignment":
            shapes[op_id] = _OperatorShape("BinOp", ("left", "right"))
        elif row.Name == "Where" and row.Type == "Clause":
            shapes[op_id] = _OperatorShape("WhereClauseOp")
        elif row.Name == "Get" and row.Type == "Clause":
            shapes[op_id] = _OperatorShape("GetClauseOp")
        elif row.Name == "Sub" and row.Type == "Clause":
            shapes[op_id] = _OperatorShape("SubClauseOp")
        elif row.Name == "Filter":
            shapes[op_id] = _OperatorShape("FilterOp")
        elif row.Name == "Rename":
            shapes[op_id] = _OperatorShape("RenameOp")
        elif row.Name == "RenameNode":
            shapes[op_id] = _OperatorShape("RenameNode")
        elif row.Name == "Time shift":
            # Excluded: TimeShiftOp's period_indicator is hardcoded to
            # "Q" at write time (a pre-existing bug in MLGeneration), so
            # it cannot be trusted from the DB. Classified (not simply
            # omitted) so build() can report *why* it falls back, rather
            # than a generic "unclassified operator".
            shapes[op_id] = _OperatorShape("TimeShiftOp")
        elif name_set == {"operand"}:
            shapes[op_id] = _OperatorShape("UnaryOp")
        # Anything else (ParameterRef has no operator at all;
        # AnnualiseOp/SubstrOp aren't in the DPM operator seed data) is
        # left unclassified — build() raises UnsupportedDbAst for it.

    return shapes


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")


def _normalize_date(text: str) -> Optional[str]:
    """Parse *text* as ``YYYY-MM-DD`` or ``DD/MM/YYYY``, or return ``None``.

    Mirrors mdpm's ``normalize_date`` (``util/mdm-export.py``) — the two
    formats it accepts, always re-formatted to ``YYYY-MM-DD``.
    """
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _infer_scalar(text: str) -> Tuple[str, Any]:
    """Infer a ``Constant``'s ``(type_, value)`` from its raw stored text.

    There is no separate type column for a leaf's ``Scalar`` text, so
    this has to be a heuristic — matched exactly to mdpm's own
    ``build_node`` ``Constant`` branch (``util/mdm-export.py``), since
    mdpm's algorithm is the validated reference: exact ``"true"``/
    ``"false"`` match, then ``float()`` with ``is_integer()`` deciding
    Integer vs Number, then a date parse, then String.
    """
    if text in ("true", "false"):
        return "Boolean", text == "true"
    try:
        scalar = float(text)
    except ValueError:
        normalized = _normalize_date(text)
        if normalized is not None:
            return "Date", normalized
        return "String", text
    if scalar.is_integer():
        return "Integer", int(scalar)
    return "Number", scalar


def _children_by_argument(
    tree: _Tree, node: OperationNode
) -> Dict[str, List[OperationNode]]:
    """Group *node*'s children by their ``OperatorArgument.name``.

    Children sharing the same argument name (a variadic slot, e.g.
    ``ComplexNumericOp.operands``) keep DB insertion order (ascending
    ``node_id``) — ``OperationNode`` carries no explicit sibling-order
    column, so this is the same implicit convention the writer relies on.
    """
    by_arg: Dict[str, List[OperationNode]] = {}
    for child in sorted(
        tree.children_by_parent.get(node.node_id, []),
        key=lambda c: c.node_id,
    ):
        arg = child.operator_argument
        name = arg.name if arg is not None else None
        if name is None:
            raise UnsupportedDbAst(
                f"Child node {child.node_id} has no OperatorArgument name"
            )
        by_arg.setdefault(name, []).append(child)
    return by_arg


def _one(children: Dict[str, List[OperationNode]], name: str) -> OperationNode:
    items = children.get(name)
    if not items or len(items) != 1:
        raise UnsupportedDbAst(f"Expected exactly one '{name}' child")
    return items[0]


class _DbSubClauseOp:
    """Stand-in for the DB's persisted ``sub`` shape (``operand``/
    ``condition``, like ``WhereClauseOp``) — not a real
    ``dpm_xl.ast.nodes`` class.

    ``nodes.SubOp`` expects ``operand``/``substitutions`` instead, which
    would require re-deriving a ``property_code=value`` list from a
    generic ``condition`` subtree. Building the wire shape directly (via
    :class:`_DbAstToJSONVisitor` below) is simpler.
    """

    def __init__(self, operand: Any, condition: Any) -> None:
        self.operand = operand
        self.condition = condition


class _DbAstToJSONVisitor(ASTToJSONVisitor):
    """Reuses dpmcore's own visitor unchanged for every node type it can;
    only ``VarID``/``VarRef``/the DB-only ``sub`` stand-in are overridden
    below, each for a documented reason it would be wrong to inherit the
    base behaviour.
    """

    def visit_VarID(self, node: Any) -> Dict[str, Any]:
        """Base ``visit_VarID`` recomputes ``node.data`` from a pandas
        DataFrame and reads the wrong field for ``operand_reference_id``
        (dpmcore#364). :meth:`_Builder._build_varid` already built the
        correct dict; this just returns it.
        """
        return node._db_ast_dict  # type: ignore[attr-defined]

    def visit_VarRef(self, node: Any) -> Dict[str, Any]:
        """``ASTToJSONVisitor`` has no ``visit_VarRef``; ``generic_visit``
        would silently drop ``variable``. Confirmed via
        ``ml_generation.py``'s ``visit_VarRef``/``_precondition_codes.py``:
        ``variable`` holds the variable *code*, not its id.
        """
        return {"class_name": "VarRef", "variable": node.variable}

    def visit__DbSubClauseOp(self, node: "_DbSubClauseOp") -> Dict[str, Any]:
        return {
            "class_name": "SubClauseOp",
            "operand": self.visit(node.operand),
            "condition": self.visit(node.condition),
        }


class _Builder:
    """Walks one operation's :class:`_Tree`, building real
    ``dpm_xl.ast.nodes`` objects — the same classes a freshly-parsed
    expression produces. :func:`build_ast_dict_from_db` hands the
    result to :class:`_DbAstToJSONVisitor` to get the JSON dict.
    """

    def __init__(self, session: Session, tree: _Tree, release_id: int) -> None:
        self._session = session
        self._tree = tree
        self._release_id = release_id
        self._data_type_cache: Dict[int, str] = {}
        self._signature_cache: Dict[int, str] = {}
        self._code_cache: Dict[int, str] = {}
        self._shapes = _classify_operators(session)

    # ------------------------------------------------------------- #
    # Dispatch
    # ------------------------------------------------------------- #

    def build(self, node: OperationNode) -> Any:
        if node.is_leaf:
            return self._build_leaf(node)

        op_id = node.operator_id
        shape = self._shapes.get(op_id) if op_id is not None else None
        if shape is None:
            raise UnsupportedDbAst(
                f"Unsupported or missing OperatorID on node {node.node_id}"
            )
        if shape.class_name == "TimeShiftOp":
            raise UnsupportedDbAst(
                f"TimeShiftOp (node {node.node_id}) is unsupported: its "
                "period_indicator can't be trusted from the DB"
            )

        children = _children_by_argument(self._tree, node)
        symbol = self._symbol(node)

        if shape.class_name == "UnaryOp":
            return ast_nodes.UnaryOp(
                op=symbol, operand=self.build(_one(children, "operand"))
            )
        if shape.class_name == "BinOp":
            left_name, right_name = shape.binop_args
            return ast_nodes.BinOp(
                left=self.build(_one(children, left_name)),
                op=symbol,
                right=self.build(_one(children, right_name)),
            )
        if shape.class_name == "ComplexNumericOp":
            operands = children.get("operand") or []
            if len(operands) < 2:
                raise UnsupportedDbAst(
                    "ComplexNumericOp with fewer than 2 operands"
                )
            return ast_nodes.ComplexNumericOp(
                op=symbol, operands=[self.build(c) for c in operands]
            )
        if shape.class_name == "AggregationOp":
            return self._build_aggregation(symbol, children)
        if shape.class_name == "CondExpr":
            return self._build_cond_expr(children)
        if shape.class_name == "ParExpr":
            return ast_nodes.ParExpr(
                expression=self.build(_one(children, "expression"))
            )
        if shape.class_name == "GetClauseOp":
            return ast_nodes.GetOp(
                operand=self.build(_one(children, "operand")),
                component=self._component_text(_one(children, "component")),
            )
        if shape.class_name == "WhereClauseOp":
            return ast_nodes.WhereClauseOp(
                operand=self.build(_one(children, "operand")),
                condition=self.build(_one(children, "condition")),
            )
        if shape.class_name == "SubClauseOp":
            return _DbSubClauseOp(
                operand=self.build(_one(children, "operand")),
                condition=self.build(_one(children, "condition")),
            )
        if shape.class_name == "FilterOp":
            return ast_nodes.FilterOp(
                selection=self.build(_one(children, "selection")),
                condition=self.build(_one(children, "condition")),
            )
        if shape.class_name == "RenameOp":
            rename_nodes = [
                self._build_rename_node(n) for n in children.get("node") or []
            ]
            return ast_nodes.RenameOp(
                operand=self.build(_one(children, "operand")),
                rename_nodes=rename_nodes,
            )
        raise UnsupportedDbAst(
            f"Unhandled shape {shape.class_name!r} for OperatorID={op_id}"
        )

    def _symbol(self, node: OperationNode) -> str:
        op = node.operator
        if op is None or op.symbol is None:
            raise UnsupportedDbAst(
                f"Node {node.node_id} has no resolvable Operator.Symbol"
            )
        return op.symbol

    def _build_aggregation(
        self, symbol: str, children: Dict[str, List[OperationNode]]
    ) -> Any:
        operand = self.build(_one(children, "operand"))
        grouping_clause = None
        if children.get("grouping_clause"):
            grouping_clause = self._build_grouping_clause(
                _one(children, "grouping_clause")
            )
        return ast_nodes.AggregationOp(
            op=symbol,
            operand=operand,
            grouping_clause=grouping_clause,
            analytic_clause=None,
        )

    def _build_grouping_clause(self, node: OperationNode) -> Optional[Any]:
        shape = self._shapes.get(node.operator_id)
        if shape is None or shape.class_name != "GroupingClause":
            raise UnsupportedDbAst("Expected a GroupingClause node")
        component_nodes = sorted(
            self._tree.children_by_parent.get(node.node_id, []),
            key=lambda c: c.node_id,
        )
        components: List[str] = [
            self._component_text(c) for c in component_nodes
        ]
        if not components:
            return None
        return ast_nodes.GroupingClause(components=components)

    def _component_text(self, node: OperationNode) -> str:
        """A plain-string component reference: an ``r``/``c``/``s`` axis
        marker, or a property *code* — never a nested node. mdpm's
        ``build_node`` reads ``ItemCategory.Code`` here, not ``Signature``
        (unlike ``Scalar``/``Set``).
        """
        refs = self._tree.refs_by_node.get(node.node_id) or []
        if len(refs) == 1:
            ref = refs[0]
            if ref.operand_reference in ("r", "c", "s"):
                return ref.operand_reference
            if ref.operand_reference == "property" and ref.property_id is not None:
                return self._item_category_code(ref.property_id)
        if node.scalar is not None:
            return node.scalar
        raise UnsupportedDbAst(
            f"Unrecognised component leaf at node {node.node_id}"
        )

    def _build_cond_expr(self, children: Dict[str, List[OperationNode]]) -> Any:
        condition = self.build(_one(children, "condition"))
        then_expr = self.build(_one(children, "then"))
        else_nodes = children.get("else")
        else_expr = self.build(_one(children, "else")) if else_nodes else None
        return ast_nodes.CondExpr(
            condition=condition, then_expr=then_expr, else_expr=else_expr
        )

    def _build_rename_node(self, node: OperationNode) -> Any:
        shape = self._shapes.get(node.operator_id)
        if shape is None or shape.class_name != "RenameNode":
            raise UnsupportedDbAst("Expected a RenameNode")
        children = _children_by_argument(self._tree, node)
        old = _one(children, "old_name")
        new = _one(children, "new_name")
        return ast_nodes.RenameNode(
            old_name=self._component_text(old),
            new_name=self._component_text(new),
        )

    # ------------------------------------------------------------- #
    # Leaves
    # ------------------------------------------------------------- #

    def _build_leaf(self, node: OperationNode) -> Any:
        refs = self._tree.refs_by_node.get(node.node_id) or []
        if not refs:
            if node.scalar is None:
                raise UnsupportedDbAst(
                    f"Leaf node {node.node_id} has neither a scalar nor "
                    "an OperandReference"
                )
            type_, value = _infer_scalar(node.scalar)
            return ast_nodes.Constant(type_=type_, value=value)

        discriminators = {r.operand_reference for r in refs}

        if discriminators == {"variable"}:
            # A single resolved cell is still a VarID, not a VarRef — the
            # DB distinguishes them by whether a physical location was
            # persisted at all, not by how many OperandReference rows
            # exist (confirmed against real data: a single-cell VarID has
            # exactly one "variable" reference, same as a VarRef).
            has_location = any(
                self._tree.locations_by_ref.get(r.operand_reference_id)
                is not None
                for r in refs
            )
            if has_location:
                return self._build_varid(node, refs)
            if len(refs) == 1:
                code = self._variable_code(refs[0].variable_id)
                if code is None:
                    raise UnsupportedDbAst(
                        f"No VariableVersion.Code for variable "
                        f"{refs[0].variable_id}"
                    )
                return ast_nodes.VarRef(variable=code)
            raise UnsupportedDbAst(
                f"Leaf node {node.node_id}: multiple variable references "
                "without a physical location"
            )

        if discriminators == {"item"}:
            if len(refs) > 1:
                return ast_nodes.Set(
                    children=[self._build_scalar(r) for r in refs]
                )
            return self._build_scalar(refs[0])

        if discriminators == {"property"}:
            return self._build_dimension(refs[0])

        if discriminators == {"PreconditionItem"}:
            ref = refs[0]
            if ref.variable_id is None:
                raise UnsupportedDbAst(
                    f"PreconditionItem node {node.node_id} has no VariableID"
                )
            return ast_nodes.PreconditionItem(
                variable_id=ref.variable_id,
                variable_code=self._variable_code(ref.variable_id),
            )

        raise UnsupportedDbAst(
            f"Leaf node {node.node_id} has an unrecognised OperandReference "
            f"discriminator: {discriminators}"
        )

    def _build_scalar(self, ref: OperandReference) -> Any:
        if ref.item_id is None:
            raise UnsupportedDbAst("Scalar OperandReference has no ItemID")
        return ast_nodes.Scalar(
            item=self._item_category_signature(ref.item_id),
            scalar_type="Item",
        )

    def _build_dimension(self, ref: OperandReference) -> Any:
        if ref.property_id is None:
            raise UnsupportedDbAst(
                "Dimension OperandReference has no PropertyID"
            )
        return ast_nodes.Dimension(
            dimension_code=self._item_category_code(ref.property_id),
            property_id=ref.property_id,
        )

    # ------------------------------------------------------------- #
    # VarID: the one leaf shape with resolved-cell fan-out. Matches
    # mdpm's ``build_node``/``get_varid_common_information`` exactly,
    # not dpmcore's own ``visit_VarID`` (which prunes a coordinate
    # shared by every entry; mdpm never does).
    # ------------------------------------------------------------- #

    def _build_varid(
        self, node: OperationNode, refs: List[OperandReference]
    ) -> Any:
        tables: set[str] = set()
        raw_rows: List[Optional[str]] = []
        raw_columns: List[Optional[str]] = []
        raw_sheets: List[Optional[str]] = []
        entries: List[Dict[str, Any]] = []
        for ref in refs:
            loc = self._tree.locations_by_ref.get(ref.operand_reference_id)
            if loc is None or ref.variable_id is None:
                raise UnsupportedDbAst(
                    f"VarID reference {ref.operand_reference_id} has no "
                    "location or variable"
                )
            if loc.table:
                tables.add(loc.table)
            raw_rows.append(loc.row)
            raw_columns.append(loc.column)
            raw_sheets.append(loc.sheet)

            # mdpm pairs each coordinate with its position field — "row"
            # only appears when "x" does, never independently.
            entry: Dict[str, Any] = {}
            if ref.x is not None:
                entry["x"] = int(ref.x)
                entry["row"] = loc.row
            if ref.y is not None:
                entry["y"] = int(ref.y)
                entry["column"] = loc.column
            if ref.z is not None:
                entry["z"] = int(ref.z)
                entry["sheet"] = loc.sheet
            entry["datapoint"] = int(ref.variable_id)
            entry["operand_reference_id"] = int(ref.operand_reference_id)
            # Not part of mdpm's own dict — a transient field
            # ast_generator.py's shared pipeline needs to build
            # ``variables``, stripped before the final script the same
            # way it strips it for the text-reparse path.
            entry["data_type"] = self._data_type_for_variable(ref.variable_id)
            entries.append(entry)

        if len(tables) > 1:
            raise UnsupportedDbAst(
                f"VarID node {node.node_id} resolves to more than one table"
            )

        entries.sort(
            key=lambda e: (
                e.get("x", 0),
                e.get("y", 0),
                e.get("z", 0),
                e["operand_reference_id"],
            )
        )

        result: Dict[str, Any] = {"class_name": "VarID", "data": entries}
        result["table"] = next(iter(tables), None)

        # An axis is promoted to VarID level only when every resolved
        # reference agrees on a single, non-null value — independent of
        # whether x/y/z happened to be set on that particular reference.
        def _promote(raw_values: List[Optional[str]]) -> Optional[str]:
            if not raw_values or any(v is None for v in raw_values):
                return None
            distinct = set(raw_values)
            return raw_values[0] if len(distinct) == 1 else None

        row_common = _promote(raw_rows)
        if row_common is not None:
            result["row"] = row_common
        column_common = _promote(raw_columns)
        if column_common is not None:
            result["column"] = column_common
        sheet_common = _promote(raw_sheets)
        if sheet_common is not None:
            result["sheet"] = sheet_common

        if node.fallback_value is not None:
            try:
                default = float(node.fallback_value)
                result["default"] = (
                    int(default) if default.is_integer() else default
                )
            except ValueError:
                result["default"] = ""

        result["interval"] = bool(node.use_interval_arithmetics)

        var_id = ast_nodes.VarID(
            table=result.get("table"),
            rows=None,
            cols=None,
            sheets=None,
            interval=result["interval"],
            default=result.get("default"),
        )
        var_id._db_ast_dict = result  # type: ignore[attr-defined]
        return var_id

    # ------------------------------------------------------------- #
    # Small DB lookups (release-scoped, cached per build() call).
    # ------------------------------------------------------------- #

    def _item_category_field(
        self, item_id: int, field_name: str, cache: Dict[int, str]
    ) -> str:
        """``ItemCategory.<field_name>`` for *item_id*, cached in *cache*.

        mdpm's ``build_node`` reads ``Code`` for ``Dimension``/
        ``GroupingClause``/``GetClauseOp``/rename components, but
        ``Signature`` for ``Scalar``/``Set`` — the two aren't always
        equal, so callers pick the field via
        :meth:`_item_category_code`/:meth:`_item_category_signature`.
        """
        cached = cache.get(item_id)
        if cached is not None:
            return cached
        query = self._session.query(ItemCategory).filter(
            ItemCategory.item_id == item_id
        )
        query = filter_by_release(
            query,
            start_col=ItemCategory.start_release_id,
            end_col=ItemCategory.end_release_id,
            release_id=self._release_id,
        )
        row = query.first()
        value = getattr(row, field_name) if row is not None else None
        if not value:
            raise UnsupportedDbAst(
                f"No ItemCategory.{field_name} for item {item_id}"
            )
        cache[item_id] = value
        return value

    def _item_category_signature(self, item_id: int) -> str:
        return self._item_category_field(
            item_id, "signature", self._signature_cache
        )

    def _item_category_code(self, item_id: int) -> str:
        return self._item_category_field(item_id, "code", self._code_cache)

    def _variable_code(self, variable_id: int) -> Optional[str]:
        """``VariableVersion.Code`` for *variable_id*, or ``None`` when
        unresolvable — used for ``PreconditionItem.variable_code``
        (optional in the wire format, so callers may skip it rather than
        fall back to text-reparsing).
        """
        query = self._session.query(VariableVersion.code).filter(
            VariableVersion.variable_id == variable_id
        )
        query = filter_by_release(
            query,
            start_col=VariableVersion.start_release_id,
            end_col=VariableVersion.end_release_id,
            release_id=self._release_id,
        )
        row = query.first()
        return row[0] if row is not None else None

    def _data_type_for_variable(self, variable_id: int) -> str:
        cached = self._data_type_cache.get(variable_id)
        if cached is not None:
            return cached
        query = (
            self._session.query(DataType.code)
            .join(Property, Property.data_type_id == DataType.data_type_id)
            .join(
                VariableVersion,
                VariableVersion.property_id == Property.property_id,
            )
            .filter(VariableVersion.variable_id == variable_id)
        )
        query = filter_by_release(
            query,
            start_col=VariableVersion.start_release_id,
            end_col=VariableVersion.end_release_id,
            release_id=self._release_id,
        )
        row = query.first()
        if row is None or not row[0]:
            raise UnsupportedDbAst(
                f"No DataType resolvable for variable {variable_id}"
            )
        self._data_type_cache[variable_id] = row[0]
        return row[0]


def build_ast_dict_from_db(
    session: Session, operation_vid: int, release_id: int
) -> Tuple[Dict[str, Any], int]:
    """Rebuild ``(ast_dict, root_operator_id)`` for *operation_vid* from
    the DB, instead of re-parsing its expression text.

    Raises :class:`UnsupportedDbAst` when the tree contains anything this
    module does not (yet) faithfully reconstruct — callers must catch
    this and fall back to parsing ``OperationVersion.expression`` instead.
    """
    tree = _load_tree(session, operation_vid)
    root = _root(tree)
    if root.operator_id is None:
        raise UnsupportedDbAst(f"Root node {root.node_id} has no OperatorID")
    builder = _Builder(session, tree, release_id)
    built = builder.build(root)
    ast_dict = _DbAstToJSONVisitor().visit(built)
    return ast_dict, root.operator_id
