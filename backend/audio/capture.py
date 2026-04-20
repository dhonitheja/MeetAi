"""
MeetAI Audio Capture Engine
============================
Dual-channel capture:
  • Mic channel (your voice)    → sounddevice + SpeechRecognition
  • System audio channel        → PyAudioWPatch WASAPI loopback (Windows)
                                  BlackHole / ScreenCaptureKit (macOS)

VAD (Voice Activity Detection):
  • Silero VAD (primary, < 1ms per 30ms chunk)
  • WebRTC VAD fallback (webrtcvad)
  • RMS energy fallback (always available)

After VAD detects end-of-utterance (silence after speech), the transcribed
segment is pushed to the overlay which triggers AI suggestions.

Usage:
    from backend.audio.capture import AudioEngine
    engine = AudioEngine(on_transcript=my_callback)
    engine.start()
    # ... later ...
    engine.stop()

Callback signature:
    def my_callback(speaker: str, text: str) -> None
    # speaker: "You" | "Them"
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Callable, Optional

import numpy as np

# ── Optional heavy imports with graceful fallback ────────────────────────────

try:
    import sounddevice as sd  # type: ignore
    HAS_SD = True
except ImportError:
    HAS_SD = False
    print("[audio] sounddevice not installed -- mic capture disabled (pip install sounddevice)")

try:
    import pyaudiowpatch as pyaudio  # type: ignore
    HAS_WASAPI = True
except ImportError:
    HAS_WASAPI = False
    if sys.platform == "win32":
        print("[audio] PyAudioWPatch not installed -- system audio disabled (pip install PyAudioWPatch)")

try:
    import speech_recognition as sr  # type: ignore
    HAS_SR = True
except ImportError:
    HAS_SR = False
    print("[audio] SpeechRecognition not installed (pip install SpeechRecognition)")

# Silero VAD — loaded lazily inside VAD.__init__ to avoid blocking import
HAS_SILERO = False
_silero_model = None

# WebRTC VAD fallback
try:
    import webrtcvad  # type: ignore
    HAS_WEBRTC_VAD = True
except ImportError:
    HAS_WEBRTC_VAD = False

# faster-whisper local transcription
try:
    from faster_whisper import WhisperModel  # type: ignore
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False


# ════════════════════════════════════════════════════════════════════════════
# VAD PIPELINE
# ════════════════════════════════════════════════════════════════════════════

class VAD:
    """
    Voice activity detector. Wraps Silero → WebRTC VAD → RMS energy.
    Returns True when the chunk contains speech.
    """
    SAMPLE_RATE = 16000
    CHUNK_SAMPLES = 512   # 32 ms @ 16 kHz — Silero minimum

    def __init__(self):
        global HAS_SILERO, _silero_model
        self._webrtc = None
        if HAS_WEBRTC_VAD:
            self._webrtc = webrtcvad.Vad(2)   # aggressiveness 0-3
        # Lazy-load Silero on first VAD instantiation
        if not HAS_SILERO:
            try:
                import torch as _torch  # type: ignore
                _m, _utils = _torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    force_reload=False,
                    onnx=False,
                    verbose=False,
                )
                _silero_model = _m
                HAS_SILERO = True
                print("[audio] Silero VAD loaded")
            except Exception:
                HAS_SILERO = False

    def is_speech(self, audio_int16: bytes, sample_rate: int = 16000) -> bool:
        """audio_int16: raw 16-bit PCM bytes."""
        # Silero (float32 tensor)
        if HAS_SILERO and _silero_model is not None:
            try:
                import torch as _torch  # type: ignore
                tensor = _torch.from_numpy(
                    np.frombuffer(audio_int16, dtype=np.int16).astype(np.float32) / 32768.0
                )
                confidence: float = _silero_model(tensor, sample_rate).item()
                return confidence > 0.4
            except Exception:
                pass
        # WebRTC VAD
        if HAS_WEBRTC_VAD and self._webrtc and sample_rate in (8000, 16000, 32000, 48000):
            try:
                return self._webrtc.is_speech(audio_int16, sample_rate)
            except Exception:
                pass
        # RMS energy fallback
        arr = np.frombuffer(audio_int16, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(arr ** 2))
        return rms > 800   # tunable threshold


# ════════════════════════════════════════════════════════════════════════════
# WHISPER LOCAL TRANSCRIBER
# ════════════════════════════════════════════════════════════════════════════

class LocalTranscriber:
    """
    Wraps faster-whisper for segment transcription.
    Called only when VAD detects end-of-utterance to avoid real-time cost.
    """
    def __init__(self, model_size: str = "base"):
        self._model = None
        if HAS_WHISPER:
            try:
                self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
                print(f"[audio] Whisper '{model_size}' loaded (int8, local)")
            except Exception as exc:
                print(f"[audio] Whisper init failed: {exc}")

    def transcribe(self, audio_f32: np.ndarray) -> str:
        if self._model is None:
            return ""
        try:
            # Ensure mono float32 at 16 kHz (faster-whisper expects this)
            if audio_f32.ndim > 1:
                audio_f32 = audio_f32.mean(axis=1)
            segments, _ = self._model.transcribe(
                audio_f32, beam_size=5, language="en",
                vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return text
        except Exception as exc:
            print(f"[audio] Whisper error: {exc}")
            return ""


# ════════════════════════════════════════════════════════════════════════════
# MIC CAPTURE THREAD  (sounddevice + SpeechRecognition fallback)
# ════════════════════════════════════════════════════════════════════════════

class MicCaptureThread(threading.Thread):
    """
    Captures microphone audio using sounddevice + faster-whisper.
    Falls back to SpeechRecognition (Google Cloud / browser API) if Whisper not available.
    """
    SAMPLE_RATE = 16000
    CHUNK_SECONDS = 4          # collect 4 seconds before transcribing
    SILENCE_CHUNKS = 3         # 3 consecutive silent chunks → push segment

    def __init__(
        self,
        on_transcript: Callable[[str, str], None],
        transcriber: LocalTranscriber,
        vad: VAD,
    ):
        super().__init__(daemon=True)
        self.on_transcript = on_transcript
        self.transcriber = transcriber
        self.vad = vad
        self._stop_event = threading.Event()
        self._buffer: list[np.ndarray] = []
        self._silence_count = 0
        self._speaking = False

    def run(self):
        if HAS_SD:
            self._run_sounddevice()
        elif HAS_SR:
            self._run_speech_recognition()
        else:
            print("[audio] No mic capture backend available")

    def _run_sounddevice(self):
        print("[audio] Mic capture started (sounddevice)")
        CHUNK = int(self.SAMPLE_RATE * 0.032)   # 32 ms

        def callback(indata: np.ndarray, frames, time_info, status):
            if self._stop_event.is_set():
                raise sd.CallbackAbort()
            audio_int16 = (indata[:, 0] * 32767).astype(np.int16).tobytes()
            is_speech = self.vad.is_speech(audio_int16, self.SAMPLE_RATE)
            if is_speech:
                self._buffer.append(indata.copy()[:, 0])
                self._speaking = True
                self._silence_count = 0
            elif self._speaking:
                self._silence_count += 1
                if self._silence_count >= self.SILENCE_CHUNKS:
                    # End of utterance — transcribe and push
                    self._flush_buffer()

        try:
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=CHUNK,
                callback=callback,
            ):
                while not self._stop_event.is_set():
                    time.sleep(0.1)
        except Exception as exc:
            if not self._stop_event.is_set():
                print(f"[audio] Mic capture error: {exc}")

    def _run_speech_recognition(self):
        """SpeechRecognition fallback (uses Google Web Speech API)."""
        print("[audio] Mic capture started (SpeechRecognition fallback)")
        recognizer = sr.Recognizer()
        recognizer.phrase_threshold = 0.3
        recognizer.dynamic_energy_threshold = True
        mic = sr.Microphone(sample_rate=self.SAMPLE_RATE)

        def callback(recognizer, audio):
            try:
                text = recognizer.recognize_google(audio)
                if text:
                    self.on_transcript("You", text)
            except sr.UnknownValueError:
                pass
            except Exception as exc:
                print(f"[audio] SR error: {exc}")

        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)

        stop_fn = recognizer.listen_in_background(mic, callback, phrase_time_limit=10)
        while not self._stop_event.is_set():
            time.sleep(0.5)
        stop_fn(wait_for_stop=False)

    def _flush_buffer(self):
        if not self._buffer:
            return
        audio = np.concatenate(self._buffer)
        self._buffer = []
        self._speaking = False
        self._silence_count = 0

        text = self.transcriber.transcribe(audio)
        if text and len(text.strip()) > 2:
            self.on_transcript("You", text)

    def stop(self):
        self._stop_event.set()


# ════════════════════════════════════════════════════════════════════════════
# SYSTEM AUDIO CAPTURE THREAD  (WASAPI loopback on Windows / BlackHole on macOS)
# ════════════════════════════════════════════════════════════════════════════

class SystemAudioCaptureThread(threading.Thread):
    """
    Captures system audio (other people on the call) using:
    • Windows: PyAudioWPatch WASAPI loopback (undetectable, no virtual device)
    • macOS: sounddevice pointing at BlackHole or Aggregate Device
    • Linux: sounddevice pointing at monitor device (PulseAudio/PipeWire)
    """
    SAMPLE_RATE = 16000
    SILENCE_CHUNKS = 4         # 4 × 32ms silent after speech → flush
    MIN_SPEECH_CHUNKS = 3      # ignore bursts < 3 chunks (noise)

    def __init__(
        self,
        on_transcript: Callable[[str, str], None],
        transcriber: LocalTranscriber,
        vad: VAD,
    ):
        super().__init__(daemon=True)
        self.on_transcript = on_transcript
        self.transcriber = transcriber
        self.vad = vad
        self._stop_event = threading.Event()
        self._buffer: list[np.ndarray] = []
        self._silence_count = 0
        self._speech_count = 0
        self._speaking = False

    def run(self):
        if sys.platform == "win32" and HAS_WASAPI:
            self._run_wasapi()
        elif HAS_SD:
            self._run_sounddevice_monitor()
        else:
            print("[audio] System audio capture unavailable")

    def _process_chunk(self, audio_f32: np.ndarray) -> None:
        """VAD + buffer logic shared by WASAPI and sounddevice monitor paths."""
        audio_int16 = (audio_f32 * 32767).astype(np.int16).tobytes()
        if self.vad.is_speech(audio_int16, self.SAMPLE_RATE):
            self._buffer.append(audio_f32)
            self._speech_count += 1
            self._speaking = True
            self._silence_count = 0
        elif self._speaking:
            self._silence_count += 1
            if self._silence_count >= self.SILENCE_CHUNKS:
                if self._speech_count >= self.MIN_SPEECH_CHUNKS:
                    self._flush_buffer()
                else:
                    self._buffer = []
                    self._speaking = False
                    self._speech_count = 0
                    self._silence_count = 0

    def _resample(self, audio_f32: np.ndarray, from_rate: int) -> np.ndarray:
        """Linear resample from_rate → SAMPLE_RATE. No-op if rates match."""
        if from_rate == self.SAMPLE_RATE:
            return audio_f32
        new_len = int(len(audio_f32) * self.SAMPLE_RATE / from_rate)
        return np.interp(
            np.linspace(0, len(audio_f32), new_len),
            np.arange(len(audio_f32)),
            audio_f32,
        ).astype(np.float32)

    def _run_wasapi(self):
        """WASAPI loopback — completely undetectable, reads render buffer directly."""
        print("[audio] System audio capture started (WASAPI loopback)")
        p = pyaudio.PyAudio()
        try:
            loopback = p.get_default_wasapi_loopback()
            device_rate = int(loopback["defaultSampleRate"])
            device_channels = min(loopback["maxInputChannels"], 2)
            CHUNK = 1024

            stream = p.open(
                format=pyaudio.paFloat32,
                channels=device_channels,
                rate=device_rate,
                input=True,
                input_device_index=loopback["index"],
                frames_per_buffer=CHUNK,
            )
            print(f"   Device: {loopback['name']!r} @ {device_rate} Hz")

            while not self._stop_event.is_set():
                try:
                    raw = stream.read(CHUNK, exception_on_overflow=False)
                except Exception:
                    continue

                audio_f32 = np.frombuffer(raw, dtype=np.float32)
                if device_channels > 1:
                    audio_f32 = audio_f32.reshape(-1, device_channels).mean(axis=1)
                audio_f32 = self._resample(audio_f32, device_rate)
                self._process_chunk(audio_f32)

            stream.stop_stream()
            stream.close()
        finally:
            p.terminate()

    def _run_sounddevice_monitor(self):
        """
        macOS/Linux: capture from monitor/loopback device.
        On macOS, user must select BlackHole or Aggregate Device.
        On Linux, PulseAudio monitor devices appear automatically.
        """
        print("[audio] System audio capture started (sounddevice monitor)")

        device_idx = self._find_loopback_device()
        if device_idx is None:
            print("[audio] No loopback device found. On macOS, install BlackHole.")
            print("   Download: https://github.com/ExistentialAudio/BlackHole")
            return

        CHUNK = int(self.SAMPLE_RATE * 0.032)

        def callback(indata: np.ndarray, frames, time_info, status):
            if self._stop_event.is_set():
                raise sd.CallbackAbort()
            self._process_chunk(indata.copy()[:, 0])

        try:
            with sd.InputStream(
                device=device_idx,
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=CHUNK,
                callback=callback,
            ):
                while not self._stop_event.is_set():
                    time.sleep(0.1)
        except Exception as exc:
            if not self._stop_event.is_set():
                print(f"[audio] System audio error: {exc}")

    def _find_loopback_device(self) -> Optional[int]:
        if not HAS_SD:
            return None
        keywords = ["blackhole", "monitor", "loopback", "virtual", "stereo mix", "what u hear"]
        try:
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                name_lower = dev["name"].lower()
                if dev["max_input_channels"] > 0:
                    if any(kw in name_lower for kw in keywords):
                        print(f"   Loopback device: [{i}] {dev['name']}")
                        return i
        except Exception:
            pass
        return None

    def _flush_buffer(self):
        if not self._buffer:
            return
        audio = np.concatenate(self._buffer)
        self._buffer = []
        self._speaking = False
        self._speech_count = 0
        self._silence_count = 0

        text = self.transcriber.transcribe(audio)
        if text and len(text.strip()) > 2:
            self.on_transcript("Them", text)

    def stop(self):
        self._stop_event.set()


# ════════════════════════════════════════════════════════════════════════════
# AUDIO ENGINE  (top-level orchestrator)
# ════════════════════════════════════════════════════════════════════════════

class AudioEngine:
    """
    Top-level audio orchestrator.

    Usage:
        def on_transcript(speaker: str, text: str):
            print(f"{speaker}: {text}")

        engine = AudioEngine(on_transcript=on_transcript)
        engine.start()
        ...
        engine.stop()
    """

    def __init__(
        self,
        on_transcript: Callable[[str, str], None],
        whisper_model: str = "base",
    ):
        self._callback = on_transcript
        self._vad = VAD()
        self._transcriber = LocalTranscriber(whisper_model)
        self._mic_thread: Optional[MicCaptureThread] = None
        self._sys_thread: Optional[SystemAudioCaptureThread] = None
        self._active = False

    def start(self):
        if self._active:
            return
        self._active = True
        print("[audio] AudioEngine starting")

        self._mic_thread = MicCaptureThread(self._callback, self._transcriber, self._vad)
        self._mic_thread.start()

        self._sys_thread = SystemAudioCaptureThread(self._callback, self._transcriber, self._vad)
        self._sys_thread.start()

        print("[audio] AudioEngine running (mic + system audio)")

    def stop(self):
        if not self._active:
            return
        self._active = False
        if self._mic_thread:
            self._mic_thread.stop()
        if self._sys_thread:
            self._sys_thread.stop()
        print("[audio] AudioEngine stopped")

    @property
    def active(self) -> bool:
        return self._active
