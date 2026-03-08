"""
Warning collector for semantic validation.

This module provides a thread-local warning collector that can be used to capture
warnings during semantic analysis instead of emitting them via warnings.warn().
"""

import threading
from contextlib import contextmanager
from typing import List, Optional


# Thread-local storage for the warning collector
_local = threading.local()


class WarningCollector:
    """
    Collects semantic validation warnings.

    This class provides a context manager interface to collect warnings during
    semantic analysis. When active, warnings can be added via add_warning() and
    retrieved via get_warnings().
    """

    def __init__(self) -> None:
        self._warnings: List[str] = []

    def add_warning(self, message: str) -> None:
        """Add a warning message to the collector."""
        self._warnings.append(message)

    def get_warnings(self) -> List[str]:
        """Get all collected warnings."""
        return self._warnings.copy()

    def get_combined_warning(self) -> Optional[str]:
        """
        Get all warnings combined into a single string.

        Returns:
            None if no warnings, otherwise all warnings joined with newlines.
        """
        if not self._warnings:
            return None
        return "\n".join(self._warnings)

    def clear(self) -> None:
        """Clear all collected warnings."""
        self._warnings.clear()


def get_active_collector() -> Optional[WarningCollector]:
    """Get the currently active warning collector, if any."""
    return getattr(_local, "collector", None)


def add_semantic_warning(message: str) -> None:
    """
    Add a warning to the active collector.

    If no collector is active, the warning is silently discarded.
    This allows the warning calls to work both within and outside of
    a collection context.

    Args:
        message: The warning message to add.
    """
    collector = get_active_collector()
    if collector is not None:
        collector.add_warning(message)


@contextmanager
def collect_warnings():
    """
    Context manager to collect warnings during semantic analysis.

    Usage:
        with collect_warnings() as collector:
            # Perform semantic analysis
            ...
        warnings = collector.get_combined_warning()

    Yields:
        WarningCollector: The collector that will contain any warnings.
    """
    collector = WarningCollector()
    old_collector = getattr(_local, "collector", None)
    _local.collector = collector
    try:
        yield collector
    finally:
        _local.collector = old_collector
