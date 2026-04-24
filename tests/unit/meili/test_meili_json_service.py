import json
from unittest.mock import MagicMock, patch

import pytest
from types import SimpleNamespace

from dpmcore.services.meili_json import (
    BulkDataContext,
    MeiliJsonError,
    MeiliJsonService,
    _chunked_query,
    _iso_date,
    calculate_applicable,
    create_substrings,
    get_scope_module_key,
)


# ---------------------------------------------------------------------------
# create_substrings
# ---------------------------------------------------------------------------

def test_create_substrings_produces_all_contiguous():
    result = create_substrings("ABC")
    assert "A" in result
    assert "AB" in result
    assert "ABC" in result
    assert "B" in result
    assert "BC" in result
    assert "C" in result


def test_create_substrings_empty_string_returns_empty():
    assert create_substrings("") == ""


def test_create_substrings_none_returns_empty():
    assert create_substrings(None) == ""


def test_create_substrings_single_char():
    result = create_substrings("X")
    assert "X" in result


# ---------------------------------------------------------------------------
# _iso_date
# ---------------------------------------------------------------------------

def test_iso_date_none_returns_none():
    assert _iso_date(None) is None


def test_iso_date_with_isoformat_object():
    from datetime import date
    assert _iso_date(date(2024, 1, 15)) == "2024-01-15"


def test_iso_date_fallback_to_str():
    assert _iso_date("2024-01-15") == "2024-01-15"


# ---------------------------------------------------------------------------
# get_scope_module_key
# ---------------------------------------------------------------------------

def test_get_scope_module_key_stable_order():
    modules = [
        {"code": "B", "moduleVersionNumber": "1.0"},
        {"code": "A", "moduleVersionNumber": "2.0"},
    ]
    key = get_scope_module_key(modules)
    assert key == (("A", "2.0"), ("B", "1.0"))


def test_get_scope_module_key_same_modules_equal():
    modules_a = [{"code": "A", "moduleVersionNumber": "1.0"}]
    modules_b = [{"code": "A", "moduleVersionNumber": "1.0"}]
    assert get_scope_module_key(modules_a) == get_scope_module_key(modules_b)


def test_get_scope_module_key_different_modules_not_equal():
    modules_a = [{"code": "A", "moduleVersionNumber": "1.0"}]
    modules_b = [{"code": "B", "moduleVersionNumber": "1.0"}]
    assert get_scope_module_key(modules_a) != get_scope_module_key(modules_b)


def test_get_scope_module_key_none_values_coerced_to_empty_string():
    modules = [{"code": None, "moduleVersionNumber": None}]
    key = get_scope_module_key(modules)
    assert key == (("", ""),)


# ---------------------------------------------------------------------------
# calculate_applicable
# ---------------------------------------------------------------------------

def test_calculate_applicable_empty_modules_returns_false():
    assert calculate_applicable([]) is False


def test_calculate_applicable_single_module_open_ended():
    modules = [
        {
            "moduleVersionFromReferenceDate": "2024-01-01",
            "moduleVersionToReferenceDate": None,
        }
    ]
    assert calculate_applicable(modules) is True


def test_calculate_applicable_single_module_no_from_date():
    modules = [{"moduleVersionFromReferenceDate": None, "moduleVersionToReferenceDate": None}]
    assert calculate_applicable(modules) is False


def test_calculate_applicable_single_module_closed_same_dates():
    modules = [
        {
            "moduleVersionFromReferenceDate": "2024-01-01",
            "moduleVersionToReferenceDate": "2024-01-01",
        }
    ]
    assert calculate_applicable(modules) is False


def test_calculate_applicable_single_module_valid_date_range():
    modules = [
        {
            "moduleVersionFromReferenceDate": "2024-01-01",
            "moduleVersionToReferenceDate": "2025-01-01",
        }
    ]
    assert calculate_applicable(modules) is True


def test_calculate_applicable_multiple_modules_all_open():
    modules = [
        {"moduleVersionFromReferenceDate": "2024-01-01", "moduleVersionToReferenceDate": None},
        {"moduleVersionFromReferenceDate": "2023-01-01", "moduleVersionToReferenceDate": None},
    ]
    assert calculate_applicable(modules) is True


def test_calculate_applicable_multiple_modules_no_from_dates():
    modules = [
        {"moduleVersionFromReferenceDate": None, "moduleVersionToReferenceDate": None},
        {"moduleVersionFromReferenceDate": None, "moduleVersionToReferenceDate": None},
    ]
    assert calculate_applicable(modules) is False


def test_calculate_applicable_multiple_modules_max_from_equals_min_to():
    modules = [
        {"moduleVersionFromReferenceDate": "2025-01-01", "moduleVersionToReferenceDate": "2025-06-01"},
        {"moduleVersionFromReferenceDate": "2024-01-01", "moduleVersionToReferenceDate": "2025-01-01"},
    ]
    assert calculate_applicable(modules) is False


