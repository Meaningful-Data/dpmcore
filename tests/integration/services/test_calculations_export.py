"""End-to-end tests for the calculations export service.

Seeds a minimal DPM dictionary -- one framework, two modules, three
tables, and two calculation operations linked through
``OperationOutput`` -- and exercises
``ASTGeneratorService.calculations_for_module`` /
``calculations_datapoints`` over it.

The export is a downstream contract, so the assertions are about its
*shape*: the namespace key, the operation codes paired with the right
statements, the resolved output variables and tables, and the
dependency module the calculations read from. Byte parity with the EBA
``drr_operations`` script is checked separately by
``scripts/check_export_parity.py`` against a real DPM SQL Server.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from dpmcore.errors import ConfigurationError, NotFound
from dpmcore.orm.glossary import Property
from dpmcore.orm.infrastructure import DataType, Release
from dpmcore.orm.operations import (
    Operation,
    OperationOutput,
    OperationVersion,
)
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
from dpmcore.services.ast_generator import ASTGeneratorService
from dpmcore.services.calculations_export.visitors import (
    CalculationsOperandsChecking,
)
from dpmcore.services.syntax import SyntaxService

RELEASE = 8001
LATER = 8002

HOME_MODULE = "CALC_HOME"
DEP_MODULE = "CALC_DEP"
HOME_TABLE = "C_99.00"
DEP_TABLE = "C_98.00"

REFERENCE_DATE = "2026-06-30"
PUBLICATION_DATE = "2026-01-01"

# Row/column codes shared by both tables, so a cell is addressed the
# same way in the home and the dependency table.
ROWS = ("0010", "0020", "0030")
COLUMN = "0010"


def _seed_infrastructure(session):
    """Releases, data type, property and framework."""
    session.add_all(
        [
            Release(release_id=RELEASE, code="8.0", date=date(2025, 1, 1)),
            Release(release_id=LATER, code="8.1", date=date(2026, 1, 1)),
            DataType(data_type_id=1, code="m"),
            Property(property_id=1, data_type_id=1, is_metric=True),
            Framework(framework_id=1, code="CALCFW"),
            Module(module_id=1, framework_id=1),
            Module(module_id=2, framework_id=1),
        ]
    )


def _seed_module_version(session, *, module_vid, module_id, code):
    """One open module version whose reference window covers the test date."""
    session.add(
        ModuleVersion(
            module_vid=module_vid,
            module_id=module_id,
            code=code,
            version_number="1.0.0",
            from_reference_date=date(2026, 1, 1),
            to_reference_date=date(2026, 12, 31),
            start_release_id=RELEASE,
            end_release_id=None,
        )
    )


def _seed_table(session, *, table_id, table_vid, module_vid, code):
    """A table version with one column and three rows of real cells."""
    session.add(Table(table_id=table_id))
    session.add(
        TableVersion(
            table_vid=table_vid,
            table_id=table_id,
            code=code,
            start_release_id=RELEASE,
            end_release_id=None,
        )
    )
    session.add(
        ModuleVersionComposition(
            module_vid=module_vid, table_vid=table_vid, table_id=table_id
        )
    )

    column_header_id = table_id * 100
    session.add(Header(header_id=column_header_id, direction="X", is_key=True))
    session.add(
        HeaderVersion(
            header_vid=column_header_id,
            header_id=column_header_id,
            code=COLUMN,
        )
    )
    session.add(
        TableVersionHeader(
            table_vid=table_vid,
            header_id=column_header_id,
            header_vid=column_header_id,
            order=1,
        )
    )

    for index, row_code in enumerate(ROWS, start=1):
        header_id = table_id * 100 + index
        cell_id = table_vid * 100 + index
        variable_vid = table_vid * 1000 + index
        variable_id = variable_vid

        session.add(Header(header_id=header_id, direction="Y", is_key=True))
        session.add(
            HeaderVersion(
                header_vid=header_id, header_id=header_id, code=row_code
            )
        )
        session.add(
            TableVersionHeader(
                table_vid=table_vid,
                header_id=header_id,
                header_vid=header_id,
                order=index,
            )
        )
        session.add(
            Cell(
                cell_id=cell_id,
                table_id=table_id,
                row_id=header_id,
                column_id=column_header_id,
            )
        )
        session.add(Variable(variable_id=variable_id))
        session.add(
            VariableVersion(
                variable_vid=variable_vid,
                variable_id=variable_id,
                property_id=1,
                code=f"V{variable_vid}",
                start_release_id=RELEASE,
                end_release_id=None,
            )
        )
        session.add(
            TableVersionCell(
                table_vid=table_vid,
                cell_id=cell_id,
                cell_code=f"{{{code}, r{row_code}, c{COLUMN}}}",
                variable_vid=variable_vid,
                is_nullable=True,
                is_void=False,
                is_excluded=False,
            )
        )


def _seed_operation(session, *, operation_id, module_vid, code, expression):
    """A calculation operation writing into ``module_vid``."""
    session.add(
        Operation(operation_id=operation_id, code=code, type="calculation")
    )
    session.add(
        OperationVersion(
            operation_vid=operation_id,
            operation_id=operation_id,
            expression=expression,
            start_release_id=RELEASE,
            end_release_id=None,
        )
    )
    session.add(
        OperationOutput(operation_vid=operation_id, module_vid=module_vid)
    )


@pytest.fixture
def calc_session(memory_session):
    """A dictionary with two calculations on ``HOME_MODULE``."""
    session = memory_session
    _seed_infrastructure(session)
    _seed_module_version(session, module_vid=1, module_id=1, code=HOME_MODULE)
    _seed_module_version(session, module_vid=2, module_id=2, code=DEP_MODULE)
    _seed_table(
        session, table_id=1, table_vid=11, module_vid=1, code=HOME_TABLE
    )
    _seed_table(
        session, table_id=2, table_vid=22, module_vid=2, code=DEP_TABLE
    )
    # The second calculation consumes the first one's output, so the DAG
    # has to reorder them: they are stored the other way round.
    _seed_operation(
        session,
        operation_id=101,
        module_vid=1,
        code="c_0002",
        expression=(
            f"{{t{HOME_TABLE}, r0030, c{COLUMN}}} <- "
            f"{{t{HOME_TABLE}, r0020, c{COLUMN}}} * 2"
        ),
    )
    _seed_operation(
        session,
        operation_id=100,
        module_vid=1,
        code="c_0001",
        expression=(
            f"{{t{HOME_TABLE}, r0020, c{COLUMN}}} <- "
            f"{{t{DEP_TABLE}, r0010, c{COLUMN}}} + 1"
        ),
    )
    session.commit()
    return session


@pytest.fixture(autouse=True)
def _clear_query_caches():
    """The table-data and axis caches are keyed per engine, not per test.

    Every in-memory SQLite engine shares one cache key, so an entry left
    by an earlier test module would be served to the first test here.
    Cleared on both sides of the yield for that reason.
    """
    from dpmcore.dpm_xl.model_queries import ViewDatapointsQuery

    ViewDatapointsQuery._TABLE_DATA_CACHE.clear()
    ViewDatapointsQuery._AXIS_ORDER_CACHE.clear()
    yield
    ViewDatapointsQuery._TABLE_DATA_CACHE.clear()
    ViewDatapointsQuery._AXIS_ORDER_CACHE.clear()


def _namespace(export):
    """The single namespace block of an export."""
    assert len(export) == 1
    return next(iter(export.values()))


class TestCalculationsForModule:
    def test_namespace_is_the_module_uri(self, calc_session):
        export = ASTGeneratorService(calc_session).calculations_for_module(
            HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
        )

        (uri,) = export
        assert uri == (
            "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/calcfw/8.0/"
            "mod/calc_home"
        )

    def test_module_block(self, calc_session):
        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        assert ns["module_code"] == HOME_MODULE
        assert ns["framework_code"] == "CALCFW"
        assert ns["module_version"] == "1.0.0"
        assert ns["dpm_release"] == {
            "release": "8.0",
            "publication_date": PUBLICATION_DATE,
        }
        assert ns["dates"] == {"from": "2026-01-01", "to": "2026-12-31"}

    def test_calculations_are_ordered_by_dependency(self, calc_session):
        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        # c_0001 produces r0020, which c_0002 consumes: it must come
        # first even though the rows come back in the other order.
        assert ns["calculations"]["operation_codes"] == ["c_0001", "c_0002"]

    def test_operation_codes_pair_with_their_statements(self, calc_session):
        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        children = ns["calculations"]["ast"]["children"]
        codes = ns["calculations"]["operation_codes"]
        assert len(children) == len(codes)
        # c_0001 reads the dependency table; c_0002 reads the home one.
        by_code = dict(zip(codes, children, strict=True))
        assert by_code["c_0001"]["right"]["left"]["table"] == DEP_TABLE
        assert by_code["c_0002"]["right"]["left"]["table"] == HOME_TABLE

    def test_operands_carry_their_datapoints(self, calc_session):
        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        codes = ns["calculations"]["operation_codes"]
        children = ns["calculations"]["ast"]["children"]
        first = dict(zip(codes, children, strict=True))["c_0001"]
        operand = first["right"]["left"]

        assert operand["class_name"] == "VarID"
        assert operand["row"] == "0010"
        assert operand["column"] == COLUMN
        assert [entry["datapoint"] for entry in operand["data"]] == [22001]
        assert operand["data"][0]["operand_reference_id"] > 100000

    def test_output_variables_are_the_assigned_cells(self, calc_session):
        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        # r0020 and r0030 of the home table are assigned to.
        assert ns["output_variables"] == {"11002": "m", "11003": "m"}

    def test_output_tables_are_the_home_module_tables(self, calc_session):
        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        assert set(ns["output_tables"]) == {HOME_TABLE}
        assert ns["output_tables"][HOME_TABLE]["variables"] == {
            "11002": "m",
            "11003": "m",
        }

    def test_dependency_modules_exclude_the_home_module(self, calc_session):
        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        (dep_uri,) = ns["dependency_modules"]
        assert dep_uri.endswith("/mod/calc_dep")
        tables = ns["dependency_modules"][dep_uri]["tables"]
        assert set(tables) == {DEP_TABLE}
        # The data types survive the grouping pass rather than being
        # flattened back to the "m" default.
        assert tables[DEP_TABLE]["variables"] == {"22001": "m"}

    def test_a_dependency_module_carries_its_merged_variables(
        self, calc_session
    ):
        """The consumer contract wants ``variables`` beside ``tables``.

        It is the union of the module's tables' variables, so a reader
        does not have to walk the tables to learn what the module
        contributes.
        """
        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        (dep_uri,) = ns["dependency_modules"]
        entry = ns["dependency_modules"][dep_uri]
        assert set(entry) == {"tables", "variables"}
        assert entry["variables"] == {"22001": "m"}

    def test_data_types_come_from_the_dictionary(self, calc_session):
        calc_session.query(DataType).filter(DataType.data_type_id == 1).update(
            {DataType.code: "p"}
        )
        calc_session.commit()

        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        (dep_uri,) = ns["dependency_modules"]
        deps = ns["dependency_modules"][dep_uri]["tables"][DEP_TABLE]
        assert deps["variables"] == {"22001": "p"}
        assert ns["output_variables"] == {"11002": "p", "11003": "p"}


class TestCalculationsDatapoints:
    def test_maps_every_operand_datapoint_to_its_cell(self, calc_session):
        datapoints = ASTGeneratorService(calc_session).calculations_datapoints(
            HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
        )

        assert datapoints["22001"] == {
            "table": DEP_TABLE,
            "row": "0010",
            "column": COLUMN,
            "sheet": None,
        }
        assert datapoints["11002"]["table"] == HOME_TABLE
        assert datapoints["11003"]["row"] == "0030"

    def test_agrees_with_the_export_it_accompanies(self, calc_session):
        service = ASTGeneratorService(calc_session)
        export = service.calculations_export(
            HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
        )

        ns = _namespace(export.calculations)
        for table in ns["output_tables"].values():
            for variable_id in table["variables"]:
                assert variable_id in export.datapoints


_WITH_EXPRESSION = (
    f"{{t{HOME_TABLE}, r0020, c{COLUMN}}} <- "
    f"with {{t{DEP_TABLE}, c{COLUMN}}}: {{r0010}} + 1"
)


def _use_with_expression(session):
    """Rewrite c_0001 so its operand sits inside a ``with`` context."""
    session.query(OperationVersion).filter(
        OperationVersion.operation_vid == 100
    ).update({OperationVersion.expression: _WITH_EXPRESSION})
    session.commit()


class TestWithExpressions:
    def test_a_with_context_reaches_the_dependency_tables(self, calc_session):
        """The context has to be grafted before dependencies are collected."""
        _use_with_expression(calc_session)

        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        # {r0010} only names the dependency table through the with
        # context. Collected before the context is grafted, it has no
        # table of its own and is skipped -- leaving the partial
        # selection {tC_98.00, c0010}, which selects no row and so
        # reports every datapoint of the column rather than r0010's.
        (dep_uri,) = ns["dependency_modules"]
        assert dep_uri.endswith("/mod/calc_dep")
        tables = ns["dependency_modules"][dep_uri]["tables"]
        assert set(tables) == {DEP_TABLE}
        assert tables[DEP_TABLE]["variables"] == {"22001": "m"}

    def test_the_operand_resolves_to_the_context_table(self, calc_session):
        _use_with_expression(calc_session)

        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        codes = ns["calculations"]["operation_codes"]
        children = ns["calculations"]["ast"]["children"]
        first = dict(zip(codes, children, strict=True))["c_0001"]
        operand = first["right"]["left"]
        assert operand["table"] == DEP_TABLE
        assert [entry["datapoint"] for entry in operand["data"]] == [22001]

    def test_the_wrapper_is_not_serialized(self, calc_session):
        _use_with_expression(calc_session)

        export = ASTGeneratorService(calc_session).calculations_for_module(
            HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
        )

        assert "WithExpression" not in str(export)

    def test_the_context_does_not_leak_into_the_next_statement(
        self, calc_session
    ):
        """A ``with`` is scoped to its own statement, not the rest."""
        script = (
            f"with {{t{DEP_TABLE}, c{COLUMN}}}: {{r0010}} = {{r0020}};\n"
            f"{{t{HOME_TABLE}, r0030}} <- {{t{HOME_TABLE}, r0020}} * 2;"
        )
        ast = SyntaxService().parse(script)

        checker = CalculationsOperandsChecking(
            calc_session, script, ast, RELEASE, is_scripting=True
        )

        # The second statement omits its columns uniformly, which is
        # legal. A leaked context would silently graft c0010 onto it.
        assert checker.tables[HOME_TABLE]["cols"] is None
        assert checker.partial_selection is None


class TestOperationVersionWindow:
    """Only the operation version effective at the export's release."""

    EARLIER = 8000

    def _supersede(self, session):
        """Give operation 100 an older, already-closed version."""
        session.add(
            Release(release_id=self.EARLIER, code="7.0", date=date(2024, 1, 1))
        )
        session.flush()
        session.add(
            OperationVersion(
                operation_vid=9100,
                operation_id=100,
                expression=(
                    f"{{t{HOME_TABLE}, r0020, c{COLUMN}}} <- "
                    f"{{t{DEP_TABLE}, r0010, c{COLUMN}}}"
                ),
                start_release_id=self.EARLIER,
                end_release_id=RELEASE,
            )
        )
        session.add(OperationOutput(operation_vid=9100, module_vid=1))
        session.commit()

    def test_a_superseded_version_is_not_exported(self, calc_session):
        """``OperationOutput`` links every version, not just the current one.

        Unwindowed, the closed version comes back beside its successor
        and the two assign the same cell -- which the duplicate-output
        check rejects, aborting the module's export outright.
        """
        self._supersede(calc_session)

        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        assert ns["calculations"]["operation_codes"] == ["c_0001", "c_0002"]

    def test_the_operations_are_read_in_a_stable_order(self, calc_session):
        """Row order decides the script, so it cannot be left to the join."""
        from dpmcore.services.calculations_export.queries import (
            get_calculations,
        )

        rows = get_calculations(calc_session, 1, RELEASE)

        assert [row["operation_vid"] for row in rows] == [100, 101]


