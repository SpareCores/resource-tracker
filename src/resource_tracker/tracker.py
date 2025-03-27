"""
Track resource usage of a process or server.
"""

from contextlib import suppress
from csv import QUOTE_NONNUMERIC
from csv import writer as csv_writer
from logging import getLogger
from multiprocessing import SimpleQueue, get_context
from os import getpid, unlink
from signal import SIGINT, SIGTERM, signal
from sys import platform, stdout
from tempfile import NamedTemporaryFile
from time import sleep, time
from typing import Optional
from weakref import finalize

from .helpers import get_tracker_implementation
from .tiny_data_frame import TinyDataFrame

logger = getLogger(__name__)


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
    - utime (int): The total user+nice mode CPU time in seconds.
    - stime (int): The total system mode CPU time in seconds.
    - cpu_usage (float): The current CPU usage between 0 and number of CPUs.
    - memory (int): The current memory usage in kB. Implementation depends on the
      operating system, and it is preferably PSS (Proportional Set Size) on Linux,
      USS (Unique Set Size) on macOS and Windows, and RSS (Resident Set Size) on
      Windows.
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
        self.get_pid_stats, _ = get_tracker_implementation()

        self.pid = pid
        self.status = "running"
        self.interval = interval
        self.cycle = 0
        self.children = children
        self.start_time = time()
        self.stats = self.get_pid_stats(pid, children)
        if autostart:
            self.start_tracking(output_file)

    def __call__(self):
        """Dummy method to make this class callable."""
        pass

    def diff_stats(self):
        """Calculate stats since last call."""
        last_stats = self.stats
        self.stats = self.get_pid_stats(self.pid, self.children)
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
                    / (self.stats["timestamp"] - last_stats["timestamp"]),
                ),
                4,
            ),
            "memory": self.stats["memory"],
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
                if current_stats["memory"] == 0:
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
    - utime (int): The total user+nice mode CPU time in seconds.
    - stime (int): The total system mode CPU time in seconds.
    - cpu_usage (float): The current CPU usage between 0 and number of CPUs.
    - memory_free (int): The amount of free memory in kB.
    - memory_used (int): The amount of used memory in kB.
    - memory_buffers (int): The amount of memory used for buffers in kB.
    - memory_cached (int): The amount of memory used for caching in kB.
    - memory_active (int): The amount of memory used for active pages in kB.
    - memory_inactive (int): The amount of memory used for inactive pages in kB.
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
        _, self.get_system_stats = get_tracker_implementation()

        self.status = "running"
        self.interval = interval
        self.cycle = 0
        self.start_time = time()

        self.stats = self.get_system_stats()
        if autostart:
            self.start_tracking(output_file)

    def __call__(self):
        """Dummy method to make this class callable."""
        pass

    def diff_stats(self):
        """Calculate stats since last call."""
        last_stats = self.stats
        self.stats = self.get_system_stats()
        self.cycle += 1

        time_diff = self.stats["timestamp"] - last_stats["timestamp"]

        total_read_bytes = 0
        total_write_bytes = 0
        for disk_name in set(self.stats["disk_stats"]) & set(last_stats["disk_stats"]):
            read_bytes = max(
                0,
                self.stats["disk_stats"][disk_name]["read_bytes"]
                - last_stats["disk_stats"][disk_name]["read_bytes"],
            )
            write_bytes = max(
                0,
                self.stats["disk_stats"][disk_name]["write_bytes"]
                - last_stats["disk_stats"][disk_name]["write_bytes"],
            )
            total_read_bytes += read_bytes
            total_write_bytes += write_bytes

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
                    / time_diff,
                ),
                4,
            ),
            "memory_free": self.stats["memory_free"],
            "memory_used": self.stats["memory_used"],
            "memory_buffers": self.stats["memory_buffers"],
            "memory_cached": self.stats["memory_cached"],
            "memory_active": self.stats["memory_active"],
            "memory_inactive": self.stats["memory_inactive"],
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


def _run_tracker(tracker_type, error_queue, **kwargs):
    """Run either PidTracker or SystemTracker with dynamic import resolution and error handling.

    This functions is standalone so that it can be pickled by multiprocessing,
    and tries to clean up resources before exiting.
    """
    from importlib import import_module

    def signal_handler(signum, frame):
        exit(0)

    signal(SIGTERM, signal_handler)
    signal(SIGINT, signal_handler)

    def resolve_class(tracker_type):
        # the trackers might be coming from the resource-tracker package,
        # or a module of the Metaflow decorator, or a flat module structure
        candidates = [
            f"{__package__}.resource_tracker",
            ".resource_tracker",
            "resource_tracker",
        ]
        class_names = {
            "pid": "PidTracker",
            "system": "SystemTracker",
        }

        for module_path in candidates:
            try:
                module = import_module(module_path, package=__package__)
                cls = getattr(module, class_names[tracker_type])
                return cls
            except (ImportError, AttributeError, KeyError):
                continue
        raise ImportError(
            f"Could not find {class_names[tracker_type]} in any of: {candidates}"
        )

    try:
        tracker_cls = resolve_class(tracker_type)
        if not callable(tracker_cls):
            raise TypeError(f"{tracker_type} is not callable")
        return tracker_cls(**kwargs)
    except Exception:
        import traceback
        from sys import exc_info, exit

        exc_info = exc_info()
        error_queue.put(
            {
                "name": exc_info[0].__name__,
                "module": exc_info[0].__module__,
                "message": str(exc_info[1]),
                "traceback": traceback.format_exception(*exc_info),
            }
        )
        exit(1)


