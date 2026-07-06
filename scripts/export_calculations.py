#!/usr/bin/env python
"""Export a module's calculations set as JSON (EBA drr_operations format).

Replicates ``EBA/drr_operations/development/export_calculations.py`` on
top of dpmcore. Given a module code and a reference date, pulls the
module's calculation operations from the database (``ModuleVersion`` ⨝
``OperationOutput`` ⨝ ``OperationVersion``) and writes:

- the main calculations JSON (keyed by the module's EBA taxonomy URI),
- a companion ``*_datapoints.json`` mapping variable_id to cell codes.

The output format is a downstream contract (deployment scripts /
KRI-CODIS): it must stay byte-identical to what the drr_operations
script produces. This file mirrors the EBA script; everything that
script gets from CodeDRR / models.py / the EBA SQL views lives in
``scripts/_eba_parity.py`` (importing it also applies the parity shim
over dpmcore's internals).

Usage:
    python scripts/export_calculations.py <MODULE_CODE> \
        --reference-date YYYY-MM-DD \
        [--publication-date YYYY-MM-DD] \
        [--db <sqlite path | SQLAlchemy URL>] \
        [--output out.json] [--datapoints-output out_dp.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

from _eba_parity import (
    CalculationsJSONVisitor,
    DAGAnalyzer,
    EBAOperandsChecking,
    filter_by_release_eba,
    get_calculations,
    get_eba_data_types,
    get_module_version_id,
    get_operation_codes_for_module,
    get_output_variable_ids,
    live_table_vids,
)
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker

from dpmcore.dpm_xl.ast.nodes import Constant, VarID, VarRef, WithExpression
from dpmcore.dpm_xl.ast.template import ASTTemplate
from dpmcore.dpm_xl.model_queries import (
    ViewDatapointsQuery,
    ViewKeyComponentsQuery,
)
from dpmcore.dpm_xl.utils.data_handlers import filter_all_data, generate_xyz
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import TableVersion, TableVersionCell
from dpmcore.services.syntax import SyntaxService

logger = logging.getLogger(__name__)

EBA_BASE_URI = "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/"
_DEFAULT_DB = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "test_data.db"
)


# ---------------------------------------------------------------------------
# Module / release resolution
# ---------------------------------------------------------------------------


def _to_python_int(value):
    """Convert numpy/DB int types to Python int (None-safe)."""
    return int(value) if value is not None else None


def get_module_metadata(session, module_vid):
    """Get module metadata from database."""
    mv = (
        session.query(ModuleVersion)
        .filter(ModuleVersion.module_vid == module_vid)
        .first()
    )
    if mv is None:
        raise ValueError(f"Module version {module_vid} not found")
    return {
        "module_vid": module_vid,
        "code": mv.code,
        "version_number": mv.version_number or "1.0.0",
        "from_date": mv.from_reference_date,
        "to_date": mv.to_reference_date,
        "start_release_id": _to_python_int(mv.start_release_id),
    }


def get_release_info(session, release_id, publication_date=None):
    """Get DPM release information."""
    pub_date = publication_date or str(date.today())  # noqa: DTZ011
    release_code = None
    if release_id is not None:
        release = (
            session.query(Release)
            .filter(Release.release_id == _to_python_int(release_id))
            .first()
        )
        release_code = release.code if release else None
    return {"release": release_code, "publication_date": pub_date}


def get_module_uri(session, module_vid):
    """Build the EBA module URI from Framework and Release data.

    Returns (uri, framework_code).
    """
    result = (
        session.query(
            ModuleVersion.code.label("module_code"),
            Framework.code.label("framework_code"),
            Release.code.label("release_code"),
        )
        .join(Module, Module.module_id == ModuleVersion.module_id)
        .join(Framework, Framework.framework_id == Module.framework_id)
        .outerjoin(
            Release, Release.release_id == ModuleVersion.start_release_id
        )
        .filter(ModuleVersion.module_vid == int(module_vid))
        .first()
    )
    if result is None:
        raise ValueError(
            f"Could not find framework info for module VID {module_vid}"
        )
    uri = (
        f"{EBA_BASE_URI}{result.framework_code.lower()}/"
        f"{result.release_code}/mod/{result.module_code.lower()}"
    )
    return uri, result.framework_code


# ---------------------------------------------------------------------------
# Dependency / output table queries
# ---------------------------------------------------------------------------


def group_tables_by_module(session, tables, release_id=None):
    """Group dependency tables by their containing module.

    Args:
        session: Database session.
        tables: {table_code: {"variables": ..., "open_keys": ...}}.
        release_id: Optional release filter.

    Returns:
        {module_code: {module_vid, from_date, to_date, tables}}.
    """
    module_tables = {}

    for table_code, table_info in tables.items():
        table_query = session.query(TableVersion.table_vid).filter(
            TableVersion.code == table_code
        )
        if release_id:
            table_query = filter_by_release_eba(
                table_query,
                TableVersion.start_release_id,
                TableVersion.end_release_id,
                release_id,
            )
        else:
            table_query = table_query.filter(
                or_(
                    TableVersion.end_release_id.is_(None),
                    TableVersion.end_release_id == 9999,
                )
            )
        table_result = table_query.first()
        if not table_result:
            continue
        table_vid = table_result[0]

        module_query = (
            session.query(
                ModuleVersionComposition.module_vid.label("ModuleVID"),
                ModuleVersion.code.label("module_code"),
                ModuleVersion.from_reference_date.label("FromReferenceDate"),
                ModuleVersion.to_reference_date.label("ToReferenceDate"),
            )
            .join(
                ModuleVersion,
                ModuleVersion.module_vid
                == ModuleVersionComposition.module_vid,
            )
            .filter(ModuleVersionComposition.table_vid == table_vid)
        )
        if release_id:
            module_query = filter_by_release_eba(
                module_query,
                ModuleVersion.start_release_id,
                ModuleVersion.end_release_id,
                release_id,
            )
        else:
            module_query = module_query.filter(
                or_(
                    ModuleVersion.end_release_id.is_(None),
                    ModuleVersion.end_release_id == 9999,
                )
            )

        for row in module_query.all():
            module_code = row.module_code
            if module_code not in module_tables:
                module_tables[module_code] = {
                    "module_vid": row.ModuleVID,
                    "from_date": row.FromReferenceDate,
                    "to_date": row.ToReferenceDate,
                    "tables": {},
                }
            module_tables[module_code]["tables"][table_code] = {
                "variables": {str(v): "m" for v in table_info["variables"]},
                "open_keys": table_info.get("open_keys", {}),
            }

    return module_tables


def get_output_tables(
    session, module_vid, output_variable_ids, release_id=None
):
    """Output tables of the module holding the given output VariableVIDs.

    Returns {table_code: {"variables": {var_id: data_type}}}.
    """
    if not output_variable_ids:
        return {}

    composition_query = (
        session.query(
            ModuleVersionComposition.table_vid.label("TableVID"),
            TableVersion.code.label("table_code"),
        )
        .join(
            TableVersion,
            TableVersion.table_vid == ModuleVersionComposition.table_vid,
        )
        .filter(ModuleVersionComposition.module_vid == module_vid)
    )

    output_tables = {}
    for comp_row in composition_query.all():
        cell_query = session.query(TableVersionCell.variable_vid).filter(
            TableVersionCell.table_vid == comp_row.TableVID,
            TableVersionCell.variable_vid.in_(output_variable_ids),
        )
        table_var_ids = [row.variable_vid for row in cell_query.all()]
        if table_var_ids:
            data_types_map = get_eba_data_types(
                session, table_var_ids, release_id
            )
            output_tables[comp_row.table_code] = {
                "variables": {
                    str(var_id): data_types_map.get(str(var_id), "m")
                    for var_id in table_var_ids
                }
            }
    return output_tables


# ---------------------------------------------------------------------------
# AST visitors (ports of the EBA script's visitors)
# ---------------------------------------------------------------------------


class OutputExtractor(ASTTemplate):
    """Extract output variables from PersistentAssignment nodes.

    Handles both VarRef (variable code) and VarID (table cell) left
    sides.
    """

    def __init__(self, data=None):
        """Track outputs, optionally resolving VarID cells via *data*."""
        super().__init__()
        self.data = data
        # From VarRef assignments
        self.output_variables = []
        # From VarID assignments
        self.output_variable_ids = []
        self.output_table_variables = {}

    def visit_PersistentAssignment(self, node):
        """Collect the assignment's LHS, then walk its RHS."""
        if isinstance(node.left, VarRef):
            self.output_variables.append(node.left.variable)
        elif isinstance(node.left, VarID) and self.data is not None:
            self._extract_varid_outputs(node.left)
        self.visit(node.right)

    def visit_TemporaryAssignment(self, node):
        """Walk the RHS only (temporaries produce no output)."""
        self.visit(node.right)

    def _extract_varid_outputs(self, varid_node):
        try:
            filtered = filter_all_data(
                self.data,
                varid_node.table,
                varid_node.rows or [],
                varid_node.cols or [],
                varid_node.sheets or [],
            )
        except Exception:
            logger.warning(
                "Failed to filter data for output VarID table=%s",
                varid_node.table,
            )
            return

        if not filtered.empty:
            var_ids = [int(v) for v in filtered["variable_id"].unique()]
            self.output_variable_ids.extend(var_ids)
            table = varid_node.table
            if table not in self.output_table_variables:
                self.output_table_variables[table] = []
            self.output_table_variables[table].extend(var_ids)


