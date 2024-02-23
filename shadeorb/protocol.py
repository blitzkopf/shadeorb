from bitstruct import pack as bitpack
from struct import pack
from typing import Dict, List, NamedTuple, Optional, Tuple, Union

class ORBProtocol:

    def construct_message(self, raw_bytes: bytearray) -> bytearray:
        """Original protocol uses no checksum."""
        return raw_bytes

    @property
    def on_byte(self) -> int:
        """The on byte."""
        return 0x01

    @property
    def off_byte(self) -> int:
        """The off byte."""
        return 0x00

    def construct_state_change(self,cmd_prefix: bytes, turn_on: int) -> bytearray:
        """The bytes to send for a state change request."""
        return self.construct_message(
            bytearray(cmd_prefix) + bytearray([ 0x00, 0x41, 0x06, self.on_byte if turn_on else self.off_byte])
        )

    def construct_levels_change(
        self,
        cmd_prefix: bytes,
        inner_warm_white: int,
        inner_cool_white: int,
        outer_warm_white: int,
        outer_cool_white: int,
        edge_white: int,
        edge_red: int,
        edge_green: int,
        edge_blue: int,
        #write_mode: LevelWriteMode,
    ) -> List[bytearray]:
        """The bytes to send for a level change request."""
        inner_bytes=bitpack('u12u12',inner_warm_white,inner_cool_white)
        print('inner_bytes:',inner_bytes.hex())
        outer_bytes=bitpack('u12u12',outer_warm_white,outer_cool_white)
        print('inner_bytes:',outer_bytes.hex())
        print('Colors:',edge_red,edge_green,edge_blue,edge_white)
        edge_bytes=bitpack('u12u12u12u12',edge_white,edge_red,edge_green,edge_blue)
        print('edge_bytes:',edge_bytes.hex())
        return self.construct_message(
            bytearray(cmd_prefix) 
            + bytearray(
                [
                    0x00, 0x41, 0x11, 0xFF,
                ]
            )+inner_bytes+outer_bytes+edge_bytes
        )
    
    def construct_effect_start(
        self,
        cmd_prefix: bytes,
        effect: int,
    ) -> List[bytearray]:
        """The bytes to send for a level change request."""
        return self.construct_message(
            bytearray(cmd_prefix) 
            + bytearray(
                [
                     0xC0, 0x01, 0x01, 
                ]
            )+pack('B',effect)
        )