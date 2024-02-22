#BASE_UUID_FORMAT = "0000{}-0000-1000-8000-00805f9b34fb"
BASE_UUID_FORMAT = "0000{}-3d1c-019e-ab4a-65fd86e87333"
# "00001523-3d1c-019e-ab4a-65fd86e87333'
# '00001521-3d1c-019e-ab4a-65fd86e87333'
# '00001522-3d1c-019e-ac4a-65fd86e87333'


# "ff01" - 0x97 socket - LEDnetWF010097DAB37A, LEDnetWF01001C49D272
# "ffd4" - Triones:B30200000459C - legacy


class CharacteristicMissingError(Exception):
    """Raised when a characteristic is missing."""


POSSIBLE_WRITE_CHARACTERISTIC_UUIDS = [
    BASE_UUID_FORMAT.format(part) for part in ["1523"]
]
POSSIBLE_READ_CHARACTERISTIC_UUIDS = [
    BASE_UUID_FORMAT.format(part) for part in ["1527"]
]

QUERY_STATE_BYTES = bytearray([0xEF, 0x01, 0x77])