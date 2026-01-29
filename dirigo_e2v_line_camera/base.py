from typing import ClassVar

from pydantic import Field

from dirigo.hw_interfaces.image_transport import SerialControl
from dirigo.hw_interfaces.camera import LineCameraConfig, LineCamera



class E2VLineCameraConfig(LineCameraConfig):
    vendor: str = Field(
        default           = "Teledyne e2v",
        json_schema_extra = {"ui": {"hidden": True}},
    )
    # Model is introspected by the device
    model: None = Field(
        default           = None,
        json_schema_extra = {"ui": {"hidden": True}},
    )


class E2VLineCamera(LineCamera):
    """
    Shared base for e2v line-scan cameras that are controlled over a serial channel
    exposed by an ImageTransport (typically a Camera Link frame grabber).
    """
    config_model: ClassVar[type] = E2VLineCameraConfig

    def __init__(self, cfg: LineCameraConfig, *, transport: SerialControl, **kwargs):
        super().__init__(cfg, **kwargs)
        if not isinstance(transport, SerialControl):
            raise TypeError(
                f"{type(self).__name__} requires a transport implementing SerialControl "
                f"(serial_write/serial_read). Got {type(transport).__name__}."
            )
        self._transport = transport

    # Convenience wrappers
    def _write(self, cmd: str) -> None:
        self._transport.serial_write(cmd)

    def _read(self, nbytes: int | None = None) -> str:
        return self._transport.serial_read(nbytes=nbytes)