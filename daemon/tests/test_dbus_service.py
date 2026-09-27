"""Run the D-Bus service on a private bus, with a fake polkit authority"""

import asyncio
import json
import shutil
import subprocess

import pytest
from dbus_fast import Message, MessageFlag, MessageType
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

from damx_daemon import VERSION
from damx_daemon.commands import CommandProcessor
from damx_daemon.dbus_service import (
    ACTION_CHANGE_SETTINGS,
    ACTION_MANAGE_DRIVER,
    BUS_NAME,
    ERROR_NOT_AUTHORIZED,
    INTERFACE,
    OBJECT_PATH,
    DBusService,
    required_action,
)

pytestmark = pytest.mark.skipif(shutil.which("dbus-daemon") is None, reason="needs dbus-daemon")


class NoFeatures:
    available_features = set()


class FakeAuthority(ServiceInterface):
    """Stands in for polkit, authorising only the actions in `allowed`"""

    def __init__(self, allowed):
        super().__init__("org.freedesktop.PolicyKit1.Authority")
        self.allowed = allowed
        self.checks = []

    @method()
    def CheckAuthorization(self, subject: "(sa{sv})", action_id: "s", details: "a{ss}",
                           flags: "u", cancellation_id: "s") -> "(bba{ss})":
        kind, subject_details = subject
        self.checks.append((kind, subject_details["name"].value, action_id, flags))
        return [action_id in self.allowed, False, {}]


@pytest.fixture
def bus_address():
    daemon = subprocess.Popen(
        ["dbus-daemon", "--session", "--nofork", "--print-address"],
        stdout=subprocess.PIPE, text=True)
    address = daemon.stdout.readline().strip()
    yield address
    daemon.terminate()
    daemon.wait()


async def serve_and_call(bus_address, allowed, calls):
    """Start the service and a fake authority, then run Execute for each (command, params)"""
    authority_bus = await MessageBus(bus_address=bus_address).connect()
    authority = FakeAuthority(allowed)
    authority_bus.export("/org/freedesktop/PolicyKit1/Authority", authority)
    await authority_bus.request_name("org.freedesktop.PolicyKit1")

    stop = asyncio.Event()
    service = DBusService(CommandProcessor(NoFeatures()), bus_address=bus_address)
    serving = asyncio.create_task(service.run(stop))

    client = await MessageBus(bus_address=bus_address).connect()
    for _ in range(100):
        reply = await client.call(Message(
            destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
            interface="org.freedesktop.DBus", member="NameHasOwner", signature="s", body=[BUS_NAME]))
        if reply.body[0]:
            break
        await asyncio.sleep(0.01)

    replies = []
    for command, params in calls:
        replies.append(await client.call(Message(
            destination=BUS_NAME, path=OBJECT_PATH, interface=INTERFACE, member="Execute",
            signature="ss", body=[command, json.dumps(params)],
            flags=MessageFlag.ALLOW_INTERACTIVE_AUTHORIZATION)))

    stop.set()
    await serving
    client.disconnect()
    authority_bus.disconnect()
    return replies, authority.checks, client.unique_name


def run(coroutine):
    return asyncio.run(coroutine)


def test_required_actions():
    assert required_action("get_all_settings") is None
    assert required_action("set_fan_speed") == ACTION_CHANGE_SETTINGS
    assert required_action("force_nitro_model") == ACTION_MANAGE_DRIVER
    assert required_action("something_new") == ACTION_CHANGE_SETTINGS


def test_read_only_commands_need_no_authorization(bus_address):
    replies, checks, _ = run(serve_and_call(bus_address, set(), [("get_version", {})]))
    assert json.loads(replies[0].body[0]) == {"success": True, "data": {"version": VERSION}}
    assert checks == []


def test_authorized_commands_are_run(bus_address):
    replies, checks, caller = run(serve_and_call(
        bus_address, {ACTION_CHANGE_SETTINGS}, [("set_fan_speed", {"cpu": 50, "gpu": 50})]))
    assert json.loads(replies[0].body[0])["error"] == "Fan speed control is not supported on this device"
    assert checks == [("system-bus-name", caller, ACTION_CHANGE_SETTINGS, 1)]


def test_unauthorized_commands_are_refused(bus_address):
    replies, checks, _ = run(serve_and_call(
        bus_address, {ACTION_CHANGE_SETTINGS}, [("restart_daemon", {})]))
    assert replies[0].message_type == MessageType.ERROR
    assert replies[0].error_name == ERROR_NOT_AUTHORIZED
    assert [check[2] for check in checks] == [ACTION_MANAGE_DRIVER]


def test_invalid_params(bus_address):
    replies, _, _ = run(serve_and_call(bus_address, set(), [("get_version", [1, 2])]))
    assert json.loads(replies[0].body[0]) == {"success": False, "error": "Invalid JSON format"}


def test_no_reply_is_sent_once_the_bus_is_closed(bus_address):
    async def scenario():
        service = DBusService(CommandProcessor(NoFeatures()), bus_address=bus_address)
        service.bus = await MessageBus(bus_address=bus_address).connect()
        service.bus.disconnect()
        await asyncio.sleep(0.05)
        service._reply(Message(destination=BUS_NAME, path=OBJECT_PATH, member="Execute", serial=1), {"success": True})

    run(scenario())
