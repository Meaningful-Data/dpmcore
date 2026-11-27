"""Shared fixtures and marker auto-assignment."""

import importlib.util
from pathlib import Path

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


@pytest.fixture(scope="session")
def validator():
    """``tests/validate_script.py``, the Script Format 2.0 validator."""
    spec = importlib.util.spec_from_file_location(
        "validate_script", Path(__file__).parent / "validate_script.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
