"""Tests for the PWD-2013 table linkbase parser."""

from pathlib import Path

import pytest

from dpmcore.loaders.xbrl.model import XbrlImportError
from dpmcore.loaders.xbrl.rend_parser import (
    parse_label_linkbase,
    parse_rend_file,
)

FIXTURES = (
    Path(__file__).parent.parent.parent / "fixtures" / "xbrl"
)
MINI_TAB = (
    FIXTURES / "mini_dpm1" / "fws" / "mini" / "2015-01-01" / "tab"
    / "t_1.00"
)


def canonicalize(namespace, local):
    prefix = namespace.rstrip("/").rsplit("/", 1)[-1]
    return f"c_{prefix}:{local}"


class TestParseRendFile:
    def test_table_identity(self):
        rend = parse_rend_file(MINI_TAB / "t_1.00-rend.xml", canonicalize)
        assert rend.table_id == "be_tT_1.00"
        assert rend.code == "T_1.00"

    def test_axes_and_nodes(self):
        rend = parse_rend_file(MINI_TAB / "t_1.00-rend.xml", canonicalize)
        directions = [axis.direction for axis in rend.axes]
        assert directions == ["X", "Y", "Z"]

        x_axis = rend.axes[0]
        assert [n.node_id for n in x_axis.nodes] == [
            "be_a1.root",
            "be_c1",
            "be_c2",
        ]
        assert x_axis.nodes[0].is_abstract is True
        assert x_axis.nodes[1].parent_id == "be_a1.root"
        assert x_axis.nodes[1].dim_members == (
            ("c_dim:EXD", "c_MD:x1"),
        )

    def test_rule_node_concept_aspect(self):
        rend = parse_rend_file(MINI_TAB / "t_1.00-rend.xml", canonicalize)
        y_axis = rend.axes[1]
        metrics = [n.metric_qname for n in y_axis.nodes]
        assert metrics == [None, "c_met:mi1", "c_met:ii2"]

    def test_aspect_node_becomes_open_dimension(self):
        rend = parse_rend_file(MINI_TAB / "t_1.00-rend.xml", canonicalize)
        z_axis = rend.axes[2]
        assert z_axis.nodes == ()
        assert z_axis.open_dimension_qnames == ("c_dim:TYD",)

    def test_file_without_table_raises(self, tmp_path):
        bogus = tmp_path / "empty-rend.xml"
        bogus.write_text(
            '<?xml version="1.0"?>\n'
            '<link:linkbase '
            'xmlns:link="http://www.xbrl.org/2003/linkbase"/>\n',
            encoding="utf-8",
        )
        with pytest.raises(XbrlImportError, match="no table:table"):
            parse_rend_file(bogus, canonicalize)


class TestParseLabelLinkbase:
    def test_generic_labels_with_codes(self):
        labels = parse_label_linkbase(MINI_TAB / "t_1.00-lab-codes.xml")
        key = ("t_1.00-rend.xml", "be_c1")
        assert [label.text for label in labels[key]] == ["010"]
        assert labels[key][0].role == "code"

    def test_generic_standard_labels(self):
        labels = parse_label_linkbase(MINI_TAB / "t_1.00-lab-en.xml")
        key = ("t_1.00-rend.xml", "be_tT_1.00")
        assert labels[key][0].text == "T_1.00 Mini table"
        assert labels[key][0].role == "standard"
        assert labels[key][0].lang == "en"

    def test_classic_2003_label_linkbase(self):
        met_lab = (
            FIXTURES / "mini_dpm1" / "dict" / "met" / "met-lab-en.xml"
        )
        labels = parse_label_linkbase(met_lab)
        assert labels[("met.xsd", "be_mi1")][0].text == "Carrying amount"

    def test_unknown_roles_are_ignored(self, tmp_path):
        linkbase = tmp_path / "odd-lab.xml"
        linkbase.write_text(
            '<?xml version="1.0"?>\n'
            '<link:linkbase '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">\n'
            ' <link:labelLink xlink:type="extended">\n'
            '  <link:loc xlink:type="locator" xlink:href="x.xsd#a"'
            ' xlink:label="l"/>\n'
            '  <link:label xlink:type="resource" xlink:label="r"'
            ' xml:lang="en"'
            ' xlink:role="http://www.xbrl.org/2003/role/verboseLabel"'
            ">Verbose</link:label>\n"
            '  <link:labelArc xlink:type="arc" xlink:from="l"'
            ' xlink:to="r"/>\n'
            " </link:labelLink>\n"
            "</link:linkbase>\n",
            encoding="utf-8",
        )
        assert parse_label_linkbase(linkbase) == {}


