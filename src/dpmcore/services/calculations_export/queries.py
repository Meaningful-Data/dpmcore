"""Database queries behind the calculations export.

Everything the export needs that is not already a dpmcore query: the
``OperationOutput`` join that yields a module's calculations, the module
metadata and EBA taxonomy URI, per-datapoint data types, and the output
and dependency tables.

The EBA ``drr_operations`` pipeline these mirror compares release IDs
numerically and spells its perpetual release ``9999``. Neither holds in
dpmcore -- ``ReleaseID`` became opaque at DPM 4.2.1 and the perpetual
release is identified by
:func:`~dpmcore.orm.release_sort_order.compute_sort_order` -- so every
release window here goes through :func:`_release_window`.
"""

from __future__ import annotations

import logging
from datetime import date as date_cls
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, cast

import pandas as pd

from dpmcore.dpm_xl.model_queries import read_sql_with_connection
from dpmcore.dpm_xl.utils.filters import (
    filter_by_date,
    filter_by_release,
    filter_live_only,
)
from dpmcore.errors import NotFound
from dpmcore.orm.glossary import Property
from dpmcore.orm.infrastructure import DataType, Release
from dpmcore.orm.operations import (
    Operation,
    OperationOutput,
    OperationVersion,
)
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.query_utils import chunked_in
from dpmcore.orm.release_sort_order import compute_sort_order
from dpmcore.orm.rendering import TableVersion, TableVersionCell
from dpmcore.orm.variables import VariableVersion

if TYPE_CHECKING:
    from sqlalchemy.orm import Query, Session

logger = logging.getLogger(__name__)

EBA_BASE_URI = "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/"
"""Namespace prefix of the EBA taxonomy URIs the export is keyed by."""


def _release_window(
    query: "Query[Any]",
    start_col: Any,
    end_col: Any,
    release_id: Optional[int],
) -> "Query[Any]":
    """Window a query by ``release_id``, or by "live" when it is ``None``.

    Args:
        query: Session-bound query to filter.
        start_col: Start-release column.
        end_col: End-release column.
        release_id: Release to window at; ``None`` selects the rows that
            are open now and already published
            (:func:`~dpmcore.dpm_xl.utils.filters.filter_live_only`).

    Returns:
        The filtered query.
    """
    if release_id is None:
        return filter_live_only(query, start_col, end_col)
    return filter_by_release(
        query,
        start_col=start_col,
        end_col=end_col,
        release_id=release_id,
    )


def get_module_version_id(
    session: "Session", module_code: str, reference_date: str
) -> int:
    """Return the ``ModuleVID`` of ``module_code`` valid at a date.

    Args:
        session: SQLAlchemy session.
        module_code: Module code (e.g. ``"KRI"``).
        reference_date: Reference date, ``YYYY-MM-DD``.

    Returns:
        The module version ID.

    Raises:
        NotFound: If no module version, or more than one, matches.
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
    rows = query.all()
    if len(rows) != 1:
        raise NotFound(
            title="Module version not resolvable",
            description=(
                f"{len(rows)} module versions of {module_code!r} are valid "
                f"at {reference_date}; exactly one is required."
            ),
        )
    return int(rows[0][0])


def get_module_metadata(session: "Session", module_vid: int) -> Dict[str, Any]:
    """Return the module version's code, version, dates and start release.

    Args:
        session: SQLAlchemy session.
        module_vid: Module version ID.

    Returns:
        Dict with ``module_vid``, ``code``, ``version_number``,
        ``from_date``, ``to_date`` and ``start_release_id``.

    Raises:
        NotFound: If no ``ModuleVersion`` has that VID.
    """
    mv = (
        session.query(ModuleVersion)
        .filter(ModuleVersion.module_vid == module_vid)
        .first()
    )
    if mv is None:
        raise NotFound(
            title="Module version not found",
            description=f"No ModuleVersion with VID {module_vid}.",
        )
    return {
        "module_vid": module_vid,
        "code": mv.code,
        "version_number": mv.version_number or "1.0.0",
        "from_date": mv.from_reference_date,
        "to_date": mv.to_reference_date,
        "start_release_id": (
            int(mv.start_release_id)
            if mv.start_release_id is not None
            else None
        ),
    }


def get_release_info(
    session: "Session",
    release_id: Optional[int],
    publication_date: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Return the ``dpm_release`` block: release code and publication date.

    Args:
        session: SQLAlchemy session.
        release_id: Release the module version starts at, or ``None``.
        publication_date: Publication date to stamp; defaults to today.

    Returns:
        ``{"release": code | None, "publication_date": str}``.
    """
    pub_date = publication_date or str(date_cls.today())  # noqa: DTZ011
    release_code = None
    if release_id is not None:
        release = (
            session.query(Release)
            .filter(Release.release_id == release_id)
            .first()
        )
        release_code = release.code if release else None
    return {"release": release_code, "publication_date": pub_date}


