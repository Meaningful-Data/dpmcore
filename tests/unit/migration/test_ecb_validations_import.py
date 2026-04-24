import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dpmcore.orm.infrastructure import Organisation
from dpmcore.services.ecb_validations_import import (
    EcbValidationsImportError,
    EcbValidationsImportService,
)

from unittest.mock import MagicMock, patch

@pytest.fixture()
def sqlite_engine():
    return create_engine("sqlite:///:memory:")


@pytest.fixture()
def sqlite_engine_with_schema():
    engine = create_engine("sqlite:///:memory:")
    from dpmcore.orm.base import Base
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def service(sqlite_engine):
    return EcbValidationsImportService(sqlite_engine)


@pytest.fixture()
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
        assert str(service._parse_submission_date("17/03/2026")) == "2026-03-17"
        assert str(service._parse_submission_date("2026-03-17")) == "2026-03-17"
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

    def test_import_csv_missing_columns_raises_via_file(self, service, tmp_path):
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
        assert service._resolve_release({"4.0": mock_release}, "4.0") is mock_release

    def test_resolve_release_returns_none_for_unknown_code(self, service):
        assert service._resolve_release({"4.0": object()}, "5.0") is None

    def test_resolve_release_applies_code_remap(self, service):
        from unittest.mock import MagicMock
        mock_release = MagicMock()
        # _RELEASE_CODE_MAP maps "3.2" → "3.4"
        assert service._resolve_release({"3.4": mock_release}, "3.2") is mock_release

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
            session.add(Organisation(org_id=5, name="Org5", acronym="O5", id_prefix=1))
            session.add(Organisation(org_id=10, name="Org10", acronym="O10", id_prefix=2))
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
            session.add(Release(release_id=1, code="4.0"))
            session.add(Release(release_id=2, code="4.1"))
            session.add(Release(release_id=3, code="4.2"))
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
            session.add(Release(release_id=1, code="4.0"))
            session.add(Release(release_id=2, code="4.1"))
            session.add(Release(release_id=3, code="4.2"))
            session.flush()

            result = EcbValidationsImportService._get_valid_release_ids(
                session, start_release_id=1, end_release_id=3
            )
            assert result == [1, 2]
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
                session, operation_class=None, owner=None
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
            org = Organisation(org_id=1, name="Test", acronym="TST", id_prefix=1)
            cls = DpmClass(class_id=1, name="Operation")
            session.add(org)
            session.add(cls)
            session.flush()

            result = service_with_schema._create_operation_concept(
                session, operation_class=cls, owner=org
            )
            assert result is not None
            assert len(result) == 36  # UUID format
        finally:
            session.close()

    # ------------------------------------------------------------------
    # import_csv end-to-end with minimal DB
    # ------------------------------------------------------------------

    def test_import_csv_unknown_release_creates_operation_and_warns(
        self, service_with_schema, tmp_path
    ):
        csv_file = tmp_path / "valid.csv"
        csv_file.write_text("vr_code,start_release\nV1,4.0\n", encoding="utf-8")

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
        csv_file.write_text("vr_code,start_release\nV1_1,4.0\n", encoding="utf-8")

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
        csv_file.write_text("vr_code,start_release\nV1,4.0\n", encoding="utf-8")

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
            assert service_with_schema._extract_table_codes_for_expression(
                session,
                expression=None,
                start_release_id=1,
                latest_release_id=2,
            ) == set()

            assert service_with_schema._extract_table_codes_for_expression(
                session,
                expression="   ",
                start_release_id=1,
                latest_release_id=2,
            ) == set()
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
            patch("dpmcore.services.ecb_validations_import.SyntaxService") as syntax_cls,
            patch("dpmcore.services.ecb_validations_import.OperandsChecking") as checker_cls,
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
            patch("dpmcore.services.ecb_validations_import.SyntaxService") as syntax_cls,
            patch("dpmcore.services.ecb_validations_import.OperandsChecking") as checker_cls,
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
        csv_file.write_text("vr_code,start_release\nV1,4.0\n", encoding="utf-8")

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