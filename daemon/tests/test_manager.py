import os
import subprocess
import threading

import pytest

from damx_daemon import paths
from damx_daemon.driver import LaptopType, detect_driver_module
from damx_daemon.manager import DAMXManager


def read(path):
    with open(path) as f:
        return f.read()


@pytest.fixture
def manager(fake_system, no_subprocesses):
    return DAMXManager()


def test_driver_module_is_read_from_the_device(fake_system):
    assert detect_driver_module() == "acer_wmi"


def test_driver_module_defaults_to_linuwu_sense(fake_system):
    os.unlink(os.path.join(paths.ACER_WMI_DEVICE_PATH, "driver", "module"))
    assert detect_driver_module() == "linuwu_sense"


def test_detects_a_nitro_and_its_features(manager):
    assert manager.laptop_type == LaptopType.NITRO
    assert manager.driver_module == "acer_wmi"
    assert manager.base_path == os.path.join(paths.ACER_WMI_DEVICE_PATH, "nitro_sense")
    assert manager.available_features == {
        "backlight_timeout", "battery_calibration", "battery_limiter", "boot_animation_sound",
        "fan_speed", "lcd_override", "usb_charging", "thermal_profile",
    }
    assert manager.get_driver_version() == "7.3.0.1"


def test_unknown_laptop_with_acer_wmi_does_not_reload_the_driver(fake_system, no_subprocesses):
    remove_nitro_sense()

    manager = DAMXManager()
    assert manager.laptop_type == LaptopType.UNKNOWN
    assert manager.available_features == {"thermal_profile"}


def remove_nitro_sense():
    sense = os.path.join(paths.ACER_WMI_DEVICE_PATH, "nitro_sense")
    for name in os.listdir(sense):
        os.unlink(os.path.join(sense, name))
    os.rmdir(sense)


def test_unknown_laptop_with_linuwu_sense_reloads_the_driver_once(fake_system, monkeypatch):
    remove_nitro_sense()
    os.unlink(os.path.join(paths.ACER_WMI_DEVICE_PATH, "driver", "module"))
    monkeypatch.setattr(DAMXManager, "DRIVER_SETTLE_TIMEOUT", 0.2)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: calls.append(args))

    manager = DAMXManager()
    assert calls == [["rmmod", "linuwu_sense"], ["modprobe", "linuwu_sense"]]
    assert manager.laptop_type == LaptopType.UNKNOWN


def test_waits_for_the_driver_to_register_its_settings(fake_system, monkeypatch):
    sense = os.path.join(paths.ACER_WMI_DEVICE_PATH, "nitro_sense")
    os.rename(sense, sense + ".later")
    os.unlink(os.path.join(paths.ACER_WMI_DEVICE_PATH, "driver", "module"))
    threading.Timer(0.3, os.rename, (sense + ".later", sense)).start()

    manager = DAMXManager()
    assert manager.laptop_type == LaptopType.NITRO


@pytest.mark.parametrize("name", [
    "backlight_timeout", "battery_calibration", "battery_limiter", "boot_animation_sound", "lcd_override",
])
def test_boolean_settings_write_1_or_0(manager, name):
    attribute = os.path.join(manager.base_path, name)
    assert getattr(manager, f"set_{name}")(True)
    assert read(attribute) == "1"
    assert getattr(manager, f"set_{name}")(False)
    assert read(attribute) == "0"


def test_fan_speed(manager):
    assert manager.get_fan_speed() == ("0", "0")
    assert manager.set_fan_speed(40, 60)
    assert read(os.path.join(manager.base_path, "fan_speed")) == "40,60"
    assert not manager.set_fan_speed(101, 0)


def test_usb_charging_accepts_only_known_levels(manager):
    assert manager.set_usb_charging(20)
    assert read(os.path.join(manager.base_path, "usb_charging")) == "20"
    assert not manager.set_usb_charging(15)


def test_thermal_profile_accepts_only_offered_choices(manager):
    assert manager.get_thermal_profile() == "balanced"
    assert manager.set_thermal_profile("performance")
    assert read(paths.PLATFORM_PROFILE_PATH) == "performance"
    assert not manager.set_thermal_profile("turbo")


def test_all_settings(manager):
    settings = manager.get_all_settings()
    assert settings["laptop_type"] == "NITRO"
    assert settings["thermal_profile"]["current"] == "balanced"
    assert settings["fan_speed"] == {"cpu": "0", "gpu": "0"}
    assert settings["usb_charging"] == "30"


def test_modprobe_parameter_names_the_driving_module(manager):
    assert manager._set_modprobe_parameter("nitro_v4")
    assert read(paths.MODPROBE_CONFIG_PATH) == "options acer_wmi nitro_v4=1\n"
    assert manager.get_modprobe_parameter() == "nitro_v4"
    assert manager._remove_modprobe_parameter()
    assert not os.path.exists(paths.MODPROBE_CONFIG_PATH)


def test_enable_all_is_refused_for_acer_wmi(manager):
    assert not manager.set_modprobe_parameter("enable_all")
    assert not os.path.exists(paths.MODPROBE_CONFIG_PATH)


def test_the_daemon_restart_waits_for_the_answer(manager):
    # no_subprocesses fails the test if systemctl is run here
    assert manager._restart_daemon()
    assert manager.restart_requested
