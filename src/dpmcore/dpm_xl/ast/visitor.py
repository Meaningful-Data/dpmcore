from __future__ import annotations

from typing import Any


class NodeVisitor:
    """Foundation of the Visit pattern. Gets the AST Object class name and checks if a method
    named visit_ + class name is present. If not, raises a NotImplementedError.
    """

    def visit(self, node: Any) -> Any:
        method_name = "visit_" + type(node).__name__
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: Any) -> Any:
        raise NotImplementedError(
            "No visit_{} method".format(type(node).__name__)
        )
