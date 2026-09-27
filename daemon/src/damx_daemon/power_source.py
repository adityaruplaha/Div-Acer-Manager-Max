"""Detection of the power source, and the thermal profile limits on battery

The source is read from sysfs. UPower's OnBattery property, which changes
when an adapter is plugged in or out, says when to read it again, so that
the daemon need not poll; without UPower it falls back to polling.
"""

import asyncio
import os
import subprocess
import threading
from typing import Optional

from dbus_fast import BusType
from dbus_fast.aio import MessageBus

from . import paths
from .logs import log

UPOWER_NAME = "org.freedesktop.UPower"
UPOWER_PATH = "/org/freedesktop/UPower"


class PowerSourceDetector:
    """Detects power source and manages automatic mode switching"""

    # Seconds between checks when UPower is not available
    POLL_INTERVAL = 5

    def __init__(self, manager):
        self.manager = manager
        self.current_source = None
        self.bus = None
        self._lock = threading.Lock()

        self.possible_power_supply_paths = [
            os.path.join(paths.POWER_SUPPLY_DIR, name, "online")
            for name in ("AC", "ACAD", "ADP1", "AC0")
        ]

    async def run(self, stop: asyncio.Event, bus_type: BusType = BusType.SYSTEM, bus_address: str = None):
        """Check the power source now and whenever it may have changed, until stop is set"""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.check_power_source)

        try:
            if await self._watch_upower(bus_type, bus_address):
                log.info("Watching UPower for power source changes")
                await stop.wait()
                return

            log.info(f"UPower is not available, checking the power source every {self.POLL_INTERVAL} seconds")
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), self.POLL_INTERVAL)
                except TimeoutError:
                    await loop.run_in_executor(None, self.check_power_source)
        finally:
            if self.bus:
                self.bus.disconnect()
                self.bus = None

    async def _watch_upower(self, bus_type: BusType, bus_address: str) -> bool:
        """Subscribe to changes of UPower's OnBattery, returning whether that worked"""
        try:
            self.bus = await MessageBus(bus_type=bus_type, bus_address=bus_address).connect()
            introspection = await self.bus.introspect(UPOWER_NAME, UPOWER_PATH)
            proxy = self.bus.get_proxy_object(UPOWER_NAME, UPOWER_PATH, introspection)
            proxy.get_interface("org.freedesktop.DBus.Properties").on_properties_changed(self._on_upower_changed)
            return True
        except Exception as e:
            log.debug(f"Could not watch UPower: {e}")
            if self.bus:
                self.bus.disconnect()
                self.bus = None
            return False

    def _on_upower_changed(self, interface: str, changed: dict, invalidated: list):
        if interface == UPOWER_NAME and "OnBattery" in changed:
            asyncio.get_running_loop().run_in_executor(None, self.check_power_source)

    def check_power_source(self):
        """Check current power source and adjust settings if needed"""
        with self._lock:
            is_plugged_in = self._is_ac_connected()

            # Only take action if power state changed
            if is_plugged_in is not None and is_plugged_in != self.current_source:
                self.current_source = is_plugged_in
                self._handle_power_change(is_plugged_in)

    def _is_ac_connected(self) -> Optional[bool]:
        """Check if AC power is connected"""
        online_statuses = []

        try:
            # Discover AC adapters by their sysfs type rather than their name.
            for entry in os.scandir(paths.POWER_SUPPLY_DIR):
                try:
                    supply_type = self._read_status(os.path.join(entry.path, "type"))
                    if supply_type != "Mains":
                        continue

                    status = self._read_status(os.path.join(entry.path, "online"))
                    if status in ("0", "1"):
                        online_statuses.append(status == "1")
                except OSError as e:
                    log.warning(f"Could not read power supply status at {entry.path}: {e}")
        except OSError as e:
            log.debug(f"Could not scan power supplies: {e}")

        if online_statuses:
            return any(online_statuses)

        try:
            # Keep compatibility with systems that expose online without type.
            for path in self.possible_power_supply_paths:
                if os.path.exists(path):
                    status = self._read_status(path)
                    if status in ("0", "1"):
                        return status == "1"

            # If no power supply file is found, try command-line tools
            upower_status = self._check_using_upower()
            return upower_status if upower_status is not None else self._check_using_acpi()

        except Exception as e:
            log.error(f"Error checking power status: {e}")
            return None

    @staticmethod
    def _read_status(path: str) -> str:
        with open(path, "r") as status_file:
            return status_file.read().strip()

    def _check_using_upower(self) -> Optional[bool]:
        """Check power status using upower"""
        try:
            result = subprocess.run(
                ["upower", "-i", "/org/freedesktop/UPower/devices/line_power_AC"],
                capture_output=True,
                text=True,
                check=True
            )
            output = result.stdout.lower()
            if "online: yes" in output:
                return True
            if "online: no" in output:
                return False
            return None
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log.warning(f"upower check failed: {e}")
            return None

    def _check_using_acpi(self) -> Optional[bool]:
        """Check power status using acpi"""
        try:
            result = subprocess.run(
                ["acpi", "-a"],
                capture_output=True,
                text=True,
                check=True
            )
            output = result.stdout.lower()
            if "on-line" in output:
                return True
            if "off-line" in output:
                return False
            return None
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log.warning(f"acpi check failed: {e}")
            return None

    def _handle_power_change(self, is_plugged_in: bool):
        """Handle power source changes"""
        if not hasattr(self.manager, 'available_features') or "thermal_profile" not in self.manager.available_features:
            return

        current_profile = self.manager.get_thermal_profile()
        available_profiles = self.manager.get_thermal_profile_choices()

        if is_plugged_in:
            # On AC power - no restrictions
            log.info("Switched to AC power")
        else:
            # On battery power - enforce balanced or eco mode
            log.info("Switched to battery power")

            if current_profile not in ["balanced", "quiet", "power-saver"]:
                # If current profile isn't battery-friendly, switch to balanced
                if "balanced" in available_profiles:
                    log.info("Auto-switching to balanced mode for battery power")
                    self.manager.set_thermal_profile("balanced")
                elif "quiet" in available_profiles:
                    log.info("Auto-switching to quiet mode for battery power")
                    self.manager.set_thermal_profile("quiet")
                elif "power-saver" in available_profiles:
                    log.info("Auto-switching to power-saver mode for battery power")
                    self.manager.set_thermal_profile("power-saver")
                else:
                    log.warning("No battery-friendly thermal profile available")