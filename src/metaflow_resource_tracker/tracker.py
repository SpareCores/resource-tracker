from contextlib import suppress
from os import getpid, sysconf
from time import sleep, time


def get_pid_children(pid):
    """Get all descendant processes recursively.

    Returns:
        set[int]: All descendant process ids.
    """
    try:
        with open(f"/proc/{pid}/task/{pid}/children", "r") as f:
            children = {int(child) for child in f.read().strip().split()}
            descendants = set()
            for child in children:
                descendants.update(get_pid_children(child))
            return children | descendants
    except FileNotFoundError:
        return set()


def get_pid_rss(pid):
    """Get the current resident set size of a process.

    Returns:
        int: The current resident set size of the process in kB.
    """
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS"):
                    return int(line.split()[1])
    except FileNotFoundError:
        return 0


def get_pid_pss_rollup(pid):
    """Reads the total PSS from /proc/[pid]/smaps_rollup.

    Returns:
        int: The total PSS in kB.
    """
    with suppress(FileNotFoundError):
        with open(f"/proc/{pid}/smaps_rollup", "r") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    return 0


def get_pid_proc_times(pid: int, children: bool = True):
    """Get the current user and system times of a process from /proc/<pid>/stat.

    Note that cannot use cutime/cstime for real-time monitoring, as they need to
    wait for the children to exit.

    Args:
        pid (int): Process ID to track
        children (bool, optional): Whether to include stats from exited child processes. Defaults to True.

    Returns:
        dict[str, int]: A dictionary containing process time information:
            - utime (int): User mode CPU time in clock ticks
            - stime (int): System mode CPU time in clock ticks
    """
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            values = f.read().split()
            # https://docs.kernel.org/filesystems/proc.html
            return {
                "utime": int(values[13]) + (int(values[15]) if children else 0),
                "stime": int(values[14]) + (int(values[16]) if children else 0),
            }
    except FileNotFoundError:
        return {"utime": 0, "stime": 0}


def get_pid_proc_io(pid):
    """Get the total bytes read and written by a process from /proc/<pid>/io.

    Note that it is not tracking reading from memory-mapped objects.

    Returns:
        dict[str, int]: A dictionary containing the total bytes read and written by the process.
    """
    try:
        with open(f"/proc/{pid}/io", "r") as f:
            return {
                parts[0]: int(parts[1]) for line in f if (parts := line.split(": "))
            }
    except FileNotFoundError:
        return {"read_bytes": 0, "write_bytes": 0}


def get_pid_stats(pid, children: bool = True):
    """Collect current/cumulative stats of a process from procfs.

    Args:
        pid (int): The process ID to track.
        children (bool, optional): Whether to include child processes. Defaults to True.

    Returns:
        dict[str, int | float | None]: A dictionary containing process stats.
        - timestamp (float): The current timestamp.
        - pid (int): The process ID.
        - children (int | None): The current number of child processes.
        - utime (int): The total user mode CPU time in clock ticks.
        - stime (int): The total system mode CPU time in clock ticks.
        - pss_rollup (int): The current PSS (Proportional Set Size) in kB.
        - read_bytes (int): The total number of bytes read.
        - write_bytes (int): The total number of bytes written.
    """
    current_time = time()
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
    return {
        "timestamp": current_time,
        "pid": pid,
        "children": len(current_children) if children else None,
        "utime": current_proc_times["utime"],
        "stime": current_proc_times["stime"],
        "pss": current_pss,
        "read_bytes": current_io["read_bytes"],
        "write_bytes": current_io["write_bytes"],
    }


# TODO add system-wide info, including network traffic


class PidTracker:
    """Track resource usage of a process and optionally its children.

    This class monitors system resources like CPU time, memory usage, and I/O operations
    for a given process ID and optionally its child processes.

    Args:
        pid (int, optional): Process ID to track. Defaults to current process ID.
        interval (float, optional): Sampling interval in seconds. Defaults to 1.
        children (bool, optional): Whether to track child processes. Defaults to True.
    """

    def __init__(self, pid: int = getpid(), interval: float = 1, children: bool = True):
        self.pid = pid
        self.status = "running"
        self.interval = interval
        self.cycle = 0
        self.children = children
        self.start_time = time()
        self.stats = get_pid_stats(pid, children)
        self.start_tracking()

    def diff_stats(self):
        """Calculate stats since last call."""
        last_stats = self.stats
        self.stats = get_pid_stats(self.pid, self.children)
        self.cycle += 1

        return {
            "timestamp": self.stats["timestamp"],
            "cycle": self.cycle,
            "duration": round(self.stats["timestamp"] - last_stats["timestamp"], 3),
            "pid": self.pid,
            "children": self.stats["children"],
            "utime": max(0, self.stats["utime"] - last_stats["utime"]),
            "stime": max(0, self.stats["stime"] - last_stats["stime"]),
            "cpu_usage": round(
                max(
                    0,
                    (
                        (
                            (self.stats["utime"] + self.stats["stime"])
                            - (last_stats["utime"] + last_stats["stime"])
                        )
                        / (self.stats["timestamp"] - last_stats["timestamp"])
                        / sysconf("SC_CLK_TCK")
                    ),
                ),
                4,
            ),
            "pss": self.stats["pss"],
            "read_bytes": max(0, self.stats["read_bytes"] - last_stats["read_bytes"]),
            "write_bytes": max(
                0, self.stats["write_bytes"] - last_stats["write_bytes"]
            ),
        }

    def start_tracking(self, print_header: bool = True):
        """Start an infinite loop tracking resource usage of the process until it exits."""
        while True:
            current_time = time()
            current_stats = self.diff_stats()
            if current_stats["pss"] == 0:
                # the process has exited
                self.status = "exited"
                break
            if self.cycle == 1 and print_header:
                print(",".join(current_stats.keys()))
            else:
                print(",".join(str(v) for v in current_stats.values()))
            sleep(max(0, self.interval - (time() - current_time)))
