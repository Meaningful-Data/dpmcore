"""Integration tests for LayoutExporterService."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from openpyxl import load_workbook

from dpmcore.services.layout_exporter.models import ExportConfig
from dpmcore.services.layout_exporter.service import (
    LayoutExporterService,
    _fix_xlsx_timestamps,
)
from tests.integration.services.layout_exporter._helpers import (
    add_cell,
    add_header,
    add_subcategory,
    add_table,
    add_variable_version,
    build_basic_module_with_table,
    make_module,
    make_property,
    seed_data_types,
    seed_domain_category,
    seed_property_category,
    seed_releases,
)


def test_service_init_stores_session(memory_session):
    svc = LayoutExporterService(memory_session)
    assert svc.session is memory_session


def test_export_module_writes_workbook(memory_session, tmp_path):
    build_basic_module_with_table(memory_session)
    svc = LayoutExporterService(memory_session)
    out = svc.export_module("MOD1", output_path=str(tmp_path / "x.xlsx"))
    assert out.exists()
    wb = load_workbook(out)
    assert "T1" in wb.sheetnames
    assert "Index" in wb.sheetnames


def test_export_module_default_output_path(memory_session, tmp_path):
    build_basic_module_with_table(memory_session)
    svc = LayoutExporterService(memory_session)
    cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        out = svc.export_module("MOD1")
        assert out == Path("MOD1.xlsx")
        assert out.exists()
    finally:
        os.chdir(cwd)


def test_export_module_raises_when_no_tables(memory_session):
    svc = LayoutExporterService(memory_session)
    with pytest.raises(ValueError, match="No tables found"):
        svc.export_module("UNKNOWN")


def test_export_module_raises_includes_release_in_msg(memory_session):
    svc = LayoutExporterService(memory_session)
    with pytest.raises(
        ValueError,
        match=r"No tables found.*at release 'REL_X'",
    ):
        svc.export_module("UNKNOWN", release_code="REL_X")


def test_export_module_filters_empty_layouts(memory_session, tmp_path):
    """A table with no rows/cols should not appear in the workbook."""
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    make_module(memory_session, module_id=1, module_vid=10, code="MOD1")
    # Two tables: the second has no headers and should be filtered out
    add_table(
        memory_session,
        table_id=100,
        table_vid=1000,
        code="T_OK",
        name="OK",
        module_vid=10,
        order=1,
    )
    add_table(
        memory_session,
        table_id=101,
        table_vid=1001,
        code="T_EMPTY",
        name="Empty",
        module_vid=10,
        order=2,
    )
    add_header(
        memory_session,
        table_vid=1000,
        table_id=100,
        header_id=1,
        header_vid=11,
        direction="x",
        code="010",
        label="Col",
    )
    add_header(
        memory_session,
        table_vid=1000,
        table_id=100,
        header_id=2,
        header_vid=12,
        direction="y",
        code="010",
        label="Row",
    )
    memory_session.commit()

    svc = LayoutExporterService(memory_session)
    out = svc.export_module("MOD1", output_path=str(tmp_path / "out.xlsx"))
    wb = load_workbook(out)
    assert "T_OK" in wb.sheetnames
    assert "T_EMPTY" not in wb.sheetnames


def test_export_tables_writes_workbook(memory_session, tmp_path):
    build_basic_module_with_table(memory_session)
    svc = LayoutExporterService(memory_session)
    out = svc.export_tables(["T1"], output_path=str(tmp_path / "x.xlsx"))
    assert out.exists()


def test_export_tables_default_output_path(memory_session, tmp_path):
    build_basic_module_with_table(memory_session)
    svc = LayoutExporterService(memory_session)
    cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        out = svc.export_tables(["T1"])
        assert out == Path("tables.xlsx")
        assert out.exists()
    finally:
        os.chdir(cwd)


def test_export_tables_skips_missing_codes(memory_session, tmp_path):
    build_basic_module_with_table(memory_session)
    svc = LayoutExporterService(memory_session)
    out = svc.export_tables(
        ["T1", "MISSING"], output_path=str(tmp_path / "x.xlsx")
    )
    wb = load_workbook(out)
    assert "T1" in wb.sheetnames
    assert "MISSING" not in wb.sheetnames


def test_export_tables_raises_when_all_missing(memory_session):
    svc = LayoutExporterService(memory_session)
    with pytest.raises(ValueError, match="No valid tables"):
        svc.export_tables(["NOPE1", "NOPE2"])


def test_export_tables_skips_layout_without_rows_or_cols(
    memory_session, tmp_path
):
    """An existing table with no headers is filtered out of the workbook."""
    build_basic_module_with_table(memory_session)
    add_table(
        memory_session,
        table_id=200,
        table_vid=2000,
        code="EMPTY",
        name="Empty",
    )
    memory_session.commit()
    svc = LayoutExporterService(memory_session)
    out = svc.export_tables(
        ["EMPTY", "T1"],
        output_path=str(tmp_path / "x.xlsx"),
    )
    wb = load_workbook(out)
    assert "EMPTY" not in wb.sheetnames
    assert "T1" in wb.sheetnames


def test_build_layout_skips_cell_without_variable_vid(memory_session):
    """A cell without variable_vid still produces a valid layout."""
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    seed_domain_category(memory_session, 10, "DOM")
    make_module(memory_session, module_id=1, module_vid=10, code="MODX")
    add_table(
        memory_session,
        table_id=100,
        table_vid=1000,
        code="TX",
        name="X",
        module_vid=10,
    )
    make_property(
        memory_session,
        property_id=200,
        name="Carrying amount",
        data_type_id=1,
        dim_code="qC",
        domain_category_id=10,
    )
    add_header(
        memory_session,
        table_vid=1000,
        table_id=100,
        header_id=1,
        header_vid=11,
        direction="x",
        code="010",
        label="Col",
        property_id=200,
    )
    add_header(
        memory_session,
        table_vid=1000,
        table_id=100,
        header_id=2,
        header_vid=12,
        direction="y",
        code="010",
        label="Row",
    )
    # Cell without variable_vid (None)
    add_cell(
        memory_session,
        cell_id=900,
        table_id=100,
        table_vid=1000,
        column_id=1,
        row_id=2,
        variable_vid=None,
    )
    memory_session.commit()
    svc = LayoutExporterService(memory_session)
    layout = svc.build_layout("TX")
    assert (2, 1, None) in layout.cells


def test_build_layout_key_column_without_property(memory_session):
    """Key column whose key variable points to a missing property_id.

    Triggers the ``if atm_dm:`` False branch for key-column annotations
    (atm_dm is None when the property has no Item/Property row).
    """
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    make_module(memory_session, module_id=1, module_vid=10, code="MODK")
    add_table(
        memory_session,
        table_id=100,
        table_vid=1000,
        code="TK",
        name="K",
        module_vid=10,
    )
    # Variable references a property_id that has no Item/Property,
    # so load_property_as_categorisation returns nothing for it.
    add_variable_version(
        memory_session,
        variable_id=400,
        variable_vid=4000,
        code="V",
        property_id=999,
    )
    # Open-row table: only a key column, no rows
    add_header(
        memory_session,
        table_vid=1000,
        table_id=100,
        header_id=1,
        header_vid=11,
        direction="x",
        code="010",
        label="Key",
        is_key=True,
        key_variable_vid=4000,
    )
    memory_session.commit()
    svc = LayoutExporterService(memory_session)
    layout = svc.build_layout("TK")
    assert layout.columns
    assert layout.columns[0].key_categorisations == []


def test_build_layout_returns_layout(memory_session):
    build_basic_module_with_table(memory_session)
    svc = LayoutExporterService(memory_session)
    layout = svc.build_layout("T1")
    assert layout.table_code == "T1"
    assert len(layout.columns) == 1
    assert len(layout.rows) == 1


def test_build_layout_raises_when_table_missing(memory_session):
    svc = LayoutExporterService(memory_session)
    with pytest.raises(ValueError, match="not found"):
        svc.build_layout("NOPE")


def test_build_layout_with_release_code(memory_session):
    build_basic_module_with_table(memory_session)
    svc = LayoutExporterService(memory_session)
    layout = svc.build_layout("T1", release_code="REL1")
    assert layout.table_code == "T1"


def test_build_layout_full_pipeline_with_key_columns(memory_session):
    """Exercise key-variable annotation path in _build_layout."""
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    seed_domain_category(memory_session, 20, "DOMK")

    make_module(memory_session, module_id=1, module_vid=10, code="MOD1")
    add_table(
        memory_session,
        table_id=100,
        table_vid=1000,
        code="T_KEY",
        name="Key Table",
        module_vid=10,
    )

    # Property used by the key variable
    make_property(
        memory_session,
        property_id=200,
        name="Currency",
        data_type_id=2,  # 'e'
        dim_code="qCUR",
        domain_category_id=20,
    )
    add_variable_version(
        memory_session,
        variable_id=400,
        variable_vid=4000,
        code="VK",
        property_id=200,
    )

    # Open-row layout: column with key_variable_vid, no rows
    add_header(
        memory_session,
        table_vid=1000,
        table_id=100,
        header_id=1,
        header_vid=11,
        direction="x",
        code="010",
        label="Col",
        is_key=True,
        key_variable_vid=4000,
    )

    # Subcategory referenced by header (won't be used here)
    memory_session.commit()

    svc = LayoutExporterService(memory_session)
    layout = svc.build_layout("T_KEY")
    assert len(layout.columns) == 1
    col = layout.columns[0]
    assert col.is_key is True
    assert col.key_variable_id == 400
    assert col.key_data_type_code == "e"
    assert col.key_property_name == "Currency"
    # key_categorisations should be populated (synthetic from property dim)
    assert len(col.key_categorisations) == 1
    assert col.key_categorisations[0].dimension_label == "Currency"


def test_build_layout_with_subcategory_branch(memory_session):
    """Exercise subcategory_info branch in _build_layout."""
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    seed_domain_category(memory_session, 30, "BAS")

    make_module(memory_session, module_id=1, module_vid=10, code="MOD1")
    add_table(
        memory_session,
        table_id=100,
        table_vid=1000,
        code="T_SUB",
        name="Sub Table",
        module_vid=10,
    )

    add_subcategory(
        memory_session,
        subcategory_id=1,
        subcategory_vid=11,
        category_id=30,
        code="SC1",
        description="My Sub",
    )

    add_header(
        memory_session,
        table_vid=1000,
        table_id=100,
        header_id=1,
        header_vid=11,
        direction="z",
        code="010",
        label="Sheet 1",
        subcategory_vid=11,
    )
    add_header(
        memory_session,
        table_vid=1000,
        table_id=100,
        header_id=2,
        header_vid=12,
        direction="x",
        code="010",
        label="Col",
    )
    add_header(
        memory_session,
        table_vid=1000,
        table_id=100,
        header_id=3,
        header_vid=13,
        direction="y",
        code="010",
        label="Row",
    )
    memory_session.commit()

    svc = LayoutExporterService(memory_session)
    layout = svc.build_layout("T_SUB")
    assert len(layout.sheets) == 1
    assert layout.sheets[0].subcategory_code == "SC1"
    assert layout.sheets[0].subcategory_description == "My Sub"
    assert layout.sheets[0].subcategory_cat_code == "BAS"


def test_build_layout_default_sheet_id_branch(memory_session, tmp_path):
    """When no Z headers but cells have sheet_id, that gets collected."""
    seed_releases(memory_session)
    seed_data_types(memory_session)
    seed_property_category(memory_session)
    make_module(memory_session, module_id=1, module_vid=10, code="MOD1")
    add_table(
        memory_session,
        table_id=100,
        table_vid=1000,
        code="T_DSH",
        name="Default Sheet",
        module_vid=10,
    )

    # Header used as the sheet ID (must exist as a Header row)
    add_header(
        memory_session,
        table_vid=1000,
        table_id=100,
        header_id=99,
        header_vid=99,
        direction="x",  # not z, so it's used as a default sheet id
        code="DSH",
        label="DSH",
    )
    add_header(
        memory_session,
        table_vid=1000,
        table_id=100,
        header_id=1,
        header_vid=11,
        direction="x",
        code="010",
        label="Col",
    )
    add_header(
        memory_session,
        table_vid=1000,
        table_id=100,
        header_id=2,
        header_vid=12,
        direction="y",
        code="010",
        label="Row",
    )
    add_variable_version(
        memory_session, variable_id=400, variable_vid=4000, code="V"
    )
    add_cell(
        memory_session,
        cell_id=900,
        table_id=100,
        table_vid=1000,
        column_id=1,
        row_id=2,
        sheet_id=99,  # cell has a sheet_id
        variable_vid=4000,
    )
    memory_session.commit()

    svc = LayoutExporterService(memory_session)
    layout = svc.build_layout("T_DSH")
    # The cell should be present using the cell's sheet_id
    assert (2, 1, 99) in layout.cells


# ---------------------------------------------------------------- #
# _fix_xlsx_timestamps
# ---------------------------------------------------------------- #


def test_fix_xlsx_timestamps_replaces_offset(tmp_path):
    """When core.xml contains '+00:00Z' it must be replaced with 'Z'."""
    import zipfile

    path = tmp_path / "weird.xlsx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "docProps/core.xml",
            "<root>2026-03-31T16:00:00+00:00Z</root>",
        )
        zf.writestr("other.xml", "data")
    _fix_xlsx_timestamps(path)
    with zipfile.ZipFile(path, "r") as zf:
        core = zf.read("docProps/core.xml").decode("utf-8")
    assert "+00:00Z" not in core
    assert "+00:00" not in core
    assert "Z</root>" in core


def test_fix_xlsx_timestamps_no_op_without_core_xml(tmp_path):
    """Workbook without docProps/core.xml is left untouched."""
    import zipfile

    path = tmp_path / "no_core.xlsx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("other.xml", "x")
    raw = path.read_bytes()
    _fix_xlsx_timestamps(path)
    assert path.read_bytes() == raw


def test_fix_xlsx_timestamps_no_op_when_no_marker(tmp_path):
    """Core.xml without '+00:00Z' marker is left untouched."""
    import zipfile

    path = tmp_path / "ok.xlsx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "docProps/core.xml",
            "<root>2026-03-31T16:00:00Z</root>",
        )
    raw = path.read_bytes()
    _fix_xlsx_timestamps(path)
    assert path.read_bytes() == raw


_ = (ExportConfig, tempfile)
