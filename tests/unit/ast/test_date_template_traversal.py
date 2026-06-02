"""ASTTemplate traversal coverage for the date operator nodes.

The base ``ASTTemplate`` visitors for ``DateExtractionOp`` /
``DateConstructorOp`` simply recurse into their operands. The semantic
analyzer and ML generator override them, so these base methods are
exercised here directly via a minimal recording subclass.
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
