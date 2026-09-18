"""Ghost-fallback sweep enumeration over synthetic module versions.

The companion of ``test_ghost_script_export``, which pins the same rule
against the real dictionary. This one builds its own three-release
``ModuleVersion`` table in memory, so it runs everywhere -- the fixture
DB is not committed, and every test that needs it skips on CI.

Each module below is one shape of the #182/#372 rule:

==================  =======================================================
``PLAIN``           a genuine version covering R2; no substitution at all
``GHOSTED``         only a ghost covers R2, so the prior version stands in
``FIRSTGHOST``      its ghost is the first version: nothing stands in
``OLDNAME``/        like ``GHOSTED``, but the version after the ghost
``NEWNAME``         renames the module
==================  =======================================================
"""

from __future__ import annotations

from datetime import date

import pytest

from dpmcore.orm.infrastructure import Release
from dpmcore.orm.packaging import ModuleVersion
from dpmcore.services.ast_generator import (
    ASTGeneratorService,
    _sweep_order,
)

_R1, _R2, _R3 = 1, 2, 3


def _release(release_id: int, code: str, day: int) -> Release:
    return Release(
        release_id=release_id,
        code=code,
        date=date(2024, 1, day),
        status="released",
        is_current=False,
    )


def _mv(
    vid: int,
    module_id: int,
    code: str,
    version: str,
    start: int,
    end: int | None,
    *,
    ghost: bool = False,
) -> ModuleVersion:
    """A module version, collapsed to a single instant when ``ghost``."""
    return ModuleVersion(
        module_vid=vid,
        module_id=module_id,
        code=code,
        version_number=version,
        start_release_id=start,
        end_release_id=end,
        from_reference_date=date(2024, 6, 30),
        to_reference_date=date(2024, 6, 30) if ghost else date(2025, 6, 30),
    )


@pytest.fixture
def dictionary(memory_session):
    """Four modules covering each shape of the fallback rule."""
    memory_session.add_all(
        [
            _release(_R1, "1.0", 1),
            _release(_R2, "2.0", 2),
            _release(_R3, "3.0", 3),
            # Genuine version covering R2: no substitution.
            _mv(10, 1, "PLAIN", "1.0.0", _R1, None),
            # Only a ghost covers R2 -> 1.0.0 stands in for it.
            _mv(20, 2, "GHOSTED", "1.0.0", _R1, _R2),
            _mv(21, 2, "GHOSTED", "2.0.0", _R2, _R3, ghost=True),
            _mv(22, 2, "GHOSTED", "3.0.0", _R3, None),
            # The ghost is the module's first version: nothing prior.
            _mv(30, 3, "FIRSTGHOST", "1.0.0", _R1, _R3, ghost=True),
            _mv(31, 3, "FIRSTGHOST", "2.0.0", _R3, None),
            # Ghosted, and renamed by the version that follows the ghost.
            _mv(40, 4, "OLDNAME", "1.0.0", _R1, _R2),
            _mv(41, 4, "OLDNAME", "2.0.0", _R2, _R3, ghost=True),
            _mv(42, 4, "NEWNAME", "3.0.0", _R3, None),
        ]
    )
    memory_session.flush()
    return memory_session


@pytest.fixture
def service(dictionary):
    return ASTGeneratorService(dictionary)


def test_genuine_version_is_swept_unchanged(service):
    """A module with a real covering version needs no substitution."""
    assert service.list_module_versions(
        module_code="PLAIN", release="2.0"
    ) == [("PLAIN", "1.0.0")]


def test_ghost_only_module_is_swept_as_its_fallback(service):
    """The prior non-ghost version represents the release (#182)."""
    assert service.list_module_versions(
        module_code="GHOSTED", release="2.0"
    ) == [("GHOSTED", "1.0.0")]


def test_ghost_is_never_a_sweep_target(service):
    """The substitution must not put the ghost itself in the sweep."""
    targets = service.list_module_versions(release="2.0")

    assert ("GHOSTED", "2.0.0") not in targets
    assert ("FIRSTGHOST", "1.0.0") not in targets
    assert ("OLDNAME", "2.0.0") not in targets


def test_ghost_with_nothing_prior_is_left_out(service):
    """No prior non-ghost version means the module is simply absent."""
    assert (
        service.list_module_versions(module_code="FIRSTGHOST", release="2.0")
        == []
    )


def test_rename_does_not_leak_the_old_code(service):
    """``NEWNAME`` does not exist at R2, so nothing is returned for it.

    The module is the same one whose fallback is ``OLDNAME 1.0.0``;
    resolving the requested code to a *module* rather than filtering the
    fallback's own code answered this with ``('OLDNAME', '1.0.0')``.
    """
    assert (
        service.list_module_versions(module_code="NEWNAME", release="2.0")
        == []
    )
    assert service.list_module_versions(
        module_code="OLDNAME", release="2.0"
    ) == [("OLDNAME", "1.0.0")]


def test_scoped_sweep_always_matches_the_all_modules_slice(service):
    """The invariant that the rename broke, over every code and release."""
    codes = {"PLAIN", "GHOSTED", "FIRSTGHOST", "OLDNAME", "NEWNAME"}

    for release in ("1.0", "2.0", "3.0"):
        everything = set(service.list_module_versions(release=release))
        for code in codes:
            scoped = set(
                service.list_module_versions(module_code=code, release=release)
            )
            assert scoped == {p for p in everything if p[0] == code}, (
                f"{code} at {release}"
            )


def test_sweep_is_ordered_by_code_then_release_date(service):
    """Fallback rows sort in with the rows the release query returned."""
    targets = service.list_module_versions(release="2.0")

    assert targets == sorted(targets)


def test_sweep_order_follows_dates_not_opaque_release_ids():
    """The tie-break is the release's date order, never its id.

    ``ReleaseID`` stopped being monotonic at DPM 4.2.1 (``4.2.1`` is
    ``1010000003``), so ordering on the raw id would put a later release
    before an earlier one whenever the ids disagree with the dates.
    """
    # id 1010000003 is the *latest* release; id 9 an earlier one.
    sort_orders = {9: 200, 1010000003: 300}
    rows = [
        ("MOD", "2.0.0", 1010000003),
        ("MOD", "1.0.0", 9),
    ]

    assert [
        version
        for _code, version, _start in sorted(
            rows, key=lambda row: _sweep_order(sort_orders, row)
        )
    ] == ["1.0.0", "2.0.0"]


def test_sweep_order_puts_an_unknown_start_first():
    """A null or orphan start release sorts ahead of every dated one."""
    sort_orders = {7: 100}
    rows = [("MOD", "dated", 7), ("MOD", "null", None), ("MOD", "orphan", 42)]

    assert [
        version
        for _code, version, _start in sorted(
            rows, key=lambda row: _sweep_order(sort_orders, row)
        )
    ] == ["null", "orphan", "dated"]


def test_no_release_applies_no_substitution(service):
    """Without a target release there is no "prior" to fall back to."""
    targets = service.list_module_versions()

    assert ("GHOSTED", "1.0.0") in targets
    assert ("GHOSTED", "3.0.0") in targets
    # Ghosts are excluded outright, substitution or not.
    assert ("GHOSTED", "2.0.0") not in targets
