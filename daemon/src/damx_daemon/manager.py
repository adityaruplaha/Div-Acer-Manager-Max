"""Detection and control of the laptop's features"""

import ctypes
import fcntl
import glob
import os
import subprocess
import sys
import time
from typing import Dict, List, Set, Tuple

from . import VERSION, paths
from .driver import DEFAULT_DRIVER_MODULE, LaptopType, detect_driver_module
from .enek5130 import ENEK5130_HID_ID, ENEK5130_HID_NAME, HIDIOCSFEATURE
from .files import atomic_write
from .logs import log


class DAMXManager:
    """Manages all the DAMX-Daemon features"""

    MAX_RESTART_ATTEMPTS = 20
    # Kept in /run, which only root can write and which is cleared at boot,
    # rather than in world-writable /tmp
    RESTART_COUNTER_DIR = "/run/damx"
    RESTART_COUNTER_FILE = os.path.join(RESTART_COUNTER_DIR, "restart_attempts")

    def __init__(self):
        """Detect the driver, the laptop type and the available features"""
        log.info(f"** Starting DAMX-Daemon v{VERSION} **")

        # Check that a driver has registered the acer-wmi device
        self.driver_module = detect_driver_module()
        if not os.path.exists(paths.ACER_WMI_DEVICE_PATH):
            log.error("acer-wmi device not found. Please install a driver that provides it, such as linuwu_sense, first.")
        else:
            log.info(f"acer-wmi device found, driven by the {self.driver_module} module. Proceeding with initialization.")
        
        self.laptop_type = self._detect_laptop_type()
        # self.keyboard_monitor = None

        #added a delay so that driver sets up properly first
        time.sleep(0.2)

        # If unknown laptop type detected, try restarting drivers (with limit)
        if self.laptop_type == LaptopType.UNKNOWN:
            current_attempts = self._get_restart_attempts()
            
            if self.driver_module != DEFAULT_DRIVER_MODULE:
                # Restarting helps linuwu_sense, which can come up before its
                # settings are ready; other modules gain nothing from it.
                log.info(f"Not restarting {self.driver_module}, continuing with limited functionality")
            elif current_attempts < self.MAX_RESTART_ATTEMPTS:
                attempts = self._increment_restart_attempts()
                log.warning(f"Unknown laptop type detected, attempting driver restart (attempt {attempts}/{self.MAX_RESTART_ATTEMPTS})...")
                
                if self._restart_drivers_and_daemon():
                    # The daemon will restart itself, so we should exit this instance
                    log.info("Driver restart initiated, daemon will restart automatically")
                    sys.exit(0)
                else:
                    log.error(f"Failed to restart drivers (attempt {attempts}), continuing with limited functionality")
            else:
                log.error(f"Maximum restart attempts ({self.MAX_RESTART_ATTEMPTS}) reached, giving up on driver restart")
                log.info("Continuing with unknown laptop type and limited functionality")
        else:
            # Reset counter on successful detection
            self._reset_restart_attempts()
        
        self.base_path = self._get_base_path()
        self.has_four_zone_kb = self._check_four_zone_kb()
        self.enek5130_hid_device = self._find_enek5130_hid_device()
        self.current_modprobe_param = self._detect_current_modprobe_param()

        # Available features set
        self.available_features = self._detect_available_features()

        log.info(f"Detected laptop type: {self.laptop_type.name}")
        log.info(f"Base path: {self.base_path}")
        log.info(f"Four-zone keyboard: {'Yes' if self.has_four_zone_kb else 'No'}")
        log.info(f"ENEK5130 HID RGB device: {self.enek5130_hid_device or 'Not found'}")
        log.info(f"Available features: {', '.join(self.available_features)}")

        # Check if paths exist
        if not os.path.exists(self.base_path) and self.laptop_type != LaptopType.UNKNOWN:
            log.error(f"Base path does not exist: {self.base_path}")
            raise FileNotFoundError(f"Base path does not exist: {self.base_path}")
        
        self.power_monitor = None

    def _get_restart_attempts(self) -> int:
        """Get current restart attempt count"""
        try:
            if os.path.exists(self.RESTART_COUNTER_FILE):
                with open(self.RESTART_COUNTER_FILE, 'r') as f:
                    return int(f.read().strip())
        except (ValueError, IOError):
            pass
        return 0

    def _increment_restart_attempts(self) -> int:
        """Increment and return restart attempt count"""
        attempts = self._get_restart_attempts() + 1
        try:
            os.makedirs(self.RESTART_COUNTER_DIR, mode=0o700, exist_ok=True)
            with open(self.RESTART_COUNTER_FILE, 'w') as f:
                f.write(str(attempts))
        except IOError as e:
            log.error(f"Failed to write restart counter: {e}")
        return attempts

    def _reset_restart_attempts(self):
        """Reset restart attempt counter"""
        try:
            if os.path.exists(self.RESTART_COUNTER_FILE):
                os.unlink(self.RESTART_COUNTER_FILE)
        except IOError as e:
            log.error(f"Failed to reset restart counter: {e}")

    def _force_model_nitro(self):
        """Restart the driver module and DAMX daemon service with nitro_v4 parameter"""
        log.info("Forcing model detection to Nitro by restarting drivers and daemon")

        try:
            # Remove the module
            subprocess.run(['rmmod', self.driver_module], check=True)
            log.info(f"Successfully removed {self.driver_module} module")
            
            # Wait a moment
            time.sleep(2)
            
            # Reload the module
            subprocess.run(['modprobe', self.driver_module, 'nitro_v4'], check=True)
            log.info(f"Successfully reloaded {self.driver_module} module")
            
            # Wait a moment for module to initialize
            time.sleep(3)
            
            # Restart the daemon service
            log.info("Restarting DAMX daemon service (may produce an error)")
            subprocess.run(['systemctl', 'restart', 'damx-daemon.service'], check=True)
            
            return True
        
        except Exception as e:
            log.error(f"Unexpected error while Forcing Nitro Model: {e}")
            return False
        

    def _force_model_predator(self):
        """Restart the driver module and DAMX daemon service with predator_v4 parameter"""
        log.info("Forcing model detection to Predator by restarting drivers and daemon")

        try:
            # Remove the module
            subprocess.run(['rmmod', self.driver_module], check=True)
            log.info(f"Successfully removed {self.driver_module} module")
            
            # Wait a moment
            time.sleep(2)
            
            # Reload the module
            subprocess.run(['modprobe', self.driver_module, 'predator_v4'], check=True)
            log.info(f"Successfully reloaded {self.driver_module} module")

            # Wait a moment for module to initialize
            time.sleep(3)

            # Restart the daemon service
            log.info("Restarting DAMX daemon service (may produce an error)")
            subprocess.run(['systemctl', 'restart', 'damx-daemon.service'], check=True)

            return True

        except Exception as e:
            log.error(f"Unexpected error while Forcing Predator Model: {e}")
            return False

    def _force_enable_all(self):
        """Restart the driver module and DAMX daemon service with enable_all parameter"""
        log.info("Forcing all features by restarting daemon and drivers with parameter enable_all")

        if self.driver_module != "linuwu_sense":
            log.error(f"enable_all is a linuwu_sense parameter; {self.driver_module} does not support it")
            return False

        try:
            # Remove the module
            subprocess.run(['rmmod', self.driver_module], check=True)
            log.info(f"Successfully removed {self.driver_module} module")
            
            # Wait a moment
            time.sleep(2)
            
            # Reload the module
            subprocess.run(['modprobe', self.driver_module, 'enable_all'], check=True)
            log.info(f"Successfully reloaded {self.driver_module} module with enable_all parameter")
            
            # Wait a moment for module to initialize
            time.sleep(3)
            
            # Restart the daemon service
            log.info("Restarting DAMX daemon service (may produce an error)")
            subprocess.run(['systemctl', 'restart', 'damx-daemon.service'], check=True)
            
            return True
        
        except Exception as e:
            log.error(f"Unexpected error while Forcing All Features: {e}")
            return False
        
    def _detect_current_modprobe_param(self) -> str:
        """Detect which modprobe parameter is currently set"""
        try:
            if os.path.exists(paths.MODPROBE_CONFIG_PATH):
                with open(paths.MODPROBE_CONFIG_PATH, 'r') as f:
                    content = f.read().strip().lower()
                    if "nitro_v4" in content:
                        return "nitro_v4"
                    elif "predator_v4" in content:
                        return "predator_v4"
                    elif "enable_all" in content:
                        return "enable_all"
        except Exception as e:
            log.error(f"Failed to read modprobe config: {e}")
        return ""

    def _set_modprobe_parameter(self, param: str) -> bool:
        """Set modprobe parameter in config file"""
        try:
            atomic_write(paths.MODPROBE_CONFIG_PATH, f"options {self.driver_module} {param}=1\n")

            # Verify the write was successful
            if os.path.exists(paths.MODPROBE_CONFIG_PATH):
                with open(paths.MODPROBE_CONFIG_PATH, 'r') as f:
                    content = f.read().strip()
                    expected = f"options {self.driver_module} {param}=1"
                    if expected in content:
                        log.info(f"Successfully set modprobe parameter: {param}")
                        self.current_modprobe_param = param
                        return True
                    else:
                        log.error(f"Verification failed. Expected '{expected}', got '{content}'")
                        return False
            else:
                log.error(f"Config file not found after write: {paths.MODPROBE_CONFIG_PATH}")
                return False
                
        except Exception as e:
            log.error(f"Failed to set modprobe parameter: {e}")
            return False

    def _remove_modprobe_parameter(self) -> bool:
        """Remove modprobe parameter config file"""
        try:
            if os.path.exists(paths.MODPROBE_CONFIG_PATH):
                os.unlink(paths.MODPROBE_CONFIG_PATH)
                # Verify removal
                if not os.path.exists(paths.MODPROBE_CONFIG_PATH):
                    log.info("Successfully removed modprobe parameter config")
                    self.current_modprobe_param = ""
                    return True
                else:
                    log.error("Failed to verify modprobe parameter removal")
                    return False
            else:
                self.current_modprobe_param = ""
                return True
        except Exception as e:
            log.error(f"Failed to remove modprobe parameter: {e}")
            return False

    def get_modprobe_parameter(self) -> str:
        """Get current modprobe parameter"""
        return self.current_modprobe_param

    def set_modprobe_parameter(self, param: str) -> bool:
        """Set modprobe parameter and restart drivers"""
        log.info(f"Attempting to set modprobe parameter: {param}")
        log.info(f"Current parameter: {self.current_modprobe_param}")
        log.info(f"Config path: {paths.MODPROBE_CONFIG_PATH}")
        
        if param not in ["nitro_v4", "predator_v4", "enable_all", ""]:
            log.error(f"Invalid modprobe parameter: {param}")
            return False

        if param == "enable_all" and self.driver_module != "linuwu_sense":
            log.error(f"enable_all is a linuwu_sense parameter; {self.driver_module} does not support it")
            return False
        
        if param == "":
            # Remove parameter
            log.info("Removing modprobe parameter")
            if not self._remove_modprobe_parameter():
                log.error("Failed to remove modprobe parameter")
                return False
        else:
            # Set parameter
            log.info(f"Setting modprobe parameter to: {param}")
            if not self._set_modprobe_parameter(param):
                log.error(f"Failed to set modprobe parameter: {param}")
                return False
        
        # Verify the change
        if param != "":
            if not self._verify_modprobe_parameter(param):
                log.error(f"Verification failed for parameter: {param}")
                return False
        
        # Restart drivers and daemon
        log.info("Restarting drivers and daemon with new parameter")
        return self._restart_drivers_and_daemon()

    def _verify_modprobe_parameter(self, param: str) -> bool:
        """Verify that the modprobe parameter was written correctly"""
        try:
            if os.path.exists(paths.MODPROBE_CONFIG_PATH):
                with open(paths.MODPROBE_CONFIG_PATH, 'r') as f:
                    content = f.read().strip()
                    expected = f"options {self.driver_module} {param}=1"
                    if expected in content:
                        log.info(f"Verification successful for parameter: {param}")
                        return True
                    else:
                        log.error(f"Verification failed. Expected '{expected}', got '{content}'")
                        return False
            else:
                log.error(f"Config file does not exist: {paths.MODPROBE_CONFIG_PATH}")
                return False
        except Exception as e:
            log.error(f"Verification error: {e}")
            return False
        
    def _restart_daemon(self):
        """Restart DAMX daemon service alone"""
        attempts = self._get_restart_attempts()
        log.info("Attempting to restart daemon")
        
        try:
            # Restart the daemon service
            log.info("Restarting DAMX daemon service (may produce an error)")
            subprocess.run(['systemctl', 'restart', 'damx-daemon.service'], check=True)
            
            return True
            
        except Exception as e:
            log.error(f"Unexpected error during restart (attempt {attempts}): {e}")
            return False
            

    def _restart_drivers_and_daemon(self):
        """Restart the driver module and DAMX daemon service"""
        attempts = self._get_restart_attempts()
        log.info(f"Attempting to restart drivers and daemon (attempt {attempts}/{self.MAX_RESTART_ATTEMPTS})...")
        
        try:
            # Remove the module
            subprocess.run(['rmmod', self.driver_module], check=True)
            log.info(f"Successfully removed {self.driver_module} module")
            
            # Wait a moment
            time.sleep(2)
            
            # Reload the module
            subprocess.run(['modprobe', self.driver_module], check=True)
            log.info(f"Successfully reloaded {self.driver_module} module")
            
            # Wait a moment for module to initialize
            time.sleep(3)
            
            # Restart the daemon service
            log.info("Restarting DAMX daemon service (may produce an error)")
            subprocess.run(['systemctl', 'restart', 'damx-daemon.service'], check=True)
            
            return True
            
        except Exception as e:
            log.error(f"Unexpected error during restart (attempt {attempts}): {e}")
            return False
            
    def _detect_laptop_type(self) -> LaptopType:
        """Detect whether this is a Predator or Nitro laptop"""
        predator_path = os.path.join(paths.ACER_WMI_DEVICE_PATH, "predator_sense")
        nitro_path = os.path.join(paths.ACER_WMI_DEVICE_PATH, "nitro_sense")

        if os.path.exists(predator_path):
            return LaptopType.PREDATOR
        elif os.path.exists(nitro_path):
            return LaptopType.NITRO
        else:
            return LaptopType.UNKNOWN

    def _get_base_path(self) -> str:
        """Get the base path for VFS access based on laptop type"""
        if self.laptop_type == LaptopType.PREDATOR:
            return os.path.join(paths.ACER_WMI_DEVICE_PATH, "predator_sense")
        elif self.laptop_type == LaptopType.NITRO:
            return os.path.join(paths.ACER_WMI_DEVICE_PATH, "nitro_sense")
        else:
            return ""

    def get_driver_version(self) -> str:
        """Get Driver version"""
        version_file = os.path.join(self.base_path, "version")
        if not os.path.isfile(version_file):
            return "Unknown Version"
        
        try:
            with open(version_file, "r") as f:
                return f.read().strip() or "Unknown Version"
        except (OSError, IOError):
            return "Unknown Version"
    

    def _detect_available_features(self) -> Set[str]:
        """Detect which features are available on the current laptop"""
        available = set()

        # Always check thermal profile since it's ACPI standard
        if os.path.exists(paths.PLATFORM_PROFILE_PATH):
            available.add("thermal_profile")

        # Only check other features if laptop type is recognized
        if self.laptop_type != LaptopType.UNKNOWN and os.path.exists(self.base_path):
            feature_files = [
                ("backlight_timeout", "backlight_timeout"),
                ("battery_calibration", "battery_calibration"),
                ("battery_limiter", "battery_limiter"),
                ("boot_animation_sound", "boot_animation_sound"),
                ("fan_speed", "fan_speed"),
                ("lcd_override", "lcd_override"),
                ("usb_charging", "usb_charging"),
            ]

            for feature_name, file_name in feature_files:
                file_path = os.path.join(self.base_path, file_name)
                if os.path.exists(file_path):
                    available.add(feature_name)

        # Check keyboard features
        if self.has_four_zone_kb:
            kb_base = os.path.join(paths.ACER_WMI_DEVICE_PATH, "four_zoned_kb")
            if os.path.exists(os.path.join(kb_base, "per_zone_mode")):
                available.add("per_zone_mode")
            if os.path.exists(os.path.join(kb_base, "four_zone_mode")):
                available.add("four_zone_mode")

        # Newer Acer keyboards can require direct ENEK5130 HID feature reports.
        # Do not advertise the existing linuwu_sense RGB feature names unless
        # their sysfs files exist; the ENEK backend is currently a static-color
        # supplement for devices where those sysfs writes are ineffective.
        if self.enek5130_hid_device:
            available.add("enek5130_hid_rgb")

        return available

    def _check_four_zone_kb(self) -> bool:
        """Check if four-zone keyboard is available"""
        if self.laptop_type != LaptopType.UNKNOWN:
            kb_path = os.path.join(paths.ACER_WMI_DEVICE_PATH, "four_zoned_kb")
            return os.path.exists(kb_path)
        return False

    def _read_file(self, path: str) -> str:
        """Read from a VFS file"""
        try:
            with open(path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            log.error(f"Failed to read from {path}: {e}")
            return ""

    def _write_file(self, path: str, value: str) -> bool:
        """Write to a VFS file"""
        try:
            with open(path, 'w') as f:
                f.write(str(value))
            return True
        except Exception as e:
            log.error(f"Failed to write to {path}: {e}")
            return False

    def _find_enek5130_hid_device(self) -> str:
        """Find the ENEK5130 RGB hidraw device by stable sysfs identity."""
        candidates = self._find_enek5130_hid_candidates()
        return candidates[0] if candidates else ""

    def _find_enek5130_hid_candidates(self) -> List[str]:
        """Find all ENEK5130 hidraw candidates by stable sysfs identity."""
        candidates = []
        for dev in sorted(glob.glob('/dev/hidraw*')):
            uevent_path = f"/sys/class/hidraw/{os.path.basename(dev)}/device/uevent"
            try:
                with open(uevent_path, 'r', encoding='utf-8') as f:
                    uevent = f.read()
            except OSError:
                continue

            if ENEK5130_HID_ID in uevent or ENEK5130_HID_NAME in uevent:
                candidates.append(dev)

        return candidates

    def _set_enek5130_hid_report(self, effect: int, red: int, green: int, blue: int,
                                  brightness: int, speed: int, direction: int,
                                  zone_mask: int) -> bool:
        """Send an ENEK5130 keyboard RGB HID feature report.

        Known packet format:
        a4 21 effect brightness speed direction rr gg bb zone_mask 00
        zone_mask 0x01/0x02/0x04/0x08 targets zones 1-4; 0x0f targets all zones.
        """
        candidates = self._find_enek5130_hid_candidates()
        if self.enek5130_hid_device and self.enek5130_hid_device not in candidates:
            candidates.insert(0, self.enek5130_hid_device)

        if not candidates:
            log.debug("ENEK5130 HID RGB device not found")
            return False

        if not all(0 <= value <= 255 for value in [effect, speed, direction]):
            log.error(f"Invalid ENEK5130 effect fields: effect={effect}, speed={speed}, direction={direction}")
            return False

        if not (0 <= brightness <= 100):
            log.error(f"Invalid ENEK5130 brightness. Must be between 0 and 100: {brightness}")
            return False

        if not all(0 <= color <= 255 for color in [red, green, blue]):
            log.error(f"Invalid ENEK5130 RGB values. Must be 0-255: {red},{green},{blue}")
            return False

        if not (0 <= zone_mask <= 0x0F):
            log.error(f"Invalid ENEK5130 zone mask. Must be 0x00-0x0f: {zone_mask:#x}")
            return False

        packet = bytes([
            0xA4, 0x21, effect, brightness,
            speed, direction,
            red, green, blue, zone_mask, 0x00
        ])

        for device in candidates:
            try:
                fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)
                try:
                    buf = ctypes.create_string_buffer(packet, len(packet))
                    ret = fcntl.ioctl(fd, HIDIOCSFEATURE(len(packet)), buf, True)
                    log.info(
                        "Set ENEK5130 HID RGB via %s report=%s ret=%s",
                        device,
                        ' '.join(f'{b:02x}' for b in packet),
                        ret
                    )
                    self.enek5130_hid_device = device
                    return True
                finally:
                    os.close(fd)
            except Exception as e:
                log.warning(f"Failed ENEK5130 HID RGB candidate {device}: {e}")

        return False

    def _set_enek5130_zone_color(self, red: int, green: int, blue: int,
                                  brightness: int, zone_mask: int) -> bool:
        """Set a static color on one or more ENEK5130 keyboard zones."""
        return self._set_enek5130_hid_report(0x02, red, green, blue, brightness, 0x00, 0x00, zone_mask)

    def _set_enek5130_static_color(self, red: int, green: int, blue: int, brightness: int,
                                   speed: int = 0, direction: int = 0) -> bool:
        """Set static all-zone color using the Acer ENEK5130 HID feature report."""
        return self._set_enek5130_zone_color(red, green, blue, brightness, 0x0F)

    def _set_enek5130_per_zone_color(self, zones: List[str], brightness: int) -> bool:
        """Set four ENEK5130 zones using confirmed zone masks 0x01,0x02,0x04,0x08."""
        zone_masks = [0x01, 0x02, 0x04, 0x08]
        for zone, zone_mask in zip(zones, zone_masks):
            red = int(zone[0:2], 16)
            green = int(zone[2:4], 16)
            blue = int(zone[4:6], 16)
            if not self._set_enek5130_zone_color(red, green, blue, brightness, zone_mask):
                return False
        return True

    def _set_enek5130_effect(self, mode: int, speed: int, brightness: int,
                             direction: int, red: int, green: int, blue: int) -> bool:
        """Set a confirmed ENEK5130 dynamic lighting effect.

        DAMX UI modes:
        0 Static, 1 Breathing, 2 Neon, 3 Wave, 4 Shifting,
        5 Zoom, 6 Meteor, 7 Twinkling.

        Confirmed on Acer Nitro ANV16S-41 / ENEK5130:
        0x04 breathing, 0x05 neon-like, 0x07 wave/shifting,
        0x09 zoom, 0x0a snake/meteor-like, 0x0b random/twinkling-like.

        Unstable/unknown values are deliberately not mapped here:
        0x01/0x03 black/off, 0x06 short flash/returns to previous,
        0x08 glitch, 0x0c freezes previous lighting effect.
        """
        effect_map = {
            1: 0x04,  # Breathing Mode
            2: 0x05,  # Neon Mode
            3: 0x07,  # Wave Mode
            4: 0x07,  # Shifting Mode (same confirmed native wave/shifting effect)
            5: 0x09,  # Zoom Mode
            6: 0x0A,  # Meteor Mode (snake-like on ENEK5130)
            7: 0x0B,  # Twinkling Mode (random on ENEK5130)
        }

        effect = effect_map.get(mode)
        if effect is None:
            return False

        # DAMX currently exposes speed as 0-9. Although ENEK5130 accepts larger
        # speed bytes for breathing/neon, direct UI values match the app's
        # expected speed feel better than scaling 0-9 to 0-100.
        if effect in [0x04, 0x05]:
            hid_speed = speed
        else:
            hid_speed = min(10, max(1, speed + 1))

        return self._set_enek5130_hid_report(
            effect, red, green, blue, brightness, hid_speed, direction, 0x0F
        )

    def get_thermal_profile(self) -> str:
        """Get current thermal profile"""
        if "thermal_profile" not in self.available_features:
            return ""
        return self._read_file(paths.PLATFORM_PROFILE_PATH)

    def set_thermal_profile(self, profile: str) -> bool:
        """Set thermal profile"""
        if "thermal_profile" not in self.available_features:
            return False

        available_profiles = self.get_thermal_profile_choices()
        if profile not in available_profiles:
            log.error(f"Invalid thermal profile: {profile}. Available profiles: {available_profiles}")
            return False

        return self._write_file(paths.PLATFORM_PROFILE_PATH, profile)

    def get_thermal_profile_choices(self) -> List[str]:
        """Get available thermal profiles"""
        if "thermal_profile" not in self.available_features:
            return []

        choices = self._read_file(paths.PLATFORM_PROFILE_CHOICES_PATH)
        return choices.split() if choices else []

    def get_backlight_timeout(self) -> str:
        """Get backlight timeout status"""
        if "backlight_timeout" not in self.available_features:
            return ""

        return self._read_file(os.path.join(self.base_path, "backlight_timeout"))

    def set_backlight_timeout(self, enabled: bool) -> bool:
        """Set backlight timeout status"""
        if "backlight_timeout" not in self.available_features:
            return False

        return self._write_file(
            os.path.join(self.base_path, "backlight_timeout"),
            "1" if enabled else "0"
        )

    def get_battery_calibration(self) -> str:
        """Get battery calibration status"""
        if "battery_calibration" not in self.available_features:
            return ""

        return self._read_file(os.path.join(self.base_path, "battery_calibration"))

    def set_battery_calibration(self, enabled: bool) -> bool:
        """Start or stop battery calibration"""
        if "battery_calibration" not in self.available_features:
            return False

        return self._write_file(
            os.path.join(self.base_path, "battery_calibration"),
            "1" if enabled else "0"
        )

    def get_battery_limiter(self) -> str:
        """Get battery limiter status"""
        if "battery_limiter" not in self.available_features:
            return ""

        return self._read_file(os.path.join(self.base_path, "battery_limiter"))

    def set_battery_limiter(self, enabled: bool) -> bool:
        """Set battery limiter status"""
        if "battery_limiter" not in self.available_features:
            return False

        return self._write_file(
            os.path.join(self.base_path, "battery_limiter"),
            "1" if enabled else "0"
        )

    def get_boot_animation_sound(self) -> str:
        """Get boot animation sound status"""
        if "boot_animation_sound" not in self.available_features:
            return ""

        return self._read_file(os.path.join(self.base_path, "boot_animation_sound"))

    def set_boot_animation_sound(self, enabled: bool) -> bool:
        """Set boot animation sound status"""
        if "boot_animation_sound" not in self.available_features:
            return False

        return self._write_file(
            os.path.join(self.base_path, "boot_animation_sound"),
            "1" if enabled else "0"
        )

    def get_fan_speed(self) -> Tuple[str, str]:
        """Get CPU and GPU fan speeds"""
        if "fan_speed" not in self.available_features:
            return ("", "")

        file_path = os.path.join(self.base_path, "fan_speed")

        try:
            with open(file_path, 'r') as f:
                speeds = f.read().strip()

                if "," in speeds:
                    cpu, gpu = speeds.split(",", 1)
                    return (cpu.strip(), gpu.strip())
        except Exception as e:
            log.error(f"Error reading fan speed: {e}")

        return ("0", "0")  # Fallback

    def set_fan_speed(self, cpu: int, gpu: int) -> bool:
        """Set CPU and GPU fan speeds"""
        if "fan_speed" not in self.available_features:
            return False

        # Validate values
        if not (0 <= cpu <= 100 and 0 <= gpu <= 100):
            log.error(f"Invalid fan speeds. Values must be between 0 and 100: cpu={cpu}, gpu={gpu}")
            return False

        return self._write_file(
            os.path.join(self.base_path, "fan_speed"),
            f"{cpu},{gpu}"
        )


    def get_lcd_override(self) -> str:
        """Get LCD override status"""
        if "lcd_override" not in self.available_features:
            return ""

        return self._read_file(os.path.join(self.base_path, "lcd_override"))

    def set_lcd_override(self, enabled: bool) -> bool:
        """Set LCD override status"""
        if "lcd_override" not in self.available_features:
            return False

        return self._write_file(
            os.path.join(self.base_path, "lcd_override"),
            "1" if enabled else "0"
        )

    def get_usb_charging(self) -> str:
        """Get USB charging status"""
        if "usb_charging" not in self.available_features:
            return ""

        return self._read_file(os.path.join(self.base_path, "usb_charging"))

    def set_usb_charging(self, level: int) -> bool:
        """Set USB charging level (0, 10, 20, 30)"""
        if "usb_charging" not in self.available_features:
            return False

        # Validate values
        if level not in [0, 10, 20, 30]:
            log.error(f"Invalid USB charging level. Must be 0, 10, 20, or 30: {level}")
            return False

        return self._write_file(
            os.path.join(self.base_path, "usb_charging"),
            str(level)
        )

    def get_per_zone_mode(self) -> str:
        """Get per-zone mode configuration"""
        if "per_zone_mode" not in self.available_features:
            return ""

        return self._read_file(os.path.join(paths.ACER_WMI_DEVICE_PATH, "four_zoned_kb", "per_zone_mode"))

    def set_per_zone_mode(self, zone1: str, zone2: str, zone3: str, zone4: str, brightness: int) -> bool:
        """Set per-zone mode configuration
        
        Args:
            zone1-zone4: RGB hex values (e.g., "4287f5")
            brightness: 0-100
        """
        if "per_zone_mode" not in self.available_features:
            return False

        # Validate hex values
        for i, zone in enumerate([zone1, zone2, zone3, zone4], 1):
            try:
                # Check if valid hex color
                int(zone, 16)
                if len(zone) != 6:
                    log.error(f"Invalid hex color for zone {i}: {zone}. Must be 6 characters.")
                    return False
            except ValueError:
                log.error(f"Invalid hex color for zone {i}: {zone}")
                return False

        # Validate brightness
        if not (0 <= brightness <= 100):
            log.error(f"Invalid brightness. Must be between 0 and 100: {brightness}")
            return False

        value = f"{zone1},{zone2},{zone3},{zone4},{brightness}\n"

        if self.enek5130_hid_device:
            if self._set_enek5130_per_zone_color([zone1, zone2, zone3, zone4], brightness):
                return True

        return self._write_file(
            os.path.join(paths.ACER_WMI_DEVICE_PATH, "four_zoned_kb", "per_zone_mode"),
            value
        )

    def get_four_zone_mode(self) -> str:
        """Get four-zone mode configuration"""
        if "four_zone_mode" not in self.available_features:
            return ""

        return self._read_file(os.path.join(paths.ACER_WMI_DEVICE_PATH, "four_zoned_kb", "four_zone_mode"))

    def set_four_zone_mode(self, mode: int, speed: int, brightness: int,
                           direction: int, red: int, green: int, blue: int) -> bool:
        """Set four-zone mode configuration
        
        Args:
            mode: 0-7 (lighting effect type)
            speed: 0-9 (effect speed)
            brightness: 0-100 (light intensity)
            direction: 1-2 (1=right to left, 2=left to right)
            red, green, blue: 0-255 (RGB color values)
        """
        if "four_zone_mode" not in self.available_features:
            return False

        # Validate values
        if not (0 <= mode <= 7):
            log.error(f"Invalid mode. Must be between 0 and 7: {mode}")
            return False

        if not (0 <= speed <= 9):
            log.error(f"Invalid speed. Must be between 0 and 9: {speed}")
            return False

        if not (0 <= brightness <= 100):
            log.error(f"Invalid brightness. Must be between 0 and 100: {brightness}")
            return False

        if direction not in [1, 2]:
            log.error(f"Invalid direction. Must be 1 or 2: {direction}")
            return False

        if not all(0 <= color <= 255 for color in [red, green, blue]):
            log.error(f"Invalid RGB values. Must be between 0 and 255: {red},{green},{blue}")
            return False

        value = f"{mode},{speed},{brightness},{direction},{red},{green},{blue}\n"

        if self.enek5130_hid_device:
            if mode == 0:
                if self._set_enek5130_static_color(red, green, blue, brightness):
                    return True
            elif self._set_enek5130_effect(mode, speed, brightness, direction, red, green, blue):
                return True

        return self._write_file(
            os.path.join(paths.ACER_WMI_DEVICE_PATH, "four_zoned_kb", "four_zone_mode"),
            value
        )

    def get_all_settings(self) -> Dict:
        """Get all DAMX-Daemon settings as a dictionary"""
        settings = {
            "laptop_type": self.laptop_type.name,
            "has_four_zone_kb": self.has_four_zone_kb,
            "available_features": list(self.available_features),
            "version": VERSION,
            "driver_version": self.get_driver_version(),
            "modprobe_parameter": self.current_modprobe_param
        }

        # Only include thermal profile if available
        if "thermal_profile" in self.available_features:
            settings["thermal_profile"] = {
                "current": self.get_thermal_profile(),
                "available": self.get_thermal_profile_choices()
            }
        else:
            # Include an empty entry for compatibility
            settings["thermal_profile"] = {
                "current": "",
                "available": []
            }

        # Add all other features if available
        if "backlight_timeout" in self.available_features:
            settings["backlight_timeout"] = self.get_backlight_timeout()

        if "battery_calibration" in self.available_features:
            settings["battery_calibration"] = self.get_battery_calibration()

        if "battery_limiter" in self.available_features:
            settings["battery_limiter"] = self.get_battery_limiter()

        if "boot_animation_sound" in self.available_features:
            settings["boot_animation_sound"] = self.get_boot_animation_sound()

        if "fan_speed" in self.available_features:
            cpu_fan, gpu_fan = self.get_fan_speed()
            settings["fan_speed"] = {
                "cpu": cpu_fan,
                "gpu": gpu_fan
            }

        if "lcd_override" in self.available_features:
            settings["lcd_override"] = self.get_lcd_override()

        if "usb_charging" in self.available_features:
            settings["usb_charging"] = self.get_usb_charging()

        if "per_zone_mode" in self.available_features:
            settings["per_zone_mode"] = self.get_per_zone_mode()

        if "four_zone_mode" in self.available_features:
            settings["four_zone_mode"] = self.get_four_zone_mode()

        return settings
