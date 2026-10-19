"""End-to-end tests for the calculations export service.

Seeds a minimal DPM dictionary -- one framework, two modules, three
tables, and two calculation operations linked through
``OperationOutput`` -- and exercises
``ASTGeneratorService.calculations_for_module`` /
``calculations_datapoints`` over it.

The export is a downstream contract, so the assertions are about its
*shape*: the namespace key, the operation codes paired with the right
statements, the resolved output variables and tables, and the
``modules`` section describing the module versions the calculations
read from.
"""

from __future__ import annotations

import re
from datetime import date

import pytest
from sqlalchemy import text

from dpmcore.errors import (
    ConfigurationError,
    NotFound,
    SemanticError,
)
from dpmcore.orm.glossary import Item, ItemCategory, Property
from dpmcore.orm.infrastructure import DataType, Organisation, Release
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
EARLIER = 7001
WORKING = 8003

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
            Release(release_id=EARLIER, code="7.0", date=date(2024, 1, 1)),
            Release(release_id=RELEASE, code="8.0", date=date(2025, 1, 1)),
            Release(release_id=LATER, code="8.1", date=date(2026, 1, 1)),
            DataType(data_type_id=1, code="m"),
            Property(property_id=1, data_type_id=1, is_metric=True),
            Organisation(org_id=1, name="Banking authority", acronym="EBA"),
            Organisation(org_id=2, name="Central bank", acronym="ECB"),
            Framework(framework_id=1, code="CALCFW"),
            Module(module_id=1, framework_id=1, owner_id=1),
            Module(module_id=2, framework_id=1, owner_id=1),
        ]
    )


def _seed_module_version(
    session,
    *,
    module_vid,
    module_id,
    code,
    number="1.0.0",
    start=date(2026, 1, 1),
    end=date(2026, 12, 31),
    release=RELEASE,
):
    """A module version; by default one whose window covers the test date."""
    session.add(
        ModuleVersion(
            module_vid=module_vid,
            module_id=module_id,
            code=code,
            version_number=number,
            from_reference_date=start,
            to_reference_date=end,
            start_release_id=release,
            end_release_id=None,
        )
    )


def _seed_table(
    session, *, table_id, table_vid, module_vid, code, release=RELEASE
):
    """A table with one column and three rows of cells, and one version.

    Its ids follow the TableID ``n``: the headers are ``n00`` (the
    column) and ``n01`` to ``n03`` (the rows), and the cell of row ``i``
    is ``nn0i`` and holds the Variable ``nn00i``, so 11001 is the first
    row of table 1.
    """
    session.add(Table(table_id=table_id))
    column_header_id = table_id * 100
    session.add(Header(header_id=column_header_id, direction="X", is_key=True))
    session.add(
        HeaderVersion(
            header_vid=column_header_id,
            header_id=column_header_id,
            code=COLUMN,
        )
    )
    for index, row_code in enumerate(ROWS, start=1):
        header_id = table_id * 100 + index
        variable_vid = table_id * 11000 + index
        session.add(Header(header_id=header_id, direction="Y", is_key=True))
        session.add(
            HeaderVersion(
                header_vid=header_id, header_id=header_id, code=row_code
            )
        )
        session.add(
            Cell(
                cell_id=table_id * 1100 + index,
                table_id=table_id,
                row_id=header_id,
                column_id=column_header_id,
            )
        )
        session.add(Variable(variable_id=variable_vid))
        session.add(
            VariableVersion(
                variable_vid=variable_vid,
                variable_id=variable_vid,
                property_id=1,
                code=f"V{variable_vid}",
                start_release_id=release,
                end_release_id=None,
            )
        )
    _seed_table_version(
        session,
        table_vid=table_vid,
        table_id=table_id,
        code=code,
        module_vid=module_vid,
        rows=range(1, len(ROWS) + 1),
        release=release,
    )


