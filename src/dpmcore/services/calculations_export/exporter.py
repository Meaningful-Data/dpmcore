"""The calculations export pipeline.

Given a module code and a reference date, collects the module version's
calculation operations, parses them as one script, resolves every
operand against the dictionary, and emits the two JSON structures the
downstream deployment consumes: the calculations export (keyed by the
module's EBA taxonomy URI) and its companion datapoint map.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)

import pandas as pd
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import SQLAlchemyError

from dpmcore.errors import ConfigurationError, Invalid, NotFound
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
from dpmcore.services.scope_calculator import ScopeCalculatorService
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

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
        # Reuses validations' shift/predecessor/substitution machinery
        # for version-window resolution.
        self._scope_calc = ScopeCalculatorService(session)

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
            Invalid: If the parsed script does not have one statement
                per calculation.
        """
        session = self.session
        module_vid = get_module_version_id(
            session, module_code, reference_date
        )
        module_meta = get_module_metadata(session, module_vid)
        release_id = module_meta["start_release_id"]
        module_uri, framework_code = get_module_uri(session, module_vid)
        release_info = get_release_info(session, release_id, publication_date)

        calculations = self._collect_calculations(
            module_vid, module_code, release_id
        )
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
        self,
        module_vid: int,
        module_code: str,
        release_id: Optional[int] = None,
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
            release_id: Release to window the operation versions at.

        Returns:
            The calculation records that carry an expression.

        Raises:
            ConfigurationError: If the database has no
                ``OperationOutput`` table.
            NotFound: If the module version has no calculations.
        """
        try:
            rows = get_calculations(self.session, module_vid, release_id)
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
            Invalid: If the script does not parse into exactly one
                statement per calculation -- the pairing is positional,
                so a mismatch would label statements with the wrong
                operation code.
        """
        ast = self._syntax.parse(script)
        if len(ast.children) != len(calculations):
            raise Invalid(
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
            ``{module_uri: {"tables": {...}, "variables": {...}}}``.
        """
        data_types = get_data_types(
            self.session, dependencies.all_datapoints, release_id
        )
        # A new mapping rather than an edit in place: the extractor's
        # own ``variables`` are sets of ids, and rewriting them as
        # ``{id: type}`` dicts would leave it unusable for a second call.
        resolved_tables: Dict[str, Dict[str, Any]] = {
            table_code: {
                **table_info,
                "variables": {
                    str(var_id): data_types.get(str(var_id), "m")
                    for var_id in sorted(table_info["variables"])
                },
            }
            for table_code, table_info in dependencies.tables.items()
        }
        _warn_on_default_data_types(
            "dependency", dependencies.all_datapoints, data_types
        )

        grouped = group_tables_by_module(
            self.session, resolved_tables, release_id
        )
        result: Dict[str, Dict[str, Any]] = {}
        for dep_module_code, dep_info in grouped.items():
            if dep_module_code == module_code:
                continue
            dep_uri, _ = get_module_uri(self.session, dep_info["module_vid"])
            # `tables` only: the calculations contract carries no
            # `variables` key on a dependency entry (that is the
            # validations export's shape), and adding one puts every
            # module with dependencies out of parity with
            # drr_operations.
            entry: Dict[str, Any] = {"tables": dep_info["tables"]}
            cross_time_periods = {
                period
                for table_code in dep_info["tables"]
                for period in dependencies.periods.get(table_code, ())
                if period != "T"
            }
            # Omitted, not empty, when never read at a shifted period.
            if cross_time_periods:
                entry["version_windows"] = (
                    self._resolve_dependency_version_windows(
                        dep_info, dependencies.periods, release_id, dep_uri
                    )
                )
            result[dep_uri] = entry
        return result

    def _resolve_dependency_version_windows(
        self,
        dep_info: Dict[str, Any],
        table_periods: Dict[str, Set[str]],
        release_id: Optional[int],
        current_uri: str,
    ) -> List[Dict[str, Any]]:
        """Resolve ``version_windows`` for one dependency module.

        Runs the substitution check per period, scoped to only that
        period's own tables so an unrelated table's rename can't block
        it, then merges same-candidate results into one entry. A
        candidate resolving to ``current_uri`` itself is not one.
        """
        all_tables = dep_info["tables"]
        ref_periods = {
            period
            for table_code in all_tables
            for period in table_periods.get(table_code, ())
            if period != "T"
        }
        windows: List[Dict[str, Any]] = []
        for period in sorted(ref_periods):
            period_tables = {
                table_code: table_data
                for table_code, table_data in all_tables.items()
                if period in table_periods.get(table_code, ())
            }
            period_variables: Dict[str, str] = {
                var_id: type_code
                for tbl in period_tables.values()
                for var_id, type_code in tbl.get("variables", {}).items()
            }
            found = self._scope_calc._find_version_window_candidate(
                module_id=dep_info["module_id"],
                d0=dep_info["from_date"],
                ref_period=period,
                window_to=dep_info["to_date"],
                current_tables=period_tables,
                current_variables=period_variables,
                current_uri=current_uri,
            )
            if found is None:
                continue
            entry: Dict[str, Any] = {
                "URI": found["URI"],
                "from_reference_date": (
                    str(found["from_reference_date"])
                    if found["from_reference_date"]
                    else None
                ),
                "to_reference_date": (
                    str(found["to_reference_date"])
                    if found["to_reference_date"]
                    else None
                ),
                "tables": _narrow_candidate_tables(
                    found["tables"], period_variables
                ),
            }
            if found["module_version"]:
                entry["module_version"] = found["module_version"]
            windows.append(entry)
        return _merge_version_windows(windows)

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
        _warn_on_default_data_types("output", datapoint_ids, datapoint_types)

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


def _narrow_candidate_tables(
    candidate_tables: Dict[str, Any],
    current_variables: Dict[str, str],
) -> Dict[str, Any]:
    """Group the candidate's own tables by the ``VariableID``s in use.

    Grouped by the candidate's own table codes, not the current side's:
    the same variable may live under a different table there.
    """
    narrowed: Dict[str, Any] = {}
    for table_code, table_data in candidate_tables.items():
        hits = {
            var_id: type_code
            for var_id, type_code in table_data.get("variables", {}).items()
            if var_id in current_variables
        }
        if not hits:
            continue
        narrowed[table_code] = {
            "variables": hits,
            "open_keys": table_data.get("open_keys", {}),
        }
    return narrowed


def _merge_version_windows(
    entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Union same-candidate entries resolved under different periods.

    Two periods landing on the same predecessor Module Version merge
    into one entry (dates unioned, ``tables`` combined).
    """
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for entry in entries:
        key = (entry["URI"], entry.get("module_version", ""))
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(entry)
            continue
        existing["from_reference_date"] = _earliest_date(
            existing["from_reference_date"], entry["from_reference_date"]
        )
        existing["to_reference_date"] = _latest_or_open_date(
            existing["to_reference_date"], entry["to_reference_date"]
        )
        existing["tables"] = _merge_tables(
            existing.get("tables", {}), entry.get("tables", {})
        )
    return list(merged.values())


def _earliest_date(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """The earlier of two ISO date strings; ``None`` on either side wins.

    ``None`` never occurs here in practice (a window's own start is
    always a concrete date), but is handled rather than assumed away.
    """
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _latest_or_open_date(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """The later of two ISO date strings; ``None`` (open-ended) wins."""
    if a is None or b is None:
        return None
    return max(a, b)


def _merge_tables(
    left: Dict[str, Any], right: Dict[str, Any]
) -> Dict[str, Any]:
    """Union two ``{table_code: {variables, open_keys}}`` maps."""
    merged = {code: dict(data) for code, data in left.items()}
    for table_code, table_data in right.items():
        if table_code not in merged:
            merged[table_code] = table_data
            continue
        merged_vars = dict(merged[table_code].get("variables", {}))
        merged_vars.update(table_data.get("variables", {}))
        merged[table_code] = {**merged[table_code], "variables": merged_vars}
    return merged


def _warn_on_default_data_types(
    what: str,
    wanted: Sequence[Any],
    resolved: Dict[str, str],
) -> None:
    """Warn when a datapoint's data type fell back to the ``"m"`` default.

    Operand datapoints come from each table's *live* version, while
    their data types are resolved in the release window the export is
    keyed at. A variable introduced after that release therefore
    resolves to nothing and silently becomes ``"m"``; saying which ones
    turns a wrong data type in the export into a visible one.

    Args:
        what: Short label naming the id set, for the log line.
        wanted: The datapoint ids looked up.
        resolved: The mapping that came back.
    """
    missing = sorted(
        {
            str(int(var_id))
            for var_id in wanted
            if not pd.isna(var_id) and str(int(var_id)) not in resolved
        }
    )
    if not missing:
        return
    logger.warning(
        "%s datapoint(s) have no data type in the export's release "
        "window and default to 'm' (%s): %s",
        len(missing),
        what,
        ", ".join(missing[:20]) + (", ..." if len(missing) > 20 else ""),
    )


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
