"""Tests for v2 combined CSV column mappings."""

from resource_tracker.column_maps import (
    PROCESS_TO_V2,
    SYSTEM_TO_V2,
    V2_BYTE_MAPPING,
    V2_COMBINED_COLUMN_ORDER,
    V2_HOST_COLUMNS,
    V2_PROC_COLUMNS,
    build_v2_combined_metrics,
)


def test_system_to_v2_mapping_complete():
    expected = {
        "processes",
        "utime",
        "stime",
        "cpu_usage",
        "memory_free_mib",
        "memory_used_mib",
        "memory_buffers_mib",
        "memory_cached_mib",
        "memory_active_mib",
        "memory_inactive_mib",
        "disk_read_bytes",
        "disk_write_bytes",
        "disk_space_total_gb",
        "disk_space_used_gb",
        "disk_space_free_gb",
        "net_recv_bytes",
        "net_sent_bytes",
        "gpu_usage",
        "gpu_vram_mib",
        "gpu_utilized",
    }
    assert set(SYSTEM_TO_V2) == expected
    assert all(name.startswith("host_") for name in SYSTEM_TO_V2.values())


def test_process_to_v2_mapping_excludes_pid():
    assert "pid" not in PROCESS_TO_V2
    assert all(name.startswith("proc_") for name in PROCESS_TO_V2.values())


def test_v2_combined_column_order():
    assert V2_COMBINED_COLUMN_ORDER[0] == "timestamp"
    assert V2_COMBINED_COLUMN_ORDER[1 : 1 + len(V2_HOST_COLUMNS)] == V2_HOST_COLUMNS
    proc_start = 1 + len(V2_HOST_COLUMNS)
    assert (
        V2_COMBINED_COLUMN_ORDER[proc_start : proc_start + len(V2_PROC_COLUMNS)]
        == V2_PROC_COLUMNS
    )
    assert V2_HOST_COLUMNS == sorted(V2_HOST_COLUMNS)
    assert V2_PROC_COLUMNS == sorted(V2_PROC_COLUMNS)


def test_v2_byte_mapping_covers_memory_and_disk_columns():
    assert "host_memory_all_used_mib_gauge" in V2_BYTE_MAPPING
    assert "proc_memory_all_used_mib_gauge" in V2_BYTE_MAPPING
    assert "host_disk_all_space_used_gb_gauge" in V2_BYTE_MAPPING


def test_build_v2_combined_metrics_order_and_names():
    from resource_tracker.tiny_data_frame import TinyDataFrame

    system_metrics = TinyDataFrame(
        data={
            "timestamp": [1.0, 2.0],
            "cpu_usage": [0.1, 0.2],
            "memory_used_mib": [100.0, 200.0],
        }
    )
    process_metrics = TinyDataFrame(
        data={
            "timestamp": [1.0, 2.0],
            "pid": [123, 123],
            "cpu_usage": [0.05, 0.06],
            "memory_mib": [50.0, 60.0],
        }
    )

    combined = build_v2_combined_metrics(system_metrics, process_metrics)
    assert combined.columns == [
        col
        for col in V2_COMBINED_COLUMN_ORDER
        if col
        in {
            "timestamp",
            "host_cpu_all_usage_core_gauge",
            "host_memory_all_used_mib_gauge",
            "proc_cpu_all_usage_core_gauge",
            "proc_memory_all_used_mib_gauge",
        }
    ]
    assert "proc_pid" not in combined.columns
    assert "process_pid" not in combined.columns
