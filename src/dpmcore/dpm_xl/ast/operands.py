from __future__ import annotations

import warnings
from abc import ABC
from typing import Any, Dict, Hashable, Tuple

import pandas as pd
from sqlalchemy.orm import Session

# Suppress pandas UserWarning about SQLAlchemy connection types
warnings.filterwarnings(
    "ignore", message=".*pandas only supports SQLAlchemy.*"
)

from dpmcore import errors
from dpmcore.dpm_xl.ast.nodes import (
    AST,
    Dimension,
    GetOp,
    OperationRef,
    PersistentAssignment,
    PreconditionItem,
    Scalar,
    TemporaryAssignment,
    VarID,
    VarRef,
    WhereClauseOp,
    WithExpression,
)
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.ast.where_clause import WhereClauseChecker
from dpmcore.dpm_xl.model_queries import (
    ItemCategoryQuery,
    OperationQuery,
    VariableVersionQuery,
    ViewDatapointsQuery,
    ViewKeyComponentsQuery,
    ViewOpenKeysQuery,
)
from dpmcore.dpm_xl.types.scalar import Integer, Mixed, Number, ScalarFactory
from dpmcore.dpm_xl.utils.data_handlers import filter_all_data
from dpmcore.dpm_xl.utils.filters import filter_by_release
from dpmcore.dpm_xl.utils.operands_mapping import (
    generate_new_label,
    set_operand_label,
)
from dpmcore.errors import SemanticError
from dpmcore.orm.rendering import (
    Header,
    Table,
    TableVersion,
    TableVersionHeader,
)

operand_elements = ["table", "rows", "cols", "sheets", "default", "interval"]

# Implicit open keys that are always available without being declared in the database
# These are special dimensions that arise from the reporting context itself
# - refPeriod: The reference period of the report (date type "d")
# - entityID: The identifier of the reporting entity (string type "s")
IMPLICIT_OPEN_KEYS = {
    "refPeriod": "d",  # date type
    "entityID": "s",  # string type
}


_HEADERS_CACHE: Dict[
    Tuple[Hashable, int | None, Tuple[str, ...]], pd.DataFrame
] = {}


def _create_operand_label(node: VarID | PreconditionItem) -> None:
    label = generate_new_label()
    node.label = label


def _modify_element_info(
    new_data: list[str] | None,
    element: str,
    table_info: dict[str, list[str] | None],
) -> None:
    if (
        new_data is None
        and table_info[element] is None
        or table_info[element] == ["*"]
    ):
        pass
    elif new_data is not None and table_info[element] is None:
        table_info[element] = new_data

    elif new_data == ["*"]:
        # We have already all data available
        table_info[element] = new_data

    else:
        # We get only the elements that are not already in the info and sort them
        existing = table_info[element] or []
        new_list = [x for x in (new_data or []) if x not in existing]
        new_list += existing
        new_list = sorted(new_list)
        table_info[element] = new_list


def _modify_table(
    node: VarID, table_info: dict[str, list[str] | None]
) -> None:
    for element in table_info:
        _modify_element_info(getattr(node, element), element, table_info)


def format_missing_data(node: VarID) -> None:
    rows = ", ".join([f"r{x}" for x in node.rows]) if node.rows else None
    cols = ", ".join([f"c{x}" for x in node.cols]) if node.cols else None
    sheets = ", ".join([f"s{x}" for x in node.sheets]) if node.sheets else None
    op_pos = [node.table, rows, cols, sheets]
    cell_exp = ", ".join(x for x in op_pos if x is not None)
    raise errors.SemanticError("1-2", cell_expression=cell_exp)


def _has_range_syntax(values: Any) -> bool:
    """Check if a list of values contains range syntax (e.g., '0010-0080')."""
    if not values or not isinstance(values, list):
        return False
    return any("-" in str(v) for v in values if v and v != "*")


