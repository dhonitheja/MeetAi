import asyncio
import time

import numpy as np

from backend.profiling.profiler import (
    FPSMeter,
    LatencyRegistry,
    ResourceMonitor,
    generate_report,
    measure_latency,
)


async def profile_voice_pipeline() -> None:
    """Profile VoxCPM2 streaming latency (requires model loaded)."""
    print("Profiling voice pipeline...")
    try:
        from backend.voice.voice_clone_engine import VoiceCloneEngine

        engine = VoiceCloneEngine()
        engine.load()

        @measure_latency("voice.generate_streaming.first_chunk")
        async def time_first_chunk(text: str):
            async for chunk in engine.generate_streaming(text, None):
                return chunk  # only time first chunk
            return None

        for i in range(10):
            try:
                await time_first_chunk(
                    f"Test sentence number {i} for latency measurement."
                )
            except Exception:
                pass

        engine.unload()
    except Exception as e:
        print(f"Voice profiling skipped: {e}")


def profile_face_pipeline() -> dict:
    """Profile InsightFace FPS on mock frames."""
    print("Profiling face pipeline...")
    meter = FPSMeter(session_duration_seconds=10)
    meter.start()

    try:
        from backend.face.face_swap_engine import FaceSwapEngine

        engine = FaceSwapEngine()
        engine.load()

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        @measure_latency("face.process_frame")
        def time_frame() -> None:
            engine.process_frame(frame)

        deadline = time.perf_counter() + meter.duration
        while time.perf_counter() < deadline:
            try:
                time_frame()
            except Exception:
                pass
            meter.tick()

        engine.unload()
    except Exception as e:
        print(f"Face profiling skipped: {e}")

    return meter.report()


def profile_rag_pipeline() -> None:
    """Profile RAG query latency."""
    print("Profiling RAG pipeline...")
    try:
        from backend.rag.document_store import DocumentStore

        store = DocumentStore()

        @measure_latency("rag.query")
        def timed_query(text: str):
            return store.query(text=text, n_results=4)

        for i in range(20):
            try:
                timed_query(f"What should I focus on in this meeting context? #{i}")
            except Exception:
                pass
    except Exception as e:
        print(f"RAG profiling skipped: {e}")


async def main() -> None:
    LatencyRegistry.reset()
    monitor = ResourceMonitor(interval_seconds=5.0)
    monitor.start()

    fps_report: dict = {}
    try:
        await profile_voice_pipeline()
        fps_report = profile_face_pipeline()
        profile_rag_pipeline()
    finally:
        monitor.stop()

    resource_report = monitor.report()
    report_path = generate_report(
        fps_report=fps_report,
        resource_report=resource_report,
    )

    print("\nProfiling complete.")
    print(f"Report: {report_path}")
    print(f"Latency labels: {list(LatencyRegistry.summary().keys())}")


if __name__ == "__main__":
    asyncio.run(main())

