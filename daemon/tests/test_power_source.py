import os

from damx_daemon import paths
from damx_daemon.power_source import PowerSourceDetector


def set_online(value):
    with open(os.path.join(paths.POWER_SUPPLY_DIR, "ACAD", "online"), "w") as f:
        f.write(value)


def test_finds_mains_supplies_by_type(fake_system):
    set_online("0")
    adapter = os.path.join(paths.POWER_SUPPLY_DIR, "ADP0")
    os.makedirs(adapter)
    for name, value in {"type": "Mains", "online": "1"}.items():
        with open(os.path.join(adapter, name), "w") as f:
            f.write(value + "\n")
    assert PowerSourceDetector(manager=None)._is_ac_connected()


def test_reports_the_mains_supply_state(fake_system):
    detector = PowerSourceDetector(manager=None)
    assert detector._is_ac_connected()
    set_online("0")
    assert not detector._is_ac_connected()
