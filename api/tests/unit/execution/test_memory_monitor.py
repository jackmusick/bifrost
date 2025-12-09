"""
Unit tests for memory_monitor module.
"""

import pytest
from unittest.mock import patch, mock_open

from src.services.execution.memory_monitor import (
    get_available_memory_mb,
    has_sufficient_memory,
)


class TestGetAvailableMemoryMb:
    """Tests for get_available_memory_mb function."""

    def test_reads_mem_available_from_proc_meminfo(self):
        """Should parse MemAvailable from /proc/meminfo correctly."""
        mock_meminfo = """MemTotal:       16384000 kB
MemFree:         1234567 kB
MemAvailable:    8192000 kB
Buffers:          123456 kB
"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_meminfo)):
                result = get_available_memory_mb()
                # 8192000 kB = 8000 MB
                assert result == 8000

    def test_returns_negative_when_proc_meminfo_missing(self):
        """Should return -1 when /proc/meminfo doesn't exist (macOS)."""
        with patch("pathlib.Path.exists", return_value=False):
            result = get_available_memory_mb()
            assert result == -1

    def test_returns_negative_when_mem_available_not_found(self):
        """Should return -1 when MemAvailable line is missing."""
        mock_meminfo = """MemTotal:       16384000 kB
MemFree:         1234567 kB
Buffers:          123456 kB
"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_meminfo)):
                result = get_available_memory_mb()
                assert result == -1

    def test_handles_read_error_gracefully(self):
        """Should return -1 when file read fails."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", side_effect=OSError("Permission denied")):
                result = get_available_memory_mb()
                assert result == -1

    def test_handles_malformed_mem_available_line(self):
        """Should return -1 when MemAvailable line is malformed."""
        mock_meminfo = """MemTotal:       16384000 kB
MemAvailable:
Buffers:          123456 kB
"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_meminfo)):
                result = get_available_memory_mb()
                assert result == -1


class TestHasSufficientMemory:
    """Tests for has_sufficient_memory function."""

    def test_returns_true_when_memory_above_threshold(self):
        """Should return True when available memory exceeds threshold."""
        with patch(
            "src.services.execution.memory_monitor.get_available_memory_mb",
            return_value=500
        ):
            assert has_sufficient_memory(300) is True

    def test_returns_false_when_memory_below_threshold(self):
        """Should return False when available memory is below threshold."""
        with patch(
            "src.services.execution.memory_monitor.get_available_memory_mb",
            return_value=200
        ):
            assert has_sufficient_memory(300) is False

    def test_returns_true_when_memory_equals_threshold(self):
        """Should return True when available memory equals threshold."""
        with patch(
            "src.services.execution.memory_monitor.get_available_memory_mb",
            return_value=300
        ):
            assert has_sufficient_memory(300) is True

    def test_returns_true_when_memory_check_unavailable(self):
        """Should return True when memory check returns -1 (macOS)."""
        with patch(
            "src.services.execution.memory_monitor.get_available_memory_mb",
            return_value=-1
        ):
            # Should not block execution on macOS/dev environments
            assert has_sufficient_memory(300) is True

    def test_uses_default_threshold_of_300mb(self):
        """Should use 300MB as default threshold."""
        with patch(
            "src.services.execution.memory_monitor.get_available_memory_mb",
            return_value=250
        ):
            # 250 < 300 (default threshold)
            assert has_sufficient_memory() is False

        with patch(
            "src.services.execution.memory_monitor.get_available_memory_mb",
            return_value=350
        ):
            # 350 > 300 (default threshold)
            assert has_sufficient_memory() is True
