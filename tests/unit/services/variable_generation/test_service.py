"""Service-level tests on an in-memory SQLite database."""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from dpmcore.errors import Invalid, NotFound
from dpmcore.orm.base import Base
from dpmcore.orm.glossary import (
    Category,
    Context,
    ContextComposition,
    Item,
    Property,
)
from dpmcore.orm.infrastructure import DataType, Release
from dpmcore.orm.packaging import (
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
from dpmcore.services.model_validation import (
    SEVERITY_ERROR,
    Finding,
    ObjectRef,
)
from dpmcore.services.model_validation import registry as registry_mod
from dpmcore.services.model_validation.registry import rule
from dpmcore.services.variable_generation import (
    CellOutcome,
    GenerationStatus,
    VariableGenerationService,
)
from tests.unit.services.variable_generation.builders import CUR, PREV

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as sess:
        yield sess
    engine.dispose()


@pytest.fixture
def temp_rule():
    registered = []

    def factory(rule_id, findings):
        @rule(
            rule_id,
            legacy_code=rule_id,
            family="test",
            severity=SEVERITY_ERROR,
            description=f"Test rule {rule_id}",
        )
        def _fn(ctx):
            yield from findings

        registered.append(rule_id)
        return _fn

    yield factory
    for rule_id in registered:
        del registry_mod.REGISTRY[rule_id]


def _add_releases(session):
    session.add_all(
        [
            Release(
                release_id=PREV,
                code="PREVR",
                is_current=False,
                date=date(2024, 1, 1),
            ),
            Release(
                release_id=CUR,
                code="CURR",
                is_current=True,
                date=date(2025, 1, 1),
            ),
        ]
    )


def _seed_full_model(session):
    """Two current tables with one predecessor generation each.

    Expected outcomes: cell 1000 -> NEW_VARIABLE (its table gained a
    compound key), cell 2000 -> UNCHANGED, cell 2001 -> NEW_VERSION,
    cell 2002 -> NOT_REPORTABLE (void). Plus one proposed key
    variable, one compound key and two filing indicators.
    """
    _add_releases(session)
    session.add_all(
        [
            DataType(data_type_id=1, code="m"),
            Category(category_id=900, name="Templates", code="TE"),
            Item(item_id=800, name="Template", is_property=True),
            Item(item_id=801, name="isReported", is_property=True),
            Item(item_id=70, name="member"),
            Property(property_id=10, data_type_id=1),
            Property(property_id=11, data_type_id=1),
            Property(property_id=12, data_type_id=1),
            Property(property_id=13, data_type_id=1),
            Property(property_id=20, data_type_id=1),
            Context(context_id=40, signature="30_70#"),
            ContextComposition(
                context_id=40, property_id=30, item_id=70
            ),
            Module(module_id=1),
            ModuleVersion(
                module_vid=500,
                module_id=1,
                code="MOD1",
                start_release_id=CUR,
            ),
            Table(table_id=1, is_abstract=False),
            Table(table_id=2, is_abstract=False),
            TableVersion(
                table_vid=9,
                table_id=1,
                code="T1",
                start_release_id=PREV,
                end_release_id=CUR,
            ),
            TableVersion(
                table_vid=10,
                table_id=1,
                code="T1",
                start_release_id=CUR,
            ),
            TableVersion(
                table_vid=19,
                table_id=2,
                code="T2",
                start_release_id=PREV,
                end_release_id=CUR,
            ),
            TableVersion(
                table_vid=20,
                table_id=2,
                code="T2",
                start_release_id=CUR,
            ),
            ModuleVersionComposition(
                module_vid=500, table_id=1, table_vid=10
            ),
            ModuleVersionComposition(
                module_vid=500, table_id=2, table_vid=20
            ),
            Header(header_id=1, table_id=1, direction="y"),
            Header(header_id=2, table_id=1, direction="x"),
            Header(
                header_id=3, table_id=1, direction="x", is_key=True
            ),
            Header(header_id=4, table_id=2, direction="y"),
            Header(header_id=6, table_id=2, direction="y"),
            HeaderVersion(
                header_vid=100,
                header_id=1,
                property_id=10,
                start_release_id=PREV,
            ),
            HeaderVersion(
                header_vid=200,
                header_id=2,
                context_id=40,
                start_release_id=PREV,
            ),
            HeaderVersion(
                header_vid=300,
                header_id=3,
                property_id=20,
                start_release_id=CUR,
            ),
            HeaderVersion(
                header_vid=400,
                header_id=4,
                property_id=11,
                start_release_id=PREV,
            ),
            HeaderVersion(
                header_vid=600,
                header_id=6,
                property_id=12,
                start_release_id=CUR,
            ),
            TableVersionHeader(
                table_vid=10, header_id=1, header_vid=100
            ),
            TableVersionHeader(
                table_vid=10, header_id=2, header_vid=200
            ),
            TableVersionHeader(
                table_vid=10, header_id=3, header_vid=300
            ),
            TableVersionHeader(
                table_vid=20, header_id=4, header_vid=400
            ),
            TableVersionHeader(
                table_vid=20, header_id=6, header_vid=600
            ),
            Cell(cell_id=1000, table_id=1, row_id=1, column_id=2),
            Cell(cell_id=2000, table_id=2, row_id=4),
            Cell(cell_id=2001, table_id=2, row_id=6),
            Cell(cell_id=2002, table_id=2),
            TableVersionCell(
                table_vid=10, cell_id=1000, cell_code="c1000"
            ),
            TableVersionCell(
                table_vid=9, cell_id=1000, variable_vid=5000
            ),
            TableVersionCell(
                table_vid=20, cell_id=2000, cell_code="c2000"
            ),
            TableVersionCell(
                table_vid=19, cell_id=2000, variable_vid=5100
            ),
            TableVersionCell(
                table_vid=20, cell_id=2001, cell_code="c2001"
            ),
            TableVersionCell(
                table_vid=19, cell_id=2001, variable_vid=5200
            ),
            TableVersionCell(
                table_vid=20,
                cell_id=2002,
                cell_code="c2002",
                is_void=True,
            ),
            Variable(variable_id=600, type="fact"),
            Variable(variable_id=601, type="fact"),
            Variable(variable_id=602, type="fact"),
            VariableVersion(
                variable_vid=5000,
                variable_id=600,
                property_id=10,
                context_id=40,
                start_release_id=PREV,
            ),
            VariableVersion(
                variable_vid=5100,
                variable_id=601,
                property_id=11,
                start_release_id=PREV,
            ),
            VariableVersion(
                variable_vid=5200,
                variable_id=602,
                property_id=13,
                start_release_id=PREV,
            ),
        ]
    )
    session.commit()


# ------------------------------------------------------------------
# Happy path
# ------------------------------------------------------------------


def test_generate_full_plan(session):
    _seed_full_model(session)
    service = VariableGenerationService(session)
    result = service.generate(validate_first=False)

    assert result.status == GenerationStatus.COMPLETED
    assert result.release_id == CUR
    assert result.release_code == "CURR"
    assert result.validation is None
    assert result.consistency_violations == ()
    assert result.header_deduplications == ()

    # supporting objects
    key_vars = [v for v in result.new_variables if v.type == "key"]
    assert len(key_vars) == 1
    assert key_vars[0].versions[0].aspect.property_id == 20
    assert [k.signature for k in result.new_compound_keys] == ["20#"]
    assert result.new_compound_keys[0].member_variable_refs == (
        key_vars[0].versions[0].temp_id,
    )
    fi_codes = [f.code for f in result.new_filing_indicators]
    assert fi_codes == ["T1", "T2"]
    assert all(
        f.module_vids == (500,)
        for f in result.new_filing_indicators
    )
    assert [c.signature for c in result.new_contexts] == [
        "800_fi:1#",
        "800_fi:2#",
    ]

    # cell outcomes
    outcomes = {
        (a.table_vid, a.cell_id): a.outcome
        for a in result.cell_assignments
    }
    assert outcomes == {
        (10, 1000): CellOutcome.NEW_VARIABLE,
        (20, 2000): CellOutcome.UNCHANGED,
        (20, 2001): CellOutcome.NEW_VERSION,
        (20, 2002): CellOutcome.NOT_REPORTABLE,
    }
    by_cell = {
        (a.table_vid, a.cell_id): a for a in result.cell_assignments
    }
    new_var_cell = by_cell[(10, 1000)]
    fact_vars = [v for v in result.new_variables if v.type == "fact"]
    assert len(fact_vars) == 1
    assert new_var_cell.new_variable_ref == fact_vars[0].temp_id
    assert new_var_cell.new_aspect.key_id == "key:1"
    unchanged = by_cell[(20, 2000)]
    assert unchanged.new_variable_vid_ref == 5100
    new_version_cell = by_cell[(20, 2001)]
    new_versions = [
        v
        for v in result.new_variable_versions
        if v.variable_ref == 602
    ]
    assert len(new_versions) == 1
    assert new_versions[0].supersedes_vid == 5200
    assert (
        new_version_cell.new_variable_vid_ref
        == new_versions[0].temp_id
    )
    not_reportable = by_cell[(20, 2002)]
    assert not_reportable.new_variable_vid_ref is None

    # every proposed version appears in the flat list
    flat = {v.temp_id for v in result.new_variable_versions}
    nested = {
        v.temp_id
        for variable in result.new_variables
        for v in variable.versions
    }
    assert nested <= flat

    # summary excludes unchanged and void cells
    summary = {
        (row.outcome, row.count) for row in result.summary
    }
    assert summary == {
        (CellOutcome.NEW_VARIABLE, 1),
        (CellOutcome.NEW_VERSION, 1),
    }


def test_generate_result_round_trips_to_json(session):
    _seed_full_model(session)
    result = VariableGenerationService(session).generate(
        validate_first=False
    )
    as_dict = result.to_dict()
    encoded = json.loads(json.dumps(as_dict))
    assert encoded["status"] == "completed"
    assert encoded["release_code"] == "CURR"
    assert len(encoded["cell_assignments"]) == 4
    assert encoded["new_compound_keys"][0]["signature"] == "20#"
    assert {
        row["outcome"] for row in encoded["summary"]
    } == {"new_variable", "new_version"}


def test_generate_with_passing_validation_gate(session):
    _add_releases(session)
    result = VariableGenerationService(session).generate()
    assert result.status == GenerationStatus.COMPLETED
    assert result.validation is not None
    assert result.validation.is_valid
    assert result.cell_assignments == ()
    assert result.summary == ()


# ------------------------------------------------------------------
# Blocked runs
# ------------------------------------------------------------------


def test_blocked_by_validation(session, temp_rule):
    _add_releases(session)
    temp_rule(
        "97_1",
        [Finding(objects=(ObjectRef(kind="table_version", id=1),))],
    )
    result = VariableGenerationService(session).generate()
    assert result.status == GenerationStatus.BLOCKED_BY_VALIDATION
    assert result.validation is not None
    assert not result.validation.is_valid
    assert result.consistency_violations == ()
    assert result.new_variables == ()
    assert result.cell_assignments == ()
    assert result.header_deduplications == ()
    as_dict = result.to_dict()
    assert as_dict["status"] == "blocked_by_validation"
    assert as_dict["validation"]["error_count"] == 1


def test_validate_first_false_skips_the_gate(session, temp_rule):
    _add_releases(session)
    temp_rule(
        "97_2",
        [Finding(objects=(ObjectRef(kind="table_version", id=1),))],
    )
    result = VariableGenerationService(session).generate(
        validate_first=False
    )
    assert result.status == GenerationStatus.COMPLETED
    assert result.validation is None


def test_blocked_by_consistency(session):
    _add_releases(session)
    session.add_all(
        [
            Module(module_id=1),
            ModuleVersion(
                module_vid=500,
                module_id=1,
                code="MOD1",
                start_release_id=CUR,
            ),
            Table(table_id=1, is_abstract=False),
            # an *old* table version still employed by the module
            TableVersion(
                table_vid=9,
                table_id=1,
                code="T1",
                start_release_id=PREV,
            ),
            ModuleVersionComposition(
                module_vid=500, table_id=1, table_vid=9
            ),
            Cell(cell_id=1000, table_id=1),
            TableVersionCell(
                table_vid=9,
                cell_id=1000,
                cell_code="c1000",
                variable_vid=5000,
            ),
            Variable(variable_id=600, type="fact"),
            # ... whose variable version is expired
            VariableVersion(
                variable_vid=5000,
                variable_id=600,
                property_id=10,
                start_release_id=PREV,
                end_release_id=PREV,
            ),
        ]
    )
    session.commit()
    result = VariableGenerationService(session).generate(
        validate_first=False
    )
    assert result.status == GenerationStatus.BLOCKED_BY_CONSISTENCY
    assert [v.rule_id for v in result.consistency_violations] == [
        "5_1"
    ]
    assert result.validation is None
    assert result.new_variables == ()
    assert result.cell_assignments == ()
    assert result.summary == ()


# ------------------------------------------------------------------
# Release resolution
# ------------------------------------------------------------------


def test_release_resolution_errors(session):
    _add_releases(session)
    service = VariableGenerationService(session)
    with pytest.raises(Invalid, match="not both"):
        service.generate(release_id=CUR, release_code="CURR")
    with pytest.raises(NotFound, match="id 42"):
        service.generate(release_id=42)
    with pytest.raises(NotFound, match="'nope'"):
        service.generate(release_code="nope")


def test_release_resolution_requires_a_current_release(session):
    session.add(
        Release(release_id=CUR, code="CURR", is_current=False)
    )
    session.commit()
    with pytest.raises(NotFound, match="No release is flagged"):
        VariableGenerationService(session).generate()


def test_generate_by_release_code(session):
    _add_releases(session)
    result = VariableGenerationService(session).generate(
        release_code="PREVR", validate_first=False
    )
    assert result.release_id == PREV
    assert result.release_code == "PREVR"
