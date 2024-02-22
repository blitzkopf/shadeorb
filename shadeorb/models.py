from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ORBState:

    power: bool = False
    inner_warm_cold: tuple[int,int] = (0,0)
    outer_warm_cold: tuple[int,int] = (0,0)
    edge_rgbw: tuple[int, int, int, int] = (0, 0, 0, 0)

    # model_num: int = 0
    # preset_pattern: int = 0
    # mode: int = 0
    # speed: int = 0
    # version_num: int = 0