import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Whitelisted meeting URL patterns - SSRF prevention
MEETING_URL_PATTERNS = [
    # Zoom: only zoom.us - no subdomain wildcard
    re.compile(r"https://zoom\.us/j/\d{9,11}$"),
    # Zoom vanity: company.zoom.us - single label subdomain only
    re.compile(r"https://[a-zA-Z0-9-]{1,63}\.zoom\.us/j/\d{9,11}$"),
    # Teams: exact domain, path is base64url encoded segment
    re.compile(
        r"https://teams\.microsoft\.com/l/meetup-join/[a-zA-Z0-9%._~:@!$&'()*+,;=/-]{10,500}$"
    ),
    # Google Meet: exact pattern - 3-4-3 letter code only
    re.compile(r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}$"),
    # Webex: only webex.com - no subdomain wildcard
    re.compile(r"https://webex\.com/[a-zA-Z0-9/_-]{5,200}$"),
    # Webex with www
    re.compile(r"https://www\.webex\.com/[a-zA-Z0-9/_-]{5,200}$"),
]

RECALL_API_BASE = "https://api.recall.ai/api/v1"


class RecallClient:
    """
    Thin async client for the Recall.ai REST API.

    Recall.ai joins video calls as a bot and streams
    real-time transcripts via webhook or WebSocket.

    SECURITY:
    - RECALL_API_KEY read from env only - never hardcoded
    - Meeting URLs validated against whitelist before API call (SSRF prevention)
    - All HTTP calls use timeout to prevent hanging
    """

    def __init__(self) -> None:
        api_key = os.environ.get("RECALL_API_KEY", "")
        if not api_key:
            raise EnvironmentError(
                "RECALL_API_KEY not set in environment. "
                "Add it to your .env file."
            )
        self._headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        }
        self._timeout = httpx.Timeout(30.0)

    def validate_meeting_url(self, url: str) -> bool:
        """
        Validates URL against strict whitelist of meeting platform patterns.
        Uses fullmatch - patterns are anchored with $ but fullmatch adds safety.
        Rejects: localhost, internal IPs, unknown domains, http://, wildcards.
        """
        if not url.startswith("https://"):
            return False
        return any(pattern.fullmatch(url) for pattern in MEETING_URL_PATTERNS)

    async def bot_spawn(
        self,
        meeting_url: str,
        bot_name: str = "MeetAI Assistant",
        webhook_url: str | None = None,
    ) -> dict[str, Any]:
        """
        Spawn a Recall.ai bot to join a meeting.
        meeting_url: validated meeting URL (Zoom/Teams/Meet/Webex only)
        bot_name: display name shown in the meeting
        webhook_url: optional URL for Recall to POST transcript events
        Returns Recall.ai bot object with id, status, meeting_url fields.
        Raises ValueError if URL not whitelisted.
        Raises httpx.HTTPStatusError on API failure.
        """
        if not self.validate_meeting_url(meeting_url):
            raise ValueError(
                f"Meeting URL not allowed: {meeting_url}. "
                "Only Zoom, Teams, Google Meet, and Webex URLs are accepted."
            )

        payload: dict[str, Any] = {
            "meeting_url": meeting_url,
            "bot_name": bot_name,
            "transcription_options": {
                "provider": "assembly_ai",
            },
        }
        if webhook_url:
            payload["real_time_transcription"] = {
                "destination_url": webhook_url,
            }

        async with httpx.AsyncClient(
            headers=self._headers, timeout=self._timeout
        ) as client:
            response = await client.post(f"{RECALL_API_BASE}/bot/", json=payload)
            response.raise_for_status()
            data = response.json()
            logger.info("Bot spawned: id=%s url=%s", data.get("id"), meeting_url)
            return data

    async def bot_get_status(self, bot_id: str) -> dict[str, Any]:
        """
        Get current status of a running bot.
        bot_id: Recall.ai bot ID string
        Returns bot status dict with fields: id, status_changes, meeting_url.
        """
        if not re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", bot_id):
            raise ValueError(f"Invalid bot_id format: {bot_id!r}")

        async with httpx.AsyncClient(
            headers=self._headers, timeout=self._timeout
        ) as client:
            response = await client.get(f"{RECALL_API_BASE}/bot/{bot_id}/")
            response.raise_for_status()
            return response.json()

    async def bot_leave(self, bot_id: str) -> dict[str, Any]:
        """
        Instruct a bot to leave the meeting.
        Returns updated bot status.
        """
        if not re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", bot_id):
            raise ValueError(f"Invalid bot_id format: {bot_id!r}")

        async with httpx.AsyncClient(
            headers=self._headers, timeout=self._timeout
        ) as client:
            response = await client.post(f"{RECALL_API_BASE}/bot/{bot_id}/leave_call/")
            response.raise_for_status()
            logger.info("Bot %s instructed to leave", bot_id)
            return response.json()
