"""Shared helpers for the wire-shape tests in this package.

``ASTToJSONVisitor`` is what script generation emits, so several modules
here assert on the serialized payload rather than on the AST objects.
The two helpers they need -- parse-and-serialize, and collect every
``class_name`` in a payload -- live here so a change to the visitor's
entry shape is chased in one place.
"""

import pytest

from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor
from dpmcore.services.syntax import SyntaxService


@pytest.fixture
def serialize_expr():
    """Return the serialized payload of the first expression in a script."""

    def _serialize_expr(expression: str) -> dict:
        result = ASTToJSONVisitor().visit(SyntaxService().parse(expression))
        assert isinstance(result, dict)
        return result["children"][0]

    return _serialize_expr


@pytest.fixture
def class_names():
    """Return every ``class_name`` in a serialized payload, at any depth."""

    def _class_names(node) -> set:
        if isinstance(node, dict):
            names = {node["class_name"]} if "class_name" in node else set()
            for value in node.values():
                names |= _class_names(value)
            return names
        if isinstance(node, list):
            names = set()
            for item in node:
                names |= _class_names(item)
            return names
        return set()

    return _class_names
