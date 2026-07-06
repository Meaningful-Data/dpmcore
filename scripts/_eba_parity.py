"""Compatibility layer for scripts/export_calculations.py.

Everything the drr_operations export script gets from outside its own
file — CodeDRR modules, ``models.py`` helpers, and SQL Server views
that live in the EBA databases — ported on top of dpmcore. Split out
so the main script mirrors the EBA original file-for-file.

Contents:

- The EBA numeric release filters (``filter_by_release_eba`` and
  friends), used by the queries ported below.
- A port of the ``drr_datapoints`` SQL view (``eba_get_table_data``)
  and of the ``drr_calculations`` / ``drr_data_types`` view queries.
- CodeDRR's ``DAGAnalyzer`` (pure-Python topological sort).
- ``EBAOperandsChecking`` and ``CalculationsJSONVisitor``: dpmcore's
  operand checker and serializer adjusted to CodeDRR behaviour.
- The parity shim: importing this module replaces
  ``ViewDatapointsQuery.get_table_data`` (see the bottom of the file).

If dpmcore ever absorbs these semantics natively, this module is what
gets deleted — re-run the KRI/CODIS parity diff to prove it.
"""

from __future__ import annotations

from sqlalchemy import or_

from dpmcore.dpm_xl.ast.nodes import (
    Constant,
    PersistentAssignment,
    TemporaryAssignment,
    VarID,
)
from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.model_queries import (
    ViewDatapointsQuery,
    compile_query_for_pandas,
    read_sql_with_connection,
)
from dpmcore.dpm_xl.utils.filters import filter_by_date
from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor
from dpmcore.orm.glossary import Property
from dpmcore.orm.infrastructure import DataType
from dpmcore.orm.operations import (
    Operation,
    OperationOutput,
    OperationVersion,
)
from dpmcore.orm.packaging import ModuleVersion
from dpmcore.orm.query_utils import chunked_in
from dpmcore.orm.rendering import TableVersion, TableVersionCell
from dpmcore.orm.variables import VariableVersion

# ---------------------------------------------------------------------------
# EBA (drr_operations) filter semantics — ported verbatim for parity.
# dpmcore's semver-aware filter_by_release is deliberately NOT used here.
# ---------------------------------------------------------------------------


def filter_by_release_eba(query, start_col, end_col, release_id=None):
    """Live release: (end IS NULL or end = 9999) and start != 9999.

    Specific release: start <= id and (end > id or end IS NULL or
    end = 9999) — the ghost release (9999) counts as still-live, per
    drr_operations' fix-implicit-open-keys branch.
    """
    if release_id is None:
        return query.filter(
            or_(end_col.is_(None), end_col == 9999),
            start_col != 9999,
        )
    return query.filter(
        start_col <= release_id,
        or_(
            end_col > release_id,
            end_col.is_(None),
            end_col == 9999,
        ),
    )


def _filter_elements_eba(query, column, values):
    """Port of drr_operations' ``filter_elements`` dimension filter."""
    if len(values) == 1:
        if values[0] == "*":
            return query
        if "-" in values[0]:
            limits = values[0].split("-")
            return query.filter(column.between(limits[0], limits[1]))
        return query.filter(column == values[0])
    if not any("-" in x for x in values):
        return query.filter(column.in_(values))
    dynamic_filter = []
    for x in values:
        if "-" in x:
            limits = x.split("-")
            dynamic_filter.append(column.between(limits[0], limits[1]))
        else:
            dynamic_filter.append(column == x)
    return query.filter(or_(*dynamic_filter))


def _live_table_version_filter(query):
    """The ``drr_datapoints`` view's baked-in TableVersion filter.

    (end IS NULL or end = 9999) and start != 9999 — i.e. only live
    (non-ghost) table versions ever reach the EBA pipeline.
    """
    return query.filter(
        or_(
            TableVersion.end_release_id.is_(None),
            TableVersion.end_release_id == 9999,
        ),
        TableVersion.start_release_id != 9999,
    )


def live_table_vids(session, table_code):
    """Live TableVersion VIDs for a table code.

    Used to re-apply the ``drr_datapoints`` view's live-TableVersion
    filter on top of dpmcore's ``get_filtered_datapoints`` result,
    which does not have it.
    """
    query = _live_table_version_filter(
        session.query(TableVersion.table_vid).filter(
            TableVersion.code == table_code
        )
    )
    return {r[0] for r in query.all()}


