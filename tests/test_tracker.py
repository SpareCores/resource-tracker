from importlib import import_module
from os import getpid
from platform import system

import pytest


@pytest.mark.parametrize(
    "tracker_implementation",
    [
        "resource_tracker.tracker_psutil",
        pytest.param(
            "resource_tracker.tracker_procfs",
            marks=pytest.mark.skipif(
                system() != "Linux", reason="procfs implementation only works on Linux"
            ),
        ),
    ],
)
def test_get_pid_stats_implementations(tracker_implementation):
    """Test get_pid_stats from different implementations."""
    module = import_module(tracker_implementation)
    get_pid_stats = getattr(module, "get_pid_stats")

    pid = getpid()
    stats = get_pid_stats(pid)

    # at least some values should be present
    assert stats["timestamp"] is not None
    assert stats["pid"] == pid
    assert stats["children"] is not None
    assert stats["utime"] is not None
    assert stats["stime"] is not None
    assert stats["memory"] is not None

    # test memory allocation is tracked
    memory = stats["memory"]
    bigobj = bytearray(50 * 1024 * 1024)  # 50MB
    stats = get_pid_stats(pid)
    assert stats["memory"] >= memory + 40 * 1024  # kB
    del bigobj


@pytest.mark.parametrize(
    "tracker_implementation",
    [
        "resource_tracker.tracker_psutil",
        pytest.param(
            "resource_tracker.tracker_procfs",
            marks=pytest.mark.skipif(
                system() != "Linux", reason="procfs implementation only works on Linux"
            ),
        ),
    ],
)
def test_get_system_stats_implementations(tracker_implementation):
    """Test get_system_stats from different implementations."""
    module = import_module(tracker_implementation)
    get_system_stats = getattr(module, "get_system_stats")

    stats = get_system_stats()

    # at least some values should be present
    assert stats["timestamp"] is not None
    assert stats["processes"] is not None
    assert stats["utime"] is not None
    assert stats["stime"] is not None
    assert stats["memory_free"] is not None
    assert stats["memory_used"] is not None

    # test memory allocation is tracked
    memory = stats["memory_used"]
    bigobj = bytearray(50 * 1024 * 1024)  # 50MB
    stats = get_system_stats()
    # NOTE not updated immediately
    assert stats["memory_used"] >= memory
    del bigobj


@pytest.mark.skipif(
    system() != "Linux", reason="procfs implementation only works on Linux"
)
def test_procfs_equals_psutil_children():
    """Test that deterministic fields in procfs implementation match psutil implementation."""
    from resource_tracker.tracker_procfs import get_pid_stats as procfs_pidstats
    from resource_tracker.tracker_psutil import get_pid_stats as psutil_pidstats

    pid = getpid()
    procfs_stats = procfs_pidstats(pid)
    psutil_stats = psutil_pidstats(pid)

    assert procfs_stats["children"] == psutil_stats["children"]


@pytest.mark.skipif(
    system() != "Linux", reason="procfs implementation only works on Linux"
)
@pytest.mark.parametrize(
    "field,percent_threshold,absolute_threshold,unit",
    [
        ("memory", None, 50_000, "KB"),
        ("utime", None, 0.25, "s"),
        ("stime", None, 1, "s"),
        ("read_bytes", 10, None, "B"),
        ("write_bytes", 10, None, "B"),
    ],
)
def test_procfs_equals_psutil_field_comparison(
    field, percent_threshold, absolute_threshold, unit
):
    """Test that specific fields in procfs implementation match psutil implementation within thresholds."""
    from resource_tracker.tracker_procfs import get_pid_stats as procfs_pidstats
    from resource_tracker.tracker_psutil import get_pid_stats as psutil_pidstats

    # make use of memory for testing
    if field == "memory":
        big_array = bytearray(100 * 1024 * 1024)
    # make use of cpu for testing
    if field == "utime":
        for i in range(1_000):
            i**i

    pid = getpid()
    procfs_stats = procfs_pidstats(pid)
    psutil_stats = psutil_pidstats(pid)

    value1 = procfs_stats[field]
    value2 = psutil_stats[field]
    diff = abs(value1 - value2)
    percent = diff / min(value1, value2) * 100 if value1 != 0 and value2 != 0 else 0
    if percent_threshold is not None:
        assert percent < percent_threshold, (
            f"{field} percent difference between {value1} (procfs) and {value2} (psutil) too large: {diff} {unit} ({percent:.2f}%)"
        )
    if absolute_threshold is not None:
        assert diff < absolute_threshold, (
            f"{field} absolute difference between {value1} (procfs) and {value2} (psutil) too large: {diff} {unit}"
        )