def _seed_table_version(
    session, *, table_vid, table_id, code, module_vid, rows, release=RELEASE
):
    """A version of a table of ``_seed_table``, holding the cells of ``rows``.

    ``rows`` are 1-based positions in ``ROWS``. The cells are the
    table's own, so a Variable keeps its id across the versions. A
    version of ``EARLIER`` ends where ``RELEASE`` starts.
    """
    session.add(
        TableVersion(
            table_vid=table_vid,
            table_id=table_id,
            code=code,
            start_release_id=release,
            end_release_id=RELEASE if release == EARLIER else None,
        )
    )
    session.add(
        ModuleVersionComposition(
            module_vid=module_vid, table_vid=table_vid, table_id=table_id
        )
    )
    column_header_id = table_id * 100
    session.add(
        TableVersionHeader(
            table_vid=table_vid,
            header_id=column_header_id,
            header_vid=column_header_id,
            order=1,
        )
    )
    for index in rows:
        header_id = table_id * 100 + index
        session.add(
            TableVersionHeader(
                table_vid=table_vid,
                header_id=header_id,
                header_vid=header_id,
                order=index,
            )
        )
        session.add(
            TableVersionCell(
                table_vid=table_vid,
                cell_id=table_id * 1100 + index,
                cell_code=f"{{{code}, r{ROWS[index - 1]}, c{COLUMN}}}",
                variable_vid=table_id * 11000 + index,
                is_nullable=True,
                is_void=False,
                is_excluded=False,
            )
        )


def _seed_open_key(session, *, header_id, table_id, property_id, table_vids):
    """An open-key header on ``table_vids``, keyed by ``property_id``."""
    session.add(
        Header(
            header_id=header_id,
            table_id=table_id,
            direction="Y",
            is_key=True,
        )
    )
    session.add(
        HeaderVersion(
            header_vid=header_id, header_id=header_id, property_id=property_id
        )
    )
    for table_vid in table_vids:
        session.add(
            TableVersionHeader(
                table_vid=table_vid,
                header_id=header_id,
                header_vid=header_id,
                order=99,
            )
        )


def _seed_key_property(session, property_id, *codes):
    """A key property named ``codes[0]`` at EARLIER, ``codes[-1]`` after."""
    session.add(Item(item_id=property_id))
    session.add(Property(property_id=property_id, data_type_id=1))
    session.add(
        ItemCategory(
            item_id=property_id,
            start_release_id=EARLIER,
            end_release_id=RELEASE if len(codes) > 1 else None,
            code=codes[0],
        )
    )
    if len(codes) > 1:
        session.add(
            ItemCategory(
                item_id=property_id,
                start_release_id=RELEASE,
                end_release_id=None,
                code=codes[1],
            )
        )