def eba_get_table_data(
    session, table, rows=None, columns=None, sheets=None, release_id=None
):
    """Port of EBA's ``ViewDatapoints.get_table_data`` over base tables.

    Replaces dpmcore's ``ViewDatapointsQuery.get_table_data`` (see the
    parity shim below): dpmcore's version lacks the drr_datapoints
    view's live-TableVersion filter and normalises the result with a
    sort/dedup pass the EBA pipeline does not have.
    """
    # Inner query: the drr_datapoints view, column for column (a
    # 14-column DISTINCT), so the outer 9-column select goes through
    # the same shape — and, in practice, the same plan/row order — as
    # EBA's select-from-view.
    inner, aliases = ViewDatapointsQuery._create_base_query_with_aliases(
        session
    )
    inner = inner.add_columns(
        TableVersionCell.cell_code.label("cell_code"),
        TableVersion.code.label("table_code"),
        aliases["hvr"].code.label("row_code"),
        aliases["hvc"].code.label("column_code"),
        aliases["hvs"].code.label("sheet_code"),
        VariableVersion.variable_id.label("variable_id"),
        DataType.code.label("data_type"),
        TableVersion.table_vid.label("table_vid"),
        Property.property_id.label("property_id"),
        ModuleVersion.start_release_id.label("start_release"),
        ModuleVersion.end_release_id.label("end_release"),
        TableVersionCell.cell_id.label("cell_id"),
        VariableVersion.context_id.label("context_id"),
        VariableVersion.variable_vid.label("variable_vid"),
    ).distinct()
    inner = _live_table_version_filter(inner)
    view = inner.subquery("drr_datapoints")

    query = session.query(
        view.c.cell_code,
        view.c.table_code,
        view.c.row_code,
        view.c.column_code,
        view.c.sheet_code,
        view.c.variable_id,
        view.c.data_type,
        view.c.table_vid,
        view.c.cell_id,
    ).filter(view.c.table_code == table)
    if rows is not None:
        query = _filter_elements_eba(query, view.c.row_code, rows)
    if columns is not None:
        query = _filter_elements_eba(query, view.c.column_code, columns)
    if sheets is not None:
        query = _filter_elements_eba(query, view.c.sheet_code, sheets)
    query = filter_by_release_eba(
        query,
        view.c.start_release,
        view.c.end_release,
        release_id,
    )
    return read_sql_with_connection(
        compile_query_for_pandas(query.statement, session), session
    )


# ---------------------------------------------------------------------------
# Queries the EBA script gets from CodeDRR's models.py
# ---------------------------------------------------------------------------


def get_module_version_id(session, module_code, reference_date):
    """ModuleVID for a module code valid at *reference_date*.

    Raises (like the EBA original's ``.one()``) when zero or several
    module versions match.
    """
    query = session.query(ModuleVersion.module_vid).filter(
        ModuleVersion.code == module_code
    )
    query = filter_by_date(
        query,
        reference_date,
        ModuleVersion.from_reference_date,
        ModuleVersion.to_reference_date,
    )
    return query.one()


def get_calculations(session, module_vid):
    """Calculation expressions for a module.

    Port of the ``drr_calculations`` view: ModuleVersion ⨝
    OperationOutput ⨝ OperationVersion, live-release filtered.
    """
    query = (
        session.query(
            OperationVersion.operation_vid.label("operation_vid"),
            OperationVersion.expression.label("expression"),
            ModuleVersion.module_id.label("module_id"),
        )
        .select_from(ModuleVersion)
        .join(
            OperationOutput,
            OperationOutput.module_vid == ModuleVersion.module_vid,
        )
        .join(
            OperationVersion,
            OperationVersion.operation_vid == OperationOutput.operation_vid,
        )
        .filter(ModuleVersion.module_vid == module_vid)
    )
    query = filter_by_release_eba(
        query,
        ModuleVersion.start_release_id,
        ModuleVersion.end_release_id,
        None,
    )
    df = read_sql_with_connection(
        compile_query_for_pandas(query.statement, session), session
    )
    return df.to_dict(orient="records")


