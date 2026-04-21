import functools
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

REPORT_DIR = Path("./backend/profiling")
REPORT_PATH = REPORT_DIR / "performance_results.json"


# -- LATENCY DECORATOR -------------------------------------------------
def measure_latency(label: str):
    """
    Decorator that measures execution time of sync or async functions.
    Records P50/P95 latency across multiple calls.
    Usage:
        @measure_latency("voice.generate_streaming")
        async def generate_streaming(self, ...): ...
    """

    def decorator(fn: Callable) -> Callable:
        import asyncio

        results_store: list[float] = []

        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                start = time.perf_counter()
                result = await fn(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                results_store.append(elapsed_ms)
                logger.debug(f"[PERF] {label}: {elapsed_ms:.1f}ms")
                LatencyRegistry.record(label, elapsed_ms)
                return result

            async_wrapper._perf_results = results_store  # type: ignore[attr-defined]
            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = fn(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            results_store.append(elapsed_ms)
            logger.debug(f"[PERF] {label}: {elapsed_ms:.1f}ms")
            LatencyRegistry.record(label, elapsed_ms)
            return result

        sync_wrapper._perf_results = results_store  # type: ignore[attr-defined]
        return sync_wrapper

    return decorator


class LatencyRegistry:
    """Thread-safe store for latency measurements."""

    _lock = threading.Lock()
    _data: dict[str, list[float]] = {}

    @classmethod
    def record(cls, label: str, ms: float) -> None:
        with cls._lock:
            if label not in cls._data:
                cls._data[label] = []
            cls._data[label].append(ms)

    @classmethod
    def percentile(cls, label: str, pct: float) -> float | None:
        with cls._lock:
            values = sorted(cls._data.get(label, []))
        if not values:
            return None
        idx = int(len(values) * pct / 100)
        return values[min(idx, len(values) - 1)]

    @classmethod
    def summary(cls) -> dict[str, dict]:
        with cls._lock:
            labels = list(cls._data.keys())
        result: dict[str, dict] = {}
        for label in labels:
            with cls._lock:
                values = sorted(cls._data[label])
            if not values:
                continue
            result[label] = {
                "count": len(values),
                "p50_ms": round(values[len(values) // 2], 2),
                "p95_ms": round(values[int(len(values) * 0.95)], 2),
                "min_ms": round(values[0], 2),
                "max_ms": round(values[-1], 2),
                "mean_ms": round(sum(values) / len(values), 2),
            }
        return result

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._data.clear()


# -- FPS METER ---------------------------------------------------------
class FPSMeter:
    """
    Measures average FPS for FaceSwapEngine during a mock session.
    Call tick() on each processed frame, then report() for results.
    """

    def __init__(self, session_duration_seconds: int = 60):
        self.duration = session_duration_seconds
        self._frames = 0
        self._start: float | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            self._start = time.perf_counter()
            self._frames = 0

    def tick(self) -> None:
        """Call once per processed frame."""
        with self._lock:
            self._frames += 1

    def report(self) -> dict:
        with self._lock:
            elapsed = time.perf_counter() - (self._start or time.perf_counter())
            frames = self._frames
        if elapsed <= 0:
            return {"fps": 0, "frames": 0, "duration_s": 0}
        fps = frames / elapsed
        return {
            "fps": round(fps, 2),
            "frames": frames,
            "duration_s": round(elapsed, 2),
            "target_fps": 30,
            "meets_target": fps >= 24,
        }


# -- RESOURCE MONITOR --------------------------------------------------
class ResourceMonitor:
    """
    Samples CPU, RAM, and NVIDIA VRAM usage at regular intervals.
    Runs in a background thread - call start() then stop().
    """

    def __init__(self, interval_seconds: float = 5.0):
        self.interval = interval_seconds
        self._samples: list[dict] = []
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()
        logger.info("ResourceMonitor started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def _sample_loop(self) -> None:
        while self._running:
            self._samples.append(self._take_sample())
            time.sleep(self.interval)

    def _take_sample(self) -> dict:
        sample: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            import psutil

            sample["cpu_percent"] = psutil.cpu_percent(interval=1)
            sample["ram_used_mb"] = round(psutil.Process().memory_info().rss / 1e6, 1)
            sample["ram_total_mb"] = round(psutil.virtual_memory().total / 1e6, 1)
        except ImportError:
            sample["cpu_percent"] = None
            sample["ram_used_mb"] = None

        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                sample["gpu_name"] = gpu.name
                sample["vram_used_mb"] = round(gpu.memoryUsed, 1)
                sample["vram_total_mb"] = round(gpu.memoryTotal, 1)
                sample["gpu_load_pct"] = round(gpu.load * 100, 1)
        except (ImportError, Exception):
            sample["vram_used_mb"] = None
            sample["gpu_name"] = "unavailable"

        return sample

    def report(self) -> dict:
        if not self._samples:
            return {}
        cpu = [s["cpu_percent"] for s in self._samples if s.get("cpu_percent")]
        ram = [s["ram_used_mb"] for s in self._samples if s.get("ram_used_mb")]
        vram = [s["vram_used_mb"] for s in self._samples if s.get("vram_used_mb")]
        return {
            "sample_count": len(self._samples),
            "cpu_mean_pct": round(sum(cpu) / len(cpu), 1) if cpu else None,
            "cpu_max_pct": round(max(cpu), 1) if cpu else None,
            "ram_mean_mb": round(sum(ram) / len(ram), 1) if ram else None,
            "ram_max_mb": round(max(ram), 1) if ram else None,
            "vram_mean_mb": round(sum(vram) / len(vram), 1) if vram else None,
            "vram_max_mb": round(max(vram), 1) if vram else None,
            "gpu_name": self._samples[-1].get("gpu_name"),
        }


# -- REPORT GENERATOR --------------------------------------------------
def generate_report(
    fps_report: dict | None = None, resource_report: dict | None = None
) -> Path:
    """
    Combine all profiling data into a single JSON report.
    Gemini uses this JSON to write performance_report.md.
    """

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latency": LatencyRegistry.summary(),
        "fps": fps_report or {},
        "resources": resource_report or {},
        "targets": {
            "voice_p95_ms": 200,
            "face_fps_min": 24,
            "rag_query_ms": 500,
        },
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    logger.info(f"Performance report written to {REPORT_PATH}")
    return REPORT_PATH

