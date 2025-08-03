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
from gzip import open as gzip_open
from json import dumps as json_dumps
from json import loads as json_loads
from logging import getLogger
from math import ceil
from multiprocessing import SimpleQueue, get_context
from os import getpid, path
from signal import SIGINT, SIGTERM, signal
from statistics import mean
from sys import platform, stdout
from tempfile import NamedTemporaryFile
from threading import Thread
from time import sleep, time
from typing import List, Literal, Optional
from warnings import warn
from weakref import finalize

from ._version import __version__
from .cloud_info import get_cloud_info
from .column_maps import (
    BYTE_MAPPING,
    HUMAN_NAMES_MAPPING,
    REPORT_CSV_MAPPING,
    SERVER_ALLOCATION_CHECKS,
)
from .helpers import (
    aggregate_stats,
    cleanup_files,
    cleanup_processes,
    get_tracker_implementation,
    is_psutil_available,
)
from .keeper import get_instance_price, get_recommended_cloud_servers
from .report import Report, _read_report_template_files, round_memory
from .server_info import get_server_info
from .tiny_bars import render_template
from .tiny_data_frame import StatSpec, TinyDataFrame

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

        # initial data collection so that we can use that as a baseline when diffing after the first interval
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

    Example:

        >>> from resource_tracker.dummy_workloads import cpu_single, cpu_multi
        >>> tracker = ResourceTracker()
        >>> cpu_single()
        >>> tracker.recommend_resources()
        {'cpu': 1, 'memory': 128, 'gpu': 0, 'vram': 0}
        >>> tracker = ResourceTracker()
        >>> while tracker.n_samples == 0:
        ...     cpu_multi(duration=0.5, ncores=2)
        >>> tracker.n_samples
        1
        >>> tracker.recommend_resources()  # multiprocessing is not enough efficient on Windows/macOS  # doctest: +SKIP
        {'cpu': 2, 'memory': 128, 'gpu': 0, 'vram': 0}
    """

    _server_info: Optional[dict] = None
    _cloud_info: Optional[dict] = None

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

        if platform != "linux" and not is_psutil_available():
            raise ImportError(
                "psutil is required for resource tracking on non-Linux platforms"
            )

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
        self.stop_time = None
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
                self._server_info = get_server_info()
            except Exception as e:
                logger.warning(f"Error fetching server info: {e}")

        def collect_cloud_info():
            """Collect cloud info to be run in a background thread."""
            try:
                self._cloud_info = get_cloud_info()
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
    def n_samples(self) -> int:
        """Number of samples collected by the resource tracker."""
        return min(len(self.process_metrics), len(self.system_metrics))

    @property
    def server_info(self) -> dict:
        """High-level server info.

        Collected data from [resource_tracker.get_server_info][] plus a guess
        for the allocation type of the server: if it's dedicated to the tracked
        process(es) or shared with other processes. The guess is based on the
        [resource_tracker.column_maps.SERVER_ALLOCATION_CHECKS][] checks.
        """
        server_info = self._server_info
        if server_info:
            server_info["allocation"] = None
        if self.n_samples > 0:
            for check in SERVER_ALLOCATION_CHECKS:
                try:
                    system_val = mean(self.system_metrics[check["system_column"]])
                    task_val = mean(self.process_metrics[check["process_column"]])
                    if (system_val > task_val * check["percent"]) or (
                        system_val > task_val + check["absolute"]
                    ):
                        server_info["allocation"] = "shared"
                        break
                except Exception as e:
                    logger.warning(
                        f"Error calculating server allocation based on {check['system_column']} and {check['process_column']}: {e}"
                    )
                    server_info["allocation"] = "unknown"
                    break
            server_info["allocation"] = server_info.get("allocation", "dedicated")
        return server_info

    @property
    def cloud_info(self) -> dict:
        """High-level cloud info.

        Collected data from [resource_tracker.get_cloud_info][].
        """
        return self._cloud_info

    @property
    def process_metrics(self) -> TinyDataFrame:
        """Collected data from [resource_tracker.ProcessTracker][].

        Returns:
            A [resource_tracker.tiny_data_frame.TinyDataFrame][] object containing the collected data or an empty list if the [resource_tracker.ProcessTracker][] is not running.
        """
        try:
            return TinyDataFrame(
                csv_file_path=self.process_tracker_filepath,
            )
        except Exception:
            return TinyDataFrame(data=[])

    @property
    def system_metrics(self) -> TinyDataFrame:
        """Collected data from [resource_tracker.SystemTracker][].

        Returns:
            A [resource_tracker.tiny_data_frame.TinyDataFrame][] object containing the collected data or an empty list if the [resource_tracker.SystemTracker][] is not running.
        """
        try:
            return TinyDataFrame(
                csv_file_path=self.system_tracker_filepath,
            )
        except Exception:
            return TinyDataFrame(data=[])

    def snapshot(self) -> dict:
        """Collect the current state of the resource tracker.

        Returns:
            A dictionary containing the current state of the resource tracker.
        """
        return {
            "metadata": {
                "version": 1,
                "resource_tracker": {
                    "version": __version__,
                    "implementation": "psutil" if is_psutil_available() else "procfs",
                },
                "pid": self.pid,
                "children": self.children,
                "interval": self.interval,
                "method": self.method,
                "autostart": self.autostart,
                "track_processes": "process_tracker" in self.trackers,
                "track_system": "system_tracker" in self.trackers,
                "discover_server": self.discover_server,
                "discover_cloud": self.discover_cloud,
                "start_time": self.start_time,
                "stop_time": self.stop_time or time(),
                "duration": round(
                    (self.stop_time or time()) - self.start_time + self.interval, 2
                ),
            },
            "server_info": self.server_info,
            "cloud_info": self.cloud_info,
            "process_metrics": self.process_metrics.to_dict(),
            "system_metrics": self.system_metrics.to_dict(),
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict):
        """Create a ResourceTracker from a snapshot.

        Args:
            snapshot: A dictionary containing the current state of the resource tracker, created by [resource_tracker.ResourceTracker.snapshot][].
        """
        tracker = cls(
            pid=snapshot["metadata"]["pid"],
            children=snapshot["metadata"]["children"],
            interval=snapshot["metadata"]["interval"],
            method=snapshot["metadata"]["method"],
            autostart=False,
            track_processes=snapshot["metadata"]["track_processes"],
            track_system=snapshot["metadata"]["track_system"],
            discover_server=snapshot["metadata"]["discover_server"],
            discover_cloud=snapshot["metadata"]["discover_cloud"],
        )
        tracker.start_time = snapshot["metadata"]["start_time"]
        tracker.stop_time = snapshot["metadata"]["stop_time"]
        tracker._server_info = snapshot["server_info"]
        tracker._cloud_info = snapshot["cloud_info"]
        TinyDataFrame(data=snapshot["process_metrics"]).to_csv(
            tracker.process_tracker_filepath
        )
        TinyDataFrame(data=snapshot["system_metrics"]).to_csv(
            tracker.system_tracker_filepath
        )
        return tracker

    def dumps(self) -> str:
        """Serialize the resource tracker to a JSON string.

        Returns:
            A JSON string containing the current state of the resource tracker.
        """
        return json_dumps(self.snapshot())

    @classmethod
    def loads(cls, s: str):
        """Deserialize the resource tracker from a JSON string.

        Args:
            s: The JSON string to deserialize the resource tracker from.
        """
        return cls.from_snapshot(json_loads(s))

    def dump(self, file: str):
        """Serialize the resource tracker to a gzipped JSON file.

        Args:
            file: The path to the file to write the serialized resource tracker to.
        """
        with gzip_open(file, "wb") as f:
            f.write(self.dumps().encode())

    @classmethod
    def load(cls, file: str):
        """Deserialize the resource tracker from a gzipped JSON file.

        Args:
            file: The path to the file to read the serialized resource tracker from.
        """
        with gzip_open(file, "rb") as f:
            return cls.loads(f.read().decode())

    def get_combined_metrics(
        self,
        bytes: bool = False,
        human_names: bool = False,
        system_prefix: Optional[str] = None,
        process_prefix: Optional[str] = None,
    ) -> TinyDataFrame:
        """Collected data both from the [resource_tracker.ProcessTracker][] and [resource_tracker.SystemTracker][].

        This is effectively binding the two dataframes together by timestamp,
        and adding a prefix to the column names to distinguish between the system and process metrics.

        Args:
            bytes: Whether to convert all metrics (e.g. memory, VRAM, disk usage) to bytes. Defaults to False, reporting as documented at [resource_tracker.ProcessTracker][] and [resource_tracker.SystemTracker][] (kB, MiB, or GiB).
            human_names: Whether to rename the columns to use human-friendly names. Defaults to False, reporting as documented at [resource_tracker.ProcessTracker][] and [resource_tracker.SystemTracker][] with prefixes.
            system_prefix: Prefix to add to the system-level column names. Defaults to "system_" or "System " based on the value of `human_names`.
            process_prefix: Prefix to add to the process-level column names. Defaults to "process_" or "Process " based on the value of `human_names`.

        Returns:
            A [resource_tracker.tiny_data_frame.TinyDataFrame][] object containing the combined data or an empty list if tracker(s) not running.
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
            return TinyDataFrame(data=[])

    def stats(
        self,
        specs: List[StatSpec] = [
            StatSpec(column="process_cpu_usage", agg=mean, round=2),
            StatSpec(column="process_cpu_usage", agg=max, round=2),
            StatSpec(column="process_memory", agg=mean, round=2),
            StatSpec(column="process_memory", agg=max, round=2),
            StatSpec(column="process_gpu_usage", agg=mean, round=2),
            StatSpec(column="process_gpu_usage", agg=max, round=2),
            StatSpec(column="process_gpu_vram", agg=mean, round=2),
            StatSpec(column="process_gpu_vram", agg=max, round=2),
            StatSpec(column="process_gpu_utilized", agg=mean, round=2),
            StatSpec(column="process_gpu_utilized", agg=max, round=2),
            StatSpec(column="system_disk_space_used_gb", agg=max, round=2),
            StatSpec(column="system_net_recv_bytes", agg=sum),
            StatSpec(column="system_net_sent_bytes", agg=sum),
            StatSpec(
                column="timestamp", agg=lambda x: max(x) - min(x), agg_name="duration"
            ),
        ],
    ) -> dict:
        """Collect statistics from the resource tracker.

        Args:
            specs: A list of [resource_tracker.tiny_data_frame.StatSpec][] objects specifying the statistics to collect.

        Returns:
            A dictionary containing the collected statistics.
        """
        if self.n_samples > 0:
            stats = self.get_combined_metrics().stats(specs)
            stats["timestamp"]["duration"] += self.interval
            return stats
        else:
            raise RuntimeError("No metrics collected (yet)")

    def recommend_resources(self, historical_stats: List[dict] = []) -> dict:
        """Recommend optimal resource allocation based on the measured resource tracker data.

        The recommended resources are based on the following rules:

        - target average CPU usage of the process(es)
        - target maximum memory usage of the process(es) with a 20% buffer
        - target maximum number of GPUs used by the process(es)
        - target maximum VRAM usage of the process(es) with a 20% buffer

        Args:
            historical_stats: Optional list of historical statistics (as returned by [resource_tracker.ResourceTracker.stats][])
                              to consider when making recommendations. These will be combined with the current stats.

        Returns:
            A dictionary containing the recommended resources (cpu, memory, gpu, vram).
        """
        # wait until we have at least one sample
        while self.n_samples == 0:
            sleep(self.interval / 10)
            # avoid infinite wait
            if time() - self.start_time > self.interval * 5:
                logger.warning("Timed out waiting for resource tracker samples")
                return {}

        current_stats = self.stats()
        if historical_stats:
            stats = aggregate_stats([current_stats] + historical_stats)
        else:
            stats = current_stats

        rec = {}
        # target average CPU usage
        rec["cpu"] = max(1, round(stats["process_cpu_usage"]["mean"]))
        # target maximum memory usage (kB->MB) with a 20% buffer
        rec["memory"] = round_memory(mb=stats["process_memory"]["max"] * 1.2 / 1024)
        # target maximum GPU number of GPUs used
        rec["gpu"] = (
            max(1, round(stats["process_gpu_usage"]["max"]))
            if stats["process_gpu_usage"]["mean"] > 0
            else 0
        )
        # target maximum VRAM usage (MiB) with a 20% buffer
        rec["vram"] = (
            round_memory(mb=stats["process_gpu_vram"]["max"] * 1.2)
            if stats["process_gpu_vram"]["max"] > 0
            else 0
        )
        return rec

    def recommend_server(self, **kwargs) -> dict:
        """Recommend the cheapest cloud server matching the recommended resources.

        Args:
            **kwargs: Additional filtering arguments (e.g. vendor_id or compliance_framework_id) to pass to the Spare Cores Keeper API.

        Returns:
            A dictionary containing the recommended cloud server. Response format is described at <https://keeper.sparecores.net/redoc#tag/Query-Resources/operation/search_servers_servers_get>.
        """
        historical_stats = kwargs.pop("historical_stats", [])
        rec = self.recommend_resources(historical_stats=historical_stats)
        return get_recommended_cloud_servers(**rec, **kwargs, n=1)[0]

    def report(
        self,
        integration: Literal["standalone", "metaflow"] = "standalone",
        historical_stats: List[dict] = [],
        status_failed: bool = False,
    ) -> Report:
        duration = (self.stop_time or time()) - self.start_time + self.interval

        current_stats = self.stats()
        if historical_stats:
            combined_stats = aggregate_stats([current_stats] + historical_stats)
        else:
            combined_stats = current_stats

        ctx = {
            "files": _read_report_template_files(),
            "server_info": self.server_info,
            "cloud_info": self.cloud_info,
            "process_metrics": self.process_metrics,
            "system_metrics": self.system_metrics,
            "stats": current_stats,
            "historical_stats": historical_stats,
            "combined_stats": combined_stats,
            "recommended_resources": self.recommend_resources(
                historical_stats=historical_stats
            ),
            "recommended_server": self.recommend_server(
                historical_stats=historical_stats
            ),
            "resource_tracker": {
                "version": __version__,
                "implementation": "psutil" if is_psutil_available() else "procfs",
                "integration": integration,
                "integration_is": {
                    "metaflow": integration == "metaflow",
                    "standalone": integration == "standalone",
                },
                "duration": duration,
                "start_time": self.start_time,
                "stop_time": self.stop_time,
                "stopped": self.stop_time is not None,
                "report_time": time(),
            },
            "status_failed": status_failed,
            "csv": {},
        }

        # comma-separated values
        joined = self.get_combined_metrics(bytes=True, human_names=True)
        for name, columns in REPORT_CSV_MAPPING.items():
            csv_data = joined[columns]
            # convert to JS milliseconds
            csv_data["Timestamp"] = [t * 1000 for t in csv_data["Timestamp"]]
            ctx["csv"][name] = csv_data.to_csv(quote_strings=False)

        # lookup instance prices
        rec_server_cost = ctx["recommended_server"]["min_price_ondemand"]
        rec_run_cost = rec_server_cost / 60 / 60 * duration
        ctx["recommended_server"]["best_ondemand_price_duration"] = rec_run_cost
        if ctx["cloud_info"]["instance_type"] != "unknown":
            current_server_cost = get_instance_price(
                ctx["cloud_info"]["vendor"],
                ctx["cloud_info"]["region"],
                ctx["cloud_info"]["instance_type"],
            )
            if current_server_cost:
                current_run_cost = round(current_server_cost / 60 / 60 * duration, 6)
                ctx["cloud_info"]["run_costs"] = current_run_cost
                ctx["recommended_server"]["cost_savings"] = {
                    "percent": round(
                        (current_run_cost - rec_run_cost) / current_run_cost * 100, 2
                    ),
                    "amount": round(current_run_cost - rec_run_cost, 6),
                }

        html_template_path = path.join(
            path.dirname(__file__), "report_template", "report.html"
        )
        with open(html_template_path) as f:
            html_template = f.read()
        html = render_template(html_template, ctx)
        return Report(html)