def _seed_operation(session, *, operation_id, module_vid, code, expression):
    """A calculation operation writing into ``module_vid``."""
    session.add(
        Operation(
            operation_id=operation_id,
            code=code,
            type="calculation",
            owner_id=2,
        )
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


def _set_expression(session, operation_vid, expression):
    session.query(OperationVersion).filter(
        OperationVersion.operation_vid == operation_vid
    ).update({OperationVersion.expression: expression})
    session.commit()


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
    """The datapoint caches are keyed per engine, not per test.

    Every in-memory SQLite engine shares one cache key, so an entry left
    by an earlier test module would be served to the first test here.
    Cleared on both sides of the yield for that reason.

    All four of them: the cell frame and the module membership sit
    *underneath* the table-data and axis caches, so clearing only those
    two leaves the earlier module's cells to be served again.
    """
    from dpmcore.dpm_xl.model_queries import ViewDatapointsQuery

    ViewDatapointsQuery._TABLE_DATA_CACHE.clear()
    ViewDatapointsQuery._AXIS_ORDER_CACHE.clear()
    ViewDatapointsQuery._CELL_FRAME_CACHE.clear()
    ViewDatapointsQuery._MEMBERSHIP_CACHE.clear()
    yield
    ViewDatapointsQuery._TABLE_DATA_CACHE.clear()
    ViewDatapointsQuery._AXIS_ORDER_CACHE.clear()
    ViewDatapointsQuery._CELL_FRAME_CACHE.clear()
    ViewDatapointsQuery._MEMBERSHIP_CACHE.clear()


def _namespace(export):
    """The export, the module object itself."""
    assert "module_uri" in export
    return export


class TestCalculationsForModule:
    def test_the_module_uri_is_a_member_not_the_key(self, calc_session):
        export = ASTGeneratorService(calc_session).calculations_for_module(
            HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
        )

        uri = export["module_uri"]
        assert uri == (
            "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/calcfw/8.0/"
            "mod/calc_home"
        )
        assert uri not in export

    def test_module_block(self, calc_session):
        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        assert list(ns) == [
            "owner",
            "module_code",
            "module_version",
            "module_owner",
            "module_uri",
            "format_version",
            "dpm_release",
            "dates",
            "calculations",
            "output_variables",
            "output_tables",
            "modules",
        ]
        assert ns["owner"] == "ECB"
        assert ns["module_code"] == HOME_MODULE
        assert ns["module_version"] == "1.0.0"
        assert ns["module_owner"] == "EBA"
        assert ns["format_version"] == "2.0"
        assert "framework_code" not in ns
        assert "dependency_modules" not in ns
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

    def test_modules_hold_the_dependency_and_the_home_module(
        self, calc_session
    ):
        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        assert list(ns["modules"]) == [DEP_MODULE, HOME_MODULE]
        (dep,) = ns["modules"][DEP_MODULE]["versions"]
        assert dep == {
            "version": "1.0.0",
            "URI": (
                "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/calcfw/8.0/"
                "mod/calc_dep"
            ),
            "from": "2026-01-01",
            "to": "2026-12-31",
            "tables": {
                DEP_TABLE: {
                    "variables": {
                        "22001": {
                            "data_type": "m",
                            "cells": [{"row": "0010", "column": COLUMN}],
                        }
                    },
                    "open_keys": {},
                }
            },
        }

    def test_the_home_version_lists_every_table_and_variable(
        self, calc_session
    ):
        export = ASTGeneratorService(calc_session).calculations_for_module(
            HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
        )
        ns = _namespace(export)

        (home,) = ns["modules"][HOME_MODULE]["versions"]
        assert home["URI"] == export["module_uri"]
        assert list(home["tables"]) == [HOME_TABLE]
        # Every cell of the module, not only the ones written or read.
        assert home["tables"][HOME_TABLE]["variables"] == {
            str(11000 + row): {
                "data_type": "m",
                "cells": [{"row": code, "column": COLUMN}],
            }
            for row, code in enumerate(ROWS, start=1)
        }
        assert "not_evaluable" not in home

    def test_a_table_without_variables_is_left_out(self, calc_session):
        """An abstract table has no cells, so nothing to describe."""
        calc_session.add(Table(table_id=3, is_abstract=True))
        calc_session.add(
            TableVersion(
                table_vid=31,
                table_id=3,
                code="C_00.00",
                start_release_id=RELEASE,
                end_release_id=None,
            )
        )
        calc_session.add(
            ModuleVersionComposition(module_vid=1, table_vid=31, table_id=3)
        )
        calc_session.commit()

        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        (home,) = ns["modules"][HOME_MODULE]["versions"]
        assert list(home["tables"]) == [HOME_TABLE]

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

        (dep,) = ns["modules"][DEP_MODULE]["versions"]
        variables = dep["tables"][DEP_TABLE]["variables"]
        assert variables["22001"]["data_type"] == "p"
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


class TestWithExpressions:
    EXPRESSION = (
        f"{{t{HOME_TABLE}, r0020, c{COLUMN}}} <- "
        f"with {{t{DEP_TABLE}, c{COLUMN}}}: {{r0010}} + 1"
    )

    def test_a_with_context_reaches_the_dependency_tables(self, calc_session):
        """The context has to be grafted before dependencies are collected."""
        _set_expression(calc_session, 100, self.EXPRESSION)

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
        (dep,) = ns["modules"][DEP_MODULE]["versions"]
        assert dep["URI"].endswith("/mod/calc_dep")
        tables = dep["tables"]
        assert set(tables) == {DEP_TABLE}
        assert list(tables[DEP_TABLE]["variables"]) == ["22001"]

    def test_the_operand_resolves_to_the_context_table(self, calc_session):
        _set_expression(calc_session, 100, self.EXPRESSION)

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
        _set_expression(calc_session, 100, self.EXPRESSION)

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


class TestDependencyOrderBeforeOperandChecking:
    """The script is sorted before its operands are resolved."""

    def test_an_operation_assigned_by_a_later_version_is_found(
        self, calc_session
    ):
        """``{oX}`` read by c_0001 (VID 100), assigned by VID 101."""
        _set_expression(
            calc_session,
            100,
            f"{{t{HOME_TABLE}, r0020, c{COLUMN}}} <- {{oX}} + 1",
        )
        _set_expression(
            calc_session,
            101,
            f"X := {{t{DEP_TABLE}, r0010, c{COLUMN}}} * 2",
        )

        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        assert ns["calculations"]["operation_codes"] == ["c_0002", "c_0001"]
        # The statements move with their codes
        assign_x, read_x = ns["calculations"]["ast"]["children"]
        assert assign_x["class_name"] == "TemporaryAssignment"
        assert assign_x["left"]["value"] == "X"
        assert read_x["class_name"] == "PersistentAssignment"
        assert read_x["left"]["row"] == "0020"

    def test_a_cell_read_through_a_with_context_is_ordered(self, calc_session):
        """c_0002 reads c_0001's output only through its ``with``."""
        _set_expression(
            calc_session,
            101,
            f"{{t{HOME_TABLE}, r0030, c{COLUMN}}} <- "
            f"with {{t{HOME_TABLE}, c{COLUMN}}}: {{r0020}} * 2",
        )

        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        assert ns["calculations"]["operation_codes"] == ["c_0001", "c_0002"]

    @pytest.mark.parametrize(
        "selection", ["r0020-0030", "(r0020, r0030)", "r*"]
    )
    def test_a_cell_read_inside_a_selection_is_ordered(
        self, calc_session, selection
    ):
        """c_0001 reads c_0002's output r0030 only within a selection."""
        _set_expression(
            calc_session,
            100,
            f"{{t{HOME_TABLE}, r0010, c{COLUMN}}} <- "
            f"sum({{t{HOME_TABLE}, {selection}, c{COLUMN}}})",
        )

        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        assert ns["calculations"]["operation_codes"] == ["c_0002", "c_0001"]


class TestDependencyErrors:
    def test_a_cycle_is_reported_by_its_operation_codes(self, calc_session):
        """c_0001 and c_0002 each read the cell the other writes."""
        _set_expression(
            calc_session,
            100,
            f"{{t{HOME_TABLE}, r0020, c{COLUMN}}} <- "
            f"{{t{HOME_TABLE}, r0030, c{COLUMN}}} + 1",
        )

        with pytest.raises(
            SemanticError,
            match=re.escape(
                "Circular reference between operations c_0001 and c_0002."
            ),
        ):
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )

    def test_a_cell_written_inside_a_range_is_an_overwrite(self, calc_session):
        """c_0002 writes r0020-0030, c_0001 writes r0020 on its own."""
        _set_expression(
            calc_session,
            101,
            f"{{t{HOME_TABLE}, r0020-0030, c{COLUMN}}} <- 1",
        )

        with pytest.raises(
            SemanticError,
            match=re.escape(
                "Overwriting a variable is not allowed, trying it with "
                f"{{{HOME_TABLE}, r0020, c{COLUMN}}}."
            ),
        ):
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )


