"""Semantic validation tests for analytic (windowing) aggregate operators."""

import pandas as pd
import pytest

from dpmcore.dpm_xl.ast.nodes import (
    AnalyticClause,
    OrderItem,
    WindowBoundary,
    WindowClause,
)
from dpmcore.dpm_xl.operators.aggregate import Avg, Count, Rank, Sum
from dpmcore.dpm_xl.symbols import (
    FactComponent,
    KeyComponent,
    RecordSet,
    Structure,
)
from dpmcore.dpm_xl.types.scalar import Integer, Number, String
from dpmcore.dpm_xl.utils.tokens import STANDARD
from dpmcore.errors import SemanticError


def _make_rs(fact_type=None, key_names: list[str] | None = None) -> RecordSet:
    if fact_type is None:
        fact_type = Number()
    if key_names is None:
        key_names = ["r", "c"]
    components = [
        KeyComponent(k, Number(), STANDARD, "test") for k in key_names
    ]
    components.append(FactComponent(fact_type, "test"))
    structure = Structure(components)
    return RecordSet(structure, "ds", "ds")


def _analytic(
    partition_by: list[str] | None = None,
    order_by: list[str] | None = None,
) -> AnalyticClause:
    ob = [OrderItem(k) for k in (order_by or [])]
    return AnalyticClause(
        partition_by=partition_by or [],
        order_by=ob,
        window=None,
    )


def _window_clause(
    start: str = "unbounded_preceding",
    end: str = "current_data_point",
    frame_type: str = "data_points",
) -> WindowClause:
    return WindowClause(
        frame_type=frame_type,
        start=WindowBoundary(start),
        end=WindowBoundary(end),
    )


class TestSumAnalytic:
    def test_returns_recordset_preserving_structure(self) -> None:
        rs = _make_rs(key_names=["r", "c"])
        result = Sum.validate_analytic(rs, _analytic(partition_by=["r"]))
        assert isinstance(result, RecordSet)
        assert set(result.get_key_components_names()) == {"r", "c"}

    def test_origin_reflects_over_clause(self) -> None:
        rs = _make_rs(key_names=["r", "c"])
        result = Sum.validate_analytic(
            rs, _analytic(partition_by=["r"], order_by=["c"])
        )
        assert "over(" in result.origin
        assert "partition by r" in result.origin
        assert "order by c" in result.origin

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"partition_by": ["missing_key"]},
            {"order_by": ["missing_key"]},
        ],
    )
    def test_missing_component_raises(self, kwargs: dict) -> None:
        rs = _make_rs(key_names=["r"])
        with pytest.raises(SemanticError) as exc_info:
            Sum.validate_analytic(rs, _analytic(**kwargs))
        assert exc_info.value.code == "4-4-0-2"


class TestCountAnalytic:
    def test_returns_integer_fact(self) -> None:
        result = Count.validate_analytic(
            _make_rs(key_names=["r"]), _analytic()
        )
        assert isinstance(result.get_fact_component().type, Integer)


class TestAvgAnalytic:
    def test_validates_number_fact_type(self) -> None:
        assert isinstance(
            Avg.validate_analytic(_make_rs(key_names=["r"]), _analytic()),
            RecordSet,
        )

    def test_string_fact_raises_type_error(self) -> None:
        with pytest.raises(SemanticError):
            Avg.validate_analytic(
                _make_rs(fact_type=String(), key_names=["r"]), _analytic()
            )


class TestWindowClause:
    def test_without_order_by_raises(self) -> None:
        clause = AnalyticClause(
            partition_by=[], order_by=[], window=_window_clause()
        )
        with pytest.raises(SemanticError) as exc_info:
            Sum.validate_analytic(_make_rs(key_names=["r"]), clause)
        assert exc_info.value.code == "4-4-0-5"

    def test_with_order_by_is_valid(self) -> None:
        clause = AnalyticClause(
            partition_by=[], order_by=[OrderItem("r")], window=_window_clause()
        )
        assert isinstance(
            Sum.validate_analytic(_make_rs(key_names=["r"]), clause), RecordSet
        )

    def test_n_boundary_stores_value(self) -> None:
        b = WindowBoundary("n_following", 5)
        assert b.bound_type == "n_following"
        assert b.n == 5


class TestRankValidate:
    def test_returns_integer_fact(self) -> None:
        result = Rank.validate_analytic(
            _make_rs(key_names=["r", "c"]), _analytic(order_by=["r"])
        )
        assert isinstance(result, RecordSet)
        assert isinstance(result.get_fact_component().type, Integer)

    def test_accepts_any_fact_type(self) -> None:
        result = Rank.validate_analytic(
            _make_rs(fact_type=String(), key_names=["r"]),
            _analytic(order_by=["r"]),
        )
        assert isinstance(result.get_fact_component().type, Integer)

    def test_updates_records_data_type(self) -> None:
        rs = _make_rs(key_names=["r"])
        rs.records = pd.DataFrame(
            {"r": ["1", "2"], "data_type": [Number(), Number()]}
        )
        result = Rank.validate_analytic(rs, _analytic(order_by=["r"]))
        assert result.records is not None
        assert all(isinstance(t, Integer) for t in result.records["data_type"])

    def test_origin_string(self) -> None:
        result = Rank.validate_analytic(
            _make_rs(key_names=["r", "c"]),
            _analytic(partition_by=["c"], order_by=["r"]),
        )
        assert "rank(" in result.origin
        assert "over(" in result.origin
        assert "order by r" in result.origin

    def test_order_by_fact_column_is_valid(self) -> None:
        rs = _make_rs(key_names=["r", "c"])
        result = Rank.validate_analytic(rs, _analytic(order_by=["f"]))
        assert isinstance(result.get_fact_component().type, Integer)

    def test_without_order_by_raises(self) -> None:
        with pytest.raises(SemanticError) as exc_info:
            Rank.validate_analytic(_make_rs(key_names=["r"]), _analytic())
        assert exc_info.value.code == "4-4-0-4"

    def test_with_missing_component_raises(self) -> None:
        with pytest.raises(SemanticError) as exc_info:
            Rank.validate_analytic(
                _make_rs(key_names=["r"]), _analytic(order_by=["nonexistent"])
            )
        assert exc_info.value.code == "4-4-0-2"

    def test_with_window_clause_raises(self) -> None:
        clause = AnalyticClause(
            partition_by=[], order_by=[OrderItem("r")], window=_window_clause()
        )
        with pytest.raises(SemanticError) as exc_info:
            Rank.validate_analytic(_make_rs(key_names=["r"]), clause)
        assert exc_info.value.code == "4-4-0-6"
