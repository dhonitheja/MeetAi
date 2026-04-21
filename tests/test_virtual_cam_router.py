import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from backend.face.virtual_cam_router import VirtualCamRouter


async def fake_frames(frames):
    for frame in frames:
        yield frame


def test_stop_sets_running_false():
    router = VirtualCamRouter()
    router.running = True
    router.stop()
    assert router.running is False


def test_initial_state():
    router = VirtualCamRouter()
    assert router.running is False


@pytest.mark.asyncio
async def test_camera_error_does_not_raise():
    """CameraError must be caught - overlay must never crash."""
    router = VirtualCamRouter()
    frames = [np.zeros((720, 1280, 3), dtype=np.uint8)]
    with patch("pyvirtualcam.Camera") as mock_cls:
        mock_cls.side_effect = RuntimeError("No device")
        await router.start_stream(fake_frames(frames))


@pytest.mark.asyncio
async def test_stop_flag_exits_loop():
    """stop() during stream exits loop and prevents further send() calls."""
    router = VirtualCamRouter()
    frames = [np.zeros((720, 1280, 3), dtype=np.uint8)] * 5

    async def stopping_frames():
        for idx, frame in enumerate(frames):
            if idx == 1:
                router.stop()
            yield frame

    mock_cam = MagicMock()
    mock_cam.__enter__ = MagicMock(return_value=mock_cam)
    mock_cam.__exit__ = MagicMock(return_value=False)
    mock_cam.device = "MockCam"
    with patch("pyvirtualcam.Camera", return_value=mock_cam):
        await router.start_stream(stopping_frames())
    assert mock_cam.send.call_count == 1
