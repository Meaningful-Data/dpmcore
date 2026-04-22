"""Shared fixtures and marker auto-assignment."""

import pytest

PATH_RULES = [
    ("tests/unit/", "unit"),
    ("tests/integration/", "integration"),
    ("tests/unit/api/", "api"),
]

# Tests that are known-skipped. Most former py_dpm-era tests have been
# ported or removed (see issue #11); the one entry below depends on a
# shared fixture database that is not checked into the repo.
collect_ignore_glob = [
    # Depends on a fixture database at tests/fixtures/test_data.db that is
    # not tracked in the repo. Tracked in the cleanup issue.
    "integration/validation/test_semantic_release.py",
]


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Auto-assign markers based on test file paths."""
    for item in items:
        path = str(item.fspath)
        for prefix, marker_name in PATH_RULES:
            if prefix in path:
                item.add_marker(getattr(pytest.mark, marker_name))