class DependencyTableExtractor(ASTTemplate):
    """Extract tables and their datapoints from expressions."""

    def __init__(self, session, release_id=None):
        """Collect dependency tables using *session* for lookups."""
        super().__init__()
        self.session = session
        self.release_id = release_id
        self.tables = {}
        self.all_datapoints = []

    def _get_open_keys(self, table_code):
        key_df = ViewKeyComponentsQuery.get_by_table(
            self.session, table_code, self.release_id
        )
        if key_df.empty:
            return {}
        return dict(
            zip(
                key_df["property_code"],
                key_df["data_type"],
                strict=False,
            )
        )

    def visit_VarID(self, node):
        """Register the node's table and its filtered datapoints."""
        table = node.table
        if not table:
            return

        table_info = {
            "rows": node.rows,
            "cols": node.cols,
            "sheets": node.sheets,
        }

        # Parity note: the EBA script does not pass release_id here.
        datapoints_df = ViewDatapointsQuery.get_filtered_datapoints(
            self.session, table, table_info
        )
        if not datapoints_df.empty:
            datapoints_df = datapoints_df[
                datapoints_df["table_vid"].isin(
                    live_table_vids(self.session, table)
                )
            ]
            # EBA reads from the pre-filtered view, so its variable_id
            # column is int64; restore that dtype once the ghost-table
            # rows (the only NaN source) are gone.
            if (
                not datapoints_df.empty
                and not datapoints_df["variable_id"].isnull().any()
            ):
                datapoints_df = datapoints_df.assign(
                    variable_id=datapoints_df["variable_id"].astype("int64")
                )

        if not datapoints_df.empty:
            variable_ids = datapoints_df["variable_id"].tolist()
            if table not in self.tables:
                self.tables[table] = {
                    "variables": set(),
                    "open_keys": self._get_open_keys(table),
                }
            self.tables[table]["variables"].update(variable_ids)
            self.all_datapoints.extend(variable_ids)


