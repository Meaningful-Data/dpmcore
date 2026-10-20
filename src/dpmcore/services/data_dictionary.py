"""Data dictionary service — query DPM metadata."""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
    overload,
)

import pandas as pd
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
            key=lambda r: (compute_sort_order(r.date, r.type), r.release_id),
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
            rows,
            key=lambda r: (compute_sort_order(r.date, r.type), r.release_id),
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

        See :func:`dpmcore.services._open_keys.get_open_keys_for_tables`
        for the join path.
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
    # Cells
    # ------------------------------------------------------------------ #

    def resolve_cell_variables(
        self,
        cells: Sequence[Mapping[str, Optional[str]]],
        module_code: Optional[str] = None,
        module_version: Optional[str] = None,
        release_id: Optional[int] = None,
        release_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Resolve cell coordinates to the variable each cell carries.

        Each entry of ``cells`` is a mapping with a ``table`` code and
        optional ``row``, ``column`` and ``sheet`` codes. A coordinate
        that is missing, ``None`` or empty matches a cell without that
        axis: a table that has no sheets, or the open axis of an open
        table.

        The scope is either a module version (``module_code`` +
        ``module_version``) or a release (``release_id`` or
        ``release_code``), not both. A module version is resolved to its
        release exactly as :meth:`ASTGeneratorService.script` does
        without an explicit release, so the variable ids match the ones
        in a script generated for that module version.

        Args:
            cells: Coordinates to resolve.
            module_code: Module code, e.g. ``"FINREP9"``.
            module_version: Module version number, e.g. ``"3.3.0"``.
            release_id: Release ID, when scoping by release.
            release_code: Release code, when scoping by release.

        Returns:
            One dict per input cell, in input order, with ``table``,
            ``row``, ``column``, ``sheet``, ``variable_id`` (``int``, or
            ``None`` when unresolved) and ``error``: ``None`` when
            resolved, ``"cell_not_found"`` when the table has no such
            (non-void) cell at that scope, or ``"grey_cell"`` when the
            cell exists but carries no variable.

        Raises:
            ValueError: If the scope is missing or inconsistent, the
                module version or release is unknown, or a cell has no
                ``table``.
        """
        resolved_release_id = self._resolve_cells_release(
            module_code, module_version, release_id, release_code
        )

        coordinates = [_cell_coordinates(cell) for cell in cells]
        variables_by_table: Dict[
            str, Dict[Tuple[Optional[str], ...], Any]
        ] = {}
        for table, _, _, _ in coordinates:
            if table not in variables_by_table:
                variables_by_table[table] = self._table_cell_variables(
                    table, resolved_release_id
                )

        result: List[Dict[str, Any]] = []
        for table, row, column, sheet in coordinates:
            key = (row, column, sheet)
            table_variables = variables_by_table[table]
            variable_id = table_variables.get(key)
            error: Optional[str] = None
            if key not in table_variables:
                error = "cell_not_found"
            elif variable_id is None:
                error = "grey_cell"
            result.append(
                {
                    "table": table,
                    "row": row,
                    "column": column,
                    "sheet": sheet,
                    "variable_id": variable_id,
                    "error": error,
                }
            )
        return result

    def _resolve_cells_release(
        self,
        module_code: Optional[str],
        module_version: Optional[str],
        release_id: Optional[int],
        release_code: Optional[str],
    ) -> int:
        """Resolve the scope of :meth:`resolve_cell_variables`."""
        if (module_code is None) != (module_version is None):
            raise ValueError(
                "module_code and module_version must be given together."
            )
        if module_code is not None and module_version is not None:
            if release_id is not None or release_code is not None:
                raise ValueError(
                    "Specify either a module (module_code + "
                    "module_version) or a release (release_id or "
                    "release_code), not both."
                )
            # Same resolution as script(), so the variable ids match the
            # ones of a script generated for this module version.
            from dpmcore.services.ast_generator import ASTGeneratorService

            _, release_row = ASTGeneratorService(
                self.session
            )._resolve_release(module_code, module_version, None)
            return int(release_row.release_id)

        resolved = resolve_release_id(
            self.session, release_id=release_id, release_code=release_code
        )
        if resolved is None:
            raise ValueError(
                "Specify a module (module_code + module_version) or a "
                "release (release_id or release_code)."
            )
        return resolved

    def _table_cell_variables(
        self, table: str, release_id: int
    ) -> Dict[Tuple[Optional[str], ...], Any]:
        """Return ``{(row, column, sheet): variable_id}`` for one table.

        Grey cells map to ``None``; missing axis codes are ``None``.
        """
        from dpmcore.dpm_xl.model_queries import ViewDatapointsQuery

        data = ViewDatapointsQuery.get_table_data(
            self.session, table, release_id=release_id
        )
        cell_variables: Dict[Tuple[Optional[str], ...], Any] = {}
        columns = ["row_code", "column_code", "sheet_code", "variable_id"]
        for row, column, sheet, variable_id in data[columns].itertuples(
            index=False
        ):
            key = (
                _code_or_none(row),
                _code_or_none(column),
                _code_or_none(sheet),
            )
            value = None if pd.isna(variable_id) else int(variable_id)
            # A cell carrying a variable wins over the same cell grey.
            if cell_variables.get(key) is None:
                cell_variables[key] = value
        return cell_variables

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


def _code_or_none(value: Any) -> Optional[str]:
    """Normalise an axis code: missing (``None``/NaN/empty) -> ``None``."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    code = str(value).strip()
    return code or None


def _cell_coordinates(
    cell: Mapping[str, Optional[str]],
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """Return ``(table, row, column, sheet)`` of a cell mapping."""
    table = _code_or_none(cell.get("table"))
    if table is None:
        raise ValueError(f"Cell without a table code: {dict(cell)!r}")
    return (
        table,
        _code_or_none(cell.get("row")),
        _code_or_none(cell.get("column")),
        _code_or_none(cell.get("sheet")),
    )