def test_calculate_applicable_multiple_modules_valid_range():
    modules = [
        {"moduleVersionFromReferenceDate": "2023-01-01", "moduleVersionToReferenceDate": "2025-01-01"},
        {"moduleVersionFromReferenceDate": "2024-01-01", "moduleVersionToReferenceDate": "2026-01-01"},
    ]
    assert calculate_applicable(modules) is True


# ---------------------------------------------------------------------------
# _chunked_query
# ---------------------------------------------------------------------------

def test_chunked_query_single_chunk():
    mock_query = MagicMock()
    mock_query.filter.return_value.all.return_value = ["row1", "row2"]

    result = _chunked_query(mock_query, MagicMock(), [1, 2, 3])

    assert mock_query.filter.call_count == 1
    assert result == ["row1", "row2"]


def test_chunked_query_splits_into_multiple_chunks():
    mock_query = MagicMock()
    mock_query.filter.return_value.all.return_value = ["row"]

    ids = list(range(1001))  # 1001 > 999 → 2 chunks
    result = _chunked_query(mock_query, MagicMock(), ids)

    assert mock_query.filter.call_count == 2
    assert len(result) == 2


def test_chunked_query_empty_ids_returns_empty():
    mock_query = MagicMock()

    result = _chunked_query(mock_query, MagicMock(), [])

    mock_query.filter.assert_not_called()
    assert result == []


# ---------------------------------------------------------------------------
# MeiliJsonService._get_operation_info_optimized
# ---------------------------------------------------------------------------

def test_get_operation_info_optimized_no_nodes_returns_empty():
    service = MeiliJsonService(MagicMock())
    assert service._get_operation_info_optimized(operation_vid=1, ctx=BulkDataContext()) == []


def test_get_operation_info_optimized_returns_location_data():
    service = MeiliJsonService(MagicMock())
    ctx = BulkDataContext()

    node = MagicMock()
    node.node_id = 10
    ctx.nodes_by_opvid[1] = [node]

    ref = MagicMock()
    ref.operand_reference_id = 20
    ref.variable_id = 5
    ctx.refs_by_nodeid[10] = [ref]
    ctx.operand_ref_map[20] = 5

    loc = MagicMock()
    loc.cell_id = 100
    loc.table = "T_01"
    loc.row = "01"
    loc.column = "001"
    loc.sheet = "S1"
    ctx.locations_by_refid[20] = [loc]

    result = service._get_operation_info_optimized(operation_vid=1, ctx=ctx)

    assert len(result) == 1
    assert result[0]["table"] == "T_01"
    assert result[0]["row"] == "01"
    assert result[0]["cellid_id"] == 100
    assert result[0]["variableid"] == 5


def test_get_operation_info_optimized_no_locations_returns_empty():
    service = MeiliJsonService(MagicMock())
    ctx = BulkDataContext()

    node = MagicMock()
    node.node_id = 10
    ctx.nodes_by_opvid[1] = [node]
    # refs_by_nodeid is empty → no refs → no locations

    result = service._get_operation_info_optimized(operation_vid=1, ctx=ctx)
    assert result == []


# ---------------------------------------------------------------------------
# MeiliJsonService._process_scope_compositions
# ---------------------------------------------------------------------------

def test_process_scope_compositions_empty_context_returns_empty():
    service = MeiliJsonService(MagicMock())
    scope = MagicMock()
    scope.operation_scope_id = 1

    result = service._process_scope_compositions(
        scope=scope, ctx=BulkDataContext(), include_release_info=False
    )
    assert result == []


def test_process_scope_compositions_skips_none_module_version():
    service = MeiliJsonService(MagicMock())
    scope = MagicMock()
    scope.operation_scope_id = 1
    ctx = BulkDataContext()

    comp = MagicMock()
    comp.module_version = None
    ctx.compositions_by_scopeid[1] = [comp]

    result = service._process_scope_compositions(
        scope=scope, ctx=ctx, include_release_info=False
    )
    assert result == []


def test_process_scope_compositions_returns_module_payload():
    service = MeiliJsonService(MagicMock())
    scope = MagicMock()
    scope.operation_scope_id = 1
    ctx = BulkDataContext()

    comp = MagicMock()
    comp.module_version.code = "B1"
    comp.module_version.name = "B1 Module"
    comp.module_version.version_number = "1.0"
    comp.module_version.from_reference_date = None
    comp.module_version.to_reference_date = None
    comp.module_version.module.framework.code = "FW"
    comp.module_version.module.framework.name = "Framework"
    ctx.compositions_by_scopeid[1] = [comp]

    result = service._process_scope_compositions(
        scope=scope, ctx=ctx, include_release_info=False
    )

    assert len(result) == 1
    assert result[0]["code"] == "B1"
    assert result[0]["frameworkCode"] == "FW"
    assert "moduleVersionStartReleaseCode" not in result[0]


