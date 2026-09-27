from damx_daemon import VERSION
from damx_daemon.commands import CommandProcessor


class NoFeatures:
    available_features = set()


def test_ping():
    assert CommandProcessor(NoFeatures()).process_command("ping", {}) == {"success": True}


def test_version():
    response = CommandProcessor(NoFeatures()).process_command("get_version", {})
    assert response == {"success": True, "data": {"version": VERSION}}


def test_unknown_command():
    response = CommandProcessor(NoFeatures()).process_command("nope", {})
    assert response == {"success": False, "error": "Unknown command: nope"}


def test_setting_an_unavailable_feature_is_refused():
    response = CommandProcessor(NoFeatures()).process_command("set_fan_speed", {"cpu": 50, "gpu": 50})
    assert response == {"success": False, "error": "Fan speed control is not supported on this device"}
