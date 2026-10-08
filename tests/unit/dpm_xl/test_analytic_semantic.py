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
from dpmcore.dpm_xl.types.scalar import (
    Boolean,
    Date,
    Integer,
    Mixed,
    Null,
    Number,
    ScalarType,
    String,
    TimeInterval,
)
from dpmcore.dpm_xl.utils.tokens import STANDARD
from dpmcore.errors import SemanticError


def _make_rs(
    fact_type=None,
    key_names: list[str] | None = None,
    key_types: dict[str, ScalarType] | None = None,
) -> RecordSet:
    """Keys are Number unless ``key_types`` gives them another type."""
    if fact_type is None:
        fact_type = Number()
    if key_names is None:
        key_names = ["r", "c"]
    key_types = key_types or {}
    components = [
        KeyComponent(k, key_types.get(k, Number()), STANDARD, "test")
        for k in key_names
    ]
    components.append(FactComponent(fact_type, "test"))
    structure = Structure(components)
    return RecordSet(structure, "ds", "ds")


def _date_rs(key_name: str) -> RecordSet:
    """Date keys (``DAT``/``d``) resolve to TimeInterval."""
    return _make_rs(key_names=[key_name], key_types={key_name: TimeInterval()})


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

    @staticmethod
    def _range_clause(
        order_by: str | list[str],
        start: WindowBoundary,
        frame_type: str = "range",
        end: WindowBoundary | None = None,
    ) -> AnalyticClause:
        names = [order_by] if isinstance(order_by, str) else order_by
        return AnalyticClause(
            partition_by=[],
            order_by=[OrderItem(name) for name in names],
            window=WindowClause(
                frame_type=frame_type,
                start=start,
                end=end or WindowBoundary("current_data_point"),
            ),
        )

    @pytest.mark.parametrize(
        ("order_by", "key_type"),
        [("refPeriod", TimeInterval()), ("refDate", Date())],
        ids=["refPeriod", "date"],
    )
    def test_range_on_a_date_with_a_period_is_valid(
        self, order_by: str, key_type: ScalarType
    ) -> None:
        clause = self._range_clause(
            order_by, WindowBoundary("n_preceding", 11, "M")
        )
        rs = _make_rs(key_names=[order_by], key_types={order_by: key_type})
        assert isinstance(Avg.validate_analytic(rs, clause), RecordSet)

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            (WindowBoundary("n_preceding", 11), None),
            (
                WindowBoundary("n_preceding", 11, "M"),
                WindowBoundary("n_following", 2),
            ),
            (
                WindowBoundary("n_preceding", 11),
                WindowBoundary("n_following", 2, "M"),
            ),
        ],
        ids=["no_period", "end_without_period", "start_without_period"],
    )
    def test_range_on_a_date_needs_a_period_on_its_bounds(
        self, start: WindowBoundary, end: WindowBoundary | None
    ) -> None:
        clause = self._range_clause("refDate", start, end=end)
        with pytest.raises(SemanticError) as exc_info:
            Avg.validate_analytic(_date_rs("refDate"), clause)
        assert exc_info.value.code == "4-4-0-7"

    def test_unbounded_range_on_a_date_needs_no_period(self) -> None:
        clause = self._range_clause(
            "refPeriod", WindowBoundary("unbounded_preceding")
        )
        assert isinstance(
            Sum.validate_analytic(_date_rs("refPeriod"), clause), RecordSet
        )

    @pytest.mark.parametrize("key_type", [Number(), Integer()])
    def test_range_on_a_number_without_a_period_is_valid(
        self, key_type: ScalarType
    ) -> None:
        clause = self._range_clause("yr", WindowBoundary("n_preceding", 2))
        rs = _make_rs(key_names=["yr"], key_types={"yr": key_type})
        assert isinstance(Sum.validate_analytic(rs, clause), RecordSet)

    @pytest.mark.parametrize("key_type", [Number(), Integer()])
    def test_a_period_on_a_range_over_a_number_raises(
        self, key_type: ScalarType
    ) -> None:
        clause = self._range_clause(
            "yr", WindowBoundary("n_preceding", 2, "M")
        )
        rs = _make_rs(key_names=["yr"], key_types={"yr": key_type})
        with pytest.raises(SemanticError) as exc_info:
            Sum.validate_analytic(rs, clause)
        assert exc_info.value.code == "4-4-0-8"

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            (WindowBoundary("n_preceding", 2, "M"), None),
            (
                WindowBoundary("n_preceding", 2),
                WindowBoundary("n_following", 1, "M"),
            ),
        ],
        ids=["start", "end"],
    )
    def test_a_period_on_data_points_raises(
        self, start: WindowBoundary, end: WindowBoundary | None
    ) -> None:
        clause = self._range_clause("refDate", start, "data_points", end=end)
        with pytest.raises(SemanticError) as exc_info:
            Sum.validate_analytic(_date_rs("refDate"), clause)
        assert exc_info.value.code == "4-4-0-8"

    def test_range_with_several_order_components_raises(self) -> None:
        clause = self._range_clause(
            ["refPeriod", "r"], WindowBoundary("n_preceding", 11, "M")
        )
        rs = _make_rs(
            key_names=["refPeriod", "r"],
            key_types={"refPeriod": TimeInterval()},
        )
        with pytest.raises(SemanticError) as exc_info:
            Avg.validate_analytic(rs, clause)
        assert exc_info.value.code == "4-4-0-9"

    def test_data_points_accepts_several_order_components(self) -> None:
        clause = self._range_clause(
            ["r", "c"], WindowBoundary("n_preceding", 1), "data_points"
        )
        assert isinstance(
            Sum.validate_analytic(_make_rs(key_names=["r", "c"]), clause),
            RecordSet,
        )

    @pytest.mark.parametrize(
        "key_type",
        [String(), Boolean(), Null()],
        ids=["String", "Boolean", "standard_key"],
    )
    def test_range_on_a_non_date_non_number_component_raises(
        self, key_type: ScalarType
    ) -> None:
        clause = self._range_clause("r", WindowBoundary("n_preceding", 1))
        rs = _make_rs(key_names=["r"], key_types={"r": key_type})
        with pytest.raises(SemanticError) as exc_info:
            Sum.validate_analytic(rs, clause)
        assert exc_info.value.code == "4-4-0-10"

    def test_range_on_a_missing_component_reports_it_missing(self) -> None:
        clause = self._range_clause(
            "refDate", WindowBoundary("n_preceding", 1)
        )
        with pytest.raises(SemanticError) as exc_info:
            Sum.validate_analytic(_make_rs(key_names=["r"]), clause)
        assert exc_info.value.code == "4-4-0-2"

    @pytest.mark.parametrize(
        ("start", "end"),
        [("M", "D"), ("A", "W"), ("D", "Q")],
    )
    def test_range_with_incommensurable_periods_raises(
        self, start: str, end: str
    ) -> None:
        clause = self._range_clause(
            "refDate",
            WindowBoundary("n_preceding", 3, start),
            end=WindowBoundary("n_preceding", 1, end),
        )
        with pytest.raises(SemanticError) as exc_info:
            Avg.validate_analytic(_date_rs("refDate"), clause)
        assert exc_info.value.code == "4-4-0-11"

    @pytest.mark.parametrize(
        ("start", "end"),
        [("M", "M"), ("A", "Q"), ("S", "M"), ("W", "D")],
    )
    def test_range_with_commensurable_periods_is_valid(
        self, start: str, end: str
    ) -> None:
        clause = self._range_clause(
            "refDate",
            WindowBoundary("n_preceding", 23, start),
            end=WindowBoundary("n_preceding", 12, end),
        )
        assert isinstance(
            Avg.validate_analytic(_date_rs("refDate"), clause), RecordSet
        )

    def test_n_boundary_stores_value(self) -> None:
        b = WindowBoundary("n_following", 5)
        assert b.bound_type == "n_following"
        assert b.n == 5


class TestMixedFactGuard:
    """The Mixed guard lives with the type promotion it protects.

    It used to sit in ``SemanticAnalyzer.visit_AggregationOp``, which
    ``rank`` reached through a visitor of its own and so never hit.
    ``Rank`` overrides ``validate_analytic`` and does no promotion, so it
    stays exempt by not inheriting the check rather than by a
    node-class special case.
    """

    def test_promoting_aggregate_rejects_a_mixed_fact(self) -> None:
        with pytest.raises(SemanticError) as exc_info:
            Sum.validate_analytic(
                _make_rs(fact_type=Mixed(), key_names=["r"]),
                _analytic(order_by=["r"]),
            )
        assert exc_info.value.code == "4-4-0-3"
        assert "sum(...)" in str(exc_info.value)

    def test_rank_still_accepts_a_mixed_fact(self) -> None:
        result = Rank.validate_analytic(
            _make_rs(fact_type=Mixed(), key_names=["r"]),
            _analytic(order_by=["r"]),
        )
        assert isinstance(result, RecordSet)
        assert isinstance(result.get_fact_component().type, Integer)


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
