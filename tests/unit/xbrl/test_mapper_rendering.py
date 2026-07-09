"""Tests for the rendering half of the taxonomy mapper."""

from datetime import date

from dpmcore.loaders.xbrl.model import (
    TaxonomyModel,
    XAxis,
    XCell,
    XDimension,
    XDomain,
    XHeaderNode,
    XMember,
    XMetric,
    XModule,
    XTable,
)
from dpmcore.orm.glossary import Context, ContextComposition
from dpmcore.orm.packaging import (
    Framework,
    Module,
    ModuleVersion,
    ModuleVersionComposition,
)
from dpmcore.orm.rendering import (
    Cell,
    Header,
    HeaderVersion,
    Table,
    TableVersion,
    TableVersionCell,
    TableVersionHeader,
)
from dpmcore.orm.variables import Variable, VariableVersion

from .test_mapper_dictionary import make_mapper

DOMAIN = XDomain(
    qname="d:CptyDomain",
    code=None,
    name="Counterparty domain",
    members=(
        XMember(qname="d:Banks", name="Banks"),
        XMember(qname="d:Corporates", name="Corporates"),
    ),
)

DIMENSION = XDimension(
    qname="d:ByCptyDimension",
    code=None,
    name="By counterparty",
    domain_qname="d:CptyDomain",
)

OPEN_DIMENSION = XDimension(
    qname="d:CurrencyDimension",
    code=None,
    name="Currency",
    is_open=True,
)

METRICS = (
    XMetric(
        qname="p:Cash",
        code=None,
        name="Cash",
        xbrl_type="xbrli:monetaryItemType",
        period_type="instant",
    ),
    XMetric(
        qname="p:Loans",
        code=None,
        name="Loans",
        xbrl_type="xbrli:monetaryItemType",
        period_type="instant",
    ),
)

Y_AXIS = XAxis(
    direction="Y",
    nodes=(
        XHeaderNode(
            node_id="y-root",
            parent_id=None,
            order=1,
            label="Assets",
            is_abstract=True,
        ),
        XHeaderNode(
            node_id="y-cash",
            parent_id="y-root",
            order=2,
            label="Cash",
            metric_qname="p:Cash",
        ),
        XHeaderNode(
            node_id="y-loans",
            parent_id="y-root",
            order=3,
            label="Loans",
            metric_qname="p:Loans",
        ),
    ),
)

X_AXIS = XAxis(
    direction="X",
    nodes=(
        XHeaderNode(
            node_id="x-banks",
            parent_id=None,
            order=1,
            label="Banks",
            dim_members=(("d:ByCptyDimension", "d:Banks"),),
        ),
        XHeaderNode(
            node_id="x-corp",
            parent_id=None,
            order=2,
            label="Corporates",
            dim_members=(("d:ByCptyDimension", "d:Corporates"),),
        ),
    ),
)

Z_AXIS = XAxis(direction="Z", open_dimension_qnames=("d:CurrencyDimension",))

CELLS = (
    XCell(
        row_node_id="y-cash",
        column_node_id="x-banks",
        metric_qname="p:Cash",
        dim_members=(("d:ByCptyDimension", "d:Banks"),),
    ),
    XCell(
        row_node_id="y-cash",
        column_node_id="x-corp",
        metric_qname="p:Cash",
        dim_members=(("d:ByCptyDimension", "d:Corporates"),),
    ),
    XCell(
        row_node_id="y-loans",
        column_node_id="x-banks",
        metric_qname="p:Loans",
        dim_members=(("d:ByCptyDimension", "d:Banks"),),
    ),
)

TABLE = XTable(
    code="T1",
    name="Test table",
    description="A table for tests",
    axes=(Y_AXIS, X_AXIS, Z_AXIS),
    cells=CELLS,
    entry_schema="t-Test-2008-01-01.xsd",
)

MODULE = XModule(
    code="T1M",
    name="Test module",
    entry_point="t-Test-2008-01-01.xsd",
    table_codes=("T1",),
    version="1.0",
    from_date=date(2008, 1, 1),
)


