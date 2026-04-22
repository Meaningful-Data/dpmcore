from dpmcore.dpm_xl.ast.nodes import Start, VarID, WithExpression
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.model_queries import (
    ViewModulesQuery,
)
from dpmcore.dpm_xl.utils.operands_mapping import LabelHandler
from dpmcore.dpm_xl.utils.tokens import (
    CROSS_MODULE,
    INTRA_MODULE,
    REPEATED_INTRA_MODULE,
)


class ModuleAnalyzer(ASTTemplate):
    def __init__(self, session):

        super(ASTTemplate).__init__()
        self.modules = []
        self.session = session
        self.mode = None
        self.module_info = {}
        LabelHandler().reset_instance()

    def new_label(self):
        return LabelHandler().labels.__next__()

    def extract_modules(self, tables):
        return ViewModulesQuery.get_modules(self.session, tables)

    def module_analysis(self):
        unique_modules = []

        for operand_info in self.module_info.values():
            if operand_info == "Module not found":
                print(f"Module not found: {self.module_info}")
                return
            unique_modules += operand_info
        unique_modules = list(set(unique_modules))
        if len(unique_modules) == 1:
            self.mode = INTRA_MODULE
            self.modules = unique_modules
        self.find_common_modules(unique_modules)

    def visit_Start(self, node: Start):
        self.visit(node.children[0])
        if not isinstance(node.children[0], WithExpression):
            self.module_analysis()
        return self.mode, self.modules

    def visit_WithExpression(self, node: WithExpression):
        if node.partial_selection.table is not None:
            modules = self.extract_modules([node.partial_selection.table])
            self.modules = modules
            if len(modules) > 1:
                self.mode = REPEATED_INTRA_MODULE
            elif len(modules) == 1:
                self.mode = INTRA_MODULE
            return
        self.visit(node.expression)
        self.module_analysis()

    def visit_VarID(self, node: VarID):
        modules = self.extract_modules([node.table])
        if len(modules) > 0:
            self.module_info[self.new_label()] = modules
        else:
            self.module_info[self.new_label()] = "Module not found"

    def find_common_modules(self, unique_modules):
        common_modules = []
        for operand_info in self.module_info.values():
            if len(common_modules) == 0:
                common_modules = operand_info
                continue
            common_modules = list(set(common_modules) & set(operand_info))
        if len(common_modules) == 0:
            if len(unique_modules) > 1:
                self.mode = CROSS_MODULE
                self.modules = unique_modules
            return
        elif len(common_modules) == 1:
            self.mode = INTRA_MODULE
        else:
            self.mode = CROSS_MODULE
        self.modules = common_modules
