"""Explorer service — introspection queries ("Where is X used?")."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from dpmcore.dpm_xl.utils.filters import filter_by_release
from dpmcore.orm.operations import (
    OperandReference,
    OperandReferenceLocation,
    OperationNode,
    OperationVersion,
)
from dpmcore.orm.rendering import (
    TableVersion,
)
from dpmcore.orm.variables import VariableVersion

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
                q,
                release_id=release_id,
                start_col=VariableVersion.start_release_id,
                end_col=VariableVersion.end_release_id,
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
                OperandReference.operand_reference_id
                == OperandReferenceLocation.operand_reference_id,
            )
            .join(
                OperationNode,
                OperandReference.node_id == OperationNode.node_id,
            )
            .join(
                OperationVersion,
                OperationNode.operation_vid == OperationVersion.operation_vid,
            )
            .filter(OperandReference.variable_id == variable_vid)
        )
        if release_id is not None:
            q = filter_by_release(
                q,
                release_id=release_id,
                start_col=OperationVersion.start_release_id,
                end_col=OperationVersion.end_release_id,
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
                q,
                release_id=release_id,
                start_col=TableVersion.start_release_id,
                end_col=TableVersion.end_release_id,
            )
        return [r.to_dict() for r in q.all()]
