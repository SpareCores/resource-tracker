"""
Helpers to track resource usage via psutil.
"""

from contextlib import suppress
from time import time
from typing import Dict, Set, Union

from psutil import Process

from .nvidia import process_nvidia_smi_pmon, start_nvidia_smi_pmon


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
            - utime (int): The total user mode CPU time in clock ticks.
            - stime (int): The total system mode CPU time in clock ticks.
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
                    stats["memory"] += getattr(memory_info, attr)
                    break
            io_counters = process.io_counters()
            stats["read_bytes"] += io_counters.read_bytes
            stats["write_bytes"] += io_counters.write_bytes

    stats.update(process_nvidia_smi_pmon(nvidia_process, [p.pid for p in processes]))

    return stats
