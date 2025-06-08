import time, math
from enum import Enum, IntEnum

from dirigo import units, io
from dirigo.hw_interfaces.camera import LineCamera, FrameGrabber


class AnalogGainOptions(IntEnum):
    X1 = 0
    X2 = 1
    X4 = 2


class TriggerModes(Enum):
    FREE_RUN            = 0
    EXTERNAL_TRIGGER    = 1
    # note 2 additional modes not implemented


class E2VUNiiQAPlusColor(LineCamera):
    def __init__(self, **kwargs):
        super().__init__(**kwargs) # This will load the frame grabber if available

        if self._frame_grabber is None:
            raise RuntimeError(f"{self.__class__} requires an initialized framegrabber.")
        self._frame_grabber: FrameGrabber

    @property
    def integration_time(self) -> units.Time:
        """ Get integration time. """
        cmd = "r tint\r"
        self._frame_grabber.serial_write(cmd)
        integration_time_tenth_us = self._frame_grabber.serial_read()
        # Camera returns int with precision 1/10th of microsecond
        integration_time_sec = int(integration_time_tenth_us)*1e-7
        return units.Time(integration_time_sec)
    
    @integration_time.setter
    def integration_time(self, time: units.Time):
        """ Set integration time in seconds. """
        if not isinstance(time, units.Time):
            raise ValueError("Integration time must be set with a units.Time object.")
        integration_time_tenth_us = int(float(time)*1e7)
        cmd = f"w tint {integration_time_tenth_us}\r"
        self._frame_grabber.serial_write(cmd)
        return_code = self._frame_grabber.serial_read()

    analog_gain_options = {
        "1x" : 0,
        "2x" : 1,
        "4x" : 2
    }
    analog_gain_lookup = {
        v: k for k, v in analog_gain_options.items()
    }

    @property
    def gain(self) -> str: # TODO change this property over to "analog_gain"
        cmd = "r pamp\r"
        self._frame_grabber.serial_write(cmd)
        gain_mode = self._frame_grabber.serial_read()
        return self.analog_gain_lookup[int(gain_mode)]
    
    @gain.setter
    def gain(self, new_mode):
        new_mode = f"{int(new_mode)}x"
        mode_number = self.analog_gain_options.get(new_mode)
        cmd = f"w pamp {mode_number}\r"
        self._frame_grabber.serial_write(cmd)
        return_code = self._frame_grabber.serial_read()

    @property
    def bit_depth(self) -> int:
        return 24 # RGB24
    
    @bit_depth.setter
    def bit_depth(self, value: int):
        raise NotImplementedError('Bit depth is not configurable on this camera.')
    
    @property
    def data_range(self) -> units.IntRange:
        return units.IntRange(min=0, max=255) # 8-bits

    @property
    def trigger_mode(self):
        """
        Returns description of the trigger mode 
        """
        cmd = "r sync\r"
        self._frame_grabber.serial_write(cmd)
        mode_number = self._frame_grabber.serial_read()
        if mode_number == 0:
            return TriggerModes.FREE_RUN
        elif mode_number == 1:
            return TriggerModes.EXTERNAL_TRIGGER
        else:
            raise RuntimeError("Unsupported trigger mode currently set.")

    @trigger_mode.setter
    def trigger_mode(self, new_mode: TriggerModes):
        if new_mode == TriggerModes.FREE_RUN:
            mode_number = 0
        elif new_mode == TriggerModes.EXTERNAL_TRIGGER:
            mode_number = 1
        else:
            raise ValueError("Specified trigger mode not supported.")
        cmd = f"w sync {mode_number}\r"
        self._frame_grabber.serial_write(cmd)
        return_code = self._frame_grabber.serial_read()

    def start(self):
        pass

    def stop(self):
        pass


