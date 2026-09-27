import os

from damx_daemon import paths
from damx_daemon.power_source import PowerSourceDetector


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
