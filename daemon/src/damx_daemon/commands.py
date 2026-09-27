"""The commands the GUI sends to the daemon"""

import traceback
from typing import Dict

from . import VERSION
from .logs import log
from .manager import DAMXManager


class CommandProcessor:
    """Runs the GUI's commands against the manager, independently of how they arrive"""

    def __init__(self, manager: DAMXManager):
        self.manager = manager

    def process_command(self, command: str, params: Dict) -> Dict:
        """Process a command from the client"""
        log.debug(f"Processing command: {command} with params: {params}")

        try:
            if command == "ping":
                # Used by the GUI to check that its connection is alive
                return {"success": True}

            elif command == "get_all_settings":
                settings = self.manager.get_all_settings()
                return {
                    "success": True,
                    "data": settings
                }

            elif command == "get_thermal_profile":
                # Check if feature is available
                if "thermal_profile" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Thermal profile is not supported on this device"
                    }

                profile = self.manager.get_thermal_profile()
                choices = self.manager.get_thermal_profile_choices()
                return {
                    "success": True,
                    "data": {
                        "current": profile,
                        "available": choices
                    }
                }

            elif command == "set_thermal_profile":
                # Check if feature is available
                if "thermal_profile" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Thermal profile is not supported on this device"
                    }

                profile = params.get("profile", "")
                success = self.manager.set_thermal_profile(profile)
                return {
                    "success": success,
                    "data": {"profile": profile} if success else None,
                    "error": "Failed to set thermal profile" if not success else None
                }

            elif command == "set_backlight_timeout":
                # Check if feature is available
                if "backlight_timeout" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Backlight timeout is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_backlight_timeout(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set backlight timeout" if not success else None
                }

            elif command == "set_battery_calibration":
                # Check if feature is available
                if "battery_calibration" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Battery calibration is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_battery_calibration(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set battery calibration" if not success else None
                }

            elif command == "set_battery_limiter":
                # Check if feature is available
                if "battery_limiter" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Battery limiter is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_battery_limiter(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set battery limiter" if not success else None
                }

            elif command == "set_boot_animation_sound":
                # Check if feature is available
                if "boot_animation_sound" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Boot animation sound is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_boot_animation_sound(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set boot animation sound" if not success else None
                }

            elif command == "set_fan_speed":
                # Check if feature is available
                if "fan_speed" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Fan speed control is not supported on this device"
                    }

                cpu = params.get("cpu", 0)
                gpu = params.get("gpu", 0)
                success = self.manager.set_fan_speed(cpu, gpu)
                return {
                    "success": success,
                    "data": {"cpu": cpu, "gpu": gpu} if success else None,
                    "error": "Failed to set fan speed" if not success else None
                }

            elif command == "set_lcd_override":
                # Check if feature is available
                if "lcd_override" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "LCD override is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_lcd_override(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set LCD override" if not success else None
                }

            elif command == "set_usb_charging":
                # Check if feature is available
                if "usb_charging" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "USB charging control is not supported on this device"
                    }

                level = params.get("level", 0)
                success = self.manager.set_usb_charging(level)
                return {
                    "success": success,
                    "data": {"level": level} if success else None,
                    "error": "Failed to set USB charging" if not success else None
                }

            elif command == "set_per_zone_mode":
                # Check if feature is available
                if "per_zone_mode" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Per-zone keyboard mode is not supported on this device"
                    }

                zone1 = params.get("zone1", "000000")
                zone2 = params.get("zone2", "000000")
                zone3 = params.get("zone3", "000000")
                zone4 = params.get("zone4", "000000")
                brightness = params.get("brightness", 100)
                success = self.manager.set_per_zone_mode(zone1, zone2, zone3, zone4, brightness)
                return {
                    "success": success,
                    "data": {
                        "zone1": zone1,
                        "zone2": zone2,
                        "zone3": zone3,
                        "zone4": zone4,
                        "brightness": brightness
                    } if success else None,
                    "error": "Failed to set per-zone mode" if not success else None
                }

            elif command == "set_four_zone_mode":
                # Check if feature is available
                if "four_zone_mode" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Four-zone keyboard mode is not supported on this device"
                    }

                mode = params.get("mode", 0)
                speed = params.get("speed", 0)
                brightness = params.get("brightness", 100)
                direction = params.get("direction", 1)
                red = params.get("red", 0)
                green = params.get("green", 0)
                blue = params.get("blue", 0)
                success = self.manager.set_four_zone_mode(mode, speed, brightness, direction, red, green, blue)
                return {
                    "success": success,
                    "data": {
                        "mode": mode,
                        "speed": speed,
                        "brightness": brightness,
                        "direction": direction,
                        "red": red,
                        "green": green,
                        "blue": blue
                    } if success else None,
                    "error": "Failed to set four-zone mode" if not success else None
                }

            elif command == "get_supported_features":
                return {
                    "success": True,
                    "data": {
                        "available_features": list(self.manager.available_features),
                        "laptop_type": self.manager.laptop_type.name,
                        "has_four_zone_kb": self.manager.has_four_zone_kb
                    }
                }

            elif command == "get_version":
                return {
                    "success": True,
                    "data": {
                        "version": VERSION
                    }
                }
            
            # Force Models and Features
            elif command == "force_nitro_model":
                # Force Nitro model into driver
                success = self.manager._force_model_nitro()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully forced Nitro model into driver"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to force Nitro model into driver"
                    }
                
            elif command == "force_predator_model":
                # Force Predator model into driver
                success = self.manager._force_model_predator()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully forced Predator model into driver"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to force Predator model into driver (Model may not support it)"
                    }

            elif command == "force_enable_all":
                # Force Enable All Features into driver
                success = self.manager._force_enable_all()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully forced all features into driver"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to force all features into driver (Model may not support it)"
                    }
                
            elif command == "get_modprobe_parameter":
                return {
                    "success": True,
                    "data": {
                        "parameter": self.manager.get_modprobe_parameter()
                    }
                }

            # Force Model and Parameters Permanantly
            elif command == "set_modprobe_parameter_predator":
                # Don't get parameter from params, use the specific value
                success = self.manager.set_modprobe_parameter("predator_v4")
                if success:
                    return {
                        "success": True,
                        "data": {"parameter": "predator_v4"}
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to set modprobe parameter to predator_v4"
                    }

            elif command == "set_modprobe_parameter_nitro":
                success = self.manager.set_modprobe_parameter("nitro_v4")
                if success:
                    return {
                        "success": True,
                        "data": {"parameter": "nitro_v4"}
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to set modprobe parameter to nitro_v4"
                    }

            elif command == "set_modprobe_parameter_enable_all":
                success = self.manager.set_modprobe_parameter("enable_all")
                if success:
                    return {
                        "success": True,
                        "data": {"parameter": "enable_all"}
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to set modprobe parameter to enable_all"
                    }

            elif command == "remove_modprobe_parameter":
                success = self.manager._remove_modprobe_parameter()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully removed modprobe parameter"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to remove modprobe parameter"
                    }
            
            elif command == "restart_daemon":
                # Force Nitro model into driver
                success = self.manager._restart_daemon()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully restarted DAMX daemon"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to Restart DAMX daemon (Check logs for details)"
                    }           

            elif command == "restart_drivers_and_daemon":
                # Restart linuwu-sense driver and DAMX daemon service
                success = self.manager._restart_drivers_and_daemon()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully restarted drivers and daemon"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to restart drivers and daemon"
                    }
            else:
                return {
                    "success": False,
                    "error": f"Unknown command: {command}"
                }

        except Exception as e:
            log.error(f"Error processing command {command}: {e}")
            log.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
