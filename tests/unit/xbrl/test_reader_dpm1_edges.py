"""Edge-case tests for the dpm1 reader on mutated fixture copies."""

import shutil
from pathlib import Path

from dpmcore.loaders.xbrl.reader_dpm1 import (
    _date_from_path,
    canonical_prefix,
    read_taxonomy,
)

FIXTURES = (
    Path(__file__).parent.parent.parent / "fixtures" / "xbrl"
)


def mini_copy(tmp_path):
    target = tmp_path / "mini"
    shutil.copytree(FIXTURES / "mini_dpm1", target)
    return target


def read(root):
    return read_taxonomy(
        root, framework_code="MINI", framework_name="Mini"
    )


class TestCanonicalPrefixEdges:
    def test_dict_root_namespace(self):
        assert (
            canonical_prefix("http://www.nbb.be/xbrl/crr/dict/")
            == "be_dict"
        )

    def test_bare_host(self):
        assert canonical_prefix("http://www.nbb.be") == "be_www.nbb.be"


class TestDateFromPath:
    def test_no_date_in_path_returns_none(self):
        assert _date_from_path(Path("a/b/c.xsd")) is None


class TestSchemaScanEdges:
    def test_elements_without_id_are_skipped(self, tmp_path):
        root = mini_copy(tmp_path)
        met = root / "dict" / "met" / "met.xsd"
        met.write_text(
            met.read_text(encoding="utf-8").replace(
                'id="be_mi1"', ""
            ),
            encoding="utf-8",
        )
        model = read(root)
        assert {m.qname for m in model.metrics} == {"be_met:ii2"}

    def test_empty_met_schema_warns(self, tmp_path):
        root = mini_copy(tmp_path)
        met = root / "dict" / "met" / "met.xsd"
        met.write_text(
            '<?xml version="1.0"?>\n'
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
            'targetNamespace="http://www.example.be/xbrl/crr/dict/met"/>',
            encoding="utf-8",
        )
        model = read(root)
        assert model.metrics == ()
        assert any("No metrics found" in w for w in model.warnings)


class TestDictionaryEdges:
    def test_missing_mem_def_gives_empty_domain(self, tmp_path):
        root = mini_copy(tmp_path)
        (root / "dict" / "dom" / "md" / "mem-def.xml").unlink()
        model = read(root)
        domain = next(
            d for d in model.domains if d.qname == "be_exp:MD"
        )
        assert domain.members == ()
        explicit = next(
            d for d in model.dimensions if d.qname == "be_dim:EXD"
        )
        assert explicit.is_open is True

    def test_missing_dim_def_makes_dimensions_open(self, tmp_path):
        root = mini_copy(tmp_path)
        (root / "dict" / "dim" / "dim-def.xml").unlink()
        model = read(root)
        explicit = next(
            d for d in model.dimensions if d.qname == "be_dim:EXD"
        )
        assert explicit.is_open is True
        assert any(
            "no dimension-domain arc" in w for w in model.warnings
        )

    def test_hierarchy_with_unknown_domain_is_skipped(self, tmp_path):
        root = mini_copy(tmp_path)
        hier = root / "dict" / "dom" / "md" / "hier-def.xml"
        hier.write_text(
            hier.read_text(encoding="utf-8").replace(
                "../exp.xsd#be_MD", "../exp.xsd#be_UNKNOWN"
            ),
            encoding="utf-8",
        )
        model = read(root)
        assert model.hierarchies == ()
        assert any(
            "does not start from a known domain" in w
            for w in model.warnings
        )

    def test_hierarchy_without_arcs_is_ignored(self, tmp_path):
        root = mini_copy(tmp_path)
        hier = root / "dict" / "dom" / "md" / "hier-def.xml"
        hier.write_text(
            '<?xml version="1.0"?>\n'
            '<link:linkbase '
            'xmlns:link="http://www.xbrl.org/2003/linkbase"/>',
            encoding="utf-8",
        )
        model = read(root)
        assert model.hierarchies == ()

    def test_arc_with_dangling_locator_is_skipped(self, tmp_path):
        root = mini_copy(tmp_path)
        mem_def = root / "dict" / "dom" / "md" / "mem-def.xml"
        mem_def.write_text(
            mem_def.read_text(encoding="utf-8").replace(
                'xlink:href="mem.xsd#be_x2"', 'xlink:href="mem.xsd"'
            ),
            encoding="utf-8",
        )
        model = read(root)
        domain = next(
            d for d in model.domains if d.qname == "be_exp:MD"
        )
        assert [m.code for m in domain.members] == ["x0", "x1"]

    def test_member_arc_to_unscanned_file_is_skipped(self, tmp_path):
        root = mini_copy(tmp_path)
        mem_def = root / "dict" / "dom" / "md" / "mem-def.xml"
        mem_def.write_text(
            mem_def.read_text(encoding="utf-8").replace(
                'xlink:href="mem.xsd#be_x2"',
                'xlink:href="elsewhere.xsd#be_x2"',
            ),
            encoding="utf-8",
        )
        model = read(root)
        domain = next(
            d for d in model.domains if d.qname == "be_exp:MD"
        )
        assert [m.code for m in domain.members] == ["x0", "x1"]


