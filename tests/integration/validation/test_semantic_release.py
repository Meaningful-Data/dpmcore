"""Semantic validation integration tests against the fixture database.

Each test validates a DPM-XL expression at a specific release ID using
the SemanticService backed by the fixture SQLite database.
"""

import pytest

from dpmcore.services.semantic import SemanticService


def test_validate_expression_release_1(fixture_session):
    """Expression valid at release_id=1."""
    expression = """
    with {tC_09.02}:
    if
        sum({(r0042, r0050), c0105} group by CEG) > 0
    then
        not(isnull({r0030, c0080}))
    endif
    """
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=1)
    assert result.is_valid, (
        f"Expected valid for release_id=1, but got error: {result.error_message}"
    )


def test_validate_expression_release_5(fixture_session):
    """Same expression should be invalid at release_id=5."""
    expression = """
    with {tC_09.02}:
    if
        sum({(r0042, r0050), c0105} group by CEG) > 0
    then
        not(isnull({r0030, c0080}))
    endif
    """
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert not result.is_valid, (
        "Expected invalid for release_id=5, but it was valid"
    )


def test_nonexistent_release(fixture_session):
    """Non-existing release ID should produce a clear error."""
    expression = "{tC_09.02, r0042, c0105}"
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=9999)
    assert not result.is_valid
    assert "9999" in (result.error_message or "")


