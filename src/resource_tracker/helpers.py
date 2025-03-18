"""
Helpers for the resource tracker.
"""

from functools import cache
from glob import glob
from re import search


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
