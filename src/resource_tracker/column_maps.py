"""Helper mappings."""

"""Mapping of column names to human-readable names."""
HUMAN_NAMES_MAPPING = {
    "timestamp": "Timestamp",
    # system-level metrics
    "processes": "processes",
    "utime": "CPU time (user)",
    "stime": "CPU time (system)",
    "cpu_usage": "CPU usage",
    "memory_free_mib": "free memory",
    "memory_used_mib": "used memory",
    "memory_buffers_mib": "memory buffers",
    "memory_cached_mib": "memory page/file cached",
    "memory_active_mib": "active memory",
    "memory_inactive_mib": "inactive memory",
    "disk_read_bytes": "disk read",
    "disk_write_bytes": "disk write",
    "disk_space_total_gb": "disk space total",
    "disk_space_used_gb": "disk space used",
    "disk_space_free_gb": "disk space free",
    "net_recv_bytes": "inbound network traffic",
    "net_sent_bytes": "outbound network traffic",
    "gpu_usage": "GPU usage",
    "gpu_vram_mib": "VRAM used",
    "gpu_utilized": "GPUs in use",
    # process-level metrics
    "pid": "PID",
    "children": "children",
    "memory_mib": "memory usage",
}

"""Mapping of how to convert column-specific values to bytes."""
BYTE_MAPPING = {
    # MiB -> B
    "memory_mib": 1024 * 1024,
    "memory_free_mib": 1024 * 1024,
    "memory_used_mib": 1024 * 1024,
    "memory_buffers_mib": 1024 * 1024,
    "memory_cached_mib": 1024 * 1024,
    "memory_active_mib": 1024 * 1024,
    "memory_inactive_mib": 1024 * 1024,
    "gpu_vram_mib": 1024 * 1024,
    # GiB -> B
    "disk_space_total_gb": 1000 * 1000 * 1000,
    "disk_space_used_gb": 1000 * 1000 * 1000,
    "disk_space_free_gb": 1000 * 1000 * 1000,
}

"""Ruleset to decide if a server is dedicated to the process(es) tracked or shared with other processes."""
SERVER_ALLOCATION_CHECKS = [
    {
        "process_column": "cpu_usage",
        "system_column": "cpu_usage",
        "percent": 1.25,
        "absolute": 0.25,
    },
    {
        "process_column": "memory_mib",
        "system_column": "memory_used_mib",
        "percent": 1.5,
        "absolute": 512 * 1024,  # 512 MiB
    },
    {
        "process_column": "gpu_usage",
        "system_column": "gpu_usage",
        "percent": 1.25,
        "absolute": 0.2,
    },
    {
        "process_column": "gpu_vram_mib",
        "system_column": "gpu_vram_mib",
        "percent": 1.25,
        "absolute": 512,  # 512 MiB
    },
]

"""Mapping of columns used in various charts of the HTML report."""
REPORT_CSV_MAPPING = {
    "cpu": ["Timestamp", "Process CPU usage", "System CPU usage"],
    "mem": ["Timestamp", "Process memory usage", "System used memory"],
    "disk": [
        "Timestamp",
        "Process disk read",
        "System disk read",
        "Process disk write",
        "System disk write",
    ],
    "disk_space": ["Timestamp", "System disk space used"],
    "net": [
        "Timestamp",
        "System inbound network traffic",
        "System outbound network traffic",
    ],
    "gpu_usage": ["Timestamp", "Process GPU usage", "System GPU usage"],
    "gpu_utilized": ["Timestamp", "Process GPUs in use", "System GPUs in use"],
    "gpu_vram_mib": ["Timestamp", "Process VRAM used", "System VRAM used"],
}

# ---------------------------------------------------------------------------
# v2 combined CSV column names (<level>_<scope>_<instance>_<metric>_<unit>_<kind>)
# ---------------------------------------------------------------------------

