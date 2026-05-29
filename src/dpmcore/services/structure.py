"""Structure service — SDMX-style queries for DPM artefacts."""

from __future__ import annotations

from collections import defaultdict
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    cast,
)

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from dpmcore.orm.glossary import (
    Category,
    Context,
    ContextComposition,
    Item,
    ItemCategory,
    Property,
    PropertyCategory,
    SubCategory,
    SubCategoryItem,
    SubCategoryVersion,
)
from dpmcore.orm.infrastructure import (
    Concept,
    DataType,
    Organisation,
    Release,
)
from dpmcore.orm.operations import (
    OperandReference,
    OperandReferenceLocation,
    Operation,
    OperationNode,
    OperationVersion,
    Operator,
    OperatorArgument,
)
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleParameters,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.release_sort_order import compute_sort_order
from dpmcore.orm.rendering import (
    Cell,
    Header,
    HeaderVersion,
    Table,
    TableGroup,
    TableGroupComposition,
    TableVersion,
    TableVersionCell,
    TableVersionHeader,
)
from dpmcore.orm.variables import CompoundKey, Variable, VariableVersion
from dpmcore.server.params import StructureParams

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _release_to_dict(release: Release, detail: str = "full") -> Dict[str, Any]:
    """Convert a Release ORM instance to a spec §4.10 dict."""
    if detail == "allstubs":
        return {
            "id": release.release_id,
            "code": release.code,
        }
    return {
        "id": release.release_id,
        "code": release.code,
        "date": release.date.isoformat() if release.date else None,
        "description": release.description,
        "status": release.status,
        "isCurrent": release.is_current,
        "ownerId": release.owner_id,
        "conceptGuid": release.row_guid,
    }


def _organisation_to_dict(org: Organisation) -> Dict[str, Any]:
    """Convert an Organisation ORM instance to a dict."""
    return {
        "id": org.org_id,
        "name": org.name,
        "acronym": org.acronym,
        "idPrefix": org.id_prefix,
    }


