"""
Track resource usage of a process and/or the system.

To start tracker(s) in the background as spawned or forked process(es), use the
[resource_tracker.ResourceTracker][] class. Starting this will not block the
main process and will allow you to access the collected data via the
`process_metrics` and `system_metrics` properties of the instance in real-time, or
after stopping the resource tracker(s).

For more custom use cases, you can also use the [resource_tracker.ProcessTracker][]
and [resource_tracker.SystemTracker][] classes directly logging either to the
standard output or a file, and handle putting those into a background
thread/process yourself.
"""

from csv import QUOTE_NONNUMERIC
from csv import writer as csv_writer
from logging import getLogger
from math import ceil
from multiprocessing import SimpleQueue, get_context
from os import getpid
from signal import SIGINT, SIGTERM, signal
from sys import platform, stdout
from tempfile import NamedTemporaryFile
from threading import Thread
from time import sleep, time
from typing import List, Optional, Union
from warnings import warn
from weakref import finalize

from .cloud_info import get_cloud_info
from .column_maps import BYTE_MAPPING, HUMAN_NAMES_MAPPING
from .helpers import cleanup_files, cleanup_processes, get_tracker_implementation
from .server_info import get_server_info
from .tiny_data_frame import TinyDataFrame

logger = getLogger(__name__)


class ProcessTracker:
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
        start_time: Time when to start tracking. Defaults to current time.
        interval (float, optional): Sampling interval in seconds. Defaults to 1.
        children (bool, optional): Whether to track child processes. Defaults to True.
        autostart (bool, optional): Whether to start tracking immediately. Defaults to True.
        output_file (str, optional): File to write the output to. Defaults to None, print to stdout.
    """

    def __init__(
        self,
        pid: int = getpid(),
        start_time: float = time(),
        interval: float = 1,
        children: bool = True,
        autostart: bool = True,
        output_file: str = None,
    ):
        self.get_process_stats, _ = get_tracker_implementation()

        self.pid = pid
        self.status = "running"
        self.interval = interval
        self.cycle = 0
        self.children = children
        self.start_time = start_time

        # dummy data collection so that diffing on the first time does not fail
        self.stats = self.get_process_stats(pid, children)

        if autostart:
            # wait for the start time to be reached
            if start_time > time():
                sleep(start_time - time())
            # we can now start. 1st interval used to collect baseline
            self.start_tracking(output_file)

    def __call__(self):
        """Dummy method to make this class callable."""
        pass

    def diff_stats(self):
        """Calculate stats since last call."""
        last_stats = self.stats
        self.stats = self.get_process_stats(self.pid, self.children)
        self.cycle += 1

        return {
            "timestamp": round(self.stats["timestamp"], 3),
            "pid": self.pid,
            "children": self.stats["children"],
            "utime": max(0, round(self.stats["utime"] - last_stats["utime"], 6)),
            "stime": max(0, round(self.stats["stime"] - last_stats["stime"], 6)),
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
                # don't print values yet, we collect data for the 1st baseline
                if self.cycle == 1:
                    if print_header:
                        file_writer.writerow(current_stats.keys())
                else:
                    file_writer.writerow(current_stats.values())
                if output_file:
                    file_handle.flush()
                # sleep until the next interval
                sleep(max(0, self.start_time + self.interval * self.cycle - time()))
        finally:
            if output_file and not file_handle.closed:
                file_handle.close()


class PidTracker(ProcessTracker):
    """Old name for [resource_tracker.ProcessTracker][].

    This class is deprecated and will be removed in the future.
    """

    def __init__(self, *args, **kwargs):
        warn(
            "PidTracker is deprecated and will be removed in a future release. "
            "Please use ProcessTracker instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)


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
        start_time: Time when to start tracking. Defaults to current time.
        interval: Sampling interval in seconds. Defaults to 1.
        autostart: Whether to start tracking immediately. Defaults to True.
        output_file: File to write the output to. Defaults to None, print to stdout.
    """

    def __init__(
        self,
        start_time: float = time(),
        interval: float = 1,
        autostart: bool = True,
        output_file: str = None,
    ):
        _, self.get_system_stats = get_tracker_implementation()

        self.status = "running"
        self.interval = interval
        self.cycle = 0
        self.start_time = start_time

        # dummy data collection so that diffing on the first time does not fail
        self.stats = self.get_system_stats()

        if autostart:
            # wait for the start time to be reached
            if start_time > time():
                sleep(start_time - time())
            # we can now start. 1st interval used to collect baseline
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
            "timestamp": round(self.stats["timestamp"], 3),
            "processes": self.stats["processes"],
            "utime": max(0, round(self.stats["utime"] - last_stats["utime"], 6)),
            "stime": max(0, round(self.stats["stime"] - last_stats["stime"], 6)),
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
                # don't print values yet, we collect data for the 1st baseline
                if self.cycle == 1:
                    if print_header:
                        file_writer.writerow(current_stats.keys())
                else:
                    file_writer.writerow(current_stats.values())
                if output_file:
                    file_handle.flush()
                # sleep until the next interval
                sleep(max(0, self.start_time + self.interval * self.cycle - time()))
        finally:
            if output_file and not file_handle.closed:
                file_handle.close()


