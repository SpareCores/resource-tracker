"""
Helpers to track resource usage via procfs.

Note that procfs is specific to Linux, and these helpers rely on modern (2017+)
kernel features, such as `smaps_rollup`, which is much faster than iterating
over all `smaps` files.
"""

from contextlib import suppress
from functools import cache
from glob import glob
from os import listdir, statvfs, sysconf
from time import time
from typing import Dict, Set, Union

from .helpers import get_zfs_pools_space, is_partition
from .nvidia import (
    process_nvidia_smi,
    process_nvidia_smi_pmon,
    start_nvidia_smi,
    start_nvidia_smi_pmon,
)


@cache
def get_sector_sizes() -> Dict[str, int]:
    """Get the sector size of all disks.

    Returns:
        A dictionary mapping disk names to their sector sizes.
    """
    sector_sizes = {}
    with suppress(FileNotFoundError):
        for disk_path in glob("/sys/block/*/"):
            disk_name = disk_path.split("/")[-2]
            if is_partition(disk_name):
                continue
            try:
                with open(f"{disk_path}queue/hw_sector_size", "r") as f:
                    sector_sizes[disk_name] = int(f.read().strip())
            except (FileNotFoundError, ValueError):
                sector_sizes[disk_name] = 512
    return sector_sizes


def get_pid_children(pid: int) -> Set[int]:
    """Get all descendant processes recursively.

    Args:
        pid: The process ID to get descendant processes for.

    Returns:
        All descendant process ids.
    """
    try:
        with open(f"/proc/{pid}/task/{pid}/children", "r") as f:
            children = {int(child) for child in f.read().strip().split()}
            descendants = set()
            for child in children:
                descendants.update(get_pid_children(child))
            return children | descendants
    except (ProcessLookupError, FileNotFoundError):
        return set()


def get_pid_rss(pid: int) -> int:
    """Get the current resident set size of a process.

    Args:
        pid: The process ID to get the resident set size for.

    Returns:
        The current resident set size of the process in kB.
    """
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS"):
                    return int(line.split()[1])
    except (ProcessLookupError, FileNotFoundError):
        return 0


def get_pid_pss_rollup(pid: int) -> int:
    """Reads the total PSS from `/proc/{pid}/smaps_rollup`.

    Args:
        pid: The process ID to get the total PSS for.

    Returns:
        The total PSS in kB.
    """
    with suppress(ProcessLookupError, FileNotFoundError):
        with open(f"/proc/{pid}/smaps_rollup", "r") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    return 0


def get_pid_proc_times(pid: int, children: bool = True) -> Dict[str, int]:
    """Get the current user and system times of a process from `/proc/{pid}/stat`.

    Note that cannot use `cutime`/`cstime` for real-time monitoring,
    as they need to wait for the children to exit.

    Args:
        pid: Process ID to track
        children: Whether to include stats from exited child processes

    Returns:
        A dictionary containing process time information:
            - `utime` (int): User mode CPU time in clock ticks
            - `stime` (int): System mode CPU time in clock ticks
    """
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            values = f.read().split()
            # https://docs.kernel.org/filesystems/proc.html
            return {
                "utime": int(values[13]) + (int(values[15]) if children else 0),
                "stime": int(values[14]) + (int(values[16]) if children else 0),
            }
    except (ProcessLookupError, FileNotFoundError):
        return {"utime": 0, "stime": 0}


def get_pid_proc_io(pid: int) -> Dict[str, int]:
    """Get the total bytes read and written by a process from `/proc/{pid}/io`.

    Note that it is not tracking reading from memory-mapped objects,
    and is fairly limited in what it can track. E.g. the process might
    not even have permissions to read its own `/proc/self/io`.

    Args:
        pid: The process ID to get the total bytes read and written for.

    Returns:
        A dictionary containing the total bytes read and written by the process.
    """
    try:
        with open(f"/proc/{pid}/io", "r") as f:
            return {
                parts[0]: int(parts[1]) for line in f if (parts := line.split(": "))
            }
    except (ProcessLookupError, FileNotFoundError, PermissionError):
        return {"read_bytes": 0, "write_bytes": 0}


