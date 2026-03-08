"""Explorer service — introspection queries ("Where is X used?")."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import and_, or_

from dpmcore.dpm_xl.utils.filters import filter_by_release
from dpmcore.orm.operations import (
    OperandReference,
    OperandReferenceLocation,
    OperationVersion,
)
from dpmcore.orm.packaging import (
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import (
    Cell,
    Header,
    HeaderVersion,
    TableVersion,
    TableVersionCell,
    TableVersionHeader,
)
from dpmcore.orm.variables import Variable, VariableVersion

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ExplorerService:
    """Introspection / reverse-lookup queries on the DPM model.

    Args:
        session: An open SQLAlchemy session.
    """

    def __init__(self, session: "Session") -> None:
        self.session = session

    def get_variable_by_code(
        self,
        variable_code: str,
        release_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Look up a variable by its code."""
        q = self.session.query(VariableVersion).filter(
            VariableVersion.code == variable_code,
        )
        if release_id is not None:
            q = filter_by_release(
                q, release_id=release_id,
                start_col=VariableVersion.startreleaseid,
                end_col=VariableVersion.endreleaseid,
            )
        row = q.first()
        return row.to_dict() if row else None

    def get_variable_usage(
        self,
        variable_vid: int,
        release_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Find all operations that reference *variable_vid*."""
        q = (
            self.session.query(
                OperandReference,
                OperandReferenceLocation,
                OperationVersion,
            )
            .join(
                OperandReferenceLocation,
                OperandReference.operandreferenceid
                == OperandReferenceLocation.operandreferenceid,
            )
            .join(
                OperationVersion,
                OperandReference.operationvid == OperationVersion.operationvid,
            )
            .filter(OperandReferenceLocation.variablevid == variable_vid)
        )
        if release_id is not None:
            q = filter_by_release(
                q, release_id=release_id,
                start_col=OperationVersion.startreleaseid,
                end_col=OperationVersion.endreleaseid,
            )
        rows = q.all()
        return [
            {
                "operand_reference": r[0].to_dict(),
                "location": r[1].to_dict(),
                "operation_version": r[2].to_dict(),
            }
            for r in rows
        ]

    def search_table(
        self,
        query: str,
        release_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search tables by code (partial match)."""
        q = self.session.query(TableVersion).filter(
            TableVersion.code.ilike(f"%{query}%"),
        )
        if release_id is not None:
            q = filter_by_release(
                q, release_id=release_id,
                start_col=TableVersion.startreleaseid,
                end_col=TableVersion.endreleaseid,
            )
        return [r.to_dict() for r in q.all()]
