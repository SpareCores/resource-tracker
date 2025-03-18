"""Helpers to monitor NVIDIA GPUs."""

from contextlib import suppress
from subprocess import PIPE, Popen, TimeoutExpired


def start_nvidia_smi_pmon() -> Popen | None:
    """Start a subprocess to monitor NVIDIA GPUs at the process level using `nvidia-smi pmon`.

    Note that `nvidia-smi pmon` is limited to monitoring max. 4 GPUs.

    Returns:
        The subprocess object or None if nvidia-smi is not installed.
    """
    with suppress(FileNotFoundError):
        return Popen(
            ["nvidia-smi", "pmon", "-c", "1", "-s", "um", "-d", "1"],
            stdout=PIPE,
        )


def process_nvidia_smi_pmon(
    nvidia_process: Popen | None, pids: set[int] | None = None
) -> dict[str, int | float]:
    """Wait for the `nvidia-smi pmon` subprocess to finish and process the output.

    Args:
        nvidia_process: The subprocess object to monitor or None if not started.
          Returned by `start_nvidia_smi_pmon`.
        pids: A set of process IDs to monitor. If None, all processes are monitored.

    Returns:
        A dictionary of GPU stats:

            - gpu_usage (float): The current GPU utilization between 0 and GPU count.
            - gpu_vram (float): The current GPU memory/VRAM used in MiB.
            - gpu_utilized (int): The number of GPUs with utilization > 0.
            - gpu_utilized_indexes (set[int]): The set of GPU indexes with utilization > 0.
    """
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
                if pids is None or int(parts[1]) in pids:
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
    return gpu_stats