def _run_tracker(tracker_type, error_queue, **kwargs):
    """Run either ProcessTracker or SystemTracker with dynamic import resolution and error handling.

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
            "resource_tracker",
            "resource_tracker.tracker",
            f"{__package__}.tracker",
            f"{__package__}",
            f"{__package__}.resource_tracker",
            ".resource_tracker",
            ".resource_tracker.tracker",
        ]
        class_names = {
            "process": "ProcessTracker",
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


class ResourceTracker:
    """Track resource usage of processes and the system in a non-blocking way.

    Start a [resource_tracker.ProcessTracker][] and/or a [resource_tracker.SystemTracker][] in the background as spawned
    or forked process(es), and make the collected data available easily in the
    main process via the `process_metrics` and `system_metrics` properties.

    Args:
        pid: Process ID to track. Defaults to current process ID.
        children: Whether to track child processes. Defaults to True.
        interval: Sampling interval in seconds. Defaults to 1.
        method: Multiprocessing method. Defaults to None, which tries to fork on
            Linux and macOS, and spawn on Windows.
        autostart: Whether to start tracking immediately. Defaults to True.
        track_processes: Whether to track resource usage at the process level.
            Defaults to True.
        track_system: Whether to track system-wide resource usage. Defaults to True.
        discover_server: Whether to discover the server specs in the background at
            startup. Defaults to True.
        discover_cloud: Whether to discover the cloud environment in the background
            at startup. Defaults to True.
    """

    server_info: Optional[dict] = None
    """Collected data from [resource_tracker.get_server_info][]."""
    cloud_info: Optional[dict] = None
    """Collected data from [resource_tracker.get_cloud_info][]."""

    def __init__(
        self,
        pid: int = getpid(),
        children: bool = True,
        interval: float = 1,
        method: Optional[str] = None,
        autostart: bool = True,
        track_processes: bool = True,
        track_system: bool = True,
        discover_server: bool = True,
        discover_cloud: bool = True,
    ):
        self.pid = pid
        self.children = children
        self.interval = interval
        self.method = method
        self.autostart = autostart
        self.trackers = []
        if track_processes:
            self.trackers.append("process_tracker")
        if track_system:
            self.trackers.append("system_tracker")
        self.discover_server = discover_server
        self.discover_cloud = discover_cloud

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

        # create temporary CSV file(s) for the tracker(s), and record only the file path(s)
        # to be passed later to subprocess(es) avoiding pickling the file object(s)
        for tracker_name in self.trackers:
            temp_file = NamedTemporaryFile(delete=False)
            setattr(self, f"{tracker_name}_filepath", temp_file.name)
            temp_file.close()
        # make sure to cleanup the temp file(s)
        finalize(
            self,
            cleanup_files,
            [
                getattr(self, f"{tracker_name}_filepath")
                for tracker_name in self.trackers
            ],
        )

        if autostart:
            self.start()

    def start(self):
        """Start the selected resource trackers in the background as subprocess(es)."""
        self.start_time = time()
        # round to the nearest interval in the future
        self.start_time = ceil(self.start_time / self.interval) * self.interval
        # leave at least 50 ms for trackers to start
        if self.start_time - time() < 0.05:
            self.start_time += self.interval

        if "process_tracker" in self.trackers:
            self.process_tracker_process = self.mpc.Process(
                target=_run_tracker,
                args=("process", self.error_queue),
                kwargs={
                    "pid": self.pid,
                    "start_time": self.start_time,
                    "interval": self.interval,
                    "children": self.children,
                    "output_file": self.process_tracker_filepath,
                },
                daemon=True,
            )
            self.process_tracker_process.start()

        if "system_tracker" in self.trackers:
            self.system_tracker_process = self.mpc.Process(
                target=_run_tracker,
                args=("system", self.error_queue),
                kwargs={
                    "start_time": self.start_time,
                    "interval": self.interval,
                    "output_file": self.system_tracker_filepath,
                },
                daemon=True,
            )
            self.system_tracker_process.start()

        def collect_server_info():
            """Collect server info to be run in a background thread."""
            try:
                self.server_info = get_server_info()
            except Exception as e:
                logger.warning(f"Error fetching server info: {e}")

        def collect_cloud_info():
            """Collect cloud info to be run in a background thread."""
            try:
                self.cloud_info = get_cloud_info()
            except Exception as e:
                logger.warning(f"Error fetching cloud info: {e}")

        if self.discover_server:
            server_thread = Thread(target=collect_server_info, daemon=True)
            server_thread.start()
        if self.discover_cloud:
            cloud_thread = Thread(target=collect_cloud_info, daemon=True)
            cloud_thread.start()

        # make sure to cleanup the started subprocess(es)
        finalize(
            self,
            cleanup_processes,
            [
                getattr(self, f"{tracker_name}_process")
                for tracker_name in self.trackers
            ],
        )

    def stop(self):
        """Stop the previously started resource trackers' background processes."""
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
        for tracker_name in self.trackers:
            process_attr = f"{tracker_name}_process"
            if hasattr(self, process_attr):
                cleanup_processes([getattr(self, process_attr)])
        self.error_queue.close()
        logger.debug(
            "Resource tracker stopped after %s seconds, logging %d process-level and %d system-wide records",
            self.stop_time - self.start_time,
            len(self.process_metrics),
            len(self.system_metrics),
        )

    @property
    def process_metrics(self) -> Union[TinyDataFrame, List]:
        """Collected data from [resource_tracker.ProcessTracker][].

        Returns:
            A [resource_tracker.TinyDataFrame][] object containing the collected data or an empty list if the [resource_tracker.ProcessTracker][] is not running.
        """
        try:
            return TinyDataFrame(
                csv_file_path=self.process_tracker_filepath,
            )
        except Exception:
            return []

    @property
    def system_metrics(self) -> Union[TinyDataFrame, List]:
        """Collected data from [resource_tracker.SystemTracker][].

        Returns:
            A [resource_tracker.TinyDataFrame][] object containing the collected data or an empty list if the [resource_tracker.SystemTracker][] is not running.
        """
        try:
            return TinyDataFrame(
                csv_file_path=self.system_tracker_filepath,
            )
        except Exception:
            return []

    def get_combined_metrics(
        self,
        bytes: bool = False,
        human_names: bool = False,
        system_prefix: Optional[str] = None,
        process_prefix: Optional[str] = None,
    ) -> Union[TinyDataFrame, List]:
        """Collected data both from the [resource_tracker.ProcessTracker][] and [resource_tracker.SystemTracker][].

        This is effectively binding the two dataframes together by timestamp,
        and adding a prefix to the column names to distinguish between the system and process metrics.

        Args:
            bytes: Whether to convert all metrics (e.g. memory, VRAM, disk usage) to bytes. Defaults to False, reporting as documented at [resource_tracker.ProcessTracker][] and [resource_tracker.SystemTracker][] (kB, MiB, or GiB).
            human_names: Whether to rename the columns to use human-friendly names. Defaults to False, reporting as documented at [resource_tracker.ProcessTracker][] and [resource_tracker.SystemTracker][] with prefixes.
            system_prefix: Prefix to add to the system-level column names. Defaults to "system_" or "System " based on the value of `human_names`.
            process_prefix: Prefix to add to the process-level column names. Defaults to "process_" or "Process " based on the value of `human_names`.

        Returns:
            A [resource_tracker.TinyDataFrame][] object containing the combined data or an empty list if tracker(s) not running.
        """
        try:
            process_metrics = self.process_metrics
            system_metrics = self.system_metrics

            # ensure both have the same length
            if len(process_metrics) > len(system_metrics):
                process_metrics = process_metrics[: len(system_metrics)]
            elif len(system_metrics) > len(process_metrics):
                system_metrics = system_metrics[: len(process_metrics)]

            # nothing to report on
            if len(process_metrics) == 0:
                return []

            if bytes:
                for col, factor in BYTE_MAPPING.items():
                    for metrics in (system_metrics, process_metrics):
                        if col in metrics.columns:
                            metrics[col] = [v * factor for v in metrics[col]]

            if system_prefix is None:
                system_prefix = "system_" if not human_names else "System "
            if process_prefix is None:
                process_prefix = "process_" if not human_names else "Process "

            # cbind the two dataframes with column name prefixes and optional human-friendly names
            combined = system_metrics.rename(
                columns={
                    n: (
                        (system_prefix if n != "timestamp" else "")
                        + (n if not human_names else HUMAN_NAMES_MAPPING.get(n, n))
                    )
                    for n in system_metrics.columns
                }
            )
            for col in process_metrics.columns[1:]:
                combined[
                    process_prefix
                    + (col if not human_names else HUMAN_NAMES_MAPPING.get(col, col))
                ] = process_metrics[col]

            return combined
        except Exception as e:
            logger.error(f"Error getting combined metrics: {e}")
            return []