class TestDependencyScope:
    def test_the_assigned_cell_is_not_a_dependency(self, calc_session):
        """What a calculation writes is not something it reads.

        ``ASTTemplate`` visits a ``PersistentAssignment``'s target, so
        without an override the home table is collected as a dependency
        of the calculation that writes into it.
        """
        from dpmcore.services.calculations_export.visitors import (
            DependencyTableExtractor,
        )

        script = (
            f"{{t{HOME_TABLE}, r0030, c{COLUMN}}} <- "
            f"{{t{DEP_TABLE}, r0010, c{COLUMN}}} + 1;"
        )
        ast = SyntaxService().parse(script)
        CalculationsOperandsChecking(
            calc_session,
            script,
            ast,
            RELEASE,
            is_scripting=True,
            live_table_versions=True,
        )

        extractor = DependencyTableExtractor(calc_session, RELEASE)
        extractor.visit(ast)

        assert set(extractor.tables) == {DEP_TABLE}


class TestDraftModuleVersion:
    """A module version living in a working release is still exportable."""

    WORKING = 8003

    def test_the_calculations_survive_the_working_release(
        self, calc_session, caplog
    ):
        """The URI substitution is unreachable if the export empties first.

        ``get_calculations`` used to re-gate the module version it was
        handed, which rejects exactly the module versions
        ``get_module_uri`` substitutes a published release for -- so the
        substitution reported a release for an export that then failed
        with "no calculations".
        """
        calc_session.add(
            Release(
                release_id=self.WORKING,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            )
        )
        calc_session.query(ModuleVersion).filter(
            ModuleVersion.module_vid == 1
        ).update({ModuleVersion.start_release_id: self.WORKING})
        calc_session.commit()

        with caplog.at_level("WARNING"):
            export = ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )

        (uri,) = export
        assert uri.endswith("/calcfw/8.1/mod/calc_home")
        assert "working release" in caplog.text
        assert _namespace(export)["calculations"]["operation_codes"] == [
            "c_0001",
            "c_0002",
        ]


