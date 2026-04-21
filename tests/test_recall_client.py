import asyncio
import os

import pytest

os.environ["RECALL_API_KEY"] = "test-key-placeholder"

from backend.meeting.recall_client import RecallClient


def test_validate_zoom_url() -> None:
    c = RecallClient()
    assert c.validate_meeting_url("https://zoom.us/j/123456789")
    assert c.validate_meeting_url("https://company.zoom.us/j/987654321")


def test_validate_teams_url() -> None:
    c = RecallClient()
    assert c.validate_meeting_url(
        "https://teams.microsoft.com/l/meetup-join/abc123def456ghi789"
    )


def test_validate_meet_url() -> None:
    c = RecallClient()
    assert c.validate_meeting_url("https://meet.google.com/abc-defg-hij")


def test_reject_arbitrary_url() -> None:
    c = RecallClient()
    assert not c.validate_meeting_url("https://evil.com/steal-data")
    assert not c.validate_meeting_url("http://localhost:8000/internal")
    assert not c.validate_meeting_url("https://zoom.us.evil.com/j/123")


def test_reject_subdomain_spoofing() -> None:
    c = RecallClient()
    # Attacker registers zoom.us.evil.com
    assert not c.validate_meeting_url("https://zoom.us.evil.com/j/123456789")
    # Attacker uses *.webex.com they control
    assert not c.validate_meeting_url("https://attacker.webex.com/meet/abc")
    # HTTP rejected
    assert not c.validate_meeting_url("http://zoom.us/j/123456789")
    # Localhost rejected
    assert not c.validate_meeting_url("https://localhost/j/123456789")


def test_valid_urls_still_pass() -> None:
    c = RecallClient()
    assert c.validate_meeting_url("https://zoom.us/j/12345678901")
    assert c.validate_meeting_url("https://meet.google.com/abc-defg-hij")
    assert c.validate_meeting_url("https://webex.com/meet/myroom")


def test_missing_api_key_raises() -> None:
    original = os.environ.pop("RECALL_API_KEY", None)
    try:
        with pytest.raises(EnvironmentError):
            RecallClient()
    finally:
        if original is not None:
            os.environ["RECALL_API_KEY"] = original


def test_invalid_bot_id_raises() -> None:
    c = RecallClient()
    with pytest.raises(ValueError):
        asyncio.run(c.bot_get_status("../../etc/passwd"))
