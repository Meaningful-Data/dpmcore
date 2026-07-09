"""Tests for the neutral intermediate taxonomy model."""

import pytest

from dpmcore.loaders.xbrl.model import (
    DIRECTION_X,
    DIRECTION_Y,
    DIRECTION_Z,
    TaxonomyModel,
    XAxis,
    XbrlImportError,
    XCell,
    XDimension,
    XDomain,
    XHierarchy,
    XHierarchyNode,
    XMember,
    XMetric,
    XModule,
    XTable,
    merge_models,
)


def _member(qname="d:m1", **kwargs):
    return XMember(qname=qname, name=f"Member {qname}", **kwargs)


def _dimension(qname="d:dim1", **kwargs):
    kwargs.setdefault("code", None)
    kwargs.setdefault("name", f"Dimension {qname}")
    return XDimension(qname=qname, **kwargs)


def _domain(qname="d:dom1", **kwargs):
    kwargs.setdefault("code", None)
    kwargs.setdefault("name", f"Domain {qname}")
    return XDomain(qname=qname, **kwargs)


def _metric(qname="p:met1", **kwargs):
    kwargs.setdefault("code", None)
    kwargs.setdefault("name", f"Metric {qname}")
    kwargs.setdefault("xbrl_type", "xbrli:monetaryItemType")
    kwargs.setdefault("period_type", "instant")
    return XMetric(qname=qname, **kwargs)


def _table(code="T1", **kwargs):
    kwargs.setdefault("name", f"Table {code}")
    return XTable(code=code, **kwargs)


def _module(code="M1", **kwargs):
    kwargs.setdefault("name", f"Module {code}")
    kwargs.setdefault("entry_point", f"{code.lower()}.xsd")
    return XModule(code=code, **kwargs)


def _model(**kwargs):
    kwargs.setdefault("framework_code", "B2P2")
    kwargs.setdefault("framework_name", "Basel II Pillar 2")
    return TaxonomyModel(**kwargs)


class TestAxis:
    def test_axis_without_open_dimensions_is_closed(self):
        axis = XAxis(direction=DIRECTION_X)
        assert axis.is_open is False

    def test_axis_with_open_dimensions_is_open(self):
        axis = XAxis(
            direction=DIRECTION_Z,
            open_dimension_qnames=("d:CurrencyDim",),
        )
        assert axis.is_open is True


class TestTable:
    def test_axis_lookup_by_direction(self):
        x_axis = XAxis(direction=DIRECTION_X)
        y_axis = XAxis(direction=DIRECTION_Y)
        table = _table(axes=(x_axis, y_axis))
        assert table.axis(DIRECTION_X) is x_axis
        assert table.axis(DIRECTION_Y) is y_axis

    def test_axis_lookup_missing_direction_returns_none(self):
        table = _table(axes=(XAxis(direction=DIRECTION_X),))
        assert table.axis(DIRECTION_Z) is None


