from collections.abc import Iterable, Sequence
from typing import Any, cast

import pandas as pd

from dpmcore.dpm_xl.utils.range_resolution import (
    build_axis_order_map,
    sort_by_order,
)
from dpmcore.dpm_xl.utils.tokens import *
from dpmcore.errors import SemanticError

# Stored-order column that carries the display order for each *_code column.
_ORDER_COLUMN = {
    ROW_CODE: ROW_ORDER,
    COLUMN_CODE: COLUMN_ORDER,
    SHEET_CODE: SHEET_ORDER,
}


def _raise_cells_not_found(
    cells_not_found: Sequence[str],
    element_name: str,
    table_code: str,
) -> None:
    """Raise a ``1-2`` (cell not found) error for missing selector codes.

    The codes are echoed in selector notation (``c0040``, ``r0010``, ...) so
    the message mirrors how the codes are written in a DPM-XL expression.
    """
    header = (
        "rows"
        if element_name == ROW_CODE
        else "columns"
        if element_name == COLUMN_CODE
        else "sheets"
    )
    not_found_expr = ", ".join([f"{header[0]}{x}" for x in cells_not_found])
    op_pos: list[str | None] = [table_code, not_found_expr]
    cell_exp = ", ".join(x for x in op_pos if x is not None)
    raise SemanticError("1-2", cell_expression=cell_exp)


def _check_range_endpoints(
    available: set[str],
    limits: Sequence[str],
    element_name: str,
    table_code: str,
) -> None:
    """Verify both endpoints of a range exist among ``available`` codes.

    A range such as ``c0010-0030`` resolves via a between-comparison, which
    silently accepts a bogus endpoint (e.g. the typo ``c0010-c0030`` reads the
    second endpoint as code ``c0030``): the comparison still spans the real
    codes in between, so no cell is missing and the mistake goes unnoticed.
    Checking the endpoints themselves — the same existence check already
    applied to the table code and to listed cells — surfaces the error.
    """
    missing = [
        endpoint
        for endpoint in dict.fromkeys((limits[0], limits[1]))
        if endpoint not in available
    ]
    if missing:
        _raise_cells_not_found(missing, element_name, table_code)


