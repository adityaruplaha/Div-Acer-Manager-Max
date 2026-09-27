import asyncio
import os

from dbus_fast import PropertyAccess
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, dbus_property

from damx_daemon import paths
from damx_daemon.power_source import UPOWER_NAME, UPOWER_PATH, PowerSourceDetector


def set_online(value):
    with open(os.path.join(paths.POWER_SUPPLY_DIR, "ACAD", "online"), "w") as f:
        f.write(value)


def test_finds_mains_supplies_by_type(fake_system):
    assert list(PowerSourceDetector._mains_supplies()) == [os.path.join(paths.POWER_SUPPLY_DIR, "ACAD")]


def test_reports_the_mains_supply_state(fake_system):
    detector = PowerSourceDetector(manager=None)
    assert detector._is_ac_connected()
    set_online("0")
    assert not detector._is_ac_connected()


class FakeManager:
    """Records the thermal profiles the detector sets"""

    available_features = {"thermal_profile"}

    def __init__(self):
        self.profile = "performance"
        self.set_profiles = []

    def get_thermal_profile(self):
        return self.profile

    def get_thermal_profile_choices(self):
        return ["quiet", "balanced", "performance"]

    def set_thermal_profile(self, profile):
        self.profile = profile
        self.set_profiles.append(profile)
        return True


class FakeUPower(ServiceInterface):
    def __init__(self):
        super().__init__("org.freedesktop.UPower")
        self.on_battery = False

    @dbus_property(access=PropertyAccess.READ)
    def OnBattery(self) -> "b":
        return self.on_battery

    def unplug(self):
        self.on_battery = True
        self.emit_properties_changed({"OnBattery": True})


async def wait_until(condition, timeout=5):
    for _ in range(int(timeout / 0.02)):
        if condition():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached")


def test_battery_limits_the_thermal_profile(fake_system):
    manager = FakeManager()
    detector = PowerSourceDetector(manager)
    detector.check_power_source()
    set_online("0")
    detector.check_power_source()
    assert manager.set_profiles == ["balanced"]


def test_upower_signals_a_recheck(fake_system, bus_address):
    async def scenario():
        upower_bus = await MessageBus(bus_address=bus_address).connect()
        upower = FakeUPower()
        upower_bus.export(UPOWER_PATH, upower)
        await upower_bus.request_name(UPOWER_NAME)

        manager = FakeManager()
        detector = PowerSourceDetector(manager)
        detector.POLL_INTERVAL = 3600
        stop = asyncio.Event()
        running = asyncio.create_task(detector.run(stop, bus_address=bus_address))
        await wait_until(lambda: detector.bus is not None and detector.current_source is True)

        set_online("0")
        upower.unplug()
        await wait_until(lambda: detector.current_source is False)
        stop.set()
        await running
        upower_bus.disconnect()
        return manager.set_profiles

    assert asyncio.run(scenario()) == ["balanced"]


def test_polls_without_upower(fake_system, bus_address):
    async def scenario():
        detector = PowerSourceDetector(FakeManager())
        detector.POLL_INTERVAL = 0.05
        stop = asyncio.Event()
        running = asyncio.create_task(detector.run(stop, bus_address=bus_address))
        await wait_until(lambda: detector.current_source is True)
        set_online("0")
        await wait_until(lambda: detector.current_source is False)
        stop.set()
        await running
        return detector.bus

    assert asyncio.run(scenario()) is None
