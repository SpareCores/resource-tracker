"""
Helpers to track resource usage via psutil.
"""

from contextlib import suppress
from time import time
from typing import Dict, Set, Union

from psutil import (
    Process,
    cpu_times,
    disk_io_counters,
    disk_partitions,
    disk_usage,
    net_io_counters,
    pids,
    virtual_memory,
)

from .helpers import get_zfs_pools_space, is_partition
from .nvidia import (
    process_nvidia_smi,
    process_nvidia_smi_pmon,
    start_nvidia_smi,
    start_nvidia_smi_pmon,
)


def get_pid_stats(
    pid: int, children: bool = True
) -> Dict[str, Union[int, float, None, Set[int]]]:
    """Collect current/cumulative stats of a process via psutil.

    Args:
        pid: The process ID to track.
        children: Whether to include child processes.

    Returns:
        A dictionary containing process stats:

            - timestamp (float): The current timestamp.
            - pid (int): The process ID.
            - children (int | None): The current number of child processes.
            - utime (int): The total user mode CPU time in seconds.
            - stime (int): The total system mode CPU time in seconds.
            - memory (int): The current PSS (Proportional Set Size) on Linux,
              USS (Unique Set Size) on macOS and Windows, and RSS (Resident Set Size) on
              other OSs where neither PSS nor USS are available in kB. See more details at
              <https://gmpy.dev/blog/2016/real-process-memory-and-environ-in-python>.
            - read_bytes (int): The total number of bytes read.
            - write_bytes (int): The total number of bytes written.
            - gpu_usage (float): The current GPU utilization between 0 and GPU count.
            - gpu_vram (float): The current GPU memory used in MiB.
            - gpu_utilized (int): The number of GPUs with utilization > 0.
    """
    current_time = time()
    nvidia_process = start_nvidia_smi_pmon()

    processes = [Process(pid)]
    if children:
        current_children = processes[0].children(recursive=True)
        processes = processes + list(current_children)

    stats = {
        "timestamp": current_time,
        "pid": pid,
        "children": len(current_children) if children else None,
        "utime": 0,
        "stime": 0,
        "memory": 0,
        "read_bytes": 0,
        "write_bytes": 0,
    }

    for process in processes:
        # process might have been terminated, so silently skip if not found
        with suppress(Exception):
            cpu_times = process.cpu_times()
            stats["utime"] += cpu_times.user
            stats["stime"] += cpu_times.system
            memory_info = process.memory_full_info()
            for attr in ("pss", "uss", "rss"):
                if (
                    hasattr(memory_info, attr)
                    and getattr(memory_info, attr) is not None
                    and getattr(memory_info, attr) != 0
                ):
                    stats["memory"] += getattr(memory_info, attr) / 1024  # kB
                    break
            io_counters = process.io_counters()
            stats["read_bytes"] += io_counters.read_bytes
            stats["write_bytes"] += io_counters.write_bytes

    stats.update(process_nvidia_smi_pmon(nvidia_process, [p.pid for p in processes]))

    return stats


def get_system_stats() -> Dict[str, Union[int, float, Dict]]:
    """Collect current system-wide stats via psutil.

    Note that some fields are not available on all platforms,
    e.g. memory buffers/cache are specific to Linux and BSD,
    and active/inactive anonymous pages are specific to Linux,
    so `0` is returned for these fields on other platforms.

    Returns:
        A dictionary containing system stats:

            - timestamp (float): The current timestamp.
            - processes (int): Number of running processes.
            - utime (int): Total user mode CPU time in seconds.
            - stime (int): Total system mode CPU time in seconds.
            - memory_free (int): Free physical memory in kB.
            - memory_used (int): Used physical memory in kB (excluding buffers/cache).
            - memory_buffers (int): Memory used for buffers in kB.
            - memory_cached (int): Memory used for cache in kB.
            - memory_active (int): Memory used for active pages in kB.
            - memory_inactive (int): Memory used for inactive pages in kB.
            - disk_stats (dict): Dictionary mapping disk names to their stats:

                - read_bytes (int): Bytes read from this disk.
                - write_bytes (int): Bytes written to this disk.

            - disk_spaces (dict): Dictionary mapping mount points to their space stats:

                - total (int): Total space in bytes.
                - used (int): Used space in bytes.
                - free (int): Free space in bytes.

            - net_recv_bytes (int): Total bytes received over network.
            - net_sent_bytes (int): Total bytes sent over network.
    """
    stats = {
        "timestamp": time(),
        "processes": 0,
        "utime": 0,
        "stime": 0,
        "memory_free": 0,
        "memory_used": 0,
        "memory_buffers": 0,
        "memory_cached": 0,
        "memory_active": 0,
        "memory_inactive": 0,
        "disk_stats": {},
        "disk_spaces": {},
        "net_recv_bytes": 0,
        "net_sent_bytes": 0,
    }

    nvidia_process = start_nvidia_smi()

    cpu = cpu_times()
    stats["utime"] = cpu.user
    if hasattr(cpu, "nice"):
        stats["utime"] += cpu.nice
    stats["stime"] = cpu.system
    stats["processes"] = len(pids())

    # store memory stats in kB
    memory = virtual_memory()
    stats["memory_free"] = memory.free / 1024
    if hasattr(memory, "buffers"):
        stats["memory_buffers"] = memory.buffers / 1024
    if hasattr(memory, "cached"):
        stats["memory_cached"] = memory.cached / 1024
    if hasattr(memory, "active"):
        stats["memory_active"] = memory.active / 1024
    if hasattr(memory, "inactive"):
        stats["memory_inactive"] = memory.inactive / 1024
    stats["memory_used"] = memory.used / 1024

    disk_io = disk_io_counters(perdisk=True)
    stats["disk_stats"] = {
        disk_name: {
            "read_bytes": disk_io[disk_name].read_bytes,
            "write_bytes": disk_io[disk_name].write_bytes,
        }
        for disk_name in disk_io
        if not is_partition(disk_name)
    }

    net_io = net_io_counters()
    stats["net_recv_bytes"] = net_io.bytes_recv
    stats["net_sent_bytes"] = net_io.bytes_sent

    check_zfs = False
    disks = disk_partitions()
    for disk in disks:
        if disk.fstype == "zfs":
            check_zfs = True
            continue
        usage = disk_usage(disk.mountpoint)
        stats["disk_spaces"][disk.mountpoint] = {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
        }
    if check_zfs:
        stats["disk_spaces"].update(get_zfs_pools_space())

    stats.update(process_nvidia_smi(nvidia_process))

    return stats