def filter_data_by_cell_element(
    series: pd.DataFrame,
    cell_elements: Sequence[str],
    element_name: str,
    table_code: str,
    valid_codes: set[str] | None = None,
    order_map: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Filter data by cell elements.

    :param series: data to be filtered
    :param cell_elements: rows, columns or sheets using to filter data
    :param element_name: name of cell elements using to filter data
    :param table_code: table code, echoed in "cell not found" errors
    :param valid_codes: the full set of codes defined for ``element_name``
        in the table, used only to validate range endpoints. When ``None``
        the codes present in ``series`` are used. Callers that narrow one
        axis after another (see :func:`filter_all_data`) must pass the
        table-wide set, so a range endpoint that is a real code but does
        not intersect the already-selected cells is not misreported as a
        missing cell.
    :param order_map: the table-wide ``{code: order}`` display order for
        ``element_name``. When provided (the axis is fully ordered), range
        membership follows the stored order instead of the code text, so
        non-numeric / non-padded / mixed-width codes resolve correctly. A
        reversed range (``order[lo] > order[hi]``) resolves to nothing,
        preserving today's "cell not found" behaviour. When ``None`` the code
        text is compared, as before.
    :return: filtered data.
    """
    if valid_codes is None:
        valid_codes = set(series[element_name])
    order_col = _ORDER_COLUMN.get(element_name)
    use_order = (
        bool(order_map)
        and order_col is not None
        and (order_col in series.columns)
    )

    def _in_range(lo: str, hi: str) -> "pd.Series[bool]":
        """Boolean mask of ``series`` rows inside the range ``lo``-``hi``."""
        if use_order and order_map is not None and order_col is not None:
            lo_order = order_map.get(lo)
            hi_order = order_map.get(hi)
            if lo_order is None or hi_order is None or lo_order > hi_order:
                return pd.Series(False, index=series.index)
            return series[order_col].between(lo_order, hi_order)
        return series[element_name].between(lo, hi)

    if len(cell_elements) == 1 and "-" not in cell_elements[0]:
        series = series[series[element_name] == cell_elements[0]]
    elif len(cell_elements) == 1 and "-" in cell_elements[0]:
        limits = cell_elements[0].split("-")
        _check_range_endpoints(valid_codes, limits, element_name, table_code)
        series = series[_in_range(limits[0], limits[1])]
    else:
        range_control = any("-" in x for x in cell_elements)
        if range_control:  # Range in cell elements, we must separate them
            data_range = []
            data_single = []
            for x in cell_elements:
                if "-" in x:
                    limits = x.split("-")
                    _check_range_endpoints(
                        valid_codes, limits, element_name, table_code
                    )
                    data_range += list(
                        series[_in_range(limits[0], limits[1])][
                            element_name
                        ].unique()
                    )
                else:
                    data_single.append(x)
            combined = set(data_range + data_single)
            cell_elements = (
                sort_by_order(combined, order_map)
                if use_order and order_map is not None
                else sorted(combined)
            )
        series = series[series[element_name].isin(cell_elements)]
        cells_not_found = [
            x
            for x in cell_elements
            if x not in list(series[element_name].unique())
        ]

        if cells_not_found:
            _raise_cells_not_found(cells_not_found, element_name, table_code)
    return series


def filter_all_data(
    data: pd.DataFrame,
    table_code: str,
    rows: Sequence[str],
    cols: Sequence[str],
    sheets: Sequence[str],
) -> pd.DataFrame:
    df = data[data["table_code"] == table_code].reset_index(drop=True)
    # Capture each axis's full code universe from the table-scoped frame
    # before any narrowing, so range endpoints are validated against every
    # code defined for the table -- not just the codes that survive the
    # preceding axis filters, which would reject a valid endpoint that does
    # not intersect the already-selected cells in a sparse table.
    row_codes = set(df[ROW_CODE])
    col_codes = set(df[COLUMN_CODE])
    sheet_codes = set(df[SHEET_CODE])
    # Build each axis's table-wide {code: order} map so ranges resolve by the
    # stored display order rather than by code text. ``build_axis_order_map``
    # returns ``None`` when the axis is not fully ordered, which makes
    # ``filter_data_by_cell_element`` fall back to string comparison.
    row_orders = _axis_order_map(df, ROW_CODE, ROW_ORDER)
    col_orders = _axis_order_map(df, COLUMN_CODE, COLUMN_ORDER)
    sheet_orders = _axis_order_map(df, SHEET_CODE, SHEET_ORDER)
    if rows and rows[0] != "*":
        df = filter_data_by_cell_element(
            df, rows, ROW_CODE, table_code, row_codes, row_orders
        )
    if cols and cols[0] != "*":
        df = filter_data_by_cell_element(
            df, cols, COLUMN_CODE, table_code, col_codes, col_orders
        )
    if sheets and sheets[0] != "*":
        df = filter_data_by_cell_element(
            df, sheets, SHEET_CODE, table_code, sheet_codes, sheet_orders
        )
    df = df.reset_index(drop=True)
    return df


def _axis_order_map(
    df: pd.DataFrame, code_col: str, order_col: str
) -> dict[str, int] | None:
    """Build ``{code: order}`` for one axis of ``df`` (``None`` if unordered).

    Returns ``None`` when the order column is absent or the axis is not fully
    ordered, so the caller falls back to string comparison.
    """
    if order_col not in df.columns:
        return None
    return build_axis_order_map(df[code_col], df[order_col])


def _rank_column(data: pd.DataFrame, code_col: str, order_col: str) -> str:
    """Return the column to rank/sort an axis by: order when fully populated.

    Uses the stored display-order column when it is present and has no missing
    values (all-or-nothing per axis), so ``r10`` ranks after ``r9`` rather than
    after ``r1``. Falls back to the code column otherwise, preserving the
    previous text-based ranking for tables without a usable order.
    """
    if order_col in data.columns and not data[order_col].isna().any():
        return order_col
    return code_col


def generate_xyz(data: pd.DataFrame) -> list[dict[str, Any]]:

    for letter in [INDEX_X, INDEX_Y, INDEX_Z]:
        data[letter] = None

    number_of_rows = len(list(data[ROW_CODE].unique()))
    number_of_columns = len(list(data[COLUMN_CODE].unique()))
    number_of_sheets = len(list(data[SHEET_CODE].unique()))
    group: list[str] = []

    # Rank/sort each axis by its stored display order when available, so the
    # X/Y/Z coordinates follow the table layout instead of the code text.
    # This is applied to whatever codes are present, so it fixes wildcard and
    # explicit-list selections too, not only ranges.
    row_key = _rank_column(data, ROW_CODE, ROW_ORDER)
    col_key = _rank_column(data, COLUMN_CODE, COLUMN_ORDER)
    sheet_key = _rank_column(data, SHEET_CODE, SHEET_ORDER)

    if number_of_rows > 1:
        data.sort_values(by=[row_key], inplace=True)
        data[INDEX_X] = data[row_key].rank(method="dense").astype(int)
        group.append(row_key)

    if number_of_columns > 1:
        data.sort_values(by=[col_key], inplace=True)
        if data[INDEX_X].isnull().all():
            data[INDEX_Y] = data[col_key].rank(method="dense").astype(int)
        else:
            col_groups = cast(
                Iterable[tuple[Any, pd.DataFrame]], data.groupby(row_key)
            )
            for _, group_data in col_groups:
                group_data.sort_values(by=[col_key], inplace=True)
                group_data[INDEX_Y] = (
                    group_data[col_key].rank(method="dense").astype(int)
                )
                # Add to data[INDEX_Y] the values of group_data[INDEX_Y]
                data.loc[group_data.index, INDEX_Y] = group_data[INDEX_Y]
        group.append(col_key)

    if number_of_sheets > 1:
        data.sort_values(by=[sheet_key], inplace=True)
        if len(group) == 0:
            data[INDEX_Z] = data[sheet_key].rank(method="dense").astype(int)
        else:
            sheet_groups = cast(
                Iterable[tuple[Any, pd.DataFrame]], data.groupby(group)
            )
            for _, group_data in sheet_groups:
                group_data.sort_values(by=[sheet_key], inplace=True)
                group_data[INDEX_Z] = (
                    group_data[sheet_key].rank(method="dense").astype(int)
                )
                data.loc[group_data.index, INDEX_Z] = group_data[INDEX_Z]
        group.append(sheet_key)
    if len(group) > 0:
        data.sort_values(by=group, inplace=True)
    data.drop_duplicates(keep="first", inplace=True)
    # The order columns are internal ranking helpers; drop them so the records
    # keep their previous shape (they never reach the engine output).
    data = data.drop(
        columns=[ROW_ORDER, COLUMN_ORDER, SHEET_ORDER], errors="ignore"
    )
    list_xyz = cast(list[dict[str, Any]], data.to_dict(orient="records"))
    return list_xyz
