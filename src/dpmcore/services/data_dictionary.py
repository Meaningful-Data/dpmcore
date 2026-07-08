"""Data dictionary service — query DPM metadata."""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    Union,
    overload,
)

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
from dpmcore.orm.release_sort_order import compute_sort_order
from dpmcore.orm.rendering import TableVersion
from dpmcore.services._open_keys import (
    get_open_keys_for_tables as _get_open_keys_for_tables,
)

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
        """Return all releases, latest first.

        Ordered by the date-based sort order (see
        :func:`compute_sort_order`), so an undated (unpublished) working
        release ranks as the latest and comes first; ties break by
        ``release_id`` for determinism.
        """
        rows = self.session.query(Release).all()
        rows.sort(
            key=lambda r: (compute_sort_order(r.date), r.release_id),
            reverse=True,
        )
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
        """Return the latest release by the date-based sort order.

        An undated (unpublished) working release ranks as the latest;
        ties break by ``release_id`` for determinism.
        """
        rows = self.session.query(Release).all()
        if not rows:
            return None
        row = max(
            rows, key=lambda r: (compute_sort_order(r.date), r.release_id)
        )
        return row.to_dict()

    # ------------------------------------------------------------------ #
    # Tables
    # ------------------------------------------------------------------ #

    @overload
    def get_tables(
        self,
        release_id: Optional[int] = ...,
        date: Optional[str] = ...,
        release_code: Optional[str] = ...,
        verbose: Literal[False] = ...,
    ) -> List[str]:
        pass

    @overload
    def get_tables(
        self,
        release_id: Optional[int] = ...,
        date: Optional[str] = ...,
        release_code: Optional[str] = ...,
        *,
        verbose: Literal[True],
    ) -> List[Dict[str, Optional[str]]]:
        pass

    def get_tables(
        self,
        release_id: Optional[int] = None,
        date: Optional[str] = None,
        release_code: Optional[str] = None,
        verbose: bool = False,
    ) -> Union[List[str], List[Dict[str, Optional[str]]]]:
        """Return available tables.

        When ``verbose`` is ``False`` (default) returns a list of table
        codes. When ``verbose`` is ``True`` returns a list of dicts with
        ``{code, name, description}`` for each active table version.
        """
        q: Any
        if verbose:
            q = self.session.query(
                TableVersion.code,
                TableVersion.name,
                TableVersion.description,
            )
        else:
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
        if verbose:
            return [
                {"code": r[0], "name": r[1], "description": r[2]}
                for r in q.all()
            ]
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

    def get_open_keys_for_tables(
        self,
        table_codes: List[str],
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> Dict[str, Dict[str, str]]:
        """Return ``{table_code: {property_code: data_type_code}}``.

        Identifies the open-key (compound-key) variables of each table
        by walking ``TableVersion`` → ``KeyComposition`` →
        ``VariableVersion`` → ``Property`` → ``ItemCategory`` (for the
        property code) → ``DataType`` (for the type code).
        """
        release_id = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )
        return _get_open_keys_for_tables(
            self.session, table_codes, release_id=release_id
        )

    def get_open_keys_for_table(
        self,
        table_code: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> Dict[str, str]:
        """Return ``{property_code: data_type_code}`` for one table."""
        return self.get_open_keys_for_tables(
            [table_code],
            release_id=release_id,
            release_code=release_code,
        ).get(table_code, {})

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
