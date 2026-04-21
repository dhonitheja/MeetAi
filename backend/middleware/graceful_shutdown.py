import asyncio
import logging

logger = logging.getLogger(__name__)


async def shutdown_voice_engine() -> None:
    """Release VoxCPM2 model and GPU memory."""
    try:
        from backend.routers import voice as voice_module

        if voice_module._engine is not None:
            voice_module._engine.unload()
            logger.info("shutdown_complete", extra={"component": "voice_engine"})
    except Exception as e:
        logger.error("shutdown_failed", extra={"component": "voice_engine", "error": str(e)})


async def shutdown_face_engine() -> None:
    """Release InsightFace + inswapper models and GPU memory."""
    try:
        from backend.routers import face as face_module

        if face_module._engine is not None:
            face_module._engine.unload()
            logger.info("shutdown_complete", extra={"component": "face_engine"})
    except Exception as e:
        logger.error("shutdown_failed", extra={"component": "face_engine", "error": str(e)})


async def shutdown_chroma() -> None:
    """Release ChromaDB store reference; PersistentClient auto-persists."""
    try:
        from backend.routers import rag as rag_module

        if rag_module._store is not None:
            # ChromaDB >= 0.4.0: PersistentClient persists automatically.
            # No explicit persist() call needed.
            rag_module._store = None
            logger.info("ChromaDB shutdown clean")
    except Exception as e:
        logger.warning("chroma_shutdown_note", extra={"detail": str(e)})


async def shutdown_recall_bots() -> None:
    """Instruct any active Recall.ai bots to leave before shutdown."""
    try:
        from backend.routers import meeting as meeting_module

        active = dict(meeting_module._active_bots)
        if not active:
            return
        recall = meeting_module.get_recall()
        for bot_id in active:
            try:
                await recall.bot_leave(bot_id)
                logger.info("bot_left_on_shutdown", extra={"bot_id": bot_id})
            except Exception as e:
                logger.warning("bot_leave_failed", extra={"bot_id": bot_id, "error": str(e)})
        meeting_module._active_bots.clear()
    except Exception as e:
        logger.error("shutdown_failed", extra={"component": "recall_bots", "error": str(e)})


async def run_graceful_shutdown() -> None:
    """
    Run all shutdown handlers concurrently with timeout.
    Each handler is isolated - one failure does not block others.
    Total timeout: 10 seconds before forced exit.
    """
    logger.info("graceful_shutdown_started")

    handlers = [
        shutdown_voice_engine(),
        shutdown_face_engine(),
        shutdown_chroma(),
        shutdown_recall_bots(),
    ]

    try:
        await asyncio.wait_for(
            asyncio.gather(*handlers, return_exceptions=True),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        logger.error("graceful_shutdown_timeout", extra={"timeout_seconds": 10})

    logger.info("graceful_shutdown_complete")
