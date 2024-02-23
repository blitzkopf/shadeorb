import asyncio
import logging

from collections.abc import Callable
from dataclasses import replace
from typing import Any, TypeVar

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.backends.service import BleakGATTCharacteristic, BleakGATTServiceCollection
from bleak.exc import BleakDBusError
from bleak_retry_connector import BLEAK_RETRY_EXCEPTIONS as BLEAK_EXCEPTIONS
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BleakError,
    BleakNotFoundError,
    establish_connection,
    retry_bluetooth_connection_error,
)
from .const import (
    POSSIBLE_READ_CHARACTERISTIC_UUIDS,
    POSSIBLE_WRITE_CHARACTERISTIC_UUIDS,
)
from .exceptions import CharacteristicMissingError
from .models import ORBState
from .protocol import ORBProtocol

BLEAK_BACKOFF_TIME = 0.25

DISCONNECT_DELAY = 600

_LOGGER = logging.getLogger(__name__)

DEFAULT_ATTEMPTS = 3


class ORB:
    def __init__(
        self, ble_device: BLEDevice,
        cmd_prefix: str,
        advertisement_data: AdvertisementData | None = None
    ) -> None:
        self._ble_device = ble_device
        self._cmd_prefix = bytes.fromhex(cmd_prefix.translate({ord(i): None for i in ' -:'}))
        self._advertisement_data = advertisement_data
        self._operation_lock = asyncio.Lock()
        self._state = ORBState()
        self._connect_lock: asyncio.Lock = asyncio.Lock()
        self._read_char: BleakGATTCharacteristic | None = None
        self._write_char: BleakGATTCharacteristic | None = None
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._client: BleakClientWithServiceCache | None = None
        self._expected_disconnect = False
        self.loop = asyncio.get_running_loop()
        self._callbacks: list[Callable[[ORBState], None]] = []
        #self._model_data: ORBModel | None = None
        #self._protocol: PROTOCOL_TYPES | None = None
        self._protocol= ORBProtocol()

        self._resolve_protocol_event = asyncio.Event()
    def set_ble_device_and_advertisement_data(
        self, ble_device: BLEDevice, advertisement_data: AdvertisementData
    ) -> None:
        """Set the ble device."""
        self._ble_device = ble_device
        self._advertisement_data = advertisement_data

    @property
    def address(self) -> str:
        """Return the address."""
        return self._ble_device.address

    @property
    def _address(self) -> str:
        """Return the address."""
        return self._ble_device.address

    # @property
    # def model_data(self) -> LEDBLEModel:
    #     """Return the model data."""
    #     assert self._model_data is not None  # nosec
    #     return self._model_data

    @property
    def name(self) -> str:
        """Get the name of the device."""
        return self._ble_device.name or self._ble_device.address

    @property
    def rssi(self) -> int | None:
        """Get the rssi of the device."""
        if self._advertisement_data:
            return self._advertisement_data.rssi
        return None

    @property
    def state(self) -> ORBState:
        """Return the state."""
        return self._state

    @property
    def on(self) -> bool:
        _LOGGER.debug("%s: Getting power %s", self.name, self._state.power)
        return self._state.power

    @property
    def effect_list(self):
        """Return the list of supported effects."""
        return ['0','1','2','3','4','5','6','7']

    async def update(self) -> None:
        """Update the Orb."""
        await self._ensure_connected()
        #await self._resolve_protocol()
        _LOGGER.debug("%s: Updating", self.name)
        assert self._protocol is not None  # nosec
        # I have no idea how to get the state of the orb
        #command = self._protocol.construct_state_query()
        #await self._send_command([command])
        ## YS: this really should not be here
        self._fire_callbacks()


    async def turn_on(self) -> None:
        """Turn on."""
        _LOGGER.debug("%s: Turn on", self.name)
        assert self._protocol is not None  # nosec
        await self._send_command(self._protocol.construct_state_change(self._cmd_prefix,True))
        self._state = replace(self._state, power=True)
        self._fire_callbacks()

    async def turn_off(self) -> None:
        """Turn off."""
        _LOGGER.debug("%s: Turn off", self.name)
        assert self._protocol is not None  # nosec
        await self._send_command(self._protocol.construct_state_change(self._cmd_prefix,False))
        self._state = replace(self._state, power=False)
        self._fire_callbacks()

    async def set_edge_rgbw(
        self, rgbw: tuple[int, int, int,int], brightness: int | None = None
    ) -> None:
        """Set rgb."""
        _LOGGER.debug("%s: Set rgb: %s brightness: %s", self.name, rgbw, brightness)
        for value in rgbw:
            if not 0 <= value <= 4095:
                raise ValueError("Value {} is outside the valid range of 0-4095")
        # if brightness is not None:
        #     rgb = self._calculate_brightness(rgb, brightness)
        _LOGGER.debug("%s: Set rgbw after brightness: %s", self.name, rgbw)
        assert self._protocol is not None  # nosec

        command = self._protocol.construct_levels_change(
            self._cmd_prefix,
            *self._state.inner_warm_cold,
            *self._state.outer_warm_cold,
            rgbw[3], *rgbw[0:3], 
        )
        print('Command:',command.hex())
        await self._send_command(command)
        self._state = replace(
            self._state,
            edge_rgbw=rgbw,
            #preset_pattern=1 if self.dream else self.preset_pattern_num,
        )
        self._fire_callbacks()

    async def set_inner_whites(
        self, whites: tuple[int, int], brightness: int | None = None
    ) -> None:
        """Set rgb."""
        _LOGGER.debug("%s: Set light 0 whites: %s brightness: %s", self.name, whites, brightness)
        for value in whites:
            if not 0 <= value <= 4095:
                raise ValueError("Value {} is outside the valid range of 0-4095")
        # if brightness is not None:
        #     rgb = self._calculate_brightness(rgb, brightness)
        _LOGGER.debug("%s: Set whites after brightness: %s", self.name, whites)
        assert self._protocol is not None  # nosec

        command = self._protocol.construct_levels_change(
            self._cmd_prefix,
            *whites,
            *self._state.outer_warm_cold,
            self._state.edge_rgbw[3],
            *self._state.edge_rgbw[0:3],
        )
        print('Command:',command.hex())
        await self._send_command(command)
        self._state = replace(
            self._state,
            inner_warm_cold=whites,
            #preset_pattern=1 if self.dream else self.preset_pattern_num,
        )
        self._fire_callbacks()

    async def set_outer_whites(
        self, whites: tuple[int, int], brightness: int | None = None
    ) -> None:
        """Set rgb."""
        _LOGGER.debug("%s: Set light 0 whites: %s brightness: %s", self.name, whites, brightness)
        for value in whites:
            if not 0 <= value <= 4095:
                raise ValueError("Value {} is outside the valid range of 0-4095")
        # if brightness is not None:
        #     rgb = self._calculate_brightness(rgb, brightness)
        _LOGGER.debug("%s: Set whites after brightness: %s", self.name, whites)
        assert self._protocol is not None  # nosec

        command = self._protocol.construct_levels_change(
            self._cmd_prefix,
            *self._state.inner_warm_cold,
            *whites,
            self._state.edge_rgbw[3],
            *self._state.edge_rgbw[0:3],
        )
        print('Command:',command.hex())
        await self._send_command(command)
        self._state = replace(
            self._state,
            outer_warm_cold=whites,
            #preset_pattern=1 if self.dream else self.preset_pattern_num,
        )
        self._fire_callbacks()

    async def set_effect(self, effect: str, brightness: int) -> None:
        """Set an effect."""
        _LOGGER.debug("%s: Set effect: %s brightness: %s", self.name, effect, brightness)
        assert self._protocol is not None
        command = self._protocol.construct_effect_start(self._cmd_prefix,int(effect))
        await self._send_command(command)
        self._fire_callbacks()


    async def stop(self) -> None:
        """Stop the ORB."""
        _LOGGER.debug("%s: Stop", self.name)
        await self._execute_disconnect()

    # def _calculate_brightness(
    #     self, rgb: tuple[int, int, int], level: int
    # ) -> tuple[int, int, int]:
    #     hsv = colorsys.rgb_to_hsv(*rgb)
    #     r, g, b = colorsys.hsv_to_rgb(hsv[0], hsv[1], level)
    #     return int(r), int(g), int(b)

    def _fire_callbacks(self) -> None:
        """Fire the callbacks."""
        for callback in self._callbacks:
            callback(self._state)

    def register_callback(
        self, callback: Callable[[ORBState], None]
    ) -> Callable[[], None]:
        """Register a callback to be called when the state changes."""

        def unregister_callback() -> None:
            self._callbacks.remove(callback)

        self._callbacks.append(callback)
        return unregister_callback

    def _notification_handler(self, _sender: int, data: bytearray) -> None:
        """Handle notification responses."""
        _LOGGER.debug("%s: Notification received: %s", self.name, data.hex())

        # if len(data) == 4 and data[0] == 0xCC:
        #     on = data[1] == 0x23
        #     self._state = replace(self._state, power=on)
        #     return
        # if len(data) < 11:
        #     return
        # model_num = data[1]
        # on = data[2] == 0x23
        # preset_pattern = data[3]
        # mode = data[4]
        # speed = data[5]
        # r = data[6]
        # g = data[7]
        # b = data[8]
        # w = data[9]
        # version = data[10]
        # self._state = LEDBLEState(
        #     on, (r, g, b), w, model_num, preset_pattern, mode, speed, version
        # )

        # _LOGGER.debug(
        #     "%s: Notification received; RSSI: %s: %s %s",
        #     self.name,
        #     self.rssi,
        #     data.hex(),
        #     self._state,
        # )

        # if not self._resolve_protocol_event.is_set():
        #     self._resolve_protocol_event.set()
        #     self._model_data = get_model(model_num)
        #     self._set_protocol(self._model_data.protocol_for_version_num(version))

        # self._fire_callbacks()

    def _reset_disconnect_timer(self) -> None:
        """Reset disconnect timer."""
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
        self._expected_disconnect = False
        self._disconnect_timer = self.loop.call_later(
            DISCONNECT_DELAY, self._disconnect
        )

    def _disconnected(self, client: BleakClientWithServiceCache) -> None:
        """Disconnected callback."""
        if self._expected_disconnect:
            _LOGGER.debug(
                "%s: Disconnected from device; RSSI: %s", self.name, self.rssi
            )
            return
        _LOGGER.warning(
            "%s: Device unexpectedly disconnected; RSSI: %s",
            self.name,
            self.rssi,
        )
    def _disconnect(self) -> None:
        """Disconnect from device."""
        self._disconnect_timer = None
        asyncio.create_task(self._execute_timed_disconnect())

    async def _execute_timed_disconnect(self) -> None:
        """Execute timed disconnection."""
        _LOGGER.debug(
            "%s: Disconnecting after timeout of %s",
            self.name,
            DISCONNECT_DELAY,
        )
        await self._execute_disconnect()

    async def _execute_disconnect(self) -> None:
        """Execute disconnection."""
        async with self._connect_lock:
            read_char = self._read_char
            client = self._client
            self._expected_disconnect = True
            self._client = None
            self._read_char = None
            self._write_char = None
            if client and client.is_connected:
                if read_char:
                    try:
                        await client.stop_notify(read_char)
                    except BleakError:
                        _LOGGER.debug(
                            "%s: Failed to stop notifications", self.name, exc_info=True
                        )
                await client.disconnect()
    async def _ensure_connected(self) -> None:
        """Ensure connection to device is established."""
        if self._connect_lock.locked():
            _LOGGER.debug(
                "%s: Connection already in progress, waiting for it to complete; RSSI: %s",
                self.name,
                self.rssi,
            )
        if self._client and self._client.is_connected:
            self._reset_disconnect_timer()
            return
        async with self._connect_lock:
            # Check again while holding the lock
            if self._client and self._client.is_connected:
                self._reset_disconnect_timer()
                return
            _LOGGER.debug("%s: Connecting; RSSI: %s", self.name, self.rssi)
            client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self.name,
                self._disconnected,
                use_services_cache=True,
                ble_device_callback=lambda: self._ble_device,
            )
            _LOGGER.debug("%s: Connected; RSSI: %s", self.name, self.rssi)
            resolved = self._resolve_characteristics(client.services)
            if not resolved:
                # Try to handle services failing to load
                resolved = self._resolve_characteristics(await client.get_services())

            self._client = client
            self._reset_disconnect_timer()

            # _LOGGER.debug(
            #     "%s: Subscribe to notifications; RSSI: %s", self.name, self.rssi
            # )
            # await client.start_notify(self._read_char, self._notification_handler)
            # if not self._protocol:
            #     await self._resolve_protocol()

    @retry_bluetooth_connection_error(DEFAULT_ATTEMPTS)
    async def _send_command_locked(self, commands: list[bytes]) -> None:
        """Send command to device and read response."""
        try:
            await self._execute_command_locked(commands)
        except BleakDBusError as ex:
            # Disconnect so we can reset state and try again
            await asyncio.sleep(BLEAK_BACKOFF_TIME)
            _LOGGER.debug(
                "%s: RSSI: %s; Backing off %ss; Disconnecting due to error: %s",
                self.name,
                self.rssi,
                BLEAK_BACKOFF_TIME,
                ex,
            )
            await self._execute_disconnect()
            raise
        except BleakError as ex:
            # Disconnect so we can reset state and try again
            _LOGGER.debug(
                "%s: RSSI: %s; Disconnecting due to error: %s", self.name, self.rssi, ex
            )
            await self._execute_disconnect()
            raise

    async def _send_command(
        self, commands: list[bytes] | bytes, retry: int | None = None
    ) -> None:
        """Send command to device and read response."""
        await self._ensure_connected()
        #await self._resolve_protocol()
        if not isinstance(commands, list):
            commands = [commands]
        await self._send_command_while_connected(commands, retry)

    async def _send_command_while_connected(
        self, commands: list[bytes], retry: int | None = None
    ) -> None:
        """Send command to device and read response."""
        _LOGGER.debug(
            "%s: Sending commands %s",
            self.name,
            [command.hex() for command in commands],
        )
        if self._operation_lock.locked():
            _LOGGER.debug(
                "%s: Operation already in progress, waiting for it to complete; RSSI: %s",
                self.name,
                self.rssi,
            )
        async with self._operation_lock:
            try:
                await self._send_command_locked(commands)
                return
            except BleakNotFoundError:
                _LOGGER.error(
                    "%s: device not found, no longer in range, or poor RSSI: %s",
                    self.name,
                    self.rssi,
                    exc_info=True,
                )
                raise
            except CharacteristicMissingError as ex:
                _LOGGER.debug(
                    "%s: characteristic missing: %s; RSSI: %s",
                    self.name,
                    ex,
                    self.rssi,
                    exc_info=True,
                )
                raise
            except BLEAK_EXCEPTIONS:
                _LOGGER.debug("%s: communication failed", self.name, exc_info=True)
                raise

        raise RuntimeError("Unreachable")

    async def _execute_command_locked(self, commands: list[bytes]) -> None:
        """Execute command and read response."""
        assert self._client is not None  # nosec
        # if not self._read_char:
        #     raise CharacteristicMissingError("Read characteristic missing")
        if not self._write_char:
            raise CharacteristicMissingError("Write characteristic missing")
        for command in commands:
            await self._client.write_gatt_char(self._write_char, command, False)

    def _resolve_characteristics(self, services: BleakGATTServiceCollection) -> bool:
        """Resolve characteristics."""
        ## probably need to change this to match the characteristics of the orb
        for characteristic in POSSIBLE_READ_CHARACTERISTIC_UUIDS:
            if char := services.get_characteristic(characteristic):
                self._read_char = char
                break
        for characteristic in POSSIBLE_WRITE_CHARACTERISTIC_UUIDS:
            if char := services.get_characteristic(characteristic):
                self._write_char = char
                break
        return bool(self._read_char and self._write_char)