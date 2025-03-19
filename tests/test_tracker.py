import importlib
from os import getpid

import pytest


@pytest.mark.parametrize(
    "tracker_implementation",
    ["resource_tracker.tracker_psutil", "resource_tracker.tracker_procfs"],
)
def test_get_pid_stats_implementations(tracker_implementation):
    """Test get_pid_stats from different implementations."""
    module = importlib.import_module(tracker_implementation)
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
    assert stats["memory"] >= memory + 10 * 1024 * 1024
    del bigobj