def test_hint_expression_release_5(fixture_session):
    """The hint expression from the user should be valid at release_id=5."""
    expression = (
        "with {default: 0, interval: true}: "
        "sum ({tF_32.01, r0010, (c0010, c0060)}) = {tF_01.01, r0380, c0010}"
    )
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"Hint expression failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0022_1_release_5(fixture_session):
    """Test EGDQ_0022_1 expression validation for release_id=5."""
    expression = """with {tC_17.01.a, c0010-0080}:
    if {tC_17.01.b, r0020, c0090, default: 0} < 1000 and {r0050} = {r0060} then {r0010}  in {0, 1} endif"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0022_1 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0052_1_release_5(fixture_session):
    """Test EGDQ_0052_1 expression validation for release_id=5."""
    expression = """if {tF_32.04.b, r0010-0110, c0030} > 0 then {tF_32.04.a, r0010-0110, c0010} > 0 endif"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0052_1 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0058_release_5(fixture_session):
    """Test EGDQ_0058 expression validation for release_id=5."""
    expression = """if not({tC_27.00,c050} in {[eba_CT:x598], [eba_CT:x20]}) then isnull({tC_27.00, c060}) else not(isnull({tC_27.00, c060})) endif"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0058 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0059_release_5(fixture_session):
    """Test EGDQ_0059 expression validation for release_id=5."""
    expression = """if {tC_27.00, c050} = [eba_CT:x598] then len({tC_27.00, c060}) > 8  endif"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0059 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0063_release_5(fixture_session):
    """Test EGDQ_0063 expression validation for release_id=5."""
    expression = """if {tC_27.00, c070} = [eba_ZZ:x662] then ((({tC_27.00, c050} = [eba_CT:x598]) or (isnull({tC_27.00, c050}))) or {tC_27.00, c050} in {[eba_CT:x12], [eba_CT:x599]} and (not ({tC_27.00, c040} in {[eba_GA:AT], [eba_GA:BE], [eba_GA:BG], [eba_GA:CY], [eba_GA:CZ], [eba_GA:DE], [eba_GA:DK], [eba_GA:EE], [eba_GA:ES], [eba_GA:FI], [eba_GA:FR], [eba_GA:GR], [eba_GA:HR], [eba_GA:HU], [eba_GA:IE], [eba_GA:IT], [eba_GA:LT], [eba_GA:LU], [eba_GA:LV], [eba_GA:MT], [eba_GA:NL], [eba_GA:PL], [eba_GA:PT], [eba_GA:RO], [eba_GA:SE], [eba_GA:SI], [eba_GA:SK]}))) endif"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0063 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0084a_release_5(fixture_session):
    """Test EGDQ_0084a expression validation for release_id=5."""
    expression = """({tC_17.01.a, r0910, c0010} >= max_aggr({tC_17.01.a, (r0010, r0110, r0210, r0310, r0410, r0510, r0610, r0710, r0810), c0010})) and ({tC_17.01.a, r0910, c0020} >= max_aggr({tC_17.01.a, (r0010, r0110, r0210, r0310, r0410, r0510, r0610, r0710, r0810), c0020})) and ({tC_17.01.a, r0910, c0030} >= max_aggr({tC_17.01.a, (r0010, r0110, r0210, r0310, r0410, r0510, r0610, r0710, r0810), c0030})) and ({tC_17.01.a, r0910, c0040} >= max_aggr({tC_17.01.a, (r0010, r0110, r0210, r0310, r0410, r0510, r0610, r0710, r0810), c0040})) and ({tC_17.01.a, r0910, c0050} >= max_aggr({tC_17.01.a, (r0010, r0110, r0210, r0310, r0410, r0510, r0610, r0710, r0810), c0050})) and ({tC_17.01.a, r0910, c0060} >= max_aggr({tC_17.01.a, (r0010, r0110, r0210, r0310, r0410, r0510, r0610, r0710, r0810), c0060})) and ({tC_17.01.a, r0910, c0070} >= max_aggr({tC_17.01.a, (r0010, r0110, r0210, r0310, r0410, r0510, r0610, r0710, r0810), c0070})) and ({tC_17.01.a, r0910, c0080} >= max_aggr({tC_17.01.a, (r0010, r0110, r0210, r0310, r0410, r0510, r0610, r0710, r0810), c0080}))"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0084a failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0362e_release_5(fixture_session):
    """Test EGDQ_0362e expression validation for release_id=5."""
    expression = """with {tC_14.00}:
    if {c0110} = [eba_RS:x2] and not({c0160} in {[eba_UE:x3], [eba_UE:x9]}) then
    not(isnull({c0060})) endif"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0362e failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0532_release_5(fixture_session):
    """Test EGDQ_0532 expression validation for release_id=5."""
    expression = """with {tC_22.00, c0080, default: 0}: {r0010} = {r0020}"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0532 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0774_release_5(fixture_session):
    """Test EGDQ_0774 expression validation for release_id=5."""
    expression = """if {tC_47.00, r0300, c0010} > 0 then {tC_47.00, r0440, c0010} = {tC_47.00, r0420, c0010} + {tC_47.00, r0370, c0010} / {tC_47.00, r0300, c0010} endif"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0774 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0921a_release_5(fixture_session):
    """Test EGDQ_0921a expression validation for release_id=5."""
    expression = """with {tJ_05.00.b, (r0010, r0030, r0040, r0050, r0060, r0070, r0090, r0100, r0110, r0120, r0180, r0190, r0200, r0220, r0230, r0240, r0260, r0270, r0290, r0300, r0310, r0330, r0340, r0350, r0370, r0380, r0390, r0410, r0420, r0440, r0450, r0460, r0510, r0520)}:
    if {c0010, default:0} != 0 then not(isnull({c0050})) and {c0050} < 0.5 endif"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0921a failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_C199_release_5(fixture_session):
    """Test EGDQ_C199 expression validation for release_id=5."""
    expression = """with {tC_33.00.a, default: 0}:
    sum({c0290, r0010}[where RCP = [eba_GA:qx2014]]) > 0 and
    sum({c0290, r0010}[where not(RCP in {[eba_GA:qx2014], [eba_GA:qx2000]})]) > 0"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_C199 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0735_release_5(fixture_session):
    """Test EGDQ_0735 expression validation for release_id=5."""
    expression = """with {tC_66.01.a, (c0020, c0030, c0040, c0050, c0060, c0070, c0080, c0090, c0100, c0110, c0120, c0130, c0140, c0150, c0160, c0170, c0180, c0190, c0200, c0210, c0220), default:0, interval:true}: (sum({r0380, s*})) - (sum({r0350, s*})) - (sum({r0360, s*})) >=
    0.9 * ({tF_01.02,r0040,c0010}+{tF_01.02,r0050,c0010}+{tF_01.02,r0060,c0010}+{tF_01.02,r0064,c0010}+{tF_01.02,r0065,c0010}+{tF_01.02,r0066,c0010}+{tF_01.02,r0070,c0010}+{tF_01.02,r0110,c0010}+{tF_01.02,r0141,c0010}+{tF_01.02,r0240,c0010})"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0735 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0861_2_release_5(fixture_session):
    """Test EGDQ_0861_2 expression validation for release_id=5."""
    expression = """with {default:0, interval:true}: {tP_04.01,r010,c020} >= 0.5 *
   ({tP_02.04,r010,c020}*{tP_01.01,r030,c030} + {tP_02.04,r050,c020}*{tP_01.01,r100,c030} + {tP_02.04,r085,c020}*{tP_01.01,r180,c030}
   + {tP_02.04,r120,c020}*{tP_01.01,r190,c030} + {tP_02.04,r160,c020}*{tP_01.01,r195,c030} + {tP_02.04,r170,c020}*{tP_01.01,r197,c030})"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0861_2 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0865_3_release_5(fixture_session):
    """Test EGDQ_0865_3 expression validation for release_id=5."""
    expression = """with {(r010, r090, r200, r210), default:0, interval:true}:
    (abs({tP_04.01, c040} - {tP_04.01, c030})) / max(abs({tP_04.01, c040}), abs({tP_04.01, c030})) < 0.8"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0865_3 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0454b_1_release_5(fixture_session):
    """Test EGDQ_0454b_1 expression validation for release_id=5."""
    expression = """with {tC_66.01.a, s*, default: 0}:
    {r1080, c0030} = {r1080, c0020} + {r1070, c0030}"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0454b_1 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0678_11_release_5(fixture_session):
    """Test EGDQ_0678_11 expression validation for release_id=5."""
    expression = """with {tF_18.00.a, r0195}:
    {tF_04.03.1, r0150, c0030} = {c0057} + {c0109}"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0678_11 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0480_5_release_5(fixture_session):
    """Test EGDQ_0480_5 expression validation for release_id=5."""
    expression = """with {default: 0}:
    sum({tF_18.00.a, (r0050, r0185), (c0080, c0090, c0101, c0102, c0106, c0107)}) +
    sum({tF_18.00.b, (r0050, r0185), (c0170, c0180, c0191, c0192, c0196, c0197)})
    <=
    sum({tF_07.01, r0100, (c0030, c0060, c0090, c0120)}) +
    sum({tF_07.02, r0100, (c0030, c0060)})"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0480_5 failed for release_id=5: {result.error_message}"
    )


def test_EGDQ_0455a_11_release_5(fixture_session):
    """Test EGDQ_0455a_11 expression validation for release_id=5."""
    expression = """with {tC_66.01.a, s*, default: 0}:
    {r0720, c0130} = {r0720, c0120} + {r0710, c0130}"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"EGDQ_0455a_11 failed for release_id=5: {result.error_message}"
    )


