"""End-to-end import of the mini dpm1 (TREP-style) fixture."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dpmcore.loaders.xbrl.mapper import TaxonomyMapper
from dpmcore.loaders.xbrl.model import XbrlImportError
from dpmcore.loaders.xbrl.reader_dpm1 import (
    canonical_prefix,
    read_taxonomy,
)
from dpmcore.orm.glossary import Category, ItemCategory, SubCategoryItem
from dpmcore.orm.infrastructure import Translation
from dpmcore.orm.packaging import ModuleVersion
from dpmcore.orm.rendering import Header, TableVersion, TableVersionCell


@pytest.fixture
def schema_session():
    engine = create_engine("sqlite:///:memory:")
    from dpmcore.orm.base import Base

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def mini_model(xbrl_fixtures_dir):
    return read_taxonomy(
        xbrl_fixtures_dir / "mini_dpm1",
        framework_code="MINI",
        framework_name="Mini framework",
    )


class TestCanonicalPrefix:
    def test_eba_domain(self):
        namespace = "http://www.eba.europa.eu/xbrl/crr/dict/dom/BA"
        assert canonical_prefix(namespace) == "eba_BA"

    def test_nbb_met(self):
        assert (
            canonical_prefix("http://www.nbb.be/xbrl/crr/dict/met")
            == "be_met"
        )

    def test_fallback_last_segment(self):
        assert (
            canonical_prefix("http://www.nbb.be/xbrl/other/thing")
            == "be_thing"
        )


class TestMiniRead:
    def test_dictionary_content(self, mini_model):
        assert {d.qname for d in mini_model.dimensions} == {
            "be_dim:EXD",
            "be_dim:TYD",
        }
        typed = next(
            d for d in mini_model.dimensions if d.qname == "be_dim:TYD"
        )
        assert typed.is_typed is True
        assert typed.domain_qname == "be_typ:TH"

        explicit_domain = next(
            d for d in mini_model.domains if d.qname == "be_exp:MD"
        )
        assert [m.code for m in explicit_domain.members] == [
            "x0",
            "x1",
            "x2",
        ]
        assert explicit_domain.members[1].name == "Banks"

    def test_hierarchy_tree(self, mini_model):
        hierarchy = mini_model.hierarchies[0]
        nodes = {n.member_qname: n for n in hierarchy.nodes}
        assert nodes["be_MD:x0"].parent_qname is None
        assert nodes["be_MD:x1"].parent_qname == "be_MD:x0"

    def test_metrics(self, mini_model):
        metrics = {m.qname: m for m in mini_model.metrics}
        assert metrics["be_met:mi1"].name == "Carrying amount"
        assert metrics["be_met:ii2"].period_type == "duration"

    def test_table_structure(self, mini_model):
        table = mini_model.tables[0]
        assert table.code == "T_1.00"
        assert table.name == "T_1.00 Mini table"
        x_axis = table.axis("X")
        assert [n.code for n in x_axis.nodes] == [None, "010", "020"]
        z_axis = table.axis("Z")
        assert z_axis.open_dimension_qnames == ("be_dim:TYD",)
        # 2 metrics x 2 columns.
        assert len(table.cells) == 4
        first = table.cells[0]
        assert first.metric_qname == "be_met:mi1"
        assert first.dim_members == (("be_dim:EXD", "be_MD:x1"),)

    def test_module(self, mini_model):
        module = mini_model.modules[0]
        assert module.code == "mod_a"
        assert module.name == "Module A, consolidé"
        assert module.table_codes == ("T_1.00",)
        assert module.from_date == date(2015, 1, 1)

    def test_bad_root_raises(self, tmp_path):
        with pytest.raises(XbrlImportError, match="dict/ or fws/"):
            read_taxonomy(
                tmp_path,
                framework_code="X",
                framework_name="X",
            )


class TestMiniMapping:
    def test_maps_into_dpm_database(self, mini_model, schema_session):
        mapper = TaxonomyMapper(
            schema_session,
            owner_name="National Bank of Belgium",
            owner_acronym="NBB",
            release_code="1.0.2",
            release_date=date(2015, 1, 1),
            fresh=True,
        )
        outcome = mapper.map_model(mini_model)
        schema_session.commit()

        assert outcome.created["TableVersion"] == 1
        assert outcome.created["ModuleVersion"] == 1
        assert outcome.created["Cell"] == 4
        # Member signatures follow the DPM convention.
        signatures = {
            link.signature
            for link in schema_session.query(ItemCategory).all()
        }
        assert "be_MD:x1" in signatures

        # French labels land in Translation.
        translations = {
            t.translation
            for t in schema_session.query(Translation).all()
        }
        assert "Banques" in translations  # member label
        assert "Valeur comptable" in translations  # metric label

        # The typed dimension becomes an open sheet key header.
        key_header = (
            schema_session.query(Header)
            .filter(Header.is_key.is_(True))
            .one()
        )
        assert key_header.direction == "Z"

        version = schema_session.query(TableVersion).one()
        assert version.code == "T_1.00"
        cell_codes = {
            link.cell_code
            for link in schema_session.query(TableVersionCell).all()
        }
        assert "{T_1.00, r010, c010}" in cell_codes

        module_version = schema_session.query(ModuleVersion).one()
        assert module_version.code == "mod_a"

        domain_category = (
            schema_session.query(Category)
            .filter(Category.code == "MD")
            .one()
        )
        assert domain_category.is_enumerated is True

        hierarchy_nodes = schema_session.query(SubCategoryItem).count()
        assert hierarchy_nodes == 3
