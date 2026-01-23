from dirigo import units
from dirigo.hw_interfaces.geometry import GlobalAxes

from dirigo_ni_frame_grabber.dirigo_ni_frame_grabber import NIFrameGrabber, NIFrameGrabberConfig

from dirigo_e2v_line_camera.uniiqa import UniiqaPlusColorConfig, UniiqaPlusColor
from dirigo_e2v_line_camera.aviiva import AviivaM2Config, AviivaM2

# Make framegrabber
cfg = NIFrameGrabberConfig(
    device_name = "img0"
)

fg = NIFrameGrabber(cfg)
fg.connect()

# Make camera
cfg = UniiqaPlusColorConfig(
    axis       = GlobalAxes.X
)
cam = UniiqaPlusColor(cfg, transport=fg)


# cfg = AviivaM2Config(
#     axis       = GlobalAxes.X
# )
# cam = AviivaM2(cfg, transport=fg)
# cid = cam._camera_identification_readout()


a=1