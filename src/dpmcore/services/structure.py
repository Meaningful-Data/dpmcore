"""Structure service — SDMX-style queries for DPM artefacts."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import or_

from dpmcore.orm.glossary import Category, Item, ItemCategory
from dpmcore.orm.infrastructure import Concept, Organisation, Release
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
        "createdRelease": category.created_release,
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
        self._owner_cache: Dict[int, Optional[str]] = {}

    # ------------------------------------------------------------------ #
    # Releases
    # ------------------------------------------------------------------ #

    def _get_all_releases(self) -> List[Release]:
        """Return all releases sorted by date ascending (cached)."""
        if self._releases_cache is None:
            self._releases_cache = (
                self.session.query(Release).order_by(Release.date.asc()).all()
            )
        return self._releases_cache

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
            if (
                category.created_release is not None
                and rel.release_id < category.created_release
            ):
                continue

            alive_ics = [
                ic
                for ic in ics
                if ic.start_release_id <= rel.release_id
                and (
                    ic.end_release_id is None
                    or ic.end_release_id >= rel.release_id
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

    @staticmethod
    def _version_at_release(
        versions: List[Tuple[Release, Dict[str, Any]]],
        target_release: Release,
    ) -> Optional[Dict[str, Any]]:
        """Find the version active at *target_release*.

        Returns the last version whose release_id <= target's.
        """
        active: Optional[Dict[str, Any]] = None
        for rel, version_dict in versions:
            if rel.release_id <= target_release.release_id:
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