def test_process_scope_compositions_include_release_info_adds_release_fields():
    service = MeiliJsonService(MagicMock())
    scope = MagicMock()
    scope.operation_scope_id = 1
    ctx = BulkDataContext()

    comp = MagicMock()
    comp.module_version.code = "B1"
    comp.module_version.name = "B1 Module"
    comp.module_version.version_number = "1.0"
    comp.module_version.from_reference_date = None
    comp.module_version.to_reference_date = None
    comp.module_version.start_release = None
    comp.module_version.end_release = None
    ctx.compositions_by_scopeid[1] = [comp]

    result = service._process_scope_compositions(
        scope=scope, ctx=ctx, include_release_info=True
    )

    assert len(result) == 1
    assert "moduleVersionStartReleaseCode" in result[0]
    assert "moduleVersionEndReleaseCode" in result[0]
    assert result[0]["moduleVersionStartReleaseCode"] is None
    assert result[0]["moduleVersionEndReleaseCode"] is None


# ---------------------------------------------------------------------------
# MeiliJsonService._build_payload
# ---------------------------------------------------------------------------

def test_build_payload_skips_none_operation():
    service = MeiliJsonService(MagicMock())
    op_version = MagicMock()
    op_version.operation = None

    assert service._build_payload([op_version], BulkDataContext()) == []


def test_build_payload_skips_precondition_type():
    service = MeiliJsonService(MagicMock())
    op_version = MagicMock()
    op_version.operation.type = "precondition"

    assert service._build_payload([op_version], BulkDataContext()) == []


def test_build_payload_skips_empty_expression():
    service = MeiliJsonService(MagicMock())
    op_version = MagicMock()
    op_version.operation.type = "validation"
    op_version.expression = "   "

    assert service._build_payload([op_version], BulkDataContext()) == []


def test_build_payload_skips_none_expression():
    service = MeiliJsonService(MagicMock())
    op_version = MagicMock()
    op_version.operation.type = "validation"
    op_version.expression = None

    assert service._build_payload([op_version], BulkDataContext()) == []


def test_build_payload_valid_operation_produces_record():
    service = MeiliJsonService(MagicMock())

    op_version = MagicMock()
    op_version.operation_vid = 42
    op_version.operation.type = "validation"
    op_version.expression = "x > 0"
    op_version.operation.group_operation_id = None
    op_version.precondition_operation = None
    op_version.operation.concept = None  # no owner

    result = service._build_payload([op_version], BulkDataContext())

    assert len(result) == 1
    record = result[0]
    assert record["ID"] == 42
    assert record["expression"] == "x > 0"
    assert record["ownerAcronym"] is None
    assert record["ownerName"] is None
    assert record["precondition"] is None
    assert record["parentoperationVID"] is None
    assert record["crossmodule"] is False
    assert record["multiscope"] is False
    assert record["operationScopes"] == []
    assert record["versions"] == []


def test_build_payload_sets_precondition_data_when_present():
    service = MeiliJsonService(MagicMock())

    op_version = MagicMock()
    op_version.operation_vid = 10
    op_version.operation.type = "validation"
    op_version.expression = "x > 0"
    op_version.operation.group_operation_id = None
    op_version.operation.concept = None
    op_version.precondition_operation.operation_vid = 99
    op_version.precondition_operation.expression = "y != 0"

    result = service._build_payload([op_version], BulkDataContext())

    assert len(result) == 1
    assert result[0]["precondition"] == {
        "preconditionVID": 99,
        "preconditionExpression": "y != 0",
    }


def test_build_payload_mixed_valid_and_skipped():
    service = MeiliJsonService(MagicMock())

    valid = MagicMock()
    valid.operation_vid = 1
    valid.operation.type = "validation"
    valid.expression = "a > 0"
    valid.operation.group_operation_id = None
    valid.precondition_operation = None
    valid.operation.concept = None

    precondition = MagicMock()
    precondition.operation.type = "precondition"

    no_expr = MagicMock()
    no_expr.operation.type = "validation"
    no_expr.expression = ""

    result = service._build_payload([valid, precondition, no_expr], BulkDataContext())

    assert len(result) == 1
    assert result[0]["ID"] == 1


def _make_op_version(*, vid: int, operation_id: int = 10):
    op = MagicMock()
    op.operation_vid = vid
    op.operation_id = operation_id
    op.operation.type = "validation"
    op.expression = "x > 0"
    op.operation.group_operation_id = None
    op.precondition_operation = None
    op.operation.concept = None
    return op


def _make_composition(code: str, module_vid: int = 0, scope_id: int = 0):
    comp = MagicMock()
    # These two ints are needed by the sorted() key in _process_scope_compositions.
    comp.module_vid = module_vid
    comp.operation_scope_id = scope_id
    comp.module_version.code = code
    comp.module_version.name = f"Module {code}"
    comp.module_version.version_number = "1.0"
    comp.module_version.from_reference_date = "2024-01-01"
    comp.module_version.to_reference_date = None
    comp.module_version.module.framework = None
    return comp