SYSTEM_TO_V2 = {
    "processes": "host_processes_all_total_count_gauge",
    "utime": "host_cpu_all_utime_s_delta",
    "stime": "host_cpu_all_stime_s_delta",
    "cpu_usage": "host_cpu_all_usage_core_gauge",
    "memory_free_mib": "host_memory_all_free_mib_gauge",
    "memory_used_mib": "host_memory_all_used_mib_gauge",
    "memory_buffers_mib": "host_memory_all_buffers_mib_gauge",
    "memory_cached_mib": "host_memory_all_cached_mib_gauge",
    "memory_active_mib": "host_memory_all_active_mib_gauge",
    "memory_inactive_mib": "host_memory_all_inactive_mib_gauge",
    "disk_read_bytes": "host_disk_all_read_bytes_delta",
    "disk_write_bytes": "host_disk_all_write_bytes_delta",
    "disk_space_total_gb": "host_disk_all_space_total_gb_gauge",
    "disk_space_used_gb": "host_disk_all_space_used_gb_gauge",
    "disk_space_free_gb": "host_disk_all_space_free_gb_gauge",
    "net_recv_bytes": "host_net_all_recv_bytes_delta",
    "net_sent_bytes": "host_net_all_sent_bytes_delta",
    "gpu_usage": "host_gpu_all_usage_core_gauge",
    "gpu_vram_mib": "host_gpu_all_memory_mib_gauge",
    "gpu_utilized": "host_gpu_all_utilized_count_gauge",
}

PROCESS_TO_V2 = {
    "utime": "proc_cpu_all_utime_s_delta",
    "stime": "proc_cpu_all_stime_s_delta",
    "cpu_usage": "proc_cpu_all_usage_core_gauge",
    "children": "proc_processes_all_children_count_gauge",
    "memory_mib": "proc_memory_all_used_mib_gauge",
    "disk_read_bytes": "proc_disk_all_read_bytes_delta",
    "disk_write_bytes": "proc_disk_all_write_bytes_delta",
    "gpu_usage": "proc_gpu_all_usage_core_gauge",
    "gpu_vram_mib": "proc_gpu_all_memory_mib_gauge",
    "gpu_utilized": "proc_gpu_all_utilized_count_gauge",
}

V2_HOST_COLUMNS = sorted(SYSTEM_TO_V2.values())
V2_CGROUP_COLUMNS: list = []
V2_PROC_COLUMNS = sorted(PROCESS_TO_V2.values())

V2_COMBINED_COLUMN_ORDER = (
    ["timestamp"] + V2_HOST_COLUMNS + V2_CGROUP_COLUMNS + V2_PROC_COLUMNS
)

V2_BYTE_MAPPING = {
    SYSTEM_TO_V2[col]: factor
    for col, factor in BYTE_MAPPING.items()
    if col in SYSTEM_TO_V2
} | {
    PROCESS_TO_V2[col]: factor
    for col, factor in BYTE_MAPPING.items()
    if col in PROCESS_TO_V2
}

V2_HUMAN_NAMES_MAPPING = {
    "timestamp": "Timestamp",
    "host_processes_all_total_count_gauge": "System processes",
    "host_cpu_all_utime_s_delta": "System CPU time (user)",
    "host_cpu_all_stime_s_delta": "System CPU time (system)",
    "host_cpu_all_usage_core_gauge": "System CPU usage",
    "host_memory_all_free_mib_gauge": "System free memory",
    "host_memory_all_used_mib_gauge": "System used memory",
    "host_memory_all_buffers_mib_gauge": "System memory buffers",
    "host_memory_all_cached_mib_gauge": "System memory page/file cached",
    "host_memory_all_active_mib_gauge": "System active memory",
    "host_memory_all_inactive_mib_gauge": "System inactive memory",
    "host_disk_all_read_bytes_delta": "System disk read",
    "host_disk_all_write_bytes_delta": "System disk write",
    "host_disk_all_space_total_gb_gauge": "System disk space total",
    "host_disk_all_space_used_gb_gauge": "System disk space used",
    "host_disk_all_space_free_gb_gauge": "System disk space free",
    "host_net_all_recv_bytes_delta": "System inbound network traffic",
    "host_net_all_sent_bytes_delta": "System outbound network traffic",
    "host_gpu_all_usage_core_gauge": "System GPU usage",
    "host_gpu_all_memory_mib_gauge": "System VRAM used",
    "host_gpu_all_utilized_count_gauge": "System GPUs in use",
    "proc_cpu_all_utime_s_delta": "Process CPU time (user)",
    "proc_cpu_all_stime_s_delta": "Process CPU time (system)",
    "proc_cpu_all_usage_core_gauge": "Process CPU usage",
    "proc_processes_all_children_count_gauge": "Process children",
    "proc_memory_all_used_mib_gauge": "Process memory usage",
    "proc_disk_all_read_bytes_delta": "Process disk read",
    "proc_disk_all_write_bytes_delta": "Process disk write",
    "proc_gpu_all_usage_core_gauge": "Process GPU usage",
    "proc_gpu_all_memory_mib_gauge": "Process VRAM used",
    "proc_gpu_all_utilized_count_gauge": "Process GPUs in use",
}