class TestModuleEdges:
    def test_schema_without_module_type_warns(self, tmp_path):
        root = mini_copy(tmp_path)
        mod = root / "fws" / "mini" / "2015-01-01" / "mod" / "mod_a.xsd"
        mod.write_text(
            mod.read_text(encoding="utf-8").replace(
                'type="model:moduleType"', 'type="xbrli:stringItemType"'
            ),
            encoding="utf-8",
        )
        model = read(root)
        assert model.modules == ()
        assert any("no moduleType" in w for w in model.warnings)
        assert any("No module schemas" in w for w in model.warnings)

    def test_module_without_id_gets_no_labels(self, tmp_path):
        root = mini_copy(tmp_path)
        mod = root / "fws" / "mini" / "2015-01-01" / "mod" / "mod_a.xsd"
        mod.write_text(
            mod.read_text(encoding="utf-8").replace(
                ' id="be_mod_a"', ""
            ),
            encoding="utf-8",
        )
        model = read(root)
        module = model.modules[0]
        assert module.name == "mod_a"
        assert module.labels == ()

    def test_module_with_english_label_prefers_it(self, tmp_path):
        root = mini_copy(tmp_path)
        lab = (
            root / "fws" / "mini" / "2015-01-01" / "mod"
            / "mod_a-lab-fr.xml"
        )
        lab.write_text(
            lab.read_text(encoding="utf-8").replace(
                'xml:lang="fr"', 'xml:lang="en"'
            ),
            encoding="utf-8",
        )
        model = read(root)
        assert model.modules[0].name == "Module A, consolidé"


class TestTableEdges:
    def test_missing_tables_warn(self, tmp_path):
        root = mini_copy(tmp_path)
        shutil.rmtree(root / "fws" / "mini" / "2015-01-01" / "tab")
        model = read(root)
        assert model.tables == ()
        assert any("No *-rend.xml" in w for w in model.warnings)

    def test_conflicting_concept_aspects_skip_cell(self, tmp_path):
        root = mini_copy(tmp_path)
        rend = (
            root / "fws" / "mini" / "2015-01-01" / "tab" / "t_1.00"
            / "t_1.00-rend.xml"
        )
        # Give the X column its own conflicting concept aspect.
        rend.write_text(
            rend.read_text(encoding="utf-8").replace(
                '<table:ruleNode xlink:type="resource" '
                'xlink:label="be_c1" id="be_c1">',
                '<table:ruleNode xlink:type="resource" '
                'xlink:label="be_c1" id="be_c1">'
                "<formula:concept><formula:qname>be_met:ii2"
                "</formula:qname></formula:concept>",
            ),
            encoding="utf-8",
        )
        model = read(root)
        table = model.tables[0]
        # mi1 x c1 conflicts (skipped); ii2 x c1 agrees; c2 fine.
        assert len(table.cells) == 3
        assert any(
            "conflicting concept aspects" in w for w in model.warnings
        )

    def test_axis_without_concept_anywhere_skips_cells(self, tmp_path):
        root = mini_copy(tmp_path)
        rend = (
            root / "fws" / "mini" / "2015-01-01" / "tab" / "t_1.00"
            / "t_1.00-rend.xml"
        )
        text = rend.read_text(encoding="utf-8")
        text = text.replace(
            "<formula:concept><formula:qname>be_met:mi1"
            "</formula:qname></formula:concept>",
            "",
        ).replace(
            "<formula:concept>\n        "
            "<formula:qname>be_met:mi1</formula:qname>\n      "
            "</formula:concept>",
            "",
        )
        rend.write_text(text, encoding="utf-8")
        model = read(root)
        assert any(
            "no concept aspect" in w for w in model.warnings
        )


class TestLabelFallbacks:
    def test_table_display_falls_back_to_non_english(self, tmp_path):
        root = mini_copy(tmp_path)
        lab = (
            root / "fws" / "mini" / "2015-01-01" / "tab" / "t_1.00"
            / "t_1.00-lab-en.xml"
        )
        lab.write_text(
            lab.read_text(encoding="utf-8").replace(
                'xml:lang="en"', 'xml:lang="nl"'
            ),
            encoding="utf-8",
        )
        model = read(root)
        assert model.tables[0].name == "T_1.00 Mini table"

    def test_dict_name_falls_back_to_non_english(self, tmp_path):
        root = mini_copy(tmp_path)
        (root / "dict" / "dom" / "md" / "mem-lab-en.xml").unlink()
        model = read(root)
        domain = next(
            d for d in model.domains if d.qname == "be_exp:MD"
        )
        member = next(m for m in domain.members if m.code == "x1")
        assert member.name == "Banques"  # fr label
        other = next(m for m in domain.members if m.code == "x2")
        assert other.name == "x2"  # element name fallback

    def test_hierarchy_arc_to_unknown_target_is_skipped(self, tmp_path):
        root = mini_copy(tmp_path)
        hier = root / "dict" / "dom" / "md" / "hier-def.xml"
        hier.write_text(
            hier.read_text(encoding="utf-8").replace(
                'xlink:href="mem.xsd#be_x2"',
                'xlink:href="ghost.xsd#be_x2"',
            ),
            encoding="utf-8",
        )
        model = read(root)
        hierarchy = model.hierarchies[0]
        assert len(hierarchy.nodes) == 2

    def test_table_without_row_leaves_has_no_cells(self, tmp_path):
        root = mini_copy(tmp_path)
        rend = (
            root / "fws" / "mini" / "2015-01-01" / "tab" / "t_1.00"
            / "t_1.00-rend.xml"
        )
        text = rend.read_text(encoding="utf-8")
        # Drop the Y breakdown wiring: no rows -> no cells.
        text = text.replace('axis="y"', 'axis="q"')
        rend.write_text(text, encoding="utf-8")
        model = read(root)
        assert model.tables[0].cells == ()