def get_operation_codes_for_module(session, module_vid, release_id=None):
    """Operation codes for a module via the OperationOutput link."""
    query = (
        session.query(
            OperationOutput.operation_vid.label("OperationVID"),
            Operation.code.label("operation_code"),
            OperationVersion.expression.label("expression"),
        )
        .join(
            OperationVersion,
            OperationVersion.operation_vid == OperationOutput.operation_vid,
        )
        .join(
            Operation,
            Operation.operation_id == OperationVersion.operation_id,
        )
        .filter(
            OperationOutput.module_vid == module_vid,
            Operation.type == "calculation",
        )
    )
    if release_id:
        query = filter_by_release_eba(
            query,
            OperationVersion.start_release_id,
            OperationVersion.end_release_id,
            release_id,
        )
    df = read_sql_with_connection(
        compile_query_for_pandas(query.statement, session), session
    )
    return df.to_dict(orient="records")


def get_eba_data_types(session, datapoints, release_id=None):
    """Data types per datapoint (VariableID), as {str(id): type_code}.

    Port of the ``drr_data_types`` view: VariableVersion ⨝ Property ⨝
    DataType, batched via ``chunked_in`` (SQL Server parameter limit).
    """
    if not datapoints:
        return {}
    ids = sorted({int(dp) for dp in datapoints})
    query = (
        session.query(
            VariableVersion.variable_id.label("datapoint"),
            DataType.code.label("data_type"),
        )
        .join(
            Property,
            Property.property_id == VariableVersion.property_id,
        )
        .join(
            DataType,
            DataType.data_type_id == Property.data_type_id,
        )
    )
    query = filter_by_release_eba(
        query,
        VariableVersion.start_release_id,
        VariableVersion.end_release_id,
        release_id,
    )
    rows = chunked_in(query, VariableVersion.variable_id, ids)
    return {str(row.datapoint): row.data_type for row in rows}


def get_output_variable_ids(session, variable_codes, release_id=None):
    """VariableVIDs for output variable codes (EBA check_precondition)."""
    result = {}
    for code in variable_codes:
        query = session.query(VariableVersion).filter(
            VariableVersion.code == code
        )
        query = filter_by_release_eba(
            query,
            VariableVersion.start_release_id,
            VariableVersion.end_release_id,
            release_id,
        )
        var_info = query.one_or_none()
        if var_info is not None:
            result[code] = var_info.variable_vid
    return result


# ---------------------------------------------------------------------------
# DAG: dependency ordering of the calculations (port of CodeDRR's
# DAGAnalyzer, with a pure-Python Kahn topological sort instead of
# networkx; insertion order is preserved to match nx.topological_sort)
# ---------------------------------------------------------------------------


