from pytest import raises

from resource_tracker.helpers import aggregate_stats


def test_aggregate_stats_empty_list():
    """Test that aggregate_stats returns an empty dict when given an empty list."""
    result = aggregate_stats([])
    assert result == {}


def test_aggregate_stats_single_stats():
    """Test that aggregate_stats returns the same stats when given a single stats dict."""
    stats = {
        "process_cpu_usage": {"mean": 1.5, "max": 2.0},
        "process_memory": {"mean": 100, "max": 150},
    }
    result = aggregate_stats([stats])

    # Check that the structure is preserved
    assert "process_cpu_usage" in result
    assert "process_memory" in result

    # Check that the values are the same
    assert result["process_cpu_usage"]["mean"] == 1.5
    assert result["process_cpu_usage"]["max"] == 2.0
    assert result["process_memory"]["mean"] == 100
    assert result["process_memory"]["max"] == 150


def test_aggregate_stats_multiple_stats():
    """Test that aggregate_stats correctly aggregates multiple stats dicts."""
    stats1 = {
        "process_cpu_usage": {"mean": 1.5, "max": 2.0},
        "process_memory": {"mean": 100, "max": 150},
        "process_gpu_usage": {"mean": 0.0, "max": 0.0},
        "timestamp": {"duration": 0.5},
    }
    stats2 = {
        "process_cpu_usage": {"mean": 2.5, "max": 3.0},
        "process_memory": {"mean": 200, "max": 250},
        "process_gpu_usage": {"mean": 1.0, "max": 1.0},
        "timestamp": {"duration": 1.5},
    }
    stats3 = {
        "process_cpu_usage": {"mean": 3.5, "max": 4.0},
        "process_memory": {"mean": 300, "max": 350},
        "system_net_recv_bytes": {"sum": 1000},
        "timestamp": {"duration": 2.5},
    }

    result = aggregate_stats([stats1, stats2, stats3])

    # Check mean values (should be averaged)
    assert result["process_cpu_usage"]["mean"] == (1.5 + 2.5 + 3.5) / 3
    assert result["process_memory"]["mean"] == (100 + 200 + 300) / 3
    assert result["process_gpu_usage"]["mean"] == (0.0 + 1.0) / 2

    # Check max values (should be maximum)
    assert result["process_cpu_usage"]["max"] == 4.0
    assert result["process_memory"]["max"] == 350
    assert result["process_gpu_usage"]["max"] == 1.0

    # Check sum values (should be maximum, not summed)
    assert result["system_net_recv_bytes"]["sum"] == 1000

    # Check duration (should be averaged)
    assert result["timestamp"]["duration"] == (0.5 + 1.5 + 2.5) / 3


def test_aggregate_stats_different_keys():
    """Test that aggregate_stats handles stats dicts with different keys."""
    stats1 = {
        "process_cpu_usage": {"mean": 1.5, "max": 2.0},
    }
    stats2 = {
        "process_memory": {"mean": 200, "max": 250},
    }

    result = aggregate_stats([stats1, stats2])

    assert "process_cpu_usage" in result
    assert "process_memory" in result
    assert result["process_cpu_usage"]["mean"] == 1.5
    assert result["process_memory"]["mean"] == 200


def test_aggregate_stats_different_agg_types():
    """Test that aggregate_stats handles stats dicts with different aggregation types."""
    stats1 = {
        "process_cpu_usage": {"mean": 1.5},
    }
    stats2 = {
        "process_cpu_usage": {"max": 2.5},
    }

    result = aggregate_stats([stats1, stats2])

    assert "mean" in result["process_cpu_usage"]
    assert "max" in result["process_cpu_usage"]
    assert result["process_cpu_usage"]["mean"] == 1.5
    assert result["process_cpu_usage"]["max"] == 2.5


def test_aggregate_stats_with_custom_agg_type():
    """Test that aggregate_stats fails with unsupported aggregation types."""
    stats1 = {
        "process_cpu_usage": {"custom": "value1"},
    }
    stats2 = {
        "process_cpu_usage": {"custom": "value2"},
    }

    with raises(ValueError):
        aggregate_stats([stats1, stats2])
