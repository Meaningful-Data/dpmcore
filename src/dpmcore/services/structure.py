"""Structure service — SDMX-style queries for DPM artefacts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from dpmcore.orm.infrastructure import Concept, Organisation, Release

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


class StructureService:
    """Query DPM structural artefacts via SDMX-style parameters.

    Args:
        session: An open SQLAlchemy session.
    """

    def __init__(self, session: "Session") -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Releases
    # ------------------------------------------------------------------ #

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
        owner_ids: List[int],
    ) -> List[Dict[str, Any]]:
        """Return deduplicated organisations for a set of owner IDs."""
        unique = [oid for oid in set(owner_ids) if oid is not None]
        if not unique:
            return []
        orgs = (
            self.session.query(Organisation)
            .filter(Organisation.org_id.in_(unique))
            .all()
        )
        return [_organisation_to_dict(o) for o in orgs]
