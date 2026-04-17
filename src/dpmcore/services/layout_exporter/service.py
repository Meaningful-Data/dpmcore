"""Layout exporter service — orchestrator.

Wires queries, processing, and Excel writing into a single API.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from dpmcore.services.layout_exporter import models, processing, queries
from dpmcore.services.layout_exporter.excel_writer import ExcelLayoutWriter
from dpmcore.services.layout_exporter.models import (
    DimensionMember,
    ExportConfig,
    TableLayout,
)


class LayoutExporterService:
    """Export annotated table layouts to Excel workbooks.

    Args:
        session: An open SQLAlchemy session.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def export_module(
        self,
        module_code: str,
        release_code: Optional[str] = None,
        output_path: Optional[str] = None,
        config: Optional[ExportConfig] = None,
    ) -> Path:
        """Export all tables in a module to a single workbook.

        Args:
            module_code: Module version code (e.g., 'FINREP9').
            release_code: Optional release code filter.
            output_path: Output file path. Defaults to '{module_code}.xlsx'.
            config: Export configuration flags.

        Returns:
            Path to the written file.
        """
        table_versions = queries.load_module_table_versions(
            self.session, module_code, release_code,
        )
        if not table_versions:
            msg = f"No tables found for module '{module_code}'"
            if release_code:
                msg += f" at release '{release_code}'"
            raise ValueError(msg)

        layouts = []
        for tv in table_versions:
            layout = self._build_layout(tv)
            if layout.rows or layout.columns:
                layouts.append(layout)

        out = Path(output_path or f"{module_code}.xlsx")
        self._write_workbook(layouts, out, config)
        return out

    def export_tables(
        self,
        table_codes: list[str],
        release_code: Optional[str] = None,
        output_path: Optional[str] = None,
        config: Optional[ExportConfig] = None,
    ) -> Path:
        """Export specific tables to a workbook.

        Args:
            table_codes: List of table codes (e.g., ['F_01.01', 'F_01.02']).
            release_code: Optional release code filter.
            output_path: Output file path.
            config: Export configuration flags.

        Returns:
            Path to the written file.
        """
        layouts = []
        for code in table_codes:
            tv = queries.load_table_version(
                self.session, code, release_code,
            )
            if tv is None:
                continue
            layout = self._build_layout(tv)
            if layout.rows or layout.columns:
                layouts.append(layout)

        if not layouts:
            raise ValueError(f"No valid tables found for codes: {table_codes}")

        out = Path(output_path or "tables.xlsx")
        self._write_workbook(layouts, out, config)
        return out

    def build_layout(
        self,
        table_code: str,
        release_code: Optional[str] = None,
    ) -> TableLayout:
        """Build the intermediate layout for a single table.

        Useful for programmatic access without Excel generation.
        """
        tv = queries.load_table_version(
            self.session, table_code, release_code,
        )
        if tv is None:
            raise ValueError(f"Table '{table_code}' not found")
        return self._build_layout(tv)

    def _build_layout(self, tv: object) -> TableLayout:
        """Core pipeline: query -> process -> TableLayout."""
        # Load all headers
        raw_headers = queries.load_headers(self.session, tv.table_vid)  # type: ignore[attr-defined]

        # Collect context_ids, property_ids, and subcategory_vids for batch loading
        context_ids: set[int] = set()
        property_ids: set[int] = set()
        subcategory_vids: set[int] = set()
        for tvh, header, hv in raw_headers:
            if hv.context_id:
                context_ids.add(hv.context_id)
            if hv.property_id:
                property_ids.add(hv.property_id)
            if hv.subcategory_vid:
                subcategory_vids.add(hv.subcategory_vid)

        # Batch load categorisations
        context_cats = queries.load_categorisations(
            self.session, context_ids,
        )
        property_cats = queries.load_property_as_categorisation(
            self.session, property_ids,
        )
        subcategory_info = queries.load_subcategory_info(
            self.session, subcategory_vids,
        )

        # Build sorted headers
        columns, rows, sheets = processing.build_layout_headers(
            raw_headers, context_cats, property_cats, subcategory_info,
        )

        # Load cells
        raw_cells = queries.load_cells(self.session, tv.table_vid)  # type: ignore[attr-defined]

        # Collect variable_vids for data point categorisations
        variable_vids: set[int] = set()
        for tvc, cell in raw_cells:
            if tvc.variable_vid:
                variable_vids.add(tvc.variable_vid)

        # Also collect key variable VIDs from open-row key columns
        for col in columns:
            if col.key_variable_vid:
                variable_vids.add(col.key_variable_vid)

        dp_cats = queries.load_dp_categorisations(
            self.session, variable_vids,
        )
        variable_info = queries.load_variable_info(
            self.session, variable_vids,
        )

        # Populate key variable fields on open-row key columns
        for col in columns:
            if col.key_variable_vid and col.key_variable_vid in variable_info:
                v_id, dtype, prop_name = variable_info[col.key_variable_vid]
                col.key_variable_id = v_id
                col.key_data_type_code = dtype
                col.key_property_name = prop_name

        # Build synthetic key dimension annotations for key columns
        key_variable_vids: set[int] = {
            col.key_variable_vid for col in columns if col.key_variable_vid
        }
        if key_variable_vids:
            key_vid_prop_ids = queries.load_key_variable_property_ids(
                self.session, key_variable_vids,
            )
            key_prop_ids = set(key_vid_prop_ids.values())
            key_prop_cats = queries.load_property_as_categorisation(
                self.session, key_prop_ids,
            )
            for col in columns:
                if col.key_variable_vid and col.key_variable_vid in key_vid_prop_ids:
                    prop_id = key_vid_prop_ids[col.key_variable_vid]
                    atm_dm = key_prop_cats.get(prop_id)
                    if atm_dm:
                        col.key_categorisations = [
                            DimensionMember(
                                property_id=atm_dm.property_id,
                                dimension_label=atm_dm.member_label,
                                dimension_code=atm_dm.member_code,
                                domain_code=atm_dm.domain_code,
                                member_label="",
                                member_code="",
                            ),
                        ]

        # Build cell data
        row_ids = {h.header_id for h in rows}
        col_ids = {h.header_id for h in columns}
        sheet_ids = {h.header_id for h in sheets}
        # Add default sheet ID if no explicit sheets
        if not sheet_ids:
            for tvc, cell in raw_cells:
                if cell.sheet_id:
                    sheet_ids.add(cell.sheet_id)

        cells = processing.build_cells(
            raw_cells, row_ids, col_ids, sheet_ids, dp_cats,
            variable_info,
        )

        return processing.build_table_layout(tv, columns, rows, sheets, cells)

    def _write_workbook(
        self,
        layouts: list[TableLayout],
        output_path: Path,
        config: Optional[ExportConfig] = None,
    ) -> None:
        """Write layouts to an Excel file."""
        writer = ExcelLayoutWriter(layouts, config)
        wb = writer.write()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))
        _fix_xlsx_timestamps(output_path)


def _fix_xlsx_timestamps(path: Path) -> None:
    """Fix openpyxl bug that writes invalid ISO timestamps.

    openpyxl serialises timestamps as e.g. ``2026-03-31T16:00:00+00:00Z``
    which is invalid (either ``+00:00`` or ``Z``, not both).
    Excel shows a repair dialog on open. This rewrites the offending XML
    in-place.
    """
    buf = BytesIO(path.read_bytes())
    with zipfile.ZipFile(buf, "r") as zin:
        names = zin.namelist()
        if "docProps/core.xml" not in names:
            return
        core_xml = zin.read("docProps/core.xml").decode("utf-8")
        if "+00:00Z" not in core_xml:
            return
        fixed_xml = core_xml.replace("+00:00Z", "Z")
        out = BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in names:
                data = fixed_xml.encode("utf-8") if name == "docProps/core.xml" else zin.read(name)
                zout.writestr(name, data)
    path.write_bytes(out.getvalue())
