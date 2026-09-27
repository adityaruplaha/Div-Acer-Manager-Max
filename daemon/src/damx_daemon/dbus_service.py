"""The daemon's D-Bus service, through which the GUI sends its commands

The GUI calls Execute(command, params) with the same commands and JSON
parameters that the old socket protocol carried, and gets the same JSON
response back. Commands that change anything are authorised with polkit for
the calling process, as power-profiles-daemon does.
"""

import asyncio
import json

from dbus_fast import BusType, Message, MessageFlag, MessageType, RequestNameReply, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

from .commands import CommandProcessor
from .logs import log

BUS_NAME = "io.github.PXDiv.DAMX"
OBJECT_PATH = "/io/github/PXDiv/DAMX"
INTERFACE = "io.github.PXDiv.DAMX"
ERROR_NOT_AUTHORIZED = "io.github.PXDiv.DAMX.Error.NotAuthorized"

# polkit actions, defined in io.github.PXDiv.DAMX.policy
ACTION_CHANGE_SETTINGS = "io.github.PXDiv.DAMX.change-settings"
ACTION_MANAGE_DRIVER = "io.github.PXDiv.DAMX.manage-driver"

# Commands that only read state, which any local user may run
READ_ONLY_COMMANDS = frozenset({
    "ping",
    "get_all_settings",
    "get_thermal_profile",
    "get_supported_features",
    "get_version",
    "get_modprobe_parameter",
})

# Commands that reload the kernel module, change its options or restart the daemon
DRIVER_COMMANDS = frozenset({
    "force_nitro_model",
    "force_predator_model",
    "force_enable_all",
    "set_modprobe_parameter_predator",
    "set_modprobe_parameter_nitro",
    "set_modprobe_parameter_enable_all",
    "remove_modprobe_parameter",
    "restart_daemon",
    "restart_drivers_and_daemon",
})


def required_action(command: str):
    """The polkit action a command needs, or None if it only reads state"""
    if command in READ_ONLY_COMMANDS:
        return None
    if command in DRIVER_COMMANDS:
        return ACTION_MANAGE_DRIVER
    return ACTION_CHANGE_SETTINGS


class DamxInterface(ServiceInterface):
    """Describes the interface for introspection

    Calls to Execute are answered by DBusService._handle_message instead,
    which, unlike a method here, can see the caller's bus name for polkit.
    """

    def __init__(self):
        super().__init__(INTERFACE)

    @method()
    def Execute(self, command: "s", params: "s") -> "s":
        raise NotImplementedError


class DBusService:
    """Owns the bus name and answers Execute calls"""

    def __init__(self, processor: CommandProcessor, bus_type: BusType = BusType.SYSTEM,
                 bus_address: str = None, authorize: bool = True):
        self.processor = processor
        self.bus_type = bus_type
        self.bus_address = bus_address
        self.authorize = authorize
        self.bus = None

    async def run(self, stop: asyncio.Event):
        """Serve until stop is set"""
        self.bus = await MessageBus(bus_type=self.bus_type, bus_address=self.bus_address).connect()
        self.bus.export(OBJECT_PATH, DamxInterface())
        self.bus.add_message_handler(self._handle_message)

        reply = await self.bus.request_name(BUS_NAME)
        if reply not in (RequestNameReply.PRIMARY_OWNER, RequestNameReply.ALREADY_OWNER):
            raise RuntimeError(f"Could not own {BUS_NAME} on the bus: {reply.name}")
        log.info(f"Serving {BUS_NAME} on the D-Bus {self.bus_type.name.lower()} bus")

        try:
            await stop.wait()
        finally:
            self.bus.disconnect()

    def _handle_message(self, msg: Message):
        if (msg.message_type == MessageType.METHOD_CALL and msg.path == OBJECT_PATH
                and msg.interface == INTERFACE and msg.member == "Execute" and msg.signature == "ss"):
            asyncio.get_running_loop().create_task(self._execute(msg))
            return True
        return None

    async def _execute(self, msg: Message):
        command, params_json = msg.body
        try:
            params = json.loads(params_json) if params_json else {}
            if not isinstance(params, dict):
                raise ValueError("params must be a JSON object")
        except ValueError:
            self._reply(msg, {"success": False, "error": "Invalid JSON format"})
            return

        action = required_action(command)
        if action and not await self._is_authorized(msg, action):
            log.warning(f"Refused {command} from {msg.sender}: not authorized for {action}")
            self.bus.send(Message.new_error(msg, ERROR_NOT_AUTHORIZED, f"Not authorized to run {command}"))
            return

        response = await asyncio.get_running_loop().run_in_executor(
            None, self.processor.process_command, command, params)
        self._reply(msg, response)

    def _reply(self, msg: Message, response: dict):
        # A command that stops the daemon can finish after the bus is closed
        if not self.bus.connected:
            log.debug(f"Not answering {msg.sender}: the bus connection is closed")
            return
        self.bus.send(Message.new_method_return(msg, "s", [json.dumps(response)]))

    async def _is_authorized(self, msg: Message, action: str) -> bool:
        """Ask polkit whether the process that sent msg may perform action"""
        if not self.authorize:
            return True

        # Let polkit ask for a password when the caller allows it
        flags = 1 if msg.flags & MessageFlag.ALLOW_INTERACTIVE_AUTHORIZATION else 0
        reply = await self.bus.call(Message(
            destination="org.freedesktop.PolicyKit1",
            path="/org/freedesktop/PolicyKit1/Authority",
            interface="org.freedesktop.PolicyKit1.Authority",
            member="CheckAuthorization",
            signature="(sa{sv})sa{ss}us",
            body=[["system-bus-name", {"name": Variant("s", msg.sender)}], action, {}, flags, ""],
        ))
        if reply.message_type == MessageType.ERROR:
            log.error(f"polkit check for {action} failed: {reply.error_name}: {reply.body}")
            return False
        is_authorized, _is_challenge, _details = reply.body[0]
        return bool(is_authorized)

