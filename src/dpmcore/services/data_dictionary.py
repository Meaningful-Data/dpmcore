"""Data dictionary service — query DPM metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import distinct

from dpmcore.dpm_xl.utils.filters import (
    filter_active_only,
    filter_by_date,
    filter_by_release,
    resolve_release_id,
)
from dpmcore.orm.glossary import ItemCategory
from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import (
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import TableVersion

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class DataDictionaryService:
    """Query the DPM data dictionary.

    Args:
        session: An open SQLAlchemy session.
    """

    def __init__(self, session: "Session") -> None:
        """Build the service bound to ``session``."""
        self.session = session

    # ------------------------------------------------------------------ #
    # Releases
    # ------------------------------------------------------------------ #

    def get_releases(self) -> List[Dict[str, Any]]:
        """Return all releases ordered by date descending."""
        rows = self.session.query(Release).order_by(Release.date.desc()).all()
        return [r.to_dict() for r in rows]

    def get_release_by_id(self, release_id: int) -> Optional[Dict[str, Any]]:
        """Return a single release by ID."""
        row = (
            self.session.query(Release)
            .filter(Release.release_id == release_id)
            .first()
        )
        return row.to_dict() if row else None

    def get_release_by_code(
        self, release_code: str
    ) -> Optional[Dict[str, Any]]:
        """Return a single release by code."""
        row = (
            self.session.query(Release)
            .filter(Release.code == release_code)
            .first()
        )
        return row.to_dict() if row else None

    def get_latest_release(self) -> Optional[Dict[str, Any]]:
        """Return the most recent release."""
        row = self.session.query(Release).order_by(Release.date.desc()).first()
        return row.to_dict() if row else None

    # ------------------------------------------------------------------ #
    # Tables
    # ------------------------------------------------------------------ #

    def get_tables(
        self,
        release_id: Optional[int] = None,
        date: Optional[str] = None,
        release_code: Optional[str] = None,
    ) -> List[str]:
        """Return available table codes."""
        q = self.session.query(TableVersion.code)

        if date:
            if release_id is not None or release_code is not None:
                raise ValueError(
                    "Specify a maximum of one of release_id, "
                    "release_code or date.",
                )
            q = q.join(
                ModuleVersionComposition,
                TableVersion.table_vid == ModuleVersionComposition.table_vid,
            ).join(
                ModuleVersion,
                ModuleVersionComposition.module_vid
                == ModuleVersion.module_vid,
            )
            q = filter_by_date(
                q,
                date,
                ModuleVersion.from_reference_date,
                ModuleVersion.to_reference_date,
            )
        else:
            resolved = resolve_release_id(
                self.session, release_id=release_id, release_code=release_code
            )
            if resolved is not None:
                q = filter_by_release(
                    q,
                    release_id=resolved,
                    start_col=TableVersion.start_release_id,
                    end_col=TableVersion.end_release_id,
                )

        q = q.order_by(TableVersion.code)
        return [row[0] for row in q.all()]

    def get_table_version(
        self,
        table_code: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return table version info for a given table code."""
        release_id = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )
        q = self.session.query(TableVersion).filter(
            TableVersion.code == table_code,
        )
        if release_id is not None:
            q = filter_by_release(
                q,
                release_id=release_id,
                start_col=TableVersion.start_release_id,
                end_col=TableVersion.end_release_id,
            )
        row = q.first()
        return row.to_dict() if row else None

    # ------------------------------------------------------------------ #
    # Items
    # ------------------------------------------------------------------ #

    def get_all_item_signatures(
        self,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> List[str]:
        """Return all distinct item signatures."""
        release_id = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )
        q = self.session.query(
            distinct(ItemCategory.signature).label("signature"),
        ).filter(ItemCategory.signature.isnot(None))

        if release_id is not None:
            q = filter_by_release(
                q,
                release_id=release_id,
                start_col=ItemCategory.start_release_id,
                end_col=ItemCategory.end_release_id,
            )
        else:
            q = filter_active_only(q, ItemCategory.end_release_id)

        q = q.order_by(ItemCategory.signature)
        return [row[0] for row in q.all()]

    def get_item_categories(
        self,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> List[Tuple[str, str]]:
        """Return (code, signature) pairs for item categories."""
        release_id = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )
        q = self.session.query(
            ItemCategory.code,
            ItemCategory.signature,
        ).filter(
            ItemCategory.code.isnot(None),
            ItemCategory.signature.isnot(None),
        )

        if release_id is not None:
            q = filter_by_release(
                q,
                release_id=release_id,
                start_col=ItemCategory.start_release_id,
                end_col=ItemCategory.end_release_id,
            )

        q = q.order_by(ItemCategory.code, ItemCategory.signature)
        return [(row[0], row[1]) for row in q.all()]
