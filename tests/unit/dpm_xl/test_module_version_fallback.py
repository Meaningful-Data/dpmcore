"""Unit tests for the ghost-version selection helpers (issue #131).

``_select_version_in_effect`` and ``_select_previous_version`` back
``_apply_fallback_for_equal_dates``. A "ghost" module version has a
collapsed validity window (``from == to``) because it was superseded on
its own start date; these helpers locate the sibling version actually in
effect on that date. The selection is date-driven so it works whether the
real version is a forward successor (the #131 regression) or a backward
predecessor, and it never relies on the opaque ``ReleaseID`` ordering.
"""

import datetime as dt

from dpmcore.dpm_xl.model_queries import (
    _select_previous_version,
    _select_version_in_effect,
)
from dpmcore.orm.packaging import ModuleVersion

_D = dt.date(2026, 3, 31)


def _mv(vid, srid, erid, ver, frm, to, mid=10):
    """Build an unattached ModuleVersion (no session needed)."""
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


class TestSelectVersionInEffect:
    """Date-window selection across both lifecycle directions."""

    def test_none_ghost_date_returns_none(self):
        sib = _mv(2, 100, None, "1.1.0", _D, None)
        assert _select_version_in_effect([sib], None) is None

    def test_forward_successor_sharing_start_date(self):
        # FINREP9DP shape: successor starts on the ghost's date, open-ended.
        ghost = _mv(1, 5, 100, "1.0.0", _D, _D)
        succ = _mv(2, 100, None, "1.1.0", _D, None)
        assert _select_version_in_effect([succ, ghost], _D) is succ

    def test_backward_predecessor_window_covers_date(self):
        # FINREP9 shape: predecessor window straddles the ghost's date.
        d = dt.date(2024, 12, 31)
        pred = _mv(
            1, 1, 3, "3.1.0", dt.date(2022, 12, 31), dt.date(2026, 3, 30)
        )
        ghost = _mv(2, 3, 5, "3.2.0", d, d)
        later = _mv(3, 5, None, "3.3.0", dt.date(2026, 3, 31), None)
        assert _select_version_in_effect([later, ghost, pred], d) is pred

    def test_returns_none_when_no_window_covers_date(self):
        # Predecessor ends before the date; only sibling left is the ghost.
        before = _mv(1, 1, 2, "1.0", dt.date(2020, 1, 1), dt.date(2021, 1, 1))
        ghost = _mv(2, 2, None, "2.0", _D, _D)
        assert _select_version_in_effect([before, ghost], _D) is None

    def test_tiebreak_prefers_open_ended_window(self):
        closed = _mv(1, 5, 9, "a", dt.date(2025, 1, 1), dt.date(2027, 1, 1))
        opened = _mv(2, 5, None, "b", dt.date(2025, 1, 1), None)
        assert _select_version_in_effect([closed, opened], _D) is opened

    def test_tiebreak_prefers_latest_start_date(self):
        early = _mv(1, 5, 9, "a", dt.date(2024, 1, 1), dt.date(2027, 1, 1))
        late = _mv(2, 6, 9, "b", dt.date(2025, 1, 1), dt.date(2027, 1, 1))
        assert _select_version_in_effect([early, late], _D) is late


class TestSelectPreviousVersion:
    """Backward release-ordered fallback (preserved behaviour)."""

    def test_returns_nearest_non_ghost_predecessor(self):
        # Provided descending by start release, as production does. A ghost
        # predecessor (v2) is skipped in favour of the real one (v1).
        v3 = _mv(3, 5, None, "3.0", dt.date(2026, 1, 1), None)
        v2 = _mv(2, 3, 5, "2.0", dt.date(2024, 1, 1), dt.date(2024, 1, 1))
        v1 = _mv(1, 1, 3, "1.0", dt.date(2020, 1, 1), dt.date(2023, 1, 1))
        assert _select_previous_version([v3, v2, v1], 4) is v1

    def test_returns_none_when_no_earlier_version(self):
        only = _mv(1, 5, None, "1.0", dt.date(2026, 1, 1), None)
        assert _select_previous_version([only], 5) is None