def _expand_ranges_from_data(node: VarID, node_data: pd.DataFrame) -> None:
    """Expand range-type values in VarID node's rows/cols/sheets to actual codes from the database.

    When a VarID has range syntax like ['0010-0080'], this function replaces it with
    the actual codes found in node_data (e.g., ['0010', '0020', '0030', ...]).

    This ensures adam-engine receives scalar values in the JSON output instead of
    list-type ranges which it cannot parse.

    Args:
        node: VarID AST node with rows, cols, sheets attributes
        node_data: DataFrame containing the actual cell data with row_code, column_code, sheet_code
    """
    if node_data.empty:
        return

    # Expand rows if they contain range syntax
    if _has_range_syntax(node.rows):
        actual_rows = list(node_data["row_code"].dropna().unique().tolist())
        if actual_rows:
            # Sort to maintain consistent ordering
            node.rows = sorted(actual_rows)

    # Expand cols if they contain range syntax
    if _has_range_syntax(node.cols):
        actual_cols = list(
            node_data["column_code"].dropna().unique().tolist()
        )
        if actual_cols:
            node.cols = sorted(actual_cols)

    # Expand sheets if they contain range syntax
    if _has_range_syntax(node.sheets):
        actual_sheets = list(
            node_data["sheet_code"].dropna().unique().tolist()
        )
        if actual_sheets:
            node.sheets = sorted(actual_sheets)