def model(**kwargs):
    kwargs.setdefault("framework_code", "B2P2")
    kwargs.setdefault("framework_name", "Basel II Pillar 2")
    kwargs.setdefault("domains", (DOMAIN,))
    kwargs.setdefault("dimensions", (DIMENSION, OPEN_DIMENSION))
    kwargs.setdefault("metrics", METRICS)
    kwargs.setdefault("tables", (TABLE,))
    kwargs.setdefault("modules", (MODULE,))
    return TaxonomyModel(**kwargs)


def run_mapper(session, m=None, **mapper_kwargs):
    mapper = make_mapper(session, **mapper_kwargs)
    outcome = mapper.map_model(m if m is not None else model())
    session.commit()
    return mapper, outcome


class TestTables:
    def test_table_and_version_created(self, schema_session):
        _, outcome = run_mapper(schema_session)
        table = schema_session.query(Table).one()
        assert table.has_open_sheets is True
        assert table.has_open_columns is False
        assert table.has_open_rows is False

        version = schema_session.query(TableVersion).one()
        assert version.code == "T1"
        assert version.name == "Test table"
        assert version.description == "A table for tests"
        assert outcome.created["Table"] == 1
        assert outcome.created["TableVersion"] == 1

    def test_headers_follow_axis_layout(self, schema_session):
        run_mapper(schema_session)
        rows = (
            schema_session.query(Header)
            .filter(Header.direction == "Y")
            .count()
        )
        cols = (
            schema_session.query(Header)
            .filter(Header.direction == "X")
            .count()
        )
        keys = (
            schema_session.query(Header)
            .filter(Header.is_key.is_(True))
            .all()
        )
        assert rows == 3
        assert cols == 2
        assert len(keys) == 1
        assert keys[0].direction == "Z"

    def test_header_versions_carry_codes_and_links(self, schema_session):
        run_mapper(schema_session)
        by_label = {
            hv.label: hv
            for hv in schema_session.query(HeaderVersion).all()
        }
        assert by_label["Assets"].code == "0010"
        assert by_label["Cash"].property_id is not None
        assert by_label["Assets"].property_id is None
        assert by_label["Banks"].context_id is not None
        # The open-dimension key header links the dimension property.
        assert by_label["Currency"].property_id is not None
        assert by_label["Currency"].code == "sK1"

    def test_header_tree_via_table_version_header(self, schema_session):
        run_mapper(schema_session)
        version = schema_session.query(TableVersion).one()
        links = {
            link.header_vid: link
            for link in schema_session.query(TableVersionHeader)
            .filter(TableVersionHeader.table_vid == version.table_vid)
            .all()
        }
        by_label = {
            hv.label: hv
            for hv in schema_session.query(HeaderVersion).all()
        }
        root_link = links[by_label["Assets"].header_vid]
        cash_link = links[by_label["Cash"].header_vid]
        assert root_link.parent_header_id is None
        assert root_link.is_abstract is True
        assert cash_link.parent_header_id == by_label["Assets"].header_id
        assert cash_link.is_abstract is False

    def test_cells_variables_and_contexts(self, schema_session):
        _, outcome = run_mapper(schema_session)
        assert schema_session.query(Cell).count() == 3
        assert schema_session.query(Variable).count() == 3
        assert schema_session.query(VariableVersion).count() == 3
        # Two distinct member combinations -> two contexts.
        assert schema_session.query(Context).count() == 2
        assert schema_session.query(ContextComposition).count() == 2
        assert outcome.created["Cell"] == 3
        assert outcome.created["Context"] == 2

    def test_context_signature_format(self, schema_session):
        run_mapper(schema_session)
        signatures = sorted(
            ctx.signature for ctx in schema_session.query(Context).all()
        )
        for signature in signatures:
            assert signature.endswith("#")
            pid, iid = signature.rstrip("#").split("_")
            assert pid.isdigit()
            assert iid.isdigit()

    def test_cell_codes_use_header_codes(self, schema_session):
        run_mapper(schema_session)
        codes = {
            tvc.cell_code
            for tvc in schema_session.query(TableVersionCell).all()
        }
        assert "{T1, r0020, c0010}" in codes
        assert "{T1, r0030, c0010}" in codes


