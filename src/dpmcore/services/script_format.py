"""Pieces of the Script Format 2.0 document shared by its producers.

The format version, how the file is named and the shape of the AST.
"""

from __future__ import annotations

from typing import Any

NODE_CLASSES = [
    "FactVarID",
    "Constant",
    "Scalar",
    "Set",
    "Dimension",
    "ParameterRef",
    "FilingIndicatorVarID",
    "ParExpr",
    "UnaryOp",
    "BinOp",
    "ComplexNumericOp",
    "SetOp",
    "SubstrOp",
    "DateConstructorOp",
    "AnnualiseOp",
    "AggregationOp",
    "GroupingClause",
    "AnalyticClause",
    "WhereClauseOp",
    "SubClauseOp",
    "GetClauseOp",
    "RenameClauseOp",
    "FilterOp",
    "CondExpr",
    "TimeShiftOp",
]
"""The twenty-five node classes of Script Format 2.0."""

CELL_POSITION = ("row", "column", "sheet")
DATE_PARTS = ("year", "month", "day")

FORMAT_VERSION = "2.0"
"""Script Format version of the documents dpmcore produces."""


def script_file_name(owner: str, module_code: str, module_version: str) -> str:
    """Return ``<owner>-<module_code>-<module_version>.json``.

    Raises:
        ValueError: If a part is blank: the file name would not
            identify the document.
    """
    if not (owner and module_code and module_version):
        raise ValueError(
            "A script file name needs an owner, a module code and a "
            f"module version; got {owner!r}, {module_code!r}, "
            f"{module_version!r}."
        )
    return f"{owner}-{module_code}-{module_version}.json"


class UnsupportedNode(ValueError):
    """An AST that Script Format 2.0 cannot express."""


def script_ast(node: Any) -> Any:
    """Turn a serialized AST into the one a Script Format 2.0 document holds.

    The serialized AST names the parser's nodes, and some of their
    classes and members are not those of the format. This walks the
    whole tree, lists included, and translates every node with
    :func:`script_node`, from the leaves up, into a new tree.

    Args:
        node: The serialized AST of an operation, as parsed from its
            expression or read from the database.

    Returns:
        A new tree in the format's shape; *node* is not modified.

    Raises:
        UnsupportedNode: If a node is of a class outside the format,
            or a filing indicator has no code.
    """
    if isinstance(node, list):
        return [script_ast(item) for item in node]
    if not isinstance(node, dict):
        return node
    return script_node({key: script_ast(value) for key, value in node.items()})


def script_node(node: dict[str, Any]) -> dict[str, Any]:
    """Translate one node into its Script Format 2.0 shape.

    Its children must already be translated, which is why
    :func:`script_ast` calls it from the leaves up. Only these classes
    change:

    - ``VarID`` becomes ``FactVarID`` and drops ``row``, ``column`` and
      ``sheet``, on the node and on each ``data`` entry: the document
      gives the cells of each Variable once, not on every reference.
    - ``PreconditionItem`` becomes ``FilingIndicatorVarID``, with just
      ``code`` and ``variable_id``.
    - ``DateConstructorOp`` renames ``year``, ``month`` and ``day`` to
      ``year_node``, ``month_node`` and ``day_node``.
    - ``Scalar`` drops ``member``.
    - ``AnalyticClause`` renames the ``period`` of its window bounds to
      ``period_indicator``.

    Every other class of the format is returned as it is. *node* may
    be modified in place.

    Raises:
        UnsupportedNode: If *node* is of a class outside the format, or
            a ``PreconditionItem`` has no ``variable_code``.
    """
    class_name = node.get("class_name")
    if class_name == "VarID":
        node = {k: v for k, v in node.items() if k not in CELL_POSITION}
        node["class_name"] = "FactVarID"
        node["data"] = [
            {k: v for k, v in entry.items() if k not in CELL_POSITION}
            for entry in node.get("data") or []
        ]
    elif class_name == "PreconditionItem":
        if not node.get("variable_code"):
            raise UnsupportedNode(
                f"The filing indicator {node.get('variable_id')} has no code."
            )
        node = {
            "class_name": "FilingIndicatorVarID",
            "code": node["variable_code"],
            "variable_id": node.get("variable_id"),
        }
    elif class_name == "DateConstructorOp":
        node = {
            f"{k}_node" if k in DATE_PARTS else k: v for k, v in node.items()
        }
    elif class_name == "Scalar":
        node.pop("member", None)
    elif class_name == "AnalyticClause" and node.get("window"):
        window = node["window"]
        for side in ("start", "end"):
            window[side] = {
                "period_indicator" if k == "period" else k: v
                for k, v in window[side].items()
            }
    elif class_name is not None and class_name not in NODE_CLASSES:
        raise UnsupportedNode(
            f"{class_name} is not a node of Script Format 2.0."
        )
    return node