class OperandsChecking(ASTTemplate, ABC):
    def __init__(
        self,
        session: Session,
        expression: str,
        ast: AST,
        release_id: int | None,
        is_scripting: bool = False,
    ) -> None:
        self.expression = expression
        self.release_id = release_id
        self.AST = ast
        self.tables: dict[str, dict[str, list[str] | None]] = {}
        self.operands: dict[str, list[VarID]] = {}
        self.key_components: dict[str, pd.DataFrame] = {}
        self.partial_selection: VarID | None = None
        self.data: pd.DataFrame | None = None
        self.items: list[str] = []
        self.preconditions = False
        self.dimension_codes: list[str] = []
        # Store references to Dimension nodes for property_id enrichment
        self.dimension_nodes: list[Dimension] = []
        self.open_keys: pd.DataFrame | None = None
        # Store GetOp component codes for property_id lookup
        self.getop_components: list[str] = []
        # Store references to GetOp nodes for property_id enrichment
        self.getop_nodes: list[GetOp] = []

        self.operations: list[str] = []
        self.operations_data: pd.DataFrame | None = None
        self.is_scripting = is_scripting

        self.session = session

        super().__init__()
        self.visit(self.AST)
        self.check_headers()
        self.check_items()
        self.check_tables()
        self.check_dimensions()
        self.check_getop_components()

        self.check_operations()

    def _check_header_present(self, table: str, header: str) -> None:
        if (
            self.partial_selection is not None
            and self.partial_selection.table == table
            and getattr(self.partial_selection, header) is not None
        ):
            return
        for node in self.operands[table]:
            if getattr(node, header) is None:
                if header == "cols":
                    header = "columns"
                raise errors.SemanticError("1-20", header=header, table=table)

    def check_headers(self) -> None:
        table_codes = list(self.tables.keys())
        if len(table_codes) == 0:
            return

        engine = self.session.get_bind()
        engine_key: Hashable = getattr(engine, "url", repr(engine))
        cache_key = (engine_key, self.release_id, tuple(sorted(table_codes)))

        df_headers = _HEADERS_CACHE.get(cache_key)
        if df_headers is None:
            query = (
                self.session.query(
                    TableVersion.code.label("Code"),
                    TableVersion.start_release_id.label("StartReleaseID"),
                    TableVersion.end_release_id.label("EndReleaseID"),
                    Header.direction.label("Direction"),
                    Table.has_open_rows.label("HasOpenRows"),
                    Table.has_open_columns.label("HasOpenColumns"),
                    Table.has_open_sheets.label("HasOpenSheets"),
                )
                .join(Table, Table.table_id == TableVersion.table_id)
                .join(
                    TableVersionHeader,
                    TableVersion.table_vid == TableVersionHeader.table_vid,
                )
                .join(Header, Header.header_id == TableVersionHeader.header_id)
                .filter(TableVersion.code.in_(table_codes))
                .distinct()
            )

            query = filter_by_release(
                query,
                start_col=TableVersion.start_release_id,
                end_col=TableVersion.end_release_id,
                release_id=self.release_id,
            )

            from dpmcore.dpm_xl.model_queries import (
                compile_query_for_pandas,
                read_sql_with_connection,
            )

            compiled_query = compile_query_for_pandas(
                query.statement, self.session
            )
            df_headers = read_sql_with_connection(compiled_query, self.session)
            _HEADERS_CACHE[cache_key] = df_headers

        for table in table_codes:
            table_headers = df_headers[df_headers["Code"] == table]
            if table_headers.empty:
                continue
            open_rows = table_headers["HasOpenRows"].values[0]
            open_cols = table_headers["HasOpenColumns"].values[0]
            open_sheets = table_headers["HasOpenSheets"].values[0]
            if "Y" in table_headers["Direction"].values and not open_rows:
                self._check_header_present(table, "rows")
            if "X" in table_headers["Direction"].values and not open_cols:
                self._check_header_present(table, "cols")
            if "Z" in table_headers["Direction"].values and not open_sheets:
                self._check_header_present(table, "sheets")

    def check_items(self) -> None:
        if len(self.items) == 0:
            return
        df_items = ItemCategoryQuery.get_items(
            self.session, self.items, self.release_id
        )
        if len(df_items.iloc[:, 0].values) < len(set(self.items)):
            not_found_items = list(
                set(self.items).difference(set(df_items["Signature"]))
            )
            raise errors.SemanticError("1-1", items=not_found_items)

    def check_dimensions(self) -> None:
        if len(self.dimension_codes) == 0:
            return

        # Separate implicit keys from database-backed keys
        implicit_codes = [
            code for code in self.dimension_codes if code in IMPLICIT_OPEN_KEYS
        ]
        database_codes = [
            code
            for code in self.dimension_codes
            if code not in IMPLICIT_OPEN_KEYS
        ]

        # Query database only for non-implicit keys
        if database_codes:
            open_keys_df = ViewOpenKeysQuery.get_keys(
                self.session, database_codes, self.release_id
            )
            self.open_keys = open_keys_df
            if len(open_keys_df) < len(database_codes):
                not_found_dimensions = list(
                    set(database_codes).difference(
                        open_keys_df["property_code"]
                    )
                )
                raise errors.SemanticError(
                    "1-5", open_keys=not_found_dimensions
                )
        else:
            self.open_keys = pd.DataFrame(
                columns=["property_id", "property_code", "data_type"]
            )

        # Add implicit open keys to the open_keys DataFrame
        # Use property_id=-1 as a sentinel for implicit keys
        if implicit_codes:
            implicit_rows = [
                {
                    "property_id": -1,
                    "property_code": code,
                    "data_type": IMPLICIT_OPEN_KEYS[code],
                }
                for code in implicit_codes
            ]
            implicit_df = pd.DataFrame(implicit_rows)
            self.open_keys = pd.concat(
                [self.open_keys, implicit_df], ignore_index=True
            )

        # Enrich Dimension nodes with property_id from open_keys
        # This is required by adam-engine for WHERE clause resolution
        # (both branches above leave ``self.open_keys`` as a DataFrame,
        # hence no ``is not None`` guard is required here).
        if not self.open_keys.empty:
            # Create a mapping from dimension_code to property_id
            property_id_map = dict(
                zip(
                    self.open_keys["property_code"],
                    self.open_keys["property_id"],
                    strict=False,
                )
            )
            for node in self.dimension_nodes:
                if node.dimension_code in property_id_map:
                    node.property_id = int(
                        property_id_map[node.dimension_code]
                    )

    def check_getop_components(self) -> None:
        """Check and enrich GetOp nodes with property_id for their component codes.

        GetOp components (like qEGS, qLGS, refPeriod, entityID) are property codes
        that need to be resolved to property_id for adam-engine to process them
        correctly. refPeriod and entityID are implicit open keys that don't need
        to be declared in the database.
        """
        if len(self.getop_components) == 0:
            return

        # Separate implicit keys from database-backed keys
        implicit_codes = [
            code
            for code in self.getop_components
            if code in IMPLICIT_OPEN_KEYS
        ]
        database_codes = [
            code
            for code in self.getop_components
            if code not in IMPLICIT_OPEN_KEYS
        ]

        # Query property_ids for GetOp components (same query as dimensions)
        if database_codes:
            getop_keys = ViewOpenKeysQuery.get_keys(
                self.session, database_codes, self.release_id
            )

            if len(getop_keys) < len(database_codes):
                not_found_components = list(
                    set(database_codes).difference(getop_keys["property_code"])
                )
                raise errors.SemanticError(
                    "1-5", open_keys=not_found_components
                )
        else:
            getop_keys = pd.DataFrame(
                columns=["property_id", "property_code", "data_type"]
            )

        # Add implicit open keys to the getop_keys DataFrame
        # Use property_id=-1 as a sentinel for implicit keys
        if implicit_codes:
            implicit_rows = [
                {
                    "property_id": -1,
                    "property_code": code,
                    "data_type": IMPLICIT_OPEN_KEYS[code],
                }
                for code in implicit_codes
            ]
            implicit_df = pd.DataFrame(implicit_rows)
            getop_keys = pd.concat(
                [getop_keys, implicit_df], ignore_index=True
            )

        # Enrich GetOp nodes with property_id
        # This is required by adam-engine for [get ...] operations
        if not getop_keys.empty:
            # Create a mapping from component code to property_id
            property_id_map = dict(
                zip(
                    getop_keys["property_code"],
                    getop_keys["property_id"],
                    strict=False,
                )
            )
            for node in self.getop_nodes:
                if node.component in property_id_map:
                    node.property_id = int(property_id_map[node.component])

    def check_tables(self) -> None:
        for table, value in self.tables.items():
            # Extract all data and filter to get only necessary data
            table_info = value
            df_table = ViewDatapointsQuery.get_table_data(
                self.session,
                table,
                table_info["rows"],
                table_info["cols"],
                table_info["sheets"],
                self.release_id,
            )
            # Insert data type on each node by selecting only data required by node
            for node in self.operands[table]:
                node_data = filter_all_data(
                    df_table,
                    table,
                    node.rows or [],
                    node.cols or [],
                    node.sheets or [],
                )
                # Checking grey cells (no variable ID in data for that cell)
                grey_cells_data = node_data[node_data["variable_id"].isnull()]
                if not grey_cells_data.empty:
                    if len(grey_cells_data) > 10:
                        list_cells = grey_cells_data["cell_code"].values[:10]
                    else:
                        list_cells = grey_cells_data["cell_code"].values
                    cell_expression = ", ".join(list_cells)
                    raise errors.SemanticError(
                        "1-17", cell_expression=cell_expression
                    )
                if node_data.empty:
                    format_missing_data(node)
                extract_data_types(node, node_data["data_type"])

                # Check for invalid sheet wildcards
                if (
                    df_table["sheet_code"].isnull().all()
                    and node.sheets is not None
                    and "*" in node.sheets
                ):
                    # Check if s* is required to avoid duplicate (row, column) combinations
                    # Group by (row_code, column_code) and check for duplicates
                    # IMPORTANT: Include NA/NULL values in grouping (dropna=False)
                    df_without_sheets = df_table.groupby(
                        ["row_code", "column_code"], dropna=False
                    ).size()
                    has_duplicates = (df_without_sheets > 1).any()

                    if not has_duplicates:
                        # Only raise error if sheets are truly not needed (no duplicates without them)
                        raise SemanticError("1-18")
                    # else: s* is required even though sheet_code is NULL, so allow it

                # Check for invalid row wildcards
                if (
                    df_table["row_code"].isnull().all()
                    and node.rows is not None
                    and "*" in node.rows
                ):
                    # Check if r* is required to avoid duplicate (column, sheet) combinations
                    # IMPORTANT: Include NA/NULL values in grouping (dropna=False)
                    df_without_rows = df_table.groupby(
                        ["column_code", "sheet_code"], dropna=False
                    ).size()
                    has_duplicates = (df_without_rows > 1).any()

                    if not has_duplicates:
                        # Only raise error if rows are truly not needed
                        raise SemanticError("1-19")
                    # else: r* is required even though row_code is NULL, so allow it

                # Attach node_data to the VarID node for later serialization
                # This enables the JSON serializer to output actual cell data
                node.data = node_data

                # Expand range-type values in rows/cols/sheets to actual codes from the database
                # This ensures adam-engine receives scalar values, not list-type ranges
                _expand_ranges_from_data(node, node_data)

            # Adding data to self.data
            if self.data is None:
                self.data = df_table
            else:
                self.data = pd.concat(
                    [self.data, df_table], axis=0
                ).reset_index(drop=True)

            self.key_components[table] = ViewKeyComponentsQuery.get_by_table(
                self.session, table, self.release_id
            )

    # Start of visiting nodes
    def visit_WithExpression(self, node: WithExpression) -> None:
        if node.partial_selection.is_table_group:
            raise errors.SemanticError(
                "1-10", table=node.partial_selection.table
            )
        self.partial_selection = node.partial_selection
        self.visit(node.expression)

    def visit_VarID(self, node: VarID) -> None:

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

        _create_operand_label(node)
        label = node.label
        if label is None:
            raise RuntimeError("VarID label not created")
        set_operand_label(label, node)

        table_info: dict[str, list[str] | None] = {
            "rows": node.rows,
            "cols": node.cols,
            "sheets": node.sheets,
        }

        if node.table not in self.tables:
            self.tables[node.table] = table_info
            self.operands[node.table] = [node]
        else:
            self.operands[node.table].append(node)
            _modify_table(node, self.tables[node.table])

    def visit_Dimension(self, node: Dimension) -> None:
        if node.dimension_code not in self.dimension_codes:
            self.dimension_codes.append(node.dimension_code)
        # Store reference to node for property_id enrichment
        self.dimension_nodes.append(node)

    def visit_GetOp(self, node: GetOp) -> None:
        """Visit GetOp nodes to collect component codes for property_id lookup."""
        # Visit the operand first to ensure it's properly validated
        self.visit(node.operand)
        if node.component not in self.getop_components:
            self.getop_components.append(node.component)
        # Store reference to node for property_id enrichment
        self.getop_nodes.append(node)
        # Visit the operand to ensure it gets processed (e.g., VarID nodes inside GetOp)
        self.visit(node.operand)

    def visit_VarRef(self, node: VarRef) -> None:
        if not VariableVersionQuery.check_variable_exists(
            self.session, node.variable, self.release_id
        ):
            raise errors.SemanticError("1-3", variable=node.variable)

    def visit_PreconditionItem(self, node: PreconditionItem) -> None:

        if self.is_scripting:
            raise errors.SemanticError("6-3", precondition=node.variable_code)

        variable_code = node.variable_code
        if variable_code is None:
            raise errors.SemanticError("1-3", variable=variable_code)

        if not VariableVersionQuery.check_variable_exists(
            self.session, variable_code, self.release_id
        ):
            raise errors.SemanticError("1-3", variable=variable_code)

        self.preconditions = True
        _create_operand_label(node)
        label = node.label
        if label is None:
            raise RuntimeError("PreconditionItem label not created")
        set_operand_label(label, node)

    def visit_Scalar(self, node: Scalar) -> None:
        if node.item and node.scalar_type == "Item":
            if node.item not in self.items:
                self.items.append(node.item)

    def visit_WhereClauseOp(self, node: WhereClauseOp) -> None:
        self.visit(node.operand)
        checker = WhereClauseChecker()
        checker.visit(node.condition)
        node.key_components = checker.key_components
        self.visit(node.condition)

    def visit_OperationRef(self, node: OperationRef) -> None:
        if not self.is_scripting:
            raise errors.SemanticError(
                "6-2", operation_code=node.operation_code
            )

    def visit_PersistentAssignment(self, node: PersistentAssignment) -> None:
        # TODO: visit node.left when there are calculations variables in database
        self.visit(node.right)

    def visit_TemporaryAssignment(self, node: TemporaryAssignment) -> None:
        temporary_identifier = node.left
        self.operations.append(temporary_identifier.value)
        self.visit(node.right)

    def check_operations(self) -> None:
        if len(self.operations):
            df_operations = OperationQuery.get_operations_from_codes(
                session=self.session,
                operation_codes=self.operations,
                release_id=self.release_id,
            )
            if len(df_operations.values) < len(self.operations):
                not_found_operations = list(
                    set(self.operations).difference(set(df_operations["Code"]))
                )
                raise errors.SemanticError(
                    "1-8", operations=not_found_operations
                )
            self.operations_data = df_operations


def extract_data_types(node: VarID, database_types: "pd.Series[Any]") -> None:
    """Extract data type of var ids from database information
    :param node: Var id
    :param database_types: Series that contains the data types of node elements
    :return: None.
    """
    unique_types = database_types.unique()
    scalar_factory = ScalarFactory()
    if len(unique_types) == 1:
        data_type = scalar_factory.database_types_mapping(unique_types[0])
        if node.interval and isinstance(data_type(), Number):
            # Only Number supports the interval-accepting constructor.
            node.type = data_type(node.interval)  # type: ignore[call-arg]
        else:
            node.type = data_type()
    else:
        data_types = {
            scalar_factory.database_types_mapping(data_type)
            for data_type in unique_types
        }
        if len(data_types) == 1:
            data_type = data_types.pop()
            node.type = data_type()
        elif (
            len(data_types) == 2
            and Number in data_types
            and Integer in data_types
        ):
            node.type = Number()
        else:
            node.type = Mixed()
