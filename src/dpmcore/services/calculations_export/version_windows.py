"""``version_windows`` of the calculations export.

A dependency module read at another reference period lists its whole
version chain, oldest first and ending with the current version, each
with its validity and only the tables that differ from the dependency's
declaration. A ``VariableID`` absent from every listed table is not
available in that version.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)

from dpmcore.orm.glossary import ItemCategory, Property
from dpmcore.orm.infrastructure import DataType
from dpmcore.orm.packaging import ModuleVersion, ModuleVersionComposition
from dpmcore.orm.release_sort_order import (
    compute_sort_order,
    load_release_sort_orders,
    release_ids_for_sort_order,
)
from dpmcore.orm.rendering import TableVersion, TableVersionCell
from dpmcore.orm.variables import KeyComposition, VariableVersion
from dpmcore.services.calculations_export.queries import (
    get_module_uri,
    release_window,
    to_date,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ONE_DAY = timedelta(days=1)


def _is_ghost_version(
    from_date: Optional[date], to_date: Optional[date]
) -> bool:
    """Whether a version never applied (one day or inverted window)."""
    return (
        from_date is not None and to_date is not None and to_date <= from_date
    )


def older_module_versions(
    candidates: List[Dict[str, Any]],
    current_from: date,
    sort_orders: Dict[int, int],
) -> List[Dict[str, Any]]:
    """Versions of the same Module applicable before ``current_from``.

    Skips ghost and Playground versions; on a shared start date, the one
    from the latest release wins.

    Args:
        candidates: Dicts with ``from_date``, ``to_date`` and
            ``start_release_id``.
        current_from: First reference date of the current version.
        sort_orders: ``{release_id: sort_order}``.

    Returns:
        The eligible versions, latest first.
    """
    draft_ids = set(
        release_ids_for_sort_order(
            sort_orders, ge=compute_sort_order(None, None)
        )
    )
    eligible = [
        c
        for c in candidates
        if c.get("from_date") is not None
        and c["from_date"] < current_from
        and not _is_ghost_version(c["from_date"], c.get("to_date"))
        and c.get("start_release_id") not in draft_ids
    ]

    def release_rank(candidate: Dict[str, Any]) -> int:
        return sort_orders.get(candidate.get("start_release_id") or -1, -1)

    by_start: Dict[date, Dict[str, Any]] = {}
    for c in eligible:
        best = by_start.get(c["from_date"])
        if best is None or release_rank(c) > release_rank(best):
            by_start[c["from_date"]] = c
    return [by_start[k] for k in sorted(by_start, reverse=True)]


def older_windows(
    older: List[Dict[str, Any]], current_from: date
) -> List[Tuple[Dict[str, Any], date, date]]:
    """Window of each older version, cut before its successor starts.

    Args:
        older: ``older_module_versions``, latest first.
        current_from: First reference date of the current version.

    Returns:
        ``[(version, start, end), ...]``, oldest first.
    """
    result: List[Tuple[Dict[str, Any], date, date]] = []
    next_start = current_from
    for version in older:  # latest first
        end = next_start - ONE_DAY
        if version.get("to_date") is not None and version["to_date"] < end:
            end = version["to_date"]
        start = version["from_date"]
        if start <= end:
            result.append((version, start, end))
        next_start = start
    result.reverse()
    return result


def current_window(
    current_from: date, current_to: Optional[date]
) -> Tuple[date, Optional[date]]:
    """Window of the current version, an inverted end counts as open."""
    if current_to is not None and current_to < current_from:
        current_to = None
    return current_from, current_to


def get_module_version_chain(
    session: "Session", module_vid: int
) -> List[Dict[str, Any]]:
    """Return the other versions of ``module_vid``'s Module.

    Not release-filtered: superseded versions are closed, yet they are
    the ones the earlier data was reported under.

    Args:
        session: SQLAlchemy session.
        module_vid: The current module version.

    Returns:
        ``[{module_vid, code, version_number, from_date, to_date,
        start_release_id}, ...]``.
    """
    module_id = (
        session.query(ModuleVersion.module_id)
        .filter(ModuleVersion.module_vid == int(module_vid))
        .scalar()
    )
    if module_id is None:
        return []
    rows = (
        session.query(
            ModuleVersion.module_vid,
            ModuleVersion.code,
            ModuleVersion.version_number,
            ModuleVersion.from_reference_date,
            ModuleVersion.to_reference_date,
            ModuleVersion.start_release_id,
        )
        .filter(
            ModuleVersion.module_id == module_id,
            ModuleVersion.module_vid != int(module_vid),
        )
        .order_by(ModuleVersion.module_vid)
        .all()
    )
    return [
        {
            "module_vid": int(row.module_vid),
            "code": row.code,
            "version_number": row.version_number,
            "from_date": to_date(row.from_reference_date),
            "to_date": to_date(row.to_reference_date),
            "start_release_id": (
                int(row.start_release_id)
                if row.start_release_id is not None
                else None
            ),
        }
        for row in rows
    ]


def get_open_keys_by_table_vid(
    session: "Session", table_vid: int, release_id: Optional[int] = None
) -> Dict[str, str]:
    """Open key components of a table version, ``{property_code: type}``.

    Codes are taken as of ``release_id`` (live when ``None``), since a
    key property can be renamed across releases. Read from the key
    composition because the key-components view only covers current
    table versions.
    """
    query: Any = (
        session.query(
            ItemCategory.code.label("property_code"),
            DataType.code.label("data_type"),
        )
        .select_from(TableVersion)
        .join(KeyComposition, KeyComposition.key_id == TableVersion.key_id)
        .join(
            VariableVersion,
            VariableVersion.variable_vid == KeyComposition.variable_vid,
        )
        .join(
            ItemCategory, ItemCategory.item_id == VariableVersion.property_id
        )
        .outerjoin(
            Property, Property.property_id == VariableVersion.property_id
        )
        .outerjoin(DataType, DataType.data_type_id == Property.data_type_id)
        .filter(TableVersion.table_vid == int(table_vid))
    )
    query = release_window(
        query,
        ItemCategory.start_release_id,
        ItemCategory.end_release_id,
        release_id,
    )
    rows = query.distinct().order_by(ItemCategory.code).all()
    return {row.property_code: row.data_type for row in rows}


def get_variable_tables(
    session: "Session", module_vid: int
) -> Dict[int, Dict[int, str]]:
    """Where each Variable is defined in Module Version ``module_vid``.

    Returns:
        ``{VariableID: {TableVID: table code}}`` over the non-void cells
        of every table of the module version.
    """
    rows = (
        session.query(
            VariableVersion.variable_id,
            TableVersion.table_vid,
            TableVersion.code,
        )
        .select_from(ModuleVersionComposition)
        .join(
            TableVersion,
            TableVersion.table_vid == ModuleVersionComposition.table_vid,
        )
        .join(
            TableVersionCell,
            TableVersionCell.table_vid == TableVersion.table_vid,
        )
        .join(
            VariableVersion,
            VariableVersion.variable_vid == TableVersionCell.variable_vid,
        )
        .filter(
            ModuleVersionComposition.module_vid == int(module_vid),
            TableVersionCell.is_void == False,  # noqa: E712
        )
        .distinct()
        .all()
    )
    holders: Dict[int, Dict[int, str]] = {}
    for row in rows:
        holders.setdefault(int(row.variable_id), {})[int(row.table_vid)] = (
            row.code
        )
    return holders


def resolve_shifted_reads(
    session: "Session",
    version: Dict[str, Any],
    shifted_ids: Dict[str, Set[str]],
    parent_tables: Dict[str, Dict[str, Any]],
    release_id: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    """Tables that differ from the declaration when read in ``version``.

    A shifted cell is matched by ``VariableID`` in tables with the same
    open keys: it stayed (same table code), moved (other tables) or is
    unavailable. Read tables with moved or unavailable cells are listed
    with what they still hold; tables receiving moved cells are listed
    with those.

    Args:
        session: SQLAlchemy session.
        version: The Module Version to resolve in (``module_vid``,
            ``code`` and ``version_number``).
        shifted_ids: ``{table code: {VariableID as text}}`` the
            calculations read at another period.
        parent_tables: The dependency's declared tables.
        release_id: Release whose key codes apply; ``None`` for live.

    Returns:
        ``{table code: {"variables": {id: type}, "open_keys": {...}}}``.
    """
    holders = get_variable_tables(session, version["module_vid"])
    keys_by_vid: Dict[int, Dict[str, str]] = {}

    def table_keys(table_vid: int) -> Dict[str, str]:
        if table_vid not in keys_by_vid:
            keys_by_vid[table_vid] = get_open_keys_by_table_vid(
                session, table_vid, release_id
            )
        return keys_by_vid[table_vid]

    types: Dict[str, str] = {
        variable_id: data_type
        for table in parent_tables.values()
        for variable_id, data_type in table.get("variables", {}).items()
    }

    stayed: Dict[str, Set[str]] = {}
    moved: Dict[str, Tuple[int, Set[str]]] = {}
    for table_code, ids in shifted_ids.items():
        parent_keys = set(
            parent_tables.get(table_code, {}).get("open_keys") or {}
        )
        stayed[table_code] = set()
        for variable_id in ids:
            holding = {
                table_vid: code
                for table_vid, code in holders.get(
                    int(variable_id), {}
                ).items()
                if set(table_keys(table_vid)) == parent_keys
            }
            if table_code in holding.values():
                stayed[table_code].add(variable_id)
                continue
            for table_vid, code in holding.items():
                moved.setdefault(code, (table_vid, set()))[1].add(variable_id)
        unavailable = (
            ids
            - stayed[table_code]
            - {v for _, m in moved.values() for v in m}
        )
        if unavailable:
            logger.info(
                "%s %s does not define %s of %s",
                version.get("code"),
                version.get("version_number"),
                sorted(unavailable, key=int),
                table_code,
            )

    listed = [code for code, ids in shifted_ids.items() if stayed[code] != ids]
    listed += sorted(code for code in moved if code not in listed)
    tables: Dict[str, Dict[str, Any]] = {}
    for code in listed:
        variables = set(stayed.get(code, set()))
        if code in moved:
            variables |= moved[code][1]
        open_keys = (
            dict(parent_tables.get(code, {}).get("open_keys") or {})
            if code in shifted_ids
            else table_keys(moved[code][0])
        )
        tables[code] = {
            "variables": {
                v: types.get(v, "m") for v in sorted(variables, key=int)
            },
            "open_keys": open_keys,
        }
    return tables


def _window_entry(
    uri: str,
    version_number: Optional[str],
    start: date,
    end: Optional[date],
    tables: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """One ``version_windows`` entry (open end serialised as ``null``)."""
    return {
        "URI": uri,
        "module_version": version_number,
        "from_reference_date": str(start),
        "to_reference_date": str(end) if end is not None else None,
        "tables": tables,
    }


def build_version_windows(
    session: "Session",
    dep_info: Dict[str, Any],
    current_uri: str,
    shifted_ids: Dict[str, Set[str]],
) -> List[Dict[str, Any]]:
    """Build ``version_windows`` for one dependency module.

    Older versions first, then the current one under the dependency's
    URI. Empty ``tables`` means nothing differs from the declaration.

    Args:
        session: SQLAlchemy session.
        dep_info: One value of ``group_tables_by_module``.
        current_uri: The dependency's URI.
        shifted_ids: ``{table code: {VariableID}}`` read at another
            period on the dependency's tables.

    Returns:
        The entries; empty when the dependency has no start date.
    """
    current_from = to_date(dep_info.get("from_date"))
    if current_from is None or not shifted_ids:
        return []

    sort_orders = load_release_sort_orders(session)
    older = older_module_versions(
        get_module_version_chain(session, dep_info["module_vid"]),
        current_from,
        sort_orders,
    )

    entries: List[Dict[str, Any]] = []
    for version, start, end in older_windows(older, current_from):
        tables = resolve_shifted_reads(
            session,
            version,
            shifted_ids,
            dep_info["tables"],
            release_id=version.get("start_release_id"),
        )
        uri, _ = get_module_uri(session, version["module_vid"])
        if uri == current_uri:
            logger.warning(
                "%s %s resolves to the same URI as its successor (%s); "
                "skipped",
                version.get("code"),
                version.get("version_number"),
                current_uri,
            )
            continue
        entries.append(
            _window_entry(
                uri, version.get("version_number"), start, end, tables
            )
        )

    current_start, current_end = current_window(
        current_from, to_date(dep_info.get("to_date"))
    )
    tables = resolve_shifted_reads(
        session, dep_info, shifted_ids, dep_info["tables"]
    )
    entries.append(
        _window_entry(
            current_uri,
            dep_info.get("version_number"),
            current_start,
            current_end,
            tables,
        )
    )
    return entries