class TestNodeLabelIndexOrdering:
    def test_code_lookup_skips_standard_labels(self):
        from dpmcore.loaders.xbrl.model import XLabel
        from dpmcore.loaders.xbrl.reader_dpm1 import _NodeLabelIndex

        index = _NodeLabelIndex(
            "f.xml",
            {
                ("f.xml", "n"): [
                    XLabel("en", "Name"),
                    XLabel("en", "010", role="code"),
                ]
            },
        )
        assert index.code("n") == "010"

    def test_display_name_skips_non_english_first(self, tmp_path):
        from dpmcore.loaders.xbrl.model import XLabel
        from dpmcore.loaders.xbrl.reader_dpm1 import _Dpm1Reader

        root = mini_copy(tmp_path)
        reader = _Dpm1Reader(root, [])
        met_path = root / "dict" / "met" / "met.xsd"
        record = reader._elements_by_file[met_path][0]
        reader._labels[(record.path.resolve(), record.fragment)] = [
            XLabel("fr", "Valeur"),
            XLabel("en", "Value"),
        ]
        assert reader._display_name(record) == "Value"

    def test_module_name_skips_non_english_first(self, tmp_path):
        root = mini_copy(tmp_path)
        lab = (
            root / "fws" / "mini" / "2015-01-01" / "mod"
            / "mod_a-lab-fr.xml"
        )
        text = lab.read_text(encoding="utf-8")
        extra = (
            '<link:loc xlink:type="locator" '
            'xlink:href="mod_a.xsd#be_mod_a" xlink:label="loc2"/>'
            '<link:label xlink:type="resource" xlink:label="lab2" '
            'xml:lang="en" '
            'xlink:role="http://www.xbrl.org/2003/role/label"'
            ">Module A, consolidated</link:label>"
            '<link:labelArc xlink:type="arc" '
            'xlink:arcrole='
            '"http://www.xbrl.org/2003/arcrole/concept-label" '
            'xlink:from="loc2" xlink:to="lab2"/>'
        )
        lab.write_text(
            text.replace("</link:labelLink>", extra + "</link:labelLink>"),
            encoding="utf-8",
        )
        model = read(root)
        assert model.modules[0].name == "Module A, consolidated"

    def test_display_name_with_only_code_labels_uses_element_name(
        self, tmp_path
    ):
        from dpmcore.loaders.xbrl.model import XLabel
        from dpmcore.loaders.xbrl.reader_dpm1 import _Dpm1Reader

        root = mini_copy(tmp_path)
        reader = _Dpm1Reader(root, [])
        met_path = root / "dict" / "met" / "met.xsd"
        record = reader._elements_by_file[met_path][0]
        reader._labels[(record.path.resolve(), record.fragment)] = [
            XLabel("en", "010", role="code"),
        ]
        assert reader._display_name(record) == record.name

    def test_non_tab_imports_are_not_table_codes(self, tmp_path):
        root = mini_copy(tmp_path)
        mod = root / "fws" / "mini" / "2015-01-01" / "mod" / "mod_a.xsd"
        mod.write_text(
            mod.read_text(encoding="utf-8").replace(
                "<xs:import",
                '<xs:import namespace='
                '"http://www.xbrl.org/2003/instance" '
                'schemaLocation="http://www.xbrl.org/2003/'
                'xbrl-instance-2003-12-31.xsd"/>\n  <xs:import',
                1,
            ),
            encoding="utf-8",
        )
        model = read(root)
        assert model.modules[0].table_codes == ("T_1.00",)

    def test_member_placed_under_two_parents_appears_once(
        self, tmp_path
    ):
        root = mini_copy(tmp_path)
        hier = root / "dict" / "dom" / "md" / "hier-def.xml"
        text = hier.read_text(encoding="utf-8")
        extra = (
            '<link:definitionArc xlink:type="arc" xlink:arcrole='
            '"http://xbrl.org/int/dim/arcrole/domain-member" '
            'xlink:from="loc_be_x1" xlink:to="loc_be_x2" order="9"/>'
        )
        hier.write_text(
            text.replace(
                "</link:definitionLink>", extra + "</link:definitionLink>"
            ),
            encoding="utf-8",
        )
        model = read(root)
        members = [n.member_qname for n in model.hierarchies[0].nodes]
        assert members.count("be_MD:x2") == 1
