import logging
import platform
import queue
from typing import ClassVar

import cv2
import numpy as np

import P2Pro.P2Pro_cmd as P2Pro_CMD

if platform.system() == "Linux":
    import pyudev

P2Pro_resolution = (256, 384)
P2Pro_fps = 25.0
P2Pro_usb_id = (0x0BDA, 0x5830)  # VID, PID

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


class Video:
    """Video."""

    # queue 0 is for GUI, 1 is for recorder
    frame_queues: ClassVar[list[queue.Queue]] = [queue.Queue(1) for _ in range(2)]
    video_running = False

    @staticmethod
    def list_cap_ids() -> tuple[list[int], list[int], list[int]]:
        """Test the ports and returns a tuple with the available ports and the ones that are working."""
        non_working_ids = []
        dev_port = 0
        working_ids = []
        available_ids = []
        log.info("Probing video capture ports...")
        while len(non_working_ids) < 6:  # if there are more than 5 non working ports stop the testing.
            camera = cv2.VideoCapture(dev_port, cv2.CAP_DSHOW)
            log.info(f"Testing video capture port {dev_port}... ")
            if not camera.isOpened():
                log.info("Not working.")
                non_working_ids.append(dev_port)
            else:
                is_reading, img = camera.read()
                w = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = camera.get(cv2.CAP_PROP_FPS)
                backend = camera.getBackendName()
                log.info(
                    f"Is present {'and working    ' if is_reading else 'but not working'} [{w}x{h} @ {fps:.1f} FPS ({backend})]",
                )
                if is_reading:
                    # print("Port %s is working and reads images (%s x %s)" %(dev_port,w,h))
                    working_ids.append((dev_port, (w, h), fps, backend))
                else:
                    # print("Port %s for camera ( %s x %s) is present but does not reads." %(dev_port,w,h))
                    available_ids.append(dev_port)

            dev_port += 1
        return working_ids, available_ids, non_working_ids

    def get_p2pro_cap_id(self) -> int | None:
        """Get the camera ID from the device name

        On Linux, just use the VID/PID via udev
        Sadly, Windows APIs / OpenCV is very limited
        the only way to detect the camera is by its characteristic resolution and framerate

        Returns:
            int | None: The camera ID or None if not found
        """
        if platform.system() == "Linux":
            for device in pyudev.Context().list_devices(subsystem="video4linux"):
                if (
                    int(device.get("ID_USB_VENDOR_ID"), 16),
                    int(device.get("ID_USB_MODEL_ID"), 16),
                ) == P2Pro_usb_id and "capture" in device.get("ID_V4L_CAPABILITIES"):
                    return device.get("DEVNAME")
            return None

        # Fallback that uses the resolution and framerate to identify the device
        working_ids, _, _ = self.list_cap_ids()
        for id in working_ids:
            if id[1] == P2Pro_resolution:  # and id[2] == P2Pro_fps:
                return id[0]
        return None

    def open(self, cam_cmd: P2Pro_CMD.P2Pro, camera_id: int | str | None = None) -> None:
        """Open the video capture device

        Args:
            cam_cmd (P2Pro_CMD.P2Pro): The P2Pro command object
            camera_id (int | str | None, optional): The camera ID. Defaults to None.

        Raises:
            ConnectionError: If the camera is not found or the video capture device cannot be opened
        """
        log.info(
            "Hotkeys:\n"
            "[q] close openCV window, then close program using [ctrl]+[c]\n"
            "[s] do NUC\n"
            "[b] do NUC for background\n"
            "[d] read shutter state\n"
            "[l] set low gain (high temperature mode)\n"
            "[h] set high gain (low temperature mode)\n"
            "[m] set shutter parameters\n"
            "[n] print shutter parameters\n"
        )
        hotkeys = {
            ord("s"): cam_cmd.shutter_actuate,
            ord("d"): cam_cmd.get_shutter_state,
            ord("b"): cam_cmd.shutter_background,
            ord("l"): cam_cmd.gain_set_low,
            ord("h"): cam_cmd.gain_set_high,
            ord("m"): cam_cmd.shutter_param_set,
            ord("n"): cam_cmd.shutter_params_print,
        }

        if camera_id is None:
            log.info("No camera ID specified, scanning... (This could take a few seconds)")
            camera_id = self.get_p2pro_cap_id()
            if camera_id is None:
                error = "Could not find camera module"
                raise ConnectionError(error)

        # check if video capture can be opened
        cap = cv2.VideoCapture(camera_id, cv2.CAP_V4L2)
        if not cap.isOpened():
            error = f"Could not open video capture device with index {camera_id}, is the module connected?"
            raise ConnectionError(error)

        # check if resolution and FPS matches that of the P2 Pro module
        capture_resolution = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        capture_fps = cap.get(cv2.CAP_PROP_FPS)
        if capture_resolution != P2Pro_resolution or capture_fps != P2Pro_fps:
            error = (
                f"Resolution/FPS of camera id {camera_id} doesn't match. "
                f"It's probably not a P2 Pro. (Got: {capture_resolution[0]}x{capture_resolution[1]}@{capture_fps})"
            )
            raise IndexError(error)

        # disable automatic YUY2->RGB conversion of OpenCV
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)

        frame_counter = 0

        while True:
            success, frame = cap.read()

            if not success:
                continue

            self.video_running = True

            frame = frame.flatten()

            # split video frame (top is pseudo color, bottom is temperature data)
            frame_mid_pos = int(len(frame) / 2)
            picture_data = frame[0:frame_mid_pos]
            thermal_data = frame[frame_mid_pos:]

            # convert buffers to numpy arrays
            yuv_picture = np.frombuffer(picture_data, dtype=np.uint8).reshape(
                (P2Pro_resolution[1] // 2, P2Pro_resolution[0], 2),
            )
            rgb_picture = cv2.cvtColor(yuv_picture, cv2.COLOR_YUV2BGR_YUY2)
            thermal_picture_16 = np.frombuffer(thermal_data, dtype=np.uint16).reshape(
                (P2Pro_resolution[1] // 2, P2Pro_resolution[0]),
            )

            # pack parsed frame data into object
            frame_obj = {
                "frame_num": frame_counter,
                "rgb_data": rgb_picture,
                "yuv_data": yuv_picture,
                "thermal_data": thermal_picture_16,
            }

            cv2.imshow("frame", rgb_picture)
            key = cv2.waitKey(1)
            if key & 0xFF == ord("q"):
                break
            hotkeys.get(key, lambda: None)()

            # populate all queues with new frame
            for frame_queue in self.frame_queues:
                # if queue is full, discard oldest frame (e.g. if frames not read fast enough or at all)
                if frame_queue.full():
                    frame_queue.get(False)
                frame_queue.put(frame_obj)

            frame_counter += 1