V2_REPORT_CSV_MAPPING = {
    "cpu": [
        "timestamp",
        "proc_cpu_all_usage_core_gauge",
        "host_cpu_all_usage_core_gauge",
    ],
    "mem": [
        "timestamp",
        "proc_memory_all_used_mib_gauge",
        "host_memory_all_used_mib_gauge",
    ],
    "disk": [
        "timestamp",
        "proc_disk_all_read_bytes_delta",
        "host_disk_all_read_bytes_delta",
        "proc_disk_all_write_bytes_delta",
        "host_disk_all_write_bytes_delta",
    ],
    "disk_space": ["timestamp", "host_disk_all_space_used_gb_gauge"],
    "net": [
        "timestamp",
        "host_net_all_recv_bytes_delta",
        "host_net_all_sent_bytes_delta",
    ],
    "gpu_usage": [
        "timestamp",
        "proc_gpu_all_usage_core_gauge",
        "host_gpu_all_usage_core_gauge",
    ],
    "gpu_utilized": [
        "timestamp",
        "proc_gpu_all_utilized_count_gauge",
        "host_gpu_all_utilized_count_gauge",
    ],
    "gpu_vram_mib": [
        "timestamp",
        "proc_gpu_all_memory_mib_gauge",
        "host_gpu_all_memory_mib_gauge",
    ],
}


def build_v2_combined_metrics(
    system_metrics,
    process_metrics,
    *,
    bytes: bool = False,
    human_names: bool = False,
):
    """Build a combined metrics dataframe using v2 column names and order."""
    from .tiny_data_frame import TinyDataFrame

    combined_data = {"timestamp": system_metrics["timestamp"]}

    for col, v2_col in SYSTEM_TO_V2.items():
        if col in system_metrics.columns:
            values = system_metrics[col]
            if bytes and col in BYTE_MAPPING:
                values = [v * BYTE_MAPPING[col] for v in values]
            combined_data[v2_col] = values

    for col, v2_col in PROCESS_TO_V2.items():
        if col in process_metrics.columns:
            values = process_metrics[col]
            if bytes and col in BYTE_MAPPING:
                values = [v * BYTE_MAPPING[col] for v in values]
            combined_data[v2_col] = values

    ordered = {
        column: combined_data[column]
        for column in V2_COMBINED_COLUMN_ORDER
        if column in combined_data
    }
    combined = TinyDataFrame(data=ordered)

    if human_names:
        combined = combined.rename(
            {col: V2_HUMAN_NAMES_MAPPING.get(col, col) for col in combined.columns}
        )

    return combined


def v2_report_chart_columns(chart_name: str, *, human_names: bool = False) -> list:
    """Return column names for an HTML report chart CSV series."""
    columns = V2_REPORT_CSV_MAPPING[chart_name]
    if not human_names:
        return columns
    return [V2_HUMAN_NAMES_MAPPING.get(col, col) for col in columns]
