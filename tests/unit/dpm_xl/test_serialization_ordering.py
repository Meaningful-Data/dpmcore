"""The JSON serializer ranks x/y/z by stored display order.

The serializer computes cell coordinates on an independent path from
``generate_xyz``; issue #209 requires both to follow the table's display
order rather than the code text. A wildcard row selection over non-padded
codes (``1`` .. ``11``) is the discriminating case: lexicographically ``10``
and ``11`` sort right after ``1``.
"""

from types import SimpleNamespace

import pandas as pd

from dpmcore.dpm_xl.utils.serialization import ASTToJSONVisitor


def _varid(with_order: bool) -> SimpleNamespace:
    rows = [str(i) for i in range(1, 12)]  # display order 1..11
    frame: dict[str, list] = {
        "row_code": rows,
        "column_code": ["1"] * 11,
        "sheet_code": [None] * 11,
        "data_type": ["m"] * 11,
        "variable_id": list(range(11)),
        "cell_id": list(range(11)),
    }
    if with_order:
        frame["row_order"] = list(range(1, 12))
        frame["column_order"] = [1] * 11
        frame["sheet_order"] = [None] * 11
    # Wildcard rows: the row order comes entirely from the data.
    return SimpleNamespace(
        table="T",
        rows=["*"],
        cols=["1"],
        sheets=None,
        data=pd.DataFrame(frame),
    )


def _x_by_row(node: SimpleNamespace) -> dict[str, int]:
    result = ASTToJSONVisitor(with_context=None).visit_VarID(node)
    data = result["data"]
    assert isinstance(data, list)
    return {rec["row"]: rec["x"] for rec in data}


class TestSerializerCoordinateOrdering:
    def test_x_follows_display_order_for_wildcard_rows(self):
        x_by_row = _x_by_row(_varid(with_order=True))
        assert x_by_row["1"] == 1
        assert x_by_row["2"] == 2
        assert x_by_row["10"] == 10
        assert x_by_row["11"] == 11

    def test_without_order_falls_back_to_text_rank(self):
        x_by_row = _x_by_row(_varid(with_order=False))
        # Lexicographic: "1","10","11","2",... -> "10" ranks second.
        assert x_by_row["10"] == 2


def _open_sheet_varid(data_type: str) -> SimpleNamespace:
    """A single cell over an open sheet axis: one row/column, two sheets.

    Mirrors ``{tC_34.03, r0160, c0010}`` in a table whose sheet (``z``)
    axis is open, so the cell reference resolves to two data points, one
    per sheet.
    """
    frame: dict[str, list] = {
        "row_code": ["0160", "0160"],
        "column_code": ["0010", "0010"],
        "sheet_code": ["0002", "0001"],
        "data_type": [data_type, data_type],
        "variable_id": [456962, 456964],
        "cell_id": [69641, 69640],
    }
    return SimpleNamespace(
        table="C_34.03",
        rows=["0160"],
        cols=["0010"],
        sheets=["0001", "0002"],
        data=pd.DataFrame(frame),
    )


def _has_coords(entry: dict) -> bool:
    return any(k in entry for k in ("x", "y", "z"))


class TestScalarCoordinateEmission:
    """Coordinates follow datapoint multiplicity, not the cell data type.

    A scalar-typed cell (``"e"``/``"b"``/``"s"``) is normally a positionless
    value, but the moment it spans an open axis it resolves to several data
    points; each still needs a coordinate so the engine can tell them apart
    (issue #243).
    """

    def test_scalar_multi_datapoint_gets_coordinates(self):
        result = ASTToJSONVisitor().visit_VarID(_open_sheet_varid("e"))
        data = result["data"]
        assert isinstance(data, list)
        assert len(data) == 2
        assert all(_has_coords(entry) for entry in data)
        # The sheet is the only axis that varies, so each entry carries z.
        assert {entry["z"] for entry in data} == {1, 2}

    def test_numeric_multi_datapoint_unchanged(self):
        # Numeric cells already carried coordinates; scalar cells now match.
        result = ASTToJSONVisitor().visit_VarID(_open_sheet_varid("m"))
        data = result["data"]
        assert isinstance(data, list)
        assert len(data) == 2
        assert all(_has_coords(entry) for entry in data)
        assert {entry["z"] for entry in data} == {1, 2}

    def test_scalar_single_datapoint_has_no_coordinates(self):
        # A scalar cell resolving to a single data point stays positionless.
        node = SimpleNamespace(
            table="C_34.03",
            rows=["0160"],
            cols=["0010"],
            sheets=["0001"],
            data=pd.DataFrame(
                {
                    "row_code": ["0160"],
                    "column_code": ["0010"],
                    "sheet_code": ["0001"],
                    "data_type": ["e"],
                    "variable_id": [456962],
                    "cell_id": [69641],
                }
            ),
        )
        result = ASTToJSONVisitor().visit_VarID(node)
        data = result["data"]
        assert isinstance(data, list)
        assert len(data) == 1
        assert not _has_coords(data[0])

    def test_multi_datapoint_never_zero_coordinates(self):
        # Two data points sharing row and column with no sheet axis: nothing
        # distinguishes them by position, yet the engine rejects a
        # multi-entry variable whose data carry no coordinates. Each entry
        # must still keep at least one coordinate.
        node = SimpleNamespace(
            table="C_34.03",
            rows=["0160"],
            cols=["0010"],
            sheets=None,
            data=pd.DataFrame(
                {
                    "row_code": ["0160", "0160"],
                    "column_code": ["0010", "0010"],
                    "sheet_code": [None, None],
                    "data_type": ["e", "e"],
                    "variable_id": [456962, 456964],
                    "cell_id": [69641, 69640],
                }
            ),
        )
        result = ASTToJSONVisitor().visit_VarID(node)
        data = result["data"]
        assert isinstance(data, list)
        assert len(data) == 2
        assert all(_has_coords(entry) for entry in data)
