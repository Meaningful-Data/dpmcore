"""End-to-end import of the real SEG/FIB 2008 taxonomies.

Loads the committed NBB taxonomies through Arelle (offline, using
the committed web-cache fixture), reduces them with the
2006-architecture reader and maps them into an in-memory DPM
database.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dpmcore.loaders.xbrl.arelle_engine import ArelleEngine
from dpmcore.loaders.xbrl.mapper import TaxonomyMapper
from dpmcore.loaders.xbrl.model import XbrlImportError
from dpmcore.loaders.xbrl.reader_eurofiling2006 import read_entry_point
from dpmcore.orm.glossary import Category, Item, Property
from dpmcore.orm.packaging import Framework, ModuleVersion
from dpmcore.orm.rendering import TableVersion, TableVersionCell
from dpmcore.orm.variables import VariableVersion


@pytest.fixture
def schema_session():
    engine = create_engine("sqlite:///:memory:")
    from dpmcore.orm.base import Base

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def read_taxonomy(xbrl_fixtures_dir, webcache_dir, folder, entry, code):
    engine = ArelleEngine(offline=True, cache_dir=webcache_dir)
    try:
        entry_path = xbrl_fixtures_dir / folder / entry
        model_xbrl = engine.load(entry_path)
        return read_entry_point(
            model_xbrl,
            framework_code=code,
            framework_name=f"{code} framework",
            entry_path=entry_path,
        )
    finally:
        engine.close()


class TestSegImport:
    def test_seg_reads_expected_structure(
        self, xbrl_fixtures_dir, webcache_dir
    ):
        model = read_taxonomy(
            xbrl_fixtures_dir,
            webcache_dir,
            "seg2008",
            "t-Segr-2008-01-01.xsd",
            "SEG",
        )
        assert len(model.metrics) == 13
        assert len(model.domains) == 1
        assert {d.qname for d in model.dimensions} == {
            "d-hh:NullDimension",
            "d-sc-be:ScopeDimension",
        }
        table = model.tables[0]
        assert table.code == "Segr"
        assert table.name == "Segregation"
        assert len(table.axis("Y").nodes) == 16
        # Scope dimension enumerates to five columns.
        assert len(table.axis("X").nodes) == 5
        assert len(table.cells) == 65
        module = model.modules[0]
        assert module.from_date == date(2008, 1, 1)
        assert model.warnings == ()

    def test_seg_maps_into_dpm_database(
        self, xbrl_fixtures_dir, webcache_dir, schema_session
    ):
        model = read_taxonomy(
            xbrl_fixtures_dir,
            webcache_dir,
            "seg2008",
            "t-Segr-2008-01-01.xsd",
            "SEG",
        )
        mapper = TaxonomyMapper(
            schema_session,
            owner_name="National Bank of Belgium",
            owner_acronym="NBB",
            release_code="2008-01-01",
            release_date=date(2008, 1, 1),
            fresh=True,
        )
        outcome = mapper.map_model(model)
        schema_session.commit()

        assert outcome.created["Framework"] == 1
        assert outcome.created["TableVersion"] == 1
        assert outcome.created["ModuleVersion"] == 1
        assert outcome.created["Cell"] == 65
        # 13 metrics + 2 dimensions as property items, 5 members.
        assert outcome.created["Property"] == 15
        framework = schema_session.query(Framework).one()
        assert framework.code == "SEG"
        assert (
            schema_session.query(VariableVersion).count()
            == outcome.created["Variable"]
        )
        # All cells reference a variable version.
        for link in schema_session.query(TableVersionCell).all():
            assert link.variable_vid is not None

    def test_seg_import_passes_schema_validation(
        self, xbrl_fixtures_dir, webcache_dir, tmp_path
    ):
        from dpmcore.services.schema_validation import (
            SchemaValidationService,
        )

        db_path = tmp_path / "seg.db"
        engine = create_engine(f"sqlite:///{db_path}")
        from dpmcore.orm.base import Base

        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        model = read_taxonomy(
            xbrl_fixtures_dir,
            webcache_dir,
            "seg2008",
            "t-Segr-2008-01-01.xsd",
            "SEG",
        )
        mapper = TaxonomyMapper(
            session,
            owner_name="National Bank of Belgium",
            owner_acronym="NBB",
            release_code="2008-01-01",
            fresh=True,
        )
        mapper.map_model(model)
        session.commit()
        session.close()

        result = SchemaValidationService(engine).validate()
        assert result.is_valid, (
            result.missing_tables,
            result.empty_required_tables,
        )
        engine.dispose()


class TestFibImport:
    def test_fib_reads_and_maps(
        self, xbrl_fixtures_dir, webcache_dir, schema_session
    ):
        model = read_taxonomy(
            xbrl_fixtures_dir,
            webcache_dir,
            "fib2008",
            "t-FinInstr-2008-01-01.xsd",
            "FIB",
        )
        assert model.tables[0].code == "FinInstr"
        assert len(model.metrics) > 0

        mapper = TaxonomyMapper(
            schema_session,
            owner_name="National Bank of Belgium",
            owner_acronym="NBB",
            release_code="2008-01-01",
            fresh=True,
        )
        outcome = mapper.map_model(model)
        schema_session.commit()
        assert outcome.created["TableVersion"] == 1
        assert outcome.created["Cell"] == len(model.tables[0].cells)


class TestMultiFrameworkAndIdempotency:
    def _map(self, session, model, release_code="2008-01-01"):
        mapper = TaxonomyMapper(
            session,
            owner_name="National Bank of Belgium",
            owner_acronym="NBB",
            release_code=release_code,
            fresh=True,
        )
        outcome = mapper.map_model(model)
        session.commit()
        return outcome

    def test_reimport_is_a_no_op(
        self, xbrl_fixtures_dir, webcache_dir, schema_session
    ):
        model = read_taxonomy(
            xbrl_fixtures_dir,
            webcache_dir,
            "seg2008",
            "t-Segr-2008-01-01.xsd",
            "SEG",
        )
        first = self._map(schema_session, model)
        second = self._map(schema_session, model)

        assert second.created.get("Item") is None
        assert second.created.get("Cell") is None
        assert second.created.get("TableVersion") is None
        assert second.reused["TableVersion"] == 1
        assert (
            schema_session.query(Item).count()
            == sum(first.created.get(k, 0) for k in ("Item",))
        )

    def test_fib_into_seg_database_coexists(
        self, xbrl_fixtures_dir, webcache_dir, schema_session
    ):
        seg = read_taxonomy(
            xbrl_fixtures_dir,
            webcache_dir,
            "seg2008",
            "t-Segr-2008-01-01.xsd",
            "SEG",
        )
        fib = read_taxonomy(
            xbrl_fixtures_dir,
            webcache_dir,
            "fib2008",
            "t-FinInstr-2008-01-01.xsd",
            "FIB",
        )
        self._map(schema_session, seg)
        outcome = self._map(schema_session, fib)

        assert schema_session.query(Framework).count() == 2
        assert schema_session.query(TableVersion).count() == 2
        # The shared d-sc-be scope members are reused, not duplicated.
        assert outcome.reused.get("Item", 0) >= 5
        special = (
            schema_session.query(Category)
            .filter(Category.code.in_(["_PR", "_NA"]))
            .count()
        )
        assert special == 2
        # Shared scope dimension property: reused via its GUID only
        # when frameworks match; FIB creates its own here, so both
        # frameworks have complete dictionaries.
        assert schema_session.query(Property).count() > 0

    def test_module_versions_carry_entry_point(
        self, xbrl_fixtures_dir, webcache_dir, schema_session
    ):
        model = read_taxonomy(
            xbrl_fixtures_dir,
            webcache_dir,
            "seg2008",
            "t-Segr-2008-01-01.xsd",
            "SEG",
        )
        self._map(schema_session, model)
        version = schema_session.query(ModuleVersion).one()
        assert version.description == "t-Segr-2008-01-01.xsd"
        assert version.from_reference_date == date(2008, 1, 1)


class TestOfflineFailure:
    def test_missing_entry_point_raises(self, webcache_dir, tmp_path):
        engine = ArelleEngine(offline=True, cache_dir=webcache_dir)
        with pytest.raises(XbrlImportError, match="does not exist"):
            engine.load(tmp_path / "nope.xsd")
        engine.close()

    def test_unresolvable_dts_raises_with_cache_hint(self, tmp_path):
        # A remote reference that is neither cached nor bundled
        # cannot resolve offline.
        entry = tmp_path / "broken.xsd"
        entry.write_text(
            '<?xml version="1.0"?>\n'
            '<schema xmlns="http://www.w3.org/2001/XMLSchema"\n'
            '        targetNamespace="http://example.com/broken">\n'
            '  <import namespace="http://example.com/missing"\n'
            '          schemaLocation='
            '"http://example.com/missing.xsd"/>\n'
            "</schema>\n",
            encoding="utf-8",
        )
        engine = ArelleEngine(
            offline=True, cache_dir=tmp_path / "empty-cache"
        )
        with pytest.raises(XbrlImportError, match="could not load"):
            engine.load(entry)
        engine.close()
