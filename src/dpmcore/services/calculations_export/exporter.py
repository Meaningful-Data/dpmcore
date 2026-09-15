"""The calculations export pipeline.

Given a module code and a reference date, collects the module version's
calculation operations, parses them as one script, resolves every
operand against the dictionary, and emits the two JSON structures the
downstream deployment consumes: the calculations export (keyed by the
module's EBA taxonomy URI) and its companion datapoint map.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import SQLAlchemyError

from dpmcore.errors import ConfigurationError, InternalError, NotFound
from dpmcore.services.calculations_export.queries import (
    get_calculations,
    get_data_types,
    get_data_types_by_version,
    get_module_metadata,
    get_module_uri,
    get_module_version_id,
    get_output_tables,
    get_output_variable_vids,
    get_release_info,
    group_tables_by_module,
)
from dpmcore.services.calculations_export.visitors import (
    CalculationsJSONVisitor,
    CalculationsOperandsChecking,
    DAGAnalyzer,
    DependencyTableExtractor,
    OutputExtractor,
    VarIDDataEnricher,
    unwrap_with_expressions,
)
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_OPERATION_OUTPUT_TABLE = "OperationOutput"


@dataclass(frozen=True)
class CalculationsExport:
    """A module version's exported calculations and its datapoint map.

    Attributes:
        calculations: The export, keyed by the module's EBA taxonomy
            URI.
        datapoints: ``{variable_id: {table, row, column, sheet}}`` for
            every datapoint the calculations touch -- the companion file
            the deployment reads alongside the export.
    """

    calculations: Dict[str, Any]
    datapoints: Dict[str, Dict[str, Any]]


class CalculationsExporter:
    """Exports a module version's calculations set.

    Args:
        session: An open SQLAlchemy session.
    """

    def __init__(self, session: "Session") -> None:
        """Bind the exporter to ``session``."""
        self.session = session
        self._syntax = SyntaxService()

    def export(
        self,
        module_code: str,
        reference_date: str,
        publication_date: Optional[str] = None,
    ) -> CalculationsExport:
        """Export ``module_code``'s calculations as of ``reference_date``.

        Args:
            module_code: Module code (e.g. ``"KRI"``).
            reference_date: Reference date, ``YYYY-MM-DD``, selecting
                the module version.
            publication_date: Publication date stamped into the
                ``dpm_release`` block; defaults to today.

        Returns:
            The export and its datapoint map.

        Raises:
            ConfigurationError: If the database has no
                ``OperationOutput`` table.
            NotFound: If the module version, or its calculations, cannot
                be resolved.
            InternalError: If the parsed script does not have one
                statement per calculation.
        """
        session = self.session
        module_vid = get_module_version_id(
            session, module_code, reference_date
        )
        module_uri, framework_code = get_module_uri(session, module_vid)
        module_meta = get_module_metadata(session, module_vid)
        release_id = module_meta["start_release_id"]
        release_info = get_release_info(session, release_id, publication_date)

        calculations = self._collect_calculations(module_vid, module_code)
        script = _build_expression(calculations)
        ast, operation_codes = self._parse(script, calculations)
        operands = CalculationsOperandsChecking(
            session,
            script,
            ast,
            release_id,
            is_scripting=True,
            live_table_versions=True,
        )

        # The with-context is on the inner operands now, so the wrapper
        # carries nothing the export needs -- and every later pass sees
        # fully-resolved VarIDs.
        unwrap_with_expressions(ast)
        operation_codes = self._order_by_dependency(ast, operation_codes)

        dependencies = DependencyTableExtractor(session, release_id)
        dependencies.visit(ast)
        enricher = VarIDDataEnricher(operands.data)
        enricher.visit(ast)
        outputs = OutputExtractor(data=operands.data)
        outputs.visit(ast)

        dependency_modules = self._dependency_modules(
            module_code, dependencies, release_id
        )
        output_variables, output_tables = self._outputs(
            module_vid, outputs, release_id
        )

        export = {
            module_uri: {
                "module_code": module_code,
                "framework_code": framework_code,
                "module_version": module_meta["version_number"],
                "dpm_release": release_info,
                "dates": {
                    "from": _as_date_string(module_meta["from_date"]),
                    "to": _as_date_string(module_meta["to_date"]),
                },
                "calculations": {
                    "ast": CalculationsJSONVisitor(enricher.payloads).visit(
                        ast
                    ),
                    "operation_codes": operation_codes,
                },
                "output_variables": output_variables,
                "output_tables": output_tables,
                "dependency_modules": dependency_modules,
            }
        }
        return CalculationsExport(
            calculations=export,
            datapoints=_build_datapoint_mapping(operands.data),
        )

    def _collect_calculations(
        self, module_vid: int, module_code: str
    ) -> List[Dict[str, Any]]:
        """Read the module version's calculations, or explain why not.

        The ``OperationOutput`` check runs only when the query has
        already failed: asking the inspector up front would report the
        table missing on any database that reaches it through a schema
        translation, which is how the EBA SQL Server databases are
        addressed.

        Args:
            module_vid: The module version to read.
            module_code: Its code, for the error message.

        Returns:
            The calculation records that carry an expression.

        Raises:
            ConfigurationError: If the database has no
                ``OperationOutput`` table.
            NotFound: If the module version has no calculations.
        """
        try:
            rows = get_calculations(self.session, module_vid)
        except SQLAlchemyError as exc:
            if self._has_operation_output():
                raise
            raise ConfigurationError(
                title="OperationOutput table missing",
                description=(
                    "This database has no OperationOutput table, so a "
                    "module's calculations cannot be resolved. The table "
                    "exists only in the EBA SQL Server DPM databases, "
                    "not in the Access DPM 2.0 distribution."
                ),
            ) from exc

        calculations = [
            row for row in rows if (row["expression"] or "").strip()
        ]
        if not calculations:
            raise NotFound(
                title="No calculations for module",
                description=(
                    f"Module {module_code!r} (VID {module_vid}) has no "
                    "calculation operation with an expression."
                ),
            )
        return calculations

    def _has_operation_output(self) -> bool:
        """Whether the bound database exposes the link table at all."""
        try:
            inspector = sa_inspect(self.session.get_bind())
            return bool(inspector.has_table(_OPERATION_OUTPUT_TABLE))
        except SQLAlchemyError:
            # The inspector could not answer; assume the table is there
            # so the original query error is the one reported.
            return True

    def _parse(
        self, script: str, calculations: List[Dict[str, Any]]
    ) -> Tuple[Any, List[Optional[str]]]:
        """Parse the calculations as one script, paired with their codes.

        Args:
            script: The concatenated script text.
            calculations: The module's calculation records.

        Returns:
            ``(ast, operation_codes)`` where ``operation_codes[i]``
            belongs to ``ast.children[i]``.

        Raises:
            InternalError: If the script does not parse into exactly one
                statement per calculation -- the pairing is positional,
                so a mismatch would label statements with the wrong
                operation code.
        """
        ast = self._syntax.parse(script)
        if len(ast.children) != len(calculations):
            raise InternalError(
                title="Calculations do not pair with their operations",
                description=(
                    f"{len(calculations)} calculation expressions parsed "
                    f"into {len(ast.children)} statements; an expression "
                    "holding more than one statement cannot be attributed "
                    "to a single operation code."
                ),
            )
        return ast, [calc["operation_code"] for calc in calculations]

    @staticmethod
    def _order_by_dependency(
        ast: Any, operation_codes: List[Optional[str]]
    ) -> List[Optional[str]]:
        """Reorder the script into dependency order, codes in lockstep.

        Args:
            ast: The parsed script; reordered in place.
            operation_codes: Codes positionally matching ``ast.children``.

        Returns:
            The codes in the new statement order.
        """
        if len(ast.children) <= 1:
            return operation_codes
        code_by_child = {
            id(child): code
            for child, code in zip(ast.children, operation_codes, strict=True)
        }
        DAGAnalyzer().create_dag(ast)
        return [code_by_child.get(id(child)) for child in ast.children]

    def _dependency_modules(
        self,
        module_code: str,
        dependencies: DependencyTableExtractor,
        release_id: Optional[int],
    ) -> Dict[str, Dict[str, Any]]:
        """Resolve the dependency tables into per-module URI entries.

        Args:
            module_code: The exported module, excluded from its own
                dependencies.
            dependencies: The collected dependency tables.
            release_id: Release to resolve at.

        Returns:
            ``{module_uri: {"tables": {...}}}``.
        """
        data_types = get_data_types(
            self.session, dependencies.all_datapoints, release_id
        )
        for table_info in dependencies.tables.values():
            table_info["variables"] = {
                str(var_id): data_types.get(str(var_id), "m")
                for var_id in sorted(table_info["variables"])
            }

        grouped = group_tables_by_module(
            self.session, dependencies.tables, release_id
        )
        result: Dict[str, Dict[str, Any]] = {}
        for dep_module_code, dep_info in grouped.items():
            if dep_module_code == module_code:
                continue
            dep_uri, _ = get_module_uri(self.session, dep_info["module_vid"])
            result[dep_uri] = {"tables": dep_info["tables"]}
        return result

    def _outputs(
        self,
        module_vid: int,
        outputs: OutputExtractor,
        release_id: Optional[int],
    ) -> Tuple[Dict[str, str], Dict[str, Dict[str, Dict[str, str]]]]:
        """Resolve what the calculations write, and where.

        Two disjoint ID spaces meet here. A ``VarRef`` target names a
        calculation variable by code, which resolves to a
        ``VariableVID`` -- the id ``TableVersionCell`` and therefore
        ``output_tables`` are keyed by. A ``VarID`` target resolves to
        the ``VariableID``s of the cells it covers, the same datapoint
        ids the operand ``data`` arrays carry. Each is looked up in its
        own space: crossing them matches nothing (so every data type
        falls back to ``"m"``) while occasionally colliding with an
        unrelated row.

        Both are reported under ``output_variables``, which is what the
        downstream deployment reads.

        Args:
            module_vid: The exported module version.
            outputs: The collected assignment targets.
            release_id: Release to resolve at.

        Returns:
            ``(output_variables, output_tables)``.
        """
        vid_by_code = get_output_variable_vids(
            self.session, outputs.output_variables, release_id
        )
        variable_vids = sorted(set(vid_by_code.values()))
        datapoint_ids = sorted(set(outputs.output_variable_ids))

        vid_types = get_data_types_by_version(
            self.session, variable_vids, release_id
        )
        datapoint_types = get_data_types(
            self.session, datapoint_ids, release_id
        )

        output_variables: Dict[str, str] = {}
        for var_code in outputs.output_variables:
            var_vid = vid_by_code.get(var_code)
            if var_vid is not None:
                output_variables[str(var_vid)] = vid_types.get(
                    str(var_vid), "m"
                )
        for var_id in datapoint_ids:
            output_variables[str(var_id)] = datapoint_types.get(
                str(var_id), "m"
            )

        output_tables = get_output_tables(
            self.session, module_vid, variable_vids, release_id
        )
        for table_code, var_ids in outputs.output_table_variables.items():
            table_entry = output_tables.setdefault(
                table_code, {"variables": {}}
            )
            for var_id in var_ids:
                table_entry["variables"][str(var_id)] = datapoint_types.get(
                    str(var_id), "m"
                )
        return output_variables, output_tables


def _build_expression(calculations: List[Dict[str, Any]]) -> str:
    """Concatenate the calculations into one parseable script.

    Each expression is terminated with ``;`` unless it already ends in
    one, so an expression that happens to contain a ``;`` inside a
    string literal is still separated from the next.

    Args:
        calculations: The module's calculation records.

    Returns:
        The full script text.
    """
    parts = []
    for calc in calculations:
        expr = (calc["expression"] or "").strip()
        parts.append(expr if expr.endswith(";") else f"{expr};")
    return "\n".join(parts)


def _as_date_string(value: Any) -> Optional[str]:
    """Render a reference date as a string, passing ``None`` through."""
    return str(value) if value is not None else None


def _build_datapoint_mapping(
    data: Optional[pd.DataFrame],
) -> Dict[str, Dict[str, Any]]:
    """Map every operand datapoint to the cell it sits in.

    Args:
        data: The operands frame, or ``None`` when nothing resolved.

    Returns:
        ``{variable_id: {table, row, column, sheet}}``.
    """
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
    mapping: Dict[str, Dict[str, Any]] = {}
    for rec in subset.to_dict(orient="records"):
        mapping[str(int(rec["variable_id"]))] = {
            "table": _or_none(rec["table_code"]),
            "row": _or_none(rec["row_code"]),
            "column": _or_none(rec["column_code"]),
            "sheet": _or_none(rec["sheet_code"]),
        }
    return mapping


def _or_none(value: Any) -> Any:
    """Normalise pandas' missing markers to ``None`` for JSON output."""
    return None if pd.isna(value) else value
