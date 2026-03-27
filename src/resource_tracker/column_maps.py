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
    "disk_space_total_gib": "disk space total",
    "disk_space_used_gib": "disk space used",
    "disk_space_free_gib": "disk space free",
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
    # MiB -> B
    "gpu_vram_mib": 1024 * 1024,
    # GiB -> B
    "disk_space_total_gib": 1024 * 1024 * 1024,
    "disk_space_used_gib": 1024 * 1024 * 1024,
    "disk_space_free_gib": 1024 * 1024 * 1024,
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
