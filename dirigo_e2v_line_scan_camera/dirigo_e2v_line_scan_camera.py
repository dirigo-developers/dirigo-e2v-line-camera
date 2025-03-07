import time
from enum import IntEnum

from dirigo import units
from dirigo.hw_interfaces.camera import Camera


class AnalogGainOptions(IntEnum):
    X1 = 0
    X2 = 1
    X4 = 2

class E2VUNiiQAPlusColor(Camera):
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


class E2VAViiVAM2(Camera):
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
    def bits_per_pixel(self):
        pass
    
    @bits_per_pixel.setter
    def bits_per_pixel(self, new_value):
        pass

    @property
    def trigger_mode(self):
        pass
    
    @trigger_mode.setter
    def trigger_mode(self, new_value):
        pass

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