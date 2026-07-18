"""End-to-end tests of the XbrlTaxonomyImportService facade."""

import shutil
import zipfile
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dpmcore.loaders.xbrl import (
    XbrlImportError,
    XbrlTaxonomyImportService,
)
from dpmcore.orm.packaging import (
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.services.schema_validation import SchemaValidationService


@pytest.fixture
def memory_service():
    engine = create_engine("sqlite:///:memory:")
    yield XbrlTaxonomyImportService(engine), engine
    engine.dispose()


def seg_kwargs(**overrides):
    kwargs = {
        "framework_code": "SEG",
        "framework_name": "Segregation",
        "release_code": "2008-01-01",
        "release_date": date(2008, 1, 1),
        "offline": True,
    }
    kwargs.update(overrides)
    return kwargs


class TestFreshImport:
    def test_seg_directory_import(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, engine = memory_service
        result = service.import_taxonomy(
            xbrl_fixtures_dir / "seg2008", **seg_kwargs()
        )
        assert result.architecture == "eurofiling2006"
        assert result.created["TableVersion"] == 1
        assert result.created["Cell"] == 65
        assert result.database_path is None  # in-memory engine
        assert SchemaValidationService(engine).validate().is_valid

    def test_zip_import(
        self, memory_service, xbrl_fixtures_dir, tmp_path
    ):
        service, _ = memory_service
        archive = tmp_path / "seg.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for path in (xbrl_fixtures_dir / "seg2008").iterdir():
                zf.write(path, path.name)
        result = service.import_taxonomy(archive, **seg_kwargs())
        assert result.created["TableVersion"] == 1

    def test_dpm1_auto_detection(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, _ = memory_service
        result = service.import_taxonomy(
            xbrl_fixtures_dir / "mini_dpm1",
            framework_code="MINI",
            release_code="1.0.0",
        )
        assert result.architecture == "dpm1"
        assert result.created["ModuleVersion"] == 1
        assert result.created["Cell"] == 4

    def test_sqlite_file_gets_conventional_name(
        self, xbrl_fixtures_dir, tmp_path
    ):
        db_path = tmp_path / "seg.db"
        engine = create_engine(f"sqlite:///{db_path}")
        service = XbrlTaxonomyImportService(engine)
        result = service.import_taxonomy(
            xbrl_fixtures_dir / "seg2008", **seg_kwargs()
        )
        assert result.database_path is not None
        assert result.database_path.name.startswith("seg_2008-01-01_")
        assert result.database_path.exists()
        assert not db_path.exists()
        engine.dispose()

    def test_explicit_entry_points(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, _ = memory_service
        result = service.import_taxonomy(
            xbrl_fixtures_dir / "seg2008",
            entry_points=["t-Segr-2008-01-01.xsd"],
            **seg_kwargs(),
        )
        assert result.created["TableVersion"] == 1

    def test_duplicate_table_codes_warn(
        self, memory_service, xbrl_fixtures_dir, tmp_path
    ):
        # Two copies of the SEG entry point -> same table code twice.
        workdir = tmp_path / "dup"
        shutil.copytree(xbrl_fixtures_dir / "seg2008", workdir)
        duplicate = workdir / "t-Segr-2009-01-01.xsd"
        shutil.copy(workdir / "t-Segr-2008-01-01.xsd", duplicate)
        service, _ = memory_service
        result = service.import_taxonomy(workdir, **seg_kwargs())
        assert any(
            "Multiple entry points define tables" in w
            for w in result.warnings
        )
        assert result.created["TableVersion"] == 1


class TestSingleModule:
    """The 2006 ``single_module`` collapse option.

    Combines the SEG and FIB fixtures into one taxonomy root so that
    discovery yields two ``t-*.xsd`` entry points (tables ``Segr`` and
    ``FinInstr``); the two folders share identical ``d-*`` schemas.
    """

    @pytest.fixture
    def combined_dir(self, xbrl_fixtures_dir, tmp_path):
        workdir = tmp_path / "combined"
        shutil.copytree(xbrl_fixtures_dir / "seg2008", workdir)
        for path in (xbrl_fixtures_dir / "fib2008").iterdir():
            shutil.copy(path, workdir / path.name)
        return workdir

    def test_default_is_one_module_per_table(
        self, memory_service, combined_dir
    ):
        service, _ = memory_service
        result = service.import_taxonomy(combined_dir, **seg_kwargs())
        assert result.created["TableVersion"] == 2
        assert result.created["ModuleVersion"] == 2

    def test_single_module_collapses_all_tables(
        self, memory_service, combined_dir
    ):
        service, engine = memory_service
        result = service.import_taxonomy(
            combined_dir, **seg_kwargs(single_module=True)
        )
        assert result.created["TableVersion"] == 2
        assert result.created["ModuleVersion"] == 1
        session = sessionmaker(bind=engine)()
        try:
            version = session.query(ModuleVersion).one()
            # Coded/named after the framework, not a table.
            assert version.code == "SEG"
            assert version.name == "Segregation"
            # The one module comprises both discovered tables.
            comps = (
                session.query(ModuleVersionComposition)
                .filter(
                    ModuleVersionComposition.module_vid
                    == version.module_vid
                )
                .count()
            )
            assert comps == 2
        finally:
            session.close()


class TestExistingImport:
    def test_fib_into_seg_database(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, _ = memory_service
        service.import_taxonomy(
            xbrl_fixtures_dir / "seg2008", **seg_kwargs()
        )
        result = service.import_taxonomy(
            xbrl_fixtures_dir / "fib2008",
            framework_code="FIB",
            release_code="FIB-2008-01-01",
            offline=True,
            into_existing=True,
        )
        assert result.created["Framework"] == 1
        assert result.reused.get("Organisation") == 1
        # Members of the shared scope domain are reused by signature.
        assert result.reused.get("Item", 0) >= 5

    def test_reimport_into_existing_is_idempotent(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, _ = memory_service
        service.import_taxonomy(
            xbrl_fixtures_dir / "seg2008", **seg_kwargs()
        )
        result = service.import_taxonomy(
            xbrl_fixtures_dir / "seg2008",
            **seg_kwargs(into_existing=True),
        )
        assert result.created.get("Item") is None
        assert result.created.get("Cell") is None
        assert result.reused["TableVersion"] == 1

    def test_existing_mode_requires_valid_dpm_database(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, _ = memory_service  # empty database, no schema
        with pytest.raises(XbrlImportError, match="not a valid DPM"):
            service.import_taxonomy(
                xbrl_fixtures_dir / "seg2008",
                **seg_kwargs(into_existing=True),
            )


class TestSourceErrors:
    def test_missing_source(self, memory_service, tmp_path):
        service, _ = memory_service
        with pytest.raises(XbrlImportError, match="does not exist"):
            service.import_taxonomy(
                tmp_path / "nope", **seg_kwargs()
            )

    def test_non_zip_file_source(self, memory_service, tmp_path):
        service, _ = memory_service
        stray = tmp_path / "taxonomy.tar"
        stray.write_text("not a taxonomy", encoding="utf-8")
        with pytest.raises(XbrlImportError, match="directory or a"):
            service.import_taxonomy(stray, **seg_kwargs())

    def test_corrupt_zip(self, memory_service, tmp_path):
        service, _ = memory_service
        bad = tmp_path / "broken.zip"
        bad.write_bytes(b"PK\x03\x04 garbage")
        with pytest.raises(XbrlImportError, match="not a valid zip"):
            service.import_taxonomy(bad, **seg_kwargs())

    def test_unknown_architecture(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, _ = memory_service
        with pytest.raises(XbrlImportError, match="Unknown architecture"):
            service.import_taxonomy(
                xbrl_fixtures_dir / "seg2008",
                **seg_kwargs(architecture="dpm2"),
            )

    def test_undetectable_architecture(self, memory_service, tmp_path):
        service, _ = memory_service
        (tmp_path / "readme.txt").write_text("hi", encoding="utf-8")
        with pytest.raises(XbrlImportError, match="Could not detect"):
            service.import_taxonomy(tmp_path, **seg_kwargs())

    def test_requested_dpm1_but_not_present(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, _ = memory_service
        with pytest.raises(XbrlImportError, match="no dict/"):
            service.import_taxonomy(
                xbrl_fixtures_dir / "seg2008",
                **seg_kwargs(architecture="dpm1"),
            )

    def test_requested_2006_but_not_present(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, _ = memory_service
        with pytest.raises(XbrlImportError, match="no t-"):
            service.import_taxonomy(
                xbrl_fixtures_dir / "mini_dpm1",
                **seg_kwargs(architecture="eurofiling2006"),
            )

    def test_missing_entry_point(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, _ = memory_service
        with pytest.raises(XbrlImportError, match="not found under"):
            service.import_taxonomy(
                xbrl_fixtures_dir / "seg2008",
                entry_points=["t-Ghost-2008-01-01.xsd"],
                **seg_kwargs(),
            )

    def test_directory_without_entry_points(
        self, memory_service, tmp_path
    ):
        service, _ = memory_service
        # Force 2006 architecture on a dir whose only t-*.xsd is
        # then removed to hit the discovery error.
        marker = tmp_path / "t-Temp-2008-01-01.xsd"
        marker.write_text("<schema/>", encoding="utf-8")
        service_error = None
        marker.unlink()
        (tmp_path / "d-Other-2008-01-01.xsd").write_text(
            "<schema/>", encoding="utf-8"
        )
        try:
            service.import_taxonomy(
                tmp_path,
                **seg_kwargs(architecture="eurofiling2006"),
            )
        except XbrlImportError as exc:
            service_error = str(exc)
        assert service_error is not None


class TestMappingFailureRollsBack:
    def test_unexpected_mapper_error_is_wrapped(
        self, memory_service, xbrl_fixtures_dir, monkeypatch
    ):
        from dpmcore.loaders.xbrl import service as service_module

        service, _ = memory_service

        def explode(self, model):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            service_module.TaxonomyMapper, "map_model", explode
        )
        with pytest.raises(XbrlImportError, match="boom"):
            service.import_taxonomy(
                xbrl_fixtures_dir / "seg2008", **seg_kwargs()
            )


class TestRemainingBranches:
    def test_explicit_architecture_selection(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, _ = memory_service
        result = service.import_taxonomy(
            xbrl_fixtures_dir / "mini_dpm1",
            framework_code="MINI",
            release_code="1.0.0",
            architecture="dpm1",
        )
        assert result.architecture == "dpm1"

    def test_explicit_2006_architecture_selection(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, _ = memory_service
        result = service.import_taxonomy(
            xbrl_fixtures_dir / "seg2008",
            **seg_kwargs(architecture="eurofiling2006"),
        )
        assert result.architecture == "eurofiling2006"

    def test_entry_point_glob_pattern(
        self, memory_service, xbrl_fixtures_dir
    ):
        service, _ = memory_service
        result = service.import_taxonomy(
            xbrl_fixtures_dir / "seg2008",
            entry_points=["t-Segr-*.xsd"],
            **seg_kwargs(),
        )
        assert result.created["TableVersion"] == 1

    def test_entry_point_discovery_error(self, tmp_path):
        from dpmcore.loaders.xbrl.service import _resolve_entry_points

        with pytest.raises(XbrlImportError, match="No t-"):
            _resolve_entry_points(tmp_path, None)

    def test_mapper_import_error_passes_through(
        self, memory_service, xbrl_fixtures_dir, monkeypatch
    ):
        from dpmcore.loaders.xbrl import service as service_module

        service, _ = memory_service

        def explode(self, model):
            raise XbrlImportError("mapper says no")

        monkeypatch.setattr(
            service_module.TaxonomyMapper, "map_model", explode
        )
        with pytest.raises(XbrlImportError, match="mapper says no"):
            service.import_taxonomy(
                xbrl_fixtures_dir / "seg2008", **seg_kwargs()
            )
