from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class TranscriptLine:
    """Single sanitized transcript line from a meeting stream."""

    speaker: str
    text: str
    timestamp: str
    meeting_id: str


@dataclass
class MeetingTranscript:
    """Buffered transcript state for one meeting/bot id."""

    meeting_id: str
    lines: list[TranscriptLine] = field(default_factory=list)
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class TranscriptHandler:
    """
    Processes real-time transcript events from Recall.ai webhook.

    Recall.ai POSTs JSON events to /meeting/webhook.
    This handler parses them, extracts speaker + text,
    and updates the shared rolling buffer that CoPilotEngine reads.

    SECURITY:
    - Webhook HMAC signature validated before any processing
    - Raw event data sanitized before storage
    - Thread-safe buffer updates via threading.Lock
    """

    def __init__(self, on_new_line: Callable[[TranscriptLine], None] | None = None) -> None:
        """
        Initialize the transcript handler and in-memory store.

        Args:
            on_new_line: Optional callback fired for each new transcript line.
                Can be used to trigger real-time suggestion generation.
        """
        self._lock = threading.Lock()
        self._transcripts: dict[str, MeetingTranscript] = {}
        self._listeners: list[Callable[[TranscriptLine], None]] = []
        if on_new_line:
            self._listeners.append(on_new_line)

    def add_listener(self, callback: Callable[[TranscriptLine], None]) -> None:
        """Register a new transcript line listener."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[TranscriptLine], None]) -> None:
        """Unregister a transcript line listener."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Validate Recall.ai HMAC-SHA256 webhook signature.
        RECALL_WEBHOOK_SECRET from env only.
        Returns False (not raise) if secret missing - logs CRITICAL.
        Uses hmac.compare_digest to prevent timing attacks.
        """
        secret = os.environ.get("RECALL_WEBHOOK_SECRET", "")
        if not secret:
            logger.critical(
                "RECALL_WEBHOOK_SECRET not set. "
                "All webhook requests will be rejected."
            )
            return False

        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _sanitize_text(self, text: str) -> str:
        """Strip control characters from transcript text."""
        clean = re.sub(r"[\x00-\x1f\x7f]", " ", text)
        return clean[:1000].strip()

    def _sanitize_speaker(self, name: str) -> str:
        """Sanitize speaker name - alphanumeric + spaces only."""
        clean = re.sub(r"[^a-zA-Z0-9 _-]", "", name)
        return clean[:64].strip() or "Unknown"

    def process_event(self, data: dict[str, Any]) -> TranscriptLine | None:
        """
        Parse a Recall.ai webhook transcript event.
        Thread-safe append to in-memory meeting transcripts.
        Note: uses fine-grained locking to minimize contention but remains 
        susceptible to low-probability race if same bot sends overlapping events.
        Expected format:
        {
            "event": "transcript.data",
            "data": {
                "bot_id": str,
                "transcript": {
                    "speaker": str,
                    "words": [{"text": str, ...}]
                }
            }
        }
        Returns TranscriptLine if successfully parsed, None otherwise.
        Updates internal transcript buffer. Thread-safe.
        """
        try:
            event_type = data.get("event", "")
            if event_type not in ("transcript.data", "transcript.partial_data"):
                return None

            inner = data.get("data", {})
            bot_id = str(inner.get("bot_id", "unknown"))
            transcript = inner.get("transcript", {})

            speaker_raw = str(transcript.get("speaker", "Unknown"))
            words = transcript.get("words", [])
            text_raw = " ".join(
                str(word.get("text", "")) for word in words if isinstance(word, dict)
            )

            speaker = self._sanitize_speaker(speaker_raw)
            text = self._sanitize_text(text_raw)
            if not text:
                return None

            line = TranscriptLine(
                speaker=speaker,
                text=text,
                timestamp=datetime.now(timezone.utc).isoformat(),
                meeting_id=bot_id,
            )

            with self._lock:
                if bot_id not in self._transcripts:
                    self._transcripts[bot_id] = MeetingTranscript(meeting_id=bot_id)
                self._transcripts[bot_id].lines.append(line)
                current_listeners = list(self._listeners)

            for listener in current_listeners:
                try:
                    listener(line)
                except Exception as exc:
                    logger.error("transcript listener failed: %s", exc)

            return line
        except Exception as exc:
            logger.error("Failed to process transcript event: %s", exc)
            return None

    def get_transcript(self, meeting_id: str) -> MeetingTranscript | None:
        """Return full transcript for a meeting. Thread-safe."""
        with self._lock:
            return self._transcripts.get(meeting_id)

    def get_recent_lines(self, meeting_id: str, n: int = 10) -> list[TranscriptLine]:
        """Return last N transcript lines for a meeting."""
        with self._lock:
            transcript = self._transcripts.get(meeting_id)
            if not transcript:
                return []
            return transcript.lines[-n:]

    def clear_meeting(self, meeting_id: str) -> None:
        """Remove transcript data for a completed meeting."""
        with self._lock:
            self._transcripts.pop(meeting_id, None)
