from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, field_validator

from backend.meeting.recall_client import RecallClient
from backend.meeting.transcript_handler import TranscriptHandler

logger = logging.getLogger(__name__)

meeting_router = APIRouter(prefix="/meeting", tags=["meeting"])

_recall: Optional[RecallClient] = None
_handler: Optional[TranscriptHandler] = None
_active_bots: dict[str, dict] = {}

BOT_ID_PATTERN = re.compile(r"[a-zA-Z0-9_-]{8,64}")


def get_recall() -> RecallClient:
    global _recall
    if _recall is None:
        _recall = RecallClient()
    return _recall


def get_handler() -> TranscriptHandler:
    global _handler
    if _handler is None:
        _handler = TranscriptHandler()
    return _handler


def _validate_bot_id(bot_id: str) -> str:
    if not BOT_ID_PATTERN.fullmatch(bot_id):
        raise HTTPException(400, "Invalid bot_id format")
    return bot_id


class JoinRequest(BaseModel):
    url: str
    bot_name: str = "MeetAI Assistant"

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        try:
            client = RecallClient()
        except EnvironmentError as exc:
            raise ValueError(str(exc)) from exc
        if not client.validate_meeting_url(v):
            raise ValueError(
                "URL must be a valid Zoom, Teams, Google Meet, or Webex link"
            )
        return v

    @field_validator("bot_name")
    @classmethod
    def validate_bot_name(cls, v: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9 _-]", "", v).strip()
        if not clean:
            raise ValueError("bot_name cannot be empty")
        return clean[:64]


class SummarizeRequest(BaseModel):
    bot_id: str

    @field_validator("bot_id")
    @classmethod
    def validate_bot_id(cls, v: str) -> str:
        if not BOT_ID_PATTERN.fullmatch(v):
            raise ValueError("Invalid bot_id format")
        return v


@meeting_router.post("/join")
async def join_meeting(req: JoinRequest):
    """Spawn a Recall.ai bot. URL validated against whitelist before API call."""
    recall = get_recall()
    webhook_url = os.environ.get("RECALL_WEBHOOK_URL")
    try:
        bot = await recall.bot_spawn(
            meeting_url=req.url,
            bot_name=req.bot_name,
            webhook_url=webhook_url,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        logger.error("Bot spawn failed: %s", e)
        raise HTTPException(502, "Failed to spawn meeting bot. Check RECALL_API_KEY.") from e

    bot_id_raw = bot.get("id")
    if not isinstance(bot_id_raw, str):
        raise HTTPException(502, "Recall returned invalid bot ID")
    bot_id = _validate_bot_id(bot_id_raw)

    _active_bots[bot_id] = {
        "url": req.url,
        "bot_name": req.bot_name,
        "status": "joining",
    }
    return {"status": "joining", "bot_id": bot_id, "meeting_url": req.url}


@meeting_router.get("/status/{bot_id}")
async def bot_status(bot_id: str):
    """Get current bot status from Recall.ai."""
    validated_bot_id = _validate_bot_id(bot_id)
    recall = get_recall()
    try:
        return await recall.bot_get_status(validated_bot_id)
    except Exception as e:
        logger.error("Status check failed for %s: %s", validated_bot_id, e)
        raise HTTPException(502, "Failed to get bot status") from e


@meeting_router.post("/leave/{bot_id}")
async def leave_meeting(bot_id: str):
    """Instruct bot to leave the meeting."""
    validated_bot_id = _validate_bot_id(bot_id)
    recall = get_recall()
    try:
        result = await recall.bot_leave(validated_bot_id)
        _active_bots.pop(validated_bot_id, None)
        return result
    except Exception as e:
        raise HTTPException(502, f"Failed to leave meeting: {e}") from e


@meeting_router.post("/webhook")
async def recall_webhook(
    request: Request,
    x_recall_signature: Optional[str] = Header(None, alias="X-Recall-Signature"),
):
    """
    Receive real-time transcript events from Recall.ai.

    SECURITY: HMAC signature is validated BEFORE any payload processing.
    Requests without a valid signature are rejected with HTTP 401.
    No transcript data is read, parsed, or stored until signature passes.
    """
    # Read raw bytes before parsing so HMAC can be validated.
    payload = await request.body()

    # Step 1: reject missing signature immediately.
    if not x_recall_signature:
        logger.warning("Webhook received without X-Recall-Signature - rejected")
        raise HTTPException(401, "Missing X-Recall-Signature header")

    # Step 2: validate HMAC before any parsing/processing.
    handler = get_handler()
    if not handler.verify_webhook_signature(payload, x_recall_signature):
        logger.warning("Webhook HMAC validation failed - rejected")
        raise HTTPException(401, "Invalid webhook signature")

    # Step 3: parse only after signature validation succeeds.
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Invalid JSON payload") from exc

    line = handler.process_event(data)
    return {"status": "ok", "line_processed": line is not None}


@meeting_router.post("/summarize")
async def summarize_meeting(req: SummarizeRequest):
    """Generate post-meeting summary with action items."""
    validated_bot_id = _validate_bot_id(req.bot_id)
    handler = get_handler()
    transcript = handler.get_transcript(validated_bot_id)

    if not transcript or not transcript.lines:
        raise HTTPException(404, f"No transcript found for bot {validated_bot_id}")

    formatted = "\n".join(f"{line.speaker}: {line.text}" for line in transcript.lines)

    try:
        from server import get_completion

        summary = await get_completion(
            system=(
                "You are a meeting summarizer. Extract: "
                "1. Key decisions made. "
                "2. Action items with owners. "
                "3. Next steps. "
                "Format as structured bullet points."
            ),
            user=("Summarize this meeting transcript:\n\n" f"{formatted[:8000]}"),
            model="default",
        )
    except Exception as e:
        logger.error("Summarization failed: %s", e)
        raise HTTPException(500, "Summary generation failed") from e

    handler.clear_meeting(validated_bot_id)
    return {"bot_id": validated_bot_id, "summary": summary}


@meeting_router.get("/active")
async def list_active_bots():
    """List all currently active bots."""
    return {"bots": _active_bots}
