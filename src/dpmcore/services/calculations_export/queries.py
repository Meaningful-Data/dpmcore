"""Database queries behind the calculations export.

Everything the export needs that is not already a dpmcore query: the
``OperationOutput`` join that yields a module's calculations,
per-datapoint data types and the output tables.

The EBA ``drr_operations`` pipeline these mirror compares release IDs
numerically and spells its perpetual release ``9999``. Neither holds in
dpmcore -- ``ReleaseID`` became opaque at DPM 4.2.1 and the perpetual
release is identified by
:func:`~dpmcore.orm.release_sort_order.compute_sort_order` -- so every
release window here goes through :func:`release_window`.
"""

from __future__ import annotations

from datetime import date as date_cls
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    cast,
)

import pandas as pd

from dpmcore.dpm_xl.model_queries import read_sql_with_connection
from dpmcore.dpm_xl.utils.filters import filter_by_date
from dpmcore.errors import Invalid, NotFound
from dpmcore.orm.glossary import Property
from dpmcore.orm.infrastructure import DataType, Organisation, Release
from dpmcore.orm.operations import (
    Operation,
    OperationOutput,
    OperationVersion,
)
from dpmcore.orm.packaging import (
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.query_utils import chunked_in
from dpmcore.orm.rendering import TableVersion, TableVersionCell
from dpmcore.orm.variables import VariableVersion
from dpmcore.services.script_document.queries import release_window

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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