class TestModules:
    def test_framework_module_and_composition(self, schema_session):
        _, outcome = run_mapper(schema_session)
        framework = schema_session.query(Framework).one()
        assert framework.code == "B2P2"
        module = schema_session.query(Module).one()
        assert module.framework_id == framework.framework_id

        version = schema_session.query(ModuleVersion).one()
        assert version.code == "T1M"
        assert version.description == "t-Test-2008-01-01.xsd"
        assert version.version_number == "1.0"
        assert version.from_reference_date == date(2008, 1, 1)
        assert version.is_reported is True

        composition = schema_session.query(ModuleVersionComposition).one()
        table_version = schema_session.query(TableVersion).one()
        assert composition.table_vid == table_version.table_vid
        assert composition.order == 1
        assert outcome.created["Framework"] == 1
        assert outcome.created["Module"] == 1
        assert outcome.created["ModuleVersion"] == 1

    def test_module_with_unknown_table_warns(self, schema_session):
        bad_module = XModule(
            code="BAD",
            name="Bad module",
            entry_point="bad.xsd",
            table_codes=("MISSING",),
        )
        _, outcome = run_mapper(
            schema_session, model(modules=(MODULE, bad_module))
        )
        assert (
            schema_session.query(ModuleVersionComposition).count() == 1
        )
        assert any("unknown table" in w for w in outcome.warnings)


class TestIdempotencyAndVersioning:
    def test_reimport_same_release_reuses_everything(self, schema_session):
        run_mapper(schema_session)
        _, outcome = run_mapper(schema_session)
        assert schema_session.query(TableVersion).count() == 1
        assert schema_session.query(ModuleVersion).count() == 1
        assert schema_session.query(Cell).count() == 3
        assert outcome.created.get("Table") is None
        assert outcome.created.get("Cell") is None
        assert outcome.reused["TableVersion"] == 1
        assert outcome.reused["ModuleVersion"] == 1

    def test_new_release_end_dates_old_versions(self, schema_session):
        run_mapper(schema_session)
        _, outcome = run_mapper(
            schema_session,
            release_code="2019-10-01",
            release_date=date(2019, 10, 1),
        )
        versions = (
            schema_session.query(TableVersion)
            .order_by(TableVersion.table_vid)
            .all()
        )
        assert len(versions) == 2
        assert versions[0].end_release_id == outcome.release_id
        assert versions[1].start_release_id == outcome.release_id
        assert versions[1].end_release_id is None
        # Both versions share the same Table entity.
        assert versions[0].table_id == versions[1].table_id

        module_versions = schema_session.query(ModuleVersion).all()
        assert len(module_versions) == 2

    def test_variables_are_reused_across_releases(self, schema_session):
        run_mapper(schema_session)
        _, outcome = run_mapper(
            schema_session,
            release_code="2019-10-01",
            release_date=date(2019, 10, 1),
        )
        # Datapoints did not change, so no new Variable rows.
        assert schema_session.query(Variable).count() == 3
        assert outcome.reused["Variable"] == 3


