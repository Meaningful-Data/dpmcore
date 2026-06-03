"""ASTTemplate traversal coverage for the date operator nodes.

Date extraction operators (year, semester, quarter, month, week, day) are
represented as ``UnaryOp`` nodes and traversed via ``visit_UnaryOp``,
while ``DateConstructorOp`` has its own visitor. Both simply recurse into
their operands in the base template, with overrides handling semantic
analysis and ML generation.
"""

from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.services.syntax import SyntaxService


class _ConstantRecorder(ASTTemplate):
    """Records every Constant leaf the traversal reaches."""

    def __init__(self) -> None:
        super().__init__()
        self.constants: list = []

    def visit_Constant(self, node) -> None:  # noqa: ANN001
        self.constants.append(node)


def test_template_visits_date_extraction_operand():
    ast = SyntaxService().parse("year(#2022-03-15#)")
    recorder = _ConstantRecorder()
    recorder.visit(ast)
    assert len(recorder.constants) == 1


def test_template_visits_date_constructor_children():
    ast = SyntaxService().parse("date(2025, 12, 31)")
    recorder = _ConstantRecorder()
    recorder.visit(ast)
    assert len(recorder.constants) == 3
