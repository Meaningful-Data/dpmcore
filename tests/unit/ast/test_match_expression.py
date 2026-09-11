"""Serialization tests for the ``match`` string operator.

The engine consumes ``match`` as a plain ``BinOp`` with ``op == "match"``
(operand on the left, pattern on the right). It must NOT be emitted as a
dedicated ``MatchCharactersOp`` node -- that class name is not part of the
engine's accepted AST vocabulary and fails schema validation.
"""

from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor, serialize_ast
from dpmcore.services.syntax import SyntaxService

MATCH_EXPR = 'match({tC_27.00, c021}, "[A-Z0-9]{18}[0-9]{2}")'


def test_match_serializes_as_binop():
    ast = SyntaxService().parse(MATCH_EXPR)
    node = ASTToJSONVisitor().visit(ast)["children"][0]

    assert node["class_name"] == "BinOp"
    assert node["op"] == "match"
    # Operand on the left, regex pattern on the right.
    assert node["left"]["class_name"] == "VarID"
    assert node["right"]["class_name"] == "Constant"
    assert node["right"]["value"] == "[A-Z0-9]{18}[0-9]{2}"


def test_match_does_not_emit_match_characters_op():
    """Guard against re-introducing the rejected ``MatchCharactersOp`` name."""
    payload = serialize_ast(SyntaxService().parse(MATCH_EXPR))

    def class_names(node):
        if isinstance(node, dict):
            cn = node.get("class_name")
            if isinstance(cn, str):
                yield cn
            for value in node.values():
                yield from class_names(value)
        elif isinstance(node, list):
            for item in node:
                yield from class_names(item)

    assert "MatchCharactersOp" not in set(class_names(payload))
