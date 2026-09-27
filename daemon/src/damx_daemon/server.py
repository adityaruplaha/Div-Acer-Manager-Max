"""Unix socket server for IPC with the GUI client"""

import codecs
import json
import os
import select
import socket
import threading
import traceback
from typing import Dict

from . import VERSION, paths
from .logs import log
from .manager import DAMXManager


class DaemonServer:
    """Unix Socket server for IPC with the GUI client"""

    # Limits on what a client can make the daemon hold
    MAX_CLIENTS = 16
    MAX_REQUEST_SIZE = 64 * 1024
    # How long to wait for the rest of a request split across several reads
    CONTINUATION_TIMEOUT = 0.1

    def __init__(self, manager: DAMXManager):
        self.manager = manager
        self.socket = None
        self.running = False
        self.clients = []

    def start(self):
        """Start the Unix socket server"""
        # Remove socket if it already exists
        try:
            if os.path.exists(paths.SOCKET_PATH):
                os.unlink(paths.SOCKET_PATH)
        except OSError as e:
            log.error(f"Failed to remove existing socket: {e}")
            return False

        try:
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.bind(paths.SOCKET_PATH)
            # Ensure socket permissions allow non-root access
            os.chmod(paths.SOCKET_PATH, 0o666)
            self.socket.listen(5)
            self.socket.settimeout(1)  # 1 second timeout for clean shutdown
            self.running = True

            log.info(f"Server listening on {paths.SOCKET_PATH}")

            # Accept connections in a loop
            while self.running:
                try:
                    client, _ = self.socket.accept()

                    # Forget clients whose connections have closed
                    self.clients = [(c, t) for c, t in self.clients if t.is_alive()]
                    if len(self.clients) >= self.MAX_CLIENTS:
                        log.warning(f"Refusing connection: {self.MAX_CLIENTS} clients already connected")
                        client.close()
                        continue

                    client_thread = threading.Thread(target=self.handle_client, args=(client,))
                    client_thread.daemon = True
                    client_thread.start()
                    self.clients.append((client, client_thread))
                except socket.timeout:
                    # This is expected due to the timeout
                    continue
                except Exception as e:
                    if self.running:  # Only log if not shutting down
                        log.error(f"Error accepting connection: {e}")

            return True

        except Exception as e:
            log.error(f"Failed to start server: {e}")
            return False

    def stop(self):
        """Stop the server and clean up"""
        log.info("Stopping server...")
        self.running = False
    
        # Close all client connections
        for client, _ in self.clients:
            try:
                client.close()
            except OSError:
                pass
    
        # Close server socket
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
    
        # Clean up socket file
        self.cleanup_socket()

    def cleanup_socket(self):
        """Clean up the socket file"""
        try:
            if os.path.exists(paths.SOCKET_PATH):
                os.unlink(paths.SOCKET_PATH)
                log.info(f"Removed socket file: {paths.SOCKET_PATH}")
        except Exception as e:
            log.error(f"Failed to remove socket file: {e}")


    def _more_data_pending(self, client_socket) -> bool:
        """Whether more of a request arrives within CONTINUATION_TIMEOUT"""
        readable, _, _ = select.select([client_socket], [], [], self.CONTINUATION_TIMEOUT)
        return bool(readable)

    @staticmethod
    def _send(client_socket, response: Dict):
        client_socket.sendall(json.dumps(response).encode('utf-8'))

    def handle_client(self, client_socket):
        """Handle communication with a client

        Requests are JSON objects with no delimiter between them. A request
        may arrive split across several reads, so data is buffered until a
        complete object decodes, up to MAX_REQUEST_SIZE.
        """
        decoder = json.JSONDecoder()
        utf8 = codecs.getincrementaldecoder('utf-8')()
        buffer = ""
        try:
            while self.running:
                data = client_socket.recv(4096)
                if not data:
                    break

                try:
                    buffer += utf8.decode(data)
                except UnicodeDecodeError:
                    log.error("Invalid UTF-8 received")
                    self._send(client_socket, {"success": False, "error": "Invalid JSON format"})
                    utf8.reset()
                    buffer = ""
                    continue

                while buffer.strip():
                    buffer = buffer.lstrip()
                    try:
                        request, end = decoder.raw_decode(buffer)
                    except json.JSONDecodeError:
                        if len(buffer) < self.MAX_REQUEST_SIZE and self._more_data_pending(client_socket):
                            break  # the rest of the request is still arriving
                        log.error("Invalid JSON received")
                        self._send(client_socket, {"success": False, "error": "Invalid JSON format"})
                        buffer = ""
                        break
                    buffer = buffer[end:]

                    if not isinstance(request, dict):
                        self._send(client_socket, {"success": False, "error": "Request must be a JSON object"})
                        continue

                    try:
                        command = request.get("command", "")
                        params = request.get("params") or {}
                        self._send(client_socket, self.process_command(command, params))
                    except Exception as e:
                        log.error(f"Error processing request: {e}")
                        log.error(traceback.format_exc())
                        self._send(client_socket, {"success": False, "error": str(e)})

        except Exception as e:
            if self.running:  # Only log if not shutting down
                log.error(f"Client connection error: {e}")
        finally:
            try:
                client_socket.close()
            except OSError:
                pass

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