class TestParserEdges:
    def test_code_from_table_id_without_marker(self, tmp_path):
        rend = tmp_path / "odd-rend.xml"
        rend.write_text(
            '<?xml version="1.0"?>\n'
            '<link:linkbase '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
            'xmlns:gen="http://xbrl.org/2008/generic" '
            'xmlns:table="http://xbrl.org/PWD/2013-05-17/table">\n'
            ' <gen:link xlink:type="extended">\n'
            '  <table:table xlink:type="resource" xlink:label="MYTABLE"'
            ' id="MYTABLE"/>\n'
            " </gen:link>\n"
            "</link:linkbase>\n",
            encoding="utf-8",
        )
        parsed = parse_rend_file(rend, canonicalize)
        assert parsed.code == "MYTABLE"
        assert parsed.axes == ()

    def test_unknown_prefix_in_qname_is_kept_verbatim(self, tmp_path):
        rend = tmp_path / "raw-rend.xml"
        rend.write_text(
            '<?xml version="1.0"?>\n'
            '<link:linkbase '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
            'xmlns:gen="http://xbrl.org/2008/generic" '
            'xmlns:formula="http://xbrl.org/2008/formula" '
            'xmlns:table="http://xbrl.org/PWD/2013-05-17/table">\n'
            ' <gen:link xlink:type="extended">\n'
            '  <table:table xlink:type="resource" xlink:label="be_tT"'
            ' id="be_tT"/>\n'
            '  <table:breakdown xlink:type="resource"'
            ' xlink:label="a1" id="a1"/>\n'
            '  <table:ruleNode xlink:type="resource" xlink:label="n1"'
            ' id="n1">\n'
            "   <formula:concept><formula:qname>undeclared:met1"
            "</formula:qname></formula:concept>\n"
            '   <formula:explicitDimension dimension="undeclared:DIM"/>\n'
            "  </table:ruleNode>\n"
            '  <table:tableBreakdownArc xlink:type="arc"'
            ' xlink:from="be_tT" xlink:to="a1" axis="y" order="1"/>\n'
            '  <table:breakdownTreeArc xlink:type="arc"'
            ' xlink:from="a1" xlink:to="n1" order="1"/>\n'
            ' </gen:link>\n'
            "</link:linkbase>\n",
            encoding="utf-8",
        )
        parsed = parse_rend_file(rend, canonicalize)
        node = parsed.axes[0].nodes[0]
        # Unknown prefix stays verbatim; dimension without member
        # contributes no aspect pair.
        assert node.metric_qname == "undeclared:met1"
        assert node.dim_members == ()

    def test_dangling_arcs_and_foreign_resources_are_ignored(
        self, tmp_path
    ):
        rend = tmp_path / "dangling-rend.xml"
        rend.write_text(
            '<?xml version="1.0"?>\n'
            '<link:linkbase '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
            'xmlns:gen="http://xbrl.org/2008/generic" '
            'xmlns:df="http://xbrl.org/2008/filter/dimension" '
            'xmlns:table="http://xbrl.org/PWD/2013-05-17/table">\n'
            ' <gen:link xlink:type="extended">\n'
            '  <table:table xlink:type="resource" xlink:label="be_tT"'
            ' id="be_tT"/>\n'
            '  <df:explicitDimension xlink:type="resource"'
            ' xlink:label="filter1" id="filter1"/>\n'
            '  <table:breakdown xlink:type="resource"'
            ' xlink:label="a1" id="a1"/>\n'
            '  <table:tableBreakdownArc xlink:type="arc"'
            ' xlink:from="be_tT" xlink:to="nosuch" axis="x"'
            ' order="1"/>\n'
            '  <table:breakdownTreeArc xlink:type="arc"'
            ' xlink:from="nosuch" xlink:to="a1" order="1"/>\n'
            '  <table:tableBreakdownArc xlink:type="arc"'
            ' xlink:from="be_tT" xlink:to="a1" axis="x" order="2"/>\n'
            '  <table:breakdownTreeArc xlink:type="arc"'
            ' xlink:from="a1" xlink:to="ghostnode" order="1"/>\n'
            " </gen:link>\n"
            "</link:linkbase>\n",
            encoding="utf-8",
        )
        parsed = parse_rend_file(rend, canonicalize)
        # The dangling tree target contributes nothing.
        assert parsed.axes == ()


