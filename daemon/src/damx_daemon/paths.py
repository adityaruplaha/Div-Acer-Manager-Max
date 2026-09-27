"""Filesystem locations the daemon uses, in one place so that tests can point them elsewhere"""

SOCKET_PATH = "/var/run/DAMX.sock"
LOG_PATH = "/var/log/DAMX_Daemon_Log.log"
CONFIG_PATH = "/etc/DAMX_Daemon/config.ini"
PID_FILE = "/var/run/DAMX-Daemon.pid"
MODPROBE_CONFIG_PATH = "/etc/modprobe.d/linuwu-sense.conf"

# The acer-wmi platform device. Every driver built on the kernel's acer-wmi
# registers it, linuwu_sense included, so its sysfs directory works whichever
# module is loaded; /sys/module/<module>/drivers/platform:acer-wmi/acer-wmi is
# only a link to it.
ACER_WMI_DEVICE_PATH = "/sys/devices/platform/acer-wmi"
PLATFORM_PROFILE_PATH = "/sys/firmware/acpi/platform_profile"
PLATFORM_PROFILE_CHOICES_PATH = "/sys/firmware/acpi/platform_profile_choices"
POWER_SUPPLY_DIR = "/sys/class/power_supply"
