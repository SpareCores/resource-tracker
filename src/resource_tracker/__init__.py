"""
Resource Tracker package for monitoring resource usage, detecting cloud environments, and more.
"""

from logging import NullHandler, getLogger

from .cloud_info import get_cloud_info
from .server_info import get_server_info
from .tiny_data_frame import TinyDataFrame
from .tracker import PidTracker, ResourceTracker, SystemTracker

logger = getLogger(__name__)
logger.addHandler(NullHandler())

__all__ = [
    "PidTracker",
    "SystemTracker",
    "ResourceTracker",
    "get_cloud_info",
    "get_server_info",
    "TinyDataFrame",
]