def test_build_payload_scope_with_single_module():
    service = MeiliJsonService(MagicMock())
    op_version = _make_op_version(vid=42)
    ctx = BulkDataContext()

    scope = MagicMock()
    scope.operation_scope_id = 1
    scope.severity = "warning"
    scope.is_active = -1
    ctx.scopes_by_opvid[42] = [scope]
    ctx.compositions_by_scopeid[1] = [_make_composition("M1")]

    result = service._build_payload([op_version], ctx)

    assert len(result) == 1
    record = result[0]
    assert record["crossmodule"] is False
    assert record["multiscope"] is False
    assert len(record["operationScopes"]) == 1
    scope_entry = record["operationScopes"][0]
    assert scope_entry["operationScopeSeverity"] == "Warning"
    assert scope_entry["isActive"] is True
    assert scope_entry["applicable"] is True   # open-ended from date
    assert scope_entry["modules"][0]["code"] == "M1"


def test_build_payload_scope_with_none_severity():
    service = MeiliJsonService(MagicMock())
    op_version = _make_op_version(vid=1)
    ctx = BulkDataContext()

    scope = MagicMock()
    scope.operation_scope_id = 1
    scope.severity = None
    scope.is_active = 0
    ctx.scopes_by_opvid[1] = [scope]

    result = service._build_payload([op_version], ctx)

    assert result[0]["operationScopes"][0]["operationScopeSeverity"] is None


def test_build_payload_crossmodule_detected_when_scope_has_two_modules():
    service = MeiliJsonService(MagicMock())
    op_version = _make_op_version(vid=42)
    ctx = BulkDataContext()

    scope = MagicMock()
    scope.operation_scope_id = 1
    scope.severity = "fatal"
    scope.is_active = -1
    ctx.scopes_by_opvid[42] = [scope]
    ctx.compositions_by_scopeid[1] = [_make_composition("A"), _make_composition("B")]

    result = service._build_payload([op_version], ctx)

    record = result[0]
    assert record["crossmodule"] is True
    assert set(record["crossmodulemodules"]) == {"A", "B"}
    assert record["multiscope"] is False


def test_build_payload_multiscope_detected_when_scopes_have_different_modules():
    service = MeiliJsonService(MagicMock())
    op_version = _make_op_version(vid=42)
    ctx = BulkDataContext()

    s1 = MagicMock()
    s1.operation_scope_id = 1
    s1.severity = "warning"
    s1.is_active = -1

    s2 = MagicMock()
    s2.operation_scope_id = 2
    s2.severity = "fatal"
    s2.is_active = -1

    ctx.scopes_by_opvid[42] = [s1, s2]
    ctx.compositions_by_scopeid[1] = [_make_composition("A")]
    ctx.compositions_by_scopeid[2] = [_make_composition("B")]

    result = service._build_payload([op_version], ctx)

    record = result[0]
    assert record["multiscope"] is True
    assert set(record["multiscopemodules"]) == {"A", "B"}
    assert record["crossmodule"] is False   # each scope has only 1 module


def test_build_payload_deduplicates_scopes_with_identical_module_key():
    service = MeiliJsonService(MagicMock())
    op_version = _make_op_version(vid=42)
    ctx = BulkDataContext()

    s1 = MagicMock()
    s1.operation_scope_id = 1
    s1.severity = "warning"
    s1.is_active = -1

    s2 = MagicMock()
    s2.operation_scope_id = 2
    s2.severity = "fatal"
    s2.is_active = -1

    ctx.scopes_by_opvid[42] = [s1, s2]
    # Both scopes share the same composition → same module key → s2 deduped
    comp = _make_composition("M1")
    ctx.compositions_by_scopeid[1] = [comp]
    ctx.compositions_by_scopeid[2] = [comp]

    result = service._build_payload([op_version], ctx)

    assert len(result[0]["operationScopes"]) == 1


def test_build_payload_previous_versions_included():
    service = MeiliJsonService(MagicMock())
    op_version = _make_op_version(vid=42, operation_id=10)
    ctx = BulkDataContext()

    prev = MagicMock()
    prev.operation_vid = 41
    prev.operation_id = 10
    prev.operation.group_operation_id = None
    prev.precondition_operation = None
    ctx.all_versions_by_opid[10] = [prev]

    result = service._build_payload([op_version], ctx)

    assert len(result) == 1
    versions = result[0]["versions"]
    assert len(versions) == 1
    assert versions[0]["ID"] == 41
    assert "operationScopes" in versions[0]
    assert "operandReferences" in versions[0]


def test_build_payload_previous_version_with_precondition():
    service = MeiliJsonService(MagicMock())
    op_version = _make_op_version(vid=42, operation_id=10)
    ctx = BulkDataContext()

    prev = MagicMock()
    prev.operation_vid = 41
    prev.operation_id = 10
    prev.operation.group_operation_id = None
    prev.precondition_operation.operation_vid = 99
    prev.precondition_operation.expression = "y != 0"
    ctx.all_versions_by_opid[10] = [prev]

    result = service._build_payload([op_version], ctx)

    precond = result[0]["versions"][0]["precondition"]
    assert precond == {"preconditionVID": 99, "preconditionExpression": "y != 0"}


