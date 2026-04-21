from __future__ import annotations

import asyncio
import logging
import platform
from typing import Any, AsyncGenerator

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE: int = 48000
CHANNELS: int = 1
DTYPE: str = "int16"

# Target device names per OS
DEVICE_NAMES: dict[str, list[str]] = {
    "Windows": ["CABLE Input", "VB-Audio"],
    "Darwin": ["BlackHole 2ch", "BlackHole"],
    "Linux": [],  # no virtual device on Linux - fallback to default
}


class VirtualMicRouter:
    """
    Routes float32 audio chunks from VoiceCloneEngine to a virtual
    microphone device (VB-Audio on Windows, BlackHole on macOS).
    Meeting apps (Zoom, Teams, Meet, Webex) see the virtual device
    as their microphone input.
    """

    def __init__(self) -> None:
        self.device_index: int | None = self._find_device()

    def _find_device(self) -> int | None:
        """Find virtual audio device index. Returns None if not found."""
        os_name: str = platform.system()
        target_names: list[str] = DEVICE_NAMES.get(os_name, [])

        devices: Any = sd.query_devices()
        for i, dev in enumerate(devices):
            dev_name: str = str(dev["name"])
            if int(dev["max_output_channels"]) > 0:
                for target in target_names:
                    if target.lower() in dev_name.lower():
                        logger.info("Virtual mic found: [%s] %s", i, dev_name)
                        return i

        logger.critical(
            "VIRTUAL MIC NOT FOUND. Audio will route to system default. "
            "Install VB-Audio Cable (Windows) or BlackHole (macOS)."
        )
        return None  # fallback to system default (sd will use None = default)

    async def route_audio_stream(
        self,
        audio_generator: AsyncGenerator[np.ndarray, None],
    ) -> None:
        """
        Consume float32 chunks from VoiceCloneEngine and write to
        virtual mic output stream in real time.

        Converts float32 -> int16 at stream boundary.
        Handles device disconnect gracefully - logs error, does not crash.
        """
        loop = asyncio.get_running_loop()

        try:
            with sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                device=self.device_index,
                latency="low",
            ) as stream:
                async for chunk in audio_generator:
                    chunk_int16: np.ndarray = (
                        np.clip(chunk, -1.0, 1.0) * 32767
                    ).astype(np.int16)
                    try:
                        await loop.run_in_executor(
                            None, stream.write, chunk_int16.reshape(-1, CHANNELS)
                        )
                    except sd.PortAudioError as exc:
                        logger.error("Virtual mic stream error (device disconnect?): %s", exc)
                        return

        except sd.PortAudioError as exc:
            logger.error("Virtual mic stream error (device disconnect?): %s", exc)
            return
        except Exception as exc:
            logger.error("Unexpected error in audio routing: %s", exc)
            raise

    def list_output_devices(self) -> list[dict[str, int | str]]:
        """Utility: list all output devices for debugging."""
        devices: Any = sd.query_devices()
        return [
            {"index": i, "name": str(d["name"]), "channels": int(d["max_output_channels"])}
            for i, d in enumerate(devices)
            if int(d["max_output_channels"]) > 0
        ]