def _cleanup_temp_files(files):
    for f in files:
        with suppress(Exception):
            unlink(f)


class ResourceTracker:
    """Track resource usage of processes and the system in a non-blocking way.

    Start a `PidTracker` and a `SystemTracker` in background processes, and
    make the collected data available easily in the main process via the
    `pid_tracker` and `system_tracker` properties.

    Args:
        pid: Process ID to track. Defaults to current process ID.
        children: Whether to track child processes. Defaults to True.
        interval: Sampling interval in seconds. Defaults to 1.
        method: Multiprocessing method. Defaults to None, which tries to fork on
            Linux and macOS, and spawn on Windows.
        autostart: Whether to start tracking immediately. Defaults to True.
    """

    def __init__(
        self,
        pid: int = getpid(),
        children: bool = True,
        interval: float = 1,
        method: Optional[str] = None,
        autostart: bool = True,
    ):
        self.pid = pid
        self.children = children
        self.interval = interval
        self.method = method
        self.autostart = autostart

        if method is None:
            # try to fork when possible due to leaked semaphores on older Python versions
            # see e.g. https://github.com/python/cpython/issues/90549
            if platform in ["linux", "darwin"]:
                self.mpc = get_context("fork")
            else:
                self.mpc = get_context("spawn")
        else:
            self.mpc = get_context(method)

        # error details from subprocesses
        self.error_queue = SimpleQueue()

        # create temporary CSV files for both trackers,
        # and pass only the filepath to the subprocess to avoid pickling the file objects
        for tracker_name in ["pid_tracker", "system_tracker"]:
            temp_file = NamedTemporaryFile(delete=False)
            setattr(self, f"{tracker_name}_filepath", temp_file.name)
            temp_file.close()
        # make sure to cleanup the temp files
        finalize(
            self,
            _cleanup_temp_files,
            [self.pid_tracker_filepath, self.system_tracker_filepath],
        )

        if autostart:
            self.start()

    def start(self):
        self.start_time = time()
        self.pid_tracker_process = self.mpc.Process(
            target=_run_tracker,
            args=("pid", self.error_queue),
            kwargs={
                "pid": self.pid,
                "interval": self.interval,
                "children": self.children,
                "output_file": self.pid_tracker_filepath,
            },
            daemon=True,
        )
        self.pid_tracker_process.start()

        self.system_tracker_process = self.mpc.Process(
            target=_run_tracker,
            args=("system", self.error_queue),
            kwargs={
                "interval": self.interval,
                "output_file": self.system_tracker_filepath,
            },
            daemon=True,
        )
        self.system_tracker_process.start()

    def stop(self):
        self.stop_time = time()
        # check for errors in the subprocesses
        if not self.error_queue.empty():
            error_data = self.error_queue.get()
            logger.warning(
                "Resource tracker subprocess failed!\n"
                f"Error type: {error_data['name']} (from module {error_data['module']})\n"
                f"Error message: {error_data['message']}\n"
                f"Original traceback:\n{error_data['traceback']}"
            )
        # terminate tracker processes
        for tracker_name in ["pid_tracker", "system_tracker"]:
            process_attr = f"{tracker_name}_process"
            if hasattr(self, process_attr):
                process = getattr(self, process_attr)
                if process.is_alive():
                    with suppress(Exception):
                        process.terminate()
                        process.join(timeout=1.0)
                        if process.is_alive():
                            process.kill()
                            process.join(timeout=1.0)
                    process.close()
        self.error_queue.close()
        logger.debug(
            "Resource tracker stopped after %s seconds, logging %s records",
            self.stop_time - self.start_time,
            len(self.pid_tracker),
        )

    @property
    def pid_tracker(self):
        """Get the collected data from the `PidTracker`."""
        return TinyDataFrame(
            csv_file_path=self.pid_tracker_filepath,
        )

    @property
    def system_tracker(self):
        """Get the collected data from the `SystemTracker`."""
        return TinyDataFrame(
            csv_file_path=self.system_tracker_filepath,
        )
