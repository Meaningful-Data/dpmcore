"""Tests for the ast_generator dependency-info helpers and script flow."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _patch_orm(monkeypatch):
    """Prevent the ORM import chain on Python 3.10."""
    # Stub only the ORM chain + direct ast_generator deps. The AST template
    # package must remain a real package so the deferred import of
    # ``dpmcore.dpm_xl.ast.template`` in ``_extract_time_shifts`` resolves.
    stubs = {
        "dpmcore.orm": MagicMock(),
        "dpmcore.orm.infrastructure": MagicMock(),
        "dpmcore.orm.packaging": MagicMock(),
        "dpmcore.orm.operations": MagicMock(),
        "dpmcore.orm.rendering": MagicMock(),
        "dpmcore.orm.variables": MagicMock(),
        "dpmcore.orm.glossary": MagicMock(),
        "dpmcore.errors": MagicMock(),
        "dpmcore.services.scope_calculator": MagicMock(),
        "dpmcore.services.semantic": MagicMock(),
        "dpmcore.services.syntax": MagicMock(),
        "dpmcore.dpm_xl.utils.serialization": MagicMock(),
    }
    for name, stub in stubs.items():
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, stub)


def _load_ast_generator():
    """Load ``ast_generator`` bypassing the ORM chain."""
    mod_name = "dpmcore.services.ast_generator"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(
        mod_name,
        _REPO_ROOT / "src/dpmcore/services/ast_generator.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod.ASTGeneratorService


# ------------------------------------------------------------------ #
# _build_dependency_info
# ------------------------------------------------------------------ #


def _svc_with_scope_calc(detect_return=None, alt_return=None):
    """Build an ASTGeneratorService whose _scope_calc is a configured mock."""
    Cls = _load_ast_generator()
    svc = Cls.__new__(Cls)
    svc._scope_calc = MagicMock()
    svc._scope_calc.detect_cross_module_dependencies.return_value = (
        detect_return
        or {
            "intra_instance_validations": [],
            "cross_instance_dependencies": [],
            "dependency_modules": {},
        }
    )
    svc._scope_calc.detect_alternative_dependencies.return_value = (
        alt_return or []
    )
    return svc


class TestBuildDependencyInfo:
    def test_none_when_scope_calc_missing(self):
        Cls = _load_ast_generator()
        svc = Cls.__new__(Cls)
        svc._scope_calc = None
        assert (
            svc._build_dependency_info(
                scope_pairs=[("X",)],
                primary_module_vid=1,
                release_id=None,
            )
            is None
        )

    def test_none_when_primary_module_vid_none(self):
        svc = _svc_with_scope_calc()
        assert (
            svc._build_dependency_info(
                scope_pairs=[(("e",), MagicMock(), {})],
                primary_module_vid=None,
                release_id=None,
            )
            is None
        )

    def test_none_when_scope_pairs_empty(self):
        svc = _svc_with_scope_calc()
        assert (
            svc._build_dependency_info(
                scope_pairs=[],
                primary_module_vid=1,
                release_id=None,
            )
            is None
        )

    def test_aggregates_and_dedupes_intra(self):
        svc = _svc_with_scope_calc(
            detect_return={
                "intra_instance_validations": ["v1"],
                "cross_instance_dependencies": [],
                "dependency_modules": {},
            }
        )
        # Both items carry the same op_code -> expect one entry after dedupe.
        scope_pairs = [
            (("e1", "v1"), MagicMock(), {}),
            (("e2", "v1"), MagicMock(), {}),
        ]
        result = svc._build_dependency_info(
            scope_pairs=scope_pairs,
            primary_module_vid=1,
            release_id=None,
        )
        info = result["dependency_information"]
        assert info["intra_instance_validations"] == ["v1"]

    def test_op_code_none_when_single_element_item(self):
        svc = _svc_with_scope_calc()
        scope_pairs = [(("only_expr",), MagicMock(), {})]
        svc._build_dependency_info(
            scope_pairs=scope_pairs,
            primary_module_vid=1,
            release_id=None,
        )
        call = svc._scope_calc.detect_cross_module_dependencies.call_args
        assert call.kwargs["operation_code"] is None

    def test_passes_op_code_from_tuple(self):
        svc = _svc_with_scope_calc()
        scope_pairs = [(("expr", "V42"), MagicMock(), {"T_01": "T-1Q"})]
        svc._build_dependency_info(
            scope_pairs=scope_pairs,
            primary_module_vid=1,
            release_id=None,
        )
        call = svc._scope_calc.detect_cross_module_dependencies.call_args
        assert call.kwargs["operation_code"] == "V42"
        assert call.kwargs["time_shifts"] == {"T_01": "T-1Q"}


# ------------------------------------------------------------------ #
# _merge_dep_modules
# ------------------------------------------------------------------ #


class TestMergeDepModules:
    def test_new_uri_inserted(self):
        Cls = _load_ast_generator()
        existing = {}
        Cls._merge_dep_modules(
            existing, {"http://a": {"tables": {"T": {}}, "variables": {}}}
        )
        assert "http://a" in existing

    def test_existing_uri_merges_tables_without_overwriting(self):
        Cls = _load_ast_generator()
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
        # T1 is kept as-is (setdefault), T2 is added.
        assert existing["http://a"]["tables"]["T1"]["variables"] == {}
        assert "T2" in existing["http://a"]["tables"]
        # Variables are merged (update), so v2 appears alongside v1.
        assert existing["http://a"]["variables"] == {"v1": "x", "v2": "y"}


# ------------------------------------------------------------------ #
# _extract_time_shifts
# ------------------------------------------------------------------ #


class _FakeTimeShiftOp:
    """Type-name dispatches to ``visit_TimeShiftOp`` in ASTTemplate."""

    def __init__(self, period_indicator, shift_number, operand):
        self.period_indicator = period_indicator
        self.shift_number = shift_number
        self.operand = operand


# Match the real node class name that the AST visitor dispatches on.
_FakeTimeShiftOp.__name__ = "TimeShiftOp"


class _FakeVarID:
    def __init__(self, table):
        self.table = table


_FakeVarID.__name__ = "VarID"


class TestExtractTimeShifts:
    def test_empty_ast_returns_empty(self):
        Cls = _load_ast_generator()
        # Real ASTTemplate dispatches by class name — unknown node types
        # route to generic_visit which recurses on public attrs. A bare
        # SimpleNamespace with no attrs yields nothing.
        assert Cls._extract_time_shifts(SimpleNamespace()) == {}

    def test_negative_shift_produces_T_minus(self):
        Cls = _load_ast_generator()
        inner = _FakeVarID(table="T_01")
        node = _FakeTimeShiftOp(
            period_indicator="Q",
            shift_number="1",
            operand=inner,
        )
        assert Cls._extract_time_shifts(node) == {"T_01": "T-1Q"}

    def test_positive_shift_produces_T_plus(self):
        """``shift_number`` containing '-' drives the ``t+`` internal form."""
        Cls = _load_ast_generator()
        inner = _FakeVarID(table="T_02")
        node = _FakeTimeShiftOp(
            period_indicator="Y",
            shift_number="-2",
            operand=inner,
        )
        # internal "t+Y-2" -> "T-2Y" (num.startswith("-") branch).
        assert Cls._extract_time_shifts(node) == {"T_02": "T-2Y"}

    def test_var_without_table_is_ignored(self):
        Cls = _load_ast_generator()
        inner = _FakeVarID(table=None)
        node = _FakeTimeShiftOp(
            period_indicator="Q",
            shift_number="1",
            operand=inner,
        )
        assert Cls._extract_time_shifts(node) == {}

    def test_exception_returns_empty(self):
        """An unexpected failure is swallowed and yields ``{}``."""
        Cls = _load_ast_generator()

        class Boom:
            def __getattr__(self, item):
                raise RuntimeError("boom")

        assert Cls._extract_time_shifts(Boom()) == {}


# ------------------------------------------------------------------ #
# parse() / complete() / script() entry points
# ------------------------------------------------------------------ #


def _build_svc(session=None):
    """Construct an ASTGeneratorService with internal services pre-mocked."""
    Cls = _load_ast_generator()
    svc = Cls.__new__(Cls)
    svc.session = session
    svc._syntax = MagicMock()
    svc._semantic = MagicMock() if session is not None else None
    svc._scope_calc = MagicMock() if session is not None else None
    return svc, Cls


class TestParse:
    def test_parse_success(self, monkeypatch):
        svc, _ = _build_svc()
        svc._syntax.parse.return_value = "RAW_AST"
        monkeypatch.setattr(
            sys.modules["dpmcore.services.ast_generator"],
            "serialize_ast",
            lambda x: {"n": x},
        )
        out = svc.parse("1+1")
        assert out == {"success": True, "ast": {"n": "RAW_AST"}, "error": None}

    def test_parse_exception(self):
        svc, _ = _build_svc()
        svc._syntax.parse.side_effect = RuntimeError("bad syntax")
        out = svc.parse("???")
        assert out["success"] is False
        assert out["error"] == "bad syntax"


class TestComplete:
    def test_no_session_returns_error(self):
        svc, _ = _build_svc(session=None)
        out = svc.complete("1+1")
        assert out["success"] is False
        assert "No database session" in out["error"]

    def test_invalid_returns_error(self):
        svc, _ = _build_svc(session=MagicMock())
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=False,
            error_message="bad",
            warning=None,
        )
        out = svc.complete("x")
        assert out["success"] is False
        assert out["error"] == "bad"

    def test_valid_returns_payload(self, monkeypatch):
        svc, _ = _build_svc(session=MagicMock())
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=True, error_message=None, warning="w"
        )
        svc._semantic.ast = "AST"
        svc._semantic.oc_data = {"d": 1}
        svc._semantic.oc_tables = {"t": 2}
        monkeypatch.setattr(
            sys.modules["dpmcore.services.ast_generator"],
            "serialize_ast",
            lambda x: {"ser": x},
        )
        out = svc.complete("x")
        assert out["success"] is True
        assert out["ast"] == {"ser": "AST"}
        assert out["warning"] == "w"


class TestScript:
    def _prime_ast_modules(self, monkeypatch):
        """Inject stubs for the two ``ast`` subpackages loaded inside script()."""
        ml_mod = MagicMock()
        ml_mod.MLGeneration = lambda **kw: {"ml": kw["ast"]}
        ma_mod = MagicMock()
        ma_mod.ModuleAnalyzer.return_value.visit.return_value = ("MODE", [])
        monkeypatch.setitem(sys.modules, "dpmcore.dpm_xl.ast.ml_generation", ml_mod)
        monkeypatch.setitem(sys.modules, "dpmcore.dpm_xl.ast.module_analyzer", ma_mod)

    def test_no_session_returns_error(self):
        svc, _ = _build_svc(session=None)
        out = svc.script("x")
        assert out["success"] is False
        assert "No database session" in out["error"]

    def test_validation_error_short_circuits(self, monkeypatch):
        self._prime_ast_modules(monkeypatch)
        svc, _ = _build_svc(session=MagicMock())
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=False, error_message="nope"
        )
        out = svc.script("x")
        assert out["success"] is False
        assert out["error"] == "nope"

    def test_runtime_error_caught(self, monkeypatch):
        self._prime_ast_modules(monkeypatch)
        svc, _ = _build_svc(session=MagicMock())
        svc._semantic.validate.side_effect = RuntimeError("boom")
        out = svc.script("x")
        assert out["success"] is False
        assert "boom" in out["error"]

    def test_happy_path_no_dependency_context(self, monkeypatch):
        """Without primary_module_vid the scope branch is skipped."""
        self._prime_ast_modules(monkeypatch)
        svc, _ = _build_svc(session=MagicMock())
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=True, error_message=None
        )
        svc._semantic.ast = "AST"
        out = svc.script("x")
        assert out["success"] is True
        assert len(out["enriched_ast"]) == 1
        # _scope_calc should not have been queried.
        svc._scope_calc.calculate_from_expression.assert_not_called()
        assert "dependency_information" not in out

    def test_list_input_with_scope_and_time_shifts(self, monkeypatch):
        """Supplying primary_module_vid + operation_version_id attaches info."""
        self._prime_ast_modules(monkeypatch)
        svc, _ = _build_svc(session=MagicMock())
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=True, error_message=None
        )
        svc._semantic.ast = "AST"

        svc._scope_calc.calculate_from_expression.return_value = SimpleNamespace(
            has_error=False,
            existing_scopes=[],
            new_scopes=[],
        )
        svc._scope_calc.detect_cross_module_dependencies.return_value = {
            "intra_instance_validations": ["v1"],
            "cross_instance_dependencies": [],
            "dependency_modules": {"http://m": {"tables": {}, "variables": {}}},
        }
        svc._scope_calc.detect_alternative_dependencies.return_value = []

        out = svc.script(
            expressions=[("e1", "v1"), ("e2", "v1")],
            primary_module_vid=1,
            operation_version_id=42,
        )
        assert out["success"] is True
        info = out["dependency_information"]
        assert info["intra_instance_validations"] == ["v1"]
        assert out["dependency_modules"] == {
            "http://m": {"tables": {}, "variables": {}}
        }

    def test_scope_error_excluded_from_pairs(self, monkeypatch):
        """Scope results with ``has_error`` are skipped entirely."""
        self._prime_ast_modules(monkeypatch)
        svc, _ = _build_svc(session=MagicMock())
        svc._semantic.validate.return_value = SimpleNamespace(
            is_valid=True, error_message=None
        )
        svc._semantic.ast = "AST"
        svc._scope_calc.calculate_from_expression.return_value = SimpleNamespace(
            has_error=True,
            existing_scopes=[],
            new_scopes=[],
        )
        out = svc.script(
            "x",
            primary_module_vid=1,
            operation_version_id=42,
        )
        assert out["success"] is True
        # No pairs means _build_dependency_info returns None.
        assert "dependency_information" not in out
