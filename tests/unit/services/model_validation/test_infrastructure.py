"""Unit tests for the model-validation infrastructure.

Covers result types, release semantics, the rule registry, the
snapshot loader/indexes, and the service orchestration (release
resolution, ordering, counters).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from dpmcore.errors import Invalid, NotFound
from dpmcore.orm.base import Base
from dpmcore.orm.infrastructure import DataType, Release
from dpmcore.orm.rendering import TableVersion
from dpmcore.services.model_validation import (
    DRAFT_RELEASE_ID,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    Finding,
    ModelSnapshot,
    ModelValidationResult,
    ModelValidationService,
    ObjectRef,
    ReleaseContext,
    RuleContext,
    Violation,
)
from dpmcore.services.model_validation import registry as registry_mod
from dpmcore.services.model_validation.registry import (
    all_rule_infos,
    evaluate,
    rule,
    rule_sort_key,
)
from dpmcore.services.model_validation.service import _violation_sort_key
from dpmcore.services.model_validation.snapshot import (
    ContextCompositionRow,
    DataTypeRow,
    HeaderVersionRow,
    ModuleVersionCompositionRow,
    TableVersionCellRow,
    TableVersionHeaderRow,
    TableVersionRow,
)

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
    """Register a throwaway rule; remove it on teardown."""
    registered_ids = []

    def factory(rule_id, severity=SEVERITY_ERROR, findings=()):
        @rule(
            rule_id,
            legacy_code=rule_id,
            family="test",
            severity=severity,
            description=f"Test rule {rule_id}",
        )
        def _fn(ctx):
            yield from findings

        registered_ids.append(rule_id)
        return _fn

    yield factory
    for rule_id in registered_ids:
        del registry_mod.REGISTRY[rule_id]


@pytest.fixture
def empty_ctx():
    return RuleContext(
        snapshot=ModelSnapshot.from_rows(),
        release=ReleaseContext(current_release_id=1),
    )


# ------------------------------------------------------------------
# Types
# ------------------------------------------------------------------


def test_object_ref_to_dict():
    ref = ObjectRef(kind="table_version", id=5, code="C 01.00")
    assert ref.to_dict() == {
        "kind": "table_version",
        "id": 5,
        "code": "C 01.00",
        "name": None,
    }


def test_violation_to_dict():
    violation = Violation(
        rule_id="1_5",
        legacy_code="1_5",
        message="Duplicate table code",
        severity=SEVERITY_ERROR,
        objects=(ObjectRef(kind="table_version", id=1),),
    )
    as_dict = violation.to_dict()
    assert as_dict["rule_id"] == "1_5"
    assert as_dict["objects"][0]["id"] == 1


def test_result_to_dict_and_by_rule():
    violations = (
        Violation("1_5", "1_5", "m1", SEVERITY_ERROR),
        Violation("1_5", "1_5", "m2", SEVERITY_ERROR),
        Violation("2_1", "2_1", "m3", SEVERITY_WARNING),
    )
    result = ModelValidationResult(
        is_valid=False,
        release_id=1,
        release_code="4.0",
        violations=violations,
        error_count=2,
        warning_count=1,
        rules_run=10,
        elapsed_ms=1.0,
    )
    as_dict = result.to_dict()
    assert as_dict["error_count"] == 2
    assert len(as_dict["violations"]) == 3
    grouped = result.by_rule()
    assert [v.message for v in grouped["1_5"]] == ["m1", "m2"]
    assert len(grouped["2_1"]) == 1


# ------------------------------------------------------------------
# ReleaseContext
# ------------------------------------------------------------------


def test_release_context_without_draft():
    rel = ReleaseContext(current_release_id=7)
    assert rel.is_current(7)
    assert not rel.is_current(8)
    assert not rel.is_draft(DRAFT_RELEASE_ID)
    assert rel.is_open(None)
    assert not rel.is_open(DRAFT_RELEASE_ID)
    assert rel.starts_in_current(7)
    assert not rel.starts_in_current(None)
    assert rel.ends_in_current(7)
    assert not rel.ends_in_current(None)
    assert not rel.ends_in_current(8)


def test_release_context_with_draft():
    rel = ReleaseContext(
        current_release_id=7, draft_release_id=DRAFT_RELEASE_ID
    )
    assert rel.is_draft(DRAFT_RELEASE_ID)
    assert rel.is_current(DRAFT_RELEASE_ID)
    assert rel.is_open(DRAFT_RELEASE_ID)
    assert rel.starts_in_current(DRAFT_RELEASE_ID)
    assert rel.ends_in_current(DRAFT_RELEASE_ID)


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------


def test_rule_sort_key_natural_order():
    ids = ["1_10", "1_2", "3_5b", "3_5a", "2_1"]
    assert sorted(ids, key=rule_sort_key) == [
        "1_2",
        "1_10",
        "2_1",
        "3_5a",
        "3_5b",
    ]


def test_rule_decorator_rejects_duplicates(temp_rule):
    temp_rule("98_1")
    with pytest.raises(ValueError, match="Duplicate rule id"):
        temp_rule("98_1")
    # Failed registration must not leave state behind twice.
    assert "98_1" in registry_mod.REGISTRY


def test_rule_decorator_rejects_bad_severity():
    with pytest.raises(ValueError, match="Unknown severity"):
        rule("98_2", "98_2", "test", "fatal", "bad")


def test_evaluate_stamps_metadata_and_counts(temp_rule, empty_ctx):
    finding = Finding(objects=(ObjectRef(kind="item", id=1),))
    temp_rule("98_3", findings=[finding])
    temp_rule(
        "98_4",
        severity=SEVERITY_WARNING,
        findings=[Finding(objects=(), message="custom msg")],
    )
    violations, rules_run = evaluate(
        empty_ctx, rule_ids=["98_3", "98_4"]
    )
    assert rules_run == 2
    assert violations[0].rule_id == "98_3"
    assert violations[0].message == "Test rule 98_3"
    assert violations[1].message == "custom msg"
    assert violations[1].severity == SEVERITY_WARNING


def test_evaluate_can_skip_warnings(temp_rule, empty_ctx):
    temp_rule(
        "98_5",
        severity=SEVERITY_WARNING,
        findings=[Finding(objects=())],
    )
    violations, rules_run = evaluate(
        empty_ctx, rule_ids=["98_5"], include_warnings=False
    )
    assert violations == []
    assert rules_run == 0


def test_evaluate_unknown_rule_id(empty_ctx):
    with pytest.raises(NotFound, match="Unknown rule ids: nope"):
        evaluate(empty_ctx, rule_ids=["nope"])


def test_evaluate_all_registered(temp_rule, empty_ctx):
    temp_rule("98_6", findings=[Finding(objects=())])
    violations, rules_run = evaluate(empty_ctx)
    assert rules_run == len(registry_mod.REGISTRY)
    assert any(v.rule_id == "98_6" for v in violations)


def test_all_rule_infos_sorted(temp_rule):
    temp_rule("98_10")
    temp_rule("98_9")
    infos = all_rule_infos()
    ids = [i.rule_id for i in infos]
    assert ids.index("98_9") < ids.index("98_10")
    entry = next(i for i in infos if i.rule_id == "98_9")
    assert entry.to_dict()["family"] == "test"


# ------------------------------------------------------------------
# Snapshot
# ------------------------------------------------------------------


def test_snapshot_from_rows_rejects_unknown_store():
    with pytest.raises(TypeError, match="Unknown snapshot stores"):
        ModelSnapshot.from_rows(bogus=[])


def test_snapshot_from_rows_builds_indexes():
    tv = TableVersionRow(
        table_vid=10,
        code="T1",
        name=None,
        table_id=1,
        abstract_table_id=None,
        key_id=None,
        property_id=None,
        context_id=None,
        start_release_id=1,
        end_release_id=None,
    )
    orphan = TableVersionRow(
        table_vid=11,
        code=None,
        name=None,
        table_id=None,
        abstract_table_id=None,
        key_id=None,
        property_id=None,
        context_id=None,
        start_release_id=None,
        end_release_id=None,
    )
    snap = ModelSnapshot.from_rows(table_versions=[tv, orphan])
    assert snap.table_versions_by_vid[10].code == "T1"
    assert snap.table_versions_by_table() == {1: [tv]}
    assert snap.releases == []


def test_snapshot_shared_indexes():
    snap = ModelSnapshot.from_rows(
        table_version_headers=[
            TableVersionHeaderRow(1, 2, 3, None, None, 1, None, None),
        ],
        table_version_cells=[
            TableVersionCellRow(
                1, 5, "c", None, None, None, None, None
            ),
        ],
        module_version_compositions=[
            ModuleVersionCompositionRow(7, 1, 10, None),
            ModuleVersionCompositionRow(7, 2, None, None),
        ],
        context_compositions=[
            ContextCompositionRow(4, 8, 9),
        ],
        header_versions=[
            HeaderVersionRow(
                3, 2, "010", None, None, None, None, None, 1, None
            ),
            HeaderVersionRow(
                4, None, None, None, None, None, None, None, 1, None
            ),
        ],
    )
    assert snap.tvh_by_table_vid()[1][0].header_id == 2
    assert snap.tvc_by_table_vid()[1][0].cell_id == 5
    assert len(snap.mvc_by_module_vid()[7]) == 2
    assert snap.mvc_by_table_vid()[10][0].module_vid == 7
    assert 2 not in {
        mvc.table_vid for mvc in snap.mvc_by_table_vid().get(10, [])
    }
    assert snap.context_compositions_by_context()[4][0].item_id == 9
    assert snap.header_versions_by_header() == {
        2: snap.header_versions[:1]
    }


def test_snapshot_cache_reuses_value():
    snap = ModelSnapshot.from_rows()
    first = snap.cache("k", list)
    second = snap.cache("k", list)
    assert first is second


def test_snapshot_dpm1_datatype_codes():
    snap = ModelSnapshot.from_rows(
        datatypes=[
            DataTypeRow(1, "dt", None, None, True),
            DataTypeRow(2, "u", None, None, True),
            DataTypeRow(3, "es", None, None, True),
            DataTypeRow(4, "o", None, None, True),
            DataTypeRow(5, "m", None, None, True),
            DataTypeRow(6, None, None, None, True),
        ]
    )
    codes = snap.dpm1_datatype_codes()
    assert codes == {1: "d", 2: "s", 3: "s", 4: "s", 5: "m", 6: None}


def test_snapshot_loads_from_database(session):
    session.add(Release(release_id=1, code="4.0", is_current=True))
    session.add(DataType(data_type_id=1, code="m", name="Monetary"))
    session.add(
        TableVersion(table_vid=10, code="T1", start_release_id=1)
    )
    session.commit()
    snap = ModelSnapshot(session)
    assert snap.releases_by_id[1].is_current is True
    assert snap.datatypes_by_id[1].code == "m"
    assert snap.table_versions_by_vid[10].start_release_id == 1


# ------------------------------------------------------------------
# Service
# ------------------------------------------------------------------


def _add_releases(session, with_draft=False):
    session.add(Release(release_id=1, code="4.0", is_current=True))
    session.add(Release(release_id=2, code="3.0", is_current=False))
    if with_draft:
        session.add(
            Release(
                release_id=DRAFT_RELEASE_ID,
                code="draft",
                is_current=False,
            )
        )
    session.commit()


def test_validate_defaults_to_current_release(session):
    _add_releases(session)
    result = ModelValidationService(session).validate(rule_ids=[])
    assert result.release_id == 1
    assert result.release_code == "4.0"
    assert result.is_valid
    assert result.rules_run == 0
    assert result.to_dict()["violations"] == []


def test_validate_by_release_code_and_id(session):
    _add_releases(session)
    service = ModelValidationService(session)
    assert service.validate(release_code="3.0", rule_ids=[]).release_id == 2
    assert service.validate(release_id=2, rule_ids=[]).release_code == "3.0"


def test_validate_release_errors(session):
    _add_releases(session)
    service = ModelValidationService(session)
    with pytest.raises(Invalid, match="not both"):
        service.validate(release_id=1, release_code="4.0")
    with pytest.raises(NotFound, match="id 42"):
        service.validate(release_id=42)
    with pytest.raises(NotFound, match="'nope'"):
        service.validate(release_code="nope")


def test_validate_requires_a_current_release(session):
    session.add(Release(release_id=1, code="4.0", is_current=False))
    session.commit()
    with pytest.raises(NotFound, match="No release is flagged"):
        ModelValidationService(session).validate()


def test_validate_detects_draft_release(session, temp_rule):
    _add_releases(session, with_draft=True)
    captured = {}

    @rule(
        "98_20",
        legacy_code="98_20",
        family="test",
        severity=SEVERITY_ERROR,
        description="capture ctx",
    )
    def _capture(ctx):
        captured["draft"] = ctx.release.draft_release_id
        return ()

    try:
        service = ModelValidationService(session)
        service.validate(rule_ids=["98_20"])
        assert captured["draft"] == DRAFT_RELEASE_ID
        result = service.validate(
            release_id=DRAFT_RELEASE_ID, rule_ids=[]
        )
        assert result.release_id == DRAFT_RELEASE_ID
    finally:
        del registry_mod.REGISTRY["98_20"]


def test_validate_counts_and_sorts_violations(session, temp_rule):
    _add_releases(session)
    temp_rule(
        "99_2",
        findings=[
            Finding(objects=(ObjectRef(kind="item", id=2),)),
            Finding(objects=(ObjectRef(kind="item", id=1),)),
        ],
    )
    temp_rule(
        "99_1",
        severity=SEVERITY_WARNING,
        findings=[Finding(objects=())],
    )
    result = ModelValidationService(session).validate(
        rule_ids=["99_2", "99_1"]
    )
    assert not result.is_valid
    assert result.error_count == 2
    assert result.warning_count == 1
    assert [v.rule_id for v in result.violations] == [
        "99_1",
        "99_2",
        "99_2",
    ]
    assert [v.objects[0].id for v in result.violations[1:]] == [1, 2]


def test_violation_sort_key_without_objects():
    violation = Violation("1_1", "1_1", "msg", SEVERITY_ERROR)
    key = _violation_sort_key(violation)
    assert key == ((1, 1, ""), "", "msg")


def test_list_rules_matches_registry(session):
    infos = ModelValidationService(session).list_rules()
    assert len(infos) == len(registry_mod.REGISTRY)


def test_validate_accepts_preloaded_snapshot(session):
    _add_releases(session)
    snap = ModelSnapshot.from_rows()
    result = ModelValidationService(session).validate(
        rule_ids=[], snapshot=snap
    )
    assert result.is_valid
