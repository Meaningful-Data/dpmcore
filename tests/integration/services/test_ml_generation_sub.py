"""DPM-ML generation of ``sub`` against the fixture database"""

from dpmcore.dpm_xl.ast.ml_generation import MLGeneration
from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.orm.operations import OperandReference, OperationNode
from dpmcore.services.syntax import SyntaxService


def test_sub_stores_the_component_and_links_every_node_to_an_argument(
    fixture_session,
):
    expression = "{tF_01.01, r0010, c0010}[sub LCF = [eba_GA:qx2008]]"
    ast = SyntaxService().parse(expression)
    data = OperandsChecking(
        fixture_session, expression, ast, release_id=None
    ).data

    with fixture_session.no_autoflush:
        # The statement, not Start, so no scopes are computed.
        MLGeneration(fixture_session, data=data, op_version_id=1).visit(
            ast.children[0]
        )
        new = list(fixture_session.new)
    fixture_session.rollback()

    nodes = [n for n in new if isinstance(n, OperationNode)]
    refs = [r for r in new if isinstance(r, OperandReference)]
    assert all(n.argument_id is not None for n in nodes if n.parent)
    assert any(r.property_id is not None for r in refs)
