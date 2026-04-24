"""Tests for the semantic validation warning collector."""

import threading

from dpmcore.dpm_xl.warning_collector import (
    WarningCollector,
    add_semantic_warning,
    collect_warnings,
    get_active_collector,
)


class TestWarningCollector:
    """Tests for the WarningCollector class."""

    def test_add_warning(self):
        """Test adding a warning to the collector."""
        collector = WarningCollector()
        collector.add_warning("Test warning")
        assert collector.get_warnings() == ["Test warning"]

    def test_multiple_warnings(self):
        """Test adding multiple warnings."""
        collector = WarningCollector()
        collector.add_warning("Warning 1")
        collector.add_warning("Warning 2")
        collector.add_warning("Warning 3")
        assert collector.get_warnings() == [
            "Warning 1",
            "Warning 2",
            "Warning 3",
        ]

    def test_get_warnings_returns_copy(self):
        """Test that get_warnings returns a copy of the list."""
        collector = WarningCollector()
        collector.add_warning("Test warning")
        warnings = collector.get_warnings()
        warnings.append("Modified")
        assert collector.get_warnings() == ["Test warning"]

    def test_get_combined_warning_none(self):
        """Test get_combined_warning returns None when no warnings."""
        collector = WarningCollector()
        assert collector.get_combined_warning() is None

    def test_get_combined_warning_single(self):
        """Test get_combined_warning with single warning."""
        collector = WarningCollector()
        collector.add_warning("Single warning")
        assert collector.get_combined_warning() == "Single warning"

    def test_get_combined_warning_multiple(self):
        """Test get_combined_warning with multiple warnings."""
        collector = WarningCollector()
        collector.add_warning("Warning 1")
        collector.add_warning("Warning 2")
        assert collector.get_combined_warning() == "Warning 1\nWarning 2"

    def test_clear(self):
        """Test clearing warnings."""
        collector = WarningCollector()
        collector.add_warning("Warning 1")
        collector.add_warning("Warning 2")
        collector.clear()
        assert collector.get_warnings() == []
        assert collector.get_combined_warning() is None


class TestCollectWarningsContextManager:
    """Tests for the collect_warnings context manager."""

    def test_context_manager_basic(self):
        """Test basic context manager usage."""
        with collect_warnings() as collector:
            add_semantic_warning("Test warning")
        assert collector.get_combined_warning() == "Test warning"

    def test_context_manager_no_warnings(self):
        """Test context manager with no warnings."""
        with collect_warnings() as collector:
            pass
        assert collector.get_combined_warning() is None

    def test_nested_context_managers(self):
        """Test nested context managers."""
        with collect_warnings() as outer:
            add_semantic_warning("Outer warning")
            with collect_warnings() as inner:
                add_semantic_warning("Inner warning")
            # After inner context, outer should be restored
            add_semantic_warning("Outer warning 2")

        assert inner.get_warnings() == ["Inner warning"]
        assert outer.get_warnings() == ["Outer warning", "Outer warning 2"]

    def test_no_active_collector(self):
        """Test add_semantic_warning when no collector is active."""
        # This should not raise an error, just silently discard
        add_semantic_warning("Warning without collector")
        assert get_active_collector() is None

    def test_thread_isolation(self):
        """Test that warning collectors are thread-local."""
        results = {}

        def thread_func(thread_id):
            with collect_warnings() as collector:
                add_semantic_warning(f"Thread {thread_id} warning")
                results[thread_id] = collector.get_combined_warning()

        threads = [
            threading.Thread(target=thread_func, args=(i,)) for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results[0] == "Thread 0 warning"
        assert results[1] == "Thread 1 warning"
        assert results[2] == "Thread 2 warning"

    def test_exception_handling(self):
        """Test that context manager properly restores state on exception."""
        try:
            with collect_warnings() as collector:
                add_semantic_warning("Before exception")
                raise ValueError("Test exception")
        except ValueError:
            pass

        # After exception, there should be no active collector
        assert get_active_collector() is None
        # But the collector should still have the warning from before the exception
        assert collector.get_combined_warning() == "Before exception"


class TestGetActiveCollector:
    """Tests for get_active_collector function."""

    def test_no_active_collector(self):
        """Test when no collector is active."""
        assert get_active_collector() is None

    def test_with_active_collector(self):
        """Test when a collector is active."""
        with collect_warnings() as collector:
            active = get_active_collector()
            assert active is collector
