"""Database queries behind the ``modules`` section (Script Format 2.0).

The module metadata and taxonomy URI of a module version, the table
versions read at a release, and the module versions holding each table
read. Shared by every document that writes ``modules``.

Release IDs became opaque at DPM 4.2.1 and the perpetual release is
identified by :func:`~dpmcore.orm.release_sort_order.compute_sort_order`,
so every release window here goes through :func:`release_window`.
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
)

from dpmcore.data import get_module_schema_ref_by_version
from dpmcore.dpm_xl.utils.filters import filter_by_release, filter_live_only
from dpmcore.errors import NotFound
from dpmcore.orm.infrastructure import Organisation, Release
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.query_utils import chunked_in
from dpmcore.orm.release_sort_order import compute_sort_order
from dpmcore.orm.rendering import TableVersion

if TYPE_CHECKING:
    from sqlalchemy.orm import Query, Session

logger = logging.getLogger(__name__)

EBA_BASE_URI = "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/"
"""Namespace prefix of the EBA taxonomy URIs the export names."""


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


def get_module_uri(
    session: "Session",
    module_vid: int,
) -> tuple[str, str]:
    """Build a module version's EBA taxonomy URI.

    Versions published before 4.0 use their published schema reference
    (``get_module_schema_ref_by_version``), later ones are built from
    the framework, release and module codes.

    The release code is reported verbatim, a working release included:
    a consumer matches an instance by its module URI, so rewriting one
    to the newest published release would silently repoint it. A
    working release is logged as a warning instead.

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
    # The URI names the exported module version, so a missing part makes
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
                "the export names the module's taxonomy URI."
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
