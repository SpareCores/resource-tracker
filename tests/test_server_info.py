from resource_tracker.server_info import get_server_info, get_total_memory_mb


def test_get_total_memory_mb_implementations():
    """Test get_total_memory_mb from different implementations."""
    memory = get_total_memory_mb()
    assert memory > 0


def test_server_info():
    """Test server_info."""
    info = get_server_info()
    assert info["os"] is not None
    assert info["vcpus"] > 0
    assert info["memory_mb"] > 0
    assert info["gpu_count"] >= 0
    assert info["gpu_memory_mb"] >= 0
