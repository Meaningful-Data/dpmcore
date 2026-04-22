"""Shared fixtures and marker auto-assignment."""

import pytest

PATH_RULES = [
    ("tests/unit/", "unit"),
    ("tests/integration/", "integration"),
    ("tests/unit/api/", "api"),
]

# Tests that still reference the pre-rename `py_dpm` package. They need to
# be ported to the current `dpmcore` layout — tracked in the codebase
# cleanup issue. Excluded here so the ~12 working test files can run.
collect_ignore_glob = [
    "integration/db/test_db_connection_handling.py",
    "integration/validation/test_implicit_open_keys.py",
    "unit/api/test_instance.py",
    "unit/dpm/test_module_schema_mapping.py",
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
