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
