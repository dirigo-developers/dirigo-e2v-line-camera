import time
from enum import IntEnum

from dirigo import units
from dirigo.hw_interfaces.camera import LineScanCamera


class AnalogGainOptions(IntEnum):
    X1 = 0
    X2 = 1
    X4 = 2

class E2VUNiiQAPlusColor(LineScanCamera):
    def __init__(self, **kwargs):
        super().__init__(**kwargs) # This will load the frame grabber if available

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
        return self.analog_gain_lookup.get(int(gain_mode))
    
    @gain.setter
    def gain(self, new_mode):
        new_mode = f"{int(new_mode)}x"
        mode_number = self.analog_gain_options.get(new_mode)
        cmd = f"w pamp {mode_number}\r"
        self._frame_grabber.serial_write(cmd)
        return_code = self._frame_grabber.serial_read()




class TriggerModes(IntEnum):
    FREE_RUN            = 1
    EXTERNAL_TRIGGER    = 2
    # note 2 additional modes not implemented

class E2VAViiVAM2(LineScanCamera):
    def __init__(self, **kwargs):
        super().__init__(**kwargs) # This will load the frame grabber if available

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
    def gain(self):
        pass

    @gain.setter
    def gain(self, value):
        pass

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
    def trigger_mode(self):
        """
        Returns description of the trigger mode 
        """
        data_dict = self._get_current_settings()
        mode_number = int(data_dict["M"])
        return TriggerModes(mode_number)
    
    @trigger_mode.setter
    def trigger_mode(self, new_mode: TriggerModes):
        if not isinstance(new_mode, TriggerModes):
            raise ValueError(f"trigger_mode must be set with a TriggerMode "
                             f"object, got {type(new_mode)}")
        cmd = f"M={int(new_mode)}\r"
        self._frame_grabber.serial_write(cmd)
        response = self._frame_grabber.serial_read() 
        assert response == ">OK\r", f"Unexpected serial response: {response}"

    def start(self):
        pass

    def stop(self):
        pass



    def _get_current_settings(self) -> dict:
        """
        Helper function that polls camera's current settings.
        """
        cmd = "!=3\r"
        self._frame_grabber.serial_write(cmd)
        time.sleep(0.3) # TODO, remove this!

        return_str = str()
        while True:
            return_char = self._frame_grabber.serial_read_nbytes(1)
            return_str = return_str + return_char
            if len(return_str) > 2 and return_str[-2:] == "OK":
                break

        data_list = return_str.split("\r")
        data_dict = {
            item.split('=')[0]: item.split('=')[1] 
            for item in data_list if '=' in item
        }

        return data_dict