def get_pid_stats(
    pid: int, children: bool = True
) -> Dict[str, Union[int, float, None, Set[int]]]:
    """Collect current/cumulative stats of a process from procfs.

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
            - memory (int): The current PSS (Proportional Set Size) in kB.
            - read_bytes (int): The total number of bytes read.
            - write_bytes (int): The total number of bytes written.
            - gpu_usage (float): The current GPU utilization between 0 and GPU count.
            - gpu_vram (float): The current GPU memory used in MiB.
            - gpu_utilized (int): The number of GPUs with utilization > 0.
    """
    current_time = time()

    nvidia_process = start_nvidia_smi_pmon()

    current_children = get_pid_children(pid)
    current_pss = get_pid_pss_rollup(pid)
    if children:
        for child in current_children:
            current_pss += get_pid_pss_rollup(child)
    current_proc_times = get_pid_proc_times(pid, children)
    if children:
        for child in current_children:
            current_proc_times["utime"] += get_pid_proc_times(child, True)["utime"]
            current_proc_times["stime"] += get_pid_proc_times(child, True)["stime"]
    current_io = get_pid_proc_io(pid)
    if children:
        for child in current_children:
            child_io = get_pid_proc_io(child)
            for key in set(current_io) & set(child_io):
                current_io[key] += child_io[key]

    gpu_stats = process_nvidia_smi_pmon(nvidia_process, {pid} | current_children)

    return {
        "timestamp": current_time,
        "pid": pid,
        "children": len(current_children) if children else None,
        "utime": current_proc_times["utime"] / sysconf("SC_CLK_TCK"),
        "stime": current_proc_times["stime"] / sysconf("SC_CLK_TCK"),
        "memory": current_pss,
        "read_bytes": current_io["read_bytes"],
        "write_bytes": current_io["write_bytes"],
        **gpu_stats,
    }


def get_system_stats() -> Dict[str, Union[int, float, Dict]]:
    """Collect current system-wide stats from procfs.

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

    with suppress(FileNotFoundError):
        with open("/proc/stat", "r") as f:
            for line in f:
                if line.startswith("cpu "):
                    cpu_stats = line.split()
                    tps = sysconf("SC_CLK_TCK")
                    # user + nice
                    stats["utime"] = (int(cpu_stats[1]) + int(cpu_stats[2])) / tps
                    stats["stime"] = int(cpu_stats[3]) / tps
        stats["processes"] = len([x for x in listdir("/proc") if x.isdigit()])

    # memory stats reported in kB
    with suppress(FileNotFoundError):
        with open("/proc/meminfo", "r") as f:
            mem_info = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    value_parts = parts[1].strip().split()
                    if len(value_parts) > 0:
                        try:
                            mem_info[key] = int(value_parts[0])
                        except ValueError:
                            pass

            total = mem_info.get("MemTotal", 0)
            stats["memory_free"] = mem_info.get("MemFree", 0)
            stats["memory_buffers"] = mem_info.get("Buffers", 0)
            stats["memory_cached"] = mem_info.get("Cached", 0)
            stats["memory_cached"] += mem_info.get("SReclaimable", 0)
            stats["memory_used"] = (
                total
                - stats["memory_free"]
                - stats["memory_buffers"]
                - stats["memory_cached"]
            )
            stats["memory_active"] = mem_info.get("Active", 0)
            stats["memory_inactive"] = mem_info.get("Inactive", 0)

    with suppress(FileNotFoundError):
        with open("/proc/diskstats", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 14:
                    disk_name = parts[2]
                    if not is_partition(disk_name):
                        sector_size = get_sector_sizes().get(disk_name, 512)
                        stats["disk_stats"][disk_name] = {
                            "read_bytes": int(parts[5]) * sector_size,
                            "write_bytes": int(parts[9]) * sector_size,
                        }

    with suppress(FileNotFoundError):
        with open("/proc/net/dev", "r") as f:
            # skip header lines
            next(f)
            next(f)
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    interface = parts[0].strip()
                    if interface != "lo":
                        values = parts[1].strip().split()
                        stats["net_recv_bytes"] += int(values[0])
                        stats["net_sent_bytes"] += int(values[8])

    check_zfs = False
    with suppress(FileNotFoundError):
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mount_point = parts[1]
                    filesystem = parts[2]
                    # skip known virtual filesystems
                    if mount_point.startswith(("/proc", "/sys", "/dev", "/run")):
                        continue
                    # skip zfs, will count later due to overlapping partitions
                    if filesystem == "zfs":
                        check_zfs = True
                        continue
                    try:
                        fs_stats = statvfs(mount_point)
                        # skip pseudo filesystems
                        if fs_stats.f_blocks == 0:
                            continue
                        block_size = fs_stats.f_frsize
                        total_space = fs_stats.f_blocks * block_size
                        free_space = fs_stats.f_bavail * block_size
                        used_space = total_space - free_space
                        stats["disk_spaces"][mount_point] = {
                            "total": total_space,
                            "used": used_space,
                            "free": free_space,
                        }
                    except (OSError, PermissionError):
                        pass
    if check_zfs:
        stats["disk_spaces"].update(get_zfs_pools_space())

    stats.update(process_nvidia_smi(nvidia_process))

    return stats