def _constant_value(value):
    """Extract a scalar from a Constant node (non-Constants pass through)."""
    if not isinstance(value, Constant):
        return value
    if value.type == "Integer":
        raw = value.value
        if isinstance(raw, str) and "." in raw:
            raw = float(raw)
        return int(raw)
    if value.type == "Number":
        return float(value.value)
    return value.value


def _unwrap_with_expressions(node):
    """Replace every WithExpression in the AST with its expression child.

    Run only after OperandsChecking has resolved the with-context onto
    the inner VarIDs (their ``data`` is already attached).
    """
    if node is None or not hasattr(node, "__dict__"):
        return

    for attr_name, attr_value in list(vars(node).items()):
        while isinstance(attr_value, WithExpression):
            attr_value = attr_value.expression
            setattr(node, attr_name, attr_value)

        if isinstance(attr_value, list):
            new_list = []
            for item in attr_value:
                while isinstance(item, WithExpression):
                    item = item.expression
                new_list.append(item)
            setattr(node, attr_name, new_list)
            for item in new_list:
                _unwrap_with_expressions(item)
        else:
            _unwrap_with_expressions(attr_value)


class VarIDDataEnricher(ASTTemplate):
    """Compute the EBA-format ``data`` array for every resolvable VarID.

    Two-pass on purpose: the enrichment runs in ASTTemplate visit order
    so ``operand_reference_id`` values match the EBA original; the
    serializer then emits the precomputed dict.
    """

    def __init__(self, data):
        """Enrich against the operands *data* DataFrame."""
        super().__init__()
        self.data = data
        self._ref_counter = 0

    def _next_ref_id(self):
        self._ref_counter += 1
        return 100000 + self._ref_counter

    def visit_VarID(self, node):
        """Attach the EBA-format dict to the node (eba_varid_json)."""
        if self.data is None or self.data.empty:
            return
        try:
            filtered = filter_all_data(
                self.data,
                node.table,
                node.rows or [],
                node.cols or [],
                node.sheets or [],
            )
        except Exception:
            logger.warning(
                "Failed to filter data for VarID enrichment table=%s",
                node.table,
            )
            return
        if filtered.empty:
            return

        xyz_cols = filtered[
            [
                "row_code",
                "column_code",
                "sheet_code",
                "variable_id",
                "cell_id",
            ]
        ].copy()
        xyz_data = generate_xyz(xyz_cols)

        unique_rows = filtered["row_code"].dropna().unique()
        unique_cols = filtered["column_code"].dropna().unique()
        has_multi_rows = len(unique_rows) > 1
        has_multi_cols = len(unique_cols) > 1
        single_row = (
            unique_rows[0] if node.rows and not has_multi_rows else None
        )
        single_col = (
            unique_cols[0] if node.cols and not has_multi_cols else None
        )

        data_list = []
        for item in xyz_data:
            entry = {}
            if has_multi_rows and item.get("x") is not None:
                entry["x"] = int(item["x"])
                entry["row"] = item["row_code"]
            if has_multi_cols and item.get("y") is not None:
                entry["y"] = int(item["y"])
                entry["column"] = item["column_code"]
            entry["datapoint"] = int(item["variable_id"])
            entry["operand_reference_id"] = self._next_ref_id()
            data_list.append(entry)

        result = {"class_name": "VarID"}
        result["data"] = data_list
        result["table"] = node.table
        if single_row is not None:
            result["row"] = single_row
        if single_col is not None:
            result["column"] = single_col
        result["sheet"] = node.sheets
        result["interval"] = bool(node.interval) if node.interval else False
        result["default"] = _constant_value(node.default)
        node.eba_varid_json = result


