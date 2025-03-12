"""
Track resource usage of a process or server.
"""

from contextlib import suppress
from csv import QUOTE_NONNUMERIC
from csv import writer as csv_writer
from functools import cache
from glob import glob
from os import getpid, statvfs, sysconf
from re import search
from subprocess import PIPE, Popen, TimeoutExpired
from sys import stdout
from time import sleep, time
from typing import Optional


@cache
def is_partition(disk_name: str) -> bool:
    """
    Determine if a disk name represents a partition rather than a whole disk.

    Args:
        disk_name: Name of the disk device (e.g., 'sda1', 'nvme0n1p1')

    Returns:
        True if the device is likely a partition, False otherwise
    """
    # common partition name patterns: sdXN, nvmeXnYpZ, mmcblkXpY
    if search(r"(sd[a-z]+|nvme\d+n\d+|mmcblk\d+)p?\d+$", disk_name):
        # check if there's a parent device in /sys/block/
        parent_devices = [d.split("/")[-2] for d in glob("/sys/block/*/")]
        if any(
            disk_name.startswith(parent) and disk_name != parent
            for parent in parent_devices
        ):
            return True
    return False


def get_pid_children(pid: int) -> set[int]:
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


def get_pid_proc_times(pid: int, children: bool = True) -> dict[str, int]:
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


def get_pid_proc_io(pid: int) -> dict[str, int]:
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
) -> dict[str, int | float | None | set[int]]:
    """Collect current/cumulative stats of a process from procfs.

    Args:
        pid: The process ID to track.
        children: Whether to include child processes.

    Returns:
        A dictionary containing process stats:

            - timestamp (float): The current timestamp.
            - pid (int): The process ID.
            - children (int | None): The current number of child processes.
            - utime (int): The total user mode CPU time in clock ticks.
            - stime (int): The total system mode CPU time in clock ticks.
            - pss_rollup (int): The current PSS (Proportional Set Size) in kB.
            - read_bytes (int): The total number of bytes read.
            - write_bytes (int): The total number of bytes written.
            - gpu_usage (float): The current GPU utilization between 0 and GPU count.
            - gpu_vram (float): The current GPU memory used in MiB.
            - gpu_utilized (int): The number of GPUs with utilization > 0.
    """
    current_time = time()

    # NOTE pmon is limited to monitoring max. 4 GPUs
    with suppress(FileNotFoundError):
        nvidia_process = Popen(
            ["nvidia-smi", "pmon", "-c", "1", "-s", "um", "-d", "1"],
            stdout=PIPE,
        )

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

    gpu_stats = {
        "gpu_usage": 0,  # between 0 and GPU count
        "gpu_vram": 0,  # MiB
        "gpu_utilized": 0,  # number of GPUs with utilization > 0
        "gpu_utilized_indexes": set(),  # set of GPU indexes
    }
    try:
        stdout, _ = nvidia_process.communicate(timeout=0.5)
        if nvidia_process.returncode == 0:
            for index, line in enumerate(stdout.splitlines()):
                if index < 2:
                    continue  # skip the header lines
                parts = line.decode().split()
                # skip unmonitored processes
                if int(parts[1]) == int(pid) or (
                    children and int(parts[1]) in current_children
                ):
                    usage = 0
                    if parts[3] != "-":  # sm%
                        usage = float(parts[3])
                        gpu_stats["gpu_utilized_indexes"].add(int(parts[0]))
                    gpu_stats["gpu_usage"] += usage / 100
                    gpu_stats["gpu_vram"] += float(parts[9])
            gpu_stats["gpu_utilized"] = len(gpu_stats["gpu_utilized_indexes"])
    except TimeoutExpired:
        nvidia_process.kill()
    except Exception:
        pass

    return {
        "timestamp": current_time,
        "pid": pid,
        "children": len(current_children) if children else None,
        "utime": current_proc_times["utime"],
        "stime": current_proc_times["stime"],
        "pss": current_pss,
        "read_bytes": current_io["read_bytes"],
        "write_bytes": current_io["write_bytes"],
        **gpu_stats,
    }


