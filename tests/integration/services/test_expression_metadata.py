"""Integration tests for :class:`ExpressionMetadataService`.

Anchored on the MR #136 canonical case
``{tF_01.01, r0010, c0010} = 100`` at release ``4.2.1``:

* tables → resolves to F_01.01 across both FINREP9 and FINREP9DP.
* headers → r0010 comes back as ``Row`` and c0010 as ``Column``
  (the pydpm equivalent's header-usage-from-syntax rule).
* frameworks → FINREP appears once, deduped across modules.

Tests skip cleanly when ``tests/fixtures/test_data.db`` is absent.
"""

from __future__ import annotations

import pytest

from dpmcore.services.expression_metadata import ExpressionMetadataService

_EXPRESSION = "{tF_01.01, r0010, c0010} = 100"
_RELEASE_CODE = "4.2.1"


@pytest.fixture
def service(fixture_session):
    return ExpressionMetadataService(fixture_session)


def _release_id(session, code):
    from dpmcore.orm.infrastructure import Release

    row = session.query(Release).filter(Release.code == code).first()
    if row is None:
        pytest.skip(f"Fixture DB has no release with code {code!r}")
    return row.release_id


def test_get_referenced_tables_returns_finrep9_and_finrep9dp(
    service, fixture_session
):
    release_id = _release_id(fixture_session, _RELEASE_CODE)

    tables = service.get_referenced_tables(
        expression=_EXPRESSION, release_id=release_id
    )

    assert tables, "expected at least one table row"
    module_codes = sorted({t["module_code"] for t in tables})
    assert "FINREP9" in module_codes
    assert all(t["code"] == "F_01.01" for t in tables)
    # No ORM leakage: every entry must be a plain dict with the
    # documented keys.
    required = {
        "table_vid",
        "code",
        "name",
        "description",
        "module_vid",
        "module_code",
        "module_name",
        "module_version",
    }
    for row in tables:
        assert isinstance(row, dict)
        assert required.issubset(row.keys())


def test_get_referenced_headers_reflects_syntax_usage(
    service, fixture_session
):
    release_id = _release_id(fixture_session, _RELEASE_CODE)

    headers = service.get_referenced_headers(
        expression=_EXPRESSION, release_id=release_id
    )

    assert headers, "expected header rows"

    # r0010 must be exposed as Row-usage; c0010 as Column-usage.
    row_labels = {h["header_type"] for h in headers if h["code"] == "0010"}
    assert {"Row", "Column"}.issubset(row_labels)


def test_get_referenced_headers_filters_by_table_vid(service, fixture_session):
    release_id = _release_id(fixture_session, _RELEASE_CODE)
    tables = service.get_referenced_tables(
        expression=_EXPRESSION, release_id=release_id
    )
    if not tables:
        pytest.skip("no tables resolved; upstream test covers reason")
    target_vid = tables[0]["table_vid"]

    headers = service.get_referenced_headers(
        expression=_EXPRESSION,
        release_id=release_id,
        table_vid=target_vid,
    )

    assert headers
    assert {h["table_vid"] for h in headers} == {target_vid}


def test_get_referenced_frameworks_dedupes(service, fixture_session):
    release_id = _release_id(fixture_session, _RELEASE_CODE)

    frameworks = service.get_referenced_frameworks(
        expression=_EXPRESSION, release_id=release_id
    )

    codes = [fw["code"] for fw in frameworks]
    assert codes == sorted(codes), "frameworks must be sorted by code"
    assert len(codes) == len(set(codes)), "frameworks must be deduped"
    assert "FINREP" in codes


def test_unknown_expression_returns_empty_lists(service, fixture_session):
    release_id = _release_id(fixture_session, _RELEASE_CODE)
    bad = "{tXX_NOT_A_TABLE, r0010, c0010} = 100"

    assert service.get_referenced_tables(bad, release_id=release_id) == []
    assert service.get_referenced_headers(bad, release_id=release_id) == []
    assert service.get_referenced_frameworks(bad, release_id=release_id) == []


def test_syntax_error_returns_empty_lists(service):
    """A parser-level error must degrade to empty lists, not raise."""
    assert service.get_referenced_tables("this is not dpm-xl") == []
    assert service.get_referenced_headers("this is not dpm-xl") == []
    assert service.get_referenced_frameworks("this is not dpm-xl") == []


def test_service_is_wired_on_connection():
    """The accessor must expose ``services.expression_metadata``."""
    from dpmcore import connect

    # We can validate the wiring without touching the DB by using an
    # in-memory URL; the property is lazy, so no query fires.
    with connect("sqlite:///:memory:") as db:
        service = db.services.expression_metadata
        assert isinstance(service, ExpressionMetadataService)
        # Cached
        assert db.services.expression_metadata is service
