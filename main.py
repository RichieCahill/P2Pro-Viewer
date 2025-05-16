import logging
import os
from threading import Thread
import time

import P2Pro.P2Pro_cmd as P2Pro_CMD
import P2Pro.recorder
import P2Pro.video

logging.basicConfig()
logging.getLogger("P2Pro.recorder").setLevel(logging.INFO)
logging.getLogger("P2Pro.P2Pro_cmd").setLevel(logging.INFO)

try:
    cam_cmd = P2Pro_CMD.P2Pro()

    vid = P2Pro.video.Video()
    video_thread = Thread(
        target=vid.open,
        args=(
            cam_cmd,
            -1,
        ),
    )
    video_thread.start()

    while not vid.video_running:
        time.sleep(0.01)

    # rec = P2Pro.recorder.VideoRecorder(vid.frame_queues[1], "test",audio=False)
    # rec.start()

    # print(cam_cmd._dev)
    # cam_cmd._standard_cmd_write(P2Pro_CMD.CmdCode.sys_reset_to_rom)
    # print(cam_cmd._standard_cmd_read(P2Pro_CMD.CmdCode.cur_vtemp, 0, 2))
    # print(cam_cmd._standard_cmd_read(P2Pro_CMD.CmdCode.shutter_vtemp, 0, 2))

    cam_cmd.pseudo_color_set(0, P2Pro_CMD.PseudoColorTypes.PSEUDO_RESERVED)

    print(cam_cmd.pseudo_color_get())
    # cam_cmd.set_prop_tpd_params(P2Pro_CMD.PropTpdParams.TPD_PROP_GAIN_SEL, 0)
    print(cam_cmd.get_prop_tpd_params(P2Pro_CMD.PropTpdParams.TPD_PROP_GAIN_SEL))
    print(cam_cmd.get_device_info(P2Pro_CMD.DeviceInfoType.DEV_INFO_GET_PN))

    time.sleep(5)
    # rec.stop()

    while True:
        # print(vid.frame_queue[0].get(True, 2)) # test
        time.sleep(1)

except KeyboardInterrupt:
    print("Killing...")
    video_thread.join(timeout=0.5)
os._exit(0)
