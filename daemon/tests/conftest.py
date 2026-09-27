"""Fixtures that point the daemon at a fake sysfs tree"""

import os

import pytest

from damx_daemon import paths


def write(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


@pytest.fixture
def fake_system(tmp_path, monkeypatch):
    """A Nitro laptop driven by acer_wmi, with every NitroSense setting"""
    root = tmp_path
    device = root / "sys/devices/platform/acer-wmi"
    module = root / "sys/module/acer_wmi"
    module.mkdir(parents=True)
    (device / "driver").mkdir(parents=True)
    os.symlink(module, device / "driver" / "module")

    sense = device / "nitro_sense"
    for name, value in {
        "backlight_timeout": "0",
        "battery_calibration": "0",
        "battery_limiter": "1",
        "boot_animation_sound": "1",
        "fan_speed": "0,0",
        "lcd_override": "0",
        "usb_charging": "30",
        "version": "7.3.0.1",
    }.items():
        write(str(sense / name), value + "\n")

    acpi = root / "sys/firmware/acpi"
    write(str(acpi / "platform_profile"), "balanced\n")
    write(str(acpi / "platform_profile_choices"), "low-power quiet balanced balanced-performance performance\n")

    write(str(root / "sys/class/power_supply/ACAD/type"), "Mains\n")
    write(str(root / "sys/class/power_supply/ACAD/online"), "1\n")
    write(str(root / "sys/class/power_supply/BAT1/type"), "Battery\n")

    monkeypatch.setattr(paths, "ACER_WMI_DEVICE_PATH", str(device))
    monkeypatch.setattr(paths, "PLATFORM_PROFILE_PATH", str(acpi / "platform_profile"))
    monkeypatch.setattr(paths, "PLATFORM_PROFILE_CHOICES_PATH", str(acpi / "platform_profile_choices"))
    monkeypatch.setattr(paths, "POWER_SUPPLY_DIR", str(root / "sys/class/power_supply"))
    monkeypatch.setattr(paths, "MODPROBE_CONFIG_PATH", str(root / "etc/modprobe.d/linuwu-sense.conf"))
    monkeypatch.setattr(paths, "CONFIG_PATH", str(root / "etc/DAMX_Daemon/config.ini"))
    monkeypatch.setattr(paths, "SOCKET_PATH", str(root / "DAMX.sock"))
    return root


@pytest.fixture
def no_subprocesses(monkeypatch):
    """Fail the test if the daemon tries to run rmmod, modprobe or systemctl"""
    import subprocess

    def refuse(*args, **kwargs):
        raise AssertionError(f"unexpected subprocess: {args}")

    monkeypatch.setattr(subprocess, "run", refuse)
