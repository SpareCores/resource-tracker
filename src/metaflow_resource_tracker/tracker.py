from contextlib import suppress
from os import getpid
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
        return None


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

    Args:
        pid (int): Process ID to track.
        children (bool, optional): Whether to include resources used by child processes.
            Defaults to True.

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
        - read_bytes (int): The total number of bytes read in kB.
        - write_bytes (int): The total number of bytes written in kB.
    """
    current_time = time()
    current_children = get_pid_children(pid)
    current_pss = get_pid_pss_rollup(pid)
    if children:
        for child in current_children:
            current_pss += get_pid_pss_rollup(child)
    current_proc_times = get_pid_proc_times(pid, children)
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
        "read_bytes": current_io["read_bytes"] / 1024,
        "write_bytes": current_io["write_bytes"] / 1024,
    }


class Tracker:
    """Track resource usage of a process and optionally its children.

    This class monitors system resources like CPU time, memory usage, and I/O operations
    for a given process ID and optionally its child processes.

    Args:
        pid (int, optional): Process ID to track. Defaults to current process ID.
        interval (float, optional): Sampling interval in seconds. Defaults to 1.
        children (bool, optional): Whether to track child processes. Defaults to False.
    """

    def __init__(
        self, pid: int = getpid(), interval: float = 1, children: bool = False
    ):
        self.pid = pid
        self.interval = interval
        self.children = children
        self.start_time = time()
        # self._start_tracking()

    def _print_pid_stats_csv(self, pid):
        """Print the current stats of a process as a CSV row."""
        current_time = time()
        current_children = get_pid_children(pid)
        current_pss_rollup = get_pid_pss_rollup(pid)
        if self.children:
            for child in current_children:
                current_pss_rollup += get_pid_pss_rollup(child)
        current_proc_times = get_pid_proc_times(pid, self.children)
        current_io = get_pid_proc_io(pid)
        if self.children:
            for child in current_children:
                child_io = get_pid_proc_io(child)
                for key in current_io:
                    current_io[key] += child_io[key]
        current_data = [
            current_time,
            pid,
            len(current_children) if self.children else None,
            current_proc_times.utime,
            current_proc_times.stime,
            current_pss_rollup,
            current_io["read_bytes"],
            current_io["write_bytes"],
        ]
        print(",".join(map(str, current_data)))

    def start_tracking(self):
        """Start an infinite loop tracking resource usage."""
        # TODO print CSV header
        # NOTE if pid is missing, that's system-wide info
        # TODO add system-wide info, including network traffic
        # TODO update to run this on all subprocesses
        while True:
            self._print_pid_stats_csv(self.pid)
            sleep(self.interval)
