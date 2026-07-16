import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dpmcore.orm.infrastructure import Organisation, Release
from dpmcore.orm.operations import OperationScope, OperationScopeComposition
from dpmcore.services.ecb_validations_import import (
    EcbValidationsImportError,
    EcbValidationsImportService,
    _format_warnings,
    _stable_uuid,
)
from dpmcore.services.scope_calculator import ScopeResult


@pytest.fixture
def sqlite_engine():
    return create_engine("sqlite:///:memory:")


@pytest.fixture
def sqlite_engine_with_schema():
    engine = create_engine("sqlite:///:memory:")
    from dpmcore.orm.base import Base

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def service(sqlite_engine):
    return EcbValidationsImportService(sqlite_engine)


@pytest.fixture
def service_with_schema(sqlite_engine_with_schema):
    return EcbValidationsImportService(sqlite_engine_with_schema)


class TestEcbValidationsImport:
    def test_missing_required_columns_raise(self, service, tmp_path):
        csv_file = tmp_path / "ecb_validations_file.csv"
        csv_file.write_text("code,start\nA,4.0\n", encoding="utf-8")

        with pytest.raises(
            EcbValidationsImportError,
            match="missing required columns",
        ):
            service.import_csv(str(csv_file))

    def test_parse_submission_date_accepts_iso_and_ddmmyyyy(self, service):
        assert (
            str(service._parse_submission_date("17/03/2026")) == "2026-03-17"
        )
        assert (
            str(service._parse_submission_date("2026-03-17")) == "2026-03-17"
        )
        assert service._parse_submission_date("-") is None

    def test_normalize_text_handles_empty_and_nan(self, service):
        assert service._normalize_text(None) is None
        assert service._normalize_text("") is None
        assert service._normalize_text("   ") is None
        assert service._normalize_text("nan") is None
        assert service._normalize_text(" ECB ") == "ECB"

    def test_is_active_value(self, service):
        assert service._is_active_value("Active") == -1
        assert service._is_active_value("yes") == -1
        assert service._is_active_value("true") == -1
        assert service._is_active_value("0") == 0
        assert service._is_active_value("No") == 0

    def test_parent_operation_helpers(self, service):
        # Codes with no trailing _digits are parents; those with are children.
        assert service._is_parent_operation_code("EGDQ") is True
        assert service._is_parent_operation_code("EGDQ_0022") is False
        assert service._is_parent_operation_code("EGDQ_0022_1") is False
        assert service._get_parent_operation_code("EGDQ_0022_1") == "EGDQ_0022"
        assert service._get_parent_operation_code("EGDQ_0022") == "EGDQ"
        assert service._get_parent_operation_code("EGDQ") is None

    def test_import_csv_file_not_found_raises(self, service):
        with pytest.raises(
            EcbValidationsImportError,
            match="does not exist",
        ):
            service.import_csv("/nonexistent/path/validations.csv")

    def test_import_csv_path_is_directory_raises(self, service, tmp_path):
        with pytest.raises(
            EcbValidationsImportError,
            match="is not a file",
        ):
            service.import_csv(str(tmp_path))

    def test_parse_submission_date_invalid_format_raises(self, service):
        with pytest.raises(
            EcbValidationsImportError,
            match="Unsupported submission date",
        ):
            service._parse_submission_date("not-a-date")

    def test_parse_submission_date_none_returns_none(self, service):
        assert service._parse_submission_date(None) is None

    def test_import_csv_missing_columns_raises_via_file(
        self, service, tmp_path
    ):
        csv_file = tmp_path / "ecb_validations_file.csv"
        csv_file.write_text("code,start\nA,4.0\n", encoding="utf-8")

        with pytest.raises(
            EcbValidationsImportError,
            match="missing required columns",
        ):
            service.import_csv(str(csv_file))

    # ------------------------------------------------------------------
    # _resolve_release (static, no DB needed)
    # ------------------------------------------------------------------

    def test_resolve_release_returns_none_for_empty_value(self, service):
        assert service._resolve_release({}, "") is None
        assert service._resolve_release({}, None) is None

    def test_resolve_release_returns_release_from_cache(self, service):
        from unittest.mock import MagicMock

        mock_release = MagicMock()
        assert (
            service._resolve_release({"4.0": mock_release}, "4.0")
            is mock_release
        )

    def test_resolve_release_returns_none_for_unknown_code(self, service):
        assert service._resolve_release({"4.0": object()}, "5.0") is None

    def test_resolve_release_applies_code_remap(self, service):
        from unittest.mock import MagicMock

        mock_release = MagicMock()
        # _RELEASE_CODE_MAP maps "3.2" → "3.4"
        assert (
            service._resolve_release({"3.4": mock_release}, "3.2")
            is mock_release
        )

    # ------------------------------------------------------------------
    # _collect_table_codes_from_ast (pure logic, no DB)
    # ------------------------------------------------------------------

    def test_collect_table_codes_extracts_table_attribute(self, service):
        class Node:
            def __init__(self):
                self.table = "T_01"
                self.is_table_group = False

        result = service._collect_table_codes_from_ast(Node())
        assert "T_01" in result

    def test_collect_table_codes_skips_table_groups(self, service):
        class Node:
            def __init__(self):
                self.table = "T_01"
                self.is_table_group = True

        result = service._collect_table_codes_from_ast(Node())
        assert "T_01" not in result

    def test_collect_table_codes_recurses_into_list_attributes(self, service):
        class Child:
            def __init__(self, code):
                self.table = code
                self.is_table_group = False

        class Parent:
            def __init__(self):
                self.table = None
                self.is_table_group = False
                self.children = [Child("T_01"), Child("T_02")]

        result = service._collect_table_codes_from_ast(Parent())
        assert "T_01" in result
        assert "T_02" in result

    def test_collect_table_codes_ignores_none_node(self, service):
        result = service._collect_table_codes_from_ast(None)
        assert result == set()

    def test_collect_table_codes_skips_non_string_table(self, service):
        class Node:
            def __init__(self):
                self.table = 42  # not a string
                self.is_table_group = False

        result = service._collect_table_codes_from_ast(Node())
        assert result == set()

    # ------------------------------------------------------------------
    # _next_int_id and _get_or_create_ecb_organisation (require schema)
    # ------------------------------------------------------------------

    def test_next_int_id_returns_one_when_table_is_empty(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            result = EcbValidationsImportService._next_int_id(
                session, Organisation, "org_id"
            )
            assert result == 1
        finally:
            session.close()

    def test_next_int_id_returns_max_plus_one(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            session.add(
                Organisation(org_id=5, name="Org5", acronym="O5", id_prefix=1)
            )
            session.add(
                Organisation(
                    org_id=10, name="Org10", acronym="O10", id_prefix=2
                )
            )
            session.flush()
            result = EcbValidationsImportService._next_int_id(
                session, Organisation, "org_id"
            )
            assert result == 11
        finally:
            session.close()

    def test_get_or_create_ecb_organisation_creates_new(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            org = service_with_schema._get_or_create_ecb_organisation(session)
            assert org.acronym == "ECB"
            assert org.name == "European Central Bank"
        finally:
            session.close()

    def test_get_or_create_ecb_organisation_returns_existing(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            org1 = service_with_schema._get_or_create_ecb_organisation(session)
            session.flush()
            org2 = service_with_schema._get_or_create_ecb_organisation(session)
            assert org1.org_id == org2.org_id
        finally:
            session.close()

    # ------------------------------------------------------------------
    # _get_valid_release_ids (requires schema + Release rows)
    # ------------------------------------------------------------------

    def test_get_valid_release_ids_from_start_with_no_end(
        self, sqlite_engine_with_schema
    ):
        from dpmcore.orm.infrastructure import Release

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            session.add(
                Release(release_id=1, code="4.0", date=date(2024, 1, 1))
            )
            session.add(
                Release(release_id=2, code="4.1", date=date(2024, 2, 1))
            )
            session.add(
                Release(release_id=3, code="4.2", date=date(2024, 3, 1))
            )
            session.flush()

            result = EcbValidationsImportService._get_valid_release_ids(
                session, start_release_id=2, end_release_id=None
            )
            assert result == [2, 3]
        finally:
            session.close()

    def test_get_valid_release_ids_with_end_excludes_end(
        self, sqlite_engine_with_schema
    ):
        from dpmcore.orm.infrastructure import Release

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            session.add(
                Release(release_id=1, code="4.0", date=date(2024, 1, 1))
            )
            session.add(
                Release(release_id=2, code="4.1", date=date(2024, 2, 1))
            )
            session.add(
                Release(release_id=3, code="4.2", date=date(2024, 3, 1))
            )
            session.flush()

            result = EcbValidationsImportService._get_valid_release_ids(
                session, start_release_id=1, end_release_id=3
            )
            assert result == [1, 2]
        finally:
            session.close()

    def test_get_valid_release_ids_undated_start_is_latest(
        self, sqlite_engine_with_schema
    ):
        from dpmcore.orm.infrastructure import Release

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            # An undated (unpublished) release ranks as the latest, so a
            # range starting at it is valid and contains just itself.
            session.add(
                Release(release_id=1, code="4.0", date=date(2024, 1, 1))
            )
            session.add(Release(release_id=2, code="Playground", date=None))
            session.flush()

            result = EcbValidationsImportService._get_valid_release_ids(
                session, start_release_id=2, end_release_id=None
            )
            assert result == [2]
        finally:
            session.close()

    def test_get_valid_release_ids_unknown_start_raises(
        self, sqlite_engine_with_schema
    ):
        from dpmcore.orm.infrastructure import Release

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            # A window bound with no matching Release row cannot be placed,
            # so it raises rather than silently dropping rows.
            session.add(
                Release(release_id=2, code="4.1", date=date(2024, 2, 1))
            )
            session.flush()

            with pytest.raises(
                EcbValidationsImportError, match="has no sort_order"
            ):
                EcbValidationsImportService._get_valid_release_ids(
                    session, start_release_id=1, end_release_id=None
                )
        finally:
            session.close()

    def test_get_valid_release_ids_unknown_end_raises(
        self, sqlite_engine_with_schema
    ):
        from dpmcore.orm.infrastructure import Release

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            session.add(
                Release(release_id=1, code="4.0", date=date(2024, 1, 1))
            )
            session.flush()

            with pytest.raises(
                EcbValidationsImportError, match="has no sort_order"
            ):
                EcbValidationsImportService._get_valid_release_ids(
                    session, start_release_id=1, end_release_id=2
                )
        finally:
            session.close()

    # ------------------------------------------------------------------
    # _create_operation_concept (requires schema)
    # ------------------------------------------------------------------

    def test_create_operation_concept_returns_none_when_class_is_none(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            result = service_with_schema._create_operation_concept(
                session, operation_class=None, owner=None, stable_key="test"
            )
            assert result is None
        finally:
            session.close()

    def test_create_operation_concept_returns_guid_string(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        from dpmcore.orm.infrastructure import DpmClass, Organisation

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            org = Organisation(
                org_id=1, name="Test", acronym="TST", id_prefix=1
            )
            cls = DpmClass(class_id=1, name="Operation")
            session.add(org)
            session.add(cls)
            session.flush()

            result = service_with_schema._create_operation_concept(
                session, operation_class=cls, owner=org, stable_key="test"
            )
            assert result is not None
            assert len(result) == 38  # Access-style {UUID} format
        finally:
            session.close()

    # ------------------------------------------------------------------
    # import_csv end-to-end with minimal DB
    # ------------------------------------------------------------------

    def test_import_csv_unknown_release_creates_operation_and_warns(
        self, service_with_schema, tmp_path
    ):
        csv_file = tmp_path / "valid.csv"
        csv_file.write_text(
            "vr_code,start_release\nV1,4.0\n", encoding="utf-8"
        )

        result = service_with_schema.import_csv(str(csv_file))

        # Operation V1 is created even though the release is unknown
        assert result.operations_created == 1
        assert result.operation_versions_created == 0
        # One warning for the unresolved release
        assert len(result.warnings) == 1
        assert "4.0" in result.warnings[0]

    def test_import_csv_child_code_also_creates_parent_operation(
        self, service_with_schema, tmp_path
    ):
        csv_file = tmp_path / "valid.csv"
        csv_file.write_text(
            "vr_code,start_release\nV1_1,4.0\n", encoding="utf-8"
        )

        result = service_with_schema.import_csv(str(csv_file))

        # V1_1 and its inferred parent V1 are both created
        assert result.operations_created == 2

    def test_import_csv_known_release_creates_version(
        self, service_with_schema, sqlite_engine_with_schema, tmp_path
    ):
        from dpmcore.orm.infrastructure import Release

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        session.add(Release(release_id=1, code="4.0"))
        session.commit()
        session.close()

        csv_file = tmp_path / "valid.csv"
        csv_file.write_text(
            "vr_code,start_release\nV1,4.0\n", encoding="utf-8"
        )

        result = service_with_schema.import_csv(str(csv_file))

        assert result.operations_created == 1
        assert result.operation_versions_created == 1
        assert result.warnings == []

    def test_import_csv_duplicate_version_key_skipped(
        self, service_with_schema, sqlite_engine_with_schema, tmp_path
    ):
        from dpmcore.orm.infrastructure import Release

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        session.add(Release(release_id=1, code="4.0"))
        session.commit()
        session.close()

        # Same vr_code + start_release twice → only one version created
        csv_file = tmp_path / "valid.csv"
        csv_file.write_text(
            "vr_code,start_release\nV1,4.0\nV1,4.0\n", encoding="utf-8"
        )

        result = service_with_schema.import_csv(str(csv_file))

        assert result.operation_versions_created == 1

    def test_extract_table_codes_for_empty_expression_returns_empty_set(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            assert (
                service_with_schema._extract_table_codes_for_expression(
                    session,
                    expression=None,
                    start_release_id=1,
                    latest_release_id=2,
                )
                == set()
            )

            assert (
                service_with_schema._extract_table_codes_for_expression(
                    session,
                    expression="   ",
                    start_release_id=1,
                    latest_release_id=2,
                )
                == set()
            )
        finally:
            session.close()

    def test_extract_table_codes_for_expression_uses_latest_release_as_fallback(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        session = sessionmaker(bind=sqlite_engine_with_schema)()

        checker_start = MagicMock()
        checker_start.tables = {}

        checker_latest = MagicMock()
        checker_latest.tables = {"T_01": object(), "T_02": object()}

        with (
            patch(
                "dpmcore.services.ecb_validations_import.SyntaxService"
            ) as syntax_cls,
            patch(
                "dpmcore.services.ecb_validations_import.OperandsChecking"
            ) as checker_cls,
        ):
            syntax_cls.return_value.parse.return_value = object()
            checker_cls.side_effect = [checker_start, checker_latest]

            result = service_with_schema._extract_table_codes_for_expression(
                session,
                expression="check(T_01)",
                start_release_id=1,
                latest_release_id=2,
            )

        session.close()

        assert result == {"T_01", "T_02"}

    def test_extract_table_codes_for_expression_returns_empty_when_all_checks_fail(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        session = sessionmaker(bind=sqlite_engine_with_schema)()

        with (
            patch(
                "dpmcore.services.ecb_validations_import.SyntaxService"
            ) as syntax_cls,
            patch(
                "dpmcore.services.ecb_validations_import.OperandsChecking"
            ) as checker_cls,
        ):
            syntax_cls.return_value.parse.return_value = object()
            checker_cls.side_effect = RuntimeError("cannot inspect tables")

            result = service_with_schema._extract_table_codes_for_expression(
                session,
                expression="broken expression",
                start_release_id=1,
                latest_release_id=2,
            )

        session.close()

        assert result == set()

    def test_extract_table_codes_for_expression_records_warnings_on_failure(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        session = sessionmaker(bind=sqlite_engine_with_schema)()
        warnings: list = []

        with (
            patch(
                "dpmcore.services.ecb_validations_import.SyntaxService"
            ) as syntax_cls,
            patch(
                "dpmcore.services.ecb_validations_import.OperandsChecking"
            ) as checker_cls,
        ):
            syntax_cls.return_value.parse.return_value = object()
            checker_cls.side_effect = RuntimeError("cannot inspect tables")

            result = service_with_schema._extract_table_codes_for_expression(
                session,
                expression="broken expression",
                start_release_id=1,
                latest_release_id=2,
                warnings=warnings,
            )

        session.close()

        assert result == set()
        assert len(warnings) == 2
        assert all(
            "Table code resolution failed for expression" in w
            for w in warnings
        )
        assert "release 1" in warnings[0]
        assert "release 2" in warnings[1]

    def test_create_table_references_returns_zero_when_no_table_codes(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            result = service_with_schema._create_table_references(
                session,
                operation_vid=1,
                table_codes=set(),
            )

            assert result == 0
        finally:
            session.close()

    def test_create_table_references_skips_unknown_tables(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            result = service_with_schema._create_table_references(
                session,
                operation_vid=1,
                table_codes={"UNKNOWN_TABLE"},
            )

            assert result == 0
        finally:
            session.close()

    def test_create_table_references_creates_reference_and_location_without_cell(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        from dpmcore.orm.operations import (
            OperandReference,
            OperandReferenceLocation,
            OperationNode,
        )
        from dpmcore.orm.rendering import TableVersion

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            session.add(
                TableVersion(
                    table_vid=1,
                    code="T_01",
                    table_id=100,
                    start_release_id=1,
                )
            )
            session.flush()

            result = service_with_schema._create_table_references(
                session,
                operation_vid=10,
                table_codes={"T_01"},
            )

            assert result == 1

            node = session.query(OperationNode).one()
            ref = session.query(OperandReference).one()
            location = session.query(OperandReferenceLocation).one()

            assert node.operation_vid == 10
            assert ref.node_id == node.node_id
            assert ref.operand_reference == "T_01"
            assert location.operand_reference_id == ref.operand_reference_id
            assert location.table == "T_01"
            assert location.cell_id is None
        finally:
            session.close()

    def test_get_or_create_precondition_version_empty_expression_returns_none(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        from dpmcore.orm.infrastructure import Release

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            release = Release(release_id=1, code="4.0")

            result = service_with_schema._get_or_create_precondition_version(
                session,
                expression="",
                release=release,
                operation_class=None,
                owner=None,
                counters={"operation_id": 1, "operation_vid": 1},
                cache={},
            )

            assert result == (None, 0)
        finally:
            session.close()

    def test_get_or_create_precondition_version_creates_operation_and_version(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        from dpmcore.orm.infrastructure import Release
        from dpmcore.orm.operations import Operation, OperationVersion

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            release = Release(release_id=1, code="4.0")
            session.add(release)
            session.flush()

            counters = {"operation_id": 1, "operation_vid": 1}
            cache = {}

            precondition_vid, created = (
                service_with_schema._get_or_create_precondition_version(
                    session,
                    expression="x > 0",
                    release=release,
                    operation_class=None,
                    owner=None,
                    counters=counters,
                    cache=cache,
                )
            )

            assert precondition_vid == 1
            assert created == 1
            assert counters["operation_id"] == 2
            assert counters["operation_vid"] == 2

            operation = session.query(Operation).one()
            version = session.query(OperationVersion).one()

            assert operation.type == "precondition"
            assert operation.source == "user_defined"
            assert version.operation_vid == precondition_vid
            assert version.expression == "x > 0"
            assert version.description == "Precondition: x > 0"
        finally:
            session.close()

    def test_get_or_create_precondition_version_uses_cache(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        from dpmcore.orm.infrastructure import Release

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            release = Release(release_id=1, code="4.0")
            cache = {("x > 0", 1): 99}

            result = service_with_schema._get_or_create_precondition_version(
                session,
                expression="x > 0",
                release=release,
                operation_class=None,
                owner=None,
                counters={"operation_id": 1, "operation_vid": 1},
                cache=cache,
            )

            assert result == (99, 0)
        finally:
            session.close()

    def test_get_or_create_precondition_version_creates_when_existing_code_does_not_match(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        from dpmcore.orm.infrastructure import Release
        from dpmcore.orm.operations import Operation, OperationVersion

        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            release = Release(release_id=1, code="4.0")
            operation = Operation(
                operation_id=1,
                code="precond_EGDQ_9e3669d1",
                type="precondition",
                source="user_defined",
            )
            version = OperationVersion(
                operation_vid=10,
                operation_id=1,
                start_release_id=1,
                expression="x > 0",
            )

            session.add(release)
            session.add(operation)
            session.add(version)
            session.flush()

            cache = {}

            result = service_with_schema._get_or_create_precondition_version(
                session,
                expression="x > 0",
                release=release,
                operation_class=None,
                owner=None,
                counters={"operation_id": 2, "operation_vid": 11},
                cache=cache,
            )

            assert result == (11, 1)
            assert cache[("x > 0", 1)] == 11
        finally:
            session.close()

    def test_import_csv_rolls_back_and_wraps_unexpected_errors(
        self, service_with_schema, tmp_path
    ):
        csv_file = tmp_path / "valid.csv"
        csv_file.write_text(
            "vr_code,start_release\nV1,4.0\n", encoding="utf-8"
        )

        with patch.object(
            service_with_schema,
            "_import_ecb_validations_df",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(
                EcbValidationsImportError,
                match="Failed to import ECB validations",
            ):
                service_with_schema.import_csv(str(csv_file))

    def test_import_csv_raises_when_commit_persists_nothing(
        self, service_with_schema, tmp_path
    ):
        """A hollow commit (no ECB org row) must surface as an error.

        Regression test for the "silent transaction abort" failure mode:
        a swallowed mid-loop DB error can leave ``session.commit()``
        succeeding with nothing actually persisted. Simulated here by
        stubbing out ``_import_ecb_validations_df`` entirely, so the
        session commits without ever creating the ECB organisation.
        """
        csv_file = tmp_path / "valid.csv"
        csv_file.write_text(
            "vr_code,start_release\nV1,4.0\n", encoding="utf-8"
        )

        with patch.object(
            service_with_schema,
            "_import_ecb_validations_df",
            return_value=MagicMock(),
        ):
            with pytest.raises(
                EcbValidationsImportError,
                match="no data was persisted",
            ):
                service_with_schema.import_csv(str(csv_file))


# ---------------------------------------------------------------------------
# Scope-creation loop: dedup across releases (issue: EGDQ_C207-style
# duplicate OperationScope/OperationScopeComposition rows)
# ---------------------------------------------------------------------------


def _scope_result_for(*module_vid_sets):
    scopes = []
    for module_vids in module_vid_sets:
        scope = OperationScope()
        for module_vid in module_vids:
            scope.operation_scope_compositions.append(
                OperationScopeComposition(module_vid=module_vid)
            )
        scopes.append(scope)
    return ScopeResult(
        scopes=scopes,
        total_scopes=len(scopes),
        is_cross_module=any(len(v) > 1 for v in module_vid_sets),
        module_versions=sorted(
            {vid for vids in module_vid_sets for vid in vids}
        ),
    )


class TestScopeDeduplicationAcrossReleases:
    """A validation with no ``end_release`` matches every release from
    its start onward. When the resolved module set doesn't change
    between those releases, the scope must be created once, not once
    per matching release.
    """

    def _seed_releases(self, sqlite_engine_with_schema):
        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            session.add_all(
                [
                    Release(release_id=1, code="4.0", date=date(2024, 1, 1)),
                    Release(release_id=2, code="4.1", date=date(2024, 6, 1)),
                    Release(release_id=3, code="4.2", date=date(2024, 12, 1)),
                ]
            )
            session.commit()
        finally:
            session.close()

    def test_same_module_set_across_releases_creates_scope_once(
        self, service_with_schema, sqlite_engine_with_schema, tmp_path
    ):
        self._seed_releases(sqlite_engine_with_schema)
        csv_file = tmp_path / "ecb.csv"
        csv_file.write_text(
            "vr_code,expression,start_release\nV1,check(T_01),4.0\n",
            encoding="utf-8",
        )

        with (
            patch(
                "dpmcore.services.ecb_validations_import.SyntaxService"
            ) as syntax_cls,
            patch(
                "dpmcore.services.ecb_validations_import.OperandsChecking"
            ) as checker_cls,
            patch(
                "dpmcore.services.ecb_validations_import"
                ".ScopeCalculatorService"
            ) as calc_cls,
        ):
            syntax_cls.return_value.parse.return_value = object()
            checker_cls.side_effect = RuntimeError("skip table extraction")
            calc_cls.return_value.calculate_from_expression.side_effect = [
                _scope_result_for((100,)),
                _scope_result_for((100,)),
                _scope_result_for((100,)),
            ]

            result = service_with_schema.import_csv(str(csv_file))

        assert result.scopes_created == 1
        assert result.scope_compositions_created == 1

    def test_different_module_sets_across_releases_creates_each_once(
        self, service_with_schema, sqlite_engine_with_schema, tmp_path
    ):
        self._seed_releases(sqlite_engine_with_schema)
        csv_file = tmp_path / "ecb.csv"
        csv_file.write_text(
            "vr_code,expression,start_release\nV1,check(T_01),4.0\n",
            encoding="utf-8",
        )

        with (
            patch(
                "dpmcore.services.ecb_validations_import.SyntaxService"
            ) as syntax_cls,
            patch(
                "dpmcore.services.ecb_validations_import.OperandsChecking"
            ) as checker_cls,
            patch(
                "dpmcore.services.ecb_validations_import"
                ".ScopeCalculatorService"
            ) as calc_cls,
        ):
            syntax_cls.return_value.parse.return_value = object()
            checker_cls.side_effect = RuntimeError("skip table extraction")
            calc_cls.return_value.calculate_from_expression.side_effect = [
                _scope_result_for((100,)),
                _scope_result_for((100, 200)),
                _scope_result_for((100, 200)),
            ]

            result = service_with_schema.import_csv(str(csv_file))

        assert result.scopes_created == 2
        assert result.scope_compositions_created == 3

    def test_scopes_are_deduplicated_independently_per_validation(
        self, service_with_schema, sqlite_engine_with_schema, tmp_path
    ):
        self._seed_releases(sqlite_engine_with_schema)
        csv_file = tmp_path / "ecb.csv"
        csv_file.write_text(
            "vr_code,expression,start_release\n"
            "V1,check(T_01),4.0\n"
            "V2,check(T_02),4.0\n",
            encoding="utf-8",
        )

        with (
            patch(
                "dpmcore.services.ecb_validations_import.SyntaxService"
            ) as syntax_cls,
            patch(
                "dpmcore.services.ecb_validations_import.OperandsChecking"
            ) as checker_cls,
            patch(
                "dpmcore.services.ecb_validations_import"
                ".ScopeCalculatorService"
            ) as calc_cls,
        ):
            syntax_cls.return_value.parse.return_value = object()
            checker_cls.side_effect = RuntimeError("skip table extraction")
            # Same module set (100,) recurs both across V1's releases and
            # for V2 -- deduplication must not leak across validations.
            calc_cls.return_value.calculate_from_expression.side_effect = [
                _scope_result_for((100,)),
                _scope_result_for((100,)),
                _scope_result_for((100,)),
                _scope_result_for((100,)),
                _scope_result_for((100,)),
                _scope_result_for((100,)),
            ]

            result = service_with_schema.import_csv(str(csv_file))

        assert result.scopes_created == 2
        assert result.scope_compositions_created == 2


# ---------------------------------------------------------------------------
# _verify_persisted
# ---------------------------------------------------------------------------


class TestVerifyPersisted:
    def test_passes_silently_when_ecb_organisation_exists(
        self, service_with_schema, sqlite_engine_with_schema
    ):
        session = sessionmaker(bind=sqlite_engine_with_schema)()
        try:
            session.add(
                Organisation(
                    org_id=1,
                    name="European Central Bank",
                    acronym="ECB",
                    id_prefix=1,
                )
            )
            session.commit()
        finally:
            session.close()

        service_with_schema._verify_persisted([])

    def test_raises_when_no_ecb_organisation_exists(self, service_with_schema):
        with pytest.raises(
            EcbValidationsImportError,
            match="no data was persisted",
        ):
            service_with_schema._verify_persisted([])

    def test_error_message_includes_warnings(self, service_with_schema):
        with pytest.raises(EcbValidationsImportError, match="oops"):
            service_with_schema._verify_persisted(["oops"])


# ---------------------------------------------------------------------------
# _format_warnings
# ---------------------------------------------------------------------------


class TestFormatWarnings:
    def test_empty_list_returns_no_warnings_message(self):
        assert (
            _format_warnings([]) == " No warnings were logged during the run."
        )

    def test_small_list_shows_all_warnings_without_omission_note(self):
        result = _format_warnings(["a", "b"])
        assert result == " Warnings logged: ['a', 'b']"
        assert "omitted" not in result

    def test_caps_at_default_limit_of_20(self):
        warnings = [f"warning-{i}" for i in range(25)]

        result = _format_warnings(warnings)

        assert "warning-19" in result
        assert "warning-20" not in result
        assert "(+5 more omitted)" in result

    def test_respects_custom_limit(self):
        result = _format_warnings(["a", "b", "c"], limit=2)

        assert result == " Warnings logged: ['a', 'b'] (+1 more omitted)"


# ---------------------------------------------------------------------------
# _stable_uuid
# ---------------------------------------------------------------------------


class TestStableUuid:
    def test_deterministic_same_input_same_output(self):
        uid1 = _stable_uuid("concept", 42, "my-key")
        uid2 = _stable_uuid("concept", 42, "my-key")
        assert uid1 == uid2

    def test_different_inputs_produce_different_uuids(self):
        uid1 = _stable_uuid("concept", 1, "key-a")
        uid2 = _stable_uuid("concept", 1, "key-b")
        assert uid1 != uid2

    def test_different_prefixes_produce_different_uuids(self):
        uid1 = _stable_uuid("concept", 1, "key")
        uid2 = _stable_uuid("other", 1, "key")
        assert uid1 != uid2

    def test_none_parts_treated_as_empty_string(self):
        # None is converted to "" in the text join, so they produce identical UUIDs
        assert _stable_uuid(None) == _stable_uuid("")
        assert _stable_uuid("a", None, "b") == _stable_uuid("a", "", "b")

    def test_none_part_handled_without_error(self):
        result = _stable_uuid("concept", None, "key")
        assert isinstance(result, str)
        assert len(result) == 38

    def test_output_is_uppercase(self):
        result = _stable_uuid("test")
        assert result == result.upper()

    def test_output_is_valid_uuid_format(self):
        result = _stable_uuid("concept", 1, "key")
        parsed = uuid.UUID(result)
        assert parsed.version == 5

    def test_ordering_of_parts_matters(self):
        uid1 = _stable_uuid("a", "b")
        uid2 = _stable_uuid("b", "a")
        assert uid1 != uid2
