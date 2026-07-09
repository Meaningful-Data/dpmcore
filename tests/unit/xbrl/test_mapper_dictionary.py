"""Tests for the dictionary half of the taxonomy mapper."""

import re
from datetime import date

import pytest

from dpmcore.loaders.xbrl.mapper import (
    IdAllocator,
    MappingOutcome,
    TaxonomyMapper,
    stable_uuid,
)
from dpmcore.loaders.xbrl.model import (
    TaxonomyModel,
    XbrlImportError,
    XDimension,
    XDomain,
    XHierarchy,
    XHierarchyNode,
    XLabel,
    XMember,
    XMetric,
)
from dpmcore.orm.glossary import (
    Category,
    Item,
    ItemCategory,
    Property,
    PropertyCategory,
    SubCategory,
    SubCategoryItem,
    SubCategoryVersion,
)
from dpmcore.orm.infrastructure import (
    Organisation,
    Release,
    Translation,
)


def make_mapper(session, **kwargs):
    kwargs.setdefault("owner_name", "National Bank of Belgium")
    kwargs.setdefault("owner_acronym", "NBB")
    kwargs.setdefault("release_code", "2008-01-01")
    kwargs.setdefault("release_date", date(2008, 1, 1))
    kwargs.setdefault("fresh", True)
    return TaxonomyMapper(session, **kwargs)


def simple_model(**kwargs):
    kwargs.setdefault("framework_code", "B2P2")
    kwargs.setdefault("framework_name", "Basel II Pillar 2")
    return TaxonomyModel(**kwargs)


DOMAIN = XDomain(
    qname="d-InvestGr:InvestGradeDomain",
    code=None,
    name="Investment grade domain",
    members=(
        XMember(
            qname="d-InvestGr:InvestmentGrade",
            name="Investment grade",
            labels=(
                XLabel("en", "Investment grade"),
                XLabel("fr", "Qualité investissement"),
            ),
        ),
        XMember(
            qname="d-InvestGr:NonInvestmentGrade",
            name="Non investment grade",
            is_default=True,
        ),
    ),
)

DIMENSION = XDimension(
    qname="d-InvestGr:ByInvestGradeDimension",
    code=None,
    name="By investment grade",
    domain_qname="d-InvestGr:InvestGradeDomain",
)

METRIC = XMetric(
    qname="p-LiqStock:Cash",
    code=None,
    name="Cash",
    xbrl_type="xbrli:monetaryItemType",
    period_type="instant",
)

HIERARCHY = XHierarchy(
    code=None,
    name="Investment grade tree",
    domain_qname="d-InvestGr:InvestGradeDomain",
    role_uri="http://www.xbrl.be/role/InvestGr",
    nodes=(
        XHierarchyNode("d-InvestGr:InvestmentGrade", None, 1),
        XHierarchyNode(
            "d-InvestGr:NonInvestmentGrade",
            "d-InvestGr:InvestmentGrade",
            2,
        ),
    ),
)


class TestStableUuid:
    def test_format_is_access_style(self):
        guid = stable_uuid("Item", "B2P2", "d:qname")
        assert re.fullmatch(r"\{[0-9A-F-]{36}\}", guid)
        assert len(guid) == 38

    def test_is_deterministic(self):
        assert stable_uuid("a", 1, None) == stable_uuid("a", 1, None)
        assert stable_uuid("a", 1) != stable_uuid("a", 2)


class TestPrepare:
    def test_creates_owner_release_and_special_categories(
        self, schema_session
    ):
        mapper = make_mapper(schema_session)
        mapper.prepare()

        org = schema_session.query(Organisation).one()
        assert org.acronym == "NBB"
        assert org.id_prefix == 1

        release = schema_session.query(Release).one()
        assert release.code == "2008-01-01"
        assert release.is_current is True
        assert release.status == "released"

        codes = {
            c.code: c.category_id
            for c in schema_session.query(Category).all()
        }
        assert codes == {"_PR": 1002, "_NA": 1003}

    def test_prepare_is_idempotent(self, schema_session):
        make_mapper(schema_session).prepare()
        mapper = make_mapper(schema_session)
        mapper.prepare()
        assert schema_session.query(Organisation).count() == 1
        assert schema_session.query(Release).count() == 1
        assert schema_session.query(Category).count() == 2
        assert mapper.outcome.reused["Organisation"] == 1
        assert mapper.outcome.reused["Release"] == 1

    def test_existing_mode_release_id_is_owner_prefixed(
        self, schema_session
    ):
        # Simulate a populated database with a foreign organisation.
        schema_session.add(
            Organisation(
                org_id=1012,
                name="EBA",
                acronym="EBA",
                id_prefix=101,
            )
        )
        schema_session.add(Release(release_id=1, code="4.2.1"))
        schema_session.flush()

        mapper = make_mapper(schema_session, fresh=False)
        mapper.prepare()
        release = mapper.release
        assert release.release_id == 102 * 10**7 + 1
        assert release.is_current is False

    def test_accessors_raise_before_prepare(self, schema_session):
        mapper = make_mapper(schema_session)
        with pytest.raises(XbrlImportError, match="not prepared"):
            _ = mapper.release
        with pytest.raises(XbrlImportError, match="not prepared"):
            _ = mapper.owner


