"""Detection of the power source, and the thermal profile limits on battery

The source is read from sysfs. UPower's OnBattery property, which changes
when an adapter is plugged in or out, says when to read it again, so that
the daemon need not poll; without UPower it falls back to polling.
"""

import asyncio
import glob
import os
import subprocess
import threading

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
            if is_plugged_in != self.current_source:
                self.current_source = is_plugged_in
                self._handle_power_change(is_plugged_in)

    @staticmethod
    def _mains_supplies():
        """Power supplies the kernel reports as mains adapters, whatever their name (AC, ACAD, ADP1, ...)"""
        for supply in sorted(glob.glob(os.path.join(paths.POWER_SUPPLY_DIR, "*"))):
            try:
                with open(os.path.join(supply, "type"), 'r') as f:
                    if f.read().strip() == "Mains":
                        yield supply
            except OSError:
                continue

    def _is_ac_connected(self) -> bool:
        """Check if AC power is connected"""
        try:
            online_files = [os.path.join(supply, "online") for supply in self._mains_supplies()]
            online_files = [path for path in online_files if os.path.exists(path)]
            if online_files:
                for path in online_files:
                    with open(path, 'r') as f:
                        if f.read().strip() == "1":
                            return True
                return False

            # If the kernel exposes no mains supply, try command-line tools
            return self._check_using_upower() or self._check_using_acpi()

        except Exception as e:
            log.error(f"Error checking power status: {e}")
            return False

    def _check_using_upower(self) -> bool:
        """Check power status using upower"""
        try:
            result = subprocess.run(
                ["upower", "-i", "/org/freedesktop/UPower/devices/line_power_AC"],
                capture_output=True,
                text=True,
                check=True
            )
            return "online: yes" in result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log.error(f"upower check failed: {e}")
            return False

    def _check_using_acpi(self) -> bool:
        """Check power status using acpi"""
        try:
            result = subprocess.run(
                ["acpi", "-a"],
                capture_output=True,
                text=True,
                check=True
            )
            return "on-line" in result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log.error(f"acpi check failed: {e}")
            return False

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