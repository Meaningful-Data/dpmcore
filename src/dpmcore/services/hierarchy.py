"""Hierarchy service — framework / module / table tree queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import and_, join
from sqlalchemy.orm import aliased

from dpmcore.dpm_xl.utils.filters import (
    filter_active_only,
    filter_by_date,
    filter_by_release,
    filter_item_version,
    resolve_release_id,
)
from dpmcore.orm.glossary import (
    ContextComposition,
    Item,
    ItemCategory,
)
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import (
    Cell,
    HeaderVersion,
    Table,
    TableVersion,
    TableVersionCell,
    TableVersionHeader,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _ensure_single_filter(
    release_id: Optional[int],
    date: Optional[str],
    release_code: Optional[str] = None,
) -> None:
    """Reject callers that pass more than one of the time filters."""
    given = sum(x is not None for x in (release_id, date, release_code))
    if given > 1:
        raise ValueError(
            "Specify a maximum of one of release_id, release_code or date.",
        )


def _apply_module_filter(
    query: Any,
    release_id: Optional[int],
    date: Optional[str],
    historical: bool = False,
) -> Any:
    """Apply the module-version filter shared by hierarchical queries.

    ``release_id`` must already be resolved (no ``release_code`` here);
    callers are expected to run ``resolve_release_id`` upstream so the
    filter helpers stay session-free.

    When no filter is supplied and ``historical`` is False (the
    default), the query is restricted to currently-active module
    versions (``end_release_id IS NULL``). Pass ``historical=True`` to
    skip that fallback and return every module version regardless of
    release window — useful for callers that want the full historical
    tree.

    Predicates are added as WHERE clauses, which is fine for inner-
    joined queries that just want to discard non-matching rows. For
    queries that LEFT OUTER JOIN ``ModuleVersion`` and need to keep
    parent rows (frameworks, modules) even when no module-version
    matches, use :func:`_filtered_module_version_alias` to push the
    filter into a subquery instead.
    """
    if date:
        return filter_by_date(
            query,
            date,
            start_col=ModuleVersion.from_reference_date,
            end_col=ModuleVersion.to_reference_date,
        )
    if release_id is not None:
        return filter_by_release(
            query,
            release_id=release_id,
            start_col=ModuleVersion.start_release_id,
            end_col=ModuleVersion.end_release_id,
        )
    if historical:
        return query
    return filter_active_only(query, ModuleVersion.end_release_id)


def _filtered_module_version_alias(
    session: "Session",
    release_id: Optional[int],
    date: Optional[str],
    historical: bool = False,
) -> Any:
    """Return a ``ModuleVersion`` alias backed by a filtered subquery.

    The returned alias acts like ``ModuleVersion`` (so callers can
    reference ``alias.module_vid`` etc.) but only contains rows that
    pass the requested filter. Outer-joining against this alias keeps
    parent rows (frameworks, modules) in the result even when no
    module-version matches, which a WHERE-style filter would silently
    drop.

    The filter semantics mirror :func:`_apply_module_filter`:
    ``date`` wins over ``release_id``, and when neither is supplied
    the result is restricted to active rows unless ``historical`` is
    True.
    """
    base = session.query(ModuleVersion)
    if date:
        base = filter_by_date(
            base,
            date,
            start_col=ModuleVersion.from_reference_date,
            end_col=ModuleVersion.to_reference_date,
        )
    elif release_id is not None:
        base = filter_by_release(
            base,
            release_id=release_id,
            start_col=ModuleVersion.start_release_id,
            end_col=ModuleVersion.end_release_id,
        )
    elif not historical:
        base = filter_active_only(base, ModuleVersion.end_release_id)
    return aliased(ModuleVersion, base.subquery())


class HierarchyService:
    """Hierarchical queries on the DPM structure.

    Args:
        session: An open SQLAlchemy session.
    """

    def __init__(self, session: "Session") -> None:
        """Build the service bound to ``session``."""
        self.session = session

    def get_all_frameworks(
        self,
        release_id: Optional[int] = None,
        date: Optional[str] = None,
        release_code: Optional[str] = None,
        deep: bool = False,
        historical: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return frameworks, optionally as a Framework→Module→Table tree.

        Args:
            release_id: Restrict module versions to a release.
            date: Restrict module versions valid at a date (YYYY-MM-DD).
            release_code: Restrict by release code (resolved to ID).
            deep: When True, nest ``module_versions`` and
                ``table_versions`` under each framework. When False
                (default), return flat ``Framework`` rows.
            historical: When True and no other filter is given, return
                every module version (no active-only fallback). Ignored
                when any of ``release_id`` / ``release_code`` / ``date``
                is supplied. Only meaningful with ``deep=True``.

        Returns:
            A list of framework dictionaries. With ``deep=True``, each
            framework contains ``module_versions`` (possibly empty when
            the framework has no module versions matching the filter),
            and each module version contains ``table_versions``
            (possibly empty for the same reason). Frameworks, modules,
            and tables are joined with LEFT OUTER JOIN so empty slots
            do not silently disappear from the tree. Filter predicates
            are pushed into a ``ModuleVersion`` subquery so they don't
            turn the outer joins into an inner filter.

        Raises:
            ValueError: If more than one of ``release_id``, ``date``,
                or ``release_code`` is given, or if ``release_code``
                does not match any release.
        """
        _ensure_single_filter(release_id, date, release_code)
        release_id = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )

        if not deep:
            return [r.to_dict() for r in self.session.query(Framework).all()]

        # Push the module-version filter into a subquery so the outer
        # joins below can preserve frameworks / modules that have no
        # matching module-versions — a WHERE-style filter on the
        # outer-joined ModuleVersion would silently drop them.
        mv = _filtered_module_version_alias(
            self.session, release_id, date, historical=historical
        )

        q = (
            self.session.query(
                Framework.framework_id.label("framework_id"),
                Framework.code.label("framework_code"),
                Framework.name.label("framework_name"),
                Framework.description.label("framework_description"),
                mv.module_vid.label("module_vid"),
                mv.module_id.label("module_id"),
                mv.start_release_id.label("mv_start_release_id"),
                mv.end_release_id.label("mv_end_release_id"),
                mv.code.label("module_code"),
                mv.name.label("module_name"),
                mv.description.label("module_description"),
                mv.version_number.label("module_version_number"),
                mv.from_reference_date.label("module_from_date"),
                mv.to_reference_date.label("module_to_date"),
                TableVersion.table_vid.label("table_vid"),
                TableVersion.code.label("table_version_code"),
                TableVersion.name.label("table_version_name"),
                TableVersion.description.label("table_version_description"),
                TableVersion.table_id.label("table_version_table_id"),
                TableVersion.abstract_table_id.label("abstract_table_id"),
                TableVersion.start_release_id.label("tv_start_release_id"),
                TableVersion.end_release_id.label("tv_end_release_id"),
                Table.is_abstract.label("is_abstract"),
                Table.has_open_columns.label("has_open_columns"),
                Table.has_open_rows.label("has_open_rows"),
                Table.has_open_sheets.label("has_open_sheets"),
                Table.is_normalised.label("is_normalised"),
                Table.is_flat.label("is_flat"),
            )
            # LEFT OUTER JOIN throughout so frameworks with no modules,
            # modules with no tables, etc. still appear in the result
            # tree (with empty lists at the missing level).
            .outerjoin(Module, Module.framework_id == Framework.framework_id)
            .outerjoin(mv, mv.module_id == Module.module_id)
            .outerjoin(
                ModuleVersionComposition,
                ModuleVersionComposition.module_vid == mv.module_vid,
            )
            .outerjoin(
                TableVersion,
                TableVersion.table_vid == ModuleVersionComposition.table_vid,
            )
            .outerjoin(Table, Table.table_id == TableVersion.table_id)
            .order_by(
                Framework.framework_id,
                mv.module_vid,
                TableVersion.table_vid,
            )
        )

        frameworks: Dict[int, Dict[str, Any]] = {}
        for row in q.all():
            fw = frameworks.setdefault(
                row.framework_id,
                {
                    "framework_id": row.framework_id,
                    "code": row.framework_code,
                    "name": row.framework_name,
                    "description": row.framework_description,
                    "module_versions": {},
                },
            )
            # Outer joins yield placeholder rows where module_vid /
            # table_vid are NULL — keep the framework / module entry
            # but don't synthesise empty children from them.
            if row.module_vid is None:
                continue
            mv = fw["module_versions"].setdefault(
                row.module_vid,
                {
                    "module_vid": row.module_vid,
                    "module_id": row.module_id,
                    "start_release_id": row.mv_start_release_id,
                    "end_release_id": row.mv_end_release_id,
                    "code": row.module_code,
                    "name": row.module_name,
                    "description": row.module_description,
                    "version_number": row.module_version_number,
                    "from_reference_date": row.module_from_date,
                    "to_reference_date": row.module_to_date,
                    "table_versions": [],
                },
            )
            if row.table_vid is None:
                continue
            mv["table_versions"].append(
                {
                    "table_vid": row.table_vid,
                    "code": row.table_version_code,
                    "name": row.table_version_name,
                    "description": row.table_version_description,
                    "table_id": row.table_version_table_id,
                    "abstract_table_id": row.abstract_table_id,
                    "start_release_id": row.tv_start_release_id,
                    "end_release_id": row.tv_end_release_id,
                    "is_abstract": row.is_abstract,
                    "has_open_columns": row.has_open_columns,
                    "has_open_rows": row.has_open_rows,
                    "has_open_sheets": row.has_open_sheets,
                    "is_normalised": row.is_normalised,
                    "is_flat": row.is_flat,
                }
            )

        result: List[Dict[str, Any]] = []
        for fw in frameworks.values():
            fw["module_versions"] = list(fw["module_versions"].values())
            result.append(fw)
        return result

    def get_module_version(
        self,
        module_code: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return module version info for a given module code.

        When neither ``release_id`` nor ``release_code`` is supplied,
        only the currently-active ``ModuleVersion`` (``end_release_id
        IS NULL``) is considered, so a module that has been republished
        across releases resolves deterministically.
        """
        release_id = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )

        # Order by Release.sort_order — start_release_id is no longer
        # monotonic post-4.2.1 (4.2.1 has ReleaseID 1010000003), so
        # picking the "most recent" via the raw FK would be wrong on
        # any DB that contains opaque IDs. LEFT JOIN so a missing or
        # unparseable Release does not drop the row entirely; a NULL
        # sort_order simply sorts last via ``nulls_last``.
        mv_start_release = aliased(Release)
        q = (
            self.session.query(ModuleVersion)
            .outerjoin(
                mv_start_release,
                mv_start_release.release_id == ModuleVersion.start_release_id,
            )
            .filter(ModuleVersion.code == module_code)
        )
        if release_id is not None:
            q = filter_by_release(
                q,
                release_id=release_id,
                start_col=ModuleVersion.start_release_id,
                end_col=ModuleVersion.end_release_id,
            )
        else:
            q = filter_active_only(q, ModuleVersion.end_release_id)
        row = q.order_by(
            mv_start_release.sort_order.desc().nulls_last()
        ).first()
        return row.to_dict() if row else None

    def get_table_details(
        self,
        table_code: str,
        release_id: Optional[int] = None,
        date: Optional[str] = None,
        release_code: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return table version with headers and cells.

        All three filters resolve through the same module-version join
        as :meth:`get_table_modelling`, so the two methods always pick
        the same ``TableVersion`` for a given query.

        Args:
            table_code: Table code to look up.
            release_id: Restrict to a specific release.
            date: Resolve via the module-version date range.
            release_code: Restrict by release code (resolved to ID).

        Returns:
            Table version dictionary with ``headers`` and ``cells``,
            or ``None`` if the table does not exist for the requested
            filters.

        Raises:
            ValueError: If more than one of ``release_id``, ``date``,
                or ``release_code`` is given, or if ``release_code``
                does not match any release.
        """
        _ensure_single_filter(release_id, date, release_code)
        release_id = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )

        tv = self._resolve_table_version(table_code, release_id, date)
        if tv is None:
            return None

        result = tv.to_dict()

        # Attach headers
        headers_q = (
            self.session.query(HeaderVersion)
            .join(
                TableVersionHeader,
                HeaderVersion.header_vid == TableVersionHeader.header_vid,
            )
            .filter(TableVersionHeader.table_vid == tv.table_vid)
        )
        result["headers"] = [h.to_dict() for h in headers_q.all()]

        # Attach cells
        cells_q = (
            self.session.query(Cell)
            .join(
                TableVersionCell,
                Cell.cell_id == TableVersionCell.cell_id,
            )
            .filter(TableVersionCell.table_vid == tv.table_vid)
        )
        result["cells"] = [c.to_dict() for c in cells_q.all()]

        return result

    def get_table_modelling(
        self,
        table_code: str,
        release_id: Optional[int] = None,
        date: Optional[str] = None,
        release_code: Optional[str] = None,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Return modelling metadata for a table keyed by header_id.

        For each header on the resolved table version, returns up to
        two entries:

        * ``{"main_property_code": ..., "main_property_name": ...}``
          when the header has a property assigned.
        * ``{"context_property_code": ..., "context_property_name": ...,
          "context_item_code": ..., "context_item_name": ...}`` when
          the header carries a context composition.

        Args:
            table_code: Table code to look up.
            release_id: Restrict to a specific release.
            date: Resolve via the module-version date range.
            release_code: Restrict by release code (resolved to ID).

        Returns:
            Mapping ``header_id`` → list of property/context entries.
            Every header that appears on the resolved table version is
            present in the mapping, including ones with no joined
            metadata — those map to an empty list rather than being
            omitted. The mapping is empty only when the table has no
            headers at all. Raises if the table itself cannot be
            resolved.

        Raises:
            ValueError: If more than one of ``release_id``, ``date``,
                or ``release_code`` is given, if ``release_code`` does
                not match any release, or if no table version matches
                the filters.
        """
        _ensure_single_filter(release_id, date, release_code)
        release_id = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )

        tv = self._resolve_table_version(table_code, release_id, date)
        if tv is None:
            raise ValueError(f"Table {table_code} was not found.")

        # Resolve the reference release's sort_order once at Python
        # time so the per-row ItemCategory range comparisons emit just
        # one correlated subquery per item-side column instead of
        # three. ``filter_item_version`` accepts ``None`` (unparseable
        # code) and produces a NULL-comparing clause that never matches.
        #
        # Items/categories are versioned independently of TableVersion,
        # so when the caller asks for a specific release we evaluate
        # item membership at *that* release rather than at the table
        # version's start. Without a release filter (date-only or no
        # filter), fall back to the table version's start release as
        # the anchor.
        ref_release_id = (
            release_id if release_id is not None else tv.start_release_id
        )
        ref_sort_order = (
            self.session.query(Release.sort_order)
            .filter(Release.release_id == ref_release_id)
            .scalar()
        )

        iccp = aliased(ItemCategory)
        icci = aliased(ItemCategory)
        icmp = aliased(ItemCategory)
        icp = aliased(Item)
        ici = aliased(Item)
        mpi = aliased(Item)

        context_property_join = join(iccp, icp, iccp.item_id == icp.item_id)
        context_item_join = join(icci, ici, icci.item_id == ici.item_id)
        main_property_join = join(icmp, mpi, icmp.item_id == mpi.item_id)

        q = (
            self.session.query(
                HeaderVersion.header_id.label("header_id"),
                icmp.signature.label("main_property_code"),
                mpi.name.label("main_property_name"),
                iccp.signature.label("context_property_code"),
                icp.name.label("context_property_name"),
                icci.signature.label("context_item_code"),
                ici.name.label("context_item_name"),
            )
            .select_from(TableVersion)
            .join(
                TableVersionHeader,
                TableVersionHeader.table_vid == TableVersion.table_vid,
            )
            .join(
                HeaderVersion,
                TableVersionHeader.header_vid == HeaderVersion.header_vid,
            )
            .outerjoin(
                ContextComposition,
                HeaderVersion.context_id == ContextComposition.context_id,
            )
            .outerjoin(
                context_property_join,
                and_(
                    ContextComposition.property_id == iccp.item_id,
                    filter_item_version(
                        ref_sort_order,
                        iccp.start_release_id,
                        iccp.end_release_id,
                    ),
                ),
            )
            .outerjoin(
                context_item_join,
                and_(
                    ContextComposition.item_id == icci.item_id,
                    filter_item_version(
                        ref_sort_order,
                        icci.start_release_id,
                        icci.end_release_id,
                    ),
                ),
            )
            .outerjoin(
                main_property_join,
                and_(
                    HeaderVersion.property_id == icmp.item_id,
                    filter_item_version(
                        ref_sort_order,
                        icmp.start_release_id,
                        icmp.end_release_id,
                    ),
                ),
            )
            .filter(TableVersion.table_vid == tv.table_vid)
        )

        modelling: Dict[int, List[Dict[str, Any]]] = {}
        for row in q.all():
            entries = modelling.setdefault(row.header_id, [])
            if (
                row.main_property_code is not None
                or row.main_property_name is not None
            ):
                entries.append(
                    {
                        "main_property_code": row.main_property_code,
                        "main_property_name": row.main_property_name,
                    }
                )
            if (
                row.context_property_code is not None
                or row.context_property_name is not None
                or row.context_item_code is not None
                or row.context_item_name is not None
            ):
                entries.append(
                    {
                        "context_property_code": row.context_property_code,
                        "context_property_name": row.context_property_name,
                        "context_item_code": row.context_item_code,
                        "context_item_name": row.context_item_name,
                    }
                )

        return modelling

    def get_tables_for_module(
        self,
        module_code: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return all tables belonging to a module."""
        release_id = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )

        q = (
            self.session.query(TableVersion)
            .join(
                ModuleVersionComposition,
                TableVersion.table_vid == ModuleVersionComposition.table_vid,
            )
            .join(
                ModuleVersion,
                ModuleVersionComposition.module_vid
                == ModuleVersion.module_vid,
            )
            .filter(ModuleVersion.code == module_code)
        )
        if release_id is not None:
            q = filter_by_release(
                q,
                release_id=release_id,
                start_col=ModuleVersion.start_release_id,
                end_col=ModuleVersion.end_release_id,
            )
        return [r.to_dict() for r in q.all()]

    def _resolve_table_version(
        self,
        table_code: str,
        release_id: Optional[int],
        date: Optional[str],
    ) -> Optional[TableVersion]:
        """Pick the TableVersion matching ``table_code`` under filters.

        Joins through ModuleVersionComposition + ModuleVersion so that
        the date filter (which is tracked on ModuleVersion) applies
        consistently. Falls back to the most recent module-version
        match when several rows survive the filter.

        "Most recent" is decided by ``Release.sort_order`` because the
        raw ``start_release_id`` FK is no longer monotonic post-4.2.1
        (4.2.1 has ``ReleaseID = 1010000003``). LEFT JOIN so a missing
        or unparseable Release does not drop the row; a NULL
        sort_order simply sorts last via ``nulls_last``.
        """
        mv_start_release = aliased(Release)
        q = (
            self.session.query(TableVersion)
            .join(
                ModuleVersionComposition,
                ModuleVersionComposition.table_vid == TableVersion.table_vid,
            )
            .join(
                ModuleVersion,
                ModuleVersion.module_vid
                == ModuleVersionComposition.module_vid,
            )
            .outerjoin(
                mv_start_release,
                mv_start_release.release_id == ModuleVersion.start_release_id,
            )
            .filter(TableVersion.code == table_code)
        )
        q = _apply_module_filter(q, release_id, date)
        return q.order_by(
            mv_start_release.sort_order.desc().nulls_last()
        ).first()
