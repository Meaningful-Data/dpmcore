"""Expression-level metadata lookups.

Given a DPM-XL expression, resolve the concrete DPM entities it
references — tables, headers, frameworks — with enough context to
persist them (e.g. onto a ``ValidationVersion``) without callers ever
touching the ORM.

Callers::

    with connect(url) as db:
        tables = db.services.expression_metadata.get_referenced_tables(
            expression="{tF_01.01, r0010, c0010} = 100",
            release_id=42,
        )
        headers = db.services.expression_metadata.get_referenced_headers(
            expression="{tF_01.01, r0010, c0010} = 100",
            release_id=42,
        )
        fws = db.services.expression_metadata.get_referenced_frameworks(
            expression="{tF_01.01, r0010, c0010} = 100",
            release_id=42,
        )

All three return plain ``list[dict]`` sorted deterministically. The
service holds no state beyond its SQLAlchemy session.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import and_, or_

from dpmcore.dpm_xl.ast.operands import OperandsChecking
from dpmcore.dpm_xl.utils.filters import resolve_release_id
from dpmcore.errors import SemanticError
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import (
    Header,
    HeaderVersion,
    TableVersion,
    TableVersionHeader,
)
from dpmcore.services.syntax import SyntaxService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Mapping from DPM ``Header.direction`` to the header-usage label the
# expression syntax uses ("r*"→Row, "c*"→Column, "s*"→Sheet). Kept in
# sync with the label emitted by :meth:`get_referenced_headers`.
_DIRECTION_TO_USAGE = {"X": "Row", "Y": "Column", "Z": "Sheet"}


class ExpressionMetadataService:
    """Resolve DPM entities referenced by a DPM-XL expression.

    The service parses the expression once (via ``SyntaxService`` +
    ``OperandsChecking``) and then queries the ORM to hydrate the
    referenced tables, headers, and frameworks.

    Args:
        session: An open SQLAlchemy session.
    """

    def __init__(self, session: "Session") -> None:
        """Build the service bound to ``session``."""
        self.session = session
        self._syntax = SyntaxService()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_referenced_tables(
        self,
        expression: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return the tables referenced by ``expression``.

        Each entry is a plain dict with the keys ``table_vid``,
        ``code``, ``name``, ``description``, ``module_vid``,
        ``module_code``, ``module_name``, ``module_version``.

        Result is sorted by ``(code, table_vid, module_vid)`` so
        callers can diff-persist deterministically.

        On a syntax/semantic error (or when the expression references
        nothing that resolves), returns ``[]``.
        """
        oc = self._prepare_operands(expression, release_id, release_code)
        if oc is None:
            return []

        table_vids = self._extract_table_vids(oc)
        if not table_vids:
            return []

        release_id = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )

        query = (
            self.session.query(
                TableVersion.table_vid,
                TableVersion.code,
                TableVersion.name,
                TableVersion.description,
                ModuleVersionComposition.module_vid,
                ModuleVersion.code.label("module_code"),
                ModuleVersion.name.label("module_name"),
                ModuleVersion.version_number,
            )
            .join(
                ModuleVersionComposition,
                ModuleVersionComposition.table_vid == TableVersion.table_vid,
            )
            .join(
                ModuleVersion,
                ModuleVersion.module_vid
                == ModuleVersionComposition.module_vid,
            )
            .filter(TableVersion.table_vid.in_(table_vids))
        )

        if release_id is not None:
            query = query.filter(
                ModuleVersion.start_release_id <= release_id,
                or_(
                    ModuleVersion.end_release_id.is_(None),
                    ModuleVersion.end_release_id > release_id,
                ),
            )

        rows = query.distinct().all()

        result = [
            {
                "table_vid": row.table_vid,
                "code": row.code or "",
                "name": row.name or "",
                "description": row.description or "",
                "module_vid": row.module_vid,
                "module_code": row.module_code or "",
                "module_name": row.module_name or "",
                "module_version": row.version_number or "",
            }
            for row in rows
        ]
        result.sort(
            key=lambda r: (
                r["code"],
                r["table_vid"] or 0,
                r["module_vid"] or 0,
            )
        )
        return result

    def get_referenced_headers(
        self,
        expression: str,
        release_id: Optional[int] = None,
        table_vid: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return the headers referenced by ``expression``.

        Each entry is a plain dict with ``header_vid``, ``code``,
        ``label``, ``header_type`` (one of ``"Row"``, ``"Column"``,
        ``"Sheet"``), ``table_vid``, ``table_code``, ``table_name``.

        ``header_type`` reflects the header's *use* in the expression
        (r*/c*/s*), not the catalog ``Header.direction``: two tables
        that share a header code but are transposed relative to each
        other both emit rows whose ``header_type`` matches the syntax
        the expression used.

        ``table_vid``, when passed, narrows the result to headers of
        that specific table version.

        Result is sorted deterministically by
        ``(table_vid, header_type, code, header_vid)``.

        On a syntax/semantic error, returns ``[]``.
        """
        oc = self._prepare_operands(expression, release_id, release_code)
        if oc is None or oc.data is None or oc.data.empty:
            return []

        table_vids = self._extract_table_vids(oc)
        if table_vid is not None:
            table_vids = [v for v in table_vids if v == table_vid]
        if not table_vids:
            return []

        code_usage = self._collect_header_usage(oc)
        if not code_usage:
            return []

        rows = (
            self.session.query(
                HeaderVersion.header_vid,
                HeaderVersion.code,
                HeaderVersion.label,
                TableVersionHeader.table_vid,
                Header.direction,
                TableVersion.code.label("table_code"),
                TableVersion.name.label("table_name"),
            )
            .join(
                TableVersionHeader,
                TableVersionHeader.header_vid == HeaderVersion.header_vid,
            )
            .join(Header, Header.header_id == HeaderVersion.header_id)
            .join(
                TableVersion,
                TableVersion.table_vid == TableVersionHeader.table_vid,
            )
            .filter(
                and_(
                    TableVersionHeader.table_vid.in_(table_vids),
                    HeaderVersion.code.in_(list(code_usage.keys())),
                )
            )
            .distinct()
            .all()
        )

        result: List[Dict[str, Any]] = []
        seen: set[tuple[str, str, Optional[int]]] = set()
        for row in rows:
            usages = code_usage.get(row.code or "")
            if not usages:
                continue
            # Prefer the usage whose axis matches the catalog direction
            # when the header is used on multiple axes in the same
            # expression: this makes the round-trip deterministic and
            # keeps the (code, header_type) pair singular per table.
            catalog_usage = _DIRECTION_TO_USAGE.get(row.direction or "")
            ordered = (
                [catalog_usage] + [u for u in usages if u != catalog_usage]
                if catalog_usage and catalog_usage in usages
                else list(usages)
            )
            for usage in ordered:
                key = (row.code or "", usage, row.table_vid)
                if key in seen:
                    continue
                seen.add(key)
                result.append(
                    {
                        "header_vid": row.header_vid,
                        "code": row.code or "",
                        "label": row.label or "",
                        "header_type": usage,
                        "table_vid": row.table_vid,
                        "table_code": row.table_code or "",
                        "table_name": row.table_name or "",
                    }
                )
                break

        result.sort(
            key=lambda r: (
                r["table_vid"] or 0,
                r["header_type"],
                r["code"],
                r["header_vid"] or 0,
            )
        )
        return result

    def get_referenced_frameworks(
        self,
        expression: str,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return the frameworks touched by ``expression``.

        Each entry is a plain dict with ``framework_id``, ``code``,
        ``name``, ``description``. Result is deduped and sorted by
        ``(code, framework_id)``.

        On a syntax/semantic error, returns ``[]``.
        """
        oc = self._prepare_operands(expression, release_id, release_code)
        if oc is None:
            return []

        table_vids = self._extract_table_vids(oc)
        if not table_vids:
            return []

        release_id = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )

        query = (
            self.session.query(Framework)
            .join(Module, Module.framework_id == Framework.framework_id)
            .join(ModuleVersion, ModuleVersion.module_id == Module.module_id)
            .join(
                ModuleVersionComposition,
                ModuleVersionComposition.module_vid
                == ModuleVersion.module_vid,
            )
            .filter(ModuleVersionComposition.table_vid.in_(table_vids))
        )

        if release_id is not None:
            query = query.filter(
                ModuleVersion.start_release_id <= release_id,
                or_(
                    ModuleVersion.end_release_id.is_(None),
                    ModuleVersion.end_release_id > release_id,
                ),
            )

        rows = query.distinct().all()
        result = [
            {
                "framework_id": fw.framework_id,
                "code": fw.code or "",
                "name": fw.name or "",
                "description": fw.description or "",
            }
            for fw in rows
        ]
        result.sort(key=lambda r: (r["code"], r["framework_id"] or 0))
        return result

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _prepare_operands(
        self,
        expression: str,
        release_id: Optional[int],
        release_code: Optional[str],
    ) -> Optional[OperandsChecking]:
        """Parse ``expression`` and run ``OperandsChecking``.

        Returns ``None`` when the expression cannot be parsed or when
        the semantic pass raises — callers use that to return ``[]``.
        """
        try:
            release_id = resolve_release_id(
                self.session,
                release_id=release_id,
                release_code=release_code,
            )
            ast = self._syntax.parse(expression)
            return OperandsChecking(
                session=self.session,
                expression=expression,
                ast=ast,
                release_id=release_id,
            )
        except SemanticError as exc:
            logger.debug("Expression rejected by semantics: %s", exc)
            return None
        except Exception as exc:
            logger.warning(
                "Failed to prepare operands for expression: %s", exc
            )
            return None

    @staticmethod
    def _extract_table_vids(oc: OperandsChecking) -> List[int]:
        """Return the referenced ``table_vid``s in a deterministic order."""
        if oc.data is None or "table_vid" not in oc.data.columns:
            return []
        vids = oc.data["table_vid"].dropna().unique()
        return sorted(int(v) for v in vids.tolist())

    @staticmethod
    def _collect_header_usage(
        oc: OperandsChecking,
    ) -> Dict[str, List[str]]:
        """Map each header code to its expression-usage axes.

        Uses the ``row_code``/``column_code``/``sheet_code`` columns of
        ``OperandsChecking.data``, which already reflect wildcard
        expansion. The insertion order of the axes ("Row" first, then
        "Column", then "Sheet") keeps :meth:`get_referenced_headers`
        stable across runs.
        """
        data = oc.data
        code_usage: Dict[str, List[str]] = {}
        if data is None:
            return code_usage
        for column, label in (
            ("row_code", "Row"),
            ("column_code", "Column"),
            ("sheet_code", "Sheet"),
        ):
            if column not in data.columns:
                continue
            for code in data[column].dropna().unique().tolist():
                code = str(code)
                if not code:
                    continue
                code_usage.setdefault(code, []).append(label)
        return code_usage
