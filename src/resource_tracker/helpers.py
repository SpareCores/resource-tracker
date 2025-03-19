"""
Helpers for the resource tracker.
"""

import os
from functools import cache
from glob import glob
from importlib.util import find_spec
from re import search
from typing import Callable


@cache
def is_partition(disk_name: str) -> bool:
    """
    Determine if a disk name represents a partition rather than a whole disk.

    Args:
        disk_name: Name of the disk device (e.g., 'sda1', 'nvme0n1p1')

    Returns:s
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


@cache
def is_psutil_available() -> bool:
    """
    Check if psutil is installed and available for import.

    Returns:
        bool: True if psutil is available, False otherwise
    """
    try:
        return find_spec("psutil") is not None
    except ImportError:
        return False


@cache
def is_procfs_available() -> bool:
    """
    Check if procfs is available on the system.

    Returns:
        bool: True if procfs is available, False otherwise
    """
    return os.path.isdir("/proc") and os.access("/proc", os.R_OK)


@cache
def get_tracker_implementation() -> tuple[Callable, Callable]:
    """
    Determine which tracker implementation to use based on available system resources.

    Returns:
        tuple: A tuple containing (get_pid_stats, get_system_stats) functions from the appropriate implementation module.

    Raises:
        ImportError: If no suitable implementation is available.
    """
    if is_psutil_available():
        from .tracker_psutil import get_pid_stats, get_system_stats
    elif is_procfs_available():
        from .tracker_procfs import get_pid_stats, get_system_stats
    else:
        raise ImportError(
            "No tracker implementation available - install psutil or use a Linux system with procfs."
        )
    return get_pid_stats, get_system_stats