class E2VAViiVAM2(LineCamera):
    def __init__(self, **kwargs):
        super().__init__(**kwargs) # This will load the frame grabber if available

        if self._frame_grabber is None:
            raise RuntimeError(f"{self.__class__} requires an initialized framegrabber.")
        self._frame_grabber: FrameGrabber

    @property
    def integration_time(self) -> units.Time:
        data_dict = self._get_current_settings()
        i_time_us = int(data_dict["I"])  # integration time in microseconds
        return units.Time(i_time_us * 1e-6)
    
    @integration_time.setter
    def integration_time(self, time: units.Time):
        time_us = round(float(time) * 1e6)
        cmd = f"I={time_us}\r"
        self._frame_grabber.serial_write(cmd)
        assert self._frame_grabber.serial_read() == ">OK\r"
    
    @property
    def gain(self) -> float:
        """ Get gain, in magnitude """
        data_dict = self._get_current_settings()
        gain_db = int(data_dict["G"]) * 0.047
        return 10**(gain_db/20)
    
    @gain.setter
    def gain(self, gain: float):
        gain_db = 20 * math.log10(gain)
        gain = round(gain_db / 0.047)
        self._frame_grabber.serial_write(f"G={gain}\r")
        assert self._frame_grabber.serial_read() == ">OK\r"

    @property
    def _even_offset(self) -> int:
        data_dict = self._get_current_settings()
        return int(data_dict["O"])
    
    @_even_offset.setter
    def _even_offset(self, new_offset: int):
        self._frame_grabber.serial_write(f"O={new_offset}\r")
        response = self._frame_grabber.serial_read() 
        assert response == ">OK\r", f"Unexpected serial response: {response}"
    
    @property
    def _odd_offset(self) -> int:
        data_dict = self._get_current_settings()
        return int(data_dict["P"])
    
    @_odd_offset.setter
    def _odd_offset(self, new_offset: int):
        self._frame_grabber.serial_write(f"P={new_offset}\r")
        response = self._frame_grabber.serial_read() 
        assert response == ">OK\r", f"Unexpected serial response: {response}"

    @property
    def _even_gain(self) -> int:
        """ Gain mismatch correction. Settings 0-20. """
        data_dict = self._get_current_settings()
        return int(data_dict["A"])
    
    @_even_gain.setter
    def _even_gain(self, new_gain: int):
        self._frame_grabber.serial_write(f"A={new_gain}\r")
        response = self._frame_grabber.serial_read() 
        assert response == ">OK\r", f"Unexpected serial response: {response}"
    
    @property
    def _odd_gain(self) -> int:
        """ Gain mismatch correction. Settings 0-20. """
        data_dict = self._get_current_settings()
        return int(data_dict["B"])
    
    @_odd_gain.setter
    def _odd_gain(self, new_gain: int):
        self._frame_grabber.serial_write(f"B={new_gain}\r")
        response = self._frame_grabber.serial_read() 
        assert response == ">OK\r", f"Unexpected serial response: {response}"

    @property
    def bit_depth(self) -> int:
        """Returns the bits per pixel."""
        data_dict = self._get_current_settings()
        code = int(data_dict["S"])
        if code == 0:
            return 12
        elif code == 1:
            return 10
        else:
            return 8
   
    @bit_depth.setter
    def bit_depth(self, bits: int):
        if bits == 12:
            code = 0
        elif bits == 10:
            code = 1
        elif bits == 8:
            code = 2
        else:
            raise ValueError(f"Bits per pixel can be 8, 10, or 12. Got {bits}")
        self._frame_grabber.serial_write(f"S={code}\r")
        assert self._frame_grabber.serial_read() == ">OK\r"

    @property
    def data_range(self) -> units.IntRange:
        return units.IntRange(min=0, max=2**self.bit_depth - 1)

    @property
    def trigger_mode(self):
        """
        Returns description of the trigger mode 
        """
        data_dict = self._get_current_settings()
        mode_number = int(data_dict["M"])
        if mode_number == 1:
            return TriggerModes.FREE_RUN
        elif mode_number == 2:
            return TriggerModes.EXTERNAL_TRIGGER
        else:
            raise RuntimeError("Unsupported trigger mode currently set.")
        
    @trigger_mode.setter
    def trigger_mode(self, new_mode: TriggerModes):
        if not isinstance(new_mode, TriggerModes):
            raise ValueError(f"trigger_mode must be set with a TriggerMode "
                             f"object, got {type(new_mode)}")
        if new_mode == TriggerModes.FREE_RUN:
            mode_number = 1
        elif new_mode == TriggerModes.EXTERNAL_TRIGGER:
            mode_number = 2
        else:
            raise ValueError("Specified trigger mode not supported.")
        cmd = f"M={mode_number}\r"
        self._frame_grabber.serial_write(cmd)
        response = self._frame_grabber.serial_read() 
        assert response == ">OK\r", f"Unexpected serial response: {response}"

    def start(self):
        pass

    def stop(self):
        pass

    def load_profile(self):
        profile = io.load_toml(
            io.config_path() / "line_camera/default_profile.toml"
        )
        self.gain           = profile['gain']
        self._even_offset   = profile['even_offset']
        self._odd_offset    = profile['odd_offset']
        self._even_gain     = profile['even_gain']
        self._odd_gain      = profile['odd_gain']

    def _get_current_settings(self) -> dict:
        """
        Helper function that polls camera's current settings.
        """
        cmd = "!=3\r"
        self._frame_grabber.serial_write(cmd)
        time.sleep(0.3) # TODO, remove this!

        return_str = str()
        while True:
            return_char = self._frame_grabber.serial_read(nbytes=1)
            return_str = return_str + return_char
            if len(return_str) > 2 and return_str[-2:] == "OK":
                break

        data_list = return_str.split("\r")
        data_dict = {
            item.split('=')[0]: item.split('=')[1] 
            for item in data_list if '=' in item
        }

        return data_dict