def test_build_payload_parent_operation_resolved():
    service = MeiliJsonService(MagicMock())
    op_version = _make_op_version(vid=42)
    op_version.operation.group_operation_id = 5
    ctx = BulkDataContext()

    parent_ver = MagicMock()
    parent_ver.operation_vid = 99
    parent_ver.expression = "parent_expr"
    ctx.parent_first_versions[5] = parent_ver

    result = service._build_payload([op_version], ctx)

    assert result[0]["parentoperationVID"] == 99
    assert result[0]["parentoperationexpression"] == "parent_expr"


def test_build_payload_tables_field_populated_from_references():
    service = MeiliJsonService(MagicMock())
    op_version = _make_op_version(vid=42)
    ctx = BulkDataContext()

    node = MagicMock()
    node.node_id = 10
    ctx.nodes_by_opvid[42] = [node]

    ref = MagicMock()
    ref.operand_reference_id = 20
    ref.variable_id = None
    ctx.refs_by_nodeid[10] = [ref]
    ctx.operand_ref_map[20] = None

    loc = MagicMock()
    loc.cell_id = 1
    loc.table = "T_01"
    loc.row = "01"
    loc.column = "001"
    loc.sheet = "S1"
    ctx.locations_by_refid[20] = [loc]

    result = service._build_payload([op_version], ctx)

    assert "T_01" in result[0]["tables"]


# ---------------------------------------------------------------------------
# MeiliJsonService.generate
# ---------------------------------------------------------------------------

def test_generate_requires_session(tmp_path):
    service = MeiliJsonService()

    with pytest.raises(MeiliJsonError, match="database session is required"):
        service.generate(str(tmp_path / "operations.json"))


def test_generate_empty_result_writes_empty_json(tmp_path):
    service = MeiliJsonService(MagicMock())

    with patch.object(service, "_get_operation_versions", return_value=[]):
        result = service.generate(str(tmp_path / "operations.json"))

    assert result.operations_written == 0
    assert json.loads((tmp_path / "operations.json").read_text()) == []


def test_generate_creates_parent_directories(tmp_path):
    service = MeiliJsonService(MagicMock())
    nested_output = tmp_path / "subdir" / "deep" / "operations.json"

    with patch.object(service, "_get_operation_versions", return_value=[]):
        result = service.generate(str(nested_output))

    assert nested_output.exists()
    assert result.operations_written == 0


def test_generate_with_data_writes_payload_and_returns_count(tmp_path):
    service = MeiliJsonService(MagicMock())
    output = tmp_path / "ops.json"

    payload = [{"ID": 1, "expression": "x > 0"}, {"ID": 2, "expression": "y < 5"}]

    with patch.object(service, "_get_operation_versions", return_value=[MagicMock()]), \
         patch.object(service, "_bulk_load_related_data", return_value=BulkDataContext()), \
         patch.object(service, "_build_payload", return_value=payload):
        result = service.generate(str(output))

    assert result.operations_written == 2
    assert json.loads(output.read_text()) == payload


# ---------------------------------------------------------------------------
# MeiliJsonService.merge_by_owner
# ---------------------------------------------------------------------------

def test_merge_by_owner_replaces_matching_owner(tmp_path):
    new_file = tmp_path / "new.json"
    existing_file = tmp_path / "existing.json"
    output_file = tmp_path / "merged.json"

    new_file.write_text(
        json.dumps(
            [
                {"ID": 20, "ownerAcronym": "EBA"},
                {"ID": 21, "ownerAcronym": "EBA"},
            ]
        ),
        encoding="utf-8",
    )
    existing_file.write_text(
        json.dumps(
            [
                {"ID": 1, "ownerAcronym": "ECB"},
                {"ID": 2, "ownerAcronym": "EBA"},
                {"ID": 3, "ownerAcronym": "EBA"},
            ]
        ),
        encoding="utf-8",
    )

    service = MeiliJsonService()
    result = service.merge_by_owner(
        new_file=str(new_file),
        existing_file=str(existing_file),
        output_file=str(output_file),
    )

    merged = json.loads(output_file.read_text(encoding="utf-8"))

    assert result.operations_written == 3
    assert [item["ID"] for item in merged] == [1, 20, 21]


def test_merge_by_owner_empty_new_file_keeps_all_existing(tmp_path):
    new_file = tmp_path / "new.json"
    existing_file = tmp_path / "existing.json"
    output_file = tmp_path / "merged.json"

    new_file.write_text("[]", encoding="utf-8")
    existing_file.write_text(
        json.dumps([{"ID": 1, "ownerAcronym": "ECB"}, {"ID": 2, "ownerAcronym": "EBA"}]),
        encoding="utf-8",
    )

    service = MeiliJsonService()
    result = service.merge_by_owner(
        new_file=str(new_file),
        existing_file=str(existing_file),
        output_file=str(output_file),
    )

    merged = json.loads(output_file.read_text())
    assert result.operations_written == 2
    assert {item["ownerAcronym"] for item in merged} == {"ECB", "EBA"}


def test_merge_by_owner_file_not_found_raises(tmp_path):
    service = MeiliJsonService()

    with pytest.raises(MeiliJsonError, match="File not found"):
        service.merge_by_owner(
            new_file=str(tmp_path / "nonexistent.json"),
            existing_file=str(tmp_path / "existing.json"),
            output_file=str(tmp_path / "out.json"),
        )


