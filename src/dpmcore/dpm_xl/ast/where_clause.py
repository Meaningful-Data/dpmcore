from dpmcore.dpm_xl.ast.nodes import Dimension
from dpmcore.dpm_xl.ast.template import ASTTemplate


class WhereClauseChecker(ASTTemplate):
    def __init__(self):
        super().__init__()
        self.key_components = []

    def visit_Dimension(self, node: Dimension):
        self.key_components.append(node.dimension_code)
