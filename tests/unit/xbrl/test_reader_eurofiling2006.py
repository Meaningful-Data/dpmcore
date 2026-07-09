"""Branch tests for the 2006-architecture reader on fake models."""

from pathlib import Path

from arelle import XbrlConst

from dpmcore.loaders.xbrl.reader_eurofiling2006 import read_entry_point

from .fake_arelle import (
    STANDARD_LINK_ROLE,
    FakeConcept,
    FakeModelXbrl,
    FakeRel,
    FakeRoleType,
)

ENTRY = Path("t-Mini-2008-01-01.xsd")


def build_minimal_model():
    """One metric, one closed dimension with two members."""
    mx = FakeModelXbrl()
    metric = mx.add_concept(FakeConcept("p-Mini:Cash"))
    head = mx.add_concept(
        FakeConcept("p-Mini:Root", abstract=True, type_qname=None)
    )
    hypercube = mx.add_concept(
        FakeConcept("t-Mini:Hc", hypercube=True, abstract=True)
    )
    dim = mx.add_concept(
        FakeConcept("d-Mini:ByDim", dimension=True, abstract=True)
    )
    domain = mx.add_concept(FakeConcept("d-Mini:Dom", abstract=True))
    member_a = mx.add_concept(FakeConcept("d-Mini:A", abstract=True))
    member_b = mx.add_concept(FakeConcept("d-Mini:B", abstract=True))

    mx.add_label(metric, "Cash")
    mx.add_label(domain, "Mini domain")
    mx.add_label(member_a, "Member A")
    mx.add_label(member_b, "Member B")

    mx.add_rel(XbrlConst.parentChild, FakeRel(head, metric))
    mx.add_rel(XbrlConst.all, FakeRel(metric, hypercube))
    mx.add_rel(XbrlConst.hypercubeDimension, FakeRel(hypercube, dim))
    mx.add_rel(XbrlConst.dimensionDomain, FakeRel(dim, domain))
    mx.add_rel(
        XbrlConst.domainMember, FakeRel(domain, member_a, order=1)
    )
    mx.add_rel(
        XbrlConst.domainMember, FakeRel(domain, member_b, order=2)
    )
    return mx


def read(mx, entry=ENTRY, **kwargs):
    kwargs.setdefault("framework_code", "MINI")
    kwargs.setdefault("framework_name", "Mini framework")
    return read_entry_point(mx, entry_path=entry, **kwargs)


class TestMinimalModel:
    def test_two_member_dimension_enumerates_two_columns(self):
        model = read(build_minimal_model())
        table = model.tables[0]
        assert table.code == "Mini"
        assert len(table.axis("X").nodes) == 2
        assert len(table.cells) == 2
        assert table.axis("Z") is None

    def test_hierarchy_read_from_member_closure(self):
        model = read(build_minimal_model())
        hierarchy = model.hierarchies[0]
        assert hierarchy.domain_qname == "d-Mini:Dom"
        assert [n.member_qname for n in hierarchy.nodes] == [
            "d-Mini:A",
            "d-Mini:B",
        ]


class TestEntryNameHandling:
    def test_unconventional_entry_name_warns(self):
        model = read(
            build_minimal_model(), entry=Path("mytable.xsd")
        )
        assert model.tables[0].code == "mytable"
        assert model.modules[0].from_date is None
        assert any("convention" in w for w in model.warnings)


class TestLabelFallbacks:
    def test_non_standard_label_roles_are_ignored(self):
        mx = build_minimal_model()
        metric = mx.qnameConcepts["p-Mini:Cash"]
        mx.add_label(
            metric,
            "Verbose cash",
            role="http://www.xbrl.org/2003/role/verboseLabel",
        )
        model = read(mx)
        cash = next(m for m in model.metrics if m.qname == "p-Mini:Cash")
        assert cash.name == "Cash"

    def test_first_label_used_when_no_english(self):
        mx = build_minimal_model()
        domain = mx.qnameConcepts["d-Mini:Dom"]
        # Replace labels: French only.
        mx._rels[XbrlConst.conceptLabel] = [
            rel
            for rel in mx._rels[XbrlConst.conceptLabel]
            if rel.fromModelObject is not domain
        ]
        mx.add_label(domain, "Domaine mini", lang="fr")
        model = read(mx)
        assert model.domains[0].name == "Domaine mini"

    def test_local_name_used_when_no_labels(self):
        mx = build_minimal_model()
        member = mx.qnameConcepts["d-Mini:A"]
        mx._rels[XbrlConst.conceptLabel] = [
            rel
            for rel in mx._rels[XbrlConst.conceptLabel]
            if rel.fromModelObject is not member
        ]
        model = read(mx)
        member_a = next(
            m for m in model.domains[0].members if m.qname == "d-Mini:A"
        )
        assert member_a.name == "A"


