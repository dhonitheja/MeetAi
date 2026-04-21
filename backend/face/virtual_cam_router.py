from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

import cv2
import numpy as np
import pyvirtualcam

logger = logging.getLogger(__name__)

try:
    CAMERA_ERROR = pyvirtualcam.error.CameraError
except AttributeError:
    CAMERA_ERROR = RuntimeError

TARGET_FPS = 30
WIDTH = 1280
HEIGHT = 720


class VirtualCamRouter:
    """
    Outputs face-swapped BGR frames to a virtual camera device.
    Meeting apps (Zoom, Teams, Meet, Webex) see this device as their webcam.
    Requires OBS Virtual Camera installed on Windows or macOS.

    Input:  BGR numpy array from FaceSwapEngine.process_frame()
    Output: RGB frames to pyvirtualcam at 1280x720 @ 30fps
    """

    def __init__(self) -> None:
        """Initialize stream state."""
        self.running: bool = False

    async def start_stream(
        self,
        frame_generator: AsyncGenerator[np.ndarray, None],
    ) -> None:
        """
        Consume BGR frames and write to virtual camera at TARGET_FPS.
        Converts BGR -> RGB at stream boundary.
        Resizes frames to WIDTH x HEIGHT if needed.
        Handles device not found: logs error, returns cleanly, never crashes.
        """
        try:
            with pyvirtualcam.Camera(
                width=WIDTH,
                height=HEIGHT,
                fps=TARGET_FPS,
                fmt=pyvirtualcam.PixelFormat.RGB,
            ) as cam:
                logger.info("Virtual camera active: %s", cam.device)
                self.running = True
                async for frame in frame_generator:
                    if not self.running:
                        break
                    if frame.shape[:2] != (HEIGHT, WIDTH):
                        frame = cv2.resize(frame, (WIDTH, HEIGHT))
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    cam.send(rgb)
                    cam.sleep_until_next_frame()
        except CAMERA_ERROR as exc:
            logger.error(
                "Virtual camera device not found: %s. Install OBS Virtual Camera. "
                "Webcam feed will NOT be replaced in meeting apps.",
                exc,
            )
        except Exception as exc:
            logger.error("Unexpected virtual cam error: %s", exc)
            raise
        finally:
            self.running = False

    def stop(self) -> None:
        """Signal the stream loop to exit on next frame."""
        self.running = False