def _category_to_dict(
    category: Category,
    *,
    detail: str,
    release_code: Optional[str],
    owner_acronym: Optional[str],
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Convert a Category ORM instance to a spec dict."""
    if detail == "allstubs":
        d: Dict[str, Any] = {
            "id": category.category_id,
            "code": category.code,
        }
        if owner_acronym is not None:
            d["owner"] = owner_acronym
        if release_code is not None:
            d["release"] = release_code
        return d
    return {
        "id": category.category_id,
        "code": category.code,
        "name": category.name,
        "description": category.description,
        "isEnumerated": category.is_enumerated,
        "isActive": category.is_active,
        "isExternalRefData": category.is_external_ref_data,
        "refDataSource": category.ref_data_source,
        "createdRelease": category.created_release_id,
        "owner": owner_acronym,
        "release": release_code,
        "items": items,
    }


def _item_to_dict(
    item: Item,
    item_category: ItemCategory,
) -> Dict[str, Any]:
    """Merge Item + ItemCategory fields into a spec dict."""
    return {
        "id": item.item_id,
        "name": item.name,
        "description": item.description,
        "isActive": item.is_active,
        "code": item_category.code,
        "isDefaultItem": item_category.is_default_item,
        "signature": item_category.signature,
        "startReleaseId": item_category.start_release_id,
        "endReleaseId": item_category.end_release_id,
    }


class StructureService:
    """Query DPM structural artefacts via SDMX-style parameters.

    Args:
        session: An open SQLAlchemy session.
    """

    def __init__(self, session: "Session") -> None:  # noqa: D107
        self.session = session
        self._releases_cache: Optional[List[Release]] = None
        self._sort_orders_cache: Optional[Dict[int, Optional[int]]] = None
        self._owner_cache: Dict[int, Optional[str]] = {}

    # ------------------------------------------------------------------ #
    # Releases
    # ------------------------------------------------------------------ #

    def _get_all_releases(self) -> List[Release]:
        """Return all releases ordered by semver-parsed sort order.

        Releases are ordered ascending by ``compute_sort_order(code)``
        (NOT the opaque ``release_id`` FK, which is non-monotonic from
        DPM 4.2.1 onwards — e.g. ``4.2.1`` is ``ReleaseID 1010000003`` —
        nor by ``date``). This keeps the version walks in
        ``_compute_*_versions`` / ``_version_at_release`` monotonic and
        places a chronological backport (e.g. ``4.0.1`` published after
        ``4.2.1``) inside its own lineage.

        Releases whose ``code`` is unparseable (``sort_order`` is
        ``None`` — e.g. a ``3.5-draft`` pre-release) cannot be placed in
        semver space, so they sort *first* and are skipped by the
        version walks. ``sort_order`` is computed from the same query
        that loads the releases, so this adds no extra round-trip.
        """
        if self._releases_cache is None:
            releases = self.session.query(Release).all()
            self._sort_orders_cache = {
                r.release_id: compute_sort_order(r.code) for r in releases
            }
            sort_orders = self._sort_orders_cache
            releases.sort(
                key=lambda r: (
                    sort_orders[r.release_id] is not None,
                    sort_orders[r.release_id] or 0,
                )
            )
            self._releases_cache = releases
        return self._releases_cache

    def _release_sort_orders(self) -> Dict[int, Optional[int]]:
        """Cached ``{release_id: sort_order}`` map (semver-parsed)."""
        self._get_all_releases()  # populates _sort_orders_cache
        return self._sort_orders_cache or {}

    def _sort_order(self, release_id: int) -> Optional[int]:
        """Semver sort order of a release_id, or ``None`` if unrankable."""
        return self._release_sort_orders().get(release_id)

    def _window_alive(
        self,
        start_release_id: int,
        end_release_id: Optional[int],
        target_release_id: int,
    ) -> bool:
        """Whether a ``[start, end]`` release window covers the target.

        Comparisons use the semver-parsed sort order rather than the
        opaque ``release_id`` FK. The end bound is **inclusive** — the
        convention the category/context virtual-versioning walks have
        always used (this intentionally differs from
        ``filter_by_release``'s exclusive end). Returns ``False`` for
        any release whose code is unrankable.
        """
        target_so = self._sort_order(target_release_id)
        start_so = self._sort_order(start_release_id)
        if target_so is None or start_so is None or start_so > target_so:
            return False
        if end_release_id is None:
            return True
        end_so = self._sort_order(end_release_id)
        return end_so is None or end_so >= target_so

    def _lookup_in_windows(
        self,
        windows: List[Tuple[int, Optional[int], Any]],
        target_release_id: int,
    ) -> Any:
        """Pick the value alive at *target_release_id* from windows.

        A window ``(start, end, value)`` is alive per the inclusive
        ``_window_alive`` convention. Returns ``None`` when no window
        covers the release.
        """
        for start, end, value in windows:
            if self._window_alive(start, end, target_release_id):
                return value
        return None

    def query_releases(
        self,
        *,
        owners: Optional[List[str]] = None,
        codes: Optional[List[str]] = None,
        latest: bool = False,
        latest_stable: bool = False,
        detail: str = "full",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query releases with SDMX-style filtering.

        Returns:
            Tuple of (results list, total count).
        """
        q = self.session.query(Release)

        # Owner filtering via Concept join chain
        if owners and owners != ["*"]:
            q = (
                q.join(Concept, Release.row_guid == Concept.concept_guid)
                .join(Organisation, Concept.owner_id == Organisation.org_id)
                .filter(Organisation.acronym.in_(owners))
            )

        # Code filtering
        if codes and codes != ["*"]:
            q = q.filter(Release.code.in_(codes))

        # Status filtering for latest stable
        if latest_stable:
            q = q.filter(Release.status == "Final")

        # Count before pagination/limiting
        total = q.count()

        # Latest → order by date desc, take first
        q = q.order_by(Release.date.desc())

        if latest or latest_stable:
            q = q.limit(1)
        else:
            q = q.offset(offset).limit(limit)

        rows = q.all()
        return [_release_to_dict(r, detail) for r in rows], total

    def get_release_by_code(
        self,
        code: str,
        *,
        owner: Optional[str] = None,
        detail: str = "full",
    ) -> Optional[Dict[str, Any]]:
        """Return a single release by its code."""
        q = self.session.query(Release).filter(Release.code == code)

        if owner:
            q = (
                q.join(Concept, Release.row_guid == Concept.concept_guid)
                .join(Organisation, Concept.owner_id == Organisation.org_id)
                .filter(Organisation.acronym == owner)
            )

        row = q.first()
        return _release_to_dict(row, detail) if row else None

    def get_release_organisations(
        self,
        owner_ids: Sequence[int | None],
    ) -> List[Dict[str, Any]]:
        """Return deduplicated organisations for a set of owner IDs.

        Callers often collect ids via ``dict.get("ownerId")`` or row
        attribute access, so ``None`` values may appear in the input and
        are silently dropped here.
        """
        unique = [oid for oid in set(owner_ids) if oid is not None]
        if not unique:
            return []
        orgs = (
            self.session.query(Organisation)
            .filter(Organisation.org_id.in_(unique))
            .all()
        )
        return [_organisation_to_dict(o) for o in orgs]

    # ------------------------------------------------------------------ #
    # Categories
    # ------------------------------------------------------------------ #

    def _resolve_release(
        self,
        params: StructureParams,
    ) -> Optional[Release]:
        """Map a StructureParams release value to a Release ORM object."""
        if params.wants_all_releases:
            return None
        releases = self._get_all_releases()
        if not releases:
            return None
        if params.wants_latest:
            return releases[-1]
        if params.wants_latest_stable:
            for r in reversed(releases):
                if r.status == "Final":
                    return r
            return None
        if params.release_code:
            for r in releases:
                if r.code == params.release_code:
                    return r
            return None
        return None

    def _get_owner_acronym(
        self,
        owner_id: Optional[int],
    ) -> Optional[str]:
        """Resolve Organisation.acronym from an owner_id (cached)."""
        if owner_id is None:
            return None
        if owner_id not in self._owner_cache:
            org = (
                self.session.query(Organisation)
                .filter(Organisation.org_id == owner_id)
                .first()
            )
            self._owner_cache[owner_id] = org.acronym if org else None
        return self._owner_cache[owner_id]

    def _bulk_load_category_data(
        self,
        cat_ids: List[int],
    ) -> Tuple[
        Dict[int, List[ItemCategory]],
        Dict[int, Item],
    ]:
        """Bulk-load ItemCategory and Item rows for given categories.

        Returns:
            (ics_by_cat, items_by_id) — ItemCategory rows grouped by
            category_id and Item rows keyed by item_id.
        """
        ics = (
            self.session.query(ItemCategory)
            .filter(ItemCategory.category_id.in_(cat_ids))
            .all()
        )

        ics_by_cat: Dict[int, List[ItemCategory]] = defaultdict(
            list,
        )
        item_ids: set[int] = set()
        for ic in ics:
            if ic.category_id is None:
                continue
            ics_by_cat[ic.category_id].append(ic)
            item_ids.add(ic.item_id)

        items_by_id: Dict[int, Item] = {}
        if item_ids:
            items = (
                self.session.query(Item)
                .filter(Item.item_id.in_(list(item_ids)))
                .all()
            )
            items_by_id = {i.item_id: i for i in items}

        return dict(ics_by_cat), items_by_id

    def _compute_category_versions(
        self,
        category: Category,
        releases: List[Release],
        ics: List[ItemCategory],
        items_by_id: Dict[int, Item],
        detail: str,
        owner_acronym: Optional[str],
    ) -> List[Tuple[Release, Dict[str, Any]]]:
        """Compute virtual versions for a single category.

        A new version is emitted only when the set of alive items
        (fingerprint) changes between consecutive releases.

        Returns:
            List of (release, category_dict) tuples — one per version.
        """
        versions: List[Tuple[Release, Dict[str, Any]]] = []
        prev_fingerprint = None

        for rel in releases:
            if self._sort_order(rel.release_id) is None:
                continue
            if (
                category.created_release_id is not None
                and not self._window_alive(
                    category.created_release_id, None, rel.release_id
                )
            ):
                continue

            alive_ics = [
                ic
                for ic in ics
                if self._window_alive(
                    ic.start_release_id, ic.end_release_id, rel.release_id
                )
            ]

            fingerprint = frozenset(
                (
                    ic.item_id,
                    ic.code,
                    ic.is_default_item,
                    ic.signature,
                )
                for ic in alive_ics
            )

            if fingerprint != prev_fingerprint:
                items = (
                    [
                        _item_to_dict(
                            items_by_id[ic.item_id],
                            ic,
                        )
                        for ic in alive_ics
                        if ic.item_id in items_by_id
                    ]
                    if detail != "allstubs"
                    else []
                )
                version_dict = _category_to_dict(
                    category,
                    detail=detail,
                    release_code=rel.code,
                    owner_acronym=owner_acronym,
                    items=items,
                )
                versions.append((rel, version_dict))
                prev_fingerprint = fingerprint

        return versions

    def _version_at_release(
        self,
        versions: List[Tuple[Release, Dict[str, Any]]],
        target_release: Release,
    ) -> Optional[Dict[str, Any]]:
        """Find the version active at *target_release*.

        Returns the last version whose semver sort order does not
        exceed the target's. ``versions`` is produced in ascending
        sort order, so the walk stops at the first version that
        overshoots.
        """
        target_so = self._sort_order(target_release.release_id)
        active: Optional[Dict[str, Any]] = None
        for rel, version_dict in versions:
            rel_so = self._sort_order(rel.release_id)
            if (
                target_so is not None
                and rel_so is not None
                and (rel_so <= target_so)
            ):
                active = version_dict
            else:
                break
        return active

    def _expand_versions(
        self,
        cats: List[Category],
        releases: List[Release],
        ics_by_cat: Dict[int, List[ItemCategory]],
        items_by_id: Dict[int, Item],
        detail: str,
        params: StructureParams,
        target_release: Optional[Release],
    ) -> List[Dict[str, Any]]:
        """Expand categories into virtual version entries."""
        all_entries: List[Dict[str, Any]] = []
        for cat in cats:
            owner_acronym = self._get_owner_acronym(
                cat.owner_id,
            )
            cat_ics = ics_by_cat.get(cat.category_id, [])
            versions = self._compute_category_versions(
                cat,
                releases,
                cat_ics,
                items_by_id,
                detail,
                owner_acronym,
            )

            if params.wants_all_releases:
                all_entries.extend(v_dict for _, v_dict in versions)
            elif versions and target_release is not None:
                v = self._version_at_release(
                    versions,
                    target_release,
                )
                if v is not None:
                    all_entries.append(v)
        return all_entries

    def query_categories(
        self,
        *,
        params: StructureParams,
        detail: str = "full",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query categories with SDMX-style filtering.

        Uses virtual versioning: a new version is emitted only when
        the item composition changes between consecutive releases.
        """
        releases = self._get_all_releases()

        # Resolve target release (None only for release=*)
        target_release: Optional[Release] = None
        if not params.wants_all_releases:
            target_release = self._resolve_release(params)
            if target_release is None:
                return [], 0

        # Query matching categories
        q = self.session.query(Category)

        owners = None if params.is_owner_wildcard else params.owners
        if owners:
            q = (
                q.join(
                    Concept,
                    Category.row_guid == Concept.concept_guid,
                )
                .join(
                    Organisation,
                    Concept.owner_id == Organisation.org_id,
                )
                .filter(Organisation.acronym.in_(owners))
            )

        if not params.is_id_wildcard:
            numeric_ids = [int(v) for v in params.ids if v.isdigit()]
            if numeric_ids:
                q = q.filter(
                    or_(
                        Category.code.in_(params.ids),
                        Category.category_id.in_(numeric_ids),
                    ),
                )
            else:
                q = q.filter(Category.code.in_(params.ids))

        q = q.order_by(Category.category_id)
        cats = q.all()

        if not cats:
            return [], 0

        # Bulk load ItemCategory + Item data
        cat_ids = [c.category_id for c in cats]
        ics_by_cat, items_by_id = self._bulk_load_category_data(
            cat_ids,
        )

        # Compute virtual versions for each category
        all_entries = self._expand_versions(
            cats,
            releases,
            ics_by_cat,
            items_by_id,
            detail,
            params,
            target_release,
        )

        total = len(all_entries)
        paginated = all_entries[offset : offset + limit]
        return paginated, total

    # ------------------------------------------------------------------ #
    # Tables
    # ------------------------------------------------------------------ #

    def query_tables(
        self,
        *,
        params: StructureParams,
        detail: str = "full",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query tables with SDMX-style filtering.

        One entry per matching ``TableVersion`` (so the same table can
        appear multiple times when ``release=*``). For each entry,
        headers, cells, and the variables referenced by cells are
        populated; enumerated variables include their valid items.
        """
        from dpmcore.dpm_xl.utils.filters import filter_by_release

        # Resolve target release (None only for release=*)
        target_release: Optional[Release] = None
        if not params.wants_all_releases:
            target_release = self._resolve_release(params)
            if target_release is None:
                return [], 0

        q = (
            self.session.query(TableVersion)
            .join(Table, Table.table_id == TableVersion.table_id)
            .options(joinedload(TableVersion.table))
        )

        # Owner filtering via Concept join chain (same pattern as
        # query_categories — keeps the join predicates uniform).
        owners = None if params.is_owner_wildcard else params.owners
        if owners:
            q = (
                q.join(Concept, Table.row_guid == Concept.concept_guid)
                .join(
                    Organisation,
                    Concept.owner_id == Organisation.org_id,
                )
                .filter(Organisation.acronym.in_(owners))
            )

        # ID filter: TableVersion.code, with numeric ids tried against
        # Table.table_id (matches the category handler's convention).
        if not params.is_id_wildcard:
            numeric_ids = [int(v) for v in params.ids if v.isdigit()]
            if numeric_ids:
                q = q.filter(
                    or_(
                        TableVersion.code.in_(params.ids),
                        Table.table_id.in_(numeric_ids),
                    )
                )
            else:
                q = q.filter(TableVersion.code.in_(params.ids))

        if target_release is not None:
            q = filter_by_release(
                q,
                start_col=TableVersion.start_release_id,
                end_col=TableVersion.end_release_id,
                release_id=target_release.release_id,
            )

        q = q.order_by(TableVersion.table_id, TableVersion.start_release_id)
        table_versions: List[TableVersion] = q.all()

        if not table_versions:
            return [], 0

        total = len(table_versions)
        paginated = table_versions[offset : offset + limit]

        results: List[Dict[str, Any]] = [
            self._build_table_entry(
                tv,
                detail=detail,
                target_release=target_release,
            )
            for tv in paginated
        ]
        return results, total

    # -- table entry assembly ------------------------------------------

    def _resolve_release_code(
        self,
        release_id: Optional[int],
    ) -> Optional[str]:
        """Return the release code for a release_id (cached lookup)."""
        if release_id is None:
            return None
        for r in self._get_all_releases():
            if r.release_id == release_id:
                return r.code
        return None

    def _build_table_entry(
        self,
        tv: TableVersion,
        *,
        detail: str,
        target_release: Optional[Release],
    ) -> Dict[str, Any]:
        """Single-table convenience wrapper over the batch builder."""
        return self._build_table_entries_batch(
            [tv], detail=detail, target_release=target_release
        )[tv.table_vid]

    # -- batched table loading -----------------------------------------

    def _batch_load_headers(
        self,
        table_vids: List[int],
    ) -> Dict[int, List[Tuple[TableVersionHeader, Header, HeaderVersion]]]:
        """``{table_vid: [(TableVersionHeader, Header, HeaderVersion), ...]}``.

        One SQL statement for the whole input set.
        """
        if not table_vids:
            return {}
        rows = (
            self.session.query(TableVersionHeader, Header, HeaderVersion)
            .join(Header, Header.header_id == TableVersionHeader.header_id)
            .join(
                HeaderVersion,
                HeaderVersion.header_vid == TableVersionHeader.header_vid,
            )
            .filter(TableVersionHeader.table_vid.in_(table_vids))
            .all()
        )
        out: Dict[
            int, List[Tuple[TableVersionHeader, Header, HeaderVersion]]
        ] = defaultdict(list)
        for tvh, h, hv in rows:
            out[tvh.table_vid].append((tvh, h, hv))
        return dict(out)

    def _batch_load_cells(
        self,
        table_vids: List[int],
    ) -> Dict[int, List[Tuple[TableVersionCell, Cell]]]:
        """``{table_vid: [(TableVersionCell, Cell), ...]}``.

        One SQL statement for the whole input set.
        """
        if not table_vids:
            return {}
        rows = (
            self.session.query(TableVersionCell, Cell)
            .join(Cell, Cell.cell_id == TableVersionCell.cell_id)
            .filter(TableVersionCell.table_vid.in_(table_vids))
            .all()
        )
        out: Dict[int, List[Tuple[TableVersionCell, Cell]]] = defaultdict(list)
        for tvc, c in rows:
            out[tvc.table_vid].append((tvc, c))
        return dict(out)

    def _build_table_entries_batch(  # noqa: C901  — pipeline orchestrator
        self,
        table_versions: List[TableVersion],
        *,
        detail: str,
        target_release: Optional[Release],
    ) -> Dict[int, Dict[str, Any]]:
        """Build response dicts for many TableVersions in fixed queries.

        Loads headers, cells, variable versions, property names, and
        subcategory enumerations in bulk regardless of how many tables
        are supplied. When ``target_release`` is None (release=*), each
        TableVersion's enumeration window uses its own
        ``start_release_id`` — calls to
        :meth:`_load_subcategory_enumerations` are then grouped per
        distinct effective release_id.
        """
        if not table_versions:
            return {}

        # Per-table effective release id (None target ⇒ per-tv start).
        effective_release_by_vid: Dict[int, Optional[int]] = {
            tv.table_vid: (
                target_release.release_id
                if target_release is not None
                else tv.start_release_id
            )
            for tv in table_versions
        }

        # allstubs short-circuit — no header/cell/variable loading.
        if detail == "allstubs":
            return {
                tv.table_vid: _table_stub_to_dict(
                    tv,
                    owner_acronym=self._get_owner_acronym(
                        tv.table.owner_id if tv.table else None
                    ),
                    release_code=(
                        target_release.code
                        if target_release is not None
                        else self._resolve_release_code(tv.start_release_id)
                    ),
                )
                for tv in table_versions
            }

        table_vids = [tv.table_vid for tv in table_versions]
        headers_by_vid = self._batch_load_headers(table_vids)
        cells_by_vid = self._batch_load_cells(table_vids)

        # Collect property_ids across all tables (TableVersion + headers).
        property_ids: set[int] = set()
        for tv in table_versions:
            if tv.property_id is not None:
                property_ids.add(tv.property_id)
        for header_rows in headers_by_vid.values():
            for _tvh, _h, hv in header_rows:
                if hv.property_id is not None:
                    property_ids.add(hv.property_id)

        # Collect variable_vids (key + cell) across all tables.
        all_variable_vids: set[int] = set()
        for header_rows in headers_by_vid.values():
            for _tvh, _h, hv in header_rows:
                if hv.key_variable_vid:
                    all_variable_vids.add(hv.key_variable_vid)
        for cell_rows in cells_by_vid.values():
            for tvc, _c in cell_rows:
                if tvc.variable_vid:
                    all_variable_vids.add(tvc.variable_vid)

        # Bulk-load VariableVersion rows once.
        vv_by_vid: Dict[int, VariableVersion] = {}
        if all_variable_vids:
            for vv in (
                self.session.query(VariableVersion)
                .filter(VariableVersion.variable_vid.in_(all_variable_vids))
                .all()
            ):
                vv_by_vid[vv.variable_vid] = vv
            # Variables expose their property reference too — fold
            # those property_ids into the bulk name lookup.
            for vv in vv_by_vid.values():
                if vv.property_id is not None:
                    property_ids.add(vv.property_id)

        property_names = self._bulk_load_property_names(property_ids)

        # Per-table {variable_vid: {subcat_vid}} mapping.
        subcat_vids_per_table: Dict[int, Dict[int, set[int]]] = {
            tv.table_vid: _collect_subcategory_vids_per_variable(
                headers_by_vid.get(tv.table_vid, []),
                cells_by_vid.get(tv.table_vid, []),
            )
            for tv in table_versions
        }

        # Group subcat lookups by effective release id (often a single
        # group when target_release is set; potentially several with
        # release=*).
        subcat_vids_by_release: Dict[Optional[int], set[int]] = defaultdict(
            set
        )
        for table_vid, per_var in subcat_vids_per_table.items():
            rid = effective_release_by_vid[table_vid]
            for svid_set in per_var.values():
                subcat_vids_by_release[rid].update(svid_set)
        subcat_enums_by_release: Dict[
            Optional[int], Dict[int, Dict[str, Any]]
        ] = {
            rid: self._load_subcategory_enumerations(svids, release_id=rid)
            for rid, svids in subcat_vids_by_release.items()
        }

        # Assemble per-table dicts using only the pre-loaded data.
        result: Dict[int, Dict[str, Any]] = {}
        for tv in table_versions:
            header_rows = headers_by_vid.get(tv.table_vid, [])
            cell_rows = cells_by_vid.get(tv.table_vid, [])
            owner_acronym = self._get_owner_acronym(
                tv.table.owner_id if tv.table else None
            )
            release_code = (
                target_release.code
                if target_release is not None
                else self._resolve_release_code(tv.start_release_id)
            )

            header_dicts = [
                _header_version_to_dict(tvh, h, hv, property_names)
                for tvh, h, hv in header_rows
            ]
            cell_dicts = [_cell_to_dict(tvc, c) for tvc, c in cell_rows]

            key_vids = {
                hv.key_variable_vid
                for _tvh, _h, hv in header_rows
                if hv.key_variable_vid
            }
            cell_vids = {
                tvc.variable_vid for tvc, _ in cell_rows if tvc.variable_vid
            }

            subcat_vids_by_variable = subcat_vids_per_table[tv.table_vid]
            subcat_enums = subcat_enums_by_release.get(
                effective_release_by_vid[tv.table_vid], {}
            )

            variables_block = _assemble_variable_blocks(
                key_vids | cell_vids,
                subcat_vids_by_variable=subcat_vids_by_variable,
                subcat_enums=subcat_enums,
                vv_by_vid=vv_by_vid,
                property_names=property_names,
            )
            key_variables = [
                v for v in variables_block if v["versionId"] in key_vids
            ]
            fact_variables = [
                v for v in variables_block if v["versionId"] not in key_vids
            ]

            result[tv.table_vid] = _table_to_dict(
                tv,
                owner_acronym=owner_acronym,
                release_code=release_code,
                property_names=property_names,
                headers=header_dicts,
                cells=cell_dicts,
                key_variables=key_variables,
                fact_variables=fact_variables,
            )
        return result

    def _bulk_load_property_names(
        self,
        property_ids: set[int],
    ) -> Dict[int, Optional[str]]:
        """Resolve ``{property_id: Item.name}`` for a set of property ids."""
        if not property_ids:
            return {}
        rows = (
            self.session.query(Item.item_id, Item.name)
            .join(Property, Property.property_id == Item.item_id)
            .filter(Item.item_id.in_(property_ids))
            .all()
        )
        return {r[0]: r[1] for r in rows}

    def _load_subcategory_enumerations(
        self,
        subcategory_vids: set[int],
        *,
        release_id: Optional[int],
    ) -> Dict[int, Dict[str, Any]]:
        """Load enumeration payloads for a set of SubCategoryVersion ids.

        Returns ``{subcategory_vid: enumeration_dict}``. Each
        enumeration dict carries the subcategory's parent
        :class:`Category` identity plus the items defined by the
        :class:`SubCategoryItem` rows of that version, enriched with
        ``code``/``signature`` from the :class:`ItemCategory` rows
        valid at *release_id*. Items lacking an ItemCategory entry at
        the release are dropped (they have no code at that release).
        """
        if not subcategory_vids:
            return {}

        from dpmcore.dpm_xl.utils.filters import filter_by_release

        # SubCategoryVersion → SubCategory → parent Category.
        info_rows = (
            self.session.query(SubCategoryVersion, SubCategory, Category)
            .join(
                SubCategory,
                SubCategory.subcategory_id
                == SubCategoryVersion.subcategory_id,
            )
            .join(Category, Category.category_id == SubCategory.category_id)
            .filter(SubCategoryVersion.subcategory_vid.in_(subcategory_vids))
            .all()
        )
        subcat_info: Dict[
            int, Tuple[SubCategoryVersion, SubCategory, Category]
        ] = {sv.subcategory_vid: (sv, sc, cat) for sv, sc, cat in info_rows}

        # SubCategoryItem rows + Item names, ordered.
        item_rows = (
            self.session.query(SubCategoryItem, Item)
            .join(Item, Item.item_id == SubCategoryItem.item_id)
            .filter(SubCategoryItem.subcategory_vid.in_(subcategory_vids))
            .order_by(SubCategoryItem.subcategory_vid, SubCategoryItem.order)
            .all()
        )
        items_by_subcat: Dict[int, List[Tuple[SubCategoryItem, Item]]] = (
            defaultdict(list)
        )
        for si, item in item_rows:
            items_by_subcat[si.subcategory_vid].append((si, item))

        # ItemCategory at release window — gives code/signature per
        # (item_id, parent_category_id).
        parent_cat_ids = {
            cat.category_id for (_sv, _sc, cat) in subcat_info.values()
        }
        item_codes: Dict[Tuple[int, int], ItemCategory] = {}
        if parent_cat_ids:
            ic_q = self.session.query(ItemCategory).filter(
                ItemCategory.category_id.in_(parent_cat_ids)
            )
            ic_q = filter_by_release(
                ic_q,
                start_col=ItemCategory.start_release_id,
                end_col=ItemCategory.end_release_id,
                release_id=release_id,
                active_only_fallback=True,
            )
            for ic in ic_q.all():
                item_codes[(ic.item_id, ic.category_id)] = ic

        result: Dict[int, Dict[str, Any]] = {}
        for svid, (_sv, sc, cat) in subcat_info.items():
            items_payload: List[Dict[str, Any]] = []
            for si, item in items_by_subcat.get(svid, []):
                ic = item_codes.get((item.item_id, cat.category_id))
                if ic is None:
                    # Item has no ItemCategory in the parent category
                    # at this release — skip; no code to surface.
                    continue
                items_payload.append(
                    {
                        "itemId": item.item_id,
                        "name": item.name,
                        "code": ic.code,
                        "signature": ic.signature,
                        "isDefaultItem": ic.is_default_item,
                        "subcategoryLabel": si.label,
                        "order": si.order,
                    }
                )
            result[svid] = {
                "subcategoryVersionId": svid,
                "subcategoryCode": sc.code,
                "subcategoryName": sc.name,
                "categoryId": cat.category_id,
                "categoryCode": cat.code,
                "items": items_payload,
            }
        return result

    def _build_variable_blocks(
        self,
        variable_vids: set[int],
        *,
        subcat_vids_by_variable: Dict[int, set[int]],
        subcat_enums: Dict[int, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Loader-fronted variant of :func:`_assemble_variable_blocks`.

        Issues the VariableVersion + property-name queries itself.
        Kept for callers that don't already have those rows preloaded.
        """
        if not variable_vids:
            return []
        vvs = (
            self.session.query(VariableVersion)
            .filter(VariableVersion.variable_vid.in_(variable_vids))
            .all()
        )
        vv_by_vid = {vv.variable_vid: vv for vv in vvs}
        property_ids = {vv.property_id for vv in vvs if vv.property_id}
        property_names = self._bulk_load_property_names(property_ids)
        return _assemble_variable_blocks(
            variable_vids,
            subcat_vids_by_variable=subcat_vids_by_variable,
            subcat_enums=subcat_enums,
            vv_by_vid=vv_by_vid,
            property_names=property_names,
        )

    # ------------------------------------------------------------------ #
    # TableGroups
    # ------------------------------------------------------------------ #

    def query_tablegroups(  # noqa: C901  — pipeline orchestrator
        self,
        *,
        params: StructureParams,
        detail: str = "full",
        references: str = "none",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query table groups with SDMX-style filtering.

        TableGroup itself is release-versioned (start/end on the row);
        ``TableGroupComposition`` is also release-versioned, so the
        set of contained tables can change across releases. With
        ``references=children`` the response carries:

        - ``tables`` — full table entries, ordered by composition order,
          filtered to the effective release;
        - ``childTableGroups`` — stub objects for direct child groups
          alive at the same release.

        Hierarchy IDs (``parentTableGroupId``, ``childTableGroupIds``)
        appear in the default response too.
        """
        from dpmcore.dpm_xl.utils.filters import filter_by_release

        target_release: Optional[Release] = None
        if not params.wants_all_releases:
            target_release = self._resolve_release(params)
            if target_release is None:
                return [], 0

        q = self.session.query(TableGroup)

        owners = None if params.is_owner_wildcard else params.owners
        if owners:
            org_ids = [
                org_id
                for (org_id,) in self.session.query(Organisation.org_id)
                .filter(Organisation.acronym.in_(owners))
                .all()
            ]
            if not org_ids:
                return [], 0
            q = q.filter(TableGroup.owner_id.in_(org_ids))

        if not params.is_id_wildcard:
            numeric_ids = [int(v) for v in params.ids if v.isdigit()]
            if numeric_ids:
                q = q.filter(
                    or_(
                        TableGroup.code.in_(params.ids),
                        TableGroup.table_group_id.in_(numeric_ids),
                    )
                )
            else:
                q = q.filter(TableGroup.code.in_(params.ids))

        if target_release is not None:
            q = filter_by_release(
                q,
                start_col=TableGroup.start_release_id,
                end_col=TableGroup.end_release_id,
                release_id=target_release.release_id,
            )

        q = q.order_by(TableGroup.table_group_id, TableGroup.start_release_id)
        groups: List[TableGroup] = q.all()
        if not groups:
            return [], 0

        total = len(groups)
        paginated = groups[offset : offset + limit]

        # Hierarchy ID listings (always loaded — one extra query).
        group_ids = [g.table_group_id for g in paginated]
        child_id_map = self._bulk_load_tablegroup_child_ids(
            group_ids, target_release=target_release
        )

        # Children expansion (tables + child group stubs) only on
        # references=children or all, and only at detail=full.
        include_children = references in ("children", "all")
        tables_by_group: Dict[int, List[Dict[str, Any]]] = {}
        child_stubs_by_group: Dict[int, List[Dict[str, Any]]] = {}
        if include_children and detail != "allstubs":
            tables_by_group, child_stubs_by_group = (
                self._load_tablegroup_children(
                    paginated, target_release=target_release
                )
            )

        results: List[Dict[str, Any]] = []
        for g in paginated:
            owner_acronym = self._get_owner_acronym(g.owner_id)
            release_code = (
                target_release.code
                if target_release is not None
                else self._resolve_release_code(g.start_release_id)
            )
            child_ids = child_id_map.get(g.table_group_id, [])
            if detail == "allstubs":
                entry = _tablegroup_stub_to_dict(
                    g,
                    owner_acronym=owner_acronym,
                    release_code=release_code,
                )
            else:
                entry = _tablegroup_to_dict(
                    g,
                    owner_acronym=owner_acronym,
                    release_code=release_code,
                    child_table_group_ids=child_ids,
                )
                if include_children:
                    entry["tables"] = tables_by_group.get(g.table_group_id, [])
                    entry["childTableGroups"] = child_stubs_by_group.get(
                        g.table_group_id, []
                    )
            results.append(entry)

        return results, total

    def _bulk_load_tablegroup_child_ids(
        self,
        parent_ids: List[int],
        *,
        target_release: Optional[Release],
    ) -> Dict[int, List[int]]:
        """``{parent_table_group_id: [child_table_group_id, ...]}``.

        Release-filtered when ``target_release`` is set.
        """
        from dpmcore.dpm_xl.utils.filters import filter_by_release

        if not parent_ids:
            return {}
        q = (
            self.session.query(
                TableGroup.parent_table_group_id, TableGroup.table_group_id
            )
            .filter(TableGroup.parent_table_group_id.in_(parent_ids))
            .order_by(
                TableGroup.parent_table_group_id, TableGroup.table_group_id
            )
        )
        if target_release is not None:
            q = filter_by_release(
                q,
                start_col=TableGroup.start_release_id,
                end_col=TableGroup.end_release_id,
                release_id=target_release.release_id,
            )
        out: Dict[int, List[int]] = defaultdict(list)
        for parent_id, child_id in q.all():
            out[parent_id].append(child_id)
        return dict(out)

    def _load_tablegroup_children(  # noqa: C901  — pipeline
        self,
        groups: List[TableGroup],
        *,
        target_release: Optional[Release],
    ) -> Tuple[
        Dict[int, List[Dict[str, Any]]],
        Dict[int, List[Dict[str, Any]]],
    ]:
        """Per-group tables and direct child-group stubs.

        Returns ``(tables_by_group, child_stubs_by_group)``.

        Compositions and the child-group stubs are filtered by the
        effective release per group (target_release for literal/~/+,
        the group's own start_release_id for release=*). For release=*
        we bucket groups by their effective release and run one set
        of queries per bucket — query budget stays bounded.
        """
        from dpmcore.dpm_xl.utils.filters import filter_by_release

        if not groups:
            return {}, {}

        # Bucket groups by effective release.
        groups_by_effective_release: Dict[int, List[TableGroup]] = defaultdict(
            list
        )
        for g in groups:
            rid = (
                target_release.release_id
                if target_release is not None
                else g.start_release_id
            )
            if rid is not None:
                groups_by_effective_release[rid].append(g)

        # Build a quick lookup of release_id → Release for the batch
        # table builder.
        release_by_id = {r.release_id: r for r in self._get_all_releases()}

        tables_by_group: Dict[int, List[Dict[str, Any]]] = {}
        child_stubs_by_group: Dict[int, List[Dict[str, Any]]] = {}

        for rid, bucket in groups_by_effective_release.items():
            bucket_ids = [g.table_group_id for g in bucket]

            # Compositions at this release.
            comp_q = self.session.query(TableGroupComposition).filter(
                TableGroupComposition.table_group_id.in_(bucket_ids)
            )
            comp_q = filter_by_release(
                comp_q,
                start_col=TableGroupComposition.start_release_id,
                end_col=TableGroupComposition.end_release_id,
                release_id=rid,
            )
            comps = comp_q.all()

            comps_by_group: Dict[int, List[TableGroupComposition]] = (
                defaultdict(list)
            )
            table_ids: set[int] = set()
            for cc in comps:
                comps_by_group[cc.table_group_id].append(cc)
                if cc.table_id is not None:
                    table_ids.add(cc.table_id)

            tv_by_table_id: Dict[int, TableVersion] = {}
            if table_ids:
                tv_q = (
                    self.session.query(TableVersion)
                    .options(joinedload(TableVersion.table))
                    .filter(TableVersion.table_id.in_(table_ids))
                )
                tv_q = filter_by_release(
                    tv_q,
                    start_col=TableVersion.start_release_id,
                    end_col=TableVersion.end_release_id,
                    release_id=rid,
                )
                for tv in tv_q.all():
                    tv_by_table_id[tv.table_id] = tv

            entries_by_tvid: Dict[int, Dict[str, Any]] = {}
            if tv_by_table_id:
                target_for_batch = release_by_id.get(rid)
                entries_by_tvid = self._build_table_entries_batch(
                    list(tv_by_table_id.values()),
                    detail="full",
                    target_release=target_for_batch,
                )

            for g in bucket:
                ordered = sorted(
                    comps_by_group.get(g.table_group_id, []),
                    key=lambda c: c.order if c.order is not None else 0,
                )
                ordered_entries: List[Dict[str, Any]] = []
                for cc in ordered:
                    if cc.table_id is None:
                        continue
                    tv = tv_by_table_id.get(cc.table_id)
                    if tv is None:
                        continue
                    entry = entries_by_tvid.get(tv.table_vid)
                    if entry is not None:
                        ordered_entries.append(entry)
                tables_by_group[g.table_group_id] = ordered_entries

            # Child TableGroups at this release.
            child_q = self.session.query(TableGroup).filter(
                TableGroup.parent_table_group_id.in_(bucket_ids)
            )
            child_q = filter_by_release(
                child_q,
                start_col=TableGroup.start_release_id,
                end_col=TableGroup.end_release_id,
                release_id=rid,
            )
            child_q = child_q.order_by(
                TableGroup.parent_table_group_id, TableGroup.table_group_id
            )
            child_stubs: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
            for cg in child_q.all():
                child_stubs[cg.parent_table_group_id].append(
                    {
                        "id": cg.table_group_id,
                        "code": cg.code,
                        "name": cg.name,
                        "type": cg.type,
                        "startReleaseId": cg.start_release_id,
                        "endReleaseId": cg.end_release_id,
                    }
                )
            for g in bucket:
                child_stubs_by_group[g.table_group_id] = child_stubs.get(
                    g.table_group_id, []
                )

        return tables_by_group, child_stubs_by_group

    # ------------------------------------------------------------------ #
    # Modules
    # ------------------------------------------------------------------ #

    def query_modules(  # noqa: C901  — pipeline orchestrator
        self,
        *,
        params: StructureParams,
        detail: str = "full",
        references: str = "none",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query modules with SDMX-style filtering.

        One entry per matching :class:`ModuleVersion`. When
        ``references == "children"`` or ``"all"``, each entry includes
        a ``tables`` array (full table shape, batch-loaded).
        """
        from dpmcore.dpm_xl.utils.filters import filter_by_release

        target_release: Optional[Release] = None
        if not params.wants_all_releases:
            target_release = self._resolve_release(params)
            if target_release is None:
                return [], 0

        q = (
            self.session.query(ModuleVersion)
            .join(Module, Module.module_id == ModuleVersion.module_id)
            .options(joinedload(ModuleVersion.module))
        )

        # Owner filter — Module carries owner_id directly; we still join
        # Concept→Organisation to translate acronym → id (cleaner than
        # querying Organisation up front).
        owners = None if params.is_owner_wildcard else params.owners
        if owners:
            q = (
                q.join(Concept, Module.row_guid == Concept.concept_guid)
                .join(
                    Organisation,
                    Concept.owner_id == Organisation.org_id,
                )
                .filter(Organisation.acronym.in_(owners))
            )

        # ID filter on ModuleVersion.code (with numeric fallback to
        # Module.module_id — matches the table handler's convention).
        if not params.is_id_wildcard:
            numeric_ids = [int(v) for v in params.ids if v.isdigit()]
            if numeric_ids:
                q = q.filter(
                    or_(
                        ModuleVersion.code.in_(params.ids),
                        Module.module_id.in_(numeric_ids),
                    )
                )
            else:
                q = q.filter(ModuleVersion.code.in_(params.ids))

        if target_release is not None:
            q = filter_by_release(
                q,
                start_col=ModuleVersion.start_release_id,
                end_col=ModuleVersion.end_release_id,
                release_id=target_release.release_id,
            )

        q = q.order_by(ModuleVersion.module_id, ModuleVersion.start_release_id)
        module_versions: List[ModuleVersion] = q.all()

        if not module_versions:
            return [], 0

        total = len(module_versions)
        paginated = module_versions[offset : offset + limit]

        # Bulk loads shared by every detail level.
        module_vids = [mv.module_vid for mv in paginated]
        parameter_vids_by_module = self._bulk_load_module_parameters(
            module_vids
        )
        framework_ids = {
            mv.module.framework_id
            for mv in paginated
            if mv.module and mv.module.framework_id is not None
        }
        framework_refs = self._bulk_load_framework_refs(framework_ids)

        include_children = references in ("children", "all")
        tables_by_module: Dict[int, List[Dict[str, Any]]] = {}
        if include_children and detail != "allstubs":
            tables_by_module = self._load_module_children(
                paginated, target_release=target_release, detail=detail
            )

        results: List[Dict[str, Any]] = []
        for mv in paginated:
            module = mv.module
            owner_acronym = (
                self._get_owner_acronym(module.owner_id) if module else None
            )
            release_code = (
                target_release.code
                if target_release is not None
                else self._resolve_release_code(mv.start_release_id)
            )
            framework_ref = (
                framework_refs.get(module.framework_id)
                if module and module.framework_id is not None
                else None
            )

            if detail == "allstubs":
                entry = _module_stub_to_dict(
                    mv,
                    owner_acronym=owner_acronym,
                    release_code=release_code,
                )
            else:
                entry = _module_version_to_dict(
                    mv,
                    owner_acronym=owner_acronym,
                    release_code=release_code,
                    framework_ref=framework_ref,
                    parameter_variable_vids=parameter_vids_by_module.get(
                        mv.module_vid, []
                    ),
                )
                if include_children:
                    entry["tables"] = tables_by_module.get(mv.module_vid, [])
            results.append(entry)

        return results, total

    def _load_module_children(
        self,
        module_versions: List[ModuleVersion],
        *,
        target_release: Optional[Release],
        detail: str,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Load ordered table dicts per module_vid using the batch builder.

        One query for ModuleVersionComposition, one for TableVersion +
        Table, and then the table batch builder handles the rest. Tables
        are returned in ``ModuleVersionComposition.order``.
        """
        if not module_versions:
            return {}

        module_vids = [mv.module_vid for mv in module_versions]
        comp_rows = (
            self.session.query(ModuleVersionComposition)
            .filter(ModuleVersionComposition.module_vid.in_(module_vids))
            .order_by(
                ModuleVersionComposition.module_vid,
                ModuleVersionComposition.order,
            )
            .all()
        )

        ordered_vids_by_module: Dict[int, List[int]] = defaultdict(list)
        all_table_vids: set[int] = set()
        for comp in comp_rows:
            if comp.table_vid is None:
                continue
            ordered_vids_by_module[comp.module_vid].append(comp.table_vid)
            all_table_vids.add(comp.table_vid)

        if not all_table_vids:
            return {}

        tvs = (
            self.session.query(TableVersion)
            .options(joinedload(TableVersion.table))
            .filter(TableVersion.table_vid.in_(all_table_vids))
            .all()
        )
        table_entries = self._build_table_entries_batch(
            tvs, detail=detail, target_release=target_release
        )

        # Project per module in composition order, skipping any
        # composition rows whose table_vid didn't resolve.
        return {
            module_vid: [
                table_entries[tvid]
                for tvid in ordered_vids
                if tvid in table_entries
            ]
            for module_vid, ordered_vids in ordered_vids_by_module.items()
        }

    # ------------------------------------------------------------------ #
    # Operators
    # ------------------------------------------------------------------ #

    def query_operators(
        self,
        *,
        params: StructureParams,
        detail: str = "full",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query operators.

        Operators are flat, unversioned, and unowned. The ``{owner}``
        URL segment must be ``*`` (concrete owners 204); the release
        segment is ignored. The ``{id}`` segment matches
        ``Operator.name`` or numeric ``operator_id`` — symbols are
        intentionally not supported as URL ids because operator
        symbols often clash with URL syntax (``+``, ``*``, ``/``).

        Each operator carries its ``OperatorArgument`` list inline at
        ``detail=full`` (the argument set is part of the operator's
        definition; a handful of entries per operator).
        """
        if not params.is_owner_wildcard:
            return [], 0

        q = self.session.query(Operator)

        if not params.is_id_wildcard:
            numeric_ids = [int(v) for v in params.ids if v.isdigit()]
            if numeric_ids:
                q = q.filter(
                    or_(
                        Operator.name.in_(params.ids),
                        Operator.operator_id.in_(numeric_ids),
                    )
                )
            else:
                q = q.filter(Operator.name.in_(params.ids))

        total = q.with_entities(func.count(Operator.operator_id)).scalar() or 0
        if total == 0:
            return [], 0

        q = q.order_by(Operator.operator_id)
        rows = q.offset(offset).limit(limit).all()

        if detail == "allstubs":
            return [_operator_stub_to_dict(op) for op in rows], total

        operator_ids = [op.operator_id for op in rows]
        args_by_operator = self._bulk_load_operator_arguments(operator_ids)

        results = [
            _operator_to_dict(
                op,
                arguments=args_by_operator.get(op.operator_id, []),
            )
            for op in rows
        ]
        return results, total

    def _bulk_load_operator_arguments(
        self,
        operator_ids: List[int],
    ) -> Dict[int, List[Dict[str, Any]]]:
        """``{operator_id: [argument_dict, ...]}`` in one query."""
        if not operator_ids:
            return {}
        rows = (
            self.session.query(OperatorArgument)
            .filter(OperatorArgument.operator_id.in_(operator_ids))
            .order_by(
                OperatorArgument.operator_id,
                OperatorArgument.order,
                OperatorArgument.argument_id,
            )
            .all()
        )
        out: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for a in rows:
            out[cast(int, a.operator_id)].append(
                {
                    "id": a.argument_id,
                    "order": a.order,
                    "name": a.name,
                    "isMandatory": a.is_mandatory,
                }
            )
        return dict(out)

    # ------------------------------------------------------------------ #
    # Operations
    # ------------------------------------------------------------------ #

    def query_operations(  # noqa: C901  — pipeline orchestrator
        self,
        *,
        params: StructureParams,
        detail: str = "full",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query operations with nested versions/nodes/references.

        Each Operation carries a ``versions`` array. The ``{release}``
        URL segment filters which versions appear inside — Operations
        with no version active at the release are dropped from the
        result set entirely.

        At ``detail=full`` (default) every version carries the full
        node tree, each node carries its operand references, and each
        reference carries its physical locations (table/row/column/sheet).
        ``detail=allstubs`` returns just the Operation identifiers plus
        the list of operationVersionIds.
        """
        from dpmcore.dpm_xl.utils.filters import filter_by_release

        target_release: Optional[Release] = None
        if not params.wants_all_releases:
            target_release = self._resolve_release(params)
            if target_release is None:
                return [], 0

        q = self.session.query(Operation)

        # Owner filter via direct owner_id (same lesson as contexts —
        # row_guid → Concept can be NULL in real data).
        owners = None if params.is_owner_wildcard else params.owners
        if owners:
            org_ids = [
                org_id
                for (org_id,) in self.session.query(Organisation.org_id)
                .filter(Organisation.acronym.in_(owners))
                .all()
            ]
            if not org_ids:
                return [], 0
            q = q.filter(Operation.owner_id.in_(org_ids))

        if not params.is_id_wildcard:
            numeric_ids = [int(v) for v in params.ids if v.isdigit()]
            if numeric_ids:
                q = q.filter(
                    or_(
                        Operation.code.in_(params.ids),
                        Operation.operation_id.in_(numeric_ids),
                    )
                )
            else:
                q = q.filter(Operation.code.in_(params.ids))

        if target_release is not None:
            # EXISTS subquery: include Operation only if it has at
            # least one OperationVersion active at the target release.
            version_subq = self.session.query(
                OperationVersion.operation_id
            ).filter(OperationVersion.operation_id == Operation.operation_id)
            version_subq = filter_by_release(
                version_subq,
                start_col=OperationVersion.start_release_id,
                end_col=OperationVersion.end_release_id,
                release_id=target_release.release_id,
            )
            q = q.filter(version_subq.exists())

        total = (
            q.with_entities(func.count(Operation.operation_id)).scalar() or 0
        )
        if total == 0:
            return [], 0

        q = q.order_by(Operation.operation_id)
        operations: List[Operation] = q.offset(offset).limit(limit).all()
        if not operations:
            return [], total

        operation_ids = [op.operation_id for op in operations]

        # Bulk-load OperationVersions for the paginated Operations,
        # filtered by the requested release.
        versions_by_op = self._bulk_load_operation_versions(
            operation_ids, target_release=target_release
        )

        # For full detail: bulk-load the rest of the tree.
        nodes_by_vid: Dict[int, List[OperationNode]] = {}
        refs_by_node: Dict[int, List[OperandReference]] = {}
        locs_by_ref: Dict[int, List[OperandReferenceLocation]] = {}
        if detail != "allstubs":
            all_vids = [
                v.operation_vid for vs in versions_by_op.values() for v in vs
            ]
            nodes_by_vid = self._bulk_load_operation_nodes(all_vids)
            all_node_ids = [
                n.node_id for ns in nodes_by_vid.values() for n in ns
            ]
            refs_by_node = self._bulk_load_operand_references(all_node_ids)
            all_ref_ids = [
                r.operand_reference_id
                for rs in refs_by_node.values()
                for r in rs
            ]
            locs_by_ref = self._bulk_load_reference_locations(all_ref_ids)

        results: List[Dict[str, Any]] = []
        for op in operations:
            owner_acronym = self._get_owner_acronym(op.owner_id)
            op_versions = versions_by_op.get(op.operation_id, [])
            if not op_versions:
                # release filter dropped every version — skip the row.
                continue
            if detail == "allstubs":
                results.append(
                    _operation_stub_to_dict(
                        op,
                        owner_acronym=owner_acronym,
                        version_ids=[v.operation_vid for v in op_versions],
                    )
                )
                continue
            version_dicts: List[Dict[str, Any]] = []
            for v in op_versions:
                release_code = (
                    target_release.code
                    if target_release is not None
                    else self._resolve_release_code(v.start_release_id)
                )
                node_dicts = [
                    _operation_node_to_dict(
                        n,
                        references=[
                            _operand_reference_to_dict(
                                r,
                                locations=[
                                    _operand_reference_location_to_dict(loc)
                                    for loc in locs_by_ref.get(
                                        r.operand_reference_id, []
                                    )
                                ],
                            )
                            for r in refs_by_node.get(n.node_id, [])
                        ],
                    )
                    for n in nodes_by_vid.get(v.operation_vid, [])
                ]
                version_dicts.append(
                    _operation_version_to_dict(
                        v,
                        release_code=release_code,
                        nodes=node_dicts,
                    )
                )
            results.append(
                _operation_to_dict(
                    op,
                    owner_acronym=owner_acronym,
                    versions=version_dicts,
                )
            )

        return results, total

    def _bulk_load_operation_versions(
        self,
        operation_ids: List[int],
        *,
        target_release: Optional[Release],
    ) -> Dict[int, List[OperationVersion]]:
        """``{operation_id: [OperationVersion, ...]}``, release-filtered."""
        from dpmcore.dpm_xl.utils.filters import filter_by_release

        if not operation_ids:
            return {}
        q = self.session.query(OperationVersion).filter(
            OperationVersion.operation_id.in_(operation_ids)
        )
        if target_release is not None:
            q = filter_by_release(
                q,
                start_col=OperationVersion.start_release_id,
                end_col=OperationVersion.end_release_id,
                release_id=target_release.release_id,
            )
        q = q.order_by(
            OperationVersion.operation_id, OperationVersion.start_release_id
        )
        out: Dict[int, List[OperationVersion]] = defaultdict(list)
        for v in q.all():
            out[cast(int, v.operation_id)].append(v)
        return dict(out)

    def _bulk_load_operation_nodes(
        self,
        operation_vids: List[int],
    ) -> Dict[int, List[OperationNode]]:
        """``{operation_vid: [OperationNode, ...]}`` in one query."""
        if not operation_vids:
            return {}
        rows = (
            self.session.query(OperationNode)
            .filter(OperationNode.operation_vid.in_(operation_vids))
            .order_by(OperationNode.operation_vid, OperationNode.node_id)
            .all()
        )
        out: Dict[int, List[OperationNode]] = defaultdict(list)
        for n in rows:
            out[cast(int, n.operation_vid)].append(n)
        return dict(out)

    def _bulk_load_operand_references(
        self,
        node_ids: List[int],
    ) -> Dict[int, List[OperandReference]]:
        """``{node_id: [OperandReference, ...]}`` in one query."""
        if not node_ids:
            return {}
        rows = (
            self.session.query(OperandReference)
            .filter(OperandReference.node_id.in_(node_ids))
            .order_by(
                OperandReference.node_id,
                OperandReference.operand_reference_id,
            )
            .all()
        )
        out: Dict[int, List[OperandReference]] = defaultdict(list)
        for r in rows:
            out[cast(int, r.node_id)].append(r)
        return dict(out)

    def _bulk_load_reference_locations(
        self,
        reference_ids: List[int],
    ) -> Dict[int, List[OperandReferenceLocation]]:
        """``{operand_reference_id: [OperandReferenceLocation, ...]}``.

        Schema declares ``operand_reference_id`` as the location's
        primary key, so the list is typically 0 or 1 entry — we still
        surface it as a list to mirror the ORM relationship.
        """
        if not reference_ids:
            return {}
        rows = (
            self.session.query(OperandReferenceLocation)
            .filter(
                OperandReferenceLocation.operand_reference_id.in_(
                    reference_ids
                )
            )
            .order_by(OperandReferenceLocation.operand_reference_id)
            .all()
        )
        out: Dict[int, List[OperandReferenceLocation]] = defaultdict(list)
        for loc in rows:
            out[loc.operand_reference_id].append(loc)
        return dict(out)

    # ------------------------------------------------------------------ #
    # DataTypes
    # ------------------------------------------------------------------ #

    def query_datatypes(
        self,
        *,
        params: StructureParams,
        detail: str = "full",
        references: str = "none",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query data types.

        DataTypes are flat, unversioned, and unowned, but they form a
        hierarchy via ``parent_data_type_id``. Default response carries
        ``parentDataTypeId`` + ``childDataTypeIds``;
        ``references=children`` adds expanded ``childDataTypes`` stubs.

        - ``{owner}`` must be ``*`` — DataTypes have no owner, so a
          concrete owner deliberately returns 204.
        - ``{release}`` is ignored — DataTypes are not versioned.
        """
        # DataTypes have no owner; a concrete owner filter cannot match.
        if not params.is_owner_wildcard:
            return [], 0

        q = self.session.query(DataType)

        if not params.is_id_wildcard:
            numeric_ids = [int(v) for v in params.ids if v.isdigit()]
            if numeric_ids:
                q = q.filter(
                    or_(
                        DataType.code.in_(params.ids),
                        DataType.data_type_id.in_(numeric_ids),
                    )
                )
            else:
                q = q.filter(DataType.code.in_(params.ids))

        total = (
            q.with_entities(func.count(DataType.data_type_id)).scalar() or 0
        )
        if total == 0:
            return [], 0

        q = q.order_by(DataType.data_type_id)
        rows = q.offset(offset).limit(limit).all()

        parent_ids = [r.data_type_id for r in rows]
        child_id_map = self._bulk_load_datatype_child_ids(parent_ids)

        include_children = references in ("children", "all")
        child_expansions: Dict[int, List[Dict[str, Any]]] = {}
        if include_children and detail != "allstubs":
            child_expansions = self._bulk_load_datatype_child_expansions(
                parent_ids
            )

        results: List[Dict[str, Any]] = []
        for dt in rows:
            if detail == "allstubs":
                entry = _datatype_stub_to_dict(dt)
            else:
                entry = _datatype_to_dict(
                    dt,
                    child_data_type_ids=child_id_map.get(dt.data_type_id, []),
                )
                if include_children:
                    entry["childDataTypes"] = child_expansions.get(
                        dt.data_type_id, []
                    )
            results.append(entry)
        return results, total

    def _bulk_load_datatype_child_ids(
        self,
        parent_ids: List[int],
    ) -> Dict[int, List[int]]:
        """``{parent_data_type_id: [child_id, ...]}`` in one query."""
        if not parent_ids:
            return {}
        rows = (
            self.session.query(
                DataType.parent_data_type_id, DataType.data_type_id
            )
            .filter(DataType.parent_data_type_id.in_(parent_ids))
            .order_by(DataType.parent_data_type_id, DataType.data_type_id)
            .all()
        )
        out: Dict[int, List[int]] = defaultdict(list)
        for parent_id, child_id in rows:
            out[parent_id].append(child_id)
        return dict(out)

    def _bulk_load_datatype_child_expansions(
        self,
        parent_ids: List[int],
    ) -> Dict[int, List[Dict[str, Any]]]:
        """``{parent_data_type_id: [child_stub, ...]}`` in one query."""
        if not parent_ids:
            return {}
        rows = (
            self.session.query(DataType)
            .filter(DataType.parent_data_type_id.in_(parent_ids))
            .order_by(DataType.parent_data_type_id, DataType.data_type_id)
            .all()
        )
        out: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for dt in rows:
            out[cast(int, dt.parent_data_type_id)].append(
                _datatype_stub_to_dict(dt)
            )
        return dict(out)

    # ------------------------------------------------------------------ #
    # Organisations
    # ------------------------------------------------------------------ #

    def query_organisations(
        self,
        *,
        params: StructureParams,
        detail: str = "full",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query organisations.

        Organisations are not release-versioned; the release path
        segment is accepted but ignored for selection. Both the
        ``{owner}`` and ``{id}`` URL segments filter on
        ``Organisation.acronym`` (or numeric ``org_id``) — for
        organisations they target the same column.
        """
        q = self.session.query(Organisation)

        if not params.is_owner_wildcard:
            q = q.filter(Organisation.acronym.in_(params.owners))

        if not params.is_id_wildcard:
            numeric_ids = [int(v) for v in params.ids if v.isdigit()]
            non_numeric = [v for v in params.ids if not v.isdigit()]
            id_clauses = []
            if numeric_ids:
                id_clauses.append(Organisation.org_id.in_(numeric_ids))
            if non_numeric:
                id_clauses.append(Organisation.acronym.in_(non_numeric))
            if id_clauses:
                q = q.filter(or_(*id_clauses))

        total = q.with_entities(func.count(Organisation.org_id)).scalar() or 0
        if total == 0:
            return [], 0

        q = q.order_by(Organisation.org_id)
        rows = q.offset(offset).limit(limit).all()

        if detail == "allstubs":
            return [
                {"id": o.org_id, "acronym": o.acronym} for o in rows
            ], total
        return [_organisation_to_dict(o) for o in rows], total

    # ------------------------------------------------------------------ #
    # Contexts
    # ------------------------------------------------------------------ #

    def query_contexts(  # noqa: C901  — pipeline orchestrator
        self,
        *,
        params: StructureParams,
        detail: str = "full",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query contexts with SDMX-style filtering + virtual versioning.

        :class:`ContextComposition` is **not** release-versioned —
        the same (property, item) pairs apply to a context across
        the whole timeline. The codes of those properties/items,
        however, ARE release-versioned via their ItemCategory rows.
        We surface a new "virtual version" of a context every time
        the set of (propertyCode, itemCode) pairs changes between
        consecutive releases.

        The URL ``id`` segment matches ``Context.context_id``
        (contexts have no human-readable code field).
        """
        target_release: Optional[Release] = None
        if not params.wants_all_releases:
            target_release = self._resolve_release(params)
            if target_release is None:
                return [], 0

        # Context query. Real-data note: Context rows often have
        # ``row_guid`` NULL while ``owner_id`` is populated — so we
        # filter on the direct column rather than the Concept join
        # used by other endpoints.
        q = self.session.query(Context)

        owners = None if params.is_owner_wildcard else params.owners
        if owners:
            org_ids = [
                org_id
                for (org_id,) in self.session.query(Organisation.org_id)
                .filter(Organisation.acronym.in_(owners))
                .all()
            ]
            if not org_ids:
                return [], 0
            q = q.filter(Context.owner_id.in_(org_ids))

        if not params.is_id_wildcard:
            numeric_ids = [int(v) for v in params.ids if v.isdigit()]
            if not numeric_ids:
                # Contexts have no code; non-numeric ids match nothing.
                return [], 0
            q = q.filter(Context.context_id.in_(numeric_ids))

        q = q.order_by(Context.context_id)
        contexts: List[Context] = q.all()
        if not contexts:
            return [], 0

        # Bulk-load compositions for all matched contexts.
        context_ids = [c.context_id for c in contexts]
        comp_rows = (
            self.session.query(ContextComposition)
            .filter(ContextComposition.context_id.in_(context_ids))
            .all()
        )
        comps_by_context: Dict[int, List[ContextComposition]] = defaultdict(
            list
        )
        all_property_ids: set[int] = set()
        all_item_ids: set[int] = set()
        for cc in comp_rows:
            comps_by_context[cc.context_id].append(cc)
            all_property_ids.add(cc.property_id)
            if cc.item_id is not None:
                all_item_ids.add(cc.item_id)

        # Bulk-load the three pieces of release-versioned lookup data.
        property_code_windows = self._bulk_load_property_code_windows(
            all_property_ids
        )
        property_category_windows = self._bulk_load_property_category_windows(
            all_property_ids
        )
        item_code_windows = self._bulk_load_item_code_windows(all_item_ids)

        releases = self._get_all_releases()

        all_entries: List[Dict[str, Any]] = []
        for context in contexts:
            compositions = comps_by_context.get(context.context_id, [])
            versions = self._compute_context_versions(
                context,
                compositions,
                releases,
                property_code_windows,
                property_category_windows,
                item_code_windows,
                detail=detail,
            )
            if not versions:
                continue
            if params.wants_all_releases:
                all_entries.extend(v_dict for _, v_dict in versions)
            elif target_release is not None:
                v = self._version_at_release(versions, target_release)
                if v is not None:
                    all_entries.append(v)

        total = len(all_entries)
        paginated = all_entries[offset : offset + limit]
        return paginated, total

    # -- bulk loaders for release-windowed lookups --------------------

    def _bulk_load_property_code_windows(
        self,
        property_ids: set[int],
    ) -> Dict[int, List[Tuple[int, Optional[int], str]]]:
        """``{property_id: [(start_release_id, end_release_id, code)]}``.

        Codes come from the property item's ItemCategory rows. We
        do not hardcode the meta-category code (e.g. ``_PR``) — we
        accept any ItemCategory pointing at a Category for which the
        item is registered as a property. In practice every property
        item in EBA data lives in a single ``_PR`` row; this helper
        works regardless.
        """
        if not property_ids:
            return {}
        rows = (
            self.session.query(
                ItemCategory.item_id,
                ItemCategory.start_release_id,
                ItemCategory.end_release_id,
                ItemCategory.code,
            )
            .join(Item, Item.item_id == ItemCategory.item_id)
            .filter(
                ItemCategory.item_id.in_(property_ids),
                Item.is_property.is_(True),
            )
            .all()
        )
        out: Dict[int, List[Tuple[int, Optional[int], str]]] = defaultdict(
            list
        )
        for pid, start, end, code in rows:
            if code is not None:
                out[pid].append((start, end, code))
        return dict(out)

    def _bulk_load_property_category_windows(
        self,
        property_ids: set[int],
    ) -> Dict[int, List[Tuple[int, Optional[int], int]]]:
        """Map ``property_id`` to its category windows.

        Returns ``{property_id: [(start, end, category_id)]}``.
        """
        if not property_ids:
            return {}
        rows = (
            self.session.query(
                PropertyCategory.property_id,
                PropertyCategory.start_release_id,
                PropertyCategory.end_release_id,
                PropertyCategory.category_id,
            )
            .filter(PropertyCategory.property_id.in_(property_ids))
            .all()
        )
        out: Dict[int, List[Tuple[int, Optional[int], int]]] = defaultdict(
            list
        )
        for pid, start, end, cat_id in rows:
            if cat_id is not None:
                out[pid].append((start, end, cat_id))
        return dict(out)

    def _bulk_load_item_code_windows(
        self,
        item_ids: set[int],
    ) -> Dict[Tuple[int, int], List[Tuple[int, Optional[int], str]]]:
        """``{(item_id, category_id): [(start, end, code), ...]}``.

        An item can have ItemCategory rows in several Categories;
        keying by (item_id, category_id) keeps the lookup unambiguous
        when the caller knows which Category the item should be looked
        up in.
        """
        if not item_ids:
            return {}
        rows = (
            self.session.query(
                ItemCategory.item_id,
                ItemCategory.category_id,
                ItemCategory.start_release_id,
                ItemCategory.end_release_id,
                ItemCategory.code,
            )
            .filter(ItemCategory.item_id.in_(item_ids))
            .all()
        )
        out: Dict[Tuple[int, int], List[Tuple[int, Optional[int], str]]] = (
            defaultdict(list)
        )
        for item_id, cat_id, start, end, code in rows:
            if code is not None and cat_id is not None:
                out[(item_id, cat_id)].append((start, end, code))
        return dict(out)

    def _compute_context_versions(  # noqa: C901  — orchestrator
        self,
        context: Context,
        compositions: List[ContextComposition],
        releases: List[Release],
        property_code_windows: Dict[int, List[Tuple[int, Optional[int], str]]],
        property_category_windows: Dict[
            int, List[Tuple[int, Optional[int], int]]
        ],
        item_code_windows: Dict[
            Tuple[int, int], List[Tuple[int, Optional[int], str]]
        ],
        *,
        detail: str,
    ) -> List[Tuple[Release, Dict[str, Any]]]:
        """Emit one virtual version per fingerprint change."""
        owner_acronym = self._get_owner_acronym(context.owner_id)
        versions: List[Tuple[Release, Dict[str, Any]]] = []
        prev_fingerprint: Optional[Tuple[Tuple[str, Optional[str]], ...]] = (
            None
        )

        for rel in releases:
            pairs: List[Tuple[str, Optional[str]]] = []
            for cc in compositions:
                prop_code = self._lookup_in_windows(
                    property_code_windows.get(cc.property_id, []),
                    rel.release_id,
                )
                if prop_code is None:
                    continue
                item_code: Optional[str] = None
                if cc.item_id is not None:
                    cat_id = self._lookup_in_windows(
                        property_category_windows.get(cc.property_id, []),
                        rel.release_id,
                    )
                    if cat_id is not None:
                        item_code = self._lookup_in_windows(
                            item_code_windows.get((cc.item_id, cat_id), []),
                            rel.release_id,
                        )
                pairs.append((prop_code, item_code))
            pairs.sort()
            fingerprint = tuple(pairs)

            # Skip empty / unchanged fingerprints.
            if not fingerprint or fingerprint == prev_fingerprint:
                continue

            version_dict = _context_to_dict(
                context,
                owner_acronym=owner_acronym,
                release_code=rel.code,
                start_release_id=rel.release_id,
                compositions=pairs,
                detail=detail,
            )
            versions.append((rel, version_dict))
            prev_fingerprint = fingerprint

        return versions

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #

    def query_properties(  # noqa: C901  — pipeline orchestrator
        self,
        *,
        params: StructureParams,
        detail: str = "full",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query properties with SDMX-style filtering.

        Properties don't have a dedicated *PropertyVersion* table; their
        per-release identity lives in :class:`ItemCategory` rows whose
        ``item_id`` matches a Property (and the parent
        :class:`Category` is the meta-category that registers
        properties, typically ``_PR``). One result entry per matching
        ItemCategory row.
        """
        from dpmcore.dpm_xl.utils.filters import filter_by_release

        target_release: Optional[Release] = None
        if not params.wants_all_releases:
            target_release = self._resolve_release(params)
            if target_release is None:
                return [], 0

        # Anchor on ItemCategory + Property to get one row per
        # property-version pair (a property's "version" is its
        # ItemCategory row at the release).
        q = (
            self.session.query(
                ItemCategory, Item, Property, Category, DataType
            )
            .join(Item, Item.item_id == ItemCategory.item_id)
            .join(Property, Property.property_id == Item.item_id)
            .join(Category, Category.category_id == ItemCategory.category_id)
            .outerjoin(
                DataType, DataType.data_type_id == Property.data_type_id
            )
            .filter(Item.is_property.is_(True))
        )

        owners = None if params.is_owner_wildcard else params.owners
        if owners:
            q = (
                q.join(Concept, Item.row_guid == Concept.concept_guid)
                .join(
                    Organisation,
                    Concept.owner_id == Organisation.org_id,
                )
                .filter(Organisation.acronym.in_(owners))
            )

        if not params.is_id_wildcard:
            numeric_ids = [int(v) for v in params.ids if v.isdigit()]
            if numeric_ids:
                q = q.filter(
                    or_(
                        ItemCategory.code.in_(params.ids),
                        Property.property_id.in_(numeric_ids),
                    )
                )
            else:
                q = q.filter(ItemCategory.code.in_(params.ids))

        if target_release is not None:
            q = filter_by_release(
                q,
                start_col=ItemCategory.start_release_id,
                end_col=ItemCategory.end_release_id,
                release_id=target_release.release_id,
            )

        total = q.with_entities(func.count()).scalar() or 0
        if total == 0:
            return [], 0

        q = q.order_by(Property.property_id, ItemCategory.start_release_id)
        paginated = q.offset(offset).limit(limit).all()
        if not paginated:
            return [], total

        if detail == "allstubs":
            return [
                _property_stub_to_dict(
                    ic,
                    item=item,
                    owner_acronym=self._get_owner_acronym(item.owner_id),
                    release_code=(
                        target_release.code
                        if target_release is not None
                        else self._resolve_release_code(ic.start_release_id)
                    ),
                )
                for ic, item, _prop, _cat, _dt in paginated
            ], total

        # Bulk-load enumeration links grouped by effective release.
        # The effective release is keyed per ItemCategory row (the
        # target when pinned, else the row's own start release) — NOT
        # per property_id, which would collide across a property's
        # versions at release=* and apply one version's window to all.
        property_ids_by_release: Dict[Optional[int], set[int]] = defaultdict(
            set
        )
        for ic, _item, prop, _cat, _dt in paginated:
            effective = (
                target_release.release_id
                if target_release is not None
                else ic.start_release_id
            )
            property_ids_by_release[effective].add(prop.property_id)
        enums_by_release: Dict[Optional[int], Dict[int, Dict[str, Any]]] = {
            rid: self._load_property_enumerations(pids, release_id=rid)
            for rid, pids in property_ids_by_release.items()
        }

        results: List[Dict[str, Any]] = []
        for ic, item, prop, cat, dt in paginated:
            owner_acronym = self._get_owner_acronym(item.owner_id)
            release_code = (
                target_release.code
                if target_release is not None
                else self._resolve_release_code(ic.start_release_id)
            )
            effective = (
                target_release.release_id
                if target_release is not None
                else ic.start_release_id
            )
            enumeration = enums_by_release.get(effective, {}).get(
                prop.property_id
            )
            results.append(
                _property_to_dict(
                    ic,
                    item=item,
                    prop=prop,
                    defining_category=cat,
                    data_type=dt,
                    owner_acronym=owner_acronym,
                    release_code=release_code,
                    enumeration=enumeration,
                )
            )
        return results, total

    def _load_property_enumerations(
        self,
        property_ids: set[int],
        *,
        release_id: Optional[int],
    ) -> Dict[int, Dict[str, Any]]:
        """Resolve enumeration payloads keyed by property_id.

        A property is "enumerated" when its :class:`PropertyCategory`
        link, active at *release_id*, points at an enumerated Category.
        The enumeration members are that Category's
        :class:`ItemCategory` rows valid at the same release. Each
        member carries ``code`` + ``signature`` from its
        ItemCategory entry.
        """
        if not property_ids:
            return {}

        from dpmcore.dpm_xl.utils.filters import filter_by_release

        pc_q = (
            self.session.query(PropertyCategory, Category)
            .join(
                Category,
                Category.category_id == PropertyCategory.category_id,
            )
            .filter(
                PropertyCategory.property_id.in_(property_ids),
                Category.is_enumerated.is_(True),
            )
        )
        pc_q = filter_by_release(
            pc_q,
            start_col=PropertyCategory.start_release_id,
            end_col=PropertyCategory.end_release_id,
            release_id=release_id,
            active_only_fallback=True,
        )
        # Deterministic pick when a property links to multiple
        # enumerated categories: lowest category_id wins.
        enum_category_by_property: Dict[int, Category] = {}
        for pc, cat in pc_q.all():
            existing = enum_category_by_property.get(pc.property_id)
            if existing is None or cat.category_id < existing.category_id:
                enum_category_by_property[pc.property_id] = cat
        if not enum_category_by_property:
            return {}

        category_ids = {
            cat.category_id for cat in enum_category_by_property.values()
        }
        ic_q = (
            self.session.query(ItemCategory, Item)
            .join(Item, Item.item_id == ItemCategory.item_id)
            .filter(ItemCategory.category_id.in_(category_ids))
        )
        ic_q = filter_by_release(
            ic_q,
            start_col=ItemCategory.start_release_id,
            end_col=ItemCategory.end_release_id,
            release_id=release_id,
            active_only_fallback=True,
        )
        items_by_category: Dict[int, List[Tuple[ItemCategory, Item]]] = (
            defaultdict(list)
        )
        for ic, item in ic_q.all():
            items_by_category[ic.category_id].append((ic, item))

        result: Dict[int, Dict[str, Any]] = {}
        for property_id, cat in enum_category_by_property.items():
            result[property_id] = {
                "categoryId": cat.category_id,
                "categoryCode": cat.code,
                "categoryName": cat.name,
                "items": [
                    {
                        "itemId": item.item_id,
                        "name": item.name,
                        "code": ic.code,
                        "signature": ic.signature,
                        "isDefaultItem": ic.is_default_item,
                    }
                    for ic, item in items_by_category.get(cat.category_id, [])
                ],
            }
        return result

    # ------------------------------------------------------------------ #
    # Variables
    # ------------------------------------------------------------------ #

    def query_variables(  # noqa: C901  — pipeline orchestrator
        self,
        *,
        params: StructureParams,
        detail: str = "full",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query variables with SDMX-style filtering.

        One entry per matching :class:`VariableVersion`. Each entry
        carries the variable's intrinsic enumeration (from
        ``VariableVersion.subcategory_vid``) when present — not the
        derived enumeration that the ``/structure/table`` endpoint
        computes from header subcategories. Variables are leaves;
        ``references=children`` is silently a no-op.
        """
        from dpmcore.dpm_xl.utils.filters import filter_by_release

        target_release: Optional[Release] = None
        if not params.wants_all_releases:
            target_release = self._resolve_release(params)
            if target_release is None:
                return [], 0

        q = (
            self.session.query(VariableVersion)
            .join(
                Variable,
                Variable.variable_id == VariableVersion.variable_id,
            )
            .options(joinedload(VariableVersion.variable))
        )

        owners = None if params.is_owner_wildcard else params.owners
        if owners:
            q = (
                q.join(Concept, Variable.row_guid == Concept.concept_guid)
                .join(
                    Organisation,
                    Concept.owner_id == Organisation.org_id,
                )
                .filter(Organisation.acronym.in_(owners))
            )

        if not params.is_id_wildcard:
            numeric_ids = [int(v) for v in params.ids if v.isdigit()]
            if numeric_ids:
                q = q.filter(
                    or_(
                        VariableVersion.code.in_(params.ids),
                        Variable.variable_id.in_(numeric_ids),
                    )
                )
            else:
                q = q.filter(VariableVersion.code.in_(params.ids))

        if target_release is not None:
            q = filter_by_release(
                q,
                start_col=VariableVersion.start_release_id,
                end_col=VariableVersion.end_release_id,
                release_id=target_release.release_id,
            )

        # Count first, paginate at the DB. Variables can be on the order
        # of 100k rows; pulling them all just to slice in Python would
        # be a 3-second tax per request. ``with_entities(func.count(...))``
        # avoids SQLAlchemy's default subquery-wrapping count.
        total = (
            q.with_entities(func.count(VariableVersion.variable_vid)).scalar()
            or 0
        )
        if total == 0:
            return [], 0
        q = q.order_by(
            VariableVersion.variable_id, VariableVersion.start_release_id
        )
        paginated: List[VariableVersion] = q.offset(offset).limit(limit).all()

        if not paginated:
            return [], total

        # Effective release per row drives enumeration windowing.
        effective_release_by_vid: Dict[int, Optional[int]] = {
            vv.variable_vid: (
                target_release.release_id
                if target_release is not None
                else vv.start_release_id
            )
            for vv in paginated
        }

        if detail == "allstubs":
            return [
                _variable_standalone_stub_to_dict(
                    vv,
                    owner_acronym=self._get_owner_acronym(
                        vv.variable.owner_id if vv.variable else None
                    ),
                    release_code=(
                        target_release.code
                        if target_release is not None
                        else self._resolve_release_code(vv.start_release_id)
                    ),
                    var_type=vv.variable.type if vv.variable else None,
                )
                for vv in paginated
            ], total

        property_ids = {vv.property_id for vv in paginated if vv.property_id}
        property_names = self._bulk_load_property_names(property_ids)

        key_ids = {vv.key_id for vv in paginated if vv.key_id}
        key_signatures = self._bulk_load_key_signatures(key_ids)

        # Subcategory enumeration loads grouped by effective release.
        subcat_vids_by_release: Dict[Optional[int], set[int]] = defaultdict(
            set
        )
        for vv in paginated:
            if vv.subcategory_vid:
                subcat_vids_by_release[
                    effective_release_by_vid[vv.variable_vid]
                ].add(vv.subcategory_vid)
        subcat_enums_by_release: Dict[
            Optional[int], Dict[int, Dict[str, Any]]
        ] = {
            rid: self._load_subcategory_enumerations(svids, release_id=rid)
            for rid, svids in subcat_vids_by_release.items()
        }

        results: List[Dict[str, Any]] = []
        for vv in paginated:
            owner_acronym = self._get_owner_acronym(
                vv.variable.owner_id if vv.variable else None
            )
            release_code = (
                target_release.code
                if target_release is not None
                else self._resolve_release_code(vv.start_release_id)
            )
            property_ref: Optional[Dict[str, Any]] = None
            if vv.property_id is not None:
                property_ref = {
                    "id": vv.property_id,
                    "name": property_names.get(vv.property_id),
                }
            enumeration: Optional[Dict[str, Any]] = None
            if vv.subcategory_vid:
                rid = effective_release_by_vid[vv.variable_vid]
                enumeration = subcat_enums_by_release.get(rid, {}).get(
                    vv.subcategory_vid
                )
            results.append(
                _variable_standalone_to_dict(
                    vv,
                    owner_acronym=owner_acronym,
                    release_code=release_code,
                    var_type=vv.variable.type if vv.variable else None,
                    property_ref=property_ref,
                    key_signature=(
                        key_signatures.get(vv.key_id)
                        if vv.key_id is not None
                        else None
                    ),
                    enumeration=enumeration,
                )
            )
        return results, total

    def _bulk_load_key_signatures(
        self,
        key_ids: set[int],
    ) -> Dict[int, Optional[str]]:
        """``{key_id: CompoundKey.signature}`` in one query."""
        if not key_ids:
            return {}
        rows = (
            self.session.query(CompoundKey.key_id, CompoundKey.signature)
            .filter(CompoundKey.key_id.in_(key_ids))
            .all()
        )
        return dict(row._tuple() for row in rows)

    # ------------------------------------------------------------------ #
    # Frameworks
    # ------------------------------------------------------------------ #

    def query_frameworks(  # noqa: C901  — pipeline orchestrator
        self,
        *,
        params: StructureParams,
        detail: str = "full",
        references: str = "none",
        offset: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query frameworks with SDMX-style filtering.

        Framework itself isn't release-versioned, so the ``release``
        path segment doesn't constrain the framework set — it's used
        only to filter the ``modules`` children when
        ``references=children`` (or ``all``).
        """
        # Resolve release only for child filtering. An unresolvable
        # literal release means children come back empty without
        # erroring the framework selection.
        target_release: Optional[Release] = None
        if not params.wants_all_releases:
            target_release = self._resolve_release(params)
        child_release_resolvable = (
            params.wants_all_releases or target_release is not None
        )

        q = self.session.query(Framework)

        owners = None if params.is_owner_wildcard else params.owners
        if owners:
            q = (
                q.join(Concept, Framework.row_guid == Concept.concept_guid)
                .join(
                    Organisation,
                    Concept.owner_id == Organisation.org_id,
                )
                .filter(Organisation.acronym.in_(owners))
            )

        if not params.is_id_wildcard:
            numeric_ids = [int(v) for v in params.ids if v.isdigit()]
            if numeric_ids:
                q = q.filter(
                    or_(
                        Framework.code.in_(params.ids),
                        Framework.framework_id.in_(numeric_ids),
                    )
                )
            else:
                q = q.filter(Framework.code.in_(params.ids))

        q = q.order_by(Framework.framework_id)
        frameworks: List[Framework] = q.all()

        if not frameworks:
            return [], 0

        total = len(frameworks)
        paginated = frameworks[offset : offset + limit]

        include_children = references in ("children", "all")
        modules_by_framework: Dict[int, List[Dict[str, Any]]] = {}
        if (
            include_children
            and detail != "allstubs"
            and child_release_resolvable
        ):
            modules_by_framework = self._load_framework_children(
                paginated, target_release=target_release
            )

        results: List[Dict[str, Any]] = []
        for fw in paginated:
            owner_acronym = self._get_owner_acronym(fw.owner_id)
            if detail == "allstubs":
                entry = _framework_stub_to_dict(
                    fw, owner_acronym=owner_acronym
                )
            else:
                entry = _framework_to_dict(fw, owner_acronym=owner_acronym)
                if include_children:
                    entry["modules"] = modules_by_framework.get(
                        fw.framework_id, []
                    )
            results.append(entry)

        return results, total

    def _load_framework_children(
        self,
        frameworks: List[Framework],
        *,
        target_release: Optional[Release],
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Bulk-load ModuleVersions for the given frameworks.

        Returns ``{framework_id: [module_dict, ...]}``. Modules are
        sorted by module_id then start_release_id within each
        framework. Each module dict has the same shape that
        ``/structure/module`` returns by default (no nested tables).
        """
        from dpmcore.dpm_xl.utils.filters import filter_by_release

        if not frameworks:
            return {}

        framework_ids = [fw.framework_id for fw in frameworks]

        q = (
            self.session.query(ModuleVersion)
            .join(Module, Module.module_id == ModuleVersion.module_id)
            .options(joinedload(ModuleVersion.module))
            .filter(Module.framework_id.in_(framework_ids))
        )
        if target_release is not None:
            q = filter_by_release(
                q,
                start_col=ModuleVersion.start_release_id,
                end_col=ModuleVersion.end_release_id,
                release_id=target_release.release_id,
            )

        q = q.order_by(
            Module.framework_id,
            ModuleVersion.module_id,
            ModuleVersion.start_release_id,
        )
        module_versions: List[ModuleVersion] = q.all()
        if not module_versions:
            return {}

        module_vids = [mv.module_vid for mv in module_versions]
        parameter_vids_by_module = self._bulk_load_module_parameters(
            module_vids
        )
        # Frameworks are already in hand; build framework refs locally
        # without an extra query.
        framework_refs = {
            fw.framework_id: {
                "id": fw.framework_id,
                "code": fw.code,
                "name": fw.name,
            }
            for fw in frameworks
        }

        result: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for mv in module_versions:
            module = mv.module
            if module is None or module.framework_id is None:
                continue
            owner_acronym = self._get_owner_acronym(module.owner_id)
            release_code = (
                target_release.code
                if target_release is not None
                else self._resolve_release_code(mv.start_release_id)
            )
            entry = _module_version_to_dict(
                mv,
                owner_acronym=owner_acronym,
                release_code=release_code,
                framework_ref=framework_refs.get(module.framework_id),
                parameter_variable_vids=parameter_vids_by_module.get(
                    mv.module_vid, []
                ),
            )
            result[module.framework_id].append(entry)
        return dict(result)

    def _bulk_load_framework_refs(
        self,
        framework_ids: set[int],
    ) -> Dict[int, Dict[str, Any]]:
        """``{framework_id: {"id", "code", "name"}}`` in one query."""
        if not framework_ids:
            return {}
        rows = (
            self.session.query(
                Framework.framework_id, Framework.code, Framework.name
            )
            .filter(Framework.framework_id.in_(framework_ids))
            .all()
        )
        return {
            fid: {"id": fid, "code": code, "name": name}
            for fid, code, name in rows
        }

    def _bulk_load_module_parameters(
        self,
        module_vids: List[int],
    ) -> Dict[int, List[int]]:
        """``{module_vid: [variable_vid, ...]}`` in one query."""
        if not module_vids:
            return {}
        rows = (
            self.session.query(
                ModuleParameters.module_vid, ModuleParameters.variable_vid
            )
            .filter(ModuleParameters.module_vid.in_(module_vids))
            .order_by(
                ModuleParameters.module_vid, ModuleParameters.variable_vid
            )
            .all()
        )
        out: Dict[int, List[int]] = defaultdict(list)
        for mvid, vvid in rows:
            out[mvid].append(vvid)
        return dict(out)


# ------------------------------------------------------------------ #
# Table dict shape helpers
# ------------------------------------------------------------------ #


def _assemble_variable_blocks(
    variable_vids: set[int],
    *,
    subcat_vids_by_variable: Dict[int, set[int]],
    subcat_enums: Dict[int, Dict[str, Any]],
    vv_by_vid: Dict[int, VariableVersion],
    property_names: Dict[int, Optional[str]],
) -> List[Dict[str, Any]]:
    """Build deduplicated variable dicts from preloaded VariableVersions.

    Each dict carries a property reference and at most one enumeration.
    A variable reachable from multiple subcategories gets the lowest-id
    match deterministically. Variables in *variable_vids* that aren't
    present in *vv_by_vid* are silently skipped (the caller didn't
    preload them).
    """
    results: List[Dict[str, Any]] = []
    for vid in sorted(variable_vids):
        vv = vv_by_vid.get(vid)
        if vv is None:
            continue
        property_dict: Optional[Dict[str, Any]] = None
        if vv.property_id is not None:
            property_dict = {
                "id": vv.property_id,
                "name": property_names.get(vv.property_id),
            }
        applicable_svids = subcat_vids_by_variable.get(vid, set())
        enumeration: Optional[Dict[str, Any]] = next(
            (
                subcat_enums[svid]
                for svid in sorted(applicable_svids)
                if svid in subcat_enums
            ),
            None,
        )
        results.append(
            _variable_version_to_dict(vv, property_dict, enumeration)
        )
    return results


def _collect_subcategory_vids_per_variable(
    header_rows: List[Tuple[TableVersionHeader, Header, HeaderVersion]],
    cell_rows: List[Tuple[TableVersionCell, Cell]],
) -> Dict[int, set[int]]:
    """Map variable_vids to the subcategory_vids of their related headers.

    Related headers are:
      - the HeaderVersion that names the variable as its key_variable_vid;
      - any HeaderVersion of a header (column/row/sheet) that bounds a
        cell whose variable_vid is the one in question.
    """
    header_version_by_id: Dict[int, HeaderVersion] = {
        h.header_id: hv for _tvh, h, hv in header_rows
    }
    out: Dict[int, set[int]] = defaultdict(set)

    for _tvh, _h, hv in header_rows:
        if hv.key_variable_vid and hv.subcategory_vid:
            out[hv.key_variable_vid].add(hv.subcategory_vid)

    for tvc, cell in cell_rows:
        if not tvc.variable_vid:
            continue
        for hid in (cell.column_id, cell.row_id, cell.sheet_id):
            if hid is None:
                continue
            matched = header_version_by_id.get(hid)
            if matched and matched.subcategory_vid:
                out[tvc.variable_vid].add(matched.subcategory_vid)

    return out


def _table_stub_to_dict(
    tv: TableVersion,
    *,
    owner_acronym: Optional[str],
    release_code: Optional[str],
) -> Dict[str, Any]:
    """``detail=allstubs`` row — identifiers only."""
    return {
        "id": tv.table_id,
        "tableVersionId": tv.table_vid,
        "code": tv.code,
        "name": tv.name,
        "owner": owner_acronym,
        "release": release_code,
        "startReleaseId": tv.start_release_id,
        "endReleaseId": tv.end_release_id,
    }


def _table_to_dict(
    tv: TableVersion,
    *,
    owner_acronym: Optional[str],
    release_code: Optional[str],
    property_names: Dict[int, Optional[str]],
    headers: List[Dict[str, Any]],
    cells: List[Dict[str, Any]],
    key_variables: List[Dict[str, Any]],
    fact_variables: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Full ``detail=full`` table-version row."""
    table = tv.table
    property_ref: Optional[Dict[str, Any]] = None
    if tv.property_id is not None:
        property_ref = {
            "id": tv.property_id,
            "name": property_names.get(tv.property_id),
        }
    context_ref: Optional[Dict[str, Any]] = (
        {"id": tv.context_id} if tv.context_id is not None else None
    )

    return {
        "id": tv.table_id,
        "tableVersionId": tv.table_vid,
        "code": tv.code,
        "name": tv.name,
        "description": tv.description,
        "owner": owner_acronym,
        "release": release_code,
        "startReleaseId": tv.start_release_id,
        "endReleaseId": tv.end_release_id,
        "isAbstract": table.is_abstract if table else None,
        "hasOpenColumns": table.has_open_columns if table else None,
        "hasOpenRows": table.has_open_rows if table else None,
        "hasOpenSheets": table.has_open_sheets if table else None,
        "isNormalised": table.is_normalised if table else None,
        "isFlat": table.is_flat if table else None,
        "property": property_ref,
        "context": context_ref,
        "headers": headers,
        "cells": cells,
        "keyVariables": key_variables,
        "factVariables": fact_variables,
    }


def _header_version_to_dict(
    tvh: TableVersionHeader,
    header: Header,
    header_version: HeaderVersion,
    property_names: Dict[int, Optional[str]],
) -> Dict[str, Any]:
    """One header row in the ``headers`` array of a table entry."""
    property_ref: Optional[Dict[str, Any]] = None
    if header_version.property_id is not None:
        property_ref = {
            "id": header_version.property_id,
            "name": property_names.get(header_version.property_id),
        }
    context_ref: Optional[Dict[str, Any]] = (
        {"id": header_version.context_id}
        if header_version.context_id is not None
        else None
    )

    return {
        "id": header.header_id,
        "headerVersionId": header_version.header_vid,
        "direction": header.direction,
        "isKey": header.is_key,
        "isAttribute": header.is_attribute,
        "code": header_version.code,
        "label": header_version.label,
        "order": tvh.order,
        "parentHeaderId": tvh.parent_header_id,
        "parentFirst": tvh.parent_first,
        "isAbstractInVersion": tvh.is_abstract,
        "isUniqueInVersion": tvh.is_unique,
        "startReleaseId": header_version.start_release_id,
        "endReleaseId": header_version.end_release_id,
        "property": property_ref,
        "context": context_ref,
        "subcategoryVersionId": header_version.subcategory_vid,
        "keyVariableVersionId": header_version.key_variable_vid,
    }


def _cell_to_dict(
    tvc: TableVersionCell,
    cell: Cell,
) -> Dict[str, Any]:
    """One cell row in the ``cells`` array of a table entry."""
    return {
        "cellId": cell.cell_id,
        "cellCode": tvc.cell_code,
        "columnHeaderId": cell.column_id,
        "rowHeaderId": cell.row_id,
        "sheetHeaderId": cell.sheet_id,
        "isNullable": tvc.is_nullable,
        "isExcluded": tvc.is_excluded,
        "isVoid": tvc.is_void,
        "sign": tvc.sign,
        "variableVersionId": tvc.variable_vid,
    }


def _variable_version_to_dict(
    vv: VariableVersion,
    property_ref: Optional[Dict[str, Any]],
    enumeration: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build one variable dict for a table entry.

    ``enumeration`` is the single applicable subcategory dict, or
    None when no related header carries a subcategory. Goes into the
    table's ``keyVariables`` or ``factVariables`` array depending on
    the caller's classification.
    """
    return {
        "id": vv.variable_id,
        "versionId": vv.variable_vid,
        "code": vv.code,
        "name": vv.name,
        "isMultiValued": vv.is_multi_valued,
        "startReleaseId": vv.start_release_id,
        "endReleaseId": vv.end_release_id,
        "property": property_ref,
        "isEnumerated": enumeration is not None,
        "enumeration": enumeration,
    }


# ------------------------------------------------------------------ #
# Context dict shape helpers
# ------------------------------------------------------------------ #


def _context_to_dict(
    context: Context,
    *,
    owner_acronym: Optional[str],
    release_code: Optional[str],
    start_release_id: int,
    compositions: List[Tuple[str, Optional[str]]],
    detail: str,
) -> Dict[str, Any]:
    """One context-version row.

    ``compositions`` is the sorted list of (propertyCode, itemCode)
    pairs alive at this virtual version's start release. ``detail=
    allstubs`` strips the compositions.
    """
    if detail == "allstubs":
        return {
            "id": context.context_id,
            "owner": owner_acronym,
            "release": release_code,
            "startReleaseId": start_release_id,
        }
    return {
        "id": context.context_id,
        "signature": context.signature,
        "owner": owner_acronym,
        "release": release_code,
        "startReleaseId": start_release_id,
        "compositions": [
            {"propertyCode": pc, "itemCode": ic} for pc, ic in compositions
        ],
    }


# ------------------------------------------------------------------ #
# Property dict shape helpers
# ------------------------------------------------------------------ #


def _property_stub_to_dict(
    ic: ItemCategory,
    *,
    item: Item,
    owner_acronym: Optional[str],
    release_code: Optional[str],
) -> Dict[str, Any]:
    """``detail=allstubs`` row for a property — identifiers only."""
    return {
        "id": item.item_id,
        "code": ic.code,
        "signature": ic.signature,
        "label": item.name,
        "owner": owner_acronym,
        "release": release_code,
        "startReleaseId": ic.start_release_id,
        "endReleaseId": ic.end_release_id,
    }


def _property_to_dict(
    ic: ItemCategory,
    *,
    item: Item,
    prop: Property,
    defining_category: Category,
    data_type: Optional[DataType],
    owner_acronym: Optional[str],
    release_code: Optional[str],
    enumeration: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Full property-version row (one entry per ItemCategory row).

    The property's release-scoped identity (``code``, ``signature``,
    ``startReleaseId``, ``endReleaseId``) comes from the
    ``ItemCategory`` row. ``label`` is from the parent ``Item``;
    structural flags + data type from ``Property``;
    ``definingCategory`` is the ItemCategory's parent Category (the
    meta-category that registers the property, typically ``_PR``);
    ``enumeration`` (when present) reflects the property's
    ``PropertyCategory`` link at the release.
    """
    data_type_ref: Optional[Dict[str, Any]] = None
    if data_type is not None:
        data_type_ref = {
            "id": data_type.data_type_id,
            "code": data_type.code,
            "name": data_type.name,
        }
    return {
        "id": item.item_id,
        "code": ic.code,
        "signature": ic.signature,
        "label": item.name,
        "description": item.description,
        "owner": owner_acronym,
        "release": release_code,
        "startReleaseId": ic.start_release_id,
        "endReleaseId": ic.end_release_id,
        "isComposite": prop.is_composite,
        "isMetric": prop.is_metric,
        "valueLength": prop.value_length,
        "periodType": prop.period_type,
        "dataType": data_type_ref,
        "definingCategory": {
            "id": defining_category.category_id,
            "code": defining_category.code,
            "name": defining_category.name,
        },
        "isEnumerated": enumeration is not None,
        "enumeration": enumeration,
    }


# ------------------------------------------------------------------ #
# Variable dict shape helpers (standalone /structure/variable endpoint)
# ------------------------------------------------------------------ #


def _variable_standalone_stub_to_dict(
    vv: VariableVersion,
    *,
    owner_acronym: Optional[str],
    release_code: Optional[str],
    var_type: Optional[str],
) -> Dict[str, Any]:
    """``detail=allstubs`` row — identifiers only."""
    return {
        "id": vv.variable_id,
        "versionId": vv.variable_vid,
        "code": vv.code,
        "name": vv.name,
        "type": var_type,
        "owner": owner_acronym,
        "release": release_code,
        "startReleaseId": vv.start_release_id,
        "endReleaseId": vv.end_release_id,
    }


def _variable_standalone_to_dict(
    vv: VariableVersion,
    *,
    owner_acronym: Optional[str],
    release_code: Optional[str],
    var_type: Optional[str],
    property_ref: Optional[Dict[str, Any]],
    key_signature: Optional[str],
    enumeration: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Full standalone variable-version row.

    Enumeration comes from ``VariableVersion.subcategory_vid`` (the
    variable's intrinsic enumeration domain), not from any table
    context. Differs from :func:`_variable_version_to_dict` which is
    used inside table entries.
    """
    return {
        "id": vv.variable_id,
        "versionId": vv.variable_vid,
        "code": vv.code,
        "name": vv.name,
        "type": var_type,
        "owner": owner_acronym,
        "release": release_code,
        "startReleaseId": vv.start_release_id,
        "endReleaseId": vv.end_release_id,
        "isMultiValued": vv.is_multi_valued,
        "property": property_ref,
        "subcategoryVersionId": vv.subcategory_vid,
        "contextId": vv.context_id,
        "keyId": vv.key_id,
        "keySignature": key_signature,
        "isEnumerated": enumeration is not None,
        "enumeration": enumeration,
    }


# ------------------------------------------------------------------ #
# Framework dict shape helpers
# ------------------------------------------------------------------ #


def _framework_stub_to_dict(
    fw: Framework,
    *,
    owner_acronym: Optional[str],
) -> Dict[str, Any]:
    """``detail=allstubs`` row — identifiers only."""
    return {
        "id": fw.framework_id,
        "code": fw.code,
        "name": fw.name,
        "owner": owner_acronym,
    }


def _framework_to_dict(
    fw: Framework,
    *,
    owner_acronym: Optional[str],
) -> Dict[str, Any]:
    """Full ``detail=full`` framework row (no children).

    Caller adds ``"modules"`` after this when ``references=children``.
    """
    return {
        "id": fw.framework_id,
        "code": fw.code,
        "name": fw.name,
        "description": fw.description,
        "owner": owner_acronym,
    }


# ------------------------------------------------------------------ #
# Operator dict shape helpers
# ------------------------------------------------------------------ #


def _operator_stub_to_dict(op: Operator) -> Dict[str, Any]:
    """``detail=allstubs`` row — identifiers only."""
    return {
        "id": op.operator_id,
        "name": op.name,
        "symbol": op.symbol,
    }


def _operator_to_dict(
    op: Operator,
    *,
    arguments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Full operator row with inline ``arguments``."""
    return {
        "id": op.operator_id,
        "name": op.name,
        "symbol": op.symbol,
        "type": op.type,
        "arguments": arguments,
    }


# ------------------------------------------------------------------ #
# Operation dict shape helpers
# ------------------------------------------------------------------ #


def _operation_stub_to_dict(
    op: Operation,
    *,
    owner_acronym: Optional[str],
    version_ids: List[int],
) -> Dict[str, Any]:
    """``detail=allstubs`` row — identifiers + version VID list only."""
    return {
        "id": op.operation_id,
        "code": op.code,
        "type": op.type,
        "owner": owner_acronym,
        "operationVersionIds": version_ids,
    }


def _operation_to_dict(
    op: Operation,
    *,
    owner_acronym: Optional[str],
    versions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Full Operation row with nested ``versions``."""
    return {
        "id": op.operation_id,
        "code": op.code,
        "type": op.type,
        "source": op.source,
        "owner": owner_acronym,
        "groupOperationId": op.group_operation_id,
        "versions": versions,
    }


def _operation_version_to_dict(
    v: OperationVersion,
    *,
    release_code: Optional[str],
    nodes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """One OperationVersion entry inside an Operation's ``versions``."""
    return {
        "operationVersionId": v.operation_vid,
        "release": release_code,
        "startReleaseId": v.start_release_id,
        "endReleaseId": v.end_release_id,
        "expression": v.expression,
        "description": v.description,
        "endorsement": v.endorsement,
        "isVariantApproved": v.is_variant_approved,
        "preconditionOperationVid": v.precondition_operation_vid,
        "severityOperationVid": v.severity_operation_vid,
        "nodes": nodes,
    }


def _operation_node_to_dict(
    n: OperationNode,
    *,
    references: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """One OperationNode entry inside a version's ``nodes``.

    Nodes are returned as a flat list keyed by ``nodeId`` /
    ``parentNodeId`` — clients can reconstruct the tree by walking
    parent links. Listing them flat keeps the response stable
    regardless of tree shape.
    """
    return {
        "nodeId": n.node_id,
        "parentNodeId": n.parent_node_id,
        "operatorId": n.operator_id,
        "argumentId": n.argument_id,
        "absoluteTolerance": n.absolute_tolerance,
        "relativeTolerance": n.relative_tolerance,
        "fallbackValue": n.fallback_value,
        "useIntervalArithmetics": n.use_interval_arithmetics,
        "operandType": n.operand_type,
        "isLeaf": n.is_leaf,
        "scalar": n.scalar,
        "references": references,
    }


def _operand_reference_to_dict(
    r: OperandReference,
    *,
    locations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """One OperandReference entry inside a node's ``references``."""
    return {
        "operandReferenceId": r.operand_reference_id,
        "x": r.x,
        "y": r.y,
        "z": r.z,
        "operandReference": r.operand_reference,
        "itemId": r.item_id,
        "propertyId": r.property_id,
        "variableId": r.variable_id,
        "subcategoryId": r.subcategory_id,
        "locations": locations,
    }


def _operand_reference_location_to_dict(
    loc: OperandReferenceLocation,
) -> Dict[str, Any]:
    """One OperandReferenceLocation entry inside a reference."""
    return {
        "cellId": loc.cell_id,
        "table": loc.table,
        "row": loc.row,
        "column": loc.column,
        "sheet": loc.sheet,
    }


# ------------------------------------------------------------------ #
# DataType dict shape helpers
# ------------------------------------------------------------------ #


def _datatype_stub_to_dict(dt: DataType) -> Dict[str, Any]:
    """Compact DataType representation (also used for child expansion)."""
    return {
        "id": dt.data_type_id,
        "code": dt.code,
        "name": dt.name,
        "isActive": dt.is_active,
    }


def _datatype_to_dict(
    dt: DataType,
    *,
    child_data_type_ids: List[int],
) -> Dict[str, Any]:
    """Full ``detail=full`` data-type row.

    Caller appends ``childDataTypes`` after this when
    ``references=children``.
    """
    return {
        "id": dt.data_type_id,
        "code": dt.code,
        "name": dt.name,
        "isActive": dt.is_active,
        "parentDataTypeId": dt.parent_data_type_id,
        "childDataTypeIds": child_data_type_ids,
    }


# ------------------------------------------------------------------ #
# TableGroup dict shape helpers
# ------------------------------------------------------------------ #


def _tablegroup_stub_to_dict(
    g: TableGroup,
    *,
    owner_acronym: Optional[str],
    release_code: Optional[str],
) -> Dict[str, Any]:
    """``detail=allstubs`` row — identifiers only."""
    return {
        "id": g.table_group_id,
        "code": g.code,
        "name": g.name,
        "owner": owner_acronym,
        "release": release_code,
        "startReleaseId": g.start_release_id,
        "endReleaseId": g.end_release_id,
    }


def _tablegroup_to_dict(
    g: TableGroup,
    *,
    owner_acronym: Optional[str],
    release_code: Optional[str],
    child_table_group_ids: List[int],
) -> Dict[str, Any]:
    """Full ``detail=full`` table-group row (no expanded children).

    Caller appends ``tables`` and ``childTableGroups`` after this when
    ``references=children``. ``childTableGroupIds`` is always present
    and gives a cheap pointer to the hierarchy without requiring
    children expansion.
    """
    return {
        "id": g.table_group_id,
        "code": g.code,
        "name": g.name,
        "description": g.description,
        "type": g.type,
        "owner": owner_acronym,
        "release": release_code,
        "startReleaseId": g.start_release_id,
        "endReleaseId": g.end_release_id,
        "parentTableGroupId": g.parent_table_group_id,
        "childTableGroupIds": child_table_group_ids,
    }


# ------------------------------------------------------------------ #
# Module dict shape helpers
# ------------------------------------------------------------------ #


def _module_stub_to_dict(
    mv: ModuleVersion,
    *,
    owner_acronym: Optional[str],
    release_code: Optional[str],
) -> Dict[str, Any]:
    """``detail=allstubs`` row — identifiers only."""
    return {
        "id": mv.module_id,
        "moduleVersionId": mv.module_vid,
        "code": mv.code,
        "name": mv.name,
        "owner": owner_acronym,
        "release": release_code,
        "startReleaseId": mv.start_release_id,
        "endReleaseId": mv.end_release_id,
    }


def _module_version_to_dict(
    mv: ModuleVersion,
    *,
    owner_acronym: Optional[str],
    release_code: Optional[str],
    framework_ref: Optional[Dict[str, Any]],
    parameter_variable_vids: List[int],
) -> Dict[str, Any]:
    """Full ``detail=full`` module-version row.

    Caller adds ``"tables"`` after this when ``references=children``.
    """
    return {
        "id": mv.module_id,
        "moduleVersionId": mv.module_vid,
        "code": mv.code,
        "name": mv.name,
        "description": mv.description,
        "versionNumber": mv.version_number,
        "owner": owner_acronym,
        "release": release_code,
        "startReleaseId": mv.start_release_id,
        "endReleaseId": mv.end_release_id,
        "fromReferenceDate": (
            mv.from_reference_date.isoformat()
            if mv.from_reference_date is not None
            else None
        ),
        "toReferenceDate": (
            mv.to_reference_date.isoformat()
            if mv.to_reference_date is not None
            else None
        ),
        "isReported": mv.is_reported,
        "isCalculated": mv.is_calculated,
        "isDocumentModule": (
            mv.module.is_document_module if mv.module is not None else None
        ),
        "framework": framework_ref,
        "globalKeyId": mv.global_key_id,
        "parameterVariableVersionIds": parameter_variable_vids,
    }