class TestFailureModes:
    def test_unknown_module_is_reported(self, calc_session):
        with pytest.raises(NotFound, match="Module version not found"):
            ASTGeneratorService(calc_session).calculations_for_module(
                "NOPE", REFERENCE_DATE
            )

    def test_module_without_calculations_is_reported(self, calc_session):
        with pytest.raises(NotFound, match="No calculations for module"):
            ASTGeneratorService(calc_session).calculations_for_module(
                DEP_MODULE, REFERENCE_DATE
            )

    def test_a_database_without_operation_output_is_reported(
        self, calc_session
    ):
        """Every other lookup succeeds; only the link table is absent."""
        calc_session.execute(text("DROP TABLE OperationOutput"))
        calc_session.commit()

        with pytest.raises(
            ConfigurationError, match="OperationOutput table missing"
        ):
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE
            )

    def test_without_a_session_the_service_says_so(self):
        with pytest.raises(ValueError, match="No database session"):
            ASTGeneratorService().calculations_for_module(
                HOME_MODULE, REFERENCE_DATE
            )


class TestVariableOutputs:
    """A statement may produce a calculation variable instead of a cell."""

    @pytest.fixture
    def variable_session(self, calc_session):
        """One calculation writing to the variable ``VR_1``."""
        calc_session.add(
            VariableVersion(
                variable_vid=77001,
                variable_id=77,
                property_id=1,
                code="VR_1",
                start_release_id=RELEASE,
                end_release_id=None,
            )
        )
        calc_session.query(OperationVersion).filter(
            OperationVersion.operation_vid == 101
        ).delete()
        calc_session.query(OperationOutput).filter(
            OperationOutput.operation_vid == 101
        ).delete()
        calc_session.query(OperationVersion).filter(
            OperationVersion.operation_vid == 100
        ).update(
            {
                OperationVersion.expression: (
                    f"{{vVR_1}} <- {{t{DEP_TABLE}, r0010, c{COLUMN}}} + 1"
                )
            }
        )
        calc_session.commit()
        return calc_session

    def test_the_variable_is_reported_by_its_version_id(
        self, variable_session
    ):
        ns = _namespace(
            ASTGeneratorService(variable_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        # Resolved to the VariableVID, which is what the output tables
        # are keyed by.
        assert ns["output_variables"] == {"77001": "m"}

    def test_a_single_calculation_needs_no_reordering(self, variable_session):
        ns = _namespace(
            ASTGeneratorService(variable_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        assert ns["calculations"]["operation_codes"] == ["c_0001"]
        assert len(ns["calculations"]["ast"]["children"]) == 1

    def test_an_unresolvable_variable_is_left_out(self, variable_session):
        variable_session.query(VariableVersion).filter(
            VariableVersion.code == "VR_1"
        ).delete()
        variable_session.commit()

        ns = _namespace(
            ASTGeneratorService(variable_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        assert ns["output_variables"] == {}

    def test_the_variable_carries_its_own_data_type(self, variable_session):
        """Looked up by version id -- by datapoint id it matches nothing."""
        variable_session.add(DataType(data_type_id=2, code="p"))
        variable_session.add(
            Property(property_id=2, data_type_id=2, is_metric=True)
        )
        variable_session.query(VariableVersion).filter(
            VariableVersion.variable_vid == 77001
        ).update({VariableVersion.property_id: 2})
        variable_session.commit()

        ns = _namespace(
            ASTGeneratorService(variable_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        assert ns["output_variables"] == {"77001": "p"}


class TestModuleUri:
    def test_a_module_with_no_release_cannot_be_keyed(self, calc_session):
        """The URI keys the document, so a missing part is fatal."""
        calc_session.query(ModuleVersion).filter(
            ModuleVersion.module_vid == 1
        ).update({ModuleVersion.start_release_id: None})
        calc_session.commit()

        with pytest.raises(NotFound, match="Module URI not resolvable"):
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE
            )


@pytest.mark.integration
class TestWorkingReleaseUri:
    """A draft release must not key an exported taxonomy URI.

    ``filter_by_release`` already keeps a correctly-typed working
    release out of a published export, so this only bites when the
    export itself is keyed at one -- exporting the draft dictionary.
    """

    WORKING = 8003

    def _seed(self, session):
        session.add_all(
            [
                Release(release_id=RELEASE, code="8.0", date=date(2025, 1, 1)),
                Release(release_id=LATER, code="8.1", date=date(2026, 1, 1)),
                # Dated, but typed as the working dictionary: it sorts as
                # the latest whatever its date says.
                Release(
                    release_id=self.WORKING,
                    code="Playground",
                    date=date(1970, 1, 1),
                    type="playground",
                ),
                Framework(framework_id=1, code="CALC_FW"),
                Module(module_id=1, framework_id=1),
            ]
        )
        session.add(
            ModuleVersion(
                module_vid=1,
                module_id=1,
                code=HOME_MODULE,
                version_number="1.0.0",
                from_reference_date=date(2026, 1, 1),
                to_reference_date=date(2026, 12, 31),
                start_release_id=self.WORKING,
                end_release_id=None,
            )
        )
        session.commit()

    def test_a_working_release_is_replaced_by_the_published_one(
        self, memory_session, caplog
    ):
        from dpmcore.services.calculations_export.queries import (
            get_module_uri,
        )

        self._seed(memory_session)

        with caplog.at_level("WARNING"):
            uri, _ = get_module_uri(memory_session, 1, self.WORKING)

        # 8.1 is the newest published release; "Playground" never
        # reaches the URI.
        assert uri.endswith("/calc_fw/8.1/mod/calc_home")
        assert "Playground" not in uri
        # Substituting silently would hide that the exported content is
        # still the working version's.
        assert "working release" in caplog.text
        assert "Playground" in caplog.text

    def test_a_published_release_is_left_alone(self, memory_session, caplog):
        from dpmcore.services.calculations_export.queries import (
            get_module_uri,
        )

        self._seed(memory_session)
        memory_session.query(ModuleVersion).filter(
            ModuleVersion.module_vid == 1
        ).update({ModuleVersion.start_release_id: RELEASE})
        memory_session.commit()

        with caplog.at_level("WARNING"):
            uri, _ = get_module_uri(memory_session, 1, RELEASE)

        assert uri.endswith("/calc_fw/8.0/mod/calc_home")
        assert caplog.text == ""
