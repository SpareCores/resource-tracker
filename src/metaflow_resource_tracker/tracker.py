from os import getpid
from resource import RUSAGE_SELF, getrusage
from time import sleep, time


class Tracker:
    def __init__(self, pid: int = getpid(), interval: float = 1):
        self.pid = pid
        self.interval = interval
        self.start_time = time()
        self.start_resources = getrusage(RUSAGE_SELF)
        self._start_tracking()

    @staticmethod
    def _get_vm_rss(pid):
        """Get the current resident set size of a process.

        Returns:
            int: The current resident set size of the process in kB.
        """
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS"):
                    return int(line.split()[1])
        return None

    @staticmethod
    def _get_pid_stat(pid):
        """Get the current stats of a process from /proc/<pid>/stat.

        Returns:
            list[str | int]: Values read from /proc/<pid>/stat.
        """
        with open(f"/proc/{pid}/stat", "r") as f:
            return f.read().split()

    @staticmethod
    def _get_pid_io(pid):
        """Get the current I/O stats of a process from /proc/<pid>/io.

        Returns:
            dict[str, int]: Values read from /proc/<pid>/io.
        """
        with open(f"/proc/{pid}/io", "r") as f:
            return {
                parts[0]: int(parts[1]) for line in f if (parts := line.split(": "))
            }

    def _print_pid_stats_csv(self, pid):
        """Print the current stats of a process as a CSV row."""
        current_usage = getrusage(RUSAGE_SELF)
        current_io = self._get_pid_io(pid)
        current_time = time()
        current_data = [
            current_time,
            pid,
            current_usage.ru_utime,
            current_usage.ru_stime,
            # TODO record number of threads?
            self._get_vm_rss(pid),
            current_usage.ru_maxrss,
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