class TestLabelLinkbaseEdges:
    def test_locators_without_labels_are_ignored(self, tmp_path):
        linkbase = tmp_path / "sparse-lab.xml"
        linkbase.write_text(
            '<?xml version="1.0"?>\n'
            '<link:linkbase '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">\n'
            ' <link:labelLink xlink:type="extended">\n'
            '  <link:loc xlink:type="locator" xlink:href="x.xsd#a"/>\n'
            '  <link:label xlink:type="resource" xlink:label="r"'
            ' xml:lang="en"'
            ' xlink:role="http://www.xbrl.org/2003/role/label"'
            ">Text</link:label>\n"
            '  <link:labelArc xlink:type="arc" xlink:from="ghost"'
            ' xlink:to="r"/>\n'
            " </link:labelLink>\n"
            "</link:linkbase>\n",
            encoding="utf-8",
        )
        assert parse_label_linkbase(linkbase) == {}


class TestScanEdges:
    def test_aspect_node_without_dimension_text_is_ignored(
        self, tmp_path
    ):
        rend = tmp_path / "aspectless-rend.xml"
        rend.write_text(
            '<?xml version="1.0"?>\n'
            '<link:linkbase '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
            'xmlns:gen="http://xbrl.org/2008/generic" '
            'xmlns:table="http://xbrl.org/PWD/2013-05-17/table">\n'
            ' <gen:link xlink:type="extended">\n'
            '  <table:table xlink:type="resource" xlink:label="be_tT"'
            ' id="be_tT"/>\n'
            '  <table:breakdown xlink:type="resource"'
            ' xlink:label="a1" id="a1"/>\n'
            '  <table:aspectNode xlink:type="resource"'
            ' xlink:label="a1.root" id="a1.root"/>\n'
            '  <table:tableBreakdownArc xlink:type="arc"'
            ' xlink:from="be_tT" xlink:to="a1" axis="z" order="1"/>\n'
            '  <table:breakdownTreeArc xlink:type="arc"'
            ' xlink:from="a1" xlink:to="a1.root" order="1"/>\n'
            " </gen:link>\n"
            "</link:linkbase>\n",
            encoding="utf-8",
        )
        parsed = parse_rend_file(rend, canonicalize)
        assert parsed.axes == ()

    def test_label_arc_to_missing_resource_is_ignored(self, tmp_path):
        linkbase = tmp_path / "ghost-lab.xml"
        linkbase.write_text(
            '<?xml version="1.0"?>\n'
            '<link:linkbase '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">\n'
            ' <link:labelLink xlink:type="extended">\n'
            '  <link:loc xlink:type="locator" xlink:href="x.xsd#a"'
            ' xlink:label="l"/>\n'
            '  <link:labelArc xlink:type="arc" xlink:from="l"'
            ' xlink:to="ghost"/>\n'
            " </link:labelLink>\n"
            "</link:linkbase>\n",
            encoding="utf-8",
        )
        assert parse_label_linkbase(linkbase) == {}

    def test_foreign_arcs_and_incomplete_arcs_are_ignored(
        self, tmp_path
    ):
        rend = tmp_path / "filterarc-rend.xml"
        rend.write_text(
            '<?xml version="1.0"?>\n'
            '<link:linkbase '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
            'xmlns:gen="http://xbrl.org/2008/generic" '
            'xmlns:table="http://xbrl.org/PWD/2013-05-17/table">\n'
            ' <gen:link xlink:type="extended">\n'
            '  <table:table xlink:type="resource" xlink:label="be_tT"'
            ' id="be_tT"/>\n'
            '  <table:aspectNodeFilterArc xlink:type="arc"'
            ' xlink:from="x" xlink:to="y" complement="false"/>\n'
            " </gen:link>\n"
            "</link:linkbase>\n",
            encoding="utf-8",
        )
        parsed = parse_rend_file(rend, canonicalize)
        assert parsed.table_id == "be_tT"


class TestArcWithoutEndpoints:
    def test_arc_missing_from_attribute_is_ignored(self, tmp_path):
        linkbase = tmp_path / "nofrom-lab.xml"
        linkbase.write_text(
            '<?xml version="1.0"?>\n'
            '<link:linkbase '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">\n'
            ' <link:labelLink xlink:type="extended">\n'
            '  <link:loc xlink:type="locator" xlink:href="x.xsd#a"'
            ' xlink:label="l"/>\n'
            '  <link:label xlink:type="resource" xlink:label="r"'
            ' xml:lang="en"'
            ' xlink:role="http://www.xbrl.org/2003/role/label"'
            ">Text</link:label>\n"
            '  <link:labelArc xlink:type="arc" xlink:to="r"/>\n'
            " </link:labelLink>\n"
            "</link:linkbase>\n",
            encoding="utf-8",
        )
        assert parse_label_linkbase(linkbase) == {}
