from contextlib import suppress
from os import cpu_count
from subprocess import check_output


def get_total_memory_mb():
    """Get total system memory in MB from /proc/meminfo."""
    with suppress(Exception):
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if "MemTotal" in line:
                    parts = line.split(":")
                    kb = int(parts[1].strip().split()[0])
                    return round(kb / (1024), 2)
    return 0


def get_gpu_info():
    """Get GPU information using nvidia-smi command."""
    result = {"count": 0, "memory_mb": 0}

    with suppress(Exception):
        nvidia_smi_output = check_output(
            [
                "nvidia-smi",
                "--query-gpu=count,memory.total",
                "--format=csv,noheader,nounits",
            ],
            universal_newlines=True,
        )

        lines = nvidia_smi_output.strip().split("\n")
        result["count"] = len(lines)

        total_memory_mb = 0
        for line in lines:
            if line.strip():
                # Format is: count, memory.total
                parts = line.split(",")
                if len(parts) >= 2:
                    memory_mb = float(parts[1].strip())
                    total_memory_mb += memory_mb

        result["memory_mb"] = total_memory_mb

    return result


def get_server_info():
    """
    Collects important information about the Linux server.

    Returns:
        dict: A dictionary containing server information:
            - vcpus: Number of virtual CPUs
            - memory_mb: Total memory in MB
            - gpu_count: Number of GPUs (if available)
            - gpu_memory_mb: Total GPU memory in MB (if available)
    """
    gpu_info = get_gpu_info()
    info = {
        "vcpus": cpu_count(),
        "memory_mb": get_total_memory_mb(),
        "gpu_count": gpu_info["count"],
        "gpu_memory_mb": gpu_info["memory_mb"],
    }
    return info
