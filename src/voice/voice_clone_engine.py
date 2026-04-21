from __future__ import annotations

import asyncio
import queue
import threading
from typing import AsyncGenerator

import numpy as np
import torch
from voxcpm import VoxCPM


class VoiceCloneEngine:
    """
    Wraps VoxCPM2 for real-time streaming voice synthesis.
    Runs inference in a background thread to avoid blocking FastAPI event loop.
    All audio data stays in memory - zero filesystem writes.
    """

    MODEL_PATH = "./models/VoxCPM2"
    SAMPLE_RATE = 48000

    def __init__(self) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model: VoxCPM | None = None
        self._lock = threading.Lock()

    def load(self) -> None:
        """Load VoxCPM2 weights. Call once at startup. Must complete < 10 seconds."""
        with self._lock:
            model = VoxCPM.from_pretrained(self.MODEL_PATH, load_denoiser=False)
            model.to(self.device)
            self.model = model

    def extract_embedding(self, wav_data: bytes) -> torch.Tensor:
        """
        Extract voice embedding from raw WAV bytes.
        wav_data: raw WAV bytes from upload - never written to disk.
        Returns: in-memory torch.Tensor embedding on self.device.
        """
        if self.model is None:
            raise RuntimeError("VoiceCloneEngine not loaded. Call load() first.")

        import io
        import soundfile as sf

        audio_array, sr = sf.read(io.BytesIO(wav_data), dtype="float32")
        if isinstance(audio_array, np.ndarray) and audio_array.ndim > 1:
            audio_array = np.mean(audio_array, axis=1, dtype=np.float32)

        with self._lock:
            embedding = self.model.extract_speaker_embedding(audio_array, sr)

        if not isinstance(embedding, torch.Tensor):
            embedding = torch.as_tensor(embedding)
        return embedding.to(self.device)

    async def generate_streaming(
        self,
        text: str,
        embedding: torch.Tensor,
        chunk_size: int = 4096,
    ) -> AsyncGenerator[np.ndarray, None]:
        """
        Async generator yielding float32 numpy audio chunks at 48kHz.
        Runs VoxCPM2 inference in a background thread via run_in_executor.
        Yields chunks as they are produced - target <200ms to first chunk.
        """
        if self.model is None:
            raise RuntimeError("VoiceCloneEngine not loaded. Call load() first.")

        chunk_queue: queue.Queue[object] = queue.Queue()
        sentinel: object = object()
        loop = asyncio.get_running_loop()
        model = self.model

        def _run_inference() -> None:
            try:
                with self._lock:
                    for chunk in model.generate_streaming(
                        text=text,
                        reference_embedding=embedding,
                        chunk_size=chunk_size,
                    ):
                        if not isinstance(chunk, np.ndarray):
                            chunk = np.asarray(chunk, dtype=np.float32)
                        elif chunk.dtype != np.float32:
                            chunk = chunk.astype(np.float32, copy=False)
                        chunk_queue.put(chunk)
            except Exception as exc:
                chunk_queue.put(exc)
            finally:
                chunk_queue.put(sentinel)

        inference_future = loop.run_in_executor(None, _run_inference)

        try:
            while True:
                item = await loop.run_in_executor(None, chunk_queue.get)
                if item is sentinel:
                    break
                if isinstance(item, Exception):
                    raise item
                if isinstance(item, np.ndarray):
                    yield item
                else:
                    yield np.asarray(item, dtype=np.float32)
        finally:
            await asyncio.shield(inference_future)

    def unload(self) -> None:
        """Release GPU memory. Call on session end."""
        with self._lock:
            if self.model is not None:
                del self.model
                self.model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
