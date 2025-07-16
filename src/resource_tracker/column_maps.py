HUMAN_NAMES_MAPPING = {
    "timestamp": "Timestamp",
    # system-level metrics
    "processes": "processes",
    "utime": "CPU time (user)",
    "stime": "CPU time (system)",
    "cpu_usage": "CPU usage",
    "memory_free": "free memory",
    "memory_used": "used memory",
    "memory_buffers": "memory buffers",
    "memory_cached": "memory page/file cached",
    "memory_active": "active memory",
    "memory_inactive": "inactive memory",
    "disk_read_bytes": "disk read",
    "disk_write_bytes": "disk write",
    "disk_space_total_gb": "disk space total",
    "disk_space_used_gb": "disk space used",
    "disk_space_free_gb": "disk space free",
    "net_recv_bytes": "inbound network traffic",
    "net_sent_bytes": "outbound network traffic",
    "gpu_usage": "GPU usage",
    "gpu_vram": "VRAM used",
    "gpu_utilized": "GPUs in use",
    # process-level metrics
    "pid": "PID",
    "children": "children",
    "memory": "memory usage",
    "read_bytes": "disk read",
    "write_bytes": "disk write",
}

BYTE_MAPPING = {
    # KiB -> B
    "memory": 1024,
    "memory_free": 1024,
    "memory_used": 1024,
    "memory_buffers": 1024,
    "memory_cached": 1024,
    "memory_active": 1024,
    "memory_inactive": 1024,
    # MiB -> B
    "gpu_vram": 1024 * 1024,
    # GiB -> B
    "disk_space_total_gb": 1024 * 1024 * 1024,
    "disk_space_used_gb": 1024 * 1024 * 1024,
    "disk_space_free_gb": 1024 * 1024 * 1024,
}

SERVER_ALLOCATION_CHECKS = [
    {
        "process_column": "cpu_usage",
        "system_column": "cpu_usage",
        "percent": 1.25,
        "absolute": 0.25,
    },
    {
        "process_column": "memory",
        "system_column": "memory_used",
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
        "process_column": "gpu_vram",
        "system_column": "gpu_vram",
        "percent": 1.25,
        "absolute": 512,  # 512 MiB
    },
]
