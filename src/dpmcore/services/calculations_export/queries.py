"""Database queries behind the calculations export.

Everything the export needs that is not already a dpmcore query: the
``OperationOutput`` join that yields a module's calculations, the module
metadata and EBA taxonomy URI, per-datapoint data types, the output
tables, and the module versions holding each table read.

The EBA ``drr_operations`` pipeline these mirror compares release IDs
numerically and spells its perpetual release ``9999``. Neither holds in
dpmcore -- ``ReleaseID`` became opaque at DPM 4.2.1 and the perpetual
release is identified by
:func:`~dpmcore.orm.release_sort_order.compute_sort_order` -- so every
release window here goes through :func:`release_window`.
"""

from __future__ import annotations

import logging
from datetime import date as date_cls
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    cast,
)

import pandas as pd

from dpmcore.data import get_module_schema_ref_by_version
from dpmcore.dpm_xl.model_queries import read_sql_with_connection
from dpmcore.dpm_xl.utils.filters import (
    filter_by_date,
    filter_by_release,
    filter_live_only,
)
from dpmcore.errors import Invalid, NotFound
from dpmcore.orm.glossary import Property
from dpmcore.orm.infrastructure import DataType, Organisation, Release
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


def release_window(
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
        NotFound: If no module version matches.
        Invalid: If more than one does -- the reference date does not
            identify a single module version to export.
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
    if not rows:
        raise NotFound(
            title="Module version not found",
            description=(
                f"No module version of {module_code!r} is valid at "
                f"{reference_date}."
            ),
        )
    if len(rows) > 1:
        raise Invalid(
            title="Module version not resolvable",
            description=(
                f"{len(rows)} module versions of {module_code!r} are valid "
                f"at {reference_date}; exactly one is required."
            ),
        )
    return int(rows[0][0])


def get_module_metadata(session: "Session", module_vid: int) -> Dict[str, Any]:
    """Return the module version's identity, dates, release and owner.

    Args:
        session: SQLAlchemy session.
        module_vid: Module version ID.

    Returns:
        Dict with ``module_vid``, ``module_id``, ``code``,
        ``version_number``, ``from_date``, ``to_date``,
        ``start_release_id``, ``end_release_id`` and ``module_owner``
        (the acronym of the organisation owning the module, ``None``
        when it has none).

    Raises:
        NotFound: If no ``ModuleVersion`` has that VID.
    """
    row = (
        session.query(ModuleVersion, Organisation.acronym)
        .outerjoin(Module, Module.module_id == ModuleVersion.module_id)
        .outerjoin(Organisation, Organisation.org_id == Module.owner_id)
        .filter(ModuleVersion.module_vid == module_vid)
        .first()
    )
    if row is None:
        raise NotFound(
            title="Module version not found",
            description=f"No ModuleVersion with VID {module_vid}.",
        )
    mv, module_owner = row
    return {
        "module_vid": module_vid,
        "module_id": mv.module_id,
        "code": mv.code,
        "version_number": mv.version_number or "1.0.0",
        "from_date": mv.from_reference_date,
        "to_date": mv.to_reference_date,
        "start_release_id": (
            int(mv.start_release_id)
            if mv.start_release_id is not None
            else None
        ),
        "end_release_id": (
            int(mv.end_release_id) if mv.end_release_id is not None else None
        ),
        "module_owner": module_owner,
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
) -> tuple[str, str]:
    """Build a module version's EBA taxonomy URI.

    Versions published before 4.0 use their published schema reference
    (``get_module_schema_ref_by_version``), later ones are built from
    the framework, release and module codes.

    The release code is reported verbatim, a working release included:
    the reference export keys its dependency modules at ``Playground``
    and the consumer looks them up by URI, so rewriting one to the
    newest published release would silently repoint it. A working
    release is logged as a warning instead.

    Args:
        session: SQLAlchemy session.
        module_vid: Module version ID.

    Returns:
        ``(uri, framework_code)``.

    Raises:
        NotFound: If the module version has no framework/release info.
    """
    result = (
        session.query(
            ModuleVersion.code.label("module_code"),
            ModuleVersion.version_number.label("version_number"),
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
    published = _published_module_uri(
        result.module_code, result.version_number
    )
    if published is not None and result.framework_code is not None:
        return published, result.framework_code
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
        logger.warning(
            "Module %s (VID %s) lives in working release %r; its URI "
            "carries that code. A consumer resolving the URI against a "
            "published taxonomy will not find it.",
            result.module_code,
            module_vid,
            release_code,
        )

    uri = (
        f"{EBA_BASE_URI}{result.framework_code.lower()}/"
        f"{release_code}/mod/{result.module_code.lower()}"
    )
    return uri, result.framework_code


def _published_module_uri(
    module_code: Optional[str], version_number: Optional[str]
) -> Optional[str]:
    """Published URI of a pre-4.0 module version, if any."""
    if not module_code or not version_number:
        return None
    schema_ref = get_module_schema_ref_by_version(module_code, version_number)
    if schema_ref is None:
        return None
    return schema_ref.removesuffix(".json")


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
    session: "Session",
    module_vid: int,
    release_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return a module version's calculation expressions and codes.

    Mirrors the EBA ``drr_calculations`` view -- ``ModuleVersion`` join
    ``OperationOutput`` join ``OperationVersion`` -- and picks up
    ``Operation.code`` in the same query, so an expression and its
    operation code can never come from two different row sets.
    ``Operation`` is outer-joined: an ``OperationVersion`` with no
    ``Operation`` still contributes its expression, with a ``None``
    code.

    Only the *operation* version is release-windowed. ``module_vid``
    already pins the module version the caller resolved by reference
    date, so re-gating it here could only ever turn that one row into
    none -- which is what it did for a module version living in a
    working release, the case the export deliberately supports.

    Args:
        session: SQLAlchemy session.
        module_vid: Module version ID.
        release_id: Release to window the operation versions at;
            ``None`` selects the live ones. Without it a superseded
            operation version is returned beside its successor, and the
            two assign the same output.

    Returns:
        ``[{"operation_vid", "expression", "operation_code", "owner"},
        ...]``, ordered by ``OperationVID``; ``owner`` is the acronym of
        the organisation owning the operation, or ``None``.
    """
    query: Any = (
        session.query(
            OperationVersion.operation_vid.label("operation_vid"),
            OperationVersion.expression.label("expression"),
            Operation.code.label("operation_code"),
            Organisation.acronym.label("owner"),
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
        .outerjoin(Organisation, Organisation.org_id == Operation.owner_id)
        .filter(ModuleVersion.module_vid == module_vid)
    )
    query = release_window(
        query,
        OperationVersion.start_release_id,
        OperationVersion.end_release_id,
        release_id,
    )
    # Ordered explicitly: the row order decides the script's statement
    # order, the positional operation-code pairing and the dependency
    # sort's tie-break, and an unordered join is free to return the same
    # rows differently on every run -- which a byte-parity check against
    # the reference export cannot tolerate.
    query = query.order_by(OperationVersion.operation_vid)
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
    query = release_window(
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
    wanted = list(dict.fromkeys(code for code in variable_codes if code))
    if not wanted:
        return {}
    query: Any = session.query(
        VariableVersion.code.label("code"),
        VariableVersion.variable_vid.label("variable_vid"),
    )
    query = release_window(
        query,
        VariableVersion.start_release_id,
        VariableVersion.end_release_id,
        release_id,
    )
    # One batched query, not one per code: a wide calculations set names
    # enough output variables for the per-code loop to dominate the
    # export against a remote SQL Server.
    resolved: Dict[str, Optional[int]] = {}
    for row in chunked_in(query, VariableVersion.code, wanted):
        if row.code in resolved:
            # Ambiguous: recorded as unresolved rather than raising, so
            # one bad code does not abort the whole export.
            resolved[row.code] = None
        else:
            resolved[row.code] = int(row.variable_vid)
    return {
        code: vid for code in wanted if (vid := resolved.get(code)) is not None
    }


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


def to_date(value: Any) -> Optional[date_cls]:
    """Normalise a DB date (date, datetime or ``YYYY-MM-DD`` text)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_cls):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()  # noqa: DTZ007


def windowed_table_vids(
    session: "Session",
    table_codes: Sequence[str],
    release_id: Optional[int],
) -> Dict[str, int]:
    """Resolve each table code to one ``TableVID`` at ``release_id``.

    One batched query in place of one per table.

    A release window can only match two versions of one code if their
    windows overlap, which the dictionary should not contain. The lowest
    ``TableVID`` wins so the export is at least reproducible -- the
    per-table ``.first()`` this replaces had no ``ORDER BY`` at all --
    and the ambiguity is logged rather than resolved silently.

    Args:
        session: SQLAlchemy session.
        table_codes: The table codes to resolve.
        release_id: Release to window the table versions at.

    Returns:
        ``{table_code: table_vid}``, omitting codes with no version in
        the window.
    """
    query: Any = session.query(
        TableVersion.code.label("code"),
        TableVersion.table_vid.label("table_vid"),
    )
    query = release_window(
        query,
        TableVersion.start_release_id,
        TableVersion.end_release_id,
        release_id,
    )
    resolved: Dict[str, int] = {}
    ambiguous: Set[str] = set()
    for row in chunked_in(query, TableVersion.code, list(table_codes)):
        table_vid = int(row.table_vid)
        current = resolved.get(row.code)
        if current is None:
            resolved[row.code] = table_vid
            continue
        ambiguous.add(row.code)
        resolved[row.code] = min(current, table_vid)
    if ambiguous:
        logger.warning(
            "%s table(s) read have overlapping versions at the "
            "export's release, the lowest TableVID is used: %s",
            len(ambiguous),
            ", ".join(sorted(ambiguous)),
        )
    return resolved


def modules_of_table_vids(
    session: "Session",
    table_vids: "set[int]",
    release_id: Optional[int],
) -> Dict[int, List[Any]]:
    """Return the module versions holding each of ``table_vids``.

    Args:
        session: SQLAlchemy session.
        table_vids: The table versions to look up.
        release_id: Release to window the module versions at.

    Returns:
        ``{table_vid: [row, ...]}`` where each row carries
        ``module_vid``, ``module_id`` and ``module_code``.
    """
    query: Any = (
        session.query(
            ModuleVersionComposition.table_vid.label("table_vid"),
            ModuleVersionComposition.module_vid.label("module_vid"),
            ModuleVersion.module_id.label("module_id"),
            ModuleVersion.code.label("module_code"),
        )
        .join(
            ModuleVersion,
            ModuleVersion.module_vid == ModuleVersionComposition.module_vid,
        )
        .order_by(ModuleVersionComposition.module_vid)
    )
    query = release_window(
        query,
        ModuleVersion.start_release_id,
        ModuleVersion.end_release_id,
        release_id,
    )
    # The ORDER BY is safe under chunking: the batches partition
    # ``table_vids``, so every row of one table version lands in a
    # single batch and stays ordered within its group.
    grouped: Dict[int, List[Any]] = {}
    for row in chunked_in(
        query, ModuleVersionComposition.table_vid, sorted(table_vids)
    ):
        grouped.setdefault(int(row.table_vid), []).append(row)
    return grouped
