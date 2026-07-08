"""Integration tests for the Gap C/D additions to DataDictionaryService.

Anchored on the MR #136 canonical case at release ``4.2.1``:

* ``get_tables(verbose=True)`` returns dicts with ``code``, ``name`` and
  ``description``, and covers the same code set as the plain form.
* ``get_open_keys_for_table(s)`` walks the same joins the pre-existing
  private ``_get_open_keys_for_tables`` helper does — the public entry
  point must return an identical shape for a known table.

Tests skip cleanly when ``tests/fixtures/test_data.db`` is absent.
"""

from __future__ import annotations

import pytest

from dpmcore.services.data_dictionary import DataDictionaryService

_RELEASE_CODE = "4.2.1"


@pytest.fixture
def service(fixture_session):
    return DataDictionaryService(fixture_session)


def _release_id(session, code):
    from dpmcore.orm.infrastructure import Release

    row = session.query(Release).filter(Release.code == code).first()
    if row is None:
        pytest.skip(f"Fixture DB has no release with code {code!r}")
    return row.release_id


def test_get_tables_verbose_matches_plain_codes(service, fixture_session):
    release_id = _release_id(fixture_session, _RELEASE_CODE)

    plain = service.get_tables(release_id=release_id)
    verbose = service.get_tables(release_id=release_id, verbose=True)

    assert plain, "expected at least one table"
    assert verbose, "expected at least one table"
    assert len(verbose) == len(plain)

    # Every entry in verbose must be a dict with the documented keys.
    for entry in verbose:
        assert isinstance(entry, dict)
        assert set(entry) == {"code", "name", "description"}

    # Same set of codes in the same order.
    assert [e["code"] for e in verbose] == list(plain)


def test_get_tables_verbose_returns_names(service, fixture_session):
    release_id = _release_id(fixture_session, _RELEASE_CODE)

    verbose = service.get_tables(release_id=release_id, verbose=True)
    by_code = {e["code"]: e for e in verbose}
    assert "F_01.01" in by_code
    assert by_code["F_01.01"]["name"], "expected non-empty name for F_01.01"


def test_get_open_keys_for_table_matches_shared_helper(
    service, fixture_session
):
    """The public method must return the same dict as the shared helper."""
    release_id = _release_id(fixture_session, _RELEASE_CODE)

    from dpmcore.services._open_keys import get_open_keys_for_tables

    shared = get_open_keys_for_tables(
        fixture_session, ["F_01.01"], release_id=release_id
    ).get("F_01.01", {})

    public = service.get_open_keys_for_table("F_01.01", release_id=release_id)
    assert public == shared


def test_get_open_keys_for_tables_batch(service, fixture_session):
    release_id = _release_id(fixture_session, _RELEASE_CODE)

    batch = service.get_open_keys_for_tables(
        ["F_01.01", "F_02.00"], release_id=release_id
    )
    assert set(batch.keys()) == {"F_01.01", "F_02.00"}
    for value in batch.values():
        assert isinstance(value, dict)
