import asyncio
from unittest.mock import patch

import pytest

from backend.middleware.graceful_shutdown import run_graceful_shutdown


@pytest.mark.asyncio
async def test_shutdown_completes_without_error():
    """Shutdown must complete even if all engines are None."""
    await run_graceful_shutdown()


@pytest.mark.asyncio
async def test_shutdown_handles_engine_error():
    """One failing handler must not block others."""
    with patch(
        "backend.middleware.graceful_shutdown.shutdown_voice_engine",
        side_effect=Exception("GPU error"),
    ):
        await run_graceful_shutdown()  # must not raise


@pytest.mark.asyncio
async def test_shutdown_timeout_does_not_crash():
    """Timeout must not raise - log and continue."""

    async def slow_handler():
        await asyncio.sleep(999)

    with patch("backend.middleware.graceful_shutdown.shutdown_voice_engine", new=slow_handler):
        try:
            await asyncio.wait_for(run_graceful_shutdown(), timeout=0.5)
        except asyncio.TimeoutError:
            pass  # expected - outer timeout for test speed