class TestOperationVersionWindow:
    """Only the operation version effective at the export's release."""

    def _supersede(self, session):
        """Give operation 100 an older, already-closed version."""
        session.add(
            OperationVersion(
                operation_vid=9100,
                operation_id=100,
                expression=(
                    f"{{t{HOME_TABLE}, r0020, c{COLUMN}}} <- "
                    f"{{t{DEP_TABLE}, r0010, c{COLUMN}}}"
                ),
                start_release_id=EARLIER,
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

        extractor = DependencyTableExtractor(calc_session)
        extractor.visit(ast)

        assert {read.table for read in extractor.reads} == {DEP_TABLE}


class TestDraftModuleVersion:
    """A module version living in a working release is still exportable."""

    def test_the_calculations_survive_the_working_release(
        self, calc_session, caplog
    ):
        """A working-release export must not empty itself out.

        ``get_calculations`` used to re-gate the module version it was
        handed, which rejects exactly the module versions that live in a
        working release -- so the export warned about one and then
        failed with "no calculations".
        """
        calc_session.add(
            Release(
                release_id=WORKING,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            )
        )
        calc_session.query(ModuleVersion).filter(
            ModuleVersion.module_vid == 1
        ).update({ModuleVersion.start_release_id: WORKING})
        calc_session.commit()

        with caplog.at_level("WARNING"):
            export = ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )

        assert export["module_uri"].endswith(
            "/calcfw/Playground/mod/calc_home"
        )
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
    def test_a_module_with_no_release_has_no_uri(self, calc_session):
        """The URI names the export, so a missing part is fatal."""
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

    def _seed(self, session):
        session.add_all(
            [
                Release(release_id=RELEASE, code="8.0", date=date(2025, 1, 1)),
                Release(release_id=LATER, code="8.1", date=date(2026, 1, 1)),
                # Dated, but typed as the working dictionary: it sorts as
                # the latest whatever its date says.
                Release(
                    release_id=WORKING,
                    code="Playground",
                    date=date(1970, 1, 1),
                    type="playground",
                ),
                Framework(framework_id=1, code="CALC_FW"),
                Module(module_id=1, framework_id=1),
            ]
        )
        _seed_module_version(
            session,
            module_vid=1,
            module_id=1,
            code=HOME_MODULE,
            release=WORKING,
        )
        session.commit()

    def test_a_working_release_keys_the_uri_and_warns(
        self, memory_session, caplog
    ):
        from dpmcore.services.calculations_export.queries import (
            get_module_uri,
        )

        self._seed(memory_session)

        with caplog.at_level("WARNING"):
            uri, _ = get_module_uri(memory_session, 1)

        # Reported verbatim: a consumer matches an instance by its module
        # URI, so substituting a published code repoints it.
        assert uri.endswith("/calc_fw/Playground/mod/calc_home")
        # Silence would hide that the URI does not resolve against a
        # published taxonomy.
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
            uri, _ = get_module_uri(memory_session, 1)

        assert uri.endswith("/calc_fw/8.0/mod/calc_home")
        assert caplog.text == ""


class TestModuleVersions:
    """``modules`` lists every version a read can land in.

    ``CALC_DEP`` gets an earlier version (``0.9.0``, release ``7.0``,
    2025) whose ``C_98.00`` holds the cell at r0010 under the same
    ``VariableID`` but not the one at r0020, and ``c_0003`` reads both
    cells a year back.
    """

    DEP_URI = (
        "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/calcfw/{}/mod/calc_dep"
    )

    @pytest.fixture
    def shifted_session(self, calc_session):
        session = calc_session
        _seed_module_version(
            session,
            module_vid=3,
            module_id=2,
            code=DEP_MODULE,
            number="0.9.0",
            start=date(2025, 1, 1),
            end=date(2025, 12, 31),
            release=EARLIER,
        )
        _seed_table_version(
            session,
            table_vid=21,
            table_id=2,
            code=DEP_TABLE,
            module_vid=3,
            rows=[1],
            release=EARLIER,
        )
        _seed_operation(
            session,
            operation_id=102,
            module_vid=1,
            code="c_0003",
            expression=(
                f"{{t{HOME_TABLE}, r0010, c{COLUMN}}} <- "
                f"time_shift({{t{DEP_TABLE}, r0010, c{COLUMN}}}, A, 1) + "
                f"time_shift({{t{DEP_TABLE}, r0020, c{COLUMN}}}, A, 1)"
            ),
        )
        session.commit()
        return session

    def _versions(self, session, module=DEP_MODULE):
        ns = _namespace(
            ASTGeneratorService(session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )
        return ns["modules"][module]["versions"]

    def test_a_dependency_read_only_at_t_has_one_version(self, calc_session):
        assert [v["version"] for v in self._versions(calc_session)] == [
            "1.0.0"
        ]

    def test_a_read_a_year_back_reaches_the_predecessor(self, shifted_session):
        versions = self._versions(shifted_session)

        assert [
            (v["version"], v["URI"], v["from"], v["to"]) for v in versions
        ] == [
            ("0.9.0", self.DEP_URI.format("7.0"), "2025-01-01", "2025-12-31"),
            ("1.0.0", self.DEP_URI.format("8.0"), "2026-01-01", "2026-12-31"),
        ]

    def test_each_version_lists_what_lands_in_it(self, shifted_session):
        older, current = self._versions(shifted_session)

        # c_0003's reads land in 0.9.0, which has no cell for r0020.
        assert list(older["tables"][DEP_TABLE]["variables"]) == ["22001"]
        # Only c_0001's read at T lands in 1.0.0.
        assert list(current["tables"][DEP_TABLE]["variables"]) == ["22001"]

    def test_a_version_missing_a_variable_cannot_serve_its_reader(
        self, shifted_session
    ):
        older, current = self._versions(shifted_session)

        assert older["not_evaluable"] == ["c_0003"]
        assert "not_evaluable" not in current

    def test_a_version_out_of_reach_is_not_listed(self, shifted_session):
        """A year back from 2026 never reaches 2024, nor a ghost."""
        shifted_session.add_all(
            [
                Release(release_id=7000, code="6.0", date=date(2023, 1, 1)),
                Release(release_id=7002, code="7.1", date=date(2024, 6, 1)),
            ]
        )
        _seed_module_version(
            shifted_session,
            module_vid=4,
            module_id=2,
            code=DEP_MODULE,
            number="0.8.0",
            start=date(2024, 1, 1),
            end=date(2024, 12, 31),
            release=7000,
        )
        _seed_module_version(
            shifted_session,
            module_vid=5,
            module_id=2,
            code=DEP_MODULE,
            number="0.9.1",
            start=date(2025, 6, 30),
            end=date(2025, 6, 30),
            release=7002,
        )
        shifted_session.commit()

        versions = self._versions(shifted_session)

        assert [v["version"] for v in versions] == ["0.9.0", "1.0.0"]
        assert versions[0]["to"] == "2025-12-31"

    def test_a_successor_in_the_window_is_listed(self, calc_session):
        _seed_module_version(
            calc_session,
            module_vid=6,
            module_id=2,
            code=DEP_MODULE,
            number="1.1.0",
            start=date(2026, 7, 1),
            end=None,
            release=LATER,
        )
        _seed_table_version(
            calc_session,
            table_vid=23,
            table_id=2,
            code=DEP_TABLE,
            module_vid=6,
            rows=[1, 2, 3],
            release=LATER,
        )
        calc_session.commit()

        versions = self._versions(calc_session)

        assert [
            (v["version"], v["URI"], v["from"], v["to"]) for v in versions
        ] == [
            ("1.0.0", self.DEP_URI.format("8.0"), "2026-01-01", "2026-06-30"),
            ("1.1.0", self.DEP_URI.format("8.1"), "2026-07-01", None),
        ]
        assert "not_evaluable" not in versions[1]

    def _seed_draft_successor(self, session):
        """A ``CALC_DEP`` 1.1.0 from 2026-07-01 in the working release."""
        session.add(
            Release(
                release_id=WORKING,
                code="Playground",
                date=date(1970, 1, 1),
                type="playground",
            )
        )
        _seed_module_version(
            session,
            module_vid=6,
            module_id=2,
            code=DEP_MODULE,
            number="1.1.0",
            start=date(2026, 7, 1),
            end=None,
            release=WORKING,
        )
        session.commit()

    def test_a_working_release_version_is_not_listed(self, calc_session):
        """It was never published: it neither shows nor cuts a window."""
        self._seed_draft_successor(calc_session)

        versions = self._versions(calc_session)

        assert [(v["version"], v["to"]) for v in versions] == [
            ("1.0.0", "2026-12-31")
        ]

    def test_a_draft_export_lists_working_release_versions(self, calc_session):
        self._seed_draft_successor(calc_session)

        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE, "Playground"
            )
        )

        assert [
            (v["version"], v["from"], v["to"])
            for v in ns["modules"][DEP_MODULE]["versions"]
        ] == [
            ("1.0.0", "2026-01-01", "2026-06-30"),
            ("1.1.0", "2026-07-01", None),
        ]

    def _end_in_working_release(self, session, module_vid, end):
        """End a version as a working release does, in its own row."""
        session.query(ModuleVersion).filter(
            ModuleVersion.module_vid == module_vid
        ).update(
            {
                ModuleVersion.to_reference_date: end,
                ModuleVersion.end_release_id: WORKING,
            }
        )
        session.commit()

    @pytest.mark.parametrize(
        "end",
        [
            date(2026, 6, 30),
            # A working-release patch from the same date inverts it.
            date(2025, 12, 31),
        ],
    )
    def test_a_version_a_working_release_ended_is_read_as_published(
        self, calc_session, end
    ):
        self._seed_draft_successor(calc_session)
        self._end_in_working_release(calc_session, 2, end)

        versions = self._versions(calc_session)

        assert [(v["version"], v["from"], v["to"]) for v in versions] == [
            ("1.0.0", "2026-01-01", None)
        ]

    def test_the_own_dates_are_read_as_published(self, calc_session):
        self._seed_draft_successor(calc_session)
        self._end_in_working_release(calc_session, 1, date(2026, 9, 30))
        service = ASTGeneratorService(calc_session)

        published = _namespace(
            service.calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )
        draft = _namespace(
            service.calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE, "Playground"
            )
        )

        assert published["dates"] == {"from": "2026-01-01", "to": None}
        (own,) = published["modules"][HOME_MODULE]["versions"]
        assert own["to"] is None
        assert draft["dates"] == {"from": "2026-01-01", "to": "2026-09-30"}

    def _move_dependency(self, session, start, end):
        session.query(ModuleVersion).filter(
            ModuleVersion.module_vid == 2
        ).update(
            {
                ModuleVersion.from_reference_date: start,
                ModuleVersion.to_reference_date: end,
            }
        )
        session.commit()

    def test_a_dependency_off_the_dates_read_keeps_its_version(
        self, calc_session, caplog
    ):
        """No version covers the dates read: the one the table was
        resolved in still describes it.
        """
        self._move_dependency(
            calc_session, date(2025, 1, 1), date(2025, 12, 31)
        )

        with caplog.at_level("WARNING"):
            versions = self._versions(calc_session)

        assert [(v["version"], v["to"]) for v in versions] == [
            ("1.0.0", "2025-12-31")
        ]
        assert "covers a date its reads land on" in caplog.text

    def test_a_ghost_is_never_listed(self, calc_session, caplog):
        """Not even when it is the only version the table was found in."""
        self._move_dependency(
            calc_session, date(2025, 6, 30), date(2025, 6, 30)
        )

        with caplog.at_level("WARNING"):
            ns = _namespace(
                ASTGeneratorService(calc_session).calculations_for_module(
                    HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
                )
            )

        assert DEP_MODULE not in ns["modules"]
        assert "has no version to list" in caplog.text

    def test_open_keys_are_compared_by_property(self, shifted_session):
        """``SIC`` renamed ``qSIC`` is the same key: nothing changes."""
        _seed_key_property(shifted_session, 50, "SIC", "qSIC")
        _seed_open_key(
            shifted_session,
            header_id=290,
            table_id=2,
            property_id=50,
            table_vids=[21, 22],
        )
        _set_expression(
            shifted_session,
            102,
            f"{{t{HOME_TABLE}, r0010, c{COLUMN}}} <- "
            f"time_shift({{t{DEP_TABLE}, r0010, c{COLUMN}}}, A, 1)",
        )

        older, current = self._versions(shifted_session)

        assert "not_evaluable" not in older
        # Each version names the key as its own release does.
        assert older["tables"][DEP_TABLE]["open_keys"] == {"SIC": "m"}
        assert current["tables"][DEP_TABLE]["open_keys"] == {"qSIC": "m"}

    def test_a_different_open_key_cannot_serve_the_reader(
        self, shifted_session
    ):
        _seed_key_property(shifted_session, 50, "qSIC")
        _seed_key_property(shifted_session, 51, "qEGS")
        _seed_open_key(
            shifted_session,
            header_id=290,
            table_id=2,
            property_id=50,
            table_vids=[22],
        )
        _seed_open_key(
            shifted_session,
            header_id=291,
            table_id=2,
            property_id=51,
            table_vids=[21],
        )
        _set_expression(
            shifted_session,
            102,
            f"{{t{HOME_TABLE}, r0010, c{COLUMN}}} <- "
            f"time_shift({{t{DEP_TABLE}, r0010, c{COLUMN}}}, A, 1)",
        )

        older, _ = self._versions(shifted_session)

        assert older["not_evaluable"] == ["c_0003"]

    def test_a_shifted_read_of_the_home_module_reaches_its_predecessor(
        self, calc_session
    ):
        _seed_module_version(
            calc_session,
            module_vid=7,
            module_id=1,
            code=HOME_MODULE,
            number="0.9.0",
            start=date(2025, 1, 1),
            end=date(2025, 12, 31),
            release=EARLIER,
        )
        _seed_table_version(
            calc_session,
            table_vid=12,
            table_id=1,
            code=HOME_TABLE,
            module_vid=7,
            rows=[2],
            release=EARLIER,
        )
        _seed_operation(
            calc_session,
            operation_id=102,
            module_vid=1,
            code="c_0003",
            expression=(
                f"{{t{HOME_TABLE}, r0010, c{COLUMN}}} <- "
                f"time_shift({{t{HOME_TABLE}, r0020, c{COLUMN}}}, A, 1)"
            ),
        )
        calc_session.commit()

        older, own = self._versions(calc_session, HOME_MODULE)

        assert older["version"] == "0.9.0"
        assert older["URI"].endswith("/calcfw/7.0/mod/calc_home")
        assert list(older["tables"][HOME_TABLE]["variables"]) == ["11002"]
        assert "not_evaluable" not in older
        # The own version still describes every Variable of the module.
        assert len(own["tables"][HOME_TABLE]["variables"]) == len(ROWS)


