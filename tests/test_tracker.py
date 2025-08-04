from importlib import import_module
from os import getpid
from platform import system

import pytest

from resource_tracker.dummy_workloads import cpu_single


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
def test_get_process_stats_implementations(tracker_implementation):
    """Test get_process_stats from different implementations."""
    module = import_module(tracker_implementation)
    get_process_stats = getattr(module, "get_process_stats")

    pid = getpid()
    stats = get_process_stats(pid)

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
    stats = get_process_stats(pid)
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
    assert stats["processes"] > 0
    assert stats["utime"] > 0
    assert stats["stime"] > 0
    assert stats["memory_free"] > 0
    assert stats["memory_used"] > 0


@pytest.mark.skipif(
    system() != "Linux", reason="procfs implementation only works on Linux"
)
@pytest.mark.parametrize(
    "field,percent_threshold,absolute_threshold,unit",
    [
        ("children", None, 0, "processes"),
        ("memory", None, 50_000, "KB"),
        ("utime", None, 0.25, "s"),
        ("stime", None, 1, "s"),
        ("read_bytes", 10, None, "B"),
        ("write_bytes", 10, None, "B"),
    ],
)
def test_process_stats_procfs_vs_psutil(
    field, percent_threshold, absolute_threshold, unit
):
    """Test that fields in procfs process_stats implementation match psutil implementation within thresholds."""
    from resource_tracker.tracker_procfs import (
        get_process_stats as procfs_process_stats,
    )
    from resource_tracker.tracker_psutil import (
        get_process_stats as psutil_process_stats,
    )

    # make use of memory for testing
    if field == "memory":
        big_array = bytearray(100 * 1024 * 1024)
    # make use of cpu for testing
    if field == "utime":
        for i in range(1_000):
            i**i

    pid = getpid()
    procfs_stats = procfs_process_stats(pid)
    psutil_stats = psutil_process_stats(pid)

    value1 = procfs_stats[field]
    value2 = psutil_stats[field]
    diff = abs(value1 - value2)
    percent = diff / min(value1, value2) * 100 if value1 != 0 and value2 != 0 else 0
    if percent_threshold is not None:
        assert percent <= percent_threshold, (
            f"{field} percent difference between {value1} (procfs) and {value2} (psutil) too large: {diff} {unit} ({percent:.2f}%)"
        )
    if absolute_threshold is not None:
        assert diff <= absolute_threshold, (
            f"{field} absolute difference between {value1} (procfs) and {value2} (psutil) too large: {diff} {unit}"
        )

    if field == "memory":
        del big_array


@pytest.mark.skipif(
    system() != "Linux", reason="procfs implementation only works on Linux"
)
@pytest.mark.parametrize(
    "field,percent_threshold,absolute_threshold,unit",
    [
        ("processes", None, 5, "processes"),
        ("utime", None, 0.25, "s"),
        ("stime", None, 1, "s"),
        ("memory_free", None, 50_000, "KB"),
        ("memory_used", None, 50_000, "KB"),
        ("memory_buffers", None, 50_000, "KB"),
        ("memory_cached", None, 50_000, "KB"),
        ("memory_active", None, 50_000, "KB"),
        ("memory_inactive", None, 50_000, "KB"),
        ("net_recv_bytes", 10, None, "B"),
        ("net_sent_bytes", 10, None, "B"),
        ("gpu_usage", None, 0.25, "GPUs"),
        ("gpu_vram", None, 50_000, "MiB"),
        ("gpu_utilized", None, 0, "GPUs"),
    ],
)
def test_systemstats_procfs_vs_psutil(
    field, percent_threshold, absolute_threshold, unit
):
    """Test that fields in procfs systemstats implementation match psutil implementation within thresholds."""
    from resource_tracker.tracker_procfs import get_system_stats as procfs_systemstats
    from resource_tracker.tracker_psutil import get_system_stats as psutil_systemstats

    procfs_stats = procfs_systemstats()
    psutil_stats = psutil_systemstats()

    value1 = procfs_stats[field]
    value2 = psutil_stats[field]
    diff = abs(value1 - value2)
    percent = diff / min(value1, value2) * 100 if value1 != 0 and value2 != 0 else 0
    if percent_threshold is not None:
        assert percent <= percent_threshold, (
            f"{field} percent difference between {value1} (procfs) and {value2} (psutil) too large: {diff} {unit} ({percent:.2f}%)"
        )
    if absolute_threshold is not None:
        assert diff <= absolute_threshold, (
            f"{field} absolute difference between {value1} (procfs) and {value2} (psutil) too large: {diff} {unit}"
        )


