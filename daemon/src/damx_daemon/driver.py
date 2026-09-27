"""The kernel driver behind the acer-wmi device"""

import os
from enum import Enum

from . import paths

DEFAULT_DRIVER_MODULE = "linuwu_sense"


def detect_driver_module() -> str:
    """Return the kernel module driving the acer-wmi device.

    This is linuwu_sense for Linuwu-Sense, or acer_wmi for drivers such as
    acer-wmi-linuwu that replace the in-tree module. Falls back to
    linuwu_sense when the device is not bound to a module.
    """
    module_link = os.path.join(paths.ACER_WMI_DEVICE_PATH, "driver", "module")
    if os.path.exists(module_link):
        return os.path.basename(os.path.realpath(module_link))
    return DEFAULT_DRIVER_MODULE


class LaptopType(Enum):
    UNKNOWN = 0
    PREDATOR = 1
    NITRO = 2
