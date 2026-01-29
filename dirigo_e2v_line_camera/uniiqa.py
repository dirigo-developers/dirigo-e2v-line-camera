import math
from typing import Literal
from enum import StrEnum

from pydantic import Field

from dirigo import units
from dirigo.hw_interfaces.hw_interface import SettingNotSettableError
from dirigo.hw_interfaces.camera import LineCameraSettings, TriggerMode, PixelFormat, ScanDirection
from .base import E2VLineCameraConfig, E2VLineCamera, SerialControl



class SensorModes(StrEnum):
    FULL_DEF                = "4096 pixels, 5x5 μm"
    TRUE_COLOR              = "2048 pixels, 10x10 μm"
    TRUE_COLOR_CROPPED_1024 = "1024 pixels, 10x10 μm"
    TRUE_COLOR_CROPPED_512  = "512 pixels, 10x10 μm"


class UniiqaPlusColorConfig(E2VLineCameraConfig):
    # Pixel size is introspected (depends on sensor mode)
    pixel_size: None = Field(
        default           = None,
        json_schema_extra = {"ui": {"hidden": True}},
    )


class UniiqaPlusColorSettings(LineCameraSettings):
    """UNiiQA+ Color-specific device settings"""
    sensor_mode: SensorModes | None = None


class UniiqaPlusColor(E2VLineCamera):
    config_model = UniiqaPlusColorConfig
    settings_model = UniiqaPlusColorSettings
    title = "e2v UNiiQA+ Color CL"

    def __init__(self, cfg: UniiqaPlusColorConfig, *, transport: SerialControl, **kwargs):
        super().__init__(cfg, transport=transport, **kwargs)

    # do not override _connect_impl and _close_impl to leave as no-op defaults
    
    def _introspect_identity(self) -> dict[str, str]:
        introspected = {}

        self._write(f"r idnb\r")
        introspected["model"] = self._read().strip()

        self._write(f"r deid\r")
        introspected["serial"] = self._read().strip()

        self._write(f"r dhwv\r")
        introspected["hardware_rev"] = self._read().strip()

        self._write(f"r dfwv\r")
        introspected["firmware"] = self._read().strip()

        return introspected
    
    # ---- Sensor geometry ----
    @property
    def pixel_size(self) -> units.Position:
        if self.sensor_mode == SensorModes.FULL_DEF:
            return units.Position("5 μm")
        else:
            return units.Position("10 μm")

    @property
    def image_width_px(self) -> int:
        sm = self.sensor_mode
        if sm == SensorModes.FULL_DEF:
            return 4096
        elif sm == SensorModes.TRUE_COLOR:
            return 2048
        elif sm == SensorModes.TRUE_COLOR_CROPPED_1024:
            return 1024
        elif sm == SensorModes.TRUE_COLOR_CROPPED_512:
            return 512
        else:
            raise RuntimeError("Unsupported sensor mode: {sm}")
    
    # ---- Controls ----
    @property
    def integration_time(self) -> units.Time:
        self._write("r tint\r")
        resp = self._read().strip()
        # 1/10 us ticks => 1e-7 seconds
        return units.Time(int(resp) * 1e-7)
    
    @integration_time.setter
    def integration_time(self, t: units.Time):
        if not isinstance(t, units.Time):
            raise ValueError(f"Integration time must be set with units.Time instance, got {type(t)}")
        if not self.integration_time_range.within_range(t):
            raise ValueError(f"Integration time outside settable range. Got: {t} "
                             f"Settable range: {self.integration_time_range}")
        ticks = int(float(t) * 1e7)
        self._write(f"w tint {ticks}\r")
        _ = self._read()

    @property
    def integration_time_range(self) -> units.TimeRange:
        return units.TimeRange(
            min = units.Time("1.5 us"),
            max = units.Time("6.5536 ms")
        )

    @property
    def gain(self) -> Literal[1, 2, 4]:
        self._write("r pamp\r")
        mode = int(self._read().strip())
        return 2 ** mode  # 0->1, 1->2, 2->4

    @gain.setter
    def gain(self, g: float) -> None:
        if not isinstance(g, float):
            raise ValueError(f"Gain must be set with float instance, got {type(g)}")
        if g not in self.supported_gains:
            raise ValueError(f"Gain outside settable options. Got: {g} "
                             f"Settable options: {self.supported_gains}")
        code = int(math.log2(g))
        self._write(f"w pamp {code}\r")
        _ = self._read()

    @property
    def supported_gains(self) -> tuple[float, ...]:
        return (1.0, 2.0, 4.0)
    
    @property
    def pixel_format(self) -> PixelFormat:
        return PixelFormat.RGB24 # fixed

    @pixel_format.setter
    def pixel_format(self, f: PixelFormat) -> None:
        if f == PixelFormat.RGB24:
            return
        else:
            raise SettingNotSettableError("Pixel format default is RGB24 and is not settable")

    @property
    def supported_pixel_formats(self) -> tuple[PixelFormat, ...]:
        return (PixelFormat.RGB24, )

    @property
    def trigger_mode(self) -> TriggerMode:
        self._write("r sync\r")
        mode_number = int(self._read().strip())
        if mode_number == 0:
            return TriggerMode.FREE_RUN
        elif mode_number == 1:
            return TriggerMode.EXTERNAL_TRIGGER
        else:
            raise RuntimeError(f"Unsupported trigger mode code: {mode_number}")

    @trigger_mode.setter
    def trigger_mode(self, new_mode: TriggerMode) -> None:
        if new_mode == TriggerMode.FREE_RUN:
            mode_number = 0
        elif new_mode == TriggerMode.EXTERNAL_TRIGGER:
            mode_number = 1
        else:
            raise ValueError(f"Unsupported trigger mode: {new_mode}")
        self._write(f"w sync {mode_number}\r")
        _ = self._read()

    @property
    def supported_trigger_modes(self) -> tuple[TriggerMode, ...]:
        return (TriggerMode.FREE_RUN, TriggerMode.EXTERNAL_TRIGGER)

    @property
    def scan_direction(self) -> ScanDirection:
        self._write("r scdi\r")
        mode_number = int(self._read().strip())
        if mode_number == 0:
            return ScanDirection.FORWARD
        else:
            return ScanDirection.REVERSE
        
    @scan_direction.setter
    def scan_direction(self, d: ScanDirection):
        if not isinstance(d, ScanDirection):
            raise ValueError("Line direction must be set by with ScanDirection enumeration.")
        if d == ScanDirection.FORWARD:
            self._write(f"w scdi 0\r")
        else:
            self._write(f"w scdi 1\r")

    # ---- Camera-specific extras ----
    @property
    def sensor_mode(self) -> SensorModes:
        self._write("r smod\r")
        code = int(self._read().strip())
        return list(SensorModes)[code]
    
    @sensor_mode.setter
    def sensor_mode(self, mode: SensorModes) -> None:
        if not isinstance(mode, SensorModes):
            raise ValueError("Sensor mode must be set with a SensorMode enumeration")
        code = list(SensorModes).index(mode)
        self._write(f"w smod {code}\r")
        _ = self._read()

    def start_auto_white_balance(self) -> None:
        self._write("w awbc 1\r")
        _ = self._read()

    def stop_auto_white_balance(self) -> None:
        self._write("w awbc 0\r")
        _ = self._read()

    @property
    def white_balance_gains(self) -> dict[str, str]:
        colors = ("r", "b", "g", "j")
        out: dict[str, str] = {}
        for c in colors:
            self._write(f"r gwb{c}\r")
            out[c] = self._read().strip()
        return out