class TestMergeModels:
    def test_merge_of_no_models_is_an_error(self):
        with pytest.raises(XbrlImportError, match="No taxonomy content"):
            merge_models([])

    def test_merge_keeps_framework_identity_of_first_model(self):
        merged = merge_models(
            [
                _model(framework_code="FIB", framework_name="FIB name"),
                _model(framework_code="SEG", framework_name="SEG name"),
            ]
        )
        assert merged.framework_code == "FIB"
        assert merged.framework_name == "FIB name"

    def test_merge_dedupes_dictionary_content_by_qname(self):
        dim = _dimension("d:dim1")
        dim_dup = _dimension("d:dim1", name="Other name")
        dom = _domain("d:dom1")
        met = _metric("p:met1")
        merged = merge_models(
            [
                _model(
                    dimensions=(dim,),
                    domains=(dom,),
                    metrics=(met,),
                ),
                _model(
                    dimensions=(dim_dup, _dimension("d:dim2")),
                    domains=(dom,),
                    metrics=(met,),
                ),
            ]
        )
        assert [d.qname for d in merged.dimensions] == ["d:dim1", "d:dim2"]
        # First occurrence wins.
        assert merged.dimensions[0].name == "Dimension d:dim1"
        assert len(merged.domains) == 1
        assert len(merged.metrics) == 1

    def test_merge_dedupes_hierarchies_by_role_and_domain(self):
        h1 = XHierarchy(
            code=None,
            name="H1",
            domain_qname="d:dom1",
            role_uri="http://x/role/1",
            nodes=(XHierarchyNode("d:m1", None, 1),),
        )
        h1_dup = XHierarchy(
            code=None,
            name="H1 duplicate",
            domain_qname="d:dom1",
            role_uri="http://x/role/1",
        )
        h2 = XHierarchy(
            code=None,
            name="H2",
            domain_qname="d:dom2",
            role_uri="http://x/role/1",
        )
        merged = merge_models(
            [_model(hierarchies=(h1,)), _model(hierarchies=(h1_dup, h2))]
        )
        assert [h.name for h in merged.hierarchies] == ["H1", "H2"]

    def test_merge_dedupes_tables_and_modules_by_code(self):
        merged = merge_models(
            [
                _model(tables=(_table("T1"),), modules=(_module("M1"),)),
                _model(
                    tables=(_table("T1"), _table("T2")),
                    modules=(_module("M1"), _module("M2")),
                ),
            ]
        )
        assert [t.code for t in merged.tables] == ["T1", "T2"]
        assert [m.code for m in merged.modules] == ["M1", "M2"]

    def test_merge_concatenates_and_dedupes_warnings(self):
        merged = merge_models(
            [
                _model(warnings=("w1", "w2")),
                _model(warnings=("w2", "w3")),
            ]
        )
        assert merged.warnings == ("w1", "w2", "w3")


class TestCellDefaults:
    def test_cell_defaults(self):
        cell = XCell(
            row_node_id="r1",
            column_node_id="c1",
            metric_qname="p:met1",
        )
        assert cell.sheet_node_id is None
        assert cell.dim_members == ()

    def test_member_defaults(self):
        member = _member()
        assert member.code is None
        assert member.is_default is False
        assert member.labels == ()


class TestMergeUnions:
    def test_domain_members_are_unioned_across_models(self):
        partial = _domain("d:dom1", members=(_member("d:m1"),))
        fuller = _domain(
            "d:dom1",
            members=(_member("d:m1"), _member("d:m2")),
        )
        merged = merge_models(
            [_model(domains=(partial,)), _model(domains=(fuller,))]
        )
        assert [m.qname for m in merged.domains[0].members] == [
            "d:m1",
            "d:m2",
        ]

    def test_closed_dimension_variant_wins_over_open(self):
        open_variant = _dimension("d:dim1", is_open=True)
        closed_variant = _dimension(
            "d:dim1", domain_qname="d:dom1", is_open=False
        )
        merged = merge_models(
            [
                _model(dimensions=(open_variant,)),
                _model(dimensions=(closed_variant,)),
            ]
        )
        assert merged.dimensions[0].is_open is False
        assert merged.dimensions[0].domain_qname == "d:dom1"

    def test_hierarchy_nodes_are_unioned_and_renumbered(self):
        base = XHierarchy(
            code=None,
            name="H",
            domain_qname="d:dom1",
            role_uri="closure:d:dom1",
            nodes=(XHierarchyNode("d:m1", None, 1),),
        )
        extended = XHierarchy(
            code=None,
            name="H",
            domain_qname="d:dom1",
            role_uri="closure:d:dom1",
            nodes=(
                XHierarchyNode("d:m1", None, 1),
                XHierarchyNode("d:m2", "d:m1", 2),
            ),
        )
        merged = merge_models(
            [_model(hierarchies=(base,)), _model(hierarchies=(extended,))]
        )
        hierarchy = merged.hierarchies[0]
        assert [n.member_qname for n in hierarchy.nodes] == [
            "d:m1",
            "d:m2",
        ]
        assert [n.order for n in hierarchy.nodes] == [1, 2]