def wait_for_tracker(
    tracker, check_process_tracker=True, check_system_tracker=True, timeout=5
):
    """Burn CPU until the resource tracker has collected data.

    Args:
        tracker: The resource tracker to wait for.
        check_process_tracker: Whether to check the process tracker.
        check_system_tracker: Whether to check the system tracker.
        timeout: The timeout in seconds.
    """
    for i in range(timeout * 10):
        if check_process_tracker and check_system_tracker:
            if tracker.n_samples > 0:
                break
        elif check_process_tracker and len(tracker.process_metrics) > 0:
            break
        elif check_system_tracker and len(tracker.system_metrics) > 0:
            break
        cpu_single(duration=0.1)
    else:
        pytest.fail(f"No data collected after {timeout} seconds")


def test_resource_tracker_subprocesses():
    """Test that the resource tracker subprocess is working."""
    from resource_tracker import ResourceTracker

    tracker = ResourceTracker()
    tracker.start()
    wait_for_tracker(tracker)
    tracker.stop()
    assert len(tracker.process_metrics) > 0
    assert len(tracker.system_metrics) > 0
    assert tracker.process_metrics[0]["utime"] >= 0
    assert tracker.system_metrics[0]["utime"] >= 0
    assert tracker.process_metrics[0]["memory"] > 0
    assert tracker.system_metrics[0]["memory_used"] > 0
    assert tracker.system_metrics[0]["processes"] > 0


def test_resource_tracker_subprocess():
    """Test that the partial resource tracker subprocess is working."""
    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(track_processes=False)
    tracker.start()
    wait_for_tracker(tracker, check_process_tracker=False)
    tracker.stop()
    assert len(tracker.process_metrics) == 0
    assert len(tracker.system_metrics) > 0
    assert tracker.system_metrics[0]["utime"] >= 0
    assert tracker.system_metrics[0]["memory_used"] > 0
    assert tracker.system_metrics[0]["processes"] > 0


def test_resource_tracker_combined_metrics():
    """Test that the combined metrics getter is working."""
    from resource_tracker import ResourceTracker

    tracker = ResourceTracker()
    tracker.start()
    wait_for_tracker(tracker)
    tracker.stop()
    assert len(tracker.get_combined_metrics()) > 0
    assert tracker.get_combined_metrics()[0]["system_utime"] >= 0
    assert (
        tracker.get_combined_metrics(human_names=True)[0]["System CPU time (user)"] >= 0
    )
    assert tracker.get_combined_metrics()[0]["process_utime"] >= 0
    assert (
        tracker.get_combined_metrics(human_names=True)[0]["Process CPU time (user)"]
        >= 0
    )
    assert tracker.get_combined_metrics()[0]["system_memory_used"] > 0
    assert tracker.get_combined_metrics()[0]["process_memory"] > 0
    assert (
        tracker.get_combined_metrics(bytes=True)[0]["process_memory"]
        > tracker.get_combined_metrics(bytes=False)[0]["process_memory"]
    )
    assert tracker.stats()["process_cpu_usage"]["max"] > 0
    assert tracker.stats()["process_memory"]["mean"] > 0


def test_resource_tracker_report():
    """Test that the report is working."""
    from resource_tracker import ResourceTracker

    tracker = ResourceTracker()
    tracker.start()
    wait_for_tracker(tracker)

    report = tracker.report()
    assert "Process CPU usage" in report
    assert "System CPU usage" in report
    assert "Pending" in report

    tracker.stop()
    report = tracker.report()
    assert "Finished" in report

    report = tracker.report(status_failed=True)
    assert "Failed" in report