class TestDomainsAndMembers:
    def test_domain_becomes_enumerated_category(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper.map_dictionary(simple_model(domains=(DOMAIN,)))

        category = (
            schema_session.query(Category)
            .filter(Category.code == "IG")
            .one()
        )
        assert category.is_enumerated is True
        assert category.name == "Investment grade domain"
        assert category.created_release_id == mapper.release.release_id

    def test_members_get_items_with_qname_signatures(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper.map_dictionary(simple_model(domains=(DOMAIN,)))

        links = (
            schema_session.query(ItemCategory)
            .join(Category)
            .filter(Category.code == "IG")
            .order_by(ItemCategory.code)
            .all()
        )
        assert [link.code for link in links] == ["x1", "x2"]
        assert links[0].signature == "d-InvestGr:InvestmentGrade"
        assert links[1].is_default_item is True

    def test_member_labels_become_translations(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper.map_dictionary(simple_model(domains=(DOMAIN,)))

        translation = schema_session.query(Translation).one()
        assert translation.translation == "Qualité investissement"
        assert translation.language_code == 2
        assert mapper.outcome.created["Translation"] == 1

    def test_typed_domain_creates_no_category(self, schema_session):
        typed = XDomain(
            qname="typ:qDate",
            code=None,
            name="Date typed domain",
            is_typed=True,
            typed_data_type="xs:date",
        )
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper.map_dictionary(simple_model(domains=(typed,)))
        assert schema_session.query(Category).count() == 2  # _PR/_NA only

    def test_reimport_reuses_members(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper.map_dictionary(simple_model(domains=(DOMAIN,)))
        schema_session.commit()

        again = make_mapper(schema_session)
        again.prepare()
        again.map_dictionary(simple_model(domains=(DOMAIN,)))
        assert schema_session.query(Item).count() == 2
        assert again.outcome.created.get("Item") is None
        assert again.outcome.reused["Item"] == 2
        assert again.outcome.reused["Category"] >= 1


class TestDimensionsAndMetrics:
    def _map(self, session, **model_kwargs):
        mapper = make_mapper(session)
        mapper.prepare()
        mapper.map_dictionary(simple_model(**model_kwargs))
        return mapper

    def test_dimension_creates_property_item_pair(self, schema_session):
        self._map(
            schema_session,
            domains=(DOMAIN,),
            dimensions=(DIMENSION,),
        )
        prop = (
            schema_session.query(Property)
            .join(Item, Item.item_id == Property.property_id)
            .filter(Item.is_property.is_(True))
            .one()
        )
        assert prop.is_metric is False
        assert prop.datatype.code == "e"

        link = (
            schema_session.query(PropertyCategory)
            .filter(PropertyCategory.property_id == prop.property_id)
            .one()
        )
        category = schema_session.get(Category, link.category_id)
        assert category.code == "IG"

    def test_dimension_pr_item_code_is_global_sequence(
        self, schema_session
    ):
        self._map(
            schema_session,
            domains=(DOMAIN,),
            dimensions=(DIMENSION,),
            metrics=(METRIC,),
        )
        pr_links = (
            schema_session.query(ItemCategory)
            .join(Category)
            .filter(Category.code == "_PR")
            .order_by(ItemCategory.code)
            .all()
        )
        assert [link.code for link in pr_links] == ["ei1", "mi2"]
        assert [link.signature for link in pr_links] == ["ei1", "mi2"]

    def test_metric_property_flags(self, schema_session):
        self._map(schema_session, metrics=(METRIC,))
        prop = schema_session.query(Property).one()
        assert prop.is_metric is True
        assert prop.period_type == "stock"
        assert prop.datatype.code == "m"

    def test_open_dimension_links_to_na(self, schema_session):
        open_dim = XDimension(
            qname="d-cu:CurrencyDimension",
            code=None,
            name="Currency",
            domain_qname="d-cu:CurrencyCodeDomain",
            is_open=True,
        )
        self._map(schema_session, dimensions=(open_dim,))
        link = schema_session.query(PropertyCategory).one()
        category = schema_session.get(Category, link.category_id)
        assert category.code == "_NA"

    def test_typed_dimension_uses_typed_domain_datatype(
        self, schema_session
    ):
        typed_domain = XDomain(
            qname="typ:qInt",
            code=None,
            name="Integer typed domain",
            is_typed=True,
            typed_data_type="xs:integer",
        )
        typed_dim = XDimension(
            qname="dim:HDS",
            code="HDS",
            name="Some typed dim",
            domain_qname="typ:qInt",
            is_typed=True,
        )
        self._map(
            schema_session,
            domains=(typed_domain,),
            dimensions=(typed_dim,),
        )
        prop = schema_session.query(Property).one()
        assert prop.datatype.code == "i"

    def test_dimension_with_unknown_domain_warns_and_links_na(
        self, schema_session
    ):
        dangling = XDimension(
            qname="d:Dangling",
            code=None,
            name="Dangling",
            domain_qname="d:MissingDomain",
        )
        mapper = self._map(schema_session, dimensions=(dangling,))
        assert any(
            "unknown domain" in w for w in mapper.outcome.warnings
        )
        link = schema_session.query(PropertyCategory).one()
        assert schema_session.get(Category, link.category_id).code == "_NA"

    def test_unknown_xbrl_type_defaults_to_string_with_warning(
        self, schema_session
    ):
        odd = XMetric(
            qname="p:Odd",
            code=None,
            name="Odd",
            xbrl_type="xbrli:fractionItemType",
            period_type="madeup",
        )
        mapper = self._map(schema_session, metrics=(odd,))
        prop = schema_session.query(Property).one()
        assert prop.datatype.code == "s"
        assert prop.period_type == "stock"
        assert any("Unknown XBRL type" in w for w in mapper.outcome.warnings)
        assert any(
            "Unknown period type" in w for w in mapper.outcome.warnings
        )

    def test_reimport_reuses_properties(self, schema_session):
        self._map(schema_session, metrics=(METRIC,))
        schema_session.commit()
        mapper = self._map(schema_session, metrics=(METRIC,))
        assert schema_session.query(Property).count() == 1
        assert mapper.outcome.reused["Property"] == 1

    def test_duplicate_qname_within_run_is_mapped_once(
        self, schema_session
    ):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        model = simple_model(metrics=(METRIC,))
        mapper.map_dictionary(model)
        mapper.map_dictionary(model)
        assert schema_session.query(Property).count() == 1


class TestHierarchies:
    def test_hierarchy_creates_subcategory_tree(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper.map_dictionary(
            simple_model(domains=(DOMAIN,), hierarchies=(HIERARCHY,))
        )

        subcategory = schema_session.query(SubCategory).one()
        assert subcategory.code == "IG1"
        assert subcategory.name == "Investment grade tree"

        version = schema_session.query(SubCategoryVersion).one()
        assert version.start_release_id == mapper.release.release_id

        nodes = (
            schema_session.query(SubCategoryItem)
            .order_by(SubCategoryItem.order)
            .all()
        )
        assert len(nodes) == 2
        assert nodes[0].parent_item_id is None
        assert nodes[1].parent_item_id == nodes[0].item_id
        assert mapper.outcome.created["SubCategoryItem"] == 2

    def test_hierarchy_with_unknown_domain_is_skipped(
        self, schema_session
    ):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper.map_dictionary(simple_model(hierarchies=(HIERARCHY,)))
        assert schema_session.query(SubCategory).count() == 0
        assert any(
            "unknown domain" in w for w in mapper.outcome.warnings
        )

    def test_hierarchy_node_with_unknown_member_is_skipped(
        self, schema_session
    ):
        broken = XHierarchy(
            code=None,
            name="Broken",
            domain_qname="d-InvestGr:InvestGradeDomain",
            role_uri="http://www.xbrl.be/role/Broken",
            nodes=(XHierarchyNode("d:NotThere", None, 1),),
        )
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper.map_dictionary(
            simple_model(domains=(DOMAIN,), hierarchies=(broken,))
        )
        assert schema_session.query(SubCategoryItem).count() == 0
        assert any(
            "unknown member" in w for w in mapper.outcome.warnings
        )

    def test_reimport_reuses_hierarchy(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        model = simple_model(domains=(DOMAIN,), hierarchies=(HIERARCHY,))
        mapper.map_dictionary(model)
        schema_session.commit()

        again = make_mapper(schema_session)
        again.prepare()
        again.map_dictionary(model)
        assert schema_session.query(SubCategory).count() == 1
        assert again.outcome.reused["SubCategory"] == 1


class TestCategoryCodeSynthesis:
    def test_camel_case_capitals_form_the_code(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        code = mapper._synth_category_code("d:InvestGradeDomain")
        assert code == "IG"

    def test_short_local_names_fall_back_to_upper_prefix(
        self, schema_session
    ):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        assert mapper._synth_category_code("d:cu") == "CU"

    def test_collisions_get_numeric_suffix(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        first = mapper._synth_category_code("d:InvestGradeDomain")
        second = mapper._synth_category_code("d:InvGrDomain")
        assert first == "IG"
        assert second == "IG2"

    def test_collision_with_persisted_category(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper.map_dictionary(simple_model(domains=(DOMAIN,)))
        schema_session.commit()

        other = make_mapper(schema_session)
        other.prepare()
        other._framework_code = "OTHER"
        assert other._synth_category_code("x:IngestGroupDomain") == "IG2"


class TestIdAllocator:
    def test_fresh_mode_starts_at_one(self, schema_session):
        allocator = IdAllocator(schema_session, fresh=True)
        assert allocator.next_id(Item, "item_id") == 1
        assert allocator.next_id(Item, "item_id") == 2

    def test_existing_mode_uses_owner_prefix_for_items(
        self, schema_session
    ):
        schema_session.add(Item(item_id=500, name="existing"))
        schema_session.flush()
        allocator = IdAllocator(schema_session, fresh=False)
        allocator.set_owner(2)
        assert allocator.next_id(Item, "item_id") == 2_000_001

    def test_existing_mode_continues_inside_prefix_range(
        self, schema_session
    ):
        schema_session.add(Item(item_id=2_000_007, name="mine"))
        schema_session.flush()
        allocator = IdAllocator(schema_session, fresh=False)
        allocator.set_owner(2)
        assert allocator.next_id(Item, "item_id") == 2_000_008

    def test_existing_mode_small_tables_use_max_plus_one(
        self, schema_session
    ):
        schema_session.add(Category(category_id=41, code="X"))
        schema_session.flush()
        allocator = IdAllocator(schema_session, fresh=False)
        allocator.set_owner(2)
        assert allocator.next_id(Category, "category_id") == 42


class TestMappingOutcome:
    def test_bump_counts_created_and_reused_separately(self):
        outcome = MappingOutcome()
        outcome.bump("Item")
        outcome.bump("Item")
        outcome.bump("Item", reused=True)
        assert outcome.created == {"Item": 2}
        assert outcome.reused == {"Item": 1}


class TestBranchDetails:
    def test_pick_name_falls_back_to_any_standard_label(self):
        labels = (XLabel("fr", "Français"),)
        assert TaxonomyMapper.pick_name(labels, "fallback") == "Français"

    def test_pick_name_falls_back_to_default_when_no_standard(self):
        labels = (XLabel("en", "code label", role="code"),)
        assert TaxonomyMapper.pick_name(labels, "fallback") == "fallback"

    def test_concept_helper_is_idempotent(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        from dpmcore.orm.infrastructure import Concept

        guid = stable_uuid("Item", "B2P2", "x:one")
        assert mapper._concept("Item", guid) == guid
        assert mapper._concept("Item", guid) == guid
        schema_session.flush()
        assert (
            schema_session.query(Concept)
            .filter(Concept.concept_guid == guid)
            .count()
            == 1
        )

    def test_special_category_reuses_existing_canonical_concept(
        self, schema_session
    ):
        from dpmcore.loaders.xbrl.mapper import _PR_CATEGORY_GUID
        from dpmcore.orm.infrastructure import Concept

        schema_session.add(
            Concept(concept_guid=_PR_CATEGORY_GUID, class_id=None)
        )
        schema_session.flush()
        mapper = make_mapper(schema_session)
        mapper.prepare()
        assert (
            schema_session.query(Concept)
            .filter(Concept.concept_guid == _PR_CATEGORY_GUID)
            .count()
            == 1
        )

    def test_translate_without_seeded_attribute_is_a_noop(
        self, schema_session
    ):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper._translate(
            "{00000000-0000-0000-000000000000}",
            "Context",
            "Name",
            (XLabel("fr", "quelque chose"),),
        )
        assert schema_session.query(Translation).count() == 0

    def test_translate_unsupported_language_warns(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper._translate(
            "{00000000-0000-0000-000000000000}",
            "Item",
            "Name",
            (XLabel("de", "Etwas"),),
        )
        assert schema_session.query(Translation).count() == 0
        assert any(
            "unsupported language" in w for w in mapper.outcome.warnings
        )

    def test_translate_is_idempotent(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        labels = (XLabel("fr", "Trésorerie"),)
        guid = "{11111111-1111-1111-111111111111}"
        mapper._translate(guid, "Item", "Name", labels)
        schema_session.flush()
        mapper._translate(guid, "Item", "Name", labels)
        assert schema_session.query(Translation).count() == 1

    def test_data_type_code_for_missing_type_is_string(
        self, schema_session
    ):
        mapper = make_mapper(schema_session)
        assert mapper._data_type_code(None) == "s"
        assert mapper.outcome.warnings == []

    def test_pr_sequence_continues_from_existing_codes(
        self, schema_session
    ):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        schema_session.add(Item(item_id=900, name="prior"))
        schema_session.add(
            ItemCategory(
                item_id=900,
                start_release_id=mapper.release.release_id,
                category_id=1002,
                code="mi7",
                signature="mi7",
            )
        )
        schema_session.flush()
        assert mapper._next_pr_code("e") == "ei8"

    def test_duplicate_dimension_within_run_is_mapped_once(
        self, schema_session
    ):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        model = simple_model(domains=(DOMAIN,), dimensions=(DIMENSION,))
        mapper.map_dictionary(model)
        mapper.map_dictionary(model)
        assert schema_session.query(Property).count() == 1

    def test_reimport_reuses_dimension_property(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        model = simple_model(domains=(DOMAIN,), dimensions=(DIMENSION,))
        mapper.map_dictionary(model)
        schema_session.commit()

        again = make_mapper(schema_session)
        again.prepare()
        again.map_dictionary(model)
        assert schema_session.query(Property).count() == 1
        assert again.outcome.reused["Property"] == 1

    def test_typed_dimension_without_domain_defaults_to_string(
        self, schema_session
    ):
        typed_dim = XDimension(
            qname="dim:TDN",
            code="TDN",
            name="Typed, no domain",
            is_typed=True,
        )
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper.map_dictionary(simple_model(dimensions=(typed_dim,)))
        prop = schema_session.query(Property).one()
        assert prop.datatype.code == "s"

    def test_create_property_without_category_link(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper._framework_code = "B2P2"
        mapper._create_property(
            qname="p:NoCat",
            name="No category",
            labels=(),
            is_metric=True,
            data_type_code="m",
            period_type="stock",
            category=None,
        )
        assert schema_session.query(PropertyCategory).count() == 0

    def test_pr_sequence_ignores_non_property_codes(self, schema_session):
        mapper = make_mapper(schema_session)
        mapper.prepare()
        schema_session.add(Item(item_id=901, name="odd"))
        schema_session.add(
            ItemCategory(
                item_id=901,
                start_release_id=mapper.release.release_id,
                category_id=1002,
                code="odd",
                signature="odd",
            )
        )
        schema_session.flush()
        assert mapper._next_pr_code("m") == "mi1"

    def test_duplicate_hierarchy_placement_is_skipped(
        self, schema_session
    ):
        duplicated = XHierarchy(
            code=None,
            name="Duplicated",
            domain_qname="d-InvestGr:InvestGradeDomain",
            role_uri="http://www.xbrl.be/role/Dup",
            nodes=(
                XHierarchyNode("d-InvestGr:InvestmentGrade", None, 1),
                XHierarchyNode(
                    "d-InvestGr:InvestmentGrade",
                    "d-InvestGr:NonInvestmentGrade",
                    2,
                ),
            ),
        )
        mapper = make_mapper(schema_session)
        mapper.prepare()
        mapper.map_dictionary(
            simple_model(domains=(DOMAIN,), hierarchies=(duplicated,))
        )
        schema_session.flush()
        assert schema_session.query(SubCategoryItem).count() == 1
        assert any(
            "more than once" in w for w in mapper.outcome.warnings
        )