def test_merge_by_owner_invalid_json_raises(tmp_path):
    new_file = tmp_path / "new.json"
    existing_file = tmp_path / "existing.json"
    new_file.write_text("not valid json", encoding="utf-8")
    existing_file.write_text("[]", encoding="utf-8")

    service = MeiliJsonService()
    with pytest.raises(MeiliJsonError, match="Invalid JSON"):
        service.merge_by_owner(
            new_file=str(new_file),
            existing_file=str(existing_file),
            output_file=str(tmp_path / "out.json"),
        )


def test_merge_by_owner_output_sorted_by_id(tmp_path):
    new_file = tmp_path / "new.json"
    existing_file = tmp_path / "existing.json"
    output_file = tmp_path / "merged.json"

    new_file.write_text(json.dumps([{"ID": 5, "ownerAcronym": "EBA"}]), encoding="utf-8")
    existing_file.write_text(
        json.dumps([{"ID": 10, "ownerAcronym": "ECB"}, {"ID": 1, "ownerAcronym": "ECB"}]),
        encoding="utf-8",
    )

    service = MeiliJsonService()
    service.merge_by_owner(
        new_file=str(new_file),
        existing_file=str(existing_file),
        output_file=str(output_file),
    )

    merged = json.loads(output_file.read_text())
    ids = [item["ID"] for item in merged]
    assert ids == sorted(ids)


class _FakeQuery:
    def __init__(self, model, result=None):
        self.model = model
        self.result = result or []
        self.join_called = False
        self.options_called = False
        self.order_by_called = False

    def join(self, *args, **kwargs):
        self.join_called = True
        return self

    def options(self, *args, **kwargs):
        self.options_called = True
        return self

    def order_by(self, *args, **kwargs):
        self.order_by_called = True
        return self

    def all(self):
        return self.result


class _FakeSession:
    def __init__(self, result=None):
        self.result = result or []
        self.queries = []

    def query(self, model):
        query = _FakeQuery(model, self.result)
        self.queries.append(query)
        return query


def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


def _release(release_id, code):
    return _ns(release_id=release_id, code=code)


def _operation(
    *,
    operation_id=10,
    group_operation_id=None,
    code="OP_001",
    source="EBA",
    type_="validation",
    concept=None,
):
    return _ns(
        operation_id=operation_id,
        group_operation_id=group_operation_id,
        code=code,
        source=source,
        type=type_,
        concept=concept,
    )


def _operation_version(
    *,
    operation_vid,
    operation_id=10,
    operation=None,
    expression="x > 0",
    description="Description",
    endorsement="Endorsed",
    start_release=None,
    end_release=None,
    precondition_operation=None,
):
    return _ns(
        operation_vid=operation_vid,
        operation_id=operation_id,
        operation=operation,
        expression=expression,
        description=description,
        endorsement=endorsement,
        start_release=start_release,
        end_release=end_release,
        precondition_operation=precondition_operation,
    )


def _scope(*, scope_id, operation_vid, severity="warning", is_active=-1):
    return _ns(
        operation_scope_id=scope_id,
        operation_vid=operation_vid,
        severity=severity,
        is_active=is_active,
    )


def _module_version(
    *,
    code="M1",
    name="Module 1",
    version_number="1.0",
    framework=None,
    start_release=None,
    end_release=None,
    from_reference_date="2024-01-01",
    to_reference_date=None,
):
    module = _ns(framework=framework)
    return _ns(
        code=code,
        name=name,
        version_number=version_number,
        module=module,
        start_release=start_release,
        end_release=end_release,
        from_reference_date=from_reference_date,
        to_reference_date=to_reference_date,
    )


def _composition(*, scope_id, module_vid, module_version):
    return _ns(
        operation_scope_id=scope_id,
        module_vid=module_vid,
        module_version=module_version,
    )


def test_get_operation_versions_uses_expected_query_chain():
    op_version = _operation_version(
        operation_vid=1,
        operation=_operation(),
    )
    session = _FakeSession(result=[op_version])
    service = MeiliJsonService(session)

    result = service._get_operation_versions()

    assert result == [op_version]
    assert len(session.queries) == 1
    assert session.queries[0].join_called is True
    assert session.queries[0].options_called is True
    assert session.queries[0].order_by_called is True


def test_bulk_load_related_data_empty_operation_vids_returns_empty_context():
    service = MeiliJsonService(_FakeSession())

    ctx = service._bulk_load_related_data(
        operation_versions=[],
        operation_vids=[],
    )

    assert ctx.scopes_by_opvid == {}
    assert ctx.compositions_by_scopeid == {}
    assert ctx.parent_first_versions == {}
    assert ctx.all_versions_by_opid == {}
    assert ctx.nodes_by_opvid == {}
    assert ctx.refs_by_nodeid == {}
    assert ctx.operand_ref_map == {}
    assert ctx.locations_by_refid == {}


