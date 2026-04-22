from abc import ABC

from dpmcore import errors
from dpmcore.dpm_xl.ast.nodes import *
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.ast.where_clause import WhereClauseChecker
from dpmcore.dpm_xl.model_queries import (
    ItemCategoryQuery,
    TableVersionQuery,
    VariableVersionQuery,
    ViewDatapointsQuery,
    ViewModulesQuery,
)

operand_elements = ["table", "rows", "cols", "sheets", "default", "interval"]


def filter_datapoints_df(df, table, table_info: dict, release_id: int = None):
    """ """
    mapping_dictionary = {
        "rows": "row_code",
        "cols": "column_code",
        "sheets": "sheet_code",
    }
    df = df[df["table_code"] == table]
    for k, v in table_info.items():
        if v is not None:
            if "-" in v[0]:
                low_limit, high_limit = v[0].split("-")
                df = df[
                    (df[mapping_dictionary[k]].between(low_limit, high_limit))
                ]
            elif v[0] == "*":
                continue
            else:
                df = df[(df[mapping_dictionary[k]].isin(v))]

    if release_id:
        df = df[df["release_id"] == release_id]
    return df


def filter_module_by_table_df(df, table):
    """Returns a list of modules that contain the table."""
    module_list = df[df["table_code"] == table]["module_code"].tolist()
    return module_list


class ModuleDependencies(ASTTemplate, ABC):
    def __init__(
        self, session, ast, release_id, date, module_ref, is_scripting=False
    ):
        self.release_id = release_id
        self.AST = ast
        self.tables = {}
        self.operands = {}
        self.full_operands = {}
        self.module_ref = module_ref
        # self.key_components = {}
        self.partial_selection = None
        self.data = None
        self.items = []
        self.preconditions = False
        self.dimension_codes = []
        # self.open_keys = None

        self.operations = []
        self.operations_data = None
        self.is_scripting = is_scripting

        self.session = session
        self.time_period = "t"  # TODO
        self.date = date
        self.modules = {}
        self.from_time_shift = False

        super().__init__()
        self.visit(self.AST)

    # Start of visiting nodes
    def visit_WithExpression(self, node: WithExpression):
        if node.partial_selection.is_table_group:
            raise errors.SemanticError(
                "1-10", table=node.partial_selection.table
            )
        self.partial_selection: VarID = node.partial_selection
        self.visit(node.expression)

    def visit_VarID(self, node: VarID):

        if node.is_table_group:
            raise errors.SemanticError("1-10", table=node.table)

        if self.partial_selection:
            for attribute in operand_elements:
                if (
                    getattr(node, attribute, None) is None
                    and getattr(self.partial_selection, attribute, None)
                    is not None
                ):
                    setattr(
                        node,
                        attribute,
                        getattr(self.partial_selection, attribute),
                    )

        if not node.table:
            raise errors.SemanticError("1-4", table=node.table)

        table_info = {
            "rows": node.rows,
            "cols": node.cols,
            "sheets": node.sheets,
        }

        if node.table not in self.tables:
            self.tables[node.table] = table_info
            self.operands[node.table] = [self.time_period]
            # self.operands[node.table] = [node]
        else:
            if self.time_period not in self.operands[node.table]:
                self.operands[node.table].append(self.time_period)
                # self.operands[node.table].append(node)

        # Variables full
        variables_full = ViewDatapointsQuery.get_filtered_datapoints(
            self.session, node.table, table_info, release_id=self.release_id
        )
        # variables_full = ViewDatapoints.get_table_data(self.session, node.table, table_info['rows'], table_info['cols'], table_info['sheets'],
        #                                              self.release_id)

        if variables_full.empty:
            raise errors.SemanticError("1-5", open_keys=table_info)

        final_list = variables_full["variable_id"].to_list()
        # Here change table for module or modules
        modules = ViewModulesQuery.get_all_modules(self.session)  # TODO
        modules = filter_module_by_table_df(modules, node.table)
        # modules = ViewModules().get_modules(self.session, [node.table], None)
        if self.module_ref:
            if self.module_ref in modules:
                full_name = f"{self.module_ref}:{self.time_period}"
                if full_name not in self.full_operands:
                    self.full_operands[full_name] = final_list
                else:
                    for elto in final_list:
                        if elto not in self.full_operands[full_name]:
                            self.full_operands[full_name].append(elto)
            else:
                for module in modules:
                    full_name = f"{module}:{self.time_period}"
                    if full_name not in self.full_operands:
                        self.full_operands[full_name] = final_list
                    else:
                        for elto in final_list:
                            if elto not in self.full_operands[full_name]:
                                self.full_operands[full_name].append(elto)
        else:
            full_name = f"{node.table}:{self.time_period}"
            self.full_operands[full_name] = final_list

    def visit_Dimension(self, node: Dimension):
        if node.dimension_code not in self.dimension_codes:
            self.dimension_codes.append(node.dimension_code)
            if not ItemCategoryQuery.get_property_from_code(
                node.dimension_code, self.session
            ):
                raise errors.SemanticError(
                    "1-5", open_keys=node.dimension_code
                )

    def visit_VarRef(self, node: VarRef):
        if not VariableVersionQuery.check_variable_exists(
            self.session, node.variable, self.release_id
        ):
            raise errors.SemanticError("1-3", variable=node.variable)

    def visit_PreconditionItem(self, node: PreconditionItem):

        if self.is_scripting:
            raise errors.SemanticError("6-3", precondition=node.variable_id)

        if not TableVersionQuery.check_table_exists(
            self.session, node.variable_id, self.release_id
        ):
            raise errors.SemanticError("1-3", variable=node.variable_id)

        self.preconditions = True

    def visit_Scalar(self, node: Scalar):
        if node.item and node.scalar_type == "Item":
            if node.item not in self.items:
                self.items.append(node.item)
                if not ItemCategoryQuery.get_item_category_id_from_signature(
                    node.item, self.session
                ):
                    raise errors.SemanticError("1-1", items=node.item)

    def visit_WhereClauseOp(self, node: WhereClauseOp):
        self.visit(node.operand)
        checker = WhereClauseChecker()
        checker.visit(node.condition)
        node.key_components = checker.key_components
        self.visit(node.condition)

    def visit_TimeShiftOp(self, node: TimeShiftOp):
        self.from_time_shift = True
        period_indicator = node.period_indicator
        shift_number = node.shift_number
        # compute new time period
        if period_indicator not in ("A", "Q", "M", "W", "D"):
            raise ValueError("Period indicator is not valid")
        if "-" in shift_number:
            new_time_period = f"t+{period_indicator}{shift_number}"
        else:
            new_time_period = f"t-{period_indicator}{shift_number}"

        self.time_period = new_time_period
        self.visit(node.operand)
        self.from_time_shift = False

    def visit_OperationRef(self, node: OperationRef):
        if not self.is_scripting:
            raise errors.SemanticError(
                "6-2", operation_code=node.operation_code
            )

    def visit_PersistentAssignment(self, node: PersistentAssignment):
        # TODO: visit node.left when there are calculations variables in database
        self.visit(node.right)

    def visit_TemporaryAssignment(self, node: TemporaryAssignment):
        temporary_identifier = node.left
        self.operations.append(temporary_identifier.value)
        self.visit(node.right)