class DAGAnalyzer(ASTTemplate):
    """Reorders ``ast.children`` so producers precede their consumers."""

    def __init__(self):
        super().__init__()
        self.inputs = []
        self.outputs = []
        self.dependencies = {}
        self.calculation_number = 1

    def create_dag(self, ast):
        self.visit(ast)

        vertex = {}
        for key, calc in self.dependencies.items():
            if calc["outputs"]:
                vertex[key] = calc["outputs"][0]

        edges = []
        for key, calc in self.dependencies.items():
            if calc["outputs"]:
                output = calc["outputs"][0]
                for sub_key, sub_calc in self.dependencies.items():
                    if sub_calc["inputs"] and output in sub_calc["inputs"]:
                        edges.append((key, sub_key))

        sorting = self._topological_sort(list(vertex), edges)
        if edges:
            self._sort_ast(ast, sorting)

    @staticmethod
    def _topological_sort(nodes, edges):
        """Kahn's algorithm, FIFO in node insertion order."""
        indegree = dict.fromkeys(nodes, 0)
        successors = {n: [] for n in nodes}
        for a, b in edges:
            if a in indegree and b in indegree:
                successors[a].append(b)
                indegree[b] += 1
        queue = [n for n in nodes if indegree[n] == 0]
        order = []
        while queue:
            n = queue.pop(0)
            order.append(n)
            for m in successors[n]:
                indegree[m] -= 1
                if indegree[m] == 0:
                    queue.append(m)
        if len(order) != len(nodes):
            raise ValueError("Cyclic dependency detected between calculations")
        return order

    def _sort_ast(self, ast, sorting):
        calculations = list(ast.children)
        lst = [
            calculations[x - 1]
            for x in sorting
            if 0 <= x - 1 < len(calculations)
        ]
        self._check_overwriting(lst)
        ast.children = lst

    def _check_overwriting(self, outputs):
        seen = set()
        for output in outputs:
            value = None
            if isinstance(output, TemporaryAssignment):
                value = output.left.value
            elif isinstance(output, PersistentAssignment):
                value = self._cell_code(output.left)
            if value is None:
                continue
            if value in seen:
                raise ValueError(f"Output {value} is assigned more than once")
            seen.add(value)

    def _calculation_structure(self):
        return {
            "inputs": list(set(self.inputs)),
            "outputs": list(set(self.outputs)),
        }

    def visit_Start(self, node):
        for child in node.children:
            self.visit(child)
            self.dependencies[self.calculation_number] = (
                self._calculation_structure()
            )
            self.calculation_number += 1
            self.inputs = []
            self.outputs = []

    def visit_PersistentAssignment(self, node):
        self.outputs.append(self._cell_code(node.left))
        self.visit(node.right)

    def visit_TemporaryAssignment(self, node):
        self.outputs.append(node.left.value)
        self.visit(node.right)

    def visit_OperationRef(self, node):
        self.inputs.append(node.operation_code)

    def visit_WithExpression(self, node):
        self.visit(node.expression)

    def visit_VarID(self, node):
        self.inputs.append(self._cell_code(node))

    @staticmethod
    def _cell_code(node):
        if isinstance(node, VarID):
            return f"t{node.table}-{node.rows}-{node.cols}-{node.sheets}"
        return node.variable


# ---------------------------------------------------------------------------
# dpmcore internals adjusted to CodeDRR behaviour
# ---------------------------------------------------------------------------


class EBAOperandsChecking(OperandsChecking):
    """OperandsChecking that also walks assignment left-hand sides.

    dpmcore's ``visit_PersistentAssignment`` skips ``node.left`` (its
    TODO waits for calculation variables in the DB); the EBA checker
    visits it generically, so LHS cells are registered as operands,
    get datapoint data attached, and are enriched in the output.
    """

    def visit_PersistentAssignment(self, node):
        self.visit(node.left)
        self.visit(node.right)


class CalculationsJSONVisitor(ASTToJSONVisitor):
    """dpmcore's AST serializer, adjusted to the EBA node shapes."""

    def visit_VarID(self, node):
        enriched = getattr(node, "eba_varid_json", None)
        if enriched is not None:
            return enriched
        # Unresolvable VarIDs (no datapoint data) fall back to the
        # library serializer; parity for this edge case is checked in
        # the bacpac diff.
        return super().visit_VarID(node)

    def visit_TimeShiftOp(self, node):
        # EBA shape: flat period_indicator/component and a string
        # shift_number (dpmcore wraps these in Constant nodes and
        # renames component to reference_period).
        shift = node.shift_number
        if isinstance(shift, Constant):
            shift = shift.value
        return {
            "class_name": "TimeShiftOp",
            "operand": self.visit(node.operand),
            "period_indicator": node.period_indicator,
            "component": node.component,
            "shift_number": str(shift),
        }

    def visit_AggregationOp(self, node):
        # EBA's AggregationOp has no analytic_clause key; dpmcore always
        # emits it (null when absent).
        result = super().visit_AggregationOp(node)
        if result.get("analytic_clause") is None:
            result.pop("analytic_clause", None)
        return result

    def visit_CondExpr(self, node):
        # EBA always emits else_expr (null for if-then without else);
        # dpmcore's generic serialization drops None attributes.
        return {
            "class_name": "CondExpr",
            "condition": self.visit(node.condition),
            "then_expr": self.visit(node.then_expr),
            "else_expr": self.visit(node.else_expr),
        }


# ---------------------------------------------------------------------------
# Parity shim: replace dpmcore's table-data query with the
# drr_datapoints port above — dpmcore's version lacks the view's
# live-TableVersion filter and adds a sort/dedup pass the EBA pipeline
# does not have, either of which breaks output parity. Applied on
# import; process-local — the library on disk is untouched.
# ---------------------------------------------------------------------------

ViewDatapointsQuery.get_table_data = eba_get_table_data
