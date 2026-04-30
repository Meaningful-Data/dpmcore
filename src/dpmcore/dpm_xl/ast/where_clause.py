from __future__ import annotations

from dpmcore.dpm_xl.ast.nodes import Dimension
from dpmcore.dpm_xl.ast.template import ASTTemplate


class WhereClauseChecker(ASTTemplate):
    def __init__(self) -> None:
        super().__init__()
        self.key_components: list[str] = []

    def visit_Dimension(self, node: Dimension) -> None:
        self.key_components.append(node.dimension_code)
