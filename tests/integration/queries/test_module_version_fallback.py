"""Integration tests for ``_apply_fallback_for_equal_dates`` (issue #131).

A "ghost" module version (``FromReferenceDate == ToReferenceDate``) is
repaired by substituting the sibling version actually in effect on that
date. The repair must work for a forward successor that starts on the same
date (the #131 regression) as well as for a backward predecessor whose
window still covers the date, and must leave non-ghost rows untouched.
"""

import datetime as dt

import pandas as pd

from dpmcore.dpm_xl.model_queries import _apply_fallback_for_equal_dates
from dpmcore.orm.packaging import ModuleVersion

_COLS = [
    "ModuleVID",
    "variable_vid",
    "ModuleCode",
    "VersionNumber",
    "FromReferenceDate",
    "ToReferenceDate",
    "StartReleaseID",
    "EndReleaseID",
]


def _mv(vid, mid, srid, erid, ver, frm, to):
    """Build a ModuleVersion ORM row."""
    return ModuleVersion(
        module_vid=vid,
        module_id=mid,
        start_release_id=srid,
        end_release_id=erid,
        code="MOD",
        version_number=ver,
        from_reference_date=frm,
        to_reference_date=to,
    )


def _row(vid, code, ver, frm, to, srid, erid):
    """Build a result-frame row matching ``_COLS``."""
    return (vid, vid, code, ver, frm, to, srid, erid)


def _seed(session):
    """Insert the module-version fixtures used across these tests."""
    session.add_all(
        [
            # Module 63 (FINREP9DP shape): forward successor, same start date.
            _mv(
                506,
                63,
                5,
                100,
                "1.0.0",
                dt.date(2026, 3, 31),
                dt.date(2026, 3, 31),
            ),
            _mv(513, 63, 100, None, "1.1.0", dt.date(2026, 3, 31), None),
            # Module 12 (FINREP9 shape): backward predecessor covers the date.
            _mv(
                356,
                12,
                1,
                3,
                "3.1.0",
                dt.date(2022, 12, 31),
                dt.date(2026, 3, 30),
            ),
            _mv(
                404,
                12,
                3,
                5,
                "3.2.0",
                dt.date(2024, 12, 31),
                dt.date(2024, 12, 31),
            ),
            _mv(462, 12, 5, None, "3.3.0", dt.date(2026, 3, 31), None),
            # Module 70: no window covers the date -> release-order fallback.
            _mv(
                700,
                70,
                1,
                2,
                "1.0",
                dt.date(2020, 1, 1),
                dt.date(2021, 12, 31),
            ),
            _mv(
                701,
                70,
                2,
                None,
                "2.0",
                dt.date(2024, 6, 30),
                dt.date(2024, 6, 30),
            ),
            # Module 80: lone ghost with no possible replacement.
            _mv(
                800,
                80,
                1,
                None,
                "1.0",
                dt.date(2024, 1, 1),
                dt.date(2024, 1, 1),
            ),
        ]
    )
    session.flush()