def _build_datapoint_mapping(data):
    """{variable_id: {table, row, column, sheet}} from the operands data."""
    if data is None or data.empty:
        return {}
    cols = [
        "variable_id",
        "table_code",
        "row_code",
        "column_code",
        "sheet_code",
    ]
    subset = (
        data[cols]
        .dropna(subset=["variable_id"])
        .drop_duplicates(subset=["variable_id"])
    )
    subset = subset.astype(object).where(subset.notna(), None)
    mapping = {}
    for rec in subset.to_dict(orient="records"):
        mapping[str(int(rec["variable_id"]))] = {
            "table": rec["table_code"],
            "row": rec["row_code"],
            "column": rec["column_code"],
            "sheet": rec["sheet_code"],
        }
    return mapping


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _build_expression(calculations):
    """Build the full expression string from calculation records."""
    parts = []
    for calc in calculations:
        expr = calc["expression"]
        if ";" not in expr:
            expr = expr + ";"
        parts.append(expr)
    return "".join(parts)


def _resolve_output_variables(session, output_extractor, release_id):
    """Resolve output variables from VarRef and VarID assignments.

    Returns (output_variables, output_variable_id_list,
    output_var_data_types).
    """
    output_var_ids = get_output_variable_ids(
        session, output_extractor.output_variables, release_id
    )
    output_variable_id_list = list(output_var_ids.values())
    output_variable_id_list.extend(output_extractor.output_variable_ids)

    all_output_ids = list(set(output_variable_id_list))
    output_var_data_types = get_eba_data_types(
        session, all_output_ids, release_id
    )

    output_variables = {}
    # From VarRef assignments
    for var_code in output_extractor.output_variables:
        var_id = output_var_ids.get(var_code)
        if var_id:
            var_id_str = str(var_id)
            output_variables[var_id_str] = output_var_data_types.get(
                var_id_str, "m"
            )
    # From VarID assignments
    for var_id in output_extractor.output_variable_ids:
        var_id_str = str(var_id)
        output_variables[var_id_str] = output_var_data_types.get(
            var_id_str, "m"
        )

    return output_variables, output_variable_id_list, output_var_data_types