class TestWarnings:
    def test_cell_with_unknown_header_is_skipped(self, schema_session):
        broken_table = XTable(
            code="T2",
            name="Broken",
            axes=(Y_AXIS, X_AXIS),
            cells=(
                XCell(
                    row_node_id="nope",
                    column_node_id="x-banks",
                    metric_qname="p:Cash",
                ),
            ),
        )
        _, outcome = run_mapper(schema_session, model(tables=(broken_table,)))
        assert schema_session.query(Cell).count() == 0
        assert any("unknown headers" in w for w in outcome.warnings)

    def test_cell_with_unknown_metric_gets_shadow_property(
        self, schema_session
    ):
        broken_table = XTable(
            code="T3",
            name="Broken metric",
            axes=(Y_AXIS, X_AXIS),
            cells=(
                XCell(
                    row_node_id="y-cash",
                    column_node_id="x-banks",
                    metric_qname="p:NotThere",
                ),
            ),
        )
        _, outcome = run_mapper(schema_session, model(tables=(broken_table,)))
        # The cell survives, backed by an owned shadow property.
        assert schema_session.query(Cell).count() == 1
        from dpmcore.orm.glossary import Item

        shadow = (
            schema_session.query(Item)
            .filter(Item.name == "p:NotThere")
            .one()
        )
        assert shadow.is_property is True
        assert any("shadow row" in w for w in outcome.warnings)

    def test_header_with_unknown_metric_gets_shadow_property(
        self, schema_session
    ):
        axis = XAxis(
            direction="Y",
            nodes=(
                XHeaderNode(
                    node_id="y1",
                    parent_id=None,
                    order=1,
                    label="Ghost",
                    metric_qname="p:Ghost",
                ),
            ),
        )
        _, outcome = run_mapper(
            schema_session,
            model(tables=(XTable(code="T4", name="G", axes=(axis,)),)),
        )
        header_version = (
            schema_session.query(HeaderVersion)
            .filter(HeaderVersion.label == "Ghost")
            .one()
        )
        assert header_version.property_id is not None
        assert any("'p:Ghost'" in w for w in outcome.warnings)

    def test_open_axis_with_unknown_dimension_warns(self, schema_session):
        axis = XAxis(direction="Z", open_dimension_qnames=("d:Ghost",))
        _, outcome = run_mapper(
            schema_session,
            model(tables=(XTable(code="T5", name="G", axes=(axis,)),)),
        )
        assert any(
            "opens unknown dimension" in w for w in outcome.warnings
        )

    def test_unresolvable_context_pair_gets_shadow_rows(
        self, schema_session
    ):
        table = XTable(
            code="T6",
            name="Partial context",
            axes=(Y_AXIS, X_AXIS),
            cells=(
                XCell(
                    row_node_id="y-cash",
                    column_node_id="x-banks",
                    metric_qname="p:Cash",
                    dim_members=(("d:Ghost", "d:GhostMember"),),
                ),
            ),
        )
        _, outcome = run_mapper(schema_session, model(tables=(table,)))
        assert any("shadow row" in w for w in outcome.warnings)
        # The cell keeps a full context built from shadow rows.
        cell_link = schema_session.query(TableVersionCell).one()
        variable_version = schema_session.get(
            VariableVersion, cell_link.variable_vid
        )
        assert variable_version.context_id is not None
        composition = (
            schema_session.query(ContextComposition)
            .filter(
                ContextComposition.context_id
                == variable_version.context_id
            )
            .one()
        )
        from dpmcore.orm.glossary import Item

        member = schema_session.get(Item, composition.item_id)
        assert member.name == "d:GhostMember"

    def test_shadow_property_reuses_existing_signature(
        self, schema_session
    ):
        from dpmcore.orm.glossary import Item, ItemCategory, Property

        # Simulate a database that already holds the EBA metric.
        first_mapper, _ = run_mapper(schema_session)
        schema_session.add(Item(item_id=8888, name="EBA metric"))
        schema_session.add(
            Property(property_id=8888, is_metric=True)
        )
        schema_session.add(
            ItemCategory(
                item_id=8888,
                start_release_id=first_mapper.release.release_id,
                category_id=1002,
                code="mi88",
                signature="eba_met:mi88",
            )
        )
        schema_session.commit()

        table = XTable(
            code="T7B",
            name="EBA metric reuse",
            axes=(Y_AXIS, X_AXIS),
            cells=(
                XCell(
                    row_node_id="y-cash",
                    column_node_id="x-banks",
                    metric_qname="eba_met:mi88",
                ),
            ),
        )
        _, outcome = run_mapper(
            schema_session,
            model(tables=(table,)),
            release_code="2021-01-01",
        )
        assert outcome.reused.get("Property", 0) >= 1
        assert not any("'eba_met:mi88'" in w for w in outcome.warnings)