def get_module_uri(
    session: "Session",
    module_vid: int,
    published_release_id: Optional[int] = None,
) -> tuple[str, str]:
    """Build a module version's EBA taxonomy URI.

    Args:
        session: SQLAlchemy session.
        module_vid: Module version ID.
        published_release_id: The release the export is keyed at. When
            the module version itself lives in a working release, the
            URI reports the newest published release at or before this
            one instead, and a warning is logged.

    Returns:
        ``(uri, framework_code)``.

    Raises:
        NotFound: If the module version has no framework/release info.
    """
    result = (
        session.query(
            ModuleVersion.code.label("module_code"),
            Framework.code.label("framework_code"),
            Release.code.label("release_code"),
            ModuleVersion.start_release_id.label("start_release_id"),
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
        raise NotFound(
            title="Module framework not found",
            description=(
                f"No Framework is reachable from module VID {module_vid}."
            ),
        )
    # The URI keys the whole exported document, so a missing part makes
    # the export unusable rather than merely incomplete.
    missing = [
        name
        for name in ("framework_code", "release_code", "module_code")
        if getattr(result, name) is None
    ]
    if missing:
        raise NotFound(
            title="Module URI not resolvable",
            description=(
                f"Module VID {module_vid} has no {', '.join(missing)}; "
                "the export is keyed by the module's taxonomy URI."
            ),
        )
    release_code = result.release_code
    if _is_working_release(session, result.start_release_id):
        # A working release is the draft dictionary, not something a
        # consumer can resolve, so the URI carries the newest published
        # release at or before the one the export is keyed at instead.
        substitute = get_published_release_code(session, published_release_id)
        if substitute is not None:
            logger.warning(
                "Module %s (VID %s) lives in working release %r; its URI "
                "reports published release %r instead. The exported "
                "tables and variables are still the working version's.",
                result.module_code,
                module_vid,
                release_code,
                substitute,
            )
            release_code = substitute

    uri = (
        f"{EBA_BASE_URI}{result.framework_code.lower()}/"
        f"{release_code}/mod/{result.module_code.lower()}"
    )
    return uri, result.framework_code


def get_published_release_code(
    session: "Session", release_id: Optional[int]
) -> Optional[str]:
    """Return the newest *published* release code at or before *release_id*.

    "Published" is dpmcore's own rule rather than anything read off the
    code: a release whose
    :func:`~dpmcore.orm.release_sort_order.compute_sort_order` is
    chronological. An undated or non-chronologically typed (working)
    release sorts as the latest and is skipped here.

    Args:
        session: SQLAlchemy session.
        release_id: The release the export is keyed at; ``None`` yields
            the newest published release outright.

    Returns:
        The release code, or ``None`` if no published release qualifies.
    """
    rows = session.query(
        Release.release_id, Release.code, Release.date, Release.type
    ).all()
    perpetual = compute_sort_order(None, None)
    orders = {
        row.release_id: compute_sort_order(row.date, row.type) for row in rows
    }
    ceiling = orders.get(release_id, perpetual) if release_id else perpetual
    published = [
        row
        for row in rows
        if orders[row.release_id] < perpetual
        and orders[row.release_id] <= ceiling
    ]
    if not published:
        return None
    newest = max(published, key=lambda row: orders[row.release_id])
    return cast(Optional[str], newest.code)


def _is_working_release(session: "Session", release_id: Optional[int]) -> bool:
    """Whether *release_id* names a working (unpublished) release."""
    if release_id is None:
        return False
    row = (
        session.query(Release.date, Release.type)
        .filter(Release.release_id == release_id)
        .first()
    )
    if row is None:
        return False
    return compute_sort_order(row.date, row.type) >= compute_sort_order(
        None, None
    )


def get_calculations(
    session: "Session", module_vid: int
) -> List[Dict[str, Any]]:
    """Return a module version's calculation expressions and codes.

    Mirrors the EBA ``drr_calculations`` view -- ``ModuleVersion`` join
    ``OperationOutput`` join ``OperationVersion``, live-release filtered
    -- and picks up ``Operation.code`` in the same query, so an
    expression and its operation code can never come from two different
    row sets. ``Operation`` is outer-joined: an ``OperationVersion``
    with no ``Operation`` still contributes its expression, with a
    ``None`` code.

    Args:
        session: SQLAlchemy session.
        module_vid: Module version ID.

    Returns:
        ``[{"operation_vid", "expression", "operation_code"}, ...]``.
    """
    query = (
        session.query(
            OperationVersion.operation_vid.label("operation_vid"),
            OperationVersion.expression.label("expression"),
            Operation.code.label("operation_code"),
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
        .outerjoin(
            Operation,
            Operation.operation_id == OperationVersion.operation_id,
        )
        .filter(ModuleVersion.module_vid == module_vid)
    )
    query = filter_live_only(
        query,
        ModuleVersion.start_release_id,
        ModuleVersion.end_release_id,
    )
    df = read_sql_with_connection(query.statement, session)
    return cast(List[Dict[str, Any]], df.to_dict(orient="records"))


def _integer_ids(values: Sequence[Any]) -> List[int]:
    """Distinct integer ids from *values*, dropping missing markers.

    A grey cell carries no variable, so a selection over one yields
    ``NaN`` where an id would be. Those are not datapoints and must not
    reach a query (or become the string ``"4711.0"`` in the output).
    """
    return sorted({int(value) for value in values if not pd.isna(value)})


def _data_types(
    session: "Session",
    id_column: Any,
    ids: Sequence[Any],
    release_id: Optional[int],
) -> Dict[str, str]:
    """Return ``{str(id): data_type_code}`` for ``id_column`` in ``ids``.

    Mirrors the EBA ``drr_data_types`` view (``VariableVersion`` join
    ``Property`` join ``DataType``), batched through
    :func:`~dpmcore.orm.query_utils.chunked_in` to stay under SQL
    Server's bound-parameter cap.
    """
    wanted = _integer_ids(ids)
    if not wanted:
        return {}
    query: Any = (
        session.query(
            id_column.label("key"),
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
    query = _release_window(
        query,
        VariableVersion.start_release_id,
        VariableVersion.end_release_id,
        release_id,
    )
    rows = chunked_in(query, id_column, wanted)
    return {str(row.key): row.data_type for row in rows}


def get_data_types(
    session: "Session",
    datapoints: Sequence[Any],
    release_id: Optional[int] = None,
) -> Dict[str, str]:
    """Return ``{str(VariableID): data_type_code}`` for datapoints.

    This is the *datapoint* id space: what a cell selection resolves to,
    and what the exported ``data`` arrays and the datapoint map are keyed
    by. Calculation variables named by code live in the ``VariableVID``
    space instead -- see :func:`get_data_types_by_version`.

    Args:
        session: SQLAlchemy session.
        datapoints: Variable IDs; entries that are not integers (a grey
            cell's ``NaN``) are dropped rather than raising.
        release_id: Release to resolve the data types at.

    Returns:
        Mapping of variable ID (as a string) to data-type code.
    """
    return _data_types(
        session, VariableVersion.variable_id, datapoints, release_id
    )


def get_data_types_by_version(
    session: "Session",
    variable_vids: Sequence[Any],
    release_id: Optional[int] = None,
) -> Dict[str, str]:
    """Return ``{str(VariableVID): data_type_code}`` for variable versions.

    The ``VariableVID`` counterpart of :func:`get_data_types`: a
    ``VarRef`` assignment target resolves to a version id, and so do the
    cells in ``output_tables`` (``TableVersionCell.VariableVID``).
    Looking those up by ``VariableID`` matches nothing, which is how a
    real data type silently becomes the ``"m"`` default.

    Args:
        session: SQLAlchemy session.
        variable_vids: Variable version IDs.
        release_id: Release to resolve the data types at.

    Returns:
        Mapping of variable version ID (as a string) to data-type code.
    """
    return _data_types(
        session, VariableVersion.variable_vid, variable_vids, release_id
    )


def get_output_variable_vids(
    session: "Session",
    variable_codes: Sequence[str],
    release_id: Optional[int] = None,
) -> Dict[str, int]:
    """Return ``{variable_code: VariableVID}`` for assignment targets.

    A ``VarRef`` left-hand side names a calculation variable by code;
    this resolves it to the ``VariableVID`` the output tables are keyed
    by. A code that matches no variable, or several, is skipped -- the
    export reports what it could resolve rather than failing.

    Args:
        session: SQLAlchemy session.
        variable_codes: Variable codes to resolve.
        release_id: Release to resolve at.

    Returns:
        Mapping of code to ``VariableVID``, omitting unresolved codes.
    """
    result: Dict[str, int] = {}
    for code in variable_codes:
        query: Any = session.query(VariableVersion).filter(
            VariableVersion.code == code
        )
        query = _release_window(
            query,
            VariableVersion.start_release_id,
            VariableVersion.end_release_id,
            release_id,
        )
        # .first(), not .one_or_none(): the latter raises on an
        # ambiguous code, which would abort the whole export with a
        # bare SQLAlchemy error the CLI does not catch.
        rows = query.limit(2).all()
        if len(rows) == 1:
            result[code] = int(rows[0].variable_vid)
    return result


def get_output_tables(
    session: "Session",
    module_vid: int,
    output_variable_vids: Sequence[int],
    release_id: Optional[int] = None,
) -> Dict[str, Dict[str, Dict[str, str]]]:
    """Return the module's tables holding the given output ``VariableVID``s.

    Args:
        session: SQLAlchemy session.
        module_vid: Module version ID.
        output_variable_vids: ``VariableVID``s the calculations write to.
        release_id: Release to resolve data types at.

    Returns:
        ``{table_code: {"variables": {variable_vid: data_type}}}``.
    """
    if not output_variable_vids:
        return {}

    composition_query = (
        session.query(
            ModuleVersionComposition.table_vid.label("table_vid"),
            TableVersion.code.label("table_code"),
        )
        .join(
            TableVersion,
            TableVersion.table_vid == ModuleVersionComposition.table_vid,
        )
        .filter(ModuleVersionComposition.module_vid == module_vid)
    )

    # Resolved once for the whole module: the per-table loop below would
    # otherwise repeat the same lookup for every composition row.
    data_types = get_data_types_by_version(
        session, output_variable_vids, release_id
    )

    output_tables: Dict[str, Dict[str, Dict[str, str]]] = {}
    for comp_row in composition_query.all():
        cell_query = session.query(TableVersionCell.variable_vid).filter(
            TableVersionCell.table_vid == comp_row.table_vid
        )
        # Batched: a wide calculations set can name more output
        # variables than SQL Server allows bound parameters.
        table_var_vids = [
            row.variable_vid
            for row in chunked_in(
                cell_query,
                TableVersionCell.variable_vid,
                output_variable_vids,
            )
        ]
        if table_var_vids:
            output_tables[comp_row.table_code] = {
                "variables": {
                    str(var_vid): data_types.get(str(var_vid), "m")
                    for var_vid in table_var_vids
                }
            }
    return output_tables


def group_tables_by_module(
    session: "Session",
    tables: Dict[str, Dict[str, Any]],
    release_id: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    """Group dependency tables under the module versions that contain them.

    Args:
        session: SQLAlchemy session.
        tables: ``{table_code: {"variables": {id: type}, "open_keys": …}}``
            as collected from the calculations' operands.
        release_id: Release to resolve the table and module versions at.

    Returns:
        ``{module_code: {module_vid, from_date, to_date, tables}}``,
        carrying each table's variables and open keys through unchanged.
    """
    module_tables: Dict[str, Dict[str, Any]] = {}

    for table_code, table_info in tables.items():
        table_query: Any = session.query(TableVersion.table_vid).filter(
            TableVersion.code == table_code
        )
        table_query = _release_window(
            table_query,
            TableVersion.start_release_id,
            TableVersion.end_release_id,
            release_id,
        )
        table_result = table_query.first()
        if not table_result:
            continue

        module_query: Any = (
            session.query(
                ModuleVersionComposition.module_vid.label("module_vid"),
                ModuleVersion.code.label("module_code"),
                ModuleVersion.from_reference_date.label("from_date"),
                ModuleVersion.to_reference_date.label("to_date"),
            )
            .join(
                ModuleVersion,
                ModuleVersion.module_vid
                == ModuleVersionComposition.module_vid,
            )
            .filter(ModuleVersionComposition.table_vid == table_result[0])
        )
        module_query = _release_window(
            module_query,
            ModuleVersion.start_release_id,
            ModuleVersion.end_release_id,
            release_id,
        )

        for row in module_query.all():
            entry = module_tables.setdefault(
                row.module_code,
                {
                    "module_vid": row.module_vid,
                    "from_date": row.from_date,
                    "to_date": row.to_date,
                    "tables": {},
                },
            )
            entry["tables"][table_code] = {
                # Already resolved by the caller; re-deriving them here
                # would throw the data types away.
                "variables": table_info["variables"],
                "open_keys": table_info.get("open_keys", {}),
            }

    return module_tables