def _build_output_tables(
    session,
    module_vid,
    output_variable_id_list,
    output_extractor,
    output_var_data_types,
    release_id,
):
    """Build the output tables dict from VarRef and VarID sources."""
    unique_output_ids = list(set(output_variable_id_list))
    output_tables = get_output_tables(
        session, module_vid, unique_output_ids, release_id
    )
    for table_code, var_ids in output_extractor.output_table_variables.items():
        if table_code not in output_tables:
            output_tables[table_code] = {"variables": {}}
        for var_id in var_ids:
            var_id_str = str(var_id)
            output_tables[table_code]["variables"][var_id_str] = (
                output_var_data_types.get(var_id_str, "m")
            )
    return output_tables


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------


def export_calculations(
    module_code, reference_date, publication_date=None, database_url=None
):
    """Export calculations for a module as JSON structures.

    Returns (calculations_export, datapoint_mapping).
    """
    engine = create_engine(database_url)
    session = sessionmaker(bind=engine)()

    try:
        module_vid_result = get_module_version_id(
            session, module_code, reference_date
        )
        module_vid = int(module_vid_result[0])

        module_uri, framework_code = get_module_uri(session, module_vid)
        module_meta = get_module_metadata(session, module_vid)
        release_id = module_meta.get("start_release_id")
        release_info = get_release_info(session, release_id, publication_date)

        try:
            calculations = get_calculations(session, module_vid)
        except Exception as exc:
            if "OperationOutput" in str(exc):
                raise ValueError(
                    f"No calculations found for module {module_code}: "
                    "the database has no OperationOutput table (it only "
                    "exists in the EBA SQL Server DPM databases)"
                ) from exc
            raise
        if not calculations:
            raise ValueError(f"No calculations found for module {module_code}")
        full_expression = _build_expression(calculations)

        # Single AST for the whole calculations script
        ast = SyntaxService().parse(full_expression)

        # Operation codes aligned with calculations via operation VID,
        # so operation_codes[i] produced ast.children[i].
        operation_data = get_operation_codes_for_module(
            session, module_vid, release_id
        )
        code_by_vid = {
            op["OperationVID"]: op["operation_code"] for op in operation_data
        }
        operation_codes = [
            code_by_vid.get(calc["operation_vid"]) for calc in calculations
        ]

        # Extract dependency tables
        dep_extractor = DependencyTableExtractor(session, release_id)
        dep_extractor.visit(ast)

        # The DAG reorders ast.children by dependency; keep
        # operation_codes in lockstep by following each child object.
        code_by_child = {
            id(child): code
            for child, code in zip(ast.children, operation_codes, strict=False)
        }
        if len(ast.children) > 1:
            DAGAnalyzer().create_dag(ast)
        operation_codes = [
            code_by_child.get(id(child)) for child in ast.children
        ]

        # Operand resolution (attaches datapoint data to VarID nodes and
        # handles with/where clauses internally)
        operands_checker = EBAOperandsChecking(
            session, full_expression, ast, release_id, is_scripting=True
        )

        # Drop WithExpression wrappers; the with-context is already
        # resolved onto the inner VarIDs by OperandsChecking.
        _unwrap_with_expressions(ast)

        # Enrich VarID nodes with the EBA-format data arrays
        enricher = VarIDDataEnricher(operands_checker.data)
        enricher.visit(ast)

        # Extract output variables (VarRef and VarID) in a single pass
        output_extractor = OutputExtractor(data=operands_checker.data)
        output_extractor.visit(ast)

        # Data types for the dependency-table variables
        all_datapoints = list(set(dep_extractor.all_datapoints))
        eba_types = get_eba_data_types(session, all_datapoints, release_id)
        for table_info in dep_extractor.tables.values():
            table_info["variables"] = {
                str(var_id): eba_types.get(str(var_id), "m")
                for var_id in table_info["variables"]
            }

        # Group dependency tables by module; build dependency URIs
        dependency_modules = group_tables_by_module(
            session, dep_extractor.tables, release_id
        )
        dependency_modules_with_uri = {}
        for dep_module_code, dep_info in dependency_modules.items():
            if dep_module_code == module_code:
                continue
            dep_uri, _ = get_module_uri(session, dep_info["module_vid"])
            dependency_modules_with_uri[dep_uri] = {
                "tables": dep_info["tables"]
            }

        # Resolve output variables and tables
        output_variables, output_variable_id_list, output_var_data_types = (
            _resolve_output_variables(session, output_extractor, release_id)
        )
        output_tables = _build_output_tables(
            session,
            module_vid,
            output_variable_id_list,
            output_extractor,
            output_var_data_types,
            release_id,
        )

        # Serialize AST and build final output
        ast_json = CalculationsJSONVisitor().visit(ast)
        datapoints = _build_datapoint_mapping(operands_checker.data)

        main_output = {
            module_uri: {
                "module_code": module_code,
                "framework_code": framework_code,
                "module_version": module_meta.get("version_number", "1.0.0"),
                "dpm_release": release_info,
                "dates": {
                    "from": str(module_meta["from_date"])
                    if module_meta["from_date"]
                    else None,
                    "to": str(module_meta["to_date"])
                    if module_meta["to_date"]
                    else None,
                },
                "calculations": {
                    "ast": ast_json,
                    "operation_codes": operation_codes,
                },
                "output_variables": output_variables,
                "output_tables": output_tables,
                "dependency_modules": dependency_modules_with_uri,
            }
        }
        return main_output, datapoints

    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _database_url(db_arg):
    """Accept either a SQLite file path or a full SQLAlchemy URL."""
    if "://" in db_arg:
        return db_arg
    path = Path(db_arg).resolve()
    if not path.exists():
        raise ValueError(f"Database file not found: {path}")
    return f"sqlite:///{path}"


