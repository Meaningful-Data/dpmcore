"""Tests for the ast_generator helpers and the script() flow."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _patch_orm(monkeypatch):
    """Stub heavy imports so the module loads on Python 3.10 in unit tests."""
    stubs = {
        "dpmcore.orm": MagicMock(),
        "dpmcore.orm.infrastructure": MagicMock(),
        "dpmcore.orm.packaging": MagicMock(),
        "dpmcore.orm.operations": MagicMock(),
        "dpmcore.orm.rendering": MagicMock(),
        "dpmcore.orm.variables": MagicMock(),
        "dpmcore.orm.glossary": MagicMock(),
        "dpmcore.errors": MagicMock(),
        "dpmcore.loaders": MagicMock(),
        "dpmcore.loaders.migration": MagicMock(),
        "dpmcore.dpm_xl.model_queries": MagicMock(),
        "dpmcore.services.scope_calculator": MagicMock(),
        "dpmcore.services.semantic": MagicMock(),
        "dpmcore.services.syntax": MagicMock(),
    }
    for name, stub in stubs.items():
        monkeypatch.setitem(sys.modules, name, stub)


def _load_ast_generator():
    """Load ``ast_generator`` under a private shadow name."""
    shadow_name = "_test_shadow_ast_generator"
    spec = importlib.util.spec_from_file_location(
        shadow_name,
        _REPO_ROOT / "src/dpmcore/services/ast_generator.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[shadow_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ #
# Helpers used across tests
# ------------------------------------------------------------------ #


def _bare_svc():
    mod = _load_ast_generator()
    Cls = mod.ASTGeneratorService
    svc = Cls.__new__(Cls)
    return svc, Cls, mod


def _scope_calc_mock(detect_return=None, alt_return=None):
    sc = MagicMock()
    sc.detect_cross_module_dependencies.return_value = detect_return or {
        "intra_instance_validations": [],
        "cross_instance_dependencies": [],
        "dependency_modules": {},
    }
    sc.detect_alternative_dependencies.return_value = alt_return or []
    return sc


# ------------------------------------------------------------------ #
# _resolve_severities
# ------------------------------------------------------------------ #


class TestResolveSeverities:
    def test_default_is_warning(self):
        svc, _, _ = _bare_svc()
        out = svc._resolve_severities(None, None, ["v1", "v2"])
        assert out == {"v1": "warning", "v2": "warning"}

    def test_lowercases_global(self):
        svc, _, _ = _bare_svc()
        out = svc._resolve_severities("ERROR", None, ["v1"])
        assert out == {"v1": "error"}

    def test_per_code_overrides_global(self):
        svc, _, _ = _bare_svc()
        out = svc._resolve_severities("warning", {"v2": "INFO"}, ["v1", "v2"])
        assert out == {"v1": "warning", "v2": "info"}

    def test_invalid_global_raises(self):
        svc, _, _ = _bare_svc()
        with pytest.raises(ValueError, match="Invalid severity 'badvalue'"):
            svc._resolve_severities("badvalue", None, ["v1"])

    def test_invalid_per_code_raises(self):
        svc, _, _ = _bare_svc()
        with pytest.raises(
            ValueError, match=r"Invalid severity 'bogus' for validation 'v1'"
        ):
            svc._resolve_severities(None, {"v1": "bogus"}, ["v1"])

    def test_unknown_code_in_severities_raises(self):
        svc, _, _ = _bare_svc()
        with pytest.raises(ValueError, match="Unknown validation_code"):
            svc._resolve_severities(None, {"vXX": "info"}, ["v1"])

    def test_non_string_global_raises(self):
        svc, _, _ = _bare_svc()
        with pytest.raises(ValueError, match="must be a string"):
            svc._resolve_severities(123, None, ["v1"])  # type: ignore[arg-type]


# ------------------------------------------------------------------ #
# _clean_ast_data_entries
# ------------------------------------------------------------------ #


class TestCleanAstDataEntries:
    def test_strips_engine_internal_fields(self):
        _, Cls, _ = _bare_svc()
        ast = {
            "class_name": "VarID",
            "table": "C_01.00",
            "data": [
                {
                    "datapoint": 1,
                    "operand_reference_id": 7,
                    "data_type": "m",
                    "cell_code": "{r0010,c0010}",
                    "table_code": "C_01.00",
                    "table_vid": 12,
                    "x": 1,
                    "y": 1,
                }
            ],
        }
        Cls._clean_ast_data_entries(ast)
        entry = ast["data"][0]
        assert "data_type" not in entry
        assert "cell_code" not in entry
        assert "table_code" not in entry
        assert "table_vid" not in entry
        assert entry["datapoint"] == 1
        assert entry["operand_reference_id"] == 7
        assert entry["x"] == 1

    def test_recurses_into_nested_nodes(self):
        _, Cls, _ = _bare_svc()
        ast = {
            "class_name": "BinOp",
            "op": "=",
            "left": {
                "class_name": "VarID",
                "data": [{"datapoint": 1, "data_type": "m"}],
            },
            "right": {
                "class_name": "VarID",
                "data": [{"datapoint": 2, "table_code": "X"}],
            },
        }
        Cls._clean_ast_data_entries(ast)
        assert "data_type" not in ast["left"]["data"][0]
        assert "table_code" not in ast["right"]["data"][0]

    def test_non_dict_input_returns_unchanged(self):
        _, Cls, _ = _bare_svc()
        assert Cls._clean_ast_data_entries("hello") == "hello"


# ------------------------------------------------------------------ #
# _extract_referenced_tables
# ------------------------------------------------------------------ #


class TestExtractReferencedTables:
    def test_collects_table_codes_from_varid(self):
        _, Cls, _ = _bare_svc()
        ast = {
            "class_name": "BinOp",
            "left": {"class_name": "VarID", "table": "C_01.00"},
            "right": {"class_name": "VarID", "table": "C_02.00"},
        }
        assert Cls._extract_referenced_tables(ast) == {
            "C_01.00",
            "C_02.00",
        }

    def test_ignores_non_varid_nodes(self):
        _, Cls, _ = _bare_svc()
        ast = {"class_name": "Constant", "value": 0}
        assert Cls._extract_referenced_tables(ast) == set()


# ------------------------------------------------------------------ #
# _build_module_info / _build_release_info / _build_dates
# ------------------------------------------------------------------ #


class TestBuildModuleInfo:
    def test_extracts_framework_code(self):
        _, Cls, _ = _bare_svc()
        framework = SimpleNamespace(code="COREP")
        module = SimpleNamespace(framework=framework)
        mv = SimpleNamespace(
            code="COREP_Con", version_number="2.0.1", module=module
        )
        assert Cls._build_module_info(mv) == {
            "module_code": "COREP_Con",
            "module_version": "2.0.1",
            "framework_code": "COREP",
        }

    def test_missing_framework_yields_empty(self):
        _, Cls, _ = _bare_svc()
        mv = SimpleNamespace(code="X", version_number="1", module=None)
        assert Cls._build_module_info(mv)["framework_code"] == ""


class TestBuildReleaseInfo:
    def test_formats_date(self):
        _, Cls, _ = _bare_svc()
        rr = SimpleNamespace(code="4.2", date=date(2025, 4, 28))
        assert Cls._build_release_info(rr) == {
            "release": "4.2",
            "publication_date": "2025-04-28",
        }

    def test_missing_date_uses_default(self):
        _, Cls, _ = _bare_svc()
        rr = SimpleNamespace(code="4.2", date=None)
        assert Cls._build_release_info(rr)["publication_date"] == "2001-01-01"


class TestBuildDates:
    def test_emits_iso_dates(self):
        _, Cls, _ = _bare_svc()
        mv = SimpleNamespace(
            from_reference_date=date(2026, 3, 31),
            to_reference_date=None,
        )
        assert Cls._build_dates(mv) == {"from": "2026-03-31", "to": None}


# ------------------------------------------------------------------ #
# _build_operation_entry
# ------------------------------------------------------------------ #


class TestBuildOperationEntry:
    def test_deterministic_version_id(self):
        _, Cls, _ = _bare_svc()
        a = Cls._build_operation_entry(
            "expr", "v1", {"x": 1}, "warning", "2026-03-31", 24
        )
        b = Cls._build_operation_entry(
            "expr", "v1", {"x": 1}, "warning", "2026-03-31", 24
        )
        assert a["version_id"] == b["version_id"]
        assert 0 <= a["version_id"] < 10000

    def test_threads_severity_and_root(self):
        _, Cls, _ = _bare_svc()
        out = Cls._build_operation_entry(
            "expr", "v1", {"x": 1}, "info", "2026-03-31", 7
        )
        assert out["severity"] == "info"
        assert out["root_operator_id"] == 7
        assert out["expression"] == "expr"
        assert out["code"] == "v1"
        assert out["from_submission_date"] == "2026-03-31"
        assert out["ast"] == {"x": 1}


# ------------------------------------------------------------------ #
# _build_preconditions_block
# ------------------------------------------------------------------ #


class TestBuildPreconditionsBlock:
    def test_empty_input_returns_empty(self):
        svc, _, _ = _bare_svc()
        svc.session = MagicMock()
        assert svc._build_preconditions_block([], release_id=None) == (
            {},
            {},
        )

    @pytest.mark.parametrize(
        "expression",
        [
            "{v_C_01.00}",  # canonical form
            "{vC_01.00}",  # cosmetic underscore omitted
        ],
    )
    def test_single_variable_emits_p_vid(self, expression, monkeypatch):
        svc, _, mod = _bare_svc()
        svc.session = MagicMock()

        fake_query = MagicMock()
        fake_query.get_variable_vids_by_codes.return_value = {
            "C_01.00": {"variable_id": 11, "variable_vid": 110}
        }
        monkeypatch.setitem(
            sys.modules,
            "dpmcore.dpm_xl.model_queries",
            SimpleNamespace(VariableVersionQuery=fake_query),
        )

        preconds, vars_ = svc._build_preconditions_block(
            [(expression, ["v1", "v2"])], release_id=5
        )
        assert "p_110" in preconds
        entry = preconds["p_110"]
        assert entry["ast"]["class_name"] == "PreconditionItem"
        assert entry["ast"]["variable_id"] == 11
        assert entry["affected_operations"] == ["v1", "v2"]
        assert entry["version_id"] == 110
        assert entry["code"] == "p_110"
        assert vars_ == {"110": "b"}

    def test_compound_emits_left_folded_binop(self, monkeypatch):
        svc, _, _ = _bare_svc()
        svc.session = MagicMock()

        fake_query = MagicMock()
        fake_query.get_variable_vids_by_codes.return_value = {
            "A": {"variable_id": 1, "variable_vid": 10},
            "B": {"variable_id": 2, "variable_vid": 20},
            "C": {"variable_id": 3, "variable_vid": 30},
        }
        monkeypatch.setitem(
            sys.modules,
            "dpmcore.dpm_xl.model_queries",
            SimpleNamespace(VariableVersionQuery=fake_query),
        )

        preconds, vars_ = svc._build_preconditions_block(
            [("{v_A} and {v_B} and {v_C}", ["v1"])], release_id=None
        )
        assert "p_10_20_30" in preconds
        ast = preconds["p_10_20_30"]["ast"]
        # Left fold: ((A and B) and C)
        assert ast["class_name"] == "BinOp"
        assert ast["op"] == "and"
        assert ast["right"]["variable_id"] == 3
        assert ast["left"]["class_name"] == "BinOp"
        assert ast["left"]["right"]["variable_id"] == 2
        assert ast["left"]["left"]["variable_id"] == 1
        assert vars_ == {"10": "b", "20": "b", "30": "b"}

    def test_unresolved_codes_silently_skipped(self, monkeypatch):
        svc, _, _ = _bare_svc()
        svc.session = MagicMock()

        fake_query = MagicMock()
        fake_query.get_variable_vids_by_codes.return_value = {}
        monkeypatch.setitem(
            sys.modules,
            "dpmcore.dpm_xl.model_queries",
            SimpleNamespace(VariableVersionQuery=fake_query),
        )

        preconds, vars_ = svc._build_preconditions_block(
            [("{v_unresolved}", ["v1"])], release_id=None
        )
        assert preconds == {}
        assert vars_ == {}

    def test_collision_merges_affected_operations(self, monkeypatch):
        """Same precondition shape across two entries merges ops.

        Regression for B2: two preconditions producing the same key
        used to silently overwrite each other, dropping the earlier
        ``affected_operations``. The merged entry should now contain
        both validation codes, deduplicated and order-preserving.
        """
        svc, _, _ = _bare_svc()
        svc.session = MagicMock()

        fake_query = MagicMock()
        fake_query.get_variable_vids_by_codes.return_value = {
            "C_01.00": {"variable_id": 11, "variable_vid": 110},
        }
        monkeypatch.setitem(
            sys.modules,
            "dpmcore.dpm_xl.model_queries",
            SimpleNamespace(VariableVersionQuery=fake_query),
        )

        preconds, _vars = svc._build_preconditions_block(
            [
                ("{v_C_01.00}", ["v1", "v2"]),
                ("{v_C_01.00}", ["v2", "v3"]),
            ],
            release_id=None,
        )
        assert list(preconds) == ["p_110"]
        assert preconds["p_110"]["affected_operations"] == [
            "v1",
            "v2",
            "v3",
        ]

    def test_dict_format_with_custom_code_and_version_id(self, monkeypatch):
        """Dict format allows overriding code and version_id"""
        svc, _, _ = _bare_svc()
        svc.session = MagicMock()

        fake_query = MagicMock()
        fake_query.get_variable_vids_by_codes.return_value = {
            "C_01.00": {"variable_id": 11, "variable_vid": 110}
        }
        monkeypatch.setitem(
            sys.modules,
            "dpmcore.dpm_xl.model_queries",
            SimpleNamespace(VariableVersionQuery=fake_query),
        )

        preconds, vars_ = svc._build_preconditions_block(
            [
                {
                    "expression": "{v_C_01.00}",
                    "affected_operations": ["v1", "v2"],
                    "code": "P_571",  # Override default p_110
                    "version_id": 8341,  # Override default 110
                }
            ],
            release_id=5,
        )
        assert "P_571" in preconds
        entry = preconds["P_571"]
        assert entry["code"] == "P_571"
        assert entry["version_id"] == 8341
        assert entry["affected_operations"] == ["v1", "v2"]
        assert vars_ == {"110": "b"}

    def test_backward_compat_tuple_format_still_works(self, monkeypatch):
        """Tuple format (old) still works for backward compatibility."""
        svc, _, _ = _bare_svc()
        svc.session = MagicMock()

        fake_query = MagicMock()
        fake_query.get_variable_vids_by_codes.return_value = {
            "C_01.00": {"variable_id": 11, "variable_vid": 110}
        }
        monkeypatch.setitem(
            sys.modules,
            "dpmcore.dpm_xl.model_queries",
            SimpleNamespace(VariableVersionQuery=fake_query),
        )

        # Old tuple format should still work
        preconds, vars_ = svc._build_preconditions_block(
            [("{v_C_01.00}", ["v1", "v2"])],
            release_id=5,
        )
        assert "p_110" in preconds
        entry = preconds["p_110"]
        assert entry["code"] == "p_110"
        assert entry["version_id"] == 110


# ------------------------------------------------------------------ #
# _resolve_root_operator_id
# ------------------------------------------------------------------ #


class TestResolveRootOperatorId:
    def _df(self, mapping):
        df = MagicMock()
        rows = [(sym, oid) for sym, oid in mapping.items()]

        def _getitem(key):
            if isinstance(key, list):
                return MagicMock()
            mock = MagicMock()
            mock.values = [oid for sym, oid in rows if sym == key.compare]
            return mock

        return df

    def test_walks_past_start_to_binop(self, monkeypatch):
        _, Cls, _ = _bare_svc()
        binop = SimpleNamespace(op="=")
        binop.__class__.__name__  # noqa: B018  (sanity)
        # Real class names matter — set via type construction.
        BinOp = type("BinOp", (), {})
        node = BinOp()
        node.op = "="

        Start = type("Start", (), {})
        start = Start()
        start.children = [node]

        # Build a fake DataFrame-like return for OperatorQuery.
        fake_df = MagicMock()
        fake_df.__getitem__.return_value.values = []  # default

        class FakeOperatorQuery:
            @staticmethod
            def get_operators(session):  # noqa: ARG004
                import pandas as pd

                return pd.DataFrame(
                    [
                        {"Symbol": "=", "OperatorID": 24},
                        {"Symbol": ">", "OperatorID": 25},
                    ]
                )

        monkeypatch.setitem(
            sys.modules,
            "dpmcore.dpm_xl.model_queries",
            SimpleNamespace(OperatorQuery=FakeOperatorQuery),
        )
        assert Cls._resolve_root_operator_id(start, MagicMock()) == 24

    def test_walks_past_persistent_assignment(self, monkeypatch):
        _, Cls, _ = _bare_svc()
        BinOp = type("BinOp", (), {})
        op = BinOp()
        op.op = ">="

        PA = type("PersistentAssignment", (), {})
        pa = PA()
        pa.right = op

        class FakeOperatorQuery:
            @staticmethod
            def get_operators(session):  # noqa: ARG004
                import pandas as pd

                return pd.DataFrame([{"Symbol": ">=", "OperatorID": 33}])

        monkeypatch.setitem(
            sys.modules,
            "dpmcore.dpm_xl.model_queries",
            SimpleNamespace(OperatorQuery=FakeOperatorQuery),
        )
        assert Cls._resolve_root_operator_id(pa, MagicMock()) == 33

    def test_condexpr_root_resolves_to_if_then_else(self, monkeypatch):
        # A CondExpr root has no 'op'; it resolves to the if-then-else
        # operator instead of raising.
        _, Cls, _ = _bare_svc()
        CondExpr = type("CondExpr", (), {})
        node = CondExpr()
        node.op = None

        WithExpression = type("WithExpression", (), {})
        with_expr = WithExpression()
        with_expr.expression = node

        class FakeOperatorQuery:
            @staticmethod
            def get_operators(session):  # noqa: ARG004
                import pandas as pd

                return pd.DataFrame(
                    [{"Symbol": "if-then-else", "OperatorID": 30}]
                )

        monkeypatch.setitem(
            sys.modules,
            "dpmcore.dpm_xl.model_queries",
            SimpleNamespace(OperatorQuery=FakeOperatorQuery),
        )
        assert Cls._resolve_root_operator_id(with_expr, MagicMock()) == 30

    def test_unresolvable_root_raises(self, monkeypatch):
        _, Cls, _ = _bare_svc()
        # No 'op' attribute anywhere.
        Bare = type("Bare", (), {})
        bare = Bare()

        class FakeOperatorQuery:
            @staticmethod
            def get_operators(session):  # noqa: ARG004
                import pandas as pd

                return pd.DataFrame()

        monkeypatch.setitem(
            sys.modules,
            "dpmcore.dpm_xl.model_queries",
            SimpleNamespace(OperatorQuery=FakeOperatorQuery),
        )
        with pytest.raises(RuntimeError, match="Cannot resolve root"):
            Cls._resolve_root_operator_id(bare, MagicMock())

    def test_unknown_symbol_raises(self, monkeypatch):
        _, Cls, _ = _bare_svc()
        BinOp = type("BinOp", (), {})
        op = BinOp()
        op.op = "weird"

        class FakeOperatorQuery:
            @staticmethod
            def get_operators(session):  # noqa: ARG004
                import pandas as pd

                return pd.DataFrame([{"Symbol": "=", "OperatorID": 24}])

        monkeypatch.setitem(
            sys.modules,
            "dpmcore.dpm_xl.model_queries",
            SimpleNamespace(OperatorQuery=FakeOperatorQuery),
        )
        with pytest.raises(RuntimeError, match="No OperatorID"):
            Cls._resolve_root_operator_id(op, MagicMock())


# ------------------------------------------------------------------ #
# _resolve_release
# ------------------------------------------------------------------ #


class TestResolveRelease:
    def test_unresolved_module_version_raises(self):
        svc, _, _ = _bare_svc()
        svc.session = MagicMock()
        svc._resolve_module_version = lambda c, v: None
        with pytest.raises(ValueError, match="ModuleVersion not found"):
            svc._resolve_release("X", "1.0", None)

    # Explicit-release window checks now compare semver sort orders, which
    # need real Release rows. They are covered against the EBA fixture DB in
    # tests/integration/services/test_scope_release_axis.py rather than with
    # blanket ORM mocks (see issue #151).


# ------------------------------------------------------------------ #
# _latest_release_in_window
# ------------------------------------------------------------------ #


class TestLatestReleaseInWindow:
    def test_unparseable_start_release_raises(self):
        svc, _, _ = _bare_svc()
        svc.session = MagicMock()
        mv = SimpleNamespace(start_release_id=42, end_release_id=None)
        # resolve_sort_order issues session.query(Release.code).filter(
        # Release.release_id == ...).first(); return an unparseable code
        # so compute_sort_order produces None and the helper raises.
        svc.session.query.return_value.filter.return_value.first.return_value = (  # noqa: E501
            "garbage",
        )
        with pytest.raises(
            ValueError, match="window start release 42 has no sort_order"
        ):
            svc._latest_release_in_window(mv)

    def test_unparseable_end_release_raises(self):
        svc, _, _ = _bare_svc()
        svc.session = MagicMock()
        mv = SimpleNamespace(start_release_id=1, end_release_id=99)
        # Two resolve_sort_order calls: first returns a parseable code,
        # second returns an unparseable one so the end-bound resolver
        # raises.
        svc.session.query.return_value.filter.return_value.first.side_effect = [  # noqa: E501
            ("4.0",),
            ("garbage",),
        ]
        with pytest.raises(
            ValueError, match="window end release 99 has no sort_order"
        ):
            svc._latest_release_in_window(mv)


# ------------------------------------------------------------------ #
# _build_dependency_info
# ------------------------------------------------------------------ #


class TestBuildDependencyInfo:
    def test_none_when_scope_calc_missing(self):
        svc, _, _ = _bare_svc()
        svc._scope_calc = None
        assert (
            svc._build_dependency_info(
                scope_pairs=[("X",)],
                primary_module_vid=1,
                release_id=None,
            )
            is None
        )

    def test_none_when_primary_missing(self):
        svc, _, _ = _bare_svc()
        svc._scope_calc = _scope_calc_mock()
        assert (
            svc._build_dependency_info(
                scope_pairs=[(("e",), MagicMock(), {})],
                primary_module_vid=None,
                release_id=None,
            )
            is None
        )

    def test_none_when_pairs_empty(self):
        svc, _, _ = _bare_svc()
        svc._scope_calc = _scope_calc_mock()
        assert (
            svc._build_dependency_info(
                scope_pairs=[], primary_module_vid=1, release_id=None
            )
            is None
        )

    def test_aggregates_and_dedupes_intra(self):
        svc, _, _ = _bare_svc()
        svc._scope_calc = _scope_calc_mock(
            detect_return={
                "intra_instance_validations": ["v1"],
                "cross_instance_dependencies": [],
                "dependency_modules": {},
            }
        )
        scope_pairs = [
            (("e1", "v1"), MagicMock(), {}),
            (("e2", "v1"), MagicMock(), {}),
        ]
        out = svc._build_dependency_info(
            scope_pairs=scope_pairs,
            primary_module_vid=1,
            release_id=None,
        )
        assert out["dependency_information"]["intra_instance_validations"] == [
            "v1"
        ]


# ------------------------------------------------------------------ #
# _merge_dep_modules
# ------------------------------------------------------------------ #


class TestMergeDepModules:
    def test_new_uri_inserted(self):
        _, Cls, _ = _bare_svc()
        existing = {}
        Cls._merge_dep_modules(
            existing, {"http://a": {"tables": {"T": {}}, "variables": {}}}
        )
        assert "http://a" in existing

    def test_existing_uri_merges_tables_without_overwriting(self):
        _, Cls, _ = _bare_svc()
        existing = {
            "http://a": {
                "tables": {"T1": {"variables": {}, "open_keys": {}}},
                "variables": {"v1": "x"},
            }
        }
        new = {
            "http://a": {
                "tables": {
                    "T1": {"variables": {"NEW": "y"}, "open_keys": {}},
                    "T2": {"variables": {}, "open_keys": {}},
                },
                "variables": {"v2": "y"},
            }
        }
        Cls._merge_dep_modules(existing, new)
        assert existing["http://a"]["tables"]["T1"]["variables"] == {}
        assert "T2" in existing["http://a"]["tables"]
        assert existing["http://a"]["variables"] == {"v1": "x", "v2": "y"}


# ------------------------------------------------------------------ #
# _extract_time_shifts
# ------------------------------------------------------------------ #


class _FakeTimeShiftOp:
    def __init__(self, period_indicator, shift_number, operand):
        self.period_indicator = period_indicator
        self.shift_number = shift_number
        self.operand = operand


_FakeTimeShiftOp.__name__ = "TimeShiftOp"


class _FakeVarID:
    def __init__(self, table):
        self.table = table


_FakeVarID.__name__ = "VarID"


class TestExtractTimeShifts:
    def test_empty_returns_empty(self):
        _, Cls, _ = _bare_svc()
        assert Cls._extract_time_shifts(SimpleNamespace()) == {}

    def test_positive_constant_shift_produces_T_minus(self):
        _, Cls, _ = _bare_svc()
        from dpmcore.dpm_xl.ast.nodes import Constant

        sn = Constant(type_="Integer", value=1)
        node = _FakeTimeShiftOp("Q", sn, _FakeVarID(table="T_01"))
        assert Cls._extract_time_shifts(node) == {"T_01": "T-1Q"}

    def test_negative_unary_shift_produces_T_minus(self):
        _, Cls, _ = _bare_svc()
        from dpmcore.dpm_xl.ast.nodes import Constant, UnaryOp

        sn = UnaryOp(op="-", operand=Constant(type_="Integer", value=2))
        node = _FakeTimeShiftOp("Y", sn, _FakeVarID(table="T_02"))
        assert Cls._extract_time_shifts(node) == {"T_02": "T-2Y"}

    def test_var_without_table_ignored(self):
        _, Cls, _ = _bare_svc()
        from dpmcore.dpm_xl.ast.nodes import Constant

        sn = Constant(type_="Integer", value=1)
        node = _FakeTimeShiftOp("Q", sn, _FakeVarID(table=None))
        assert Cls._extract_time_shifts(node) == {}

    def test_complex_expression_ast_node_shift(self):
        _, Cls, _ = _bare_svc()
        from dpmcore.dpm_xl.ast.nodes import BinOp, Constant

        sn = BinOp(
            op="*",
            left=Constant(type_="Integer", value=5),
            right=Constant(type_="Integer", value=12),
        )
        node = _FakeTimeShiftOp("Q", sn, _FakeVarID(table="T_03"))
        result = Cls._extract_time_shifts(node)
        assert result == {"T_03": "T-nQ"}

    def test_exception_returns_empty(self):
        _, Cls, _ = _bare_svc()

        class Boom:
            def __getattr__(self, item):
                raise AttributeError("boom")

        assert Cls._extract_time_shifts(Boom()) == {}


# ------------------------------------------------------------------ #
# _build_precondition_index
# ------------------------------------------------------------------ #


class TestBuildPreconditionIndex:
    def test_unions_codes_across_preconditions(self):
        svc, _, _ = _bare_svc()
        svc._syntax = MagicMock()
        svc._syntax.parse.side_effect = lambda expr: f"AST_{expr}"
        svc._extract_precondition_codes = lambda ast: (
            ["P1"] if ast == "AST_a" else ["P2"]
        )
        idx = svc._build_precondition_index(
            [("a", ["v1", "v2"]), ("b", ["v2", "v3"])]
        )
        assert idx["v1"] == ["P1"]
        assert idx["v2"] == ["P1", "P2"]
        assert idx["v3"] == ["P2"]

    def test_parse_failure_raises_value_error(self):
        svc, _, _ = _bare_svc()
        svc._syntax = MagicMock()
        svc._syntax.parse.side_effect = RuntimeError("syntax error")
        with pytest.raises(ValueError, match="Invalid precondition"):
            svc._build_precondition_index([("bad", ["v"])])

    def test_dict_format_builds_index_correctly(self):
        """Dict format in _build_precondition_index works like tuple format."""
        svc, _, _ = _bare_svc()
        svc._syntax = MagicMock()
        svc._syntax.parse.side_effect = lambda expr: f"AST_{expr}"
        svc._extract_precondition_codes = lambda ast: (
            ["P1"] if ast == "AST_expr1" else ["P2"]
        )
        idx = svc._build_precondition_index(
            [
                {
                    "expression": "expr1",
                    "affected_operations": ["v1", "v2"],
                    "code": "P_571",  # Custom fields ignored by index builder
                    "version_id": 8341,
                },
                ("expr2", ["v2", "v3"]),  # Tuple format still works
            ]
        )
        assert idx["v1"] == ["P1"]
        assert idx["v2"] == ["P1", "P2"]
        assert idx["v3"] == ["P2"]


# ------------------------------------------------------------------ #
# script() — integration of helpers
# ------------------------------------------------------------------ #


class TestScript:
    def _build_svc(self, mv=None, release_row=None):
        svc, _, mod = _bare_svc()
        svc.session = MagicMock()
        svc._semantic = MagicMock()
        svc._scope_calc = MagicMock()
        svc._syntax = MagicMock()

        if mv is None:
            framework = SimpleNamespace(code="COREP")
            module = SimpleNamespace(framework=framework)
            mv = SimpleNamespace(
                module_vid=1,
                start_release_id=1,
                end_release_id=None,
                from_reference_date=date(2026, 3, 31),
                to_reference_date=None,
                code="MOD",
                version_number="1.0",
                module=module,
            )
        if release_row is None:
            release_row = SimpleNamespace(
                release_id=2, code="4.2", date=date(2025, 4, 28)
            )

        svc._resolve_release = lambda mc, mv_, rel: (mv, release_row)
        svc._resolve_root_operator_id = staticmethod(lambda ast, session: 24)

        svc._scope_calc._get_module_tables.return_value = {
            "C_01.00": {
                "variables": {"100": "m"},
                "open_keys": {"BASE": "e"},
            }
        }
        svc._scope_calc._get_module_uri.return_value = "http://example/mod"
        svc._scope_calc.calculate_from_expression.return_value = (
            SimpleNamespace(has_error=False, scopes=[])
        )
        svc._scope_calc.detect_cross_module_dependencies.return_value = {
            "intra_instance_validations": ["v1"],
            "cross_instance_dependencies": [],
            "dependency_modules": {},
        }
        svc._scope_calc.detect_alternative_dependencies.return_value = []
        return svc, mv, release_row, mod

    def _stub_serialize_ast(self, monkeypatch, return_value):
        ser_mod = MagicMock()
        ser_mod.serialize_ast = lambda ast: return_value
        monkeypatch.setitem(
            sys.modules, "dpmcore.dpm_xl.utils.serialization", ser_mod
        )

    def test_no_session_returns_error(self):
        svc, _, mod = _bare_svc()
        svc.session = None
        svc._semantic = None
        svc._scope_calc = None
        out = svc.script(
            expressions=[("x", "v1")],
            module_code="MOD",
            module_version="1.0",
        )
        assert out["success"] is False
        assert "No database session" in out["error"]

    def test_resolve_release_failure_returns_error(self, monkeypatch):
        svc, *_ = self._build_svc()

        def _raise(mc, mv_, rel):
            raise ValueError("ModuleVersion not found: X 1.0")

        svc._resolve_release = _raise
        out = svc.script(
            expressions=[("x", "v1")],
            module_code="X",
            module_version="1.0",
        )
        assert out["success"] is False
        assert "ModuleVersion not found" in out["error"]

    def test_validation_error_goes_to_failed_operations(self, monkeypatch):
        svc, *_ = self._build_svc()
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=False,
            error_message="Grey cells {F_32.03.a, r0040, c0010} were found.",
        )
        out = svc.script(
            expressions=[("x", "v1")],
            module_code="MOD",
            module_version="1.0",
        )
        assert out["success"] is True
        assert out["failed_operations"] == {
            "v1": "Grey cells {F_32.03.a, r0040, c0010} were found."
        }

    def test_grey_cell_skips_op_preserves_others(self, monkeypatch):
        """A grey-cell failure must skip that op, not abort the module."""
        self._stub_serialize_ast(
            monkeypatch,
            {"class_name": "VarID", "table": "C_01.00", "data": []},
        )
        svc, *_ = self._build_svc()

        svc._semantic.validate.side_effect = lambda expr, release_id=None: (
            SimpleNamespace(
                is_valid=False,
                error_message="Grey cells {F_32.03.a, r0040, c0010} were found.",
            )
            if expr == "e_bad"
            else SimpleNamespace(
                is_valid=True, error_message=None, parameters=()
            )
        )
        svc._semantic.ast = "AST"

        out = svc.script(
            expressions=[("e_bad", "v1"), ("e2", "v2"), ("e3", "v3")],
            module_code="MOD",
            module_version="1.0",
        )
        assert out["success"] is True
        ns = next(iter(out["enriched_ast"].values()))
        assert "v1" not in ns["operations"]
        assert "v2" in ns["operations"]
        assert "v3" in ns["operations"]
        assert out["failed_operations"] == {
            "v1": "Grey cells {F_32.03.a, r0040, c0010} were found."
        }

    def test_scope_error_fails_generation(self, monkeypatch):
        """Regression for #122: a scope-calculation error must fail the
        script generation instead of silently emitting the operation
        with no dependency information.
        """
        self._stub_serialize_ast(
            monkeypatch,
            {"class_name": "VarID", "table": "C_01.00", "data": []},
        )
        svc, *_ = self._build_svc()
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=True, error_message=None, parameters=()
        )
        svc._semantic.ast = "AST"
        svc._scope_calc.calculate_from_expression.return_value = (
            SimpleNamespace(
                has_error=True,
                error_message=(
                    "No module versions found for preconditions items: "
                    "{'F_40.01'}."
                ),
            )
        )
        out = svc.script(
            expressions=[("e1", "v1")],
            module_code="MOD",
            module_version="1.0",
        )
        assert out["success"] is False
        assert "'v1'" in out["error"]
        assert "No module versions found" in out["error"]

    def test_invalid_severity_returns_error(self, monkeypatch):
        svc, *_ = self._build_svc()
        out = svc.script(
            expressions=[("x", "v1")],
            module_code="MOD",
            module_version="1.0",
            severity="bogus",
        )
        assert out["success"] is False
        assert "Invalid severity" in out["error"]

    def test_unknown_code_in_severities_returns_error(self):
        svc, *_ = self._build_svc()
        out = svc.script(
            expressions=[("x", "v1")],
            module_code="MOD",
            module_version="1.0",
            severities={"vXX": "info"},
        )
        assert out["success"] is False
        assert "Unknown validation_code" in out["error"]

    def test_happy_path_returns_namespaced_shape(self, monkeypatch):
        self._stub_serialize_ast(
            monkeypatch,
            {
                "class_name": "VarID",
                "table": "C_01.00",
                "data": [{"datapoint": 1, "data_type": "m"}],
            },
        )
        svc, mv, rr, _ = self._build_svc()
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=True, error_message=None, parameters=()
        )
        svc._semantic.ast = "AST"
        out = svc.script(
            expressions=[("e1", "v1"), ("e2", "v2")],
            module_code="MOD",
            module_version="1.0",
            severity="error",
            severities={"v2": "info"},
        )
        assert out["success"] is True
        ns_block = out["enriched_ast"]["http://example/mod"]
        assert ns_block["module_code"] == "MOD"
        assert ns_block["module_version"] == "1.0"
        assert ns_block["framework_code"] == "COREP"
        assert ns_block["dpm_release"] == {
            "release": "4.2",
            "publication_date": "2025-04-28",
        }
        assert ns_block["dates"] == {
            "from": "2026-03-31",
            "to": None,
        }
        assert "v1" in ns_block["operations"]
        assert ns_block["operations"]["v1"]["severity"] == "error"
        assert ns_block["operations"]["v2"]["severity"] == "info"
        assert ns_block["operations"]["v1"]["root_operator_id"] == 24
        # AST stripped
        ast_data = ns_block["operations"]["v1"]["ast"]["data"][0]
        assert "data_type" not in ast_data
        # tables/variables seeded from the module composition
        assert "C_01.00" in ns_block["tables"]
        assert ns_block["variables"] == {"100": "m"}

    def test_tables_block_includes_unreferenced_module_tables(
        self, monkeypatch
    ):
        """#158: module-composition tables appear even when no expression
        references them; abstract (empty-variable) tables stay excluded.
        """
        self._stub_serialize_ast(
            monkeypatch,
            {"class_name": "VarID", "table": "C_01.00", "data": []},
        )
        svc, *_ = self._build_svc()
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=True, error_message=None, parameters=()
        )
        svc._semantic.ast = "AST"
        svc._scope_calc._get_module_tables.return_value = {
            "C_01.00": {"variables": {"100": "m"}, "open_keys": {}},
            "C_99.00": {"variables": {"900": "m"}, "open_keys": {}},
            "C_ABS.00": {"variables": {}, "open_keys": {}},
        }
        out = svc.script(
            expressions=[("e1", "v1")],
            module_code="MOD",
            module_version="1.0",
        )
        assert out["success"] is True
        ns = next(iter(out["enriched_ast"].values()))
        # Referenced (C_01.00) AND unreferenced-with-variables (C_99.00)
        # are present; the empty-variable (abstract) table is dropped.
        assert set(ns["tables"]) == {"C_01.00", "C_99.00"}
        assert ns["variables"] == {"100": "m", "900": "m"}

    def test_default_severity_is_warning(self, monkeypatch):
        self._stub_serialize_ast(
            monkeypatch,
            {"class_name": "VarID", "table": "C_01.00", "data": []},
        )
        svc, *_ = self._build_svc()
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=True, error_message=None, parameters=()
        )
        svc._semantic.ast = "AST"
        out = svc.script(
            expressions=[("e1", "v1")],
            module_code="MOD",
            module_version="1.0",
        )
        assert out["success"] is True
        ns = next(iter(out["enriched_ast"].values()))
        assert ns["operations"]["v1"]["severity"] == "warning"

    def test_namespace_falls_back_when_uri_missing(self, monkeypatch):
        self._stub_serialize_ast(
            monkeypatch,
            {"class_name": "VarID", "table": "C_01.00", "data": []},
        )
        svc, *_ = self._build_svc()
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=True, error_message=None, parameters=()
        )
        svc._semantic.ast = "AST"
        svc._scope_calc._get_module_uri.return_value = None
        out = svc.script(
            expressions=[("e1", "v1")],
            module_code="MOD",
            module_version="1.0",
        )
        assert "default_module" in out["enriched_ast"]

    def test_parameters_block_in_enriched_ast(self, monkeypatch):
        # A VarID (for tables) plus a ParameterRef on the RHS — the script()
        # flow must surface the parameter under the ``parameters`` block.
        self._stub_serialize_ast(
            monkeypatch,
            {
                "class_name": "BinOp",
                "left": {
                    "class_name": "VarID",
                    "table": "C_01.00",
                    "data": [{"datapoint": 1, "data_type": "m"}],
                },
                "right": {
                    "class_name": "ParameterRef",
                    "code": "threshold",
                    "param_type": "number",
                    "default": 0,
                },
            },
        )
        svc, *_ = self._build_svc()
        # Parameters now come from SemanticResult.parameters (not a re-walk of
        # the serialised AST). A SimpleNamespace stand-in exposing
        # .code/.declared_type is all _accumulate_parameters reads.
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=True,
            error_message=None,
            parameters=(
                SimpleNamespace(code="threshold", declared_type="Number"),
            ),
        )
        svc._semantic.ast = "AST"
        out = svc.script(
            expressions=[("e1", "v1"), ("e2", "v2")],
            module_code="MOD",
            module_version="1.0",
        )
        assert out["success"] is True
        ns = next(iter(out["enriched_ast"].values()))
        # The trimmed registry is a flat ``code -> declared_type`` map (no
        # nested is_set/default object), deduplicated across both expressions
        # to a single entry. Value correctness is covered by the real-module
        # tests on ``_accumulate_parameters``.
        assert list(ns["parameters"]) == ["threshold"]
        assert ns["parameters"]["threshold"] == "Number"
        assert not isinstance(ns["parameters"]["threshold"], dict)

    def test_parameters_block_empty_when_none_referenced(self, monkeypatch):
        self._stub_serialize_ast(
            monkeypatch,
            {"class_name": "VarID", "table": "C_01.00", "data": []},
        )
        svc, *_ = self._build_svc()
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=True, error_message=None, parameters=()
        )
        svc._semantic.ast = "AST"
        out = svc.script(
            expressions=[("e1", "v1")],
            module_code="MOD",
            module_version="1.0",
        )
        ns = next(iter(out["enriched_ast"].values()))
        assert ns["parameters"] == {}

    def test_script_validates_without_scope_opt_out(self, monkeypatch):
        # Regression: script() must validate each expression through the plain
        # validate() path with no scope opt-out. The opt-out was removed (the
        # scope lookup only runs when an expression references a parameter, so
        # it costs nothing on a parameter-free database), so no call may pass a
        # ``check_scope`` argument. A parameter clash with a co-scoped
        # *persisted* operation is thus always caught; the batch-wide
        # _accumulate_parameters check only sees this script's own expressions.
        self._stub_serialize_ast(
            monkeypatch,
            {"class_name": "VarID", "table": "C_01.00", "data": []},
        )
        svc, *_ = self._build_svc()
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=True, error_message=None, parameters=()
        )
        svc._semantic.ast = "AST"
        svc.script(
            expressions=[("e1", "v1")],
            module_code="MOD",
            module_version="1.0",
        )
        assert svc._semantic.validate.called
        for call in svc._semantic.validate.call_args_list:
            assert "check_scope" not in call.kwargs
