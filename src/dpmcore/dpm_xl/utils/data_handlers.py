from collections.abc import Iterable, Sequence
from typing import Any, cast

import pandas as pd

from dpmcore.dpm_xl.utils.tokens import *
from dpmcore.errors import SemanticError


def filter_data_by_cell_element(
    series: pd.DataFrame,
    cell_elements: Sequence[str],
    element_name: str,
    table_code: str,
) -> pd.DataFrame:
    """Filter data by cell elements
    :param series: data to be filtered
    :param cell_elements: rows, columns or sheets using to filter data
    :param element_name: name of cell elements using to filter data
    :return: filtered data.
    """
    if len(cell_elements) == 1 and "-" not in cell_elements[0]:
        series = series[series[element_name] == cell_elements[0]]
    elif len(cell_elements) == 1 and "-" in cell_elements[0]:
        limits = cell_elements[0].split("-")
        series = series[series[element_name].between(limits[0], limits[1])]
    else:
        range_control = any("-" in x for x in cell_elements)
        if range_control:  # Range in cell elements, we must separate them
            data_range = []
            data_single = []
            for x in cell_elements:
                if "-" in x:
                    limits = x.split("-")
                    data_range += list(
                        series[
                            series[element_name].between(limits[0], limits[1])
                        ][element_name].unique()
                    )
                else:
                    data_single.append(x)
            cell_elements = sorted(set(data_range + data_single))
        series = series[series[element_name].isin(cell_elements)]
        cells_not_found = [
            x
            for x in cell_elements
            if x not in list(series[element_name].unique())
        ]

        if cells_not_found:
            header = (
                "rows"
                if element_name == ROW_CODE
                else "columns"
                if element_name == COLUMN_CODE
                else "sheets"
            )
            not_found_expr: str | None = (
                ", ".join([f"{header[0]}{x}" for x in cells_not_found])
                if cells_not_found
                else None
            )
            op_pos: list[str | None] = [table_code, not_found_expr]
            cell_exp = ", ".join(x for x in op_pos if x is not None)
            raise SemanticError("1-2", cell_expression=cell_exp)
    return series


def filter_all_data(
    data: pd.DataFrame,
    table_code: str,
    rows: Sequence[str],
    cols: Sequence[str],
    sheets: Sequence[str],
) -> pd.DataFrame:
    df = data[data["table_code"] == table_code].reset_index(drop=True)
    if rows and rows[0] != "*":
        df = filter_data_by_cell_element(df, rows, ROW_CODE, table_code)
    if cols and cols[0] != "*":
        df = filter_data_by_cell_element(df, cols, COLUMN_CODE, table_code)
    if sheets and sheets[0] != "*":
        df = filter_data_by_cell_element(df, sheets, SHEET_CODE, table_code)
    df = df.reset_index(drop=True)
    return df


def generate_xyz(data: pd.DataFrame) -> list[dict[str, Any]]:

    for letter in [INDEX_X, INDEX_Y, INDEX_Z]:
        data[letter] = None

    number_of_rows = len(list(data[ROW_CODE].unique()))
    number_of_columns = len(list(data[COLUMN_CODE].unique()))
    number_of_sheets = len(list(data[SHEET_CODE].unique()))
    group: list[str] = []

    if number_of_rows > 1:
        data.sort_values(by=[ROW_CODE], inplace=True)
        data[INDEX_X] = data[ROW_CODE].rank(method="dense").astype(int)
        group.append(ROW_CODE)

    if number_of_columns > 1:
        data.sort_values(by=[COLUMN_CODE], inplace=True)
        if data[INDEX_X].isnull().all():
            data[INDEX_Y] = data[COLUMN_CODE].rank(method="dense").astype(int)
        else:
            col_groups = cast(
                Iterable[tuple[Any, pd.DataFrame]], data.groupby(ROW_CODE)
            )
            for _, group_data in col_groups:
                group_data.sort_values(by=[COLUMN_CODE], inplace=True)
                group_data[INDEX_Y] = (
                    group_data[COLUMN_CODE].rank(method="dense").astype(int)
                )
                # Add to data[INDEX_Y] the values of group_data[INDEX_Y]
                data.loc[group_data.index, INDEX_Y] = group_data[INDEX_Y]
        group.append(COLUMN_CODE)

    if number_of_sheets > 1:
        data.sort_values(by=[SHEET_CODE], inplace=True)
        if len(group) == 0:
            data[INDEX_Z] = data[SHEET_CODE].rank(method="dense").astype(int)
        else:
            sheet_groups = cast(
                Iterable[tuple[Any, pd.DataFrame]], data.groupby(group)
            )
            for _, group_data in sheet_groups:
                group_data.sort_values(by=[SHEET_CODE], inplace=True)
                group_data[INDEX_Z] = (
                    group_data[SHEET_CODE].rank(method="dense").astype(int)
                )
                data.loc[group_data.index, INDEX_Z] = group_data[INDEX_Z]
        group.append(SHEET_CODE)
    if len(group) > 0:
        data.sort_values(by=group, inplace=True)
    data.drop_duplicates(keep="first", inplace=True)
    list_xyz = cast(
        list[dict[str, Any]], data.to_dict(orient="records")
    )
    return list_xyz