class TestHomeTables:
    """A table of the home module is read from the home module."""

    @pytest.mark.parametrize(
        "read",
        [
            f"{{t{HOME_TABLE}, r0020, c{COLUMN}}}",
            # A month back lands in 2025-12..2026-11, inside CALC_DEP 1.0.0.
            f"time_shift({{t{HOME_TABLE}, r0020, c{COLUMN}}}, M, 1)",
        ],
    )
    def test_another_module_holding_it_is_no_alternative(
        self, calc_session, read
    ):
        """``CALC_DEP`` also holds ``C_99.00``: it gains nothing from it."""
        calc_session.add(
            ModuleVersionComposition(module_vid=2, table_vid=11, table_id=1)
        )
        _set_expression(
            calc_session, 101, f"{{t{HOME_TABLE}, r0030, c{COLUMN}}} <- {read}"
        )

        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        (dep,) = ns["modules"][DEP_MODULE]["versions"]
        assert list(dep["tables"]) == [DEP_TABLE]


class TestMovedVariable:
    def test_a_variable_moved_to_two_tables_is_listed_in_both(
        self, calc_session
    ):
        """In 0.9.0, 22001 sits in C_96.00 and C_97.00, not C_98.00.

        Both have the open keys of C_98.00 (none), so the read can be
        served from either, and both are listed.
        """
        _seed_module_version(
            calc_session,
            module_vid=3,
            module_id=2,
            code=DEP_MODULE,
            number="0.9.0",
            start=date(2025, 1, 1),
            end=date(2025, 12, 31),
            release=EARLIER,
        )
        for table_id, code in ((6, "C_96.00"), (7, "C_97.00")):
            _seed_table(
                calc_session,
                table_id=table_id,
                table_vid=table_id * 10 + 1,
                module_vid=3,
                code=code,
                release=EARLIER,
            )
        _seed_operation(
            calc_session,
            operation_id=102,
            module_vid=1,
            code="c_0003",
            expression=(
                f"{{t{HOME_TABLE}, r0010, c{COLUMN}}} <- "
                f"time_shift({{t{DEP_TABLE}, r0010, c{COLUMN}}}, A, 1)"
            ),
        )
        calc_session.commit()
        # Their r0010 holds 22001, the Variable at r0010 of C_98.00.
        calc_session.query(TableVersionCell).filter(
            TableVersionCell.table_vid.in_([61, 71]),
            TableVersionCell.cell_code.contains("r0010"),
        ).update(
            {TableVersionCell.variable_vid: 22001},
            synchronize_session="fetch",
        )
        calc_session.commit()

        ns = _namespace(
            ASTGeneratorService(calc_session).calculations_for_module(
                HOME_MODULE, REFERENCE_DATE, PUBLICATION_DATE
            )
        )

        older, _ = ns["modules"][DEP_MODULE]["versions"]
        assert {
            code: list(table["variables"])
            for code, table in older["tables"].items()
        } == {"C_96.00": ["22001"], "C_97.00": ["22001"]}
        assert "not_evaluable" not in older