def test_bulk_load_related_data_populates_all_lookup_contexts():
    current_operation = _operation(operation_id=100, group_operation_id=200)
    current_version = _operation_version(
        operation_vid=10,
        operation_id=100,
        operation=current_operation,
    )
    previous_version = _operation_version(
        operation_vid=9,
        operation_id=100,
        operation=current_operation,
    )
    ignored_version = _operation_version(
        operation_vid=99,
        operation_id=None,
        operation=current_operation,
    )

    current_scope = _scope(scope_id=1000, operation_vid=10)
    previous_scope = _scope(scope_id=900, operation_vid=9)
    ignored_scope = _scope(scope_id=999, operation_vid=None)

    current_composition = _composition(
        scope_id=1000,
        module_vid=1,
        module_version=_module_version(code="CUR"),
    )
    previous_composition = _composition(
        scope_id=900,
        module_vid=2,
        module_version=_module_version(code="PREV"),
    )

    parent_first = _operation_version(
        operation_vid=1,
        operation_id=200,
        operation=_operation(operation_id=200),
        expression="parent first",
    )
    parent_second = _operation_version(
        operation_vid=2,
        operation_id=200,
        operation=_operation(operation_id=200),
        expression="parent second",
    )

    current_node = _ns(operation_vid=10, node_id=500)
    ignored_node = _ns(operation_vid=None, node_id=501)

    reference = _ns(
        operand_reference_id=700,
        node_id=500,
        variable_id=800,
    )
    ignored_reference = _ns(
        operand_reference_id=701,
        node_id=None,
        variable_id=801,
    )

    location = _ns(
        operand_reference_id=700,
        cell_id=900,
        table="T_01",
        row="01",
        column="001",
        sheet="S1",
    )

    def fake_chunked_query(base_query, column, ids):
        model_name = base_query.model.__name__

        if model_name == "OperationScope":
            ids = set(ids)
            if ids == {10}:
                return [current_scope, ignored_scope]
            if ids == {9}:
                return [previous_scope]
            return []

        if model_name == "OperationScopeComposition":
            ids = set(ids)
            if ids == {1000, 999}:
                return [current_composition]
            if ids == {900}:
                return [previous_composition]
            return []

        if model_name == "OperationVersion":
            ids = set(ids)
            if ids == {200}:
                return [parent_first, parent_second]
            if ids == {100}:
                return [current_version, previous_version, ignored_version]
            return []

        if model_name == "OperationNode":
            return [current_node, ignored_node]

        if model_name == "OperandReference":
            return [reference, ignored_reference]

        if model_name == "OperandReferenceLocation":
            return [location]

        return []

    service = MeiliJsonService(_FakeSession())

    with patch(
        "dpmcore.services.meili_json._chunked_query",
        side_effect=fake_chunked_query,
    ):
        ctx = service._bulk_load_related_data(
            operation_versions=[current_version],
            operation_vids=[10],
        )

    assert ctx.scopes_by_opvid[10] == [current_scope]
    assert ctx.scopes_by_opvid[9] == [previous_scope]

    assert ctx.compositions_by_scopeid[1000] == [current_composition]
    assert ctx.compositions_by_scopeid[900] == [previous_composition]

    assert ctx.parent_first_versions[200] == parent_first
    assert ctx.all_versions_by_opid[100] == [current_version, previous_version]

    assert ctx.nodes_by_opvid[10] == [current_node]
    assert ctx.refs_by_nodeid[500] == [reference]
    assert ctx.operand_ref_map[700] == 800
    assert ctx.operand_ref_map[701] == 801
    assert ctx.locations_by_refid[700] == [location]


def test_build_payload_includes_owner_and_release_fields():
    owner = _ns(acronym="EBA", name="European Banking Authority")
    concept = _ns(owner=owner)

    operation = _operation(
        operation_id=10,
        group_operation_id=None,
        code="OP_001",
        source="DPM",
        type_="validation",
        concept=concept,
    )
    op_version = _operation_version(
        operation_vid=42,
        operation_id=10,
        operation=operation,
        expression="x > 0",
        start_release=_release(1, "3.4"),
        end_release=_release(2, "3.5"),
    )

    service = MeiliJsonService(MagicMock())
    result = service._build_payload([op_version], BulkDataContext())

    record = result[0]

    assert record["ownerAcronym"] == "EBA"
    assert record["ownerName"] == "European Banking Authority"
    assert record["startReleaseId"] == 1
    assert record["startReleaseCode"] == "3.4"
    assert record["endReleaseId"] == 2
    assert record["endReleaseCode"] == "3.5"