def main():
    """Parse CLI arguments, run the export, and write the JSON files."""
    parser = argparse.ArgumentParser(
        description="Export calculations for a module to JSON "
        "(EBA drr_operations format)"
    )
    parser.add_argument(
        "module_code",
        help="Module code (e.g., CAL_EXAMPLE)",
    )
    parser.add_argument(
        "--reference-date",
        required=True,
        help="Reference date (YYYY-MM-DD format)",
    )
    parser.add_argument(
        "--publication-date",
        help="Publication date for the DPM release "
        "(YYYY-MM-DD format, default: current date)",
        default=None,
    )
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB),
        help=f"SQLite file path or SQLAlchemy URL (default: {_DEFAULT_DB})",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: stdout)",
        default=None,
    )
    parser.add_argument(
        "--datapoints-output",
        help="Path for the datapoint mapping file "
        "(default: <output-base>_datapoints.json or "
        "<module_code>_datapoints.json)",
        default=None,
    )

    args = parser.parse_args()

    try:
        main_result, datapoints = export_calculations(
            args.module_code,
            args.reference_date,
            args.publication_date,
            database_url=_database_url(args.db),
        )

        main_json = json.dumps(main_result, indent=2, default=str)
        datapoints_json = json.dumps(datapoints, indent=2, default=str)

        if args.output:
            with open(args.output, "w") as f:
                f.write(main_json)
            print(f"Output written to {args.output}", file=sys.stderr)
        else:
            print(main_json)

        if args.datapoints_output:
            datapoints_path = args.datapoints_output
        elif args.output:
            base, ext = os.path.splitext(args.output)
            datapoints_path = f"{base}_datapoints{ext or '.json'}"
        else:
            datapoints_path = f"{args.module_code}_datapoints.json"

        with open(datapoints_path, "w") as f:
            f.write(datapoints_json)
        print(f"Datapoints written to {datapoints_path}", file=sys.stderr)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