class TestApplyFallbackForEqualDates:
    """End-to-end repair behaviour against an in-memory schema."""

    def test_empty_frame_returned_unchanged(self, memory_session):
        df = pd.DataFrame(columns=_COLS)
        out = _apply_fallback_for_equal_dates(memory_session, df)
        assert out.empty

    def test_no_ghost_rows_returned_unchanged(self, memory_session):
        _seed(memory_session)
        df = pd.DataFrame(
            [_row(513, "MOD", "1.1.0", dt.date(2026, 3, 31), None, 100, None)],
            columns=_COLS,
        )
        out = _apply_fallback_for_equal_dates(memory_session, df)
        assert out is df

    def test_forward_successor_replaces_ghost(self, memory_session):
        _seed(memory_session)
        df = pd.DataFrame(
            [
                _row(
                    506,
                    "FINREP9DP",
                    "1.0.0",
                    dt.date(2026, 3, 31),
                    dt.date(2026, 3, 31),
                    5,
                    100,
                )
            ],
            columns=_COLS,
        )
        out = _apply_fallback_for_equal_dates(memory_session, df)
        r = out.iloc[0]
        assert r["ModuleVID"] == 513
        assert r["VersionNumber"] == "1.1.0"
        assert r["FromReferenceDate"] == dt.date(2026, 3, 31)
        assert pd.isna(r["ToReferenceDate"])
        assert r["StartReleaseID"] == 100
        assert pd.isna(r["EndReleaseID"])

    def test_backward_predecessor_replaces_ghost(self, memory_session):
        _seed(memory_session)
        df = pd.DataFrame(
            [
                _row(
                    404,
                    "FINREP9",
                    "3.2.0",
                    dt.date(2024, 12, 31),
                    dt.date(2024, 12, 31),
                    3,
                    5,
                )
            ],
            columns=_COLS,
        )
        out = _apply_fallback_for_equal_dates(memory_session, df)
        r = out.iloc[0]
        assert r["ModuleVID"] == 356
        assert r["VersionNumber"] == "3.1.0"
        assert r["ToReferenceDate"] == dt.date(2026, 3, 30)

    def test_release_order_fallback_when_no_window_covers(
        self, memory_session
    ):
        _seed(memory_session)
        df = pd.DataFrame(
            [
                _row(
                    701,
                    "MOD70",
                    "2.0",
                    dt.date(2024, 6, 30),
                    dt.date(2024, 6, 30),
                    2,
                    None,
                )
            ],
            columns=_COLS,
        )
        out = _apply_fallback_for_equal_dates(memory_session, df)
        r = out.iloc[0]
        assert r["ModuleVID"] == 700
        assert r["VersionNumber"] == "1.0"

    def test_lone_ghost_without_replacement_kept(self, memory_session):
        _seed(memory_session)
        df = pd.DataFrame(
            [
                _row(
                    800,
                    "MOD80",
                    "1.0",
                    dt.date(2024, 1, 1),
                    dt.date(2024, 1, 1),
                    1,
                    None,
                )
            ],
            columns=_COLS,
        )
        out = _apply_fallback_for_equal_dates(memory_session, df)
        # No replacement found at all -> original frame returned unchanged.
        assert out is df
        assert out.iloc[0]["ModuleVID"] == 800

    def test_mixed_ghost_and_non_ghost_rows(self, memory_session):
        _seed(memory_session)
        df = pd.DataFrame(
            [
                _row(
                    506,
                    "FINREP9DP",
                    "1.0.0",
                    dt.date(2026, 3, 31),
                    dt.date(2026, 3, 31),
                    5,
                    100,
                ),  # ghost -> replaced by 513
                _row(
                    462,
                    "FINREP9",
                    "3.3.0",
                    dt.date(2026, 3, 31),
                    None,
                    5,
                    None,
                ),  # non-ghost -> untouched
                _row(
                    800,
                    "MOD80",
                    "1.0",
                    dt.date(2024, 1, 1),
                    dt.date(2024, 1, 1),
                    1,
                    None,
                ),  # ghost without replacement -> kept
            ],
            columns=_COLS,
        )
        out = _apply_fallback_for_equal_dates(memory_session, df)
        assert out.iloc[0]["ModuleVID"] == 513
        assert out.iloc[1]["ModuleVID"] == 462
        assert out.iloc[2]["ModuleVID"] == 800

    def test_replacement_without_release_id_columns(self, memory_session):
        _seed(memory_session)
        cols = [
            "ModuleVID",
            "ModuleCode",
            "VersionNumber",
            "FromReferenceDate",
            "ToReferenceDate",
        ]
        df = pd.DataFrame(
            [
                (
                    506,
                    "FINREP9DP",
                    "1.0.0",
                    dt.date(2026, 3, 31),
                    dt.date(2026, 3, 31),
                )
            ],
            columns=cols,
        )
        out = _apply_fallback_for_equal_dates(memory_session, df)
        r = out.iloc[0]
        assert r["ModuleVID"] == 513
        assert r["VersionNumber"] == "1.1.0"
        assert "StartReleaseID" not in out.columns

    def test_null_start_release_does_not_block_window_repair(
        self, memory_session
    ):
        # A ghost with no start release must still be repaired by date.
        memory_session.add_all(
            [
                _mv(
                    601,
                    65,
                    None,
                    None,
                    "1.0.0",
                    dt.date(2026, 3, 31),
                    dt.date(2026, 3, 31),
                ),
                _mv(602, 65, 100, None, "1.1.0", dt.date(2026, 3, 31), None),
            ]
        )
        memory_session.flush()
        df = pd.DataFrame(
            [
                _row(
                    601,
                    "MODX",
                    "1.0.0",
                    dt.date(2026, 3, 31),
                    dt.date(2026, 3, 31),
                    None,
                    None,
                )
            ],
            columns=_COLS,
        )
        out = _apply_fallback_for_equal_dates(memory_session, df)
        assert out.iloc[0]["ModuleVID"] == 602

    def test_null_module_id_ghost_kept(self, memory_session):
        memory_session.add(
            _mv(
                900,
                None,
                1,
                None,
                "1.0",
                dt.date(2024, 1, 1),
                dt.date(2024, 1, 1),
            )
        )
        memory_session.flush()
        df = pd.DataFrame(
            [
                _row(
                    900,
                    "MOD90",
                    "1.0",
                    dt.date(2024, 1, 1),
                    dt.date(2024, 1, 1),
                    1,
                    None,
                )
            ],
            columns=_COLS,
        )
        out = _apply_fallback_for_equal_dates(memory_session, df)
        assert out is df
        assert out.iloc[0]["ModuleVID"] == 900