def test_build_payload_previous_version_includes_release_parent_scopes_and_references():
    operation = _operation(
        operation_id=10,
        group_operation_id=None,
        code="OP_CURRENT",
        source="DPM",
        type_="validation",
        concept=None,
    )
    current = _operation_version(
        operation_vid=42,
        operation_id=10,
        operation=operation,
        expression="current expression",
    )

    previous_operation = _operation(
        operation_id=10,
        group_operation_id=5,
        code="OP_PREVIOUS",
        source="DPM",
        type_="validation",
        concept=None,
    )
    previous = _operation_version(
        operation_vid=41,
        operation_id=10,
        operation=previous_operation,
        expression="previous expression",
        description="previous description",
        endorsement="previous endorsement",
        start_release=_release(1, "3.3"),
        end_release=_release(2, "3.4"),
        precondition_operation=_ns(
            operation_vid=30,
            expression="precondition expression",
        ),
    )

    parent = _operation_version(
        operation_vid=5,
        operation_id=5,
        operation=_operation(operation_id=5),
        expression="parent expression",
    )

    ctx = BulkDataContext()
    ctx.all_versions_by_opid[10] = [current, previous]
    ctx.parent_first_versions[5] = parent

    previous_scope_1 = _scope(scope_id=100, operation_vid=41, severity="fatal", is_active=-1)
    previous_scope_2 = _scope(scope_id=101, operation_vid=41, severity="warning", is_active=0)

    ctx.scopes_by_opvid[41] = [previous_scope_2, previous_scope_1]

    framework = _ns(code="FW", name="Framework")
    module_version = _module_version(
        code="M1",
        name="Module 1",
        version_number="1.0",
        framework=framework,
        start_release=_release(1, "3.3"),
        end_release=_release(2, "3.4"),
    )

    ctx.compositions_by_scopeid[100] = [
        _composition(scope_id=100, module_vid=1, module_version=module_version)
    ]
    ctx.compositions_by_scopeid[101] = [
        _composition(scope_id=101, module_vid=1, module_version=module_version)
    ]

    node = _ns(operation_vid=41, node_id=500)
    reference = _ns(operand_reference_id=700, node_id=500, variable_id=800)
    location = _ns(
        operand_reference_id=700,
        cell_id=900,
        table="T_PREV",
        row="01",
        column="001",
        sheet="S1",
    )

    ctx.nodes_by_opvid[41] = [node]
    ctx.refs_by_nodeid[500] = [reference]
    ctx.operand_ref_map[700] = 800
    ctx.locations_by_refid[700] = [location]

    service = MeiliJsonService(MagicMock())
    result = service._build_payload([current], ctx)

    versions = result[0]["versions"]
    assert len(versions) == 1

    previous_payload = versions[0]

    assert previous_payload["ID"] == 41
    assert previous_payload["operationId"] == 10
    assert previous_payload["description"] == "previous description"
    assert previous_payload["expression"] == "previous expression"
    assert previous_payload["operationcode"] == "OP_PREVIOUS"
    assert previous_payload["operationsource"] == "DPM"
    assert previous_payload["operationtype"] == "validation"
    assert previous_payload["endorsement"] == "previous endorsement"

    assert previous_payload["precondition"] == {
        "preconditionVID": 30,
        "preconditionExpression": "precondition expression",
    }

    assert previous_payload["startReleaseId"] == 1
    assert previous_payload["startReleaseCode"] == "3.3"
    assert previous_payload["endReleaseId"] == 2
    assert previous_payload["endReleaseCode"] == "3.4"

    assert previous_payload["parentoperationVID"] == 5
    assert previous_payload["parentoperationexpression"] == "parent expression"

    assert len(previous_payload["operationScopes"]) == 1
    assert previous_payload["operationScopes"][0]["modules"][0]["code"] == "M1"
    assert previous_payload["operationScopes"][0]["modules"][0]["frameworkCode"] == "FW"

    assert previous_payload["operandReferences"] == [
        {
            "variableid": 800,
            "cellid_id": 900,
            "table": "T_PREV",
            "row": "01",
            "column": "001",
            "sheet": "S1",
        }
    ]


def test_build_payload_previous_version_with_operation_none_uses_none_fields():
    operation = _operation(
        operation_id=10,
        group_operation_id=None,
        code="OP_CURRENT",
        source="DPM",
        type_="validation",
        concept=None,
    )
    current = _operation_version(
        operation_vid=42,
        operation_id=10,
        operation=operation,
    )

    previous = _operation_version(
        operation_vid=41,
        operation_id=10,
        operation=None,
        expression="old expression",
        precondition_operation=None,
    )

    ctx = BulkDataContext()
    ctx.all_versions_by_opid[10] = [previous]

    service = MeiliJsonService(MagicMock())
    result = service._build_payload([current], ctx)

    previous_payload = result[0]["versions"][0]

    assert previous_payload["operationcode"] is None
    assert previous_payload["operationsource"] is None
    assert previous_payload["operationtype"] is None
    assert previous_payload["parentoperationVID"] is None
    assert previous_payload["parentoperationexpression"] is None


def test_build_payload_payload_is_sorted_by_id():
    service = MeiliJsonService(MagicMock())

    operation_a = _operation(operation_id=1, code="OP_A", concept=None)
    operation_b = _operation(operation_id=2, code="OP_B", concept=None)

    op_high = _operation_version(
        operation_vid=99,
        operation_id=1,
        operation=operation_a,
        expression="high",
    )
    op_low = _operation_version(
        operation_vid=1,
        operation_id=2,
        operation=operation_b,
        expression="low",
    )

    result = service._build_payload([op_high, op_low], BulkDataContext())

    assert [item["ID"] for item in result] == [1, 99]