class TestDictionaryBranches:
    def test_typed_dimension_is_read_as_open(self):
        mx = build_minimal_model()
        mx.add_concept(
            FakeConcept(
                "d-Mini:TypedDim",
                dimension=True,
                typed=True,
                abstract=True,
            )
        )
        model = read(mx)
        typed = next(
            d for d in model.dimensions if d.qname == "d-Mini:TypedDim"
        )
        assert typed.is_typed is True
        assert typed.is_open is True

    def test_dimension_without_domain_is_open(self):
        mx = build_minimal_model()
        mx.add_concept(
            FakeConcept(
                "d-Mini:NoDomainDim", dimension=True, abstract=True
            )
        )
        model = read(mx)
        bare = next(
            d
            for d in model.dimensions
            if d.qname == "d-Mini:NoDomainDim"
        )
        assert bare.is_open is True
        assert bare.domain_qname is None

    def test_shared_domain_is_read_once(self):
        mx = build_minimal_model()
        other_dim = mx.add_concept(
            FakeConcept("d-Mini:OtherDim", dimension=True, abstract=True)
        )
        domain = mx.qnameConcepts["d-Mini:Dom"]
        mx.add_rel(
            XbrlConst.dimensionDomain, FakeRel(other_dim, domain)
        )
        model = read(mx)
        assert len(model.domains) == 1
        assert len(model.hierarchies) == 1

    def test_unusable_members_are_excluded(self):
        mx = build_minimal_model()
        domain = mx.qnameConcepts["d-Mini:Dom"]
        unusable = mx.add_concept(
            FakeConcept("d-Mini:NotUsable", abstract=True)
        )
        mx.add_rel(
            XbrlConst.domainMember,
            FakeRel(domain, unusable, order=3, usable=False),
        )
        model = read(mx)
        qnames = {m.qname for m in model.domains[0].members}
        assert "d-Mini:NotUsable" not in qnames

    def test_dimension_default_flag(self):
        mx = build_minimal_model()
        dim = mx.qnameConcepts["d-Mini:ByDim"]
        member_a = mx.qnameConcepts["d-Mini:A"]
        mx.add_rel(XbrlConst.dimensionDefault, FakeRel(dim, member_a))
        model = read(mx)
        member = next(
            m for m in model.domains[0].members if m.qname == "d-Mini:A"
        )
        assert member.is_default is True

    def test_nested_members_keep_parent_links(self):
        mx = build_minimal_model()
        member_a = mx.qnameConcepts["d-Mini:A"]
        child = mx.add_concept(FakeConcept("d-Mini:A1", abstract=True))
        mx.add_rel(XbrlConst.domainMember, FakeRel(member_a, child))
        model = read(mx)
        hierarchy = model.hierarchies[0]
        node = next(
            n for n in hierarchy.nodes if n.member_qname == "d-Mini:A1"
        )
        assert node.parent_qname == "d-Mini:A"

    def test_member_cycle_terminates(self):
        mx = build_minimal_model()
        member_a = mx.qnameConcepts["d-Mini:A"]
        member_b = mx.qnameConcepts["d-Mini:B"]
        mx.add_rel(XbrlConst.domainMember, FakeRel(member_a, member_b))
        mx.add_rel(XbrlConst.domainMember, FakeRel(member_b, member_a))
        model = read(mx)
        assert len(model.domains[0].members) == 2


class TestRowBranches:
    def test_standard_role_used_when_only_role(self):
        mx = build_minimal_model()
        head = mx.qnameConcepts["p-Mini:Root"]
        metric = mx.qnameConcepts["p-Mini:Cash"]
        mx._rels[XbrlConst.parentChild] = []
        mx.add_rel(
            XbrlConst.parentChild,
            FakeRel(head, metric, linkrole=STANDARD_LINK_ROLE),
        )
        model = read(mx)
        assert len(model.tables[0].axis("Y").nodes) == 2

    def test_table_name_falls_back_to_code(self):
        model = read(build_minimal_model())
        assert model.tables[0].name == "Mini"

    def test_table_name_from_presentation_role(self):
        mx = build_minimal_model()
        mx.roleTypes["http://example.com/role/table"] = [
            FakeRoleType(None),
            FakeRoleType("Mini table title"),
        ]
        model = read(mx)
        assert model.tables[0].name == "Mini table title"


