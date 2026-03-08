"""Shared fixtures and marker auto-assignment."""

import pytest

PATH_RULES = [
    ("tests/unit/", "unit"),
    ("tests/integration/", "integration"),
    ("tests/unit/api/", "api"),
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