def test_item_versioning_release_3(fixture_session):
    """Item versioning expression should be invalid at release_id=3."""
    expression = """
with {tF_40.01}:
    if {c0095} = [eba_CT:x12] and {c0130} = [eba_RP:x1]
    then {tF_40.01, c0095}[get qCIN] = [eba_qCO:qx2010] endif
"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=3)
    assert not result.is_valid, (
        "Expected invalid for release_id=3, but it was valid"
    )


def test_item_versioning_release_5(fixture_session):
    """Item versioning expression should be valid at release_id=5."""
    expression = """
with {tF_40.01}:
    if {c0095} = [eba_CT:x12] and {c0130} = [eba_RP:x1]
    then {tF_40.01, c0095}[get qCIN] = [eba_qCO:qx2010] endif
"""
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert result.is_valid, (
        f"Expected valid for release_id=5, but got error: {result.error_message}"
    )


# ---------------------------------------------------------------------------
# Date extraction operators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "op", ["year", "semester", "quarter", "month", "week", "day"]
)
def test_date_extraction_on_date_literal_valid(op, fixture_session):
    """Each extraction operator accepts a date literal and is semantically valid."""
    result = SemanticService(fixture_session).validate(
        f"{op}(#2022-03-15#)", release_id=5
    )
    assert result.is_valid, (
        f"{op}(#2022-03-15#) should be valid, got: {result.error_message}"
    )


def test_year_extraction_result_usable_in_comparison(fixture_session):
    """Extraction result (Integer) can be compared to an integer literal."""
    result = SemanticService(fixture_session).validate(
        "year(#2022-03-15#) = 2022", release_id=5
    )
    assert result.is_valid, f"Expected valid, got: {result.error_message}"


def test_date_extraction_non_date_type_rejected(fixture_session):
    """Extraction operator rejects a String operand with a type error."""
    result = SemanticService(fixture_session).validate(
        'year("hello")', release_id=5
    )
    assert not result.is_valid
    assert result.error_code == "3-3"


def test_date_extraction_on_recordset_type_checked(fixture_session):
    """Extraction on a record set goes through the record-set path (not the
    constant fast-path); the non-Date fact component is rejected with 3-3.
    """
    result = SemanticService(fixture_session).validate(
        "year({tC_09.02, r0030, c0080})", release_id=5
    )
    assert not result.is_valid
    assert result.error_code == "3-3"


# ---------------------------------------------------------------------------
# Date constructor
# ---------------------------------------------------------------------------


def test_date_constructor_integer_literals_valid(fixture_session):
    """date(y, m, d) with integer literals is semantically valid."""
    result = SemanticService(fixture_session).validate(
        "date(2025, 12, 31)", release_id=5
    )
    assert result.is_valid, f"Expected valid, got: {result.error_message}"


def test_date_constructor_result_comparable_to_date_literal(fixture_session):
    """date() result (Date) can be compared to a date literal."""
    result = SemanticService(fixture_session).validate(
        "date(2025, 12, 31) = #2025-12-31#", release_id=5
    )
    assert result.is_valid, f"Expected valid, got: {result.error_message}"


def test_date_constructor_string_argument_rejected(fixture_session):
    """date() rejects a String argument with a type error."""
    result = SemanticService(fixture_session).validate(
        'date(2025, "December", 31)', release_id=5
    )
    assert not result.is_valid
    assert result.error_code == "3-3"


def test_date_constructor_non_integer_recordset_argument_rejected(
    fixture_session,
):
    """date() accepts RecordSet operands, a non-Integer recordset
    fact is rejected on the Integer type check with 3-3.
    """
    result = SemanticService(fixture_session).validate(
        "date({tC_09.02, r0030, c0080}, 1, 1)", release_id=5
    )
    assert not result.is_valid
    assert result.error_code == "3-3"


def test_date_roundtrip_extraction_and_constructor(fixture_session):
    """date(year(d), 1, 1) round-trip: extract year from date, build first-of-year date."""
    result = SemanticService(fixture_session).validate(
        "date(year(#2022-03-15#), 1, 1) = #2022-01-01#", release_id=5
    )
    assert result.is_valid, f"Expected valid, got: {result.error_message}"


# ---------------------------------------------------------------------------
# Time shift tests
# ---------------------------------------------------------------------------


def test_time_shift_string_shift_number_rejected(fixture_session):
    """time_shift shift_number must be an integer — string literal is rejected."""
    svc = SemanticService(fixture_session)
    result = svc.validate('time_shift({tC_09.02}, Q, "hello")', release_id=5)
    assert not result.is_valid
    assert result.error_code == "4-7-4"


def test_time_shift_integer_expression_shift_number_valid(fixture_session):
    """time_shift with an integer arithmetic shift_number is semantically valid."""
    svc = SemanticService(fixture_session)
    expression = (
        "with {tC_14.00}: "
        "if {c0075} = true and {c0120} >= time_shift({c0120}, A, 1 * 1, refPeriod) "
        "then {c0181, default:0} < 0.05 endif"
    )
    result = svc.validate(expression, release_code="4.1")
    assert result.is_valid, f"Expected valid but got: {result.error_message}"


def test_sub_duplicate_property_code_rejected(fixture_session):
    """Duplicate property codes in a single sub clause are rejected end-to-end.

    The duplicate-key guard in InputAnalyzer.visit_SubOp fires before the
    chained validate loop, surfacing a clear 4-5-3-1 error instead of the
    misleading 2-8 "key not on recordset" that would otherwise come from
    the second iteration.
    """
    expression = '{tC_09.02, r0030, c0080}[sub qEBB = "x", qEBB = "y"]'
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_id=5)
    assert not result.is_valid
    assert result.error_code == "4-5-3-1", (
        f"Expected error code 4-5-3-1, got {result.error_code}: "
        f"{result.error_message}"
    )
    assert "qEBB" in (result.error_message or "")


@pytest.mark.parametrize(
    ("expression", "release_code"),
    [
        # tR_06.00.b 3.4: wildcard hits a header whose code changed in 4.2+
        (
            "with {tR_06.00.b, default: null, interval: false}: {r*, c0020-0050} >= 0",
            "3.4",
        ),
        # tR_06.00.b 4.2: TVH must resolve to the updated header code
        (
            "{tR_06.00.b, r*, c*, default: 0, interval: false} <= 1",
            "4.2",
        ),
        # tK_60.00.a 3.4: same multi-release header issue on a different table
        (
            "with {tK_60.00.a, default: null, interval: false}: {r0100-0290, c*} >= 0",
            "3.4",
        ),
    ],
)
def test_no_false_2_6_on_multi_release_headers(
    fixture_session, expression, release_code
):
    """Wildcard/range selectors on tables whose headers changed code across
    releases must be valid (no errors at all).
    """
    svc = SemanticService(fixture_session)
    result = svc.validate(expression, release_code=release_code)

    assert result.is_valid, (
        f"Expected valid at release {release_code!r}, got {result.error_code}: "
        f"{result.error_message}"
    )
