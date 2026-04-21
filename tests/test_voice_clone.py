import asyncio
import builtins
import importlib
import io
import sys
import tempfile
import time
import types
import wave

import numpy as np
import pytest
import torch


class _FakeStreamingModel:
    def __init__(self, first_chunk_delay: float = 0.0):
        self.first_chunk_delay = first_chunk_delay
        self.device = None

    def to(self, device):
        self.device = device
        return self

    def extract_speaker_embedding(self, audio_array, sr):
        _ = (audio_array, sr)
        return np.ones(16, dtype=np.float32)

    def generate_streaming(self, text, reference_embedding, chunk_size):
        _ = (text, reference_embedding)
        if self.first_chunk_delay:
            time.sleep(self.first_chunk_delay)
        yield np.zeros(chunk_size, dtype=np.float32)
        yield np.ones(chunk_size, dtype=np.float32)


def _make_wav_bytes(sample_rate: int = 16000) -> bytes:
    raw = io.BytesIO()
    with wave.open(raw, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * (sample_rate // 20))
    return raw.getvalue()


@pytest.fixture
def voice_module(monkeypatch):
    # Ensure importing the engine never depends on an installed voxcpm package.
    fake_voxcpm = types.ModuleType("voxcpm")

    class _ImportSafeVoxCPM:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            raise RuntimeError("Patch VoxCPM in each test before calling load().")

    fake_voxcpm.VoxCPM = _ImportSafeVoxCPM
    monkeypatch.setitem(sys.modules, "voxcpm", fake_voxcpm)

    module = importlib.import_module("src.voice.voice_clone_engine")
    return importlib.reload(module)


def test_model_loads(monkeypatch, voice_module):
    class FakeVoxCPM:
        @classmethod
        def from_pretrained(cls, model_path, load_denoiser=False):
            assert model_path == voice_module.VoiceCloneEngine.MODEL_PATH
            assert load_denoiser is False
            return _FakeStreamingModel()

    monkeypatch.setattr(voice_module, "VoxCPM", FakeVoxCPM)

    engine = voice_module.VoiceCloneEngine()
    start = time.perf_counter()
    engine.load()
    elapsed = time.perf_counter() - start

    assert elapsed < 10.0
    assert engine.model is not None


def test_streaming_latency(monkeypatch, voice_module):
    class FakeVoxCPM:
        @classmethod
        def from_pretrained(cls, model_path, load_denoiser=False):
            _ = (model_path, load_denoiser)
            return _FakeStreamingModel(first_chunk_delay=0.02)

    monkeypatch.setattr(voice_module, "VoxCPM", FakeVoxCPM)

    engine = voice_module.VoiceCloneEngine()
    engine.load()
    embedding = torch.zeros(16, dtype=torch.float32)

    async def _first_chunk():
        stream = engine.generate_streaming("hello", embedding, chunk_size=1024)
        start = time.perf_counter()
        first = await stream.__anext__()
        elapsed = time.perf_counter() - start
        await stream.aclose()
        return elapsed, first

    elapsed, first_chunk = asyncio.run(_first_chunk())
    assert elapsed < 0.2
    assert isinstance(first_chunk, np.ndarray)
    assert first_chunk.dtype == np.float32


def test_no_disk_write(monkeypatch, voice_module):
    class FakeVoxCPM:
        @classmethod
        def from_pretrained(cls, model_path, load_denoiser=False):
            _ = (model_path, load_denoiser)
            return _FakeStreamingModel()

    monkeypatch.setattr(voice_module, "VoxCPM", FakeVoxCPM)

    fake_soundfile = types.ModuleType("soundfile")

    def fake_sf_read(buffer, dtype="float32"):
        assert isinstance(buffer, io.BytesIO)
        assert dtype == "float32"
        payload = buffer.read()
        assert payload
        return np.zeros(800, dtype=np.float32), 16000

    fake_soundfile.read = fake_sf_read
    monkeypatch.setitem(sys.modules, "soundfile", fake_soundfile)

    def _disk_open_guard(*args, **kwargs):
        _ = (args, kwargs)
        raise AssertionError("Disk I/O is not allowed in extract_embedding().")

    def _tempfile_guard(*args, **kwargs):
        _ = (args, kwargs)
        raise AssertionError("Temporary files are not allowed in extract_embedding().")

    monkeypatch.setattr(builtins, "open", _disk_open_guard)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", _tempfile_guard)

    engine = voice_module.VoiceCloneEngine()
    engine.load()
    embedding = engine.extract_embedding(_make_wav_bytes())

    assert isinstance(embedding, torch.Tensor)