class TestRemainingBranches:
    def test_cell_with_sheet_header_gets_sheet_code(self, schema_session):
        z_axis = XAxis(
            direction="Z",
            nodes=(
                XHeaderNode(
                    node_id="z-total",
                    parent_id=None,
                    order=1,
                    label="Total",
                ),
            ),
        )
        table = XTable(
            code="T7",
            name="With sheets",
            axes=(Y_AXIS, X_AXIS, z_axis),
            cells=(
                XCell(
                    row_node_id="y-cash",
                    column_node_id="x-banks",
                    sheet_node_id="z-total",
                    metric_qname="p:Cash",
                ),
            ),
        )
        run_mapper(schema_session, model(tables=(table,)))
        cell_link = schema_session.query(TableVersionCell).one()
        assert cell_link.cell_code == "{T7, r0020, c0010, s0010}"
        cell = schema_session.query(Cell).one()
        assert cell.sheet_id is not None

    def test_variable_cache_hit_for_same_datapoint(self, schema_session):
        duplicate = XTable(
            code="T8",
            name="Duplicate datapoint",
            axes=(Y_AXIS, X_AXIS),
            cells=(CELLS[0],),
        )
        _, outcome = run_mapper(
            schema_session, model(tables=(TABLE, duplicate))
        )
        # Same metric+context in both tables -> one Variable.
        assert schema_session.query(Variable).count() == 3
        assert schema_session.query(Cell).count() == 4

    def test_context_pair_resolves_member_from_db_signature(
        self, schema_session
    ):
        from dpmcore.orm.glossary import Item, ItemCategory

        # A prior import left a member with this qname signature.
        first_mapper, _ = run_mapper(schema_session)
        eba_item = Item(item_id=7777, name="EBA member")
        schema_session.add(eba_item)
        schema_session.add(
            ItemCategory(
                item_id=7777,
                start_release_id=first_mapper.release.release_id,
                category_id=1002,
                code="x99",
                signature="eba_MC:x99",
            )
        )
        schema_session.commit()

        table = XTable(
            code="T9",
            name="Reuses EBA member",
            axes=(Y_AXIS, X_AXIS),
            cells=(
                XCell(
                    row_node_id="y-cash",
                    column_node_id="x-banks",
                    metric_qname="p:Cash",
                    dim_members=(("d:ByCptyDimension", "eba_MC:x99"),),
                ),
            ),
        )
        _, outcome = run_mapper(
            schema_session,
            model(tables=(table,)),
            release_code="2020-01-01",
        )
        context = (
            schema_session.query(ContextComposition)
            .filter(ContextComposition.item_id == 7777)
            .one()
        )
        assert context is not None
        assert not any(
            "cannot resolve dimension pair" in w for w in outcome.warnings
        )

    def test_shadow_warning_is_emitted_once_per_qname(
        self, schema_session
    ):
        table = XTable(
            code="T8B",
            name="Twice unknown",
            axes=(Y_AXIS, X_AXIS),
            cells=(
                XCell(
                    row_node_id="y-cash",
                    column_node_id="x-banks",
                    metric_qname="p:SameGhost",
                ),
                XCell(
                    row_node_id="y-cash",
                    column_node_id="x-corp",
                    metric_qname="p:SameGhost",
                ),
            ),
        )
        _, outcome = run_mapper(schema_session, model(tables=(table,)))
        shadow_warnings = [
            w for w in outcome.warnings if "'p:SameGhost'" in w
        ]
        assert len(shadow_warnings) == 1

    def test_warn_shadow_dedupes_direct_calls(self, schema_session):
        mapper, _ = run_mapper(schema_session)
        mapper._warn_shadow("x:dup")
        before = len(mapper.outcome.warnings)
        mapper._warn_shadow("x:dup")
        assert len(mapper.outcome.warnings) == before
