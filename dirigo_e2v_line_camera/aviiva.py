import math
import re

from pydantic import Field

from dirigo import units
from dirigo.hw_interfaces.camera import TriggerModes
from .base import E2VSerialLineCameraConfig, E2VSerialLineCamera, SerialControl



class AviivaM2Config(E2VSerialLineCameraConfig):
    pixel_size: None = Field(
        default           = None,
        json_schema_extra = {"ui": {"hidden": True}},
    )


class AviivaM2(E2VSerialLineCamera):
    config_model = AviivaM2Config
    title = "e2v AViiVA M2 CL"

    def __init__(self, cfg: AviivaM2Config, *, transport: SerialControl, **kwargs):
        super().__init__(cfg, transport=transport, **kwargs)

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
    def integration_time(self, time_value: units.Time) -> None:
        if not isinstance(time_value, units.Time):
            raise ValueError(f"Integration time must be set with units.Time instance, got {type(time_value)}")
        time_us = round(float(time_value) * 1e6)
        self._write(f"I={time_us}\r")
        self._expect_ok()

    @property
    def gain(self) -> float:
        d = self._camera_configuration_readout()
        gain_db = int(d["G"]) * 0.047
        return 10 ** (gain_db / 20)

    @gain.setter
    def gain(self, gain_value: float) -> None:
        gain_db = 20 * math.log10(gain_value)
        code = round(gain_db / 0.047)
        self._write(f"G={code}\r")
        self._expect_ok()

    @property
    def bit_depth(self) -> int:
        d = self._camera_configuration_readout()
        code = int(d["S"])
        if code == 0:
            return 12
        if code == 1:
            return 10
        return 8

    @bit_depth.setter
    def bit_depth(self, bits: int) -> None:
        code = {12: 0, 10: 1, 8: 2}.get(bits)
        if code is None:
            raise ValueError(f"Bits per pixel can be 8, 10, or 12. Got {bits}")
        self._write(f"S={code}\r")
        self._expect_ok()

    @property
    def data_range(self) -> units.IntRange:
        return units.IntRange(min=0, max=2**self.bit_depth - 1)

    @property
    def trigger_mode(self) -> TriggerModes:
        d = self._camera_configuration_readout()
        code = int(d["M"])
        if code == 1:
            return TriggerModes.FREE_RUN
        if code == 2:
            return TriggerModes.EXTERNAL_TRIGGER
        raise RuntimeError(f"Unsupported trigger mode code: {code}")

    @trigger_mode.setter
    def trigger_mode(self, new_mode: TriggerModes) -> None:
        if new_mode == TriggerModes.FREE_RUN:
            code = 1
        elif new_mode == TriggerModes.EXTERNAL_TRIGGER:
            code = 2
        else:
            raise ValueError(f"Unsupported trigger mode: {new_mode}")
        self._write(f"M={code}\r")
        self._expect_ok()

    def load_profile(self) -> None:
        pass

    # ---- Even/odd gain/offset helpers ----
    # Since there are 2 separate taps (ADCs), they may require a bit of calibration
    @property
    def _even_gain(self) -> int:
        data_dict = self._camera_configuration_readout()
        return int(data_dict["A"])
    
    @_even_gain.setter
    def _even_gain(self, new_gain: int):
        self._write(f"A={new_gain}\r")
        self._expect_ok()

    @property
    def _odd_gain(self) -> int:
        data_dict = self._camera_configuration_readout()
        return int(data_dict["B"])
    
    @_odd_gain.setter
    def _odd_gain(self, new_gain: int):
        self._write(f"B={new_gain}\r")
        self._expect_ok()

    @property
    def _even_offset(self) -> int:
        data_dict = self._camera_configuration_readout()
        return int(data_dict["O"])
    
    @_even_offset.setter
    def _even_offset(self, new_offset: int):
        self._write(f"O={new_offset}\r")
        self._expect_ok()

    @property
    def _odd_offset(self) -> int:
        data_dict = self._camera_configuration_readout()
        return int(data_dict["P"])
    
    @_odd_offset.setter
    def _odd_offset(self, new_offset: int):
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


class AviivaM4(E2VSerialLineCamera):
    ...


class AviivaSM2(E2VSerialLineCamera):
    ...


class AviivaEM(E2VSerialLineCamera):
    ...