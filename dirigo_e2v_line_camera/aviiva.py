import math
import re

from pydantic import Field

from dirigo import units
from dirigo.hw_interfaces.camera import LineCameraSettings, TriggerMode, PixelFormat, ScanDirection
from .base import E2VLineCameraConfig, E2VLineCamera, SerialControl



class AviivaM2Config(E2VLineCameraConfig):
    # Hide pixel size because it will be introspected
    pixel_size: None = Field(
        default           = None,
        json_schema_extra = {"ui": {"hidden": True}},
    )


class AviivaM2Settings(LineCameraSettings):
    """Aviiva M2-specific device settings"""
    even_gain: int | None = None
    odd_gain: int | None = None
    even_offset: int | None = None
    odd_offset: int | None = None


class AviivaM2(E2VLineCamera):
    config_model = AviivaM2Config
    settings_model = AviivaM2Settings
    title = "e2v AViiVA M2 CL"

    def __init__(self, cfg: AviivaM2Config, *, transport: SerialControl, **kwargs):
        super().__init__(cfg, transport=transport, **kwargs)

        self._scan_direction = ScanDirection.FORWARD # has no effect on camera since it's only a single row of pixels

    # do not override _connect_impl and _close_impl to leave as no-op defaults
    
    def _introspect_identity(self) -> dict[str, str]:
        introspected = {}
        id_readout = self._camera_identification_readout()
        introspected["model"] = id_readout["model"]
        introspected["serial"] = id_readout["serial"]
        introspected["hardware_rev"] = id_readout["ind"]
        introspected["firmware"] = id_readout["version"]
        return introspected
    
    # ---- Sensor geometry ----
    @property
    def pixel_size(self) -> units.Position:
        model = self.identity.model
        base = model.split('-')[0]
        pixel_pitch_specifier = int(base[-2:])
        return units.Position(pixel_pitch_specifier*1e-6)
        
    @property
    def image_width_px(self) -> int:
        model = self.identity.model
        base = model.split('-')[0]
        pixel_count_specifier = base[-4:-2]
        if pixel_count_specifier == "40":
            return 4096
        elif pixel_count_specifier == "20":
            return 2048
        elif pixel_count_specifier == "10":
            return 1024
        elif pixel_count_specifier == "05":
            return 512
        else:
            raise RuntimeError(f"Unsupported pixel count, got {pixel_count_specifier}")

    # ---- Controls ----
    @property
    def integration_time(self) -> units.Time:
        d = self._camera_configuration_readout()
        return units.Time(int(d["I"]) * 1e-6)

    @integration_time.setter
    def integration_time(self, t: units.Time) -> None:
        if not isinstance(t, units.Time):
            raise ValueError(f"Integration time must be set with units.Time instance, got {type(t)}")
        if not self.integration_time_range.within_range(t):
            raise ValueError(f"Integration time outside settable range. Got: {t} "
                             f"Settable range: {self.integration_time_range}")
        time_us = round(float(t) * 1e6)
        self._write(f"I={time_us}\r")
        self._expect_ok()

    @property
    def integration_time_range(self) -> units.TimeRange:
        return units.TimeRange(
            min = units.Time("5 us"), 
            max = units.Time("13 ms")
        )

    @property
    def gain(self) -> float:
        d = self._camera_configuration_readout()
        gain_db = int(d["G"]) * 0.047
        return 10 ** (gain_db / 20)

    @gain.setter
    def gain(self, g: float) -> None:
        if not isinstance(g, float):
            raise ValueError(f"Gain must be set with float instance, got {type(g)}")
        if not self.supported_gains.within_range(g):
            raise ValueError(f"Gain outside settable range. Got: {g} "
                             f"Settable range: {self.supported_gains}")
        
        gain_db = 20 * math.log10(g)
        code = round(gain_db / 0.047)
        self._write(f"G={code}\r")
        self._expect_ok()

    @property
    def supported_gains(self) -> units.FloatRange:
        return units.FloatRange(
            min = 1,   # 0 dB
            max = 100  # 40 dB
        )

    @property
    def pixel_format(self) -> PixelFormat:
        d = self._camera_configuration_readout()
        code = int(d["S"])
        if code == 0:
            return PixelFormat.MONO12
        elif code == 1:
            return PixelFormat.MONO10
        elif code == 2:
            return PixelFormat.MONO8
        else:
            raise RuntimeError(f"Unsupported pixel format code, {code}")

    @pixel_format.setter
    def pixel_format(self, f: int) -> None:
        if f not in self.supported_pixel_formats:
            raise ValueError(f"Unsupported pixel format. Got {f}. "
                             f"Supported: {self.supported_pixel_formats}")
        
        if f == PixelFormat.MONO12:
            self._write(f"S=0\r")
        elif f == PixelFormat.MONO10:
            self._write(f"S=1\r")
        else:
            self._write(f"S=2\r")
        
        self._expect_ok()

    @property
    def supported_pixel_formats(self) -> tuple[PixelFormat, ...]:
        return (
            PixelFormat.MONO12,
            PixelFormat.MONO10,
            PixelFormat.MONO8,
        )

    @property
    def trigger_mode(self) -> TriggerMode:
        d = self._camera_configuration_readout()
        code = int(d["M"])
        if code == 1:
            return TriggerMode.FREE_RUN
        elif code == 2:
            return TriggerMode.EXTERNAL_TRIGGER
        raise RuntimeError(f"Unsupported trigger mode code: {code}")

    @trigger_mode.setter
    def trigger_mode(self, m: TriggerMode) -> None:
        if m not in self.supported_trigger_modes:
            raise ValueError(f"Unsupported trigger mode: {m}. "
                             f"Supported: {self.supported_trigger_modes}")
        if m == TriggerMode.FREE_RUN:
            self._write(f"M=1\r")
        else:
            self._write(f"M=2\r")
        
        self._expect_ok()

    @property
    def supported_trigger_modes(self) -> tuple[TriggerMode, ...]:
        return (TriggerMode.FREE_RUN, TriggerMode.EXTERNAL_TRIGGER)
    
    @property
    def scan_direction(self) -> ScanDirection:
        return self._scan_direction

        
    @scan_direction.setter
    def scan_direction(self, d: ScanDirection):
        if not isinstance(d, ScanDirection):
            raise ValueError(f"Invalid line direction, got {d}")
        self._scan_direction = d

    # ---- Even/odd gain/offset helpers ----
    # Since there are 2 separate taps (ADCs), they may require a bit of calibration
    @property
    def even_gain(self) -> int:
        data_dict = self._camera_configuration_readout()
        return int(data_dict["A"])
    
    @even_gain.setter
    def even_gain(self, new_gain: int):
        self._write(f"A={new_gain}\r")
        self._expect_ok()

    @property
    def odd_gain(self) -> int:
        data_dict = self._camera_configuration_readout()
        return int(data_dict["B"])
    
    @odd_gain.setter
    def odd_gain(self, new_gain: int):
        self._write(f"B={new_gain}\r")
        self._expect_ok()

    @property
    def even_offset(self) -> int:
        data_dict = self._camera_configuration_readout()
        return int(data_dict["O"])
    
    @even_offset.setter
    def even_offset(self, new_offset: int):
        self._write(f"O={new_offset}\r")
        self._expect_ok()

    @property
    def odd_offset(self) -> int:
        data_dict = self._camera_configuration_readout()
        return int(data_dict["P"])
    
    @odd_offset.setter
    def odd_offset(self, new_offset: int):
        self._write(f"P={new_offset}\r")
        self._expect_ok()

    # ---- Low-level helpers ----
    def _expect_ok(self) -> None:
        resp = self._read()
        if resp != ">OK\r":
            raise RuntimeError(f"Unexpected serial response: {resp!r}")

    def _camera_configuration_readout(self) -> dict[str, str]:
        """
        Poll camera's current settings (returns a key/value dict).
        """
        self._write("!=3\r")

        buf = ""
        while True:
            buf += self._read(nbytes=1)
            if buf.endswith("OK"):
                break

        parts = buf.split("\r")
        out: dict[str, str] = {}
        for p in parts:
            if "=" in p:
                k, v = p.split("=", 1)
                out[k] = v
        return out
    
    def _camera_identification_readout(self) -> dict[str, str]:
        """
        Poll camera's identification.
        """
        self._write("!=0\r")
        resp = self._read()
        
        # parse response into key-values
        out: dict[str, str] = {}
        s = resp.strip()
        parts = s.split('-')

        # model is "<base>-BA<rev>"
        if len(parts) >= 2 and re.fullmatch(r"BA\d+", parts[1]):
            out["model"] = f"{parts[0]}-{parts[1]}"
        else:
            raise RuntimeError(f"Could not detected valid e2v line scan camera model number, got {resp}")

        out["ind"] = parts[2]

        out["serial"] = parts[3]

        out["version"] = parts[4]

        return out
    
    def snapshot_settings(self) -> AviivaM2Settings:
        # Shadow multi getter default in favor of returning most settings with 1 call
        d = self._camera_configuration_readout() # not to be confused with the DeviceConfig (only properties needed for instantiation)
        
        gain_db = int(d["G"]) * 0.047

        code = int(d["M"])
        if code == 1:
            tm = TriggerMode.FREE_RUN
        elif code == 2:
            tm = TriggerMode.EXTERNAL_TRIGGER
        else:
            raise RuntimeError(f"Unsupported trigger mode code: {code}")
        
        code = int(d["S"])
        if code == 0:
            pf = PixelFormat.MONO12
        elif code == 1:
            pf = PixelFormat.MONO10
        elif code == 2:
            pf =  PixelFormat.MONO8
        else:
            raise RuntimeError(f"Unsupported bit depth code, {code}")

        return AviivaM2Settings(
            integration_time    = units.Time(int(d["I"]) * 1e-6),
            gain                = 10 ** ( gain_db / 20 ),
            trigger_mode        = tm,
            pixel_format        = pf,
            scan_direction      = self.scan_direction,
            even_gain           = int(d["A"]),
            odd_gain            = int(d["B"]),
            even_offset         = int(d["O"]),
            odd_offset          = int(d["P"])
        )


class AviivaM4(E2VLineCamera):
    ...


class AviivaSM2(E2VLineCamera):
    ...
    # integration time range: 1 us to 32768 us


class AviivaEM(E2VLineCamera):
    ...