class TestHypercubeBranches:
    def test_hypercube_inheritance_through_primary_tree(self):
        mx = build_minimal_model()
        head = mx.qnameConcepts["p-Mini:Root"]
        metric = mx.qnameConcepts["p-Mini:Cash"]
        hypercube = mx.qnameConcepts["t-Mini:Hc"]
        # Move the all-arc up to the abstract head; the metric
        # inherits it through the primary domain-member tree.
        mx._rels[XbrlConst.all] = []
        mx.add_rel(XbrlConst.all, FakeRel(head, hypercube))
        mx.add_rel(XbrlConst.domainMember, FakeRel(head, metric))
        model = read(mx)
        assert len(model.tables[0].cells) == 2

    def test_primary_tree_cycle_terminates(self):
        mx = build_minimal_model()
        head = mx.qnameConcepts["p-Mini:Root"]
        metric = mx.qnameConcepts["p-Mini:Cash"]
        mx.add_rel(XbrlConst.domainMember, FakeRel(head, metric))
        mx.add_rel(XbrlConst.domainMember, FakeRel(metric, head))
        model = read(mx)
        assert len(model.tables[0].cells) == 2

    def test_row_without_hypercube_gets_no_dimensional_cells(self):
        mx = build_minimal_model()
        extra = mx.add_concept(FakeConcept("p-Mini:Uncovered"))
        head = mx.qnameConcepts["p-Mini:Root"]
        mx.add_label(extra, "Uncovered")
        mx.add_rel(XbrlConst.parentChild, FakeRel(head, extra, order=2))
        model = read(mx)
        cells_by_row_metric = {
            cell.metric_qname for cell in model.tables[0].cells
        }
        assert "p-Mini:Uncovered" not in cells_by_row_metric

    def test_dimensionless_table_gets_single_value_column(self):
        mx = FakeModelXbrl()
        head = mx.add_concept(
            FakeConcept("p-Mini:Root", abstract=True, type_qname=None)
        )
        metric = mx.add_concept(FakeConcept("p-Mini:Cash"))
        hypercube = mx.add_concept(
            FakeConcept("t-Mini:Empty", hypercube=True, abstract=True)
        )
        mx.add_label(metric, "Cash")
        mx.add_rel(XbrlConst.parentChild, FakeRel(head, metric))
        mx.add_rel(XbrlConst.all, FakeRel(metric, hypercube))
        model = read(mx)
        table = model.tables[0]
        assert len(table.axis("X").nodes) == 1
        assert table.axis("X").nodes[0].label == "Value"
        assert len(table.cells) == 1

    def test_column_cap_demotes_large_dimensions(self):
        mx = build_minimal_model()
        model = read(mx, max_enumerated_columns=1)
        table = model.tables[0]
        assert len(table.axis("X").nodes) == 1
        assert table.axis("Z").open_dimension_qnames == (
            "d-Mini:ByDim",
        )
        assert any("too many members" in w for w in model.warnings)

    def test_missing_type_qname_defaults_empty(self):
        mx = build_minimal_model()
        metric = mx.qnameConcepts["p-Mini:Cash"]
        metric.typeQname = None
        metric.periodType = None
        model = read(mx)
        cash = next(m for m in model.metrics if m.qname == "p-Mini:Cash")
        assert cash.xbrl_type == ""
        assert cash.period_type == "instant"


class TestEmptyClosureAndSheets:
    def test_domain_with_no_usable_members_gets_no_hierarchy(self):
        mx = build_minimal_model()
        other_dim = mx.add_concept(
            FakeConcept("d-Mini:EmptyDim", dimension=True, abstract=True)
        )
        empty_domain = mx.add_concept(
            FakeConcept("d-Mini:EmptyDom", abstract=True)
        )
        unusable = mx.add_concept(
            FakeConcept("d-Mini:Hidden", abstract=True)
        )
        mx.add_rel(
            XbrlConst.dimensionDomain, FakeRel(other_dim, empty_domain)
        )
        mx.add_rel(
            XbrlConst.domainMember,
            FakeRel(empty_domain, unusable, usable=False),
        )
        model = read(mx)
        assert len(model.hierarchies) == 1  # only the Mini domain
        empty = next(
            d for d in model.dimensions if d.qname == "d-Mini:EmptyDim"
        )
        assert empty.is_open is True

    def test_open_dimension_on_hypercube_becomes_sheet_key(self):
        mx = build_minimal_model()
        hypercube = mx.qnameConcepts["t-Mini:Hc"]
        open_dim = mx.add_concept(
            FakeConcept("d-Mini:OpenDim", dimension=True, abstract=True)
        )
        mx.add_rel(
            XbrlConst.hypercubeDimension, FakeRel(hypercube, open_dim)
        )
        # Duplicate arc exercises the dedupe branch.
        mx.add_rel(
            XbrlConst.hypercubeDimension, FakeRel(hypercube, open_dim)
        )
        model = read(mx)
        table = model.tables[0]
        assert table.axis("Z").open_dimension_qnames == (
            "d-Mini:OpenDim",
        )
