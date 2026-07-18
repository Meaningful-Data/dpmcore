"""Unit tests for the virtual header-version deduplication."""

from __future__ import annotations

from dpmcore.services.variable_generation.header_dedup import (
    detect_and_apply,
)
from tests.unit.services.variable_generation.builders import (
    CUR,
    PREV,
    header,
    hv,
    mvc,
    rel,
    snap,
    table,
    tv,
    tvh,
)


def _dedup_stores(**overrides):
    """A tv-10 header whose current HV 101 duplicates HV 100."""
    stores = {
        "tables": [table()],
        "table_versions": [tv()],
        "headers": [header()],
        "header_versions": [
            hv(100, start=PREV, end=CUR, code="010"),
            hv(101, start=CUR, code="010"),
        ],
        "table_version_headers": [tvh(header_vid=101)],
        "module_version_compositions": [mvc()],
    }
    stores.update(overrides)
    return stores


def test_detects_and_applies_duplicate_header_version():
    rebuilt, dedups = detect_and_apply(snap(**_dedup_stores()), rel())
    assert [d.to_dict() for d in dedups] == [
        {
            "old_header_vid": 100,
            "new_header_vid": 101,
            "table_vids": [10],
        }
    ]
    # TVH repointed to the old version.
    assert rebuilt.table_version_headers[0].header_vid == 100
    # New HV removed; old HV reopened.
    vids = {h.header_vid for h in rebuilt.header_versions}
    assert vids == {100}
    assert rebuilt.header_versions[0].end_release_id is None


def test_no_candidates_returns_snapshot_unchanged():
    snapshot = snap(
        **_dedup_stores(
            header_versions=[
                hv(100, start=PREV, end=CUR, code="010"),
                hv(101, start=CUR, code="011"),  # code differs
            ]
        )
    )
    rebuilt, dedups = detect_and_apply(snapshot, rel())
    assert rebuilt is snapshot
    assert dedups == ()


def test_field_differences_prevent_dedup():
    variants = [
        {"code": "999"},
        {"label": "other"},
        {"context_id": 40},
        {"property_id": 10},
        {"subcategory_vid": 60},
    ]
    for fields in variants:
        old_fields = {"code": "010", **fields}
        stores = _dedup_stores(
            header_versions=[
                hv(100, start=PREV, end=CUR, **old_fields),
                hv(101, start=CUR, code="010"),
            ]
        )
        _, dedups = detect_and_apply(snap(**stores), rel())
        assert dedups == (), fields


def test_table_version_filters():
    base = _dedup_stores()
    cases = [
        # abstract table
        {"tables": [table(is_abstract=True)]},
        # abstract flag NULL is not "= 0"
        {"tables": [table(is_abstract=None)]},
        # table row missing entirely
        {"tables": []},
        # expired table version
        {"table_versions": [tv(end=CUR)]},
        # old table version
        {"table_versions": [tv(start=PREV)]},
        # not employed by any module version
        {"module_version_compositions": []},
        # composition without a table version
        {"module_version_compositions": [mvc(table_vid=None)]},
    ]
    for override in cases:
        stores = dict(base)
        stores.update(override)
        _, dedups = detect_and_apply(snap(**stores), rel())
        assert dedups == (), override


def test_header_filters():
    base = _dedup_stores()
    cases = [
        # key headers are excluded
        {"headers": [header(is_key=True)]},
        # NULL isKey is not "= 0"
        {"headers": [header(is_key=None)]},
        # header of another table
        {"headers": [header(table_id=2)]},
        # header without a table
        {"headers": [header(table_id=None)]},
        # header row missing
        {"headers": []},
        # abstract TVH rows do not count
        {
            "table_version_headers": [
                tvh(header_vid=101, is_abstract=True)
            ]
        },
        # NULL TVH abstract flag is not "= 0"
        {
            "table_version_headers": [
                tvh(header_vid=101, is_abstract=None)
            ]
        },
    ]
    for override in cases:
        stores = dict(base)
        stores.update(override)
        _, dedups = detect_and_apply(snap(**stores), rel())
        assert dedups == (), override


def test_header_version_filters():
    base = _dedup_stores()
    cases = [
        # new HV must be active
        [hv(100, start=PREV, end=CUR), hv(101, start=CUR, end=CUR)],
        # new HV needs a start release (NULL never joins)
        [hv(100, start=PREV, end=CUR), hv(101, start=None)],
        # predecessor must close exactly at the new HV's start
        [hv(100, start=PREV, end=PREV), hv(101, start=CUR)],
    ]
    for header_versions in cases:
        stores = dict(base)
        stores["header_versions"] = header_versions
        _, dedups = detect_and_apply(snap(**stores), rel())
        assert dedups == (), header_versions


def test_unrelated_rows_survive_the_rebuild():
    stores = _dedup_stores(
        headers=[header(), header(2, is_key=True)],
        header_versions=[
            hv(100, start=PREV, end=CUR, code="010"),
            hv(101, start=CUR, code="010"),
            hv(200, header_id=2, start=PREV, code="k"),
        ],
        table_version_headers=[
            tvh(header_vid=101),
            tvh(header_id=2, header_vid=200),
            tvh(header_id=2, header_vid=None),
        ],
    )
    rebuilt, dedups = detect_and_apply(snap(**stores), rel())
    assert len(dedups) == 1
    assert {h.header_vid for h in rebuilt.header_versions} == {
        100,
        200,
    }
    by_header = {
        t.header_id: t.header_vid
        for t in rebuilt.table_version_headers
        if t.header_vid is not None
    }
    assert by_header == {1: 100, 2: 200}
