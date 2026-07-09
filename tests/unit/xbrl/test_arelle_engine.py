"""Unit tests for the Arelle adapter using stub controllers."""

import pytest

from dpmcore.loaders.xbrl.arelle_engine import ArelleEngine
from dpmcore.loaders.xbrl.model import XbrlImportError


class StubModelXbrl:
    def __init__(self, errors):
        self.errors = errors
        self.closed = False

    def close(self):
        self.closed = True


class StubModelManager:
    def __init__(self, model):
        self._model = model
        self.loaded = []
        self.closed = False

    def load(self, path):
        self.loaded.append(path)
        return self._model

    def close(self):
        self.closed = True


class StubController:
    def __init__(self, model):
        self.modelManager = StubModelManager(model)


def engine_with_stub(model):
    engine = ArelleEngine()
    engine._cntlr = StubController(model)
    return engine


class TestLoad:
    def test_missing_entry_point_raises(self, tmp_path):
        engine = engine_with_stub(StubModelXbrl([]))
        with pytest.raises(XbrlImportError, match="does not exist"):
            engine.load(tmp_path / "missing.xsd")

    def test_successful_load_returns_model(self, tmp_path):
        entry = tmp_path / "ok.xsd"
        entry.write_text("<schema/>", encoding="utf-8")
        model = StubModelXbrl([])
        engine = engine_with_stub(model)
        assert engine.load(entry) is model

    def test_reuses_cached_controller_across_loads(self, tmp_path):
        entry = tmp_path / "ok.xsd"
        entry.write_text("<schema/>", encoding="utf-8")
        model = StubModelXbrl([])
        engine = engine_with_stub(model)
        controller = engine._cntlr
        engine.load(entry)
        engine.load(entry)
        assert engine._cntlr is controller
        assert len(controller.modelManager.loaded) == 2

    def test_io_errors_add_cache_hint(self, tmp_path):
        entry = tmp_path / "bad.xsd"
        entry.write_text("<schema/>", encoding="utf-8")
        model = StubModelXbrl(["IOerror"])
        engine = engine_with_stub(model)
        with pytest.raises(XbrlImportError, match="cache-dir"):
            engine.load(entry)
        assert model.closed is True

    def test_other_errors_have_no_cache_hint(self, tmp_path):
        entry = tmp_path / "bad.xsd"
        entry.write_text("<schema/>", encoding="utf-8")
        model = StubModelXbrl(["xmlSchema:syntax"])
        engine = engine_with_stub(model)
        with pytest.raises(XbrlImportError) as excinfo:
            engine.load(entry)
        assert "cache-dir" not in str(excinfo.value)


class TestClose:
    def test_close_disposes_controller(self):
        engine = engine_with_stub(StubModelXbrl([]))
        manager = engine._cntlr.modelManager
        engine.close()
        assert manager.closed is True
        assert engine._cntlr is None

    def test_close_without_controller_is_a_noop(self):
        engine = ArelleEngine()
        engine.close()
        assert engine._cntlr is None


class TestControllerConstruction:
    def test_controller_without_cache_dir_uses_default(
        self, tmp_path, monkeypatch
    ):
        # Keep Arelle's default config/cache inside the test tmpdir.
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
        engine = ArelleEngine(offline=True)
        controller = engine._controller()
        assert controller.webCache.workOffline is True
        engine.close()