def get_system_stats() -> dict[str, int | float | dict]:
    """Collect current system-wide stats from procfs.

    Returns:
        A dictionary containing system stats:

            - timestamp (float): The current timestamp.
            - processes (int): Number of running processes.
            - utime (int): Total user mode CPU time in clock ticks.
            - stime (int): Total system mode CPU time in clock ticks.
            - memory_used (int): Used physical memory in kB (excluding buffers/cache).
            - memory_buffers (int): Memory used for buffers in kB.
            - memory_cached (int): Memory used for cache in kB.
            - memory_active_anon (int): Memory used for anonymous pages in kB.
            - memory_inactive_anon (int): Memory used for inactive anonymous pages in kB.
            - disk_stats (dict): Dictionary mapping disk names to their stats:

                - read_sectors (int): Sectors read from this disk.
                - write_sectors (int): Sectors written to this disk.

            - disk_spaces (dict): Dictionary mapping mount points to their space stats:

                - total (int): Total space in bytes.
                - used (int): Used space in bytes.
                - free (int): Free space in bytes.

            - net_recv_bytes (int): Total bytes received over network.
            - net_sent_bytes (int): Total bytes sent over network.
    """
    current_time = time()
    stats = {
        "timestamp": current_time,
        "processes": 0,
        "utime": 0,
        "stime": 0,
        "memory_used": 0,
        "memory_buffers": 0,
        "memory_cached": 0,
        "memory_active_anon": 0,
        "memory_inactive_anon": 0,
        "disk_stats": {},
        "disk_spaces": {},
        "net_recv_bytes": 0,
        "net_sent_bytes": 0,
    }

    with suppress(FileNotFoundError):
        nvidia_process = Popen(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv"],
            stdout=PIPE,
        )

    with suppress(FileNotFoundError):
        with open("/proc/stat", "r") as f:
            for line in f:
                if line.startswith("cpu "):
                    cpu_stats = line.split()
                    # user + nice
                    stats["utime"] = int(cpu_stats[1]) + int(cpu_stats[2])
                    stats["stime"] = int(cpu_stats[3])
                elif line.startswith("processes"):
                    stats["processes"] = int(line.split()[1])

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
            stats["memory_used"] = (
                total
                - stats["memory_free"]
                - stats["memory_buffers"]
                - stats["memory_cached"]
            )
            stats["memory_active_anon"] = mem_info.get("Active(anon)", 0)
            stats["memory_inactive_anon"] = mem_info.get("Inactive(anon)", 0)
    with suppress(FileNotFoundError):
        with open("/proc/diskstats", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 14:
                    disk_name = parts[2]
                    if not is_partition(disk_name):
                        stats["disk_stats"][disk_name] = {
                            "read_sectors": int(parts[5]),
                            "write_sectors": int(parts[9]),
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
        with suppress(FileNotFoundError, OSError):
            zpool_process = Popen(
                ["zpool", "list", "-Hp", "-o", "name,size,allocated,free"],
                stdout=PIPE,
            )
            try:
                stdout, _ = zpool_process.communicate(timeout=0.25)
                if zpool_process.returncode == 0:
                    stats["zfs_pools"] = {}
                    for line in stdout.splitlines():
                        parts = line.decode().split("\t")
                        if len(parts) >= 4:
                            stats["disk_spaces"][f"zfs:{parts[0]}"] = {
                                "total": int(parts[1]),
                                "used": int(parts[2]),
                                "free": int(parts[3]),
                            }
            except TimeoutExpired:
                zpool_process.kill()
            except Exception:
                pass

    stats["gpu_usage"] = 0  # between 0 and GPU count
    stats["gpu_vram"] = 0  # MiB
    stats["gpu_utilized"] = 0  # number of GPUs with utilization > 0
    try:
        stdout, _ = nvidia_process.communicate(timeout=0.5)
        if nvidia_process.returncode == 0:
            for index, line in enumerate(stdout.splitlines()):
                if index == 0:
                    continue  # skip the header
                parts = line.decode().split(", ")
                if len(parts) == 2:
                    usage = float(parts[0].rstrip(" %"))
                    stats["gpu_usage"] += usage / 100
                    stats["gpu_vram"] += float(parts[1].rstrip(" MiB"))
                    stats["gpu_utilized"] += usage > 0
    except TimeoutExpired:
        nvidia_process.kill()
    except Exception:
        pass

    return stats


class PidTracker:
    """Track resource usage of a process and optionally its children.

    This class monitors system resources like CPU times and usage, memory usage,
    GPU and VRAM utilization, I/O operations for a given process ID and
    optionally its child processes.

    Data is collected every `interval` seconds and written to the stdout or
    `output_file` (if provided) as CSV. Currently, the following columns are
    tracked:

    - timestamp (float): The current timestamp.
    - pid (int): The monitored process ID.
    - children (int | None): The current number of child processes.
    - utime (int): The total user+nice mode CPU time in clock ticks.
    - stime (int): The total system mode CPU time in clock ticks.
    - cpu_usage (float): The current CPU usage between 0 and number of CPUs.
    - pss (int): The current PSS (Proportional Set Size) in kB.
    - read_bytes (int): The total number of bytes read from disk.
    - write_bytes (int): The total number of bytes written to disk.
    - gpu_usage (float): The current GPU utilization between 0 and GPU count.
    - gpu_vram (float): The current GPU memory used in MiB.
    - gpu_utilized (int): The number of GPUs with utilization > 0.

    Args:
        pid (int, optional): Process ID to track. Defaults to current process ID.
        interval (float, optional): Sampling interval in seconds. Defaults to 1.
        children (bool, optional): Whether to track child processes. Defaults to True.
        autostart (bool, optional): Whether to start tracking immediately. Defaults to True.
        output_file (str, optional): File to write the output to. Defaults to None, print to stdout.
    """

    def __init__(
        self,
        pid: int = getpid(),
        interval: float = 1,
        children: bool = True,
        autostart: bool = True,
        output_file: str = None,
    ):
        self.pid = pid
        self.status = "running"
        self.interval = interval
        self.cycle = 0
        self.children = children
        self.start_time = time()
        self.stats = get_pid_stats(pid, children)
        if autostart:
            self.start_tracking(output_file)

    def __call__(self):
        """Dummy method to make this class callable."""
        pass

    def diff_stats(self):
        """Calculate stats since last call."""
        last_stats = self.stats
        self.stats = get_pid_stats(self.pid, self.children)
        self.cycle += 1

        return {
            "timestamp": self.stats["timestamp"],
            "pid": self.pid,
            "children": self.stats["children"],
            "utime": max(0, self.stats["utime"] - last_stats["utime"]),
            "stime": max(0, self.stats["stime"] - last_stats["stime"]),
            "cpu_usage": round(
                max(
                    0,
                    (
                        (self.stats["utime"] + self.stats["stime"])
                        - (last_stats["utime"] + last_stats["stime"])
                    )
                    / (self.stats["timestamp"] - last_stats["timestamp"])
                    / sysconf("SC_CLK_TCK"),
                ),
                4,
            ),
            "pss": self.stats["pss"],
            "read_bytes": max(0, self.stats["read_bytes"] - last_stats["read_bytes"]),
            "write_bytes": max(
                0, self.stats["write_bytes"] - last_stats["write_bytes"]
            ),
            "gpu_usage": self.stats["gpu_usage"],
            "gpu_vram": self.stats["gpu_vram"],
            "gpu_utilized": self.stats["gpu_utilized"],
        }

    def start_tracking(
        self, output_file: Optional[str] = None, print_header: bool = True
    ):
        """Start an infinite loop tracking resource usage of the process until it exits.

        A CSV line is written every `interval` seconds.

        Args:
            output_file: File to write the output to. Defaults to None, printing to stdout.
            print_header: Whether to print the header of the CSV. Defaults to True.
        """
        file_handle = open(output_file, "w") if output_file else stdout
        file_writer = csv_writer(file_handle, quoting=QUOTE_NONNUMERIC)
        try:
            while True:
                current_time = time()
                current_stats = self.diff_stats()
                if current_stats["pss"] == 0:
                    # the process has exited
                    self.status = "exited"
                    break
                if self.cycle == 1 and print_header:
                    file_writer.writerow(current_stats.keys())
                else:
                    file_writer.writerow(current_stats.values())
                if output_file:
                    file_handle.flush()
                sleep(max(0, self.interval - (time() - current_time)))
        finally:
            if output_file and not file_handle.closed:
                file_handle.close()


class SystemTracker:
    """Track system-wide resource usage.

    This class monitors system resources like CPU times and usage, memory usage,
    GPU and VRAM utilization, disk I/O, and network traffic for the entire system.

    Data is collected every `interval` seconds and written to the stdout or
    `output_file` (if provided) as CSV. Currently, the following columns are
    tracked:

    - timestamp (float): The current timestamp.
    - processes (int): The number of running processes.
    - utime (int): The total user+nice mode CPU time in clock ticks.
    - stime (int): The total system mode CPU time in clock ticks.
    - cpu_usage (float): The current CPU usage between 0 and number of CPUs.
    - memory_free (int): The amount of free memory in kB.
    - memory_used (int): The amount of used memory in kB.
    - memory_buffers (int): The amount of memory used for buffers in kB.
    - memory_cached (int): The amount of memory used for caching in kB.
    - memory_active_anon (int): The amount of memory used for anonymous pages in kB.
    - memory_inactive_anon (int): The amount of memory used for inactive anonymous pages in kB.
    - disk_read_bytes (int): The total number of bytes read from disk.
    - disk_write_bytes (int): The total number of bytes written to disk.
    - disk_space_total_gb (float): The total disk space in GB.
    - disk_space_used_gb (float): The used disk space in GB.
    - disk_space_free_gb (float): The free disk space in GB.
    - net_recv_bytes (int): The total number of bytes received over network.
    - net_sent_bytes (int): The total number of bytes sent over network.
    - gpu_usage (float): The current GPU utilization between 0 and GPU count.
    - gpu_vram (float): The current GPU memory used in MiB.
    - gpu_utilized (int): The number of GPUs with utilization > 0.

    Args:
        interval: Sampling interval in seconds. Defaults to 1.
        autostart: Whether to start tracking immediately. Defaults to True.
        output_file: File to write the output to. Defaults to None, print to stdout.
    """

    def __init__(
        self,
        interval: float = 1,
        autostart: bool = True,
        output_file: str = None,
    ):
        self.status = "running"
        self.interval = interval
        self.cycle = 0
        self.start_time = time()

        # get sector sizes for all disks
        self.sector_sizes = {}
        with suppress(FileNotFoundError):
            for disk_path in glob("/sys/block/*/"):
                disk_name = disk_path.split("/")[-2]
                if is_partition(disk_name):
                    continue
                try:
                    with open(f"{disk_path}queue/hw_sector_size", "r") as f:
                        self.sector_sizes[disk_name] = int(f.read().strip())
                except (FileNotFoundError, ValueError):
                    self.sector_sizes[disk_name] = 512

        self.stats = get_system_stats()
        if autostart:
            self.start_tracking(output_file)

    def __call__(self):
        """Dummy method to make this class callable."""
        pass

    def diff_stats(self):
        """Calculate stats since last call."""
        last_stats = self.stats
        self.stats = get_system_stats()
        self.cycle += 1

        time_diff = self.stats["timestamp"] - last_stats["timestamp"]

        # calculate total disk I/O in bytes using per-disk sector sizes
        total_read_bytes = 0
        total_write_bytes = 0
        for disk_name in set(self.stats["disk_stats"]) & set(last_stats["disk_stats"]):
            sector_size = self.sector_sizes.get(disk_name, 512)
            read_sectors = max(
                0,
                self.stats["disk_stats"][disk_name]["read_sectors"]
                - last_stats["disk_stats"][disk_name]["read_sectors"],
            )
            write_sectors = max(
                0,
                self.stats["disk_stats"][disk_name]["write_sectors"]
                - last_stats["disk_stats"][disk_name]["write_sectors"],
            )
            total_read_bytes += read_sectors * sector_size
            total_write_bytes += write_sectors * sector_size

        # Get disk usage information for reporting
        disk_space_total = 0
        disk_space_used = 0
        disk_space_free = 0
        for disk_space in self.stats["disk_spaces"].values():
            disk_space_total += disk_space["total"]
            disk_space_used += disk_space["used"]
            disk_space_free += disk_space["free"]

        return {
            "timestamp": self.stats["timestamp"],
            "processes": self.stats["processes"],
            "utime": max(0, self.stats["utime"] - last_stats["utime"]),
            "stime": max(0, self.stats["stime"] - last_stats["stime"]),
            "cpu_usage": round(
                max(
                    0,
                    (
                        (self.stats["utime"] + self.stats["stime"])
                        - (last_stats["utime"] + last_stats["stime"])
                    )
                    / time_diff
                    / sysconf("SC_CLK_TCK"),
                ),
                4,
            ),
            "memory_free": self.stats["memory_free"],
            "memory_used": self.stats["memory_used"],
            "memory_buffers": self.stats["memory_buffers"],
            "memory_cached": self.stats["memory_cached"],
            "memory_active_anon": self.stats["memory_active_anon"],
            "memory_inactive_anon": self.stats["memory_inactive_anon"],
            "disk_read_bytes": total_read_bytes,
            "disk_write_bytes": total_write_bytes,
            "disk_space_total_gb": round(disk_space_total / (1024**3), 2),
            "disk_space_used_gb": round(disk_space_used / (1024**3), 2),
            "disk_space_free_gb": round(disk_space_free / (1024**3), 2),
            "net_recv_bytes": max(
                0, self.stats["net_recv_bytes"] - last_stats["net_recv_bytes"]
            ),
            "net_sent_bytes": max(
                0, self.stats["net_sent_bytes"] - last_stats["net_sent_bytes"]
            ),
            "gpu_usage": self.stats["gpu_usage"],
            "gpu_vram": self.stats["gpu_vram"],
            "gpu_utilized": self.stats["gpu_utilized"],
        }

    def start_tracking(
        self, output_file: Optional[str] = None, print_header: bool = True
    ):
        """Start an infinite loop tracking system resource usage.

        A CSV line is written every `interval` seconds.

        Args:
            output_file: File to write the output to. Defaults to None, printing to stdout.
            print_header: Whether to print the header of the CSV. Defaults to True.
        """
        file_handle = open(output_file, "w") if output_file else stdout
        file_writer = csv_writer(file_handle, quoting=QUOTE_NONNUMERIC)
        try:
            while True:
                current_time = time()
                current_stats = self.diff_stats()
                if self.cycle == 1 and print_header:
                    file_writer.writerow(current_stats.keys())
                else:
                    file_writer.writerow(current_stats.values())
                if output_file:
                    file_handle.flush()
                sleep(max(0, self.interval - (time() - current_time)))
        finally:
            if output_file and not file_handle.closed:
                file_handle.close()
