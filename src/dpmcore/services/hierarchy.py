"""Hierarchy service — framework / module / table tree queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import and_, or_

from dpmcore.dpm_xl.utils.filters import filter_by_release
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import (
    Cell,
    Header,
    HeaderVersion,
    Table,
    TableVersion,
    TableVersionCell,
    TableVersionHeader,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class HierarchyService:
    """Hierarchical queries on the DPM structure.

    Args:
        session: An open SQLAlchemy session.
    """

    def __init__(self, session: "Session") -> None:
        self.session = session

    def get_all_frameworks(
        self,
        release_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return all frameworks, optionally filtered by release."""
        q = self.session.query(Framework)
        return [r.to_dict() for r in q.all()]

    def get_module_version(
        self,
        module_code: str,
        release_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return module version info for a given module code."""
        q = (
            self.session.query(ModuleVersion)
            .join(Module, ModuleVersion.module_id == Module.module_id)
            .filter(Module.code == module_code)
        )
        if release_id is not None:
            q = filter_by_release(
                q, release_id=release_id,
                start_col=ModuleVersion.start_release_id,
                end_col=ModuleVersion.end_release_id,
            )
        row = q.first()
        return row.to_dict() if row else None

    def get_table_details(
        self,
        table_code: str,
        release_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return table version with headers and cells."""
        q = self.session.query(TableVersion).filter(
            TableVersion.code == table_code,
        )
        if release_id is not None:
            q = filter_by_release(
                q, release_id=release_id,
                start_col=TableVersion.start_release_id,
                end_col=TableVersion.end_release_id,
            )
        tv = q.first()
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

    def get_tables_for_module(
        self,
        module_code: str,
        release_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return all tables belonging to a module."""
        q = (
            self.session.query(TableVersion)
            .join(
                ModuleVersionComposition,
                TableVersion.table_vid == ModuleVersionComposition.table_vid,
            )
            .join(
                ModuleVersion,
                ModuleVersionComposition.module_vid == ModuleVersion.module_vid,
            )
            .join(Module, ModuleVersion.module_id == Module.module_id)
            .filter(Module.code == module_code)
        )
        if release_id is not None:
            q = filter_by_release(
                q, release_id=release_id,
                start_col=ModuleVersion.start_release_id,
                end_col=ModuleVersion.end_release_id,
            )
        return [r.to_dict() for r in q.all()]
