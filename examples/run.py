import asyncio
import logging

from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from shadeorb import ORB,ORBState

_LOGGER = logging.getLogger(__name__)

ADDRESS = "C0:4E:63:AD:78:E3"
#ADDRESS = "F4:E0:9F:B8:16:D3"
SERVICE_UUID = "00001523-3d1c-019e-ab4a-65fd86e87333"
SERVICE_UUID = "00001522-3d1c-019e-ac4a-65fd86E87333"
SERVICE_UUID = "00001801-0000-1000-8000-00805f9b34fb"

readables= []
char_vals = {}
async def list_readable_characteristics(client: BleakClient) -> None:
    #async with BleakClient(device) as client:
        for service in client.services:
            _LOGGER.info("Service: %s", service)
            for characteristic in service.characteristics:
                if "read" in characteristic.properties:
                    _LOGGER.info(
                        "  [Characteristic] %s (%s)",
                        characteristic,
                        ",".join(characteristic.properties),
                    )
                    readables.append(characteristic.uuid)
async def read_readable_characteristics(client: BleakClient) -> None:
    #async with BleakClient(device) as client:
        for uuid in readables:
            try:
                value = await client.read_gatt_char(uuid)
                if char_vals.get(uuid) != value:
                    char_vals[uuid] = value
                    _LOGGER.info(
                        "  [Characteristic changed] %s, Value: %r",
                        uuid,
                        value,
                    )
            except Exception as e:
                _LOGGER.error(
                    "  [Characteristic] %s, Error: %s",
                    uuid,
                    e,
                )



async def read_all_characteristics(device: BLEDevice) -> None:
    async with BleakClient(device) as client:
        for service in client.services:
            _LOGGER.info("Service: %s", service)
            for characteristic in service.characteristics:
                  if "read" in characteristic.properties:
                    try:
                        value = await client.read_gatt_char(characteristic.uuid)
                        _LOGGER.info(
                            "  [Characteristic] %s (%s), Value: %r",
                            characteristic,
                            ",".join(characteristic.properties),
                            value,
                        )
                    except Exception as e:
                        _LOGGER.error(
                            "  [Characteristic] %s (%s), Error: %s",
                            characteristic,
                            ",".join(characteristic.properties),
                            e,
                        )

 

async def run() -> None:
    #scanner = BleakScanner(service_uuids=[SERVICE_UUID])
    #scanner = BleakScanner(service_uuids=['00001521-3d1c-019e-ab4a-65fd86e87333', '00001522-3d1c-019e-ac4a-65fd86e87333', '00001800-0000-1000-8000-00805f9b34fb', '00001801-0000-1000-8000-00805f9b34fb', '00001828-0000-1000-8000-00805f9b34fb'])
    scanner = BleakScanner(local_name="Shade Orb")
    future: asyncio.Future[BLEDevice] = asyncio.Future()

    def on_detected(device: BLEDevice, adv: AdvertisementData) -> None:
        if future.done():
            return
        _LOGGER.info("Detected: %s", device)
        _LOGGER.info("Advert: %s", adv)
        if device.address.lower() == ADDRESS.lower():
            _LOGGER.info("Found device: %s", device.address)
            future.set_result(device)

    scanner.register_detection_callback(on_detected)
    await scanner.start()

    def on_state_changed(state: ORBState) -> None:
        _LOGGER.info("State changed: %s", state)

    device = await future
    orb = ORB(device)
    await orb._ensure_connected()
    await list_readable_characteristics(orb._client)
    cancel_callback = orb.register_callback(on_state_changed)
    await orb.update()
    await read_readable_characteristics(orb._client)
    
    await orb.turn_on()
    await read_readable_characteristics(orb._client)
    await asyncio.sleep(2)
    
    await orb.set_edge_rgbw((4095, 0, 0, 0), 4095)
    await read_readable_characteristics(orb._client)
    await asyncio.sleep(2)
    
    await orb.set_edge_rgbw((0, 4095, 0, 1024), 2047)
    await read_readable_characteristics(orb._client)
    await asyncio.sleep(2)
    
    await orb.set_edge_rgbw((0, 0, 4095, 2048), 4095)
    await read_readable_characteristics(orb._client)
    await asyncio.sleep(2)
    
    # await orb.set_edge_rgbw((4095, 4095, 4095, 2048), 4095)
    # await read_readable_characteristics(orb._client)
    # await asyncio.sleep(2)
    
    # await orb.set_edge_rgbw((0, 0, 0, 0), 4095)
    # await orb.set_l0_whites((4095, 0))
    # await asyncio.sleep(2)
    # await orb.set_l0_whites((0,4095))

    # await asyncio.sleep(5)
    # await orb.turn_off()
    # await read_readable_characteristics(orb._client)
    # # await led.update()
    cancel_callback()
    await scanner.stop()


logging.basicConfig(level=logging.INFO)
logging.getLogger("led_ble").setLevel(logging.DEBUG)
asyncio.run